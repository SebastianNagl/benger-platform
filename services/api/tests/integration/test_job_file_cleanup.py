"""F3: the daily sweep deletes the stored files of expired export and import jobs.

Export jobs and finished import jobs expire seven days after they finish, and
a failed import's upload seven days after it failed, but before the sweep only
the download endpoint looked at ``expires_at``, so the files stayed in the
bucket for good. These tests run the worker's sweep on the test DB with a
stand-in for object storage (the external boundary) that holds the files.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from job_file_cleanup import cleanup_expired_job_files
from models import ExportJob, ImportJob, JobStatus, Organization, OrgStorageConnection
from tests.integration.test_participant_tier import _as_user, _project, _user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime.now(timezone.utc)
DAY = timedelta(days=1)


class Bucket:
    """Object storage holding a set of keys; ``broken`` keys fail to delete."""

    def __init__(self, *keys, broken=()):
        self.files = set(keys)
        self.broken = set(broken)

    def delete_file(self, key):
        if key in self.broken:
            return False
        self.files.discard(key)
        return True


def _import_key(owner):
    return f"imports/2026/11/{owner}/{uuid.uuid4().hex[:8]}_data.json"


async def _export(db, project, owner, *, expires_at, status=JobStatus.COMPLETED.value):
    job = ExportJob(
        id=str(uuid.uuid4()), project_id=project.id, requested_by=owner.id,
        format="json", status=status,
        object_key=f"exports/{project.id}/{uuid.uuid4().hex}.json",
        expires_at=expires_at,
    )
    db.add(job)
    await db.flush()
    return job


async def _import(db, owner, *, status, key=None, expires_at=None, updated_at=None,
                  connection_id=None):
    job = ImportJob(
        id=str(uuid.uuid4()), project_id=None, requested_by=owner.id,
        status=status, object_key=key or _import_key(owner),
        expires_at=expires_at, source_connection_id=connection_id,
    )
    if updated_at is not None:
        job.updated_at = updated_at
    db.add(job)
    await db.flush()
    return job


async def _sweep(db, bucket, now=NOW):
    await db.commit()
    result = await db.run_sync(lambda s: cleanup_expired_job_files(s, bucket, now=now))
    db.expire_all()
    return result


async def _key(db, model, job_id):
    return (await db.execute(select(model.object_key).where(model.id == job_id))).scalar_one()


async def test_expired_exports_lose_their_file_and_live_ones_keep_it(async_test_db):
    db = async_test_db
    owner = await _user(db)
    project = await _project(db, owner)
    expired = await _export(db, project, owner, expires_at=NOW - DAY)
    live = await _export(db, project, owner, expires_at=NOW + DAY)
    running = await _export(db, project, owner, expires_at=None, status=JobStatus.RUNNING.value)
    bucket = Bucket(expired.object_key, live.object_key, running.object_key)
    ids = (expired.id, live.id, running.id)
    live_key, running_key = live.object_key, running.object_key

    await _sweep(db, bucket)

    assert bucket.files == {live_key, running_key}
    assert await _key(db, ExportJob, ids[0]) is None
    assert await _key(db, ExportJob, ids[1]) == live_key
    assert await _key(db, ExportJob, ids[2]) == running_key


async def test_a_swept_export_still_answers_expired_on_download(async_test_client, async_test_db):
    """Clearing the key must not turn the 410 'expired' into a 404 'not ready'."""
    db = async_test_db
    owner = await _user(db)
    project = await _project(db, owner)
    job = await _export(db, project, owner, expires_at=NOW - DAY)
    bucket = Bucket(job.object_key)
    project_id, job_id = project.id, job.id

    await _sweep(db, bucket)
    await db.refresh(owner)

    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{project_id}/exports/{job_id}/download")
    assert r.status_code == 410, r.text


async def test_failed_import_uploads_expire_a_week_after_the_failure(async_test_db):
    """A failed import never got an expires_at, so its upload was kept forever."""
    db = async_test_db
    owner = await _user(db)
    old = await _import(db, owner, status=JobStatus.FAILED.value, updated_at=NOW - 8 * DAY)
    recent = await _import(db, owner, status=JobStatus.FAILED.value, updated_at=NOW - 2 * DAY)
    finished = await _import(db, owner, status=JobStatus.COMPLETED.value, expires_at=NOW - DAY)
    pending = await _import(db, owner, status=JobStatus.PENDING.value, updated_at=NOW - 30 * DAY)
    bucket = Bucket(old.object_key, recent.object_key, finished.object_key, pending.object_key)
    old_id, finished_id = old.id, finished.id
    kept = {recent.object_key, pending.object_key}

    await _sweep(db, bucket)

    assert bucket.files == kept
    assert await _key(db, ImportJob, old_id) is None
    assert await _key(db, ImportJob, finished_id) is None
    swept = (await db.execute(select(ImportJob).where(ImportJob.id == old_id))).scalar_one()
    assert abs(swept.expires_at - (NOW - DAY)) < timedelta(minutes=5)


async def test_an_upload_shared_by_two_jobs_goes_with_the_last_one(async_test_db):
    """A merge preview and the merge itself import the same upload."""
    db = async_test_db
    owner = await _user(db)
    key = _import_key(owner)
    preview = await _import(db, owner, status=JobStatus.COMPLETED.value, key=key,
                            expires_at=NOW - DAY)
    merge = await _import(db, owner, status=JobStatus.COMPLETED.value, key=key,
                          expires_at=NOW + 2 * DAY)
    bucket = Bucket(key)
    preview_id, merge_id = preview.id, merge.id

    await _sweep(db, bucket)
    assert bucket.files == {key}
    assert await _key(db, ImportJob, preview_id) == key

    await _sweep(db, bucket, now=NOW + 3 * DAY)
    assert bucket.files == set()
    assert await _key(db, ImportJob, preview_id) is None
    assert await _key(db, ImportJob, merge_id) is None


async def test_cloud_imports_and_foreign_keys_are_never_deleted(async_test_db):
    """A cloud import's key names a file in the customer's bucket, and a key
    we did not mint as an import upload is not ours to delete either."""
    db = async_test_db
    owner = await _user(db)
    org = Organization(
        id=str(uuid.uuid4()), name=f"org-{uuid.uuid4().hex[:6]}", display_name="Org",
        slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True, settings={},
    )
    db.add(org)
    await db.flush()
    connection = OrgStorageConnection(
        id=str(uuid.uuid4()), organization_id=org.id, name="Customer bucket",
        bucket="customer-bucket", prefix="", encrypted_access_key="x",
        encrypted_secret_key="y",
    )
    db.add(connection)
    await db.flush()
    cloud = await _import(db, owner, status=JobStatus.COMPLETED.value, expires_at=NOW - DAY,
                          connection_id=connection.id)
    foreign = await _import(db, owner, status=JobStatus.FAILED.value,
                            key="in/2026/export.json", updated_at=NOW - 30 * DAY)
    keys = {cloud.id: cloud.object_key, foreign.id: foreign.object_key}
    bucket = Bucket(*keys.values())

    await _sweep(db, bucket)

    assert bucket.files == set(keys.values())
    for job_id, key in keys.items():
        assert await _key(db, ImportJob, job_id) == key


async def test_a_failed_delete_keeps_the_key_for_the_next_run(async_test_db):
    db = async_test_db
    owner = await _user(db)
    project = await _project(db, owner)
    job = await _export(db, project, owner, expires_at=NOW - DAY)
    bucket = Bucket(job.object_key, broken={job.object_key})
    job_id, key = job.id, job.object_key

    result = await _sweep(db, bucket)
    assert result["exports"]["failed"] >= 1
    assert await _key(db, ExportJob, job_id) == key

    bucket.broken.clear()
    await _sweep(db, bucket)
    assert bucket.files == set()
    assert await _key(db, ExportJob, job_id) is None
