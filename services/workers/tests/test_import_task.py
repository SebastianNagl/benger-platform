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


def _committed(before_commit, result):
    """What a real driver does on success: hand the result to the caller's
    hook, then commit (the fake session's commit is a no-op)."""
    assert before_commit is not None, "the worker must pass a before_commit hook"
    before_commit(result)
    return result


def _make_job(
    project_id="proj-1",
    status="pending",
    object_key="imports/proj-1/file.json",
    source_connection_id=None,
    organization_id=None,
):
    return types.SimpleNamespace(
        id="ijob-1",
        project_id=project_id,
        requested_by="user-1",
        object_key=object_key,
        source_connection_id=source_connection_id,
        organization_id=organization_id,
        format=None,
        status=status,
        byte_size=None,
        progress=0,
        result=None,
        error_message=None,
        expires_at=None,
        source_manifest=None,
        payload_sha256=None,
        idempotency_key=None,
        duplicate_of_job_id=None,
    )


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._result

    def one(self):
        assert self._result is not None
        return self._result


class _FakeSession:
    def __init__(self, by_model):
        self._by_model = by_model
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, model):
        return _FakeQuery(self._by_model.get(model))

    def flush(self):
        pass

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

    # The fake session has no import history: no earlier import matches, and
    # the advisory lock and the task links are the database's (covered end
    # to end in tests/integration/test_import_provenance_e2e.py).
    import import_provenance

    with patch.object(workers_tasks, "_publish_progress"), patch.object(
        import_provenance, "find_completed_import", return_value=None
    ), patch.object(import_provenance, "lock_import_key"), patch.object(
        import_provenance, "track_written_tasks", return_value=set()
    ), patch.object(import_provenance, "record_written_tasks"):
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

    def _fake_nested(db, project_id, fileobj, user_id, before_commit=None):
        captured["project_id"] = project_id
        captured["user_id"] = user_id
        captured["bytes"] = fileobj.read()
        return _committed(before_commit, {"created_tasks": 1})

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
    import hashlib

    assert job.payload_sha256 == hashlib.sha256(content).hexdigest()
    assert job.source_manifest["payload"] == {
        "sha256": job.payload_sha256,
        "byte_size": len(content),
    }
    assert job.idempotency_key is not None
    assert job.error_message is None
    assert job.expires_at is not None and job.expires_at > datetime.now(timezone.utc)


def test_import_comprehensive_creates_project_and_captures_id(_patched):
    workers_tasks, storage, ImportJob = _patched
    content = b'{"format_version": "1.0", "project": {"title": "X"}}'
    job = _make_job(project_id=None, object_key="imports/u1/file.json")
    _stage_object(storage, job.object_key, content)

    captured = {}

    def _fake_full(db, fileobj, user_id, organization_id=None, before_commit=None):
        captured["organization_id"] = organization_id
        return _committed(
            before_commit,
            {"project_id": "new-proj-9", "message": "ok", "statistics": {}},
        )

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
    # No org context on the job -> the importer's fallback applies.
    assert captured["organization_id"] is None


def test_import_comprehensive_passes_model_id_map_to_importer(_patched):
    """The model_id_map sent with the task reaches the create-new importer."""
    workers_tasks, storage, ImportJob = _patched
    content = b'{"format_version": "1.0", "project": {"title": "X"}}'
    job = _make_job(project_id=None, object_key="imports/u1/file.json")
    _stage_object(storage, job.object_key, content)

    captured = {}

    def _fake_full(
        db, fileobj, user_id, organization_id=None, model_id_map=None, before_commit=None
    ):
        captured["model_id_map"] = model_id_map
        return _committed(
            before_commit,
            {"project_id": "new-proj-8", "message": "ok", "statistics": {}},
        )

    session = _FakeSession({ImportJob: job})
    with patch("import_stream.run_full_project_import", _fake_full), patch.object(
        workers_tasks, "SessionLocal", return_value=session
    ):
        result = workers_tasks.import_project(
            "ijob-1", model_id_map={"custom-dev": "custom-prod"}
        )

    assert result["status"] == "completed"
    assert captured["model_id_map"] == {"custom-dev": "custom-prod"}


