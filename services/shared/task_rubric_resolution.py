"""Which Bewertungsbogen grades a task, and which sheet judges have none (sync).

One lookup for every reader that needs to know whether a task can be graded
with its grading sheet: the judge cells of the bulk run and the immediate
grading in the workers (``evaluation.cell_evaluator`` re-exports
:func:`resolve_grading_rubric` as ``_resolve_task_rubric``), and the shared
immediate dispatch (``immediate_eval_dispatch``), which holds a sheet judge
that would only produce an error row. Generic row lookup only: what a sheet
means, how it is checked and when it becomes active belong to the overlay
that writes ``task_rubrics``.

Selection:

- default: the task's single ``status='active'`` sheet (unique per task,
  ``ux_task_rubrics_one_active``);
- ``metric_parameters.rubric_selector.generator_model_id``: that generator's
  newest non-archived sheet, the lever for crossed rubric-source x judge
  designs. On a project with ``rubric_review_required`` only a sheet a person
  confirmed (``review_state == 'confirmed'``) counts there, so the selector
  never grades with a sheet that bypassed the check. The default path needs
  no such filter: in those projects a sheet becomes active only once
  confirmed (``task_rubric_service.activate_task_rubric``).

A sheet whose ``criteria`` carry no ``max_score`` cannot drive the
multi-dimension grading and counts as missing.

Sheet judges: the Bewertungsbogen judge (``llm_judge_rubric``) always grades
along the task's sheet; a config of a metric an extension registered as able
to read the sheet (``register_sheet_judge_metric``) does when its
``metric_parameters`` say ``use_task_rubric: true`` (an overlay judge that
can grade either along a per-task sheet or along a scheme of its own). No
other config is a sheet judge. Both kinds share every rule here: they are
held while the task has no usable sheet, and the waiting gradings start once
one becomes usable.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Set, Tuple

#: The metric that grades against the task's Bewertungsbogen.
RUBRIC_JUDGE_METRIC = "llm_judge_rubric"

#: ``metric_parameters`` key that makes any other config a sheet judge.
USE_TASK_RUBRIC_PARAM = "use_task_rubric"

#: Machine-readable reason of a grading that has no usable sheet: the code of
#: the worker's error row (``metrics[<metric>].error_code``), the reason of a
#: held immediate grading (``eval_metadata.billing_block.reason``) and of a
#: held config (``eval_metadata.held_configs[].reason``).
RUBRIC_MISSING = "rubric_missing"

#: ``review_state`` of a sheet a person checked and confirmed. Same value as
#: ``task_rubric_service.REVIEW_STATE_CONFIRMED`` (that module is async-only
#: and imports more than the workers need).
REVIEW_STATE_CONFIRMED = "confirmed"

NO_RUBRIC_ERROR = (
    "No usable Bewertungsbogen for task {task_id}: this evaluation grades "
    "against a per-task rubric (status='active' in task_rubrics), and none "
    "was found. Generate and activate one, or set "
    "metric_parameters.rubric_selector."
)


class NoUsableRubricError(RuntimeError):
    """A sheet judge was asked to grade a task without a usable sheet.

    ``code`` is :data:`RUBRIC_MISSING`; the message stays the developer text
    of :data:`NO_RUBRIC_ERROR` (teachers read it in their own run
    diagnostics), while participant-facing readers show a text of their own
    for the code.
    """

    code = RUBRIC_MISSING

    def __init__(self, task_id: Any):
        super().__init__(NO_RUBRIC_ERROR.format(task_id=task_id))
        self.task_id = task_id


def _project_requires_review(db, task) -> bool:
    """``projects.rubric_review_required`` of the task's project."""
    return _project_id_requires_review(db, getattr(task, "project_id", None))


def _project_id_requires_review(db, project_id) -> bool:
    from project_models import Project

    if not project_id:
        return False
    value = db.query(Project.rubric_review_required).filter(Project.id == project_id).scalar()
    return value is True


def _has_scored_step(row) -> bool:
    criteria = getattr(row, "criteria", None)
    if not isinstance(criteria, dict):
        return False
    return any(isinstance(d, dict) and d.get("max_score") is not None for d in criteria.values())


def resolve_grading_rubric(db, task, metric_parameters, *, review_required: Optional[bool] = None):
    """The ``task_rubrics`` row a sheet judge grades ``task`` with, else None.

    ``review_required`` is the project's ``rubric_review_required`` when the
    caller already knows it; otherwise it is read (only on the selector path,
    which is the only one that needs it).
    """
    from project_models import TaskRubric

    selector = (metric_parameters or {}).get("rubric_selector") or {}
    generator = selector.get("generator_model_id") if isinstance(selector, dict) else None

    query = db.query(TaskRubric).filter(TaskRubric.task_id == task.id)
    if generator:
        query = query.filter(
            TaskRubric.generator_model_id == generator,
            TaskRubric.status != "archived",
        )
        if review_required is None:
            review_required = _project_requires_review(db, task)
        if review_required:
            query = query.filter(TaskRubric.review_state == REVIEW_STATE_CONFIRMED)
        row = query.order_by(TaskRubric.created_at.desc()).first()
    else:
        row = query.filter(TaskRubric.status == "active").first()

    if row is None or not _has_scored_step(row):
        return None
    return row


