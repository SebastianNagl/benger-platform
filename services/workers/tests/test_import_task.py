"""Tests for the async project-import worker task (issue #158).

`tasks.import_project` downloads an uploaded import artifact from object storage
into a seekable spool, then runs the same shared streaming driver the synchronous
endpoints use — ``run_nested_import`` when the job names an existing project,
``run_full_project_import`` (which creates a project) when it doesn't. These tests
drive the real task body against a REAL local-backend ``ObjectStorageService``
(reading a pre-staged tmp file) with a fake DB session and stubbed import drivers,
so they exercise the actual download / dispatch / status-update orchestration
without needing Postgres, S3, or Redis. The driver internals are covered by the
API-side import tests; here the drivers are stubbed.
"""
from __future__ import annotations

import os
import types
from datetime import datetime, timezone
from unittest.mock import patch

import pytest


def _make_local_storage(tmp_path):
    from storage.object_storage import ObjectStorageService

    env = {
        "STORAGE_TYPE": "local",
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_PATH": str(tmp_path),
    }
    with patch.dict(os.environ, env, clear=False):
        return ObjectStorageService()


def _stage_object(storage, object_key, content: bytes):
    """Write an object into the local backend so download_to_fileobj can read it."""
    path = os.path.join(storage.local_storage_path, object_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def _make_job(project_id="proj-1", status="pending", object_key="imports/proj-1/file.json"):
    return types.SimpleNamespace(
        id="ijob-1",
        project_id=project_id,
        requested_by="user-1",
        object_key=object_key,
        format=None,
        status=status,
        byte_size=None,
        progress=0,
        result=None,
        error_message=None,
        expires_at=None,
    )


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, by_model):
        self._by_model = by_model
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, model):
        return _FakeQuery(self._by_model.get(model))

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.fixture
def _patched(tmp_path):
    """Wire the real task to a local storage backend + fake DB + no-op WS."""
    import tasks as workers_tasks
    from models import ImportJob

    storage = _make_local_storage(tmp_path)

    with patch.object(workers_tasks, "_publish_progress"):
        with patch("storage.object_storage.object_storage", storage):
            yield workers_tasks, storage, ImportJob


def _run_with_job(workers_tasks, ImportJob, job):
    session = _FakeSession({ImportJob: job})
    with patch.object(workers_tasks, "SessionLocal", return_value=session):
        result = workers_tasks.import_project("ijob-1")
    return result, session


def test_import_nested_runs_nested_driver(_patched):
    workers_tasks, storage, ImportJob = _patched
    content = b'{"data": [{"id": 1}], "meta": {}}'
    job = _make_job(project_id="proj-1", object_key="imports/proj-1/file.json")
    _stage_object(storage, job.object_key, content)

    captured = {}

    def _fake_nested(db, project_id, fileobj, user_id):
        captured["project_id"] = project_id
        captured["user_id"] = user_id
        captured["bytes"] = fileobj.read()
        return {"created_tasks": 1}

    with patch("import_stream.run_nested_import", _fake_nested), patch(
        "import_stream.run_full_project_import"
    ) as mock_full:
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "completed"
    mock_full.assert_not_called()
    assert captured["project_id"] == "proj-1"
    assert captured["user_id"] == "user-1"
    # The driver received the exact downloaded body, seeked to 0.
    assert captured["bytes"] == content
    assert job.status == "completed"
    assert job.format == "nested"
    assert job.byte_size == len(content)
    assert job.result == {"created_tasks": 1}
    assert job.progress == 100
    assert job.error_message is None
    assert job.expires_at is not None and job.expires_at > datetime.now(timezone.utc)


def test_import_comprehensive_creates_project_and_captures_id(_patched):
    workers_tasks, storage, ImportJob = _patched
    content = b'{"format_version": "1.0", "project": {"title": "X"}}'
    job = _make_job(project_id=None, object_key="imports/u1/file.json")
    _stage_object(storage, job.object_key, content)

    def _fake_full(db, fileobj, user_id):
        return {"project_id": "new-proj-9", "message": "ok", "statistics": {}}

    with patch("import_stream.run_full_project_import", _fake_full), patch(
        "import_stream.run_nested_import"
    ) as mock_nested:
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "completed"
    mock_nested.assert_not_called()
    assert job.format == "comprehensive"
    # The newly-created project id is back-filled onto the job.
    assert job.project_id == "new-proj-9"
    assert result["project_id"] == "new-proj-9"


def test_import_validation_error_marks_failed(_patched):
    workers_tasks, storage, ImportJob = _patched
    from import_stream import ImportValidationError

    job = _make_job(project_id="proj-1")
    _stage_object(storage, job.object_key, b'{"data": "not a list"}')

    def _bad(db, project_id, fileobj, user_id):
        raise ImportValidationError(422, "data must be an array")

    with patch("import_stream.run_nested_import", _bad):
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "error"
    assert job.status == "failed"
    assert "data must be an array" in (job.error_message or "")
    assert "422" in (job.error_message or "")


def test_import_generic_error_marks_failed(_patched):
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1")
    _stage_object(storage, job.object_key, b'{"data": []}')

    def _boom(db, project_id, fileobj, user_id):
        raise RuntimeError("driver exploded")

    with patch("import_stream.run_nested_import", _boom):
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "error"
    assert "driver exploded" in result["error"]
    assert job.status == "failed"
    assert "driver exploded" in (job.error_message or "")


def test_import_missing_object_marks_failed(_patched):
    # The job row exists but the artifact was never uploaded → download raises
    # FileNotFoundError, which must surface as a failed job, not a crash.
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1", object_key="imports/proj-1/missing.json")

    with patch("import_stream.run_nested_import") as mock_nested:
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "error"
    mock_nested.assert_not_called()
    assert job.status == "failed"


def test_import_idempotent_skip_when_already_completed(_patched):
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1", status="completed")

    with patch("import_stream.run_nested_import") as mock_nested, patch(
        "import_stream.run_full_project_import"
    ) as mock_full:
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "skipped"
    mock_nested.assert_not_called()
    mock_full.assert_not_called()


def test_import_missing_job_returns_error(_patched):
    workers_tasks, storage, ImportJob = _patched
    empty = _FakeSession({ImportJob: None})
    with patch.object(workers_tasks, "SessionLocal", return_value=empty):
        result = workers_tasks.import_project("missing")
    assert result["status"] == "error"
    assert result["error"] == "job_not_found"