def test_merge_mode_runs_the_merge_driver(_patched):
    """mode="merge" on a project-scoped job merges instead of importing new
    tasks, and hands over the model_id_map."""
    workers_tasks, storage, ImportJob = _patched
    content = b'{"format_version": "1.0", "project": {"title": "X"}}'
    job = _make_job(project_id="proj-1", object_key="imports/proj-1/file.json")
    _stage_object(storage, job.object_key, content)

    captured = {}

    def _fake_merge(db, project_id, fileobj, user_id, model_id_map=None, before_commit=None):
        captured.update(project_id=project_id, model_id_map=model_id_map)
        return _committed(before_commit, {"project_id": project_id, "statistics": {"merged": True}})

    session = _FakeSession({ImportJob: job})
    with patch("import_stream.run_merge_import", _fake_merge), patch(
        "import_stream.run_nested_import"
    ) as mock_nested, patch.object(workers_tasks, "SessionLocal", return_value=session):
        result = workers_tasks.import_project(
            "ijob-1", model_id_map={"a": "b"}, mode="merge"
        )

    assert result["status"] == "completed"
    mock_nested.assert_not_called()
    assert captured == {"project_id": "proj-1", "model_id_map": {"a": "b"}}
    assert job.format == "merge"
    assert job.project_id == "proj-1"


def test_merge_dry_run_completes_the_job_with_the_preview_and_writes_nothing(_patched):
    """dry_run=True is the merge preview: the driver runs as a dry run (it
    rolls the merge back itself and never calls before_commit), and only the
    job row is completed, as a merge_preview carrying the preview."""
    workers_tasks, storage, ImportJob = _patched
    content = b'{"format_version": "1.0", "project": {"title": "X"}}'
    job = _make_job(project_id="proj-1", object_key="imports/proj-1/file.json")
    _stage_object(storage, job.object_key, content)

    captured = {}
    preview = {
        "project_id": "proj-1",
        "statistics": {"dry_run": True, "matched_tasks": 2, "unknown_models": ["custom-x"]},
    }

    def _fake_merge(
        db, project_id, fileobj, user_id, model_id_map=None, before_commit=None, dry_run=False
    ):
        captured.update(dry_run=dry_run, before_commit=before_commit, model_id_map=model_id_map)
        return preview

    session = _FakeSession({ImportJob: job})
    with patch("import_stream.run_merge_import", _fake_merge), patch.object(
        workers_tasks, "SessionLocal", return_value=session
    ):
        result = workers_tasks.import_project(
            "ijob-1", model_id_map={"a": "b"}, mode="merge", dry_run=True
        )

    assert result["status"] == "completed"
    assert captured == {"dry_run": True, "before_commit": None, "model_id_map": {"a": "b"}}
    assert job.status == "completed"
    assert job.format == "merge_preview"
    assert job.result == preview


def test_import_comprehensive_passes_job_organization_to_importer(_patched):
    """The org context stored on the job reaches the create-new importer."""
    workers_tasks, storage, ImportJob = _patched
    content = b'{"format_version": "1.0", "project": {"title": "X"}}'
    job = _make_job(
        project_id=None, object_key="imports/u1/file.json", organization_id="org-lmu"
    )
    _stage_object(storage, job.object_key, content)

    captured = {}

    def _fake_full(db, fileobj, user_id, organization_id=None, before_commit=None):
        captured["organization_id"] = organization_id
        return _committed(
            before_commit,
            {"project_id": "new-proj-7", "message": "ok", "statistics": {}},
        )

    with patch("import_stream.run_full_project_import", _fake_full):
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "completed"
    assert captured["organization_id"] == "org-lmu"


def test_import_validation_error_marks_failed(_patched):
    workers_tasks, storage, ImportJob = _patched
    from import_stream import ImportValidationError

    job = _make_job(project_id="proj-1")
    _stage_object(storage, job.object_key, b'{"data": "not a list"}')

    def _bad(db, project_id, fileobj, user_id, **_):
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

    def _boom(db, project_id, fileobj, user_id, **_):
        raise RuntimeError("driver exploded")

    with patch("import_stream.run_nested_import", _boom):
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "error"
    assert "driver exploded" in result["error"]
    assert job.status == "failed"
    # The exception text stays in the log; the job gets a generic reason.
    assert "driver exploded" not in job.error_message
    assert job.error_message.startswith("The import failed because of an internal error.")


class _PgError(Exception):
    """Stands in for a psycopg2 error: SQLAlchemy keeps it as ``exc.orig``."""

    def __init__(self, message, pgcode):
        super().__init__(message)
        self.pgcode = pgcode


def _db_error(pgcode):
    from sqlalchemy.exc import OperationalError

    statement = (
        "INSERT INTO users (id, username, email, email_verified, "
        "encrypted_openai_api_key) VALUES (%(id)s, %(username)s, %(email)s, "
        "%(email_verified)s, %(encrypted_openai_api_key)s)"
    )
    return OperationalError(
        statement,
        {"id": "u-1", "encrypted_openai_api_key": "gAAAA-secret"},
        _PgError('canceling statement due to lock timeout in "ix_users_email"', pgcode),
    )


