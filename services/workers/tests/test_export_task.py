"""Tests for the async project-export worker task (issue #158).

`tasks.export_project` streams a project's export generator into object
storage as a multipart upload, so worker peak RAM stays bounded regardless of
project size (the synchronous path OOMKilled the API pod on the Benchathon
export). These tests drive the real task body against a REAL local-backend
``ObjectStorageService`` (writing into a tmp dir) with a fake DB session and a
stubbed export generator, so they exercise the actual buffering / part-flush /
complete / abort / status-update orchestration without needing Postgres, S3,
or Redis.
"""
from __future__ import annotations

import os
import types
from datetime import datetime, timezone
from unittest.mock import patch

import pytest


def _make_local_storage(tmp_path):
    """A real ObjectStorageService bound to the local backend + a tmp dir."""
    from storage.object_storage import ObjectStorageService

    env = {
        "STORAGE_TYPE": "local",
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_PATH": str(tmp_path),
    }
    with patch.dict(os.environ, env, clear=False):
        return ObjectStorageService()


def _make_job(fmt="json", status="pending", task_ids=None):
    return types.SimpleNamespace(
        id="job-1",
        project_id="proj-1",
        requested_by="user-1",
        format=fmt,
        status=status,
        task_ids=task_ids,
        object_key=None,
        byte_size=None,
        progress=0,
        error_message=None,
        expires_at=None,
    )


def _make_project():
    return types.SimpleNamespace(id="proj-1", title="My Project")


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._result

    def update(self, values, synchronize_session=False):
        # Mirror SQLAlchemy's bulk UPDATE against the single fixture row so the
        # worker's separate-session progress UPDATE has somewhere to write.
        if self._result is not None and isinstance(values, dict):
            for key, val in values.items():
                setattr(self._result, key, val)
        return 1


class _FakeSession:
    """Minimal Session stand-in: routes query(model) by class to a fixture."""

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
    """Wire the real task to a local storage backend + fake DB + no-op WS.

    Yields (workers_tasks, storage, job, project, set_generator) where
    set_generator(callable_or_iterable) controls what the export emits.
    """
    import tasks as workers_tasks
    from models import ExportJob
    from project_models import Project

    storage = _make_local_storage(tmp_path)
    job = _make_job()
    project = _make_project()
    session = _FakeSession({ExportJob: job, Project: project})

    gen_holder = {"chunks": [""], "task_ids": "__unset__", "drive_progress": False}

    def _fake_select_generator(db, proj, fmt, task_ids=None, progress_cb=None):
        # Record the subset the worker forwarded so tests can assert that
        # job.task_ids reaches select_export_generator unchanged.
        gen_holder["task_ids"] = task_ids
        chunks = gen_holder["chunks"]
        if callable(chunks):
            return chunks()
        if gen_holder["drive_progress"] and progress_cb is not None:
            # Mimic stream_export_json calling progress_cb once per streamed task
            # batch with (streamed_so_far, total), wrapped like the real generator
            # so a progress hiccup can never sever the export.
            def _driven():
                total = len(chunks)
                for idx, chunk in enumerate(chunks):
                    yield chunk
                    try:
                        progress_cb(idx + 1, total)
                    except Exception:
                        pass

            return _driven()
        return iter(chunks)

    with patch.object(workers_tasks, "SessionLocal", return_value=session), patch.object(
        workers_tasks, "_publish_progress"
    ) as mock_publish, patch("export_stream.select_export_generator", _fake_select_generator):
        # Patch the singleton the task imports lazily.
        with patch("storage.object_storage.object_storage", storage):
            def set_generator(chunks):
                gen_holder["chunks"] = chunks

            # Lets a test read back the task_ids the worker forwarded to
            # select_export_generator (whole-project export forwards None).
            set_generator.forwarded_task_ids = lambda: gen_holder["task_ids"]
            # Opt a test into having the fake generator drive progress_cb.
            set_generator.drive_progress = lambda on=True: gen_holder.__setitem__(
                "drive_progress", on
            )
            # Exposes the published progress events for assertions.
            set_generator.publish_calls = lambda: list(mock_publish.call_args_list)

            yield workers_tasks, storage, job, project, session, set_generator


def _stored_bytes(storage, object_key):
    path = os.path.join(storage.local_storage_path, object_key)
    with open(path, "rb") as f:
        return f.read()


def test_export_round_trips_small_payload(_patched):
    workers_tasks, storage, job, project, session, set_generator = _patched
    chunks = ['{"project": ', '{"id": "proj-1"}, "tasks": []', ', "export_complete": true}']
    set_generator(chunks)

    result = workers_tasks.export_project("job-1")

    assert result["status"] == "completed"
    assert job.status == "completed"
    assert job.object_key is not None
    expected = "".join(chunks).encode("utf-8")
    assert job.byte_size == len(expected)
    assert _stored_bytes(storage, job.object_key) == expected
    assert job.progress == 100
    assert job.error_message is None
    # 7-day expiry set roughly from now.
    assert job.expires_at is not None
    assert job.expires_at > datetime.now(timezone.utc)
    # Whole-project export forwards no subset to the generator.
    assert set_generator.forwarded_task_ids() is None


def test_export_forwards_job_task_ids_subset(_patched):
    """A subset export job carries task_ids; the worker must forward them to
    select_export_generator unchanged so the stream is restricted to the
    selected/filtered tasks (issue #158 follow-up, plan §3)."""
    workers_tasks, storage, job, project, session, set_generator = _patched
    job.task_ids = ["t-1", "t-2", "t-3"]
    set_generator(['{"project": {"id": "proj-1"}, "tasks": []}'])

    result = workers_tasks.export_project("job-1")

    assert result["status"] == "completed"
    assert set_generator.forwarded_task_ids() == ["t-1", "t-2", "t-3"]


