"""One current score per evaluation method and subject.

A subject (a submitted answer or a model generation) can carry several
``task_evaluations`` rows of the same evaluation method: the grading on
submit, a later batch run, a forced re-run, rows a multi-reference judge
wrote per reference field before the worker graded it once, or a failed
retry. Every reader that shows "the score" of a method used its own key to
collapse them: the results grid partitioned by ``(subject, field_name)``,
the cell modal deduplicated by ``field_name``, the comprehensive export did
not collapse at all, and the batch skip rule (``evaluation_planning``)
treated the bare ``field_name`` of an on-submit row and the composite
``{config_id}|{pred}|{ref}`` of a batch row as the same cell while the views
did not. This module is the one definition all of them use.

The cell of a row is ``(subject, evaluation config, prediction field,
reference field)``:

* subject: the generation, else the annotation, else the task.
* evaluation config: ``evaluation_config_id``, else the config part of a
  composite ``field_name`` (rows written before migration 057), else ``""``.
* prediction field: the prediction part of a composite ``field_name``, or
  the bare ``field_name`` of an on-submit row, without its ``human:`` /
  ``model:`` role prefix.
* reference field (:func:`cell_ref_field`): ``""`` for a config that grades
  once per prediction field (``metric_filters.graded_reference_fields`` has
  one entry or none, such as a judge that reads its reference fields itself),
  so the rows it wrote per reference field before the worker graded it once
  are one cell. A config that grades once per reference field keeps the
  reference part: those rows are different gradings, each with its own
  current score. A bare on-submit row of such a config belongs to the cell
  of the config's first reference field, the one the on-submit grader
  tries first. A row whose config is unknown (a deleted config) keeps the
  reference part of its composite ``field_name``, so rows that may be
  different gradings are never merged.

On-submit rows written before the label fix carry the config's first
prediction selector even when that selector names model outputs
(``__all_model__``) although the row graded the submitted answer. For an
annotation row with a model-side label the cell takes the config's first
answer-side selector instead (:func:`cell_pred_field`), so those rows meet
the batch rows of the same cell without rewriting stored data.

The current row of a cell is the newest row that carries a score; when no
row of the cell has a score (every attempt failed) the newest row is
current, so the failure stays visible. Older rows are history.

Pure functions over plain rows (ORM objects, SQLAlchemy rows or dicts); the
SQL twins at the end let a query rank rows by the same key.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from eval_field_classification import BULK_SELECTORS, bare_field_name
from evaluation_planning import _row_has_score
from metric_filters import graded_reference_fields
from metric_values import coerce_metric_value

SUBJECT_GENERATION = "generation"
SUBJECT_ANNOTATION = "annotation"
SUBJECT_TASK = "task"

_MODEL_SIDE_SELECTORS = ("__all_model__",)
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

CellKey = Tuple[str, str, str, str, str]


def _get(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _is_composite(field_name: str) -> bool:
    # Same test as the SQL twin (``LIKE '%|%|%'``): two separators or more.
    return field_name.count("|") >= 2


def split_field_name(field_name: Optional[str]) -> Tuple[str, str]:
    """``(config part, prediction part)`` of a stored ``field_name``.

    A composite ``{config_id}|{pred}|{ref}`` yields its first two parts; a
    bare on-submit name yields ``("", field_name)``.
    """
    value = field_name or ""
    if _is_composite(value):
        parts = value.split("|")
        return parts[0], parts[1]
    return "", value


def _is_model_side(selector: str) -> bool:
    return selector in _MODEL_SIDE_SELECTORS or selector.startswith("model:")


def _canonical_pred(selector: str) -> str:
    if selector in BULK_SELECTORS:
        return selector
    return bare_field_name(selector) or selector


def cell_pred_field(
    field_name: Optional[str],
    *,
    is_annotation: bool,
    config: Optional[Mapping[str, Any]] = None,
) -> str:
    """The prediction field of a row's cell, without the role prefix.

    For an annotation row labelled with a model-side selector (the on-submit
    rows written before the label fix), ``config`` supplies the answer-side
    selector the row actually graded: the first of its prediction fields
    that does not name model outputs, the same order the on-submit grader
    tries them in.
    """
    _, pred = split_field_name(field_name)
    if is_annotation and _is_model_side(pred) and config:
        for selector in config.get("prediction_fields") or []:
            if isinstance(selector, str) and selector and not _is_model_side(selector):
                pred = selector
                break
    return _canonical_pred(pred)


def cell_config_id(evaluation_config_id: Optional[str], field_name: Optional[str]) -> str:
    """The evaluation config of a row's cell (``""`` when none is known)."""
    if evaluation_config_id:
        return evaluation_config_id
    config_part, _ = split_field_name(field_name)
    return config_part