def test_import_database_error_never_reaches_the_job(_patched):
    """Kolibri-1 K5: a database error's text carries the whole SQL statement
    with its column list and parameters. The job only says what happened."""
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1")
    _stage_object(storage, job.object_key, b'{"data": []}')

    def _boom(db, project_id, fileobj, user_id, **_):
        raise _db_error("XX000")

    with patch("import_stream.run_nested_import", _boom):
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "error"
    assert job.status == "failed"
    for leaked in ("INSERT", "encrypted_openai_api_key", "users", "gAAAA"):
        assert leaked not in job.error_message
    assert job.error_message == (
        "The import failed because of an internal error. The server log has "
        "the details under job ijob-1."
    )


@pytest.mark.parametrize("pgcode", ["55P03", "40P01", "40001"])
def test_import_concurrent_write_conflict_says_to_retry(_patched, pgcode):
    """A lock timeout, deadlock or serialization failure is a collision with a
    concurrent job: reported as 409 import_conflict so a client can retry."""
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1")
    _stage_object(storage, job.object_key, b'{"data": []}')

    def _boom(db, project_id, fileobj, user_id, **_):
        raise _db_error(pgcode)

    with patch("import_stream.run_nested_import", _boom):
        _run_with_job(workers_tasks, ImportJob, job)

    assert job.status == "failed"
    assert job.error_message == (
        "409: import_conflict: Another job was writing the same data at the "
        "same time. Start the import again."
    )
    assert "ix_users_email" not in job.error_message


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


# ---- Cloud-source jobs (org storage connections) ---------------------------
#
# A job with `source_connection_id` set downloads from the customer bucket via
# the shared org_storage_connection_service (mocked here) instead of our own
# object storage, and tabular keys dispatch to run_tabular_import.


def _make_conn():
    return types.SimpleNamespace(
        id="conn-1",
        organization_id="org-1",
        name="Customer bucket",
        endpoint_url=None,
        bucket="customer-bucket",
        prefix="in/",
        region=None,
        use_ssl=True,
        encrypted_access_key="enc-ak",
        encrypted_secret_key="enc-sk",
    )


def _run_cloud_job(workers_tasks, ImportJob, job, conn):
    from models import OrgStorageConnection

    session = _FakeSession({ImportJob: job, OrgStorageConnection: conn})
    with patch.object(workers_tasks, "SessionLocal", return_value=session):
        result = workers_tasks.import_project("ijob-1")
    return result, session


def test_cloud_import_tabular_key_runs_tabular_driver(_patched):
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(object_key="in/data.csv", source_connection_id="conn-1")
    conn = _make_conn()
    content = b"a,b\n1,2\n"

    def _fake_download(c, key, fileobj):
        assert c is conn
        assert key == "in/data.csv"
        fileobj.write(content)

    captured = {}

    def _fake_tabular(db, project_id, fileobj, user_id, fmt, before_commit=None):
        captured["project_id"] = project_id
        captured["user_id"] = user_id
        captured["fmt"] = fmt
        captured["bytes"] = fileobj.read()
        return _committed(before_commit, {"created_tasks": 1, "format": fmt})

    with patch(
        "org_storage_connection_service.head_object_size", return_value=len(content)
    ), patch(
        "org_storage_connection_service.download_to_fileobj", _fake_download
    ), patch(
        "import_stream.run_tabular_import", _fake_tabular
    ), patch(
        "import_stream.run_nested_import"
    ) as mock_nested:
        result, _ = _run_cloud_job(workers_tasks, ImportJob, job, conn)

    assert result["status"] == "completed"
    mock_nested.assert_not_called()
    assert captured["project_id"] == "proj-1"
    assert captured["user_id"] == "user-1"
    assert captured["fmt"] == "csv"
    assert captured["bytes"] == content
    assert job.status == "completed"
    assert job.byte_size == len(content)


def test_cloud_import_json_key_runs_nested_driver(_patched):
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(object_key="in/tasks.json", source_connection_id="conn-1")
    conn = _make_conn()
    content = b'{"data": [{"id": 1}]}'

    def _fake_download(c, key, fileobj):
        fileobj.write(content)

    captured = {}

    def _fake_nested(db, project_id, fileobj, user_id, before_commit=None):
        captured["bytes"] = fileobj.read()
        return _committed(before_commit, {"created_tasks": 1})

    with patch(
        "org_storage_connection_service.head_object_size", return_value=len(content)
    ), patch(
        "org_storage_connection_service.download_to_fileobj", _fake_download
    ), patch(
        "import_stream.run_nested_import", _fake_nested
    ), patch(
        "import_stream.run_tabular_import"
    ) as mock_tabular:
        result, _ = _run_cloud_job(workers_tasks, ImportJob, job, conn)

    assert result["status"] == "completed"
    mock_tabular.assert_not_called()
    assert captured["bytes"] == content
    assert job.format == "nested"