_TASK_ID_CHUNK = 1000


def resolve_grading_rubric_ids(
    db, task_ids: Iterable[str], metric_parameters, *, review_required: Optional[bool] = None
) -> dict:
    """``{task_id: rubric_id}`` of the sheet :func:`resolve_grading_rubric`
    picks for each of ``task_ids`` (tasks of one project), in one query per
    chunk of task ids instead of one per task. Tasks without a usable sheet
    are left out."""
    from project_models import Task, TaskRubric

    wanted = [str(t) for t in task_ids or () if t]
    if not wanted:
        return {}
    selector = (metric_parameters or {}).get("rubric_selector") or {}
    generator = selector.get("generator_model_id") if isinstance(selector, dict) else None

    query = db.query(TaskRubric)
    if generator:
        query = query.filter(
            TaskRubric.generator_model_id == generator,
            TaskRubric.status != "archived",
        )
        if review_required is None:
            project_id = db.query(Task.project_id).filter(Task.id == wanted[0]).scalar()
            review_required = _project_id_requires_review(db, project_id)
        if review_required:
            query = query.filter(TaskRubric.review_state == REVIEW_STATE_CONFIRMED)
        query = query.order_by(TaskRubric.task_id, TaskRubric.created_at.desc())
    else:
        query = query.filter(TaskRubric.status == "active")

    rows = []
    for i in range(0, len(wanted), _TASK_ID_CHUNK):
        rows.extend(query.filter(TaskRubric.task_id.in_(wanted[i : i + _TASK_ID_CHUNK])).all())

    picked: dict = {}
    for row in rows:
        task_id = str(row.task_id)
        if task_id in picked:
            continue  # the selector path keeps the newest row per task
        picked[task_id] = row
    return {task_id: row.id for task_id, row in picked.items() if _has_scored_step(row)}


#: Metrics whose judge reads the task's sheet when a config sets
#: ``use_task_rubric: true``. The package that ships such a judge registers it
#: at import time, in the api and the workers process; the platform names
#: none (``llm_judge_rubric`` is a sheet judge on its own).
_SHEET_JUDGE_METRICS: Set[str] = set()


def register_sheet_judge_metric(metric: str) -> None:
    """Declare that ``metric`` can grade along the task's sheet. Registering
    twice is a no-op (reload-safe in dev)."""
    _SHEET_JUDGE_METRICS.add(metric)


def unregister_sheet_judge_metric(metric: str) -> None:
    _SHEET_JUDGE_METRICS.discard(metric)


def metric_reads_task_sheet(metric: Optional[str]) -> bool:
    """Whether ``metric`` is registered as able to grade along the sheet."""
    return bool(metric) and metric in _SHEET_JUDGE_METRICS


def is_rubric_judge(config) -> bool:
    """Whether ``config`` grades along the task's sheet (a sheet judge, see
    the module doc)."""
    if not isinstance(config, dict):
        return False
    metric = config.get("metric")
    if metric == RUBRIC_JUDGE_METRIC:
        return True
    params = config.get("metric_parameters")
    return (
        isinstance(metric, str)
        and metric_reads_task_sheet(metric)
        and isinstance(params, dict)
        and params.get(USE_TASK_RUBRIC_PARAM) is True
    )


def split_held_rubric_judges(
    db, task, configs: Iterable[dict], *, review_required: Optional[bool] = None
) -> Tuple[List[dict], List[dict]]:
    """``(kept, held)``: the configs that can run on ``task`` now, and the
    sheet judges that have no usable sheet for it.

    Order is preserved in both lists. Configs of any other metric are always
    kept. Each sheet judge costs one lookup (configs differ only in their
    selector), so callers pass the configs of one grading, not of a project.
    """
    kept: List[dict] = []
    held: List[dict] = []
    for config in configs or []:
        if is_rubric_judge(config) and (
            resolve_grading_rubric(
                db,
                task,
                config.get("metric_parameters"),
                review_required=review_required,
            )
            is None
        ):
            held.append(config)
        else:
            kept.append(config)
    return kept, held


__all__ = [
    "NO_RUBRIC_ERROR",
    "NoUsableRubricError",
    "REVIEW_STATE_CONFIRMED",
    "RUBRIC_JUDGE_METRIC",
    "RUBRIC_MISSING",
    "USE_TASK_RUBRIC_PARAM",
    "is_rubric_judge",
    "metric_reads_task_sheet",
    "register_sheet_judge_metric",
    "resolve_grading_rubric",
    "resolve_grading_rubric_ids",
    "split_held_rubric_judges",
    "unregister_sheet_judge_metric",
]
