"""Irreversible purge of a soft-deleted project, in short batches.

Shared by the worker task ``tasks.purge_project`` (the only caller in
production) and the API tests, which drive it on the test DB. Queueing a
purge (:func:`enqueue_purge_job_async` / :func:`enqueue_purge_job_sync`) lives
here too, so the API's purge and discard routes and the worker's stale-draft
sweep share one implementation.

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
    AnalysisRun,
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
        "analysis_runs": 0,
        "analysis_frames_of_other_projects": 0,
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
    # Analysis runs cascade with the project (their estimates with them), but
    # their frame snapshots live in object storage: collect the keys first and
    # delete the objects once the rows are gone.
    frame_keys = [
        key
        for (key,) in db.execute(
            select(AnalysisRun.frame_object_key).where(
                AnalysisRun.project_id == project_id,
                AnalysisRun.frame_object_key.isnot(None),
            )
        ).all()
    ]
    # A cross-project run of another project read this project's answers
    # or one of its lookup tables into its frame: the frame goes, the run
    # and its aggregate estimates stay readable to the readers of its own
    # project (a purged input project no longer counts for reads) and say
    # why the frame is gone.
    readers = db.execute(
        select(AnalysisRun).where(
            AnalysisRun.project_id != project_id,
            AnalysisRun.frame_object_key.isnot(None),
            AnalysisRun.reads_project(project_id),
        )
    ).scalars().all()
    for run in readers:
        frame_keys.append(run.frame_object_key)
        run.frame_object_key = None
        run.warnings = list(run.warnings or []) + [
            f"frame deleted: input project {project_id} was purged"
        ]
    counts["analysis_frames_of_other_projects"] = len(readers)
    counts["analysis_runs"] = db.execute(
        delete(AnalysisRun).where(AnalysisRun.project_id == project_id)
    ).rowcount
    db.execute(delete(ProjectOrganization).where(ProjectOrganization.project_id == project_id))
    counts["projects"] = db.execute(delete(Project).where(Project.id == project_id)).rowcount
    db.commit()
    delete_analysis_frames(frame_keys)
    return counts


def delete_analysis_frames(keys) -> int:
    """Delete stored analysis frame snapshots, best effort: a storage error
    is logged and leaves the object behind (the rows are already gone).
    Returns how many were deleted."""
    if not keys:
        return 0
    try:
        from storage.object_storage import object_storage
    except Exception:  # pragma: no cover - storage misconfigured in this process
        logger.exception("purge: storage unavailable, %d analysis frame(s) left behind", len(keys))
        return 0
    deleted = 0
    for key in keys:
        try:
            if object_storage.delete_file(key):
                deleted += 1
            else:
                logger.warning("purge: analysis frame %s could not be deleted", key)
        except Exception:
            logger.exception("purge: analysis frame %s could not be deleted", key)
    return deleted


# --- Queueing a purge (API routes and the stale-draft sweep) ----------------
#
# One implementation with an async (API) and a sync (worker) twin. The caller
# passes ``send(job_id)``, which publishes ``tasks.purge_project`` for the job
# and returns the Celery result (its ``id`` is stored on the job): the API
# sends through ``celery_client.send_task_safe``, the worker through its own
# app.

#: Error of a job the queue did not accept (the job is marked failed).
PURGE_QUEUE_UNAVAILABLE = "Purge queue unavailable, please retry"
#: Error of a running job that made no progress for PURGE_JOB_STALE_AFTER.
SUPERSEDED = "Superseded: the job made no progress for 30 minutes"


class PurgeQueueUnavailable(Exception):
    """The purge message could not be published; the job is marked failed."""


def _build_supersede_stale(job_id: str):
    return (
        update(ProjectPurgeJob)
        .where(ProjectPurgeJob.id == job_id, stale_running_job())
        .values(status=JobStatus.FAILED.value, error_message=SUPERSEDED)
        .execution_options(synchronize_session=False)
    )


def _build_select_active_jobs(project_id: str):
    return (
        select(ProjectPurgeJob)
        .where(
            ProjectPurgeJob.project_id == project_id,
            ProjectPurgeJob.status.in_(ACTIVE_STATUSES),
        )
        .order_by(ProjectPurgeJob.created_at.desc())
    )


def _new_purge_job(project, requested_by: Optional[str]) -> ProjectPurgeJob:
    import uuid

    return ProjectPurgeJob(
        id=str(uuid.uuid4()),
        project_id=project.id,
        project_title=project.title,
        requested_by=str(requested_by) if requested_by else None,
        status=JobStatus.PENDING.value,
        progress=0,
    )


async def supersede_if_stale_async(db, job: ProjectPurgeJob) -> bool:
    """Mark ``job`` failed if it is a running job without progress for
    ``PURGE_JOB_STALE_AFTER``, judged in the database so a worker that just
    reclaimed it keeps it; reloads ``job`` either way. Commits."""
    if job.status != JobStatus.RUNNING.value:
        return False
    superseded = (await db.execute(_build_supersede_stale(job.id))).rowcount == 1
    await db.commit()
    await db.refresh(job)
    return superseded


def supersede_if_stale_sync(db: Session, job: ProjectPurgeJob) -> bool:
    """Sync twin of :func:`supersede_if_stale_async`."""
    if job.status != JobStatus.RUNNING.value:
        return False
    superseded = db.execute(_build_supersede_stale(job.id)).rowcount == 1
    db.commit()
    db.refresh(job)
    return superseded


async def active_purge_job_async(db, project_id: str) -> Optional[ProjectPurgeJob]:
    """The live purge job of the project, or None. A running job that has not
    moved for ``PURGE_JOB_STALE_AFTER`` is dead and is marked failed here (its
    worker would skip it, should its message still arrive); a pending job is
    only waiting in the queue and stays live."""
    jobs = (await db.execute(_build_select_active_jobs(project_id))).scalars().all()
    live = None
    for job in jobs:
        if await supersede_if_stale_async(db, job):
            continue
        if live is None and job.status in ACTIVE_STATUSES:
            live = job
    return live


def active_purge_job_sync(db: Session, project_id: str) -> Optional[ProjectPurgeJob]:
    """Sync twin of :func:`active_purge_job_async`."""
    jobs = db.execute(_build_select_active_jobs(project_id)).scalars().all()
    live = None
    for job in jobs:
        if supersede_if_stale_sync(db, job):
            continue
        if live is None and job.status in ACTIVE_STATUSES:
            live = job
    return live


async def enqueue_purge_job_async(
    db, project, requested_by: Optional[str], send: Callable[[str], object]
) -> ProjectPurgeJob:
    """Queue the purge of the soft-deleted ``project``, or return the purge
    already live for it; a pending one has its message sent again, in case it
    was lost (the worker runs a job once, whatever the number of messages).
    ``requested_by`` may be None (the stale-draft sweep). Commits. Raises
    :class:`PurgeQueueUnavailable` when ``send`` fails."""
    existing = await active_purge_job_async(db, project.id)
    if existing is not None:
        if existing.status == JobStatus.RUNNING.value:
            return existing
        try:
            result = send(existing.id)
        except Exception as exc:
            logger.error("Failed to re-enqueue purge job %s: %s", existing.id, exc)
            raise PurgeQueueUnavailable(PURGE_QUEUE_UNAVAILABLE) from exc
        existing.celery_task_id = getattr(result, "id", None)
        await db.commit()
        await db.refresh(existing)
        return existing
    job = _new_purge_job(project, requested_by)
    db.add(job)
    await db.commit()
    try:
        result = send(job.id)
        job.celery_task_id = getattr(result, "id", None)
        await db.commit()
    except Exception as exc:
        logger.error("Failed to enqueue purge job %s: %s", job.id, exc)
        job.status = JobStatus.FAILED.value
        job.error_message = PURGE_QUEUE_UNAVAILABLE
        await db.commit()
        raise PurgeQueueUnavailable(PURGE_QUEUE_UNAVAILABLE) from exc
    # Loads the server-side timestamps for the response.
    await db.refresh(job)
    return job


def enqueue_purge_job_sync(
    db: Session, project, requested_by: Optional[str], send: Callable[[str], object]
) -> ProjectPurgeJob:
    """Sync twin of :func:`enqueue_purge_job_async`."""
    existing = active_purge_job_sync(db, project.id)
    if existing is not None:
        if existing.status == JobStatus.RUNNING.value:
            return existing
        try:
            result = send(existing.id)
        except Exception as exc:
            logger.error("Failed to re-enqueue purge job %s: %s", existing.id, exc)
            raise PurgeQueueUnavailable(PURGE_QUEUE_UNAVAILABLE) from exc
        existing.celery_task_id = getattr(result, "id", None)
        db.commit()
        db.refresh(existing)
        return existing
    job = _new_purge_job(project, requested_by)
    db.add(job)
    db.commit()
    try:
        result = send(job.id)
        job.celery_task_id = getattr(result, "id", None)
        db.commit()
    except Exception as exc:
        logger.error("Failed to enqueue purge job %s: %s", job.id, exc)
        job.status = JobStatus.FAILED.value
        job.error_message = PURGE_QUEUE_UNAVAILABLE
        db.commit()
        raise PurgeQueueUnavailable(PURGE_QUEUE_UNAVAILABLE) from exc
    db.refresh(job)
    return job


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