def test_cloud_import_deleted_connection_fails_job(_patched):
    # SET NULL raced / row deleted between enqueue and run: fail cleanly, never
    # fall back to our own object storage.
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(object_key="in/data.csv", source_connection_id="conn-1")

    with patch("import_stream.run_tabular_import") as mock_tabular, patch(
        "import_stream.run_nested_import"
    ) as mock_nested:
        result, _ = _run_cloud_job(workers_tasks, ImportJob, job, conn=None)

    assert result["status"] == "error"
    assert result["error"] == "storage connection removed"
    mock_tabular.assert_not_called()
    mock_nested.assert_not_called()
    assert job.status == "failed"
    assert "storage connection removed" in (job.error_message or "")


def test_cloud_import_oversize_object_fails_before_download(_patched):
    workers_tasks, storage, ImportJob = _patched
    from project.export_import_service import _CLOUD_IMPORT_MAX_BYTES

    job = _make_job(object_key="in/huge.csv", source_connection_id="conn-1")
    conn = _make_conn()

    with patch(
        "org_storage_connection_service.head_object_size",
        return_value=_CLOUD_IMPORT_MAX_BYTES + 1,
    ), patch(
        "org_storage_connection_service.download_to_fileobj"
    ) as mock_download, patch(
        "import_stream.run_tabular_import"
    ) as mock_tabular:
        result, _ = _run_cloud_job(workers_tasks, ImportJob, job, conn)

    assert result["status"] == "error"
    mock_download.assert_not_called()
    mock_tabular.assert_not_called()
    assert job.status == "failed"
    assert "413" in (job.error_message or "")


def test_driver_returning_without_the_hook_fails_the_job(_patched):
    """A driver that returns without calling before_commit has committed
    without the job's completed state; the worker must not report success."""
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1")
    _stage_object(storage, job.object_key, b'{"data": []}')

    def _no_hook(db, project_id, fileobj, user_id, before_commit=None):
        return {"created_tasks": 0}

    with patch("import_stream.run_nested_import", _no_hook):
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "error"
    assert job.status == "failed"
    assert job.error_message.startswith("The import failed because of an internal error.")


def test_error_after_the_commit_leaves_the_job_completed(_patched):
    """Once the hook's state has committed, a later error (here: the
    completion progress event) neither relabels the job nor the result."""
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1")
    _stage_object(storage, job.object_key, b'{"data": []}')

    def _nested(db, project_id, fileobj, user_id, before_commit=None):
        return _committed(before_commit, {"created_tasks": 0})

    def _publish(channel, payload):
        if payload.get("status") == "completed":
            raise RuntimeError("redis gone")

    with patch("import_stream.run_nested_import", _nested), patch.object(
        workers_tasks, "_publish_progress", side_effect=_publish
    ):
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "completed"
    assert result["project_id"] == "proj-1"
    assert job.status == "completed"
    assert job.error_message is None


# ---------------------------------------------------------------------------
# A failure before the task body's own try (rubric e2e D01): a worker running
# code older than the shared models raised ImportError on the lazy
# ``from import_stream import ...`` and left the job pending for good, so the
# project wizard polled it forever.
# ---------------------------------------------------------------------------


def _stale_module(name):
    """A module of that name missing every attribute, so ``from name import x``
    raises ImportError like a worker whose shared models predate the code."""
    import sys

    return patch.dict(sys.modules, {name: types.ModuleType(name)})


def test_import_failing_before_its_handler_marks_the_job_failed(_patched):
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1")
    published = []

    with _stale_module("import_stream"), patch.object(
        workers_tasks, "_publish_progress",
        side_effect=lambda channel, payload: published.append((channel, payload)),
    ):
        result, session = _run_with_job(workers_tasks, ImportJob, job)

    assert result["status"] == "error"
    assert "cannot import name" in result["error"]
    assert job.status == "failed"
    assert job.error_message.startswith("The import failed because of an internal error.")
    assert "import_stream" not in job.error_message
    assert session.commits >= 1
    assert published[-1] == (
        "import:progress:proj-1",
        {"job_id": "ijob-1", "status": "failed", "progress": 0},
    )


