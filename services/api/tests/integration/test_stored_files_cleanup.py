"""Deleting rows that point at object storage deletes the stored objects too.

Handed-in solutions, transcribed pages, parked uploads and the source files
of staff bulk uploads live in object storage under prefixes that never
expire. Their rows cascade away with a task, a project or an account, and
the objects used to stay behind for good. These tests store real objects
(``STORAGE_TYPE=local`` in the test runner) and check they are gone after
each delete path, and that the objects of rows that stay are kept.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from project_models import (
    PendingSubmissionUpload,
    SubmissionFile,
    SubmissionOcrJob,
    Task,
    UploadBatch,
)
from project_purge import purge_project_data
from stored_files import delete_stored_files, task_file_keys
from tests.integration.test_participant_tier import _as_user, _project, _user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _store(name="abgabe.pdf", file_type="submissions") -> str:
    from storage.object_storage import object_storage

    return object_storage.upload_file(b"%PDF-1.4 x", filename=name, file_type=file_type)["file_key"]


def _exists(key: str) -> bool:
    from storage.object_storage import object_storage

    return object_storage.get_file_info(key) is not None


async def _task_ids(db, project):
    return (
        await db.execute(select(Task.id).where(Task.project_id == project.id).order_by(Task.inner_id))
    ).scalars().all()


async def _files_for(db, project, task_id, person, *, uploader=None):
    """One of each stored-file row for ``person`` on ``task_id``; returns their keys."""
    keys = {
        "file": _store(),
        "page": _store("seite.jpg"),
        "parked": _store(),
    }
    job = SubmissionOcrJob(
        id=str(uuid.uuid4()), project_id=project.id, task_id=task_id, user_id=person.id,
        mode="on_behalf", page_keys=[{"storage_key": keys["page"], "original_filename": "seite.jpg"}],
    )
    db.add(job)
    await db.flush()
    db.add(SubmissionFile(
        id=str(uuid.uuid4()), project_id=project.id, task_id=task_id, user_id=person.id,
        uploaded_by=(uploader or person).id, storage_key=keys["file"], original_filename="abgabe.pdf",
        size_bytes=10, sha256="0" * 64, source_format="pdf",
    ))
    # The submission file of the transcribed page shares the page's key.
    db.add(SubmissionFile(
        id=str(uuid.uuid4()), project_id=project.id, task_id=task_id, user_id=person.id,
        storage_key=keys["page"], original_filename="seite.jpg", size_bytes=10, sha256="1" * 64,
        source_format="image", ocr_job_id=job.id, page_index=0,
    ))
    db.add(PendingSubmissionUpload(
        id=str(uuid.uuid4()), project_id=project.id, task_id=task_id,
        email=f"{uuid.uuid4().hex[:8]}@example.com", storage_key=keys["parked"],
        original_filename="abgabe.pdf", source_format="pdf", extracted_text="Antwort",
    ))
    await db.commit()
    return keys


async def test_purge_deletes_the_stored_files_of_every_row_it_removes(async_test_db):
    db = async_test_db
    owner = await _user(db)
    person = await _user(db)
    p = await _project(db, owner, tasks=2)
    other = await _project(db, owner, tasks=1)
    first, second = await _task_ids(db, p)
    per_task = [
        set((await _files_for(db, p, first, person)).values()),
        set((await _files_for(db, p, second, person)).values()),
    ]
    keys = sorted(per_task[0] | per_task[1])
    source = _store("punkte.xlsx", file_type="uploads")
    db.add(UploadBatch(
        id=str(uuid.uuid4()), project_id=p.id, task_id=first, kind="example", created_by=owner.id,
        source_filename="punkte.xlsx", source_storage_key=source, rows_total=2, rows_written=2,
    ))
    kept = await _files_for(db, other, (await _task_ids(db, other))[0], person)
    p.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    left_after_first_batch = []

    def _purge(s):
        def on_batch(done, _total):
            if done == 2:
                left_after_first_batch.extend(k for k in keys if _exists(k))

        return purge_project_data(s, p.id, task_batch=1, on_batch=on_batch)

    counts = await db.run_sync(_purge)

    # The first batch committed and deleted the objects of its task before
    # the second batch started; the second task's objects were still there.
    assert set(left_after_first_batch) in per_task
    assert counts["stored_files"] == 7
    assert not any(_exists(k) for k in keys + [source])
    assert all(_exists(k) for k in kept.values())
    assert (await db.execute(select(func.count()).select_from(UploadBatch).where(
        UploadBatch.project_id == p.id
    ))).scalar_one() == 0


async def test_task_bulk_delete_deletes_only_the_files_of_its_tasks(async_test_client, async_test_db):
    db = async_test_db
    admin = await _user(db, superadmin=True)
    person = await _user(db)
    p = await _project(db, admin, tasks=2)
    other = await _project(db, admin, tasks=1)
    gone_task, kept_task = await _task_ids(db, p)
    foreign_task = (await _task_ids(db, other))[0]
    gone = await _files_for(db, p, gone_task, person)
    kept = await _files_for(db, p, kept_task, person)
    foreign = await _files_for(db, other, foreign_task, person)

    with _as_user(admin):
        # A task id of another project in the list deletes nothing there.
        r = await async_test_client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": [gone_task, foreign_task]},
        )
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 1}
    assert not any(_exists(k) for k in gone.values())
    assert all(_exists(k) for k in kept.values())
    assert all(_exists(k) for k in foreign.values())


async def test_account_delete_deletes_the_persons_files_not_the_ones_they_uploaded(async_test_db):
    from auth_module.user_service import delete_user

    db = async_test_db
    # Deleting an account reassigns what it authored to a superadmin.
    await _user(db, superadmin=True)
    owner = await _user(db)
    person = await _user(db)
    classmate = await _user(db)
    p = await _project(db, owner, tasks=1)
    task_id = (await _task_ids(db, p))[0]
    own = await _files_for(db, p, task_id, person)
    # A file the person uploaded for a classmate is the classmate's.
    for_classmate = await _files_for(db, p, task_id, classmate, uploader=person)
    # A parked upload attached to the person shares the key of the
    # submission file it became; the parked row outlives the account.
    attached = _store()
    db.add(SubmissionFile(
        id=str(uuid.uuid4()), project_id=p.id, task_id=task_id, user_id=person.id,
        storage_key=attached, original_filename="abgabe.pdf", size_bytes=10, sha256="2" * 64,
        source_format="pdf",
    ))
    db.add(PendingSubmissionUpload(
        id=str(uuid.uuid4()), project_id=p.id, task_id=task_id,
        email=f"{uuid.uuid4().hex[:8]}@example.com", storage_key=attached,
        original_filename="abgabe.pdf", source_format="pdf", extracted_text="Antwort",
        status="attached", attached_user_id=person.id,
    ))
    await db.commit()
    person_id = person.id

    assert await db.run_sync(lambda s: delete_user(s, person_id)) is True

    assert not _exists(own["file"]) and not _exists(own["page"])
    assert _exists(for_classmate["file"]) and _exists(for_classmate["page"])
    # A parked upload belongs to the task, not to an account.
    assert _exists(own["parked"])
    assert _exists(attached)
    remaining = await db.execute(
        select(PendingSubmissionUpload.attached_user_id).where(PendingSubmissionUpload.storage_key == attached)
    )
    assert remaining.scalars().all() == [None]


async def test_task_file_keys_reads_every_table(async_test_db):
    db = async_test_db
    owner = await _user(db)
    person = await _user(db)
    p = await _project(db, owner, tasks=1)
    task_id = (await _task_ids(db, p))[0]
    keys = await _files_for(db, p, task_id, person)
    assert await db.run_sync(lambda s: task_file_keys(s, [task_id])) == set(keys.values())
    assert await db.run_sync(lambda s: task_file_keys(s, [])) == set()


async def test_deleting_stored_files_is_best_effort():
    from unittest.mock import patch

    with patch(
        "storage.object_storage.object_storage.delete_file",
        side_effect=[True, False, RuntimeError("down")],
    ):
        assert delete_stored_files(["a", "b", "c"]) == 1
    assert delete_stored_files([]) == 0
