"""Object storage files of the rows a delete removes, and removing them.

Several tables point at files in object storage under durable prefixes
(``submissions/``, ``uploads/``) that never expire on their own:

- ``submission_files.storage_key``: handed-in solutions and files returned
  with a grading;
- ``submission_ocr_jobs.page_keys[].storage_key``: the uploaded pages of a
  handwriting transcription;
- ``pending_submission_uploads.storage_key``: a solution parked until its
  person joins;
- ``upload_batches.source_storage_key``: the file of a staff bulk upload.

The first three cascade with their task (the first two also with the
person they are for), the last with its project. The database cascade
removes the rows but cannot remove the objects, so the code that deletes
tasks, purges a project or deletes an account collects the keys first with
:func:`task_file_keys`, :func:`project_file_keys` or :func:`user_file_keys`
and removes the objects with :func:`delete_stored_files` once the delete has
committed. Every key is
unique to its upload (``object_storage`` adds a random part), so a key of a
removed row is not shared with a row that stays; a parked upload and the
submission it became share a key, which the set of keys removes once.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Sequence, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from project_models import PendingSubmissionUpload, SubmissionFile, SubmissionOcrJob, UploadBatch

logger = logging.getLogger(__name__)


def _task_statements(task_ids: Sequence[str]):
    ids = list(task_ids)
    return (
        select(SubmissionFile.storage_key).where(SubmissionFile.task_id.in_(ids)),
        select(PendingSubmissionUpload.storage_key).where(
            PendingSubmissionUpload.task_id.in_(ids),
            PendingSubmissionUpload.storage_key.isnot(None),
        ),
        select(SubmissionOcrJob.page_keys).where(SubmissionOcrJob.task_id.in_(ids)),
    )


def _project_statement(project_id: str):
    return select(UploadBatch.source_storage_key).where(
        UploadBatch.project_id == project_id, UploadBatch.source_storage_key.isnot(None)
    )


def _keys(values: Iterable) -> Set[str]:
    """Storage keys from column values: a key, or an OCR job's page list."""
    keys: Set[str] = set()
    for value in values:
        if isinstance(value, str):
            keys.add(value)
        elif isinstance(value, list):
            for page in value:
                key = page.get("storage_key") if isinstance(page, dict) else None
                if isinstance(key, str) and key:
                    keys.add(key)
    keys.discard("")
    return keys


def task_file_keys(db: Session, task_ids: Sequence[str]) -> Set[str]:
    """Keys of the stored files that go with the tasks ``task_ids``."""
    if not task_ids:
        return set()
    return _keys(
        value for stmt in _task_statements(task_ids) for value in db.execute(stmt).scalars()
    )


async def task_file_keys_async(db: AsyncSession, task_ids: Sequence[str]) -> Set[str]:
    """Async twin of :func:`task_file_keys`."""
    if not task_ids:
        return set()
    values: List = []
    for stmt in _task_statements(task_ids):
        values.extend((await db.execute(stmt)).scalars().all())
    return _keys(values)


def project_file_keys(db: Session, project_id: str) -> Set[str]:
    """Keys of the stored files that hang off the project row itself (not a
    task): the source files of its upload batches."""
    return _keys(db.execute(_project_statement(project_id)).scalars())


def user_file_keys(db: Session, user_id: str) -> Set[str]:
    """Keys of the stored files that cascade away with the account
    ``user_id``: the files and transcribed pages for that person (files they
    uploaded for someone else stay with that person)."""
    values: List = list(
        db.execute(select(SubmissionFile.storage_key).where(SubmissionFile.user_id == user_id)).scalars()
    )
    values.extend(
        db.execute(select(SubmissionOcrJob.page_keys).where(SubmissionOcrJob.user_id == user_id)).scalars()
    )
    return _keys(values)


def delete_stored_files(keys: Iterable[str], *, what: str = "stored file") -> int:
    """Delete objects by key, best effort: a storage error is logged and
    leaves the object behind (the rows are already gone). ``what`` names the
    files in the log. Returns how many were deleted."""
    keys = list(keys)
    if not keys:
        return 0
    try:
        from storage.object_storage import object_storage
    except Exception:  # pragma: no cover - storage misconfigured in this process
        logger.exception("storage unavailable, %d %s(s) left behind", len(keys), what)
        return 0
    deleted = 0
    for key in keys:
        try:
            if object_storage.delete_file(key):
                deleted += 1
            else:
                logger.warning("%s %s could not be deleted", what, key)
        except Exception:
            logger.exception("%s %s could not be deleted", what, key)
    return deleted