def test_export_multipart_concatenates_parts(_patched):
    """A payload larger than the 8MB part size flushes multiple parts; the
    stored object must be the exact concatenation (no part-boundary corruption)."""
    workers_tasks, storage, job, project, session, set_generator = _patched
    # 3 chunks of 5MB each = 15MB -> at least two 8MB parts + a tail.
    block = "A" * (5 * 1024 * 1024)
    chunks = [block, block, block]
    set_generator(chunks)

    result = workers_tasks.export_project("job-1")

    assert result["status"] == "completed"
    expected = "".join(chunks).encode("utf-8")
    assert job.byte_size == len(expected)
    assert _stored_bytes(storage, job.object_key) == expected


def test_export_gzip_format_stores_decompressible_blob(_patched):
    """A ``ndjson_gz`` job must store an opaque gzip member (not plain text) whose
    inflate equals the generator output, with byte_size reflecting the COMPRESSED
    bytes actually written — the worker side of the .gz round-trip."""
    import gzip

    workers_tasks, storage, job, project, session, set_generator = _patched
    job.format = "ndjson_gz"
    chunks = ['{"_type":"meta"}\n', '{"_type":"task"}\n', '{"_type":"end"}\n']
    set_generator(chunks)

    result = workers_tasks.export_project("job-1")

    assert result["status"] == "completed"
    stored = _stored_bytes(storage, job.object_key)
    assert stored[:2] == b"\x1f\x8b"  # gzip magic — stored compressed, not plain
    assert gzip.decompress(stored) == "".join(chunks).encode("utf-8")
    assert job.byte_size == len(stored)


def test_export_gzip_multipart_concatenates_parts(_patched):
    """A gzipped payload whose COMPRESSED output exceeds the part size must span
    multiple upload parts and still inflate to the exact original — the gzip
    member is byte-split across parts, so concatenation must be lossless."""
    import base64
    import gzip
    import os

    workers_tasks, storage, job, project, session, set_generator = _patched
    job.format = "ndjson_gz"
    # High-entropy (base64 of random bytes) so it barely compresses: ~24MB of
    # near-incompressible text -> compressed output > the 8MB part size.
    chunks = [
        base64.b64encode(os.urandom(8 * 1024 * 1024)).decode("ascii")
        for _ in range(2)
    ]
    set_generator(chunks)

    result = workers_tasks.export_project("job-1")

    assert result["status"] == "completed"
    stored = _stored_bytes(storage, job.object_key)
    assert stored[:2] == b"\x1f\x8b"
    # Compressed output genuinely exceeded one 8MB part.
    assert len(stored) > 8 * 1024 * 1024
    assert gzip.decompress(stored) == "".join(chunks).encode("utf-8")


def test_export_failure_aborts_and_marks_failed(_patched):
    workers_tasks, storage, job, project, session, set_generator = _patched

    def _boom():
        yield "partial bytes"
        raise RuntimeError("generator exploded")

    set_generator(_boom)

    result = workers_tasks.export_project("job-1")

    assert result["status"] == "error"
    assert "generator exploded" in result["error"]
    assert job.status == "failed"
    assert job.error_message and "generator exploded" in job.error_message
    # Aborted upload leaves no staging file and no final object.
    leftovers = []
    for root, _dirs, files in os.walk(storage.local_storage_path):
        leftovers.extend(files)
    assert leftovers == []


def test_export_idempotent_skip_when_already_completed(_patched):
    workers_tasks, storage, job, project, session, set_generator = _patched
    job.status = "completed"
    called = {"n": 0}

    def _should_not_run():
        called["n"] += 1
        yield "data"

    set_generator(_should_not_run)

    result = workers_tasks.export_project("job-1")

    assert result["status"] == "skipped"
    assert called["n"] == 0


def test_export_persists_incremental_progress(_patched):
    """The worker threads a progress callback into the json generator that
    persists a real percentage as tasks stream, so the polled status advances
    instead of jumping 0 -> 100 (the download-progress-bar fix). Verified via the
    published ``running`` events carrying a 0 < progress <= 99 percent."""
    workers_tasks, storage, job, project, session, set_generator = _patched
    set_generator([f'{{"t": {i}}}' for i in range(10)])
    set_generator.drive_progress()

    result = workers_tasks.export_project("job-1")

    assert result["status"] == "completed"
    # Completion still pins the final value to 100.
    assert job.progress == 100

    # `_publish_progress(channel, payload)` is called positionally.
    running_pcts = [
        c.args[1]["progress"]
        for c in set_generator.publish_calls()
        if len(c.args) >= 2
        and isinstance(c.args[1], dict)
        and c.args[1].get("status") == "running"
    ]
    assert running_pcts, "no running progress events were published"
    # At least one mid-stream event reported genuine partial progress (not 0),
    # and progress is capped at 99 until completion flips it to 100.
    assert any(0 < p <= 99 for p in running_pcts)
    assert max(running_pcts) <= 99


def test_export_missing_job_returns_error(_patched):
    workers_tasks, storage, job, project, session, set_generator = _patched
    # Point the session at no ExportJob row.
    from models import ExportJob
    from project_models import Project

    empty = _FakeSession({ExportJob: None, Project: project})
    with patch.object(workers_tasks, "SessionLocal", return_value=empty):
        result = workers_tasks.export_project("missing")

    assert result["status"] == "error"
    assert result["error"] == "job_not_found"
