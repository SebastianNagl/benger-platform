"""What an evaluation run grades, shared by the worker and the cost estimate.

The worker's ``run_evaluation`` dispatches one cell per subject (a model
generation or a submitted answer) and each cell calls the judges for the
field pairs it has not graded yet. The cost estimate used to count those
calls with its own copy of the rules and drifted from the worker more than
once. Both now ask :func:`plan_evaluation` which cells a run grades and
:func:`judge_call_counts` how many judge calls those cells make, so the
estimate prices exactly what the run dispatches.

Pure query code over the shared models with a sync ``Session``; no Celery,
no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def _row_has_score(metrics: dict | None) -> bool:
    """A TaskEvaluation row counts as 'already evaluated' if any non-error
    metric carries a numeric value — either as a bare float (legacy shape)
    or under the unified ``{value, method, details, error}`` dict produced
    by SampleEvaluator after the academic-rigor overhaul.

    Without the dict-aware branch, every recently persisted row reads as
    "missing" and ``evaluate_missing_only=True`` silently re-runs every
    successful evaluation — burning API quota and shifting scores via LLM
    nondeterminism. Mirrors ``_coerce_metric_value`` from
    ``services/api/routers/evaluations/results.py``.
    """
    if not metrics:
        return False
    for k, v in metrics.items():
        if k == "error":
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return True
        if isinstance(v, dict):
            inner = v.get("value")
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return True
    return False


def _row_is_terminal_error(metrics: dict | None) -> bool:
    """A row that's been tried and failed in a non-recoverable way must NOT
    be re-tried on the next ``evaluate_missing_only=True`` run. The worker
    writes such rows with the unified ``{value: None, ..., error: "<msg>"}``
    blob shape, OR with a non-None top-level ``error_message`` on the row.

    Without this gate, every retry would re-attempt the same hopeless target,
    accumulate another stub row each time, and (if it's an LLM judge call)
    burn API budget on a call we already know fails. Pairs with
    ``_row_has_score`` — both must be considered when populating the
    "already evaluated" set in missing-only logic.
    """
    if not metrics:
        return False
    for k, v in metrics.items():
        if k == "error":
            continue
        if isinstance(v, dict) and v.get("error"):
            return True
    return False


def _normalize_field_key(field_name: str | None, *, is_annotation: bool) -> str | None:
    """Normalize a stored ``TaskEvaluation.field_name`` to the canonical
    pipe format ``{config_id}|{pred_field}|{ref_field}`` so missing-only
    matching tolerates legacy colon-separated rows and rows missing the
    ``human:`` annotation prefix.

    The worker has changed the separator from ``:`` to ``|`` and the
    annotation prefix convention at least once; without this normalization,
    rows persisted before the change get classified as "missing" and
    re-evaluated on every missing-only run — wasting API quota and
    polluting score history with duplicates under the new format.

    Bare legacy names (e.g. ``'loesung'``) without a separator are returned
    unchanged: recovering ``config_id`` requires project context that this
    helper doesn't have. The matching backfill ``migrate_field_names.py``
    should be run once per project to bring those rows up to canonical.
    """
    if not field_name:
        return field_name
    if "|" in field_name:
        parts = field_name.split("|")
    elif ":" in field_name:
        parts = field_name.split(":")
    else:
        return field_name  # bare legacy — caller should have backfilled
    if len(parts) != 3:
        return field_name
    cfg, pred, ref = parts
    if is_annotation and not pred.startswith("human:") and not pred.startswith("model:"):
        pred = f"human:{pred}"
    return f"{cfg}|{pred}|{ref}"


def _pred_field_matches(row_field_name: str | None, config_pred_field: str) -> bool:
    """Does a stored *bare* ``TaskEvaluation.field_name`` correspond to a
    config's ``prediction_fields`` entry, for missing-only key reconstruction?

    Immediate eval persists the BARE prediction field as ``field_name`` (e.g.
    ``"human:loesung"`` or ``"loesung"`` — see the immediate-eval block in
    ``run_single_sample_evaluation``), whereas the missing-only matcher keys on
    the 3-part ``{config_id}|{pred}|{ref}`` form. 3-part rows are already handled
    by :func:`_normalize_field_key`; this helper only bridges the bare form so a
    row whose ``evaluation_config_id`` is known can be mapped back to the exact
    expected key. The ``human:``/``model:`` role prefix is tolerated on either
    side so a bare ``"loesung"`` row matches a ``"human:loesung"`` config field.
    """
    if not row_field_name:
        return False
    # 3-part rows are the _normalize_field_key path, not this one.
    if "|" in row_field_name:
        return False

    from eval_field_classification import same_field

    return same_field(row_field_name, config_pred_field)


def _reconstruct_expected_keys(row, configs_by_id: dict) -> set:
    """Expected-key strings an existing ``TaskEvaluation`` row satisfies, derived
    from its discrete ``evaluation_config_id`` (Issue #111 / migration 057).

    Immediate eval stores a bare ``field_name`` that the 3-part missing-only
    matcher misses, but it also stores ``evaluation_config_id``; from that we
    rebuild the exact ``{config_id}|{pred}|{ref}`` strings that
    ``all_expected_field_keys`` is built from, so an immediate-graded unit counts
    as "done" without changing what immediate writes. Returns an empty set when
    the row carries no config id, or a config id not among the current run's
    configs (a re-saved config gets a new id — those rows aren't recognized).

    Wildcard prediction fields (``__all_human__``/``__all_model__``) are skipped:
    the expected set holds the literal wildcard string while rows hold the
    expanded field, so wildcard configs are a pre-existing missing-only
    limitation this must not silently change.
    """
    keys: set = set()
    cfg = configs_by_id.get(getattr(row, "evaluation_config_id", None))
    if not cfg:
        return keys
    for pf in cfg.get("prediction_fields", []):
        if pf in ("__all_human__", "__all_model__"):
            continue
        if _pred_field_matches(row.field_name, pf):
            for rf in cfg.get("reference_fields", []):
                keys.add(f"{cfg.get('id', 'unknown')}|{pf}|{rf}")
    return keys


# Statuses of the runs whose rows count as "already graded" for missing-only.
_COUNTED_RUN_STATUSES = ("completed", "running", "pending", "cancelled", "paused")


def resolve_judges(params: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The judges a config runs, as ``[{judge_model_id, runs}, ...]``.

    ``metric_parameters.judges`` when set, else the legacy single-judge keys,
    else the platform default judge. ``or``, not a .get default: writers also
    store the keys with a null or empty value.
    """
    params = params or {}
    judges = params.get("judges")
    if isinstance(judges, list) and judges:
        return judges
    from model_defaults import DEFAULT_JUDGE_MODEL_ID

    legacy = params.get("judge_model") or DEFAULT_JUDGE_MODEL_ID
    runs = int(params.get("runs_per_judge", 1) or 1)
    return [{"judge_model_id": legacy, "runs": runs}]


def judge_runs(config: Dict[str, Any]) -> List[Tuple[str, int]]:
    """``(judge_model_id, runs)`` per judge of an ``llm_judge_*`` config, with
    the same defaults the worker applies when it sets up the judge runs."""
    from model_defaults import DEFAULT_JUDGE_MODEL_ID

    out: List[Tuple[str, int]] = []
    for entry in resolve_judges(config.get("metric_parameters")):
        judge = (entry or {}).get("judge_model_id") or DEFAULT_JUDGE_MODEL_ID
        out.append((judge, max(1, int((entry or {}).get("runs", 1) or 1))))
    return out


@dataclass
class EvaluationPlan:
    """The cells one evaluation run grades, plus the pool counts its
    diagnostics need. A cell is ``(task_id, subject_id, already_done_keys)``."""

    task_ids: List[str]
    config_sides: List[dict]
    classifier_unavailable: bool
    gen_cells: List[tuple] = field(default_factory=list)
    ann_cells: List[tuple] = field(default_factory=list)
    gen_pool_scoped: int = 0
    ann_pool_scoped: int = 0
    ann_pre_filter: int = 0
    generation_filters_active: bool = False
    all_expected_field_keys: Set[str] = field(default_factory=set)


def _classify_config_sides(enabled_configs: Sequence[dict]) -> Tuple[List[dict], bool]:
    """Which side (submitted answers, model generations) each config grades."""
    try:
        from eval_field_classification import classify_pred_fields

        sides = []
        for c in enabled_configs:
            metric = c.get("metric", "") or ""
            pred = c.get("prediction_fields", []) or []
            if metric.startswith("korrektur_"):
                human_pfs, llm_pfs = [], []
            else:
                human_pfs, llm_pfs = classify_pred_fields(metric, pred)
            sides.append({
                "config_id": c.get("id") or metric or "unknown",
                "metric": metric,
                "display_name": c.get("display_name"),
                "human_fields": list(human_pfs),
                "llm_fields": list(llm_pfs),
            })
        return sides, False
    except Exception:
        # The worker cannot tell which side to grade; reported as a blocking
        # reason instead of silently grading nothing.
        return [
            {
                "config_id": c.get("id") or c.get("metric") or "unknown",
                "metric": c.get("metric", "") or "",
                "display_name": c.get("display_name"),
                "human_fields": [],
                "llm_fields": [],
            }
            for c in enabled_configs
        ], True


def _graded_keys(db, subject_col, task_ids, configs_by_id, *, is_annotation) -> Dict[str, set]:
    """Field keys already graded per subject (missing-only skip set). Rows
    with a score or a terminal error count, so hopeless retries are skipped."""
    from models import EvaluationRun, TaskEvaluation

    rows = (
        db.query(
            subject_col,
            TaskEvaluation.field_name,
            TaskEvaluation.metrics,
            TaskEvaluation.evaluation_config_id,
        )
        .join(EvaluationRun, TaskEvaluation.evaluation_id == EvaluationRun.id)
        .filter(
            TaskEvaluation.task_id.in_(task_ids),
            subject_col.isnot(None),
            EvaluationRun.status.in_(_COUNTED_RUN_STATUSES),
        )
        .all()
    )
    done_by_subject: Dict[str, set] = {}
    for r in rows:
        if _row_has_score(r.metrics) or _row_is_terminal_error(r.metrics):
            done = done_by_subject.setdefault(r[0], set())
            done.add(_normalize_field_key(r.field_name, is_annotation=is_annotation))
            # Bare-field_name rows (immediate eval) via their discrete
            # evaluation_config_id.
            done |= _reconstruct_expected_keys(r, configs_by_id)
    return done_by_subject


def plan_evaluation(
    db,
    project_id: str,
    enabled_configs: Sequence[dict],
    *,
    task_ids: Optional[List[str]] = None,
    model_ids: Optional[List[str]] = None,
    annotator_user_ids: Optional[List[str]] = None,
    structure_keys: Optional[List[str]] = None,
    label_config_version: Optional[str] = None,
    missing_only: bool = True,
) -> EvaluationPlan:
    """Enumerate the cells a run over ``enabled_configs`` grades.

    Scope filters narrow the subjects: ``task_ids``; ``model_ids``,
    ``structure_keys`` and ``label_config_version`` the generations;
    ``annotator_user_ids`` the answers. An explicitly empty ``model_ids`` or
    ``annotator_user_ids`` (not None) deselects that side ("model generations
    only"), which also covers plain fields that grade both sides. Under
    ``missing_only`` a subject whose expected field keys are all graded is
    left out; the rest carry their graded keys so the cell skips them.
    """
    from models import Generation, ResponseGeneration
    from project_models import Annotation, Task

    tq = db.query(Task.id).filter(Task.project_id == project_id)
    if task_ids:
        tq = tq.filter(Task.id.in_(task_ids))
    run_task_ids = [r[0] for r in tq.all()]

    config_sides, classifier_unavailable = _classify_config_sides(enabled_configs)
    plan = EvaluationPlan(
        task_ids=run_task_ids,
        config_sides=config_sides,
        classifier_unavailable=classifier_unavailable,
        generation_filters_active=bool(label_config_version or model_ids or structure_keys),
        all_expected_field_keys={
            f"{c.get('id', 'unknown')}|{pf}|{rf}"
            for c in enabled_configs
            for pf in c.get("prediction_fields", [])
            for rf in c.get("reference_fields", [])
        },
    )
    if not run_task_ids:
        return plan

    skip_generations = model_ids is not None and len(model_ids) == 0
    skip_annotations = annotator_user_ids is not None and len(annotator_user_ids) == 0
    if skip_generations or skip_annotations:
        for side in config_sides:
            had_fields = bool(side["human_fields"] or side["llm_fields"])
            if skip_annotations:
                side["human_fields"] = []
            if skip_generations:
                side["llm_fields"] = []
            if had_fields and not (side["human_fields"] or side["llm_fields"]):
                side["side_not_selected"] = True

    has_human_config = any(s["human_fields"] for s in config_sides)
    has_llm_config = any(s["llm_fields"] for s in config_sides)
    configs_by_id = {c.get("id", "unknown"): c for c in enabled_configs}
    expected = plan.all_expected_field_keys

    def _keep(done: set) -> bool:
        return not (missing_only and expected and expected.issubset(done))

    if has_llm_config:
        from models import TaskEvaluation

        uses_all_model = any(
            "__all_model__" in c.get("prediction_fields", []) for c in enabled_configs
        )
        gq = db.query(Generation.id, Generation.task_id).filter(
            Generation.task_id.in_(run_task_ids)
        )
        if not uses_all_model:
            gq = gq.filter(Generation.parse_status == "success")
        if label_config_version:
            gq = gq.filter(Generation.label_config_version == label_config_version)
        if model_ids:
            gq = gq.filter(Generation.model_id.in_(model_ids))
        if structure_keys:
            # SQL IN never matches NULL, so legacy generations without a
            # structure_key are left out of a structure-scoped run.
            gq = gq.join(
                ResponseGeneration, Generation.generation_id == ResponseGeneration.id
            ).filter(ResponseGeneration.structure_key.in_(structure_keys))
        gens = gq.order_by(Generation.task_id, Generation.id).all()
        plan.gen_pool_scoped = len(gens)
        done_by_gen = (
            _graded_keys(db, TaskEvaluation.generation_id, run_task_ids, configs_by_id,
                         is_annotation=False)
            if missing_only else {}
        )
        for gen_id, task_id in gens:
            done = done_by_gen.get(gen_id, set())
            if _keep(done):
                plan.gen_cells.append((task_id, gen_id, sorted(done) if done else []))

    if has_human_config:
        from models import TaskEvaluation

        aq = db.query(Annotation.id, Annotation.task_id).filter(
            Annotation.task_id.in_(run_task_ids),
            Annotation.was_cancelled == False,  # noqa: E712
        )
        plan.ann_pre_filter = aq.count()
        if annotator_user_ids:
            aq = aq.filter(Annotation.completed_by.in_(annotator_user_ids))
        anns = aq.order_by(Annotation.task_id, Annotation.id).all()
        plan.ann_pool_scoped = len(anns)
        done_by_ann = (
            _graded_keys(db, TaskEvaluation.annotation_id, run_task_ids, configs_by_id,
                         is_annotation=True)
            if missing_only else {}
        )
        for ann_id, task_id in anns:
            done = done_by_ann.get(ann_id, set())
            if _keep(done):
                plan.ann_cells.append((task_id, ann_id, sorted(done) if done else []))

    return plan


def judge_call_counts(plan: EvaluationPlan, enabled_configs: Sequence[dict]) -> Dict[str, int]:
    """LLM judge calls per judge model that the plan's cells make.

    Mirrors the cell evaluators (``evaluation/cell_evaluator.py``): a
    generation cell grades every non-human prediction field of every config,
    an answer cell the config's human fields; each (config, prediction,
    reference) pair the cell has not graded yet costs one call per judge run.
    Fields missing from a given answer or generation at run time are skipped
    there and can make the run slightly cheaper than this count.
    """
    from eval_field_classification import classify_pred_fields

    counts: Dict[str, int] = {}
    judged = [
        c for c in enabled_configs if (c.get("metric") or "").startswith("llm_judge_")
    ]
    if not judged:
        return counts

    def _add(config, keys, done_normalized, is_annotation):
        judges = judge_runs(config)
        for key in keys:
            if _normalize_field_key(key, is_annotation=is_annotation) in done_normalized:
                continue
            for judge, runs in judges:
                counts[judge] = counts.get(judge, 0) + runs

    gen_keys = {}
    ann_keys = {}
    for c in judged:
        cid = c.get("id", "unknown")
        refs = c.get("reference_fields", [])
        preds = c.get("prediction_fields", [])
        gen_keys[cid] = [
            f"{cid}|{pf}|{rf}"
            for pf in preds
            if not (pf.startswith("human:") or pf == "__all_human__")
            for rf in refs
        ]
        human, _llm = classify_pred_fields(c.get("metric"), preds)
        prefixed = [
            pf if pf.startswith("human:") or pf == "__all_human__" else f"human:{pf}"
            for pf in human
        ]
        ann_keys[cid] = [f"{cid}|{pf}|{rf}" for pf in prefixed for rf in refs]

    for _task_id, _gen_id, done in plan.gen_cells:
        done_n = {_normalize_field_key(k, is_annotation=False) for k in done}
        for c in judged:
            _add(c, gen_keys[c.get("id", "unknown")], done_n, False)
    for _task_id, _ann_id, done in plan.ann_cells:
        done_n = {_normalize_field_key(k, is_annotation=True) for k in done}
        for c in judged:
            _add(c, ann_keys[c.get("id", "unknown")], done_n, True)
    return counts