def _bare_row_ref(config: Mapping[str, Any]) -> Optional[str]:
    """The reference field of a bare row of a known config: ``""`` for a
    config that grades once per prediction field, else its first reference
    field (whose composite rows keep their own reference part)."""
    refs = graded_reference_fields(config)
    return str(refs[0]) if len(refs) > 1 else ""


def cell_ref_field(field_name: Optional[str], config: Optional[Mapping[str, Any]]) -> str:
    """The reference field of a row's cell (see the module docstring)."""
    value = field_name or ""
    composite = _is_composite(value)
    if config is not None:
        bare_ref = _bare_row_ref(config)
        if bare_ref == "" or not composite:
            return bare_ref
    return value.split("|")[2] if composite else ""


def cell_subject(row: Any) -> Tuple[str, str]:
    generation_id = _get(row, "generation_id")
    if generation_id:
        return SUBJECT_GENERATION, str(generation_id)
    annotation_id = _get(row, "annotation_id")
    if annotation_id:
        return SUBJECT_ANNOTATION, str(annotation_id)
    return SUBJECT_TASK, str(_get(row, "task_id") or "")


def cell_key(row: Any, configs_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None) -> CellKey:
    """``(subject kind, subject id, config id, prediction field, reference
    field)`` of a row."""
    kind, subject_id = cell_subject(row)
    field_name = _get(row, "field_name")
    config_id = cell_config_id(_get(row, "evaluation_config_id"), field_name)
    config = (configs_by_id or {}).get(config_id) if config_id else None
    pred = cell_pred_field(
        field_name, is_annotation=kind == SUBJECT_ANNOTATION, config=config
    )
    return kind, subject_id, config_id, pred, cell_ref_field(field_name, config)


def row_has_score(metrics: Any) -> bool:
    """Whether a row's metrics carry a score: the batch skip rule's test,
    plus the older Korrektur blob whose number sits under ``score``."""
    if not isinstance(metrics, Mapping):
        return False
    if _row_has_score(dict(metrics)):
        return True
    return any(
        isinstance(value, Mapping) and coerce_metric_value(dict(value)) is not None
        for key, value in metrics.items()
        if key != "error" and not str(key).endswith("_response")
    )


def _rank(row: Any, metrics_attr: str) -> tuple:
    created_at = _get(row, "created_at") or _EPOCH
    if isinstance(created_at, datetime) and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (
        row_has_score(_get(row, metrics_attr)),
        created_at,
        str(_get(row, "id") or _get(row, "task_evaluation_id") or ""),
    )


def pick_current(
    rows: Iterable[Any],
    configs_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
    *,
    metrics_attr: str = "metrics",
) -> Dict[CellKey, Any]:
    """The current row of every cell among ``rows``.

    Ranking per cell: rows with a score first, then the newest
    ``created_at``, then the larger id (so equal timestamps stay
    deterministic).
    """
    best: Dict[CellKey, Tuple[tuple, Any]] = {}
    for row in rows:
        key = cell_key(row, configs_by_id)
        rank = _rank(row, metrics_attr)
        held = best.get(key)
        if held is None or rank > held[0]:
            best[key] = (rank, row)
    return {key: row for key, (_rank_value, row) in best.items()}


def row_id(row: Any) -> Optional[str]:
    value = _get(row, "id")
    if value is None:
        value = _get(row, "task_evaluation_id")
    return str(value) if value is not None else None


def current_row_ids(
    rows: Iterable[Any],
    configs_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
    *,
    metrics_attr: str = "metrics",
) -> set:
    """Ids of the current rows among ``rows`` (see :func:`pick_current`)."""
    return {
        row_id(row)
        for row in pick_current(rows, configs_by_id, metrics_attr=metrics_attr).values()
    }


