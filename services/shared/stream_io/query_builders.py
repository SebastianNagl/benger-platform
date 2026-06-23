"""Deduplicated SQL/select construction used across the export stream drivers.

These builders were copy-pasted between ``stream_comprehensive_project_data_json``
and ``stream_export_ndjson`` (the ``task_id`` subquery and the per-task
generation-count GROUP BY). Extracting them keeps the two generators bit-for-bit
identical in the rows they pull. Pure move/extract — same SELECTs, same filters.
"""
from sqlalchemy import func as sa_func
from sqlalchemy import select

from models import EvaluationRun, Generation
from project_models import Task


def build_task_id_subquery(project_id: str):
    """``SELECT tasks.id WHERE tasks.project_id = :project_id`` as a subquery.

    Used inside ``IN()`` filters across the comprehensive / NDJSON exporters so
    child tables are scoped to the project's tasks without materializing the id
    list. Returns a SQLAlchemy ``select`` Core construct (the exact value the
    callers previously built inline).
    """
    return select(Task.id).where(Task.project_id == project_id)


def build_gen_counts(db, task_id_subq) -> dict:
    """Per-task generation counts for ``serialize_task(mode="full",
    total_generations=...)``.

    A single GROUP BY over the generations whose task is in ``task_id_subq``,
    returned as ``{task_id: count}``. Identical to the inline prepass both
    comprehensive exporters ran.
    """
    gen_counts: dict = {}
    for tid, n in (
        db.query(Generation.task_id, sa_func.count(Generation.id))
        .filter(Generation.task_id.in_(task_id_subq))
        .group_by(Generation.task_id)
        .all()
    ):
        gen_counts[tid] = n
    return gen_counts


def build_eval_run_ids(db, project_id: str):
    """Return ``(eval_runs, eval_run_ids)`` for ``project_id``.

    Both comprehensive exporters load every ``EvaluationRun`` of the project and
    derive the id list that scopes ``evaluation_metrics`` / ``evaluation_judge_runs``
    / ``task_evaluations``. Kept as one helper so the load + id-list derivation
    stay in lockstep.
    """
    eval_runs = (
        db.query(EvaluationRun).filter(EvaluationRun.project_id == project_id).all()
    )
    return eval_runs, [er.id for er in eval_runs]
