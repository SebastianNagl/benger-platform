"""Whether a stored grading still rests on the basis its task is graded on now.

A grading rests on two things that a teacher can change after it was
written: the grading sheet of the task (a ``task_rubrics`` row; a sheet that
already graded is never edited in place, an edit activates a clone) and the
grading scheme of its evaluation config (the criteria, prompt or barème in
the config's ``metric_parameters``). This module tells an outdated grading
from a current one, so a teacher can see how many gradings an edit affected
and re-grade exactly those (``evaluation_planning.plan_evaluation(...,
outdated_only=True)``).

What a row records (its basis stamps), in the details of the config's
metric: ``metrics[<metric>]["details"]`` for the ``{value, method, details}``
shape, else the flat sibling ``metrics["<metric>_details"]``:

* ``rubric_id``: the sheet the row was graded along (written by every sheet
  grading since the sheets exist).
* ``scheme_fingerprint``: :func:`scheme_fingerprint` of the config that
  graded it (written by the worker on every judge row since core 2.84, and
  by an overlay's own writers through :func:`stamp_grading_basis`).

The rule (:func:`outdated_reason`), for the current row of a cell
(``current_scores``; a human grader's own row for human-graded methods):

* ``sheet``: the row records a sheet and the task would now be graded along
  another one (``task_rubric_resolution``). A task without a usable sheet
  now cannot be re-graded and does not count.
* ``scheme``: the row's fingerprint differs from the config's current one.
  A row written before fingerprints existed counts as current unless the
  package owning its metric answers otherwise (``legacy_outdated`` of
  :func:`register_grading_basis`).

Which parameters are a method's scheme: :data:`JUDGE_SCHEME_KEYS` for every
``llm_judge_*`` metric, unless an extension package registered the metric
(:func:`register_grading_basis`, at import time in the api and the workers
process, owner-tracked; while the package is off for the caller, GATED,
the metric is not tracked at all). Other metrics have no scheme: a
deterministic metric or an unregistered human method never becomes
outdated through its parameters. Only add keys to a list: a key a config
does not set is left out of the fingerprint, so a new key changes nothing
for configs that do not use it, while a removed key would flag every row
of the configs that set it.

Re-grade runs (``eval_metadata.regrade``) write each row of a submitted
answer as a draft (``details.review = {"status": "draft", "reason":
"regrade"}``) that a teacher releases, whatever the method; a model
generation has nobody to release it to and keeps no review.
``metric_filters.row_awaits_release`` keeps the grading notices from
announcing such a draft.

Held gradings (core 2.92): a config whose ``metric_parameters`` say
``auto_release: false`` holds the AI grading of a submission for a
teacher, on submit and in batch runs. Each row of a submitted answer of
such a config that did not fail is written as a draft
(``details.review = {"status": "draft", "reason": "held"}``,
:func:`held_review`). On submit, the immediate-eval worker's platform
writers store it in the commit that writes the row, an overlay writer's
row gets it right after the writer returns, and a failed run's committed
rows get it before the run is marked failed. A batch run stamps its row
dicts before the cell writes them (:func:`stamp_rows`); a re-grade run
writes its re-grade draft instead, and a model generation's row is never
held, there is nobody to release it to. A batch run over an answer that
already has a released grading writes a held draft next to it, which
readers skip until a teacher releases it. :func:`holds_first_grading`
tells an overlay writer whose config holds, so it can store the draft in
its own commit. A row whose writer already stored a review (an overlay judge that
holds or releases by itself) keeps it. A config without the key, or with
``auto_release: true``, releases as before. The rule is the same
for every method: the platform knows no judge-specific release policy.

Sync ``Session`` code over the shared models; the api runs it in the
threadpool or through ``run_sync``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

RUBRIC_ID_KEY = "rubric_id"
FINGERPRINT_KEY = "scheme_fingerprint"
REVIEW_KEY = "review"
REVIEW_DRAFT = "draft"
REGRADE_REASON = "regrade"
#: ``review.reason`` of a grading on submit its config holds for a teacher.
HELD_REASON = "held"
#: The ``metric_parameters`` key that says whether a config releases its
#: grading on submit to the student by itself (absent: it does).
AUTO_RELEASE_KEY = "auto_release"

#: Why a row is outdated (:func:`outdated_reason`).
REASON_SHEET = "sheet"
REASON_SCHEME = "scheme"
REASONS = (REASON_SHEET, REASON_SCHEME)

#: ``metric_parameters`` keys that make up the grading scheme of a platform
#: LLM judge: what it grades on (dimensions, criteria, prompt template, field
#: mappings, answer type) and how it scores (scale, sheet unit, sheet use).
#: The judge model, temperature, seeds and runs are not part of it.
JUDGE_SCHEME_KEYS: Tuple[str, ...] = (
    "dimensions",
    "custom_criteria",
    "custom_prompt_template",
    "answer_type",
    "field_mappings",
    "score_scale",
    "rubric_score_unit",
    "use_task_rubric",
)

#: Values the worker applies when a key is not set; a config that sets one
#: explicitly grades exactly like one that leaves it out.
_SCHEME_DEFAULTS: Dict[str, Any] = {"score_scale": "1-5", "use_task_rubric": False}

LegacyOutdated = Callable[[Dict[str, Any], Dict[str, Any]], Optional[bool]]


@dataclass(frozen=True)
class GradingBasisSpec:
    """What a package declared for one metric (:func:`register_grading_basis`)."""

    scheme_keys: Tuple[str, ...]
    legacy_keys: Tuple[str, ...] = ()
    legacy_outdated: Optional[LegacyOutdated] = None
    owner: Optional[str] = None


_SPECS: Dict[str, GradingBasisSpec] = {}


def _registration_owner() -> Optional[str]:
    try:
        from extension_registry import current_owner
    except ImportError:  # pragma: no cover - /shared without the registry
        return None
    return current_owner()


def _owner_active(owner: Optional[str]) -> bool:
    if not owner:
        return True
    try:
        import extension_activation
    except ImportError:  # pragma: no cover
        return True
    return extension_activation.package_active(owner)


def register_grading_basis(
    metric: str,
    *,
    scheme_keys: Iterable[str],
    legacy_keys: Iterable[str] = (),
    legacy_outdated: Optional[LegacyOutdated] = None,
) -> None:
    """Declare the grading scheme of ``metric``: the ``metric_parameters``
    keys :func:`scheme_fingerprint` hashes (replacing
    :data:`JUDGE_SCHEME_KEYS` for an ``llm_judge_*`` metric).

    ``legacy_outdated(stored, config)`` answers for a row written without a
    fingerprint: ``stored`` holds the row's details under ``legacy_keys``
    (only those leave the database), ``config`` is the current config; True
    is outdated, False or None current. Re-registering replaces the entry
    (reload-safe in dev); a replacement by another package is logged.
    """
    owner = _registration_owner()
    held = _SPECS.get(metric)
    if held is not None and held.owner != owner:
        logger.warning(
            "grading basis of %r registered by %s replaces %s's",
            metric,
            owner or "the platform",
            held.owner or "the platform",
        )
    _SPECS[metric] = GradingBasisSpec(
        scheme_keys=tuple(scheme_keys),
        legacy_keys=tuple(legacy_keys),
        legacy_outdated=legacy_outdated,
        owner=owner,
    )


def unregister_grading_basis(metric: str) -> None:
    _SPECS.pop(metric, None)


def _active_spec(metric: Optional[str]) -> Tuple[bool, Optional[GradingBasisSpec]]:
    """``(registered, spec)``: ``spec`` is None while the owner is off."""
    if not metric or metric not in _SPECS:
        return False, None
    spec = _SPECS[metric]
    return True, spec if _owner_active(spec.owner) else None


def scheme_keys_for(metric: Optional[str]) -> Optional[Tuple[str, ...]]:
    """The scheme keys of ``metric``, None for a metric without a scheme."""
    registered, spec = _active_spec(metric)
    if registered:
        return spec.scheme_keys if spec is not None else None
    if isinstance(metric, str) and metric.startswith("llm_judge_"):
        return JUDGE_SCHEME_KEYS
    return None


def _meaningful(key: str, value: Any) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return False
    return not (key in _SCHEME_DEFAULTS and value == _SCHEME_DEFAULTS[key])


def scheme_fingerprint(config: Any) -> Optional[str]:
    """A stable hash of the config's grading scheme, None when its metric
    has none (:func:`scheme_keys_for`). Keys the config does not set, or
    sets to the worker's default, are left out."""
    if not isinstance(config, Mapping):
        return None
    keys = scheme_keys_for(config.get("metric"))
    if keys is None:
        return None
    params = config.get("metric_parameters")
    params = params if isinstance(params, Mapping) else {}
    scheme = {key: params[key] for key in keys if key in params and _meaningful(key, params[key])}
    payload = json.dumps(scheme, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def details_key(metric: str) -> str:
    """The flat sibling that carries a flat row's details."""
    return f"{metric}_details"


def metric_details(metrics: Any, metric: Optional[str]) -> Optional[Dict[str, Any]]:
    """The details of ``metric`` in a row's metrics (see the module doc)."""
    if not isinstance(metrics, Mapping) or not metric:
        return None
    blob = metrics.get(metric)
    if isinstance(blob, Mapping):
        details = blob.get("details")
        return dict(details) if isinstance(details, Mapping) else None
    sibling = metrics.get(details_key(metric))
    return dict(sibling) if isinstance(sibling, Mapping) else None


def regrade_review() -> Dict[str, Any]:
    """The review a re-graded row starts with: an unreviewed draft."""
    return {"status": REVIEW_DRAFT, "reason": REGRADE_REASON}


def held_review() -> Dict[str, Any]:
    """The review a held grading on submit starts with: an unreviewed draft
    (:func:`holds_first_grading`)."""
    return {"status": REVIEW_DRAFT, "reason": HELD_REASON}


def holds_first_grading(config: Any) -> bool:
    """Whether ``config`` holds its grading on submit for a teacher: its
    ``metric_parameters`` set ``auto_release`` to exactly ``False``. A
    config without the key releases on submit, as every config did before
    core 2.92. A method a person grades has no grading on submit."""
    if not isinstance(config, Mapping) or is_human_method(config.get("metric")):
        return False
    params = config.get("metric_parameters")
    return isinstance(params, Mapping) and params.get(AUTO_RELEASE_KEY) is False


def stamp_grading_basis(
    metrics: Any, config: Any, *, regrade: bool = False, on_submit: bool = False
) -> Any:
    """``metrics`` with the config's fingerprint stamped into the details of
    its metric and the draft review on a result that did not fail: for
    ``regrade`` always (:func:`regrade_review`), for ``on_submit`` (an AI
    grading of a submitted answer, on submit or in a batch run) when the
    config holds it (:func:`holds_first_grading`,
    :func:`held_review`) and the writer stored no review of its own. Returns
    ``metrics`` itself when there is nothing to stamp (a method without a
    scheme and no draft, a row that holds no result of the config's
    metric); otherwise a copy, the input is never changed.
    """
    if not isinstance(metrics, Mapping) or not isinstance(config, Mapping):
        return metrics
    metric = config.get("metric")
    if not isinstance(metric, str) or metric not in metrics:
        return metrics
    fingerprint = scheme_fingerprint(config)
    blob = metrics.get(metric)
    # A failed result (an error blob, or a flat row without a score) holds
    # nothing to release.
    failed = blob is None or (isinstance(blob, Mapping) and bool(blob.get("error")))
    draft: Optional[Dict[str, Any]] = None
    if regrade and not failed:
        draft = regrade_review()
    elif (
        on_submit
        and not failed
        and holds_first_grading(config)
        and not isinstance((metric_details(metrics, metric) or {}).get(REVIEW_KEY), Mapping)
    ):
        draft = held_review()
    if fingerprint is None and draft is None:
        return metrics
    out = dict(metrics)
    if isinstance(blob, Mapping):
        blob = dict(blob)
        details = dict(blob.get("details") or {}) if isinstance(blob.get("details"), Mapping) else {}
    else:
        sibling = metrics.get(details_key(metric))
        details = dict(sibling) if isinstance(sibling, Mapping) else {}
    if fingerprint is not None:
        details[FINGERPRINT_KEY] = fingerprint
    if draft is not None:
        details[REVIEW_KEY] = draft
    if isinstance(blob, dict):
        blob["details"] = details
        out[metric] = blob
    else:
        out[details_key(metric)] = details
    return out


def stamp_rows(
    rows: Iterable[Dict[str, Any]], configs: Iterable[Mapping[str, Any]], *, regrade: bool = False
) -> None:
    """Stamp the bulk row dicts of one cell in place (``metrics`` of each
    row, by its ``evaluation_config_id``). Only rows of a submitted answer
    become drafts: re-grade drafts in a re-grade run, held drafts of a
    config that holds its AI grading (:func:`holds_first_grading`)
    otherwise."""
    by_id = {str(c.get("id")): c for c in configs or () if isinstance(c, Mapping) and c.get("id")}
    for row in rows or ():
        config = by_id.get(str(row.get("evaluation_config_id")))
        if config is None:
            continue
        answer = bool(row.get("annotation_id"))
        row["metrics"] = stamp_grading_basis(
            row.get("metrics"), config, regrade=regrade and answer, on_submit=answer
        )


def outdated_reason(
    stored: Optional[Mapping[str, Any]],
    config: Mapping[str, Any],
    *,
    current_rubric_id: Optional[str],
    current_fingerprint: Optional[str],
) -> Optional[str]:
    """Why a row with the basis stamps ``stored`` is outdated for
    ``config`` (:data:`REASON_SHEET`, :data:`REASON_SCHEME`), None when it is
    current. ``stored`` holds the row's ``rubric_id``,
    ``scheme_fingerprint`` and the metric's ``legacy_keys``."""
    if not isinstance(stored, Mapping):
        return None
    stored_rubric = stored.get(RUBRIC_ID_KEY)
    if stored_rubric and current_rubric_id and str(stored_rubric) != str(current_rubric_id):
        return REASON_SHEET
    stored_fingerprint = stored.get(FINGERPRINT_KEY)
    if stored_fingerprint:
        if current_fingerprint and stored_fingerprint != current_fingerprint:
            return REASON_SCHEME
        return None
    _registered, spec = _active_spec(config.get("metric"))
    if spec is None or spec.legacy_outdated is None:
        return None
    subset = {key: stored.get(key) for key in spec.legacy_keys}
    try:
        verdict = spec.legacy_outdated(subset, dict(config))
    except Exception:
        logger.exception("legacy grading basis check of %s failed", config.get("metric"))
        return None
    return REASON_SCHEME if verdict is True else None


# --------------------------------------------------------------------------- #
# The current rows of a project and their verdicts
# --------------------------------------------------------------------------- #
@dataclass
class BasisRow:
    """The current row of one cell (of one grader for a human method)."""

    row_id: str
    task_id: str
    config_id: str
    cell: Tuple[str, str, str, str, str]
    field_key: Optional[str]
    grader_id: Optional[str]
    reason: Optional[str] = None

    @property
    def subject(self) -> Tuple[str, str]:
        return self.cell[0], self.cell[1]

    @property
    def outdated(self) -> bool:
        return self.reason is not None


@dataclass
class ConfigBasis:
    """The current rows of one config, with their verdicts."""

    config_id: str
    metric: str
    display_name: Optional[str]
    human: bool
    rows: List[BasisRow] = field(default_factory=list)

    @property
    def outdated_rows(self) -> List[BasisRow]:
        return [row for row in self.rows if row.outdated]

    def reason_counts(self) -> Dict[str, int]:
        counts = {reason: 0 for reason in REASONS}
        for row in self.outdated_rows:
            counts[row.reason] = counts.get(row.reason, 0) + 1
        return counts


def is_human_method(metric: Optional[str]) -> bool:
    """A method a person grades (one row per grader and subject)."""
    return isinstance(metric, str) and metric.startswith("korrektur_")


def config_is_tracked(config: Mapping[str, Any]) -> bool:
    """Whether rows of ``config`` can be outdated: its method has a scheme,
    it grades along the task's sheet, or a person grades it (human rows
    record the sheet they were graded along). A feedback-only human method
    (peer review) is feedback, never a grade, and is not tracked."""
    from human_graded_metrics import is_feedback_only_human_metric
    from task_rubric_resolution import is_rubric_judge

    metric = config.get("metric")
    if is_feedback_only_human_metric(metric):
        return False
    return (
        scheme_keys_for(metric) is not None
        or is_rubric_judge(dict(config))
        or is_human_method(metric)
    )


# Stand-in metrics of a row the SQL already found scored, so the current-row
# ranking (current_scores.pick_current) needs no blob for it.
_SCORED_STANDIN = {"score": 1.0}
_FETCH_CHUNK = 1000


def _stamp_column(metric: str, key: str, *, as_text: bool):
    from sqlalchemy import func

    from models import TaskEvaluation

    nested = TaskEvaluation.metrics[metric]["details"][key]
    flat = TaskEvaluation.metrics[details_key(metric)][key]
    if as_text:
        return func.coalesce(nested.astext, flat.astext)
    return func.coalesce(nested, flat)


def _config_rows(db, config: Mapping[str, Any], task_scope) -> List[Dict[str, Any]]:
    """Small fields of every counted row of ``config`` in ``task_scope``."""
    from sqlalchemy import and_, literal_column, or_

    from evaluation_planning import _COUNTED_RUN_STATUSES, _SCORED_METRICS_SQL
    from models import EvaluationRun, TaskEvaluation

    config_id = str(config.get("id"))
    metric = str(config.get("metric") or "")
    _registered, spec = _active_spec(metric)
    legacy_keys = spec.legacy_keys if spec is not None and spec.legacy_outdated else ()
    columns = [
        TaskEvaluation.id,
        TaskEvaluation.task_id,
        TaskEvaluation.generation_id,
        TaskEvaluation.annotation_id,
        TaskEvaluation.field_name,
        TaskEvaluation.evaluation_config_id,
        TaskEvaluation.created_at,
        TaskEvaluation.created_by,
        literal_column(_SCORED_METRICS_SQL).label("scored"),
        _stamp_column(metric, RUBRIC_ID_KEY, as_text=True).label("rubric_id"),
        _stamp_column(metric, FINGERPRINT_KEY, as_text=True).label("fingerprint"),
    ]
    columns += [
        _stamp_column(metric, key, as_text=False).label(f"legacy_{i}")
        for i, key in enumerate(legacy_keys)
    ]
    escaped = config_id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    result = (
        db.query(*columns)
        .join(EvaluationRun, TaskEvaluation.evaluation_id == EvaluationRun.id)
        .filter(
            TaskEvaluation.task_id.in_(task_scope),
            EvaluationRun.status.in_(_COUNTED_RUN_STATUSES),
            or_(
                TaskEvaluation.evaluation_config_id == config_id,
                and_(
                    TaskEvaluation.evaluation_config_id.is_(None),
                    TaskEvaluation.field_name.like(f"{escaped}|%|%", escape="\\"),
                ),
            ),
        )
        .all()
    )
    rows = []
    for r in result:
        stored = {RUBRIC_ID_KEY: r.rubric_id, FINGERPRINT_KEY: r.fingerprint}
        for i, key in enumerate(legacy_keys):
            stored[key] = getattr(r, f"legacy_{i}")
        rows.append(
            {
                "id": r.id,
                "task_id": r.task_id,
                "generation_id": r.generation_id,
                "annotation_id": r.annotation_id,
                "field_name": r.field_name,
                "evaluation_config_id": r.evaluation_config_id,
                "created_at": r.created_at,
                "created_by": r.created_by,
                "scored": bool(r.scored),
                "stored": stored,
            }
        )
    unscored = [row["id"] for row in rows if not row["scored"]]
    blobs: Dict[str, Any] = {}
    for i in range(0, len(unscored), _FETCH_CHUNK):
        chunk = unscored[i : i + _FETCH_CHUNK]
        blobs.update(
            db.query(TaskEvaluation.id, TaskEvaluation.metrics)
            .filter(TaskEvaluation.id.in_(chunk))
            .all()
        )
    for row in rows:
        row["rank_metrics"] = _SCORED_STANDIN if row["scored"] else blobs.get(row["id"])
    return rows


def _current_rows(rows: List[Dict[str, Any]], configs_by_id, *, human: bool) -> List[Dict[str, Any]]:
    from current_scores import pick_current

    if not human:
        return list(pick_current(rows, configs_by_id, metrics_attr="rank_metrics").values())
    by_grader: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for row in rows:
        by_grader.setdefault(row.get("created_by"), []).append(row)
    current: List[Dict[str, Any]] = []
    for group in by_grader.values():
        current.extend(pick_current(group, configs_by_id, metrics_attr="rank_metrics").values())
    return current


def _current_rubric_ids(db, task_ids: Sequence[str], config: Mapping[str, Any]) -> Dict[str, str]:
    from task_rubric_resolution import resolve_grading_rubric_ids

    if not task_ids:
        return {}
    return resolve_grading_rubric_ids(db, list(task_ids), config.get("metric_parameters"))


def _task_scope(db, project_id: str, task_ids: Optional[Sequence[str]]):
    from project_models import Task

    query = db.query(Task.id).filter(Task.project_id == project_id)
    if task_ids:
        query = query.filter(Task.id.in_(list(task_ids)))
    return query.scalar_subquery()


def grading_basis_by_config(
    db,
    project_id: str,
    configs: Iterable[Mapping[str, Any]],
    *,
    task_ids: Optional[Sequence[str]] = None,
    task_scope=None,
) -> List[ConfigBasis]:
    """The current rows of every tracked config (:func:`config_is_tracked`)
    among ``configs`` and whether each is outdated. ``task_ids`` (or a
    ``task_scope`` subquery of task ids) narrows the tasks; the project's
    tasks otherwise. Configs are taken as they are now: their fingerprint and
    sheet selector are what the rows are measured against."""
    from current_scores import cell_key
    from evaluation_planning import _normalize_field_key

    config_list = [
        dict(c) for c in configs or ()
        if isinstance(c, Mapping) and c.get("id") and c.get("enabled", True) is not False
    ]
    by_id = {str(c["id"]): c for c in config_list}
    scope = task_scope if task_scope is not None else _task_scope(db, project_id, task_ids)
    out: List[ConfigBasis] = []
    for config in config_list:
        if not config_is_tracked(config):
            continue
        metric = str(config.get("metric") or "")
        human = is_human_method(metric)
        rows = _current_rows(_config_rows(db, config, scope), by_id, human=human)
        fingerprint = scheme_fingerprint(config)
        sheet_tasks = sorted({row["task_id"] for row in rows if row["stored"].get(RUBRIC_ID_KEY)})
        rubric_ids = _current_rubric_ids(db, sheet_tasks, config)
        basis = ConfigBasis(
            config_id=str(config["id"]),
            metric=metric,
            display_name=config.get("display_name"),
            human=human,
        )
        for row in rows:
            key = cell_key(row, by_id)
            basis.rows.append(
                BasisRow(
                    row_id=str(row["id"]),
                    task_id=str(row["task_id"]),
                    config_id=str(config["id"]),
                    cell=key,
                    field_key=_normalize_field_key(
                        row.get("field_name"), is_annotation=key[0] == "annotation"
                    ),
                    grader_id=row.get("created_by") if human else None,
                    reason=outdated_reason(
                        row["stored"],
                        config,
                        current_rubric_id=rubric_ids.get(str(row["task_id"])),
                        current_fingerprint=fingerprint,
                    ),
                )
            )
        out.append(basis)
    return out


def outdated_gradings_summary(db, project) -> Dict[str, Any]:
    """Per config of the project, how many current gradings rest on an older
    basis: ``{"total", "ai", "human", "configs": [{"config_id", "metric",
    "display_name", "human", "graded", "outdated", "reasons": {"sheet",
    "scheme"}}]}``. ``graded`` counts the current rows the verdict ran on."""
    from current_scores import configs_by_id

    configs = list(configs_by_id(getattr(project, "evaluation_config", None)).values())
    entries = []
    totals = {"ai": 0, "human": 0}
    for basis in grading_basis_by_config(db, project.id, configs):
        outdated = len(basis.outdated_rows)
        totals["human" if basis.human else "ai"] += outdated
        entries.append(
            {
                "config_id": basis.config_id,
                "metric": basis.metric,
                "display_name": basis.display_name,
                "human": basis.human,
                "graded": len(basis.rows),
                "outdated": outdated,
                "reasons": basis.reason_counts(),
            }
        )
    return {
        "total": totals["ai"] + totals["human"],
        "ai": totals["ai"],
        "human": totals["human"],
        "configs": entries,
    }


__all__ = [
    "BasisRow",
    "ConfigBasis",
    "AUTO_RELEASE_KEY",
    "FINGERPRINT_KEY",
    "GradingBasisSpec",
    "HELD_REASON",
    "JUDGE_SCHEME_KEYS",
    "REASONS",
    "REASON_SCHEME",
    "REASON_SHEET",
    "REGRADE_REASON",
    "REVIEW_DRAFT",
    "REVIEW_KEY",
    "RUBRIC_ID_KEY",
    "config_is_tracked",
    "details_key",
    "grading_basis_by_config",
    "held_review",
    "holds_first_grading",
    "is_human_method",
    "metric_details",
    "outdated_gradings_summary",
    "outdated_reason",
    "regrade_review",
    "register_grading_basis",
    "scheme_fingerprint",
    "scheme_keys_for",
    "stamp_grading_basis",
    "stamp_rows",
    "unregister_grading_basis",
]
