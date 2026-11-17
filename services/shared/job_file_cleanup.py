"""Deletes the object-storage files of expired export and import jobs.

Run daily by the worker beat task ``tasks.cleanup_expired_job_files`` and
driven directly by the API tests on the test DB.

An export job and a finished import job get ``expires_at = now + 7 days``,
but until this sweep nothing removed their files: ``expires_at`` was only
checked on download, so every export and every uploaded import file stayed in
the bucket for good (6.27 GB on ltvm2, and production keeps the upload of
every merge). A failed import got no ``expires_at`` at all; its upload expires
``FAILED_IMPORT_RETENTION`` after the job last changed, the same seven days.

The sweep deletes the file and then clears the job's ``object_key``, so the
job row (history, statistics) stays and a swept job is never looked at again.
Only our own uploads are deleted: a cloud import's key names a file in a
customer bucket, so jobs with a storage connection, or whose key is not an
import key we minted, are left alone. Several import jobs can share one
upload (a merge preview and the merge itself), so an upload is deleted only
once every job that uses it has expired. A file whose delete fails keeps its
key and is retried by the next run.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from models import ExportJob, ImportJob, JobStatus

logger = logging.getLogger(__name__)

#: How long the upload of a failed import is kept after the job failed, the
#: retention a finished import gets.
FAILED_IMPORT_RETENTION = timedelta(days=7)

#: Jobs per transaction.
CLEANUP_BATCH = 200

#: An import key minted by ``get_upload_url(file_type="imports", ...)``.
_IMPORT_KEY = re.compile(r"imports/\d{4}/\d{2}/[^/]+/[^/]+")


def _import_expiry():
    """When an import job's upload expires (NULL while it can still run)."""
    return func.coalesce(
        ImportJob.expires_at,
        ImportJob.updated_at + FAILED_IMPORT_RETENTION,
    )


def _import_expired(now: datetime):
    return or_(
        and_(
            ImportJob.status == JobStatus.COMPLETED.value,
            ImportJob.expires_at <= now,
        ),
        and_(
            ImportJob.status == JobStatus.FAILED.value,
            _import_expiry() <= now,
        ),
    )


def _sweep_exports(db: Session, storage, now: datetime) -> Dict[str, int]:
    deleted = failed = 0
    jobs = (
        db.query(ExportJob)
        .filter(ExportJob.object_key.isnot(None), ExportJob.expires_at <= now)
        .order_by(ExportJob.expires_at, ExportJob.id)
        .all()
    )
    for index, job in enumerate(jobs, 1):
        if storage.delete_file(job.object_key):
            job.object_key = None
            deleted += 1
        else:
            failed += 1
        if index % CLEANUP_BATCH == 0:
            db.commit()
    db.commit()
    return {"deleted": deleted, "failed": failed}


def _sweep_imports(db: Session, storage, now: datetime) -> Dict[str, int]:
    deleted = failed = kept = 0
    keys = [
        key
        for (key,) in db.query(ImportJob.object_key)
        .filter(
            ImportJob.object_key.isnot(None),
            ImportJob.source_connection_id.is_(None),
            _import_expired(now),
        )
        .distinct()
        .order_by(ImportJob.object_key)
        .all()
    ]
    for index, key in enumerate(keys, 1):
        jobs = db.query(ImportJob).filter(ImportJob.object_key == key).all()
        ours = _IMPORT_KEY.fullmatch(key) is not None and all(
            job.source_connection_id is None for job in jobs
        )
        if not ours:
            kept += 1
        elif any(not _is_expired(job, now) for job in jobs):
            # Another job still needs the upload; it goes with the last one.
            kept += 1
        elif storage.delete_file(key):
            for job in jobs:
                if job.expires_at is None:
                    job.expires_at = job.updated_at + FAILED_IMPORT_RETENTION
                job.object_key = None
            deleted += 1
        else:
            failed += 1
        if index % CLEANUP_BATCH == 0:
            db.commit()
    db.commit()
    return {"deleted": deleted, "failed": failed, "kept": kept}


def _is_expired(job: ImportJob, now: datetime) -> bool:
    if job.status == JobStatus.COMPLETED.value:
        return job.expires_at is not None and job.expires_at <= now
    if job.status == JobStatus.FAILED.value:
        expiry = job.expires_at or job.updated_at + FAILED_IMPORT_RETENTION
        return expiry <= now
    return False


def cleanup_expired_job_files(
    db: Session, storage, now: Optional[datetime] = None
) -> Dict[str, Dict[str, int]]:
    """Delete the files of every expired export and import job.

    ``storage`` is the object storage service (``delete_file(key) -> bool``).
    Returns per kind the number of files deleted, of deletes that failed (to
    be retried) and, for imports, of expired uploads kept because another job
    still uses them or they are not ours.
    """
    now = now or datetime.now(timezone.utc)
    try:
        result = {
            "exports": _sweep_exports(db, storage, now),
            "imports": _sweep_imports(db, storage, now),
        }
    except Exception:
        db.rollback()
        raise
    logger.info("cleanup_expired_job_files: %s", result)
    return result