def test_escaped_failure_never_relabels_a_finished_job(_patched):
    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1", status="completed")

    from project.export_import_service import _fail_escaped_job_impl

    session = _FakeSession({ImportJob: job})
    with patch.object(workers_tasks, "SessionLocal", return_value=session):
        result = _fail_escaped_job_impl("import", "ijob-1", RuntimeError("late"))

    assert result["status"] == "error"
    assert job.status == "completed"
    assert session.commits == 0


def test_export_failing_before_its_handler_marks_the_job_failed(_patched):
    workers_tasks, storage, _ = _patched
    from models import ExportJob

    job = types.SimpleNamespace(
        id="ejob-1", project_id="proj-1", status="pending", progress=0,
        error_message=None,
    )
    session = _FakeSession({ExportJob: job})
    with _stale_module("export_stream"), patch.object(
        workers_tasks, "SessionLocal", return_value=session
    ):
        result = workers_tasks.export_project("ejob-1")

    assert result["status"] == "error"
    assert job.status == "failed"
    assert job.error_message.startswith("The export failed because of an internal error.")


def test_repeat_of_a_completed_import_is_a_no_op_without_the_driver(_patched):
    """An earlier completed import with the same key: the job completes as
    a no-op pointing at it, and no driver runs."""
    import import_provenance

    workers_tasks, storage, ImportJob = _patched
    content = b'{"data": [{"data": {"text": "a"}}]}'
    job = _make_job(project_id="proj-1", object_key="imports/proj-1/file.json")
    _stage_object(storage, job.object_key, content)
    prior = types.SimpleNamespace(
        id="ijob-0",
        project_id="proj-1",
        format="nested",
        updated_at=datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc),
        result={"created_tasks": 1},
    )

    with patch.object(
        import_provenance, "find_completed_import", return_value=prior
    ) as mock_find, patch.object(
        import_provenance, "lock_import_key"
    ) as mock_lock, patch("import_stream.run_nested_import") as mock_nested:
        result, _ = _run_with_job(workers_tasks, ImportJob, job)

    mock_nested.assert_not_called()
    mock_lock.assert_called_once()
    assert mock_lock.call_args.args[1] == job.idempotency_key
    assert mock_find.call_args.args[1:3] == (job.idempotency_key, "ijob-1")
    assert result == {
        "status": "completed",
        "job_id": "ijob-1",
        "project_id": "proj-1",
        "byte_size": len(content),
        "no_op": True,
        "duplicate_of_job_id": "ijob-0",
    }
    assert job.status == "completed"
    assert job.duplicate_of_job_id == "ijob-0"
    assert job.format == "nested"
    assert job.result["no_op"] is True
    assert job.result["duplicate_of"]["job_id"] == "ijob-0"


def test_reimport_skips_the_lookup_but_takes_the_lock(_patched):
    import import_provenance

    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1", object_key="imports/proj-1/file.json")
    _stage_object(storage, job.object_key, b'{"data": []}')
    session = _FakeSession({ImportJob: job})

    def _fake_nested(db, project_id, fileobj, user_id, before_commit=None):
        return _committed(before_commit, {"created_tasks": 0})

    with patch.object(import_provenance, "find_completed_import") as mock_find, patch.object(
        import_provenance, "lock_import_key"
    ) as mock_lock, patch("import_stream.run_nested_import", _fake_nested), patch.object(
        workers_tasks, "SessionLocal", return_value=session
    ):
        result = workers_tasks.import_project("ijob-1", reimport=True)

    assert result["status"] == "completed"
    mock_find.assert_not_called()
    mock_lock.assert_called_once()
    assert job.source_manifest["import"]["reimport"] is True
    assert job.duplicate_of_job_id is None


def test_merge_preview_records_provenance_without_a_key(_patched):
    import import_provenance

    workers_tasks, storage, ImportJob = _patched
    job = _make_job(project_id="proj-1", object_key="imports/proj-1/export.json")
    _stage_object(storage, job.object_key, b"{}")
    session = _FakeSession({ImportJob: job})

    with patch.object(import_provenance, "lock_import_key") as mock_lock, patch(
        "import_stream.run_merge_import", return_value={"statistics": {}}
    ), patch.object(workers_tasks, "SessionLocal", return_value=session):
        result = workers_tasks.import_project("ijob-1", mode="merge", dry_run=True)

    assert result["status"] == "completed"
    mock_lock.assert_not_called()
    assert job.format == "merge_preview"
    assert job.idempotency_key is None
    assert job.payload_sha256 is not None
    assert job.source_manifest["import"]["mode"] == "merge_preview"
