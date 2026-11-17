"""Irreversible purge of a soft-deleted project, in short batches.

Shared by the worker task ``tasks.purge_project`` (the only caller in
production) and the API tests, which drive it on the test DB.

Why batches on a worker: one ``DELETE FROM tasks WHERE project_id = ...`` of a
ZJS-sized project (581 tasks, 160k task_evaluations holding about 3.4 GB of
TOASTed metrics) ran for close to three minutes on ltvm2, almost all of it
removing the task_evaluations TOAST, so the API's 15 s statement timeout
cancelled it and the purge could never finish. Here every batch of ``PURGE_TASK_BATCH`` tasks is
its own transaction of a few seconds and records the job's progress, so a run
that dies half way leaves a smaller, still soft-deleted project that the next
purge continues.

Each batch deletes the big children explicitly before the tasks: task
evaluations first, so deleting the generations afterwards has no
``generation_id`` to set NULL, then the generations and generation jobs, whose
task and project keys also cascade since migration 140.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable, Dict, Optional

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    EvaluationRunMetric,
    Generation,
    JobStatus,
    ProjectPurgeJob,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import Project, ProjectOrganization, Task

logger = logging.getLogger(__name__)

#: Tasks per transaction. Ten ZJS tasks (about 2,800 task_evaluations of
#: about 20 KB each) took 5-14 s on ltvm2; the whole ZJS-sized project took
#: 5-7 minutes in 59 batches.
PURGE_TASK_BATCH = 10

#: A running job bumps its row every batch, so one whose row has not changed
#: for this long is dead (its worker was killed): a new purge request replaces
#: it, a status poll reports it failed, and a redelivered message may claim it
#: again. A pending job is only waiting in the queue and is never stale.
PURGE_JOB_STALE_AFTER = timedelta(minutes=30)

ACTIVE_STATUSES = (JobStatus.PENDING.value, JobStatus.RUNNING.value)

#: Error code of a job whose project was restored (or never soft-deleted).
NOT_DELETED = "Project is not soft-deleted; restore cancelled the purge"


class PurgeAborted(Exception):
    """The project stopped being purgeable while the purge ran."""


def stale_running_job():
    """SQL condition of a running job without progress for
    ``PURGE_JOB_STALE_AFTER``, on the database clock."""
    return and_(
        ProjectPurgeJob.status == JobStatus.RUNNING.value,
        ProjectPurgeJob.updated_at < func.clock_timestamp() - PURGE_JOB_STALE_AFTER,
    )


def _locked_deleted_at(db: Session, project_id: str):
    """``(exists, deleted_at)`` of the project, holding a row lock until the
    batch commits so a concurrent restore waits for it and the next batch
    sees the restore."""
    row = db.execute(
        select(Project.deleted_at).where(Project.id == project_id).with_for_update(read=True)
    ).first()
    return (row is not None, row[0] if row is not None else None)


def purge_project_data(
    db: Session,
    project_id: str,
    *,
    task_batch: int = PURGE_TASK_BATCH,
    on_batch: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, int]:
    """Delete the soft-deleted project ``project_id`` and all its rows.

    Commits after every batch. ``on_batch(tasks_done, tasks_total)`` runs
    inside each batch's transaction, before its commit. Returns the deleted
    row counts. Raises :class:`PurgeAborted` when the project is not
    soft-deleted (any more); a project that no longer exists returns zeros.
    """
    counts = {
        "tasks": 0,
        "task_evaluations": 0,
        "generations": 0,
        "generation_jobs": 0,
        "projects": 0,
    }
    exists, deleted_at = _locked_deleted_at(db, project_id)
    if not exists:
        db.commit()
        return counts
    if deleted_at is None:
        db.rollback()
        raise PurgeAborted(NOT_DELETED)
    total = db.execute(
        select(func.count()).select_from(Task).where(Task.project_id == project_id)
    ).scalar_one()
    db.commit()

    while True:
        exists, deleted_at = _locked_deleted_at(db, project_id)
        if not exists:
            db.commit()
            return counts
        if deleted_at is None:
            db.rollback()
            raise PurgeAborted(NOT_DELETED)
        ids = (
            db.execute(
                select(Task.id)
                .where(Task.project_id == project_id)
                .order_by(Task.id)
                .limit(task_batch)
            )
            .scalars()
            .all()
        )
        if not ids:
            break
        counts["task_evaluations"] += db.execute(
            delete(TaskEvaluation).where(TaskEvaluation.task_id.in_(ids))
        ).rowcount
        counts["generations"] += db.execute(
            delete(Generation).where(Generation.task_id.in_(ids))
        ).rowcount
        counts["generation_jobs"] += db.execute(
            delete(ResponseGeneration).where(ResponseGeneration.task_id.in_(ids))
        ).rowcount
        counts["tasks"] += db.execute(delete(Task).where(Task.id.in_(ids))).rowcount
        if on_batch is not None:
            on_batch(counts["tasks"], max(total, counts["tasks"]))
        db.commit()

    # What is left hangs off the project row itself: project-level generation
    # jobs (no task) with their generations, evaluation runs (their task
    # evaluations went with the tasks) and the small per-project tables that
    # cascade from ``projects``.
    exists, deleted_at = _locked_deleted_at(db, project_id)
    if not exists:
        db.commit()
        return counts
    if deleted_at is None:
        db.rollback()
        raise PurgeAborted(NOT_DELETED)
    project_jobs = select(ResponseGeneration.id).where(
        ResponseGeneration.project_id == project_id
    )
    counts["generations"] += db.execute(
        delete(Generation).where(Generation.generation_id.in_(project_jobs))
    ).rowcount
    counts["generation_jobs"] += db.execute(
        delete(ResponseGeneration).where(ResponseGeneration.project_id == project_id)
    ).rowcount
    # evaluation_run_metrics references evaluation_runs without ON DELETE, so
    # a leftover row would block the project delete.
    db.execute(
        delete(EvaluationRunMetric).where(
            EvaluationRunMetric.evaluation_id.in_(
                select(EvaluationRun.id).where(EvaluationRun.project_id == project_id)
            )
        )
    )
    db.execute(delete(ProjectOrganization).where(ProjectOrganization.project_id == project_id))
    counts["projects"] = db.execute(delete(Project).where(Project.id == project_id)).rowcount
    db.commit()
    return counts


def _public_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}" if not isinstance(exc, PurgeAborted) else str(exc)
    return text[:1000]


def run_project_purge_job(
    db: Session, job_id: str, *, task_batch: int = PURGE_TASK_BATCH
) -> Dict[str, object]:
    """Run the purge job ``job_id`` to its end and record the outcome on it.

    The job is claimed with one conditional update (pending, or running but
    stale), so only one message runs it; any other message for the job (a
    re-enqueued duplicate, a redelivery while the first copy still runs, a
    finished job) is skipped.
    """
    claimed = db.execute(
        update(ProjectPurgeJob)
        .where(
            ProjectPurgeJob.id == job_id,
            or_(ProjectPurgeJob.status == JobStatus.PENDING.value, stale_running_job()),
        )
        .values(status=JobStatus.RUNNING.value, updated_at=func.clock_timestamp())
        .returning(ProjectPurgeJob.project_id)
    ).first()
    db.commit()
    if claimed is None:
        job = db.get(ProjectPurgeJob, job_id)
        if job is None:
            logger.warning("purge job %s not found", job_id)
            return {"status": "missing", "job_id": job_id}
        return {"status": "skipped", "job_id": job_id, "job_status": job.status}
    project_id = claimed[0]

    def _progress(done: int, total: int) -> None:
        db.execute(
            ProjectPurgeJob.__table__.update()
            .where(ProjectPurgeJob.id == job_id)
            .values(progress=min(99, int(done * 100 / total)) if total else 99,
                    updated_at=func.clock_timestamp())
        )

    try:
        counts = purge_project_data(db, project_id, task_batch=task_batch, on_batch=_progress)
    except Exception as exc:
        db.rollback()
        message = _public_error(exc)
        logger.error("purge job %s of project %s failed: %s", job_id, project_id, message)
        job = db.get(ProjectPurgeJob, job_id)
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.error_message = message
            db.commit()
        return {"status": "failed", "job_id": job_id, "error": message}

    job = db.get(ProjectPurgeJob, job_id)
    job.status = JobStatus.COMPLETED.value
    job.progress = 100
    job.result = counts
    db.commit()
    logger.info("purge job %s removed project %s: %s", job_id, project_id, counts)
    return {"status": "completed", "job_id": job_id, "result": counts}