def configs_by_id(evaluation_config: Any) -> Dict[str, Dict[str, Any]]:
    """``{config id: config}`` of a project's stored ``evaluation_config``."""
    if not isinstance(evaluation_config, Mapping):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for config in evaluation_config.get("evaluation_configs") or []:
        if isinstance(config, Mapping) and config.get("id"):
            out[str(config["id"])] = dict(config)
    return out


def extract_grade_points(metrics: Any) -> Optional[float]:
    """The grade points a row's metrics carry, if any.

    Judges store them as a ``<metric>_grade_points`` key beside the score or
    under ``<metric>.details.grade_points``.
    """
    if not isinstance(metrics, Mapping):
        return None
    for key, value in metrics.items():
        if isinstance(key, str) and key.endswith("_grade_points"):
            points = coerce_metric_value(value)
            if points is not None:
                return points
    for value in metrics.values():
        if isinstance(value, Mapping):
            details = value.get("details")
            if isinstance(details, Mapping):
                points = details.get("grade_points")
                if isinstance(points, (int, float)) and not isinstance(points, bool):
                    return float(points)
    return None


# --------------------------------------------------------------------------- #
# SQL twins: rank rows by the same cell key inside a query.
# --------------------------------------------------------------------------- #
# The jsonpath of the batch skip set (evaluation_planning._SCORED_METRICS_SQL):
# a non-error metric that is a number or a {"value": <number>} dict.
_SCORED_JSONPATH = (
    '$.keyvalue() ? (@.key != "error" && '
    '(@.value.type() == "number" || @.value.value.type() == "number"))'
)


def sql_cell_config(config_col, field_col):
    """SQL twin of :func:`cell_config_id`."""
    from sqlalchemy import case, func, literal

    return func.coalesce(
        config_col,
        case(
            (field_col.like("%|%|%"), func.split_part(field_col, "|", 1)),
            else_=literal(""),
        ),
    )


def sql_cell_pred(field_col):
    """SQL twin of :func:`cell_pred_field` for generation rows (whose label
    always names what they graded): the prediction part without its role
    prefix. The bulk selectors keep their name, as in Python."""
    from sqlalchemy import case, func

    pred = case(
        (field_col.like("%|%|%"), func.split_part(field_col, "|", 2)),
        else_=field_col,
    )
    return func.regexp_replace(pred, "^(human|model):", "")


def sql_cell_ref(config_col, field_col, configs_by_id: Mapping[str, Mapping[str, Any]]):
    """SQL twin of :func:`cell_ref_field`; ``configs_by_id`` are the
    project's configs (:func:`configs_by_id`)."""
    from sqlalchemy import and_, case, func, literal, not_

    composite = field_col.like("%|%|%")
    config = sql_cell_config(config_col, field_col)
    whens = []
    for config_id, config_value in (configs_by_id or {}).items():
        bare_ref = _bare_row_ref(config_value)
        if bare_ref == "":
            whens.append((config == config_id, literal("")))
        else:
            whens.append((and_(config == config_id, not_(composite)), literal(bare_ref)))
    whens.append((composite, func.split_part(field_col, "|", 3)))
    return case(*whens, else_=literal(""))


def sql_has_score(metrics_col):
    """Whether a row's (lite) metrics carry a score, in SQL."""
    from sqlalchemy import func, literal_column

    return func.jsonb_path_exists(
        metrics_col,
        literal_column(f"'{_SCORED_JSONPATH}'::jsonpath"),
        literal_column("'{}'::jsonb"),
        True,
    )


def sql_current_rank_order(metrics_col, created_col, id_col) -> List[Any]:
    """``ORDER BY`` of a ``row_number()`` window whose first row per cell is
    the current one (see :func:`pick_current`)."""
    return [sql_has_score(metrics_col).desc(), created_col.desc(), id_col.desc()]


def sql_cell_partition(
    subject_col, config_col, field_col, configs_by_id: Mapping[str, Mapping[str, Any]]
) -> Sequence[Any]:
    """``PARTITION BY`` of that window for one subject column, given the
    project's configs (:func:`configs_by_id`)."""
    return [
        subject_col,
        sql_cell_config(config_col, field_col),
        sql_cell_pred(field_col),
        sql_cell_ref(config_col, field_col, configs_by_id),
    ]
