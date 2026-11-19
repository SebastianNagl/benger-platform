"""Import provenance and idempotent re-import, end to end (migration 147).

These tests drive the real ``tasks.import_project`` body against the real
test Postgres and a local object storage, with synthetic payloads only, and
check the job rows and the imported rows:

- an import records the SHA-256 of the payload and its source manifest;
- importing the same payload into the same target again is a no-op that
  writes nothing and names the earlier job, also under another file name;
- a changed payload is a new import with a different hash;
- ``reimport`` imports the same payload again on purpose;
- a create-new import repeated is a no-op that returns the earlier
  project, until that project is deleted;
- a failed import keeps its provenance and never blocks a later one;
- two identical imports running at once write the payload once.
"""

import hashlib
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import tasks

pytestmark = [pytest.mark.integration, pytest.mark.database]


def _uid():
    return str(uuid.uuid4())


@pytest.fixture()
def storage(tmp_path):
    from storage.object_storage import ObjectStorageService

    env = {
        "STORAGE_TYPE": "local",
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_PATH": str(tmp_path),
    }
    with patch.dict(os.environ, env, clear=False):
        local = ObjectStorageService()
    with patch("storage.object_storage.object_storage", local), patch.object(
        tasks, "_publish_progress"
    ):
        yield local


@pytest.fixture()
def jobs(db_conn, cleanup):
    """Track import jobs and created projects; delete them before the shared
    cleanup runs (the no-op jobs reference the jobs they repeat)."""
    from models import ImportJob
    from project_models import Project

    state = {"user_ids": set(), "titles": set()}

    yield state

    db_conn.rollback()
    if state["titles"]:
        created = [
            p
            for (p,) in db_conn.query(Project.id)
            .filter(Project.title.in_(state["titles"]))
            .all()
        ]
        cleanup.project_ids.extend(p for p in created if p not in cleanup.project_ids)
    if state["user_ids"]:
        users = list(state["user_ids"])
        db_conn.query(ImportJob).filter(ImportJob.requested_by.in_(users)).update(
            {ImportJob.duplicate_of_job_id: None}, synchronize_session=False
        )
        db_conn.query(ImportJob).filter(ImportJob.requested_by.in_(users)).delete(
            synchronize_session=False
        )
    db_conn.commit()


def _stage(storage, body: bytes, name: str) -> str:
    key = f"imports/{_uid()}/{name}"
    path = os.path.join(storage.local_storage_path, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return key


def _new_job(db, jobs, user, object_key, project_id=None, **job_fields):
    from models import ImportJob

    job = ImportJob(
        id=_uid(),
        project_id=project_id,
        requested_by=user.id,
        object_key=object_key,
        status="pending",
        **job_fields,
    )
    db.add(job)
    db.commit()
    jobs["user_ids"].add(user.id)
    return job.id


def _load(db, job_id):
    from models import ImportJob

    db.expire_all()
    return db.query(ImportJob).filter(ImportJob.id == job_id).one()


def _import(db, jobs, user, object_key, project_id=None, reimport=False, **job_fields):
    job_id = _new_job(db, jobs, user, object_key, project_id, **job_fields)
    outcome = tasks.import_project(job_id, reimport=reimport)
    return outcome, _load(db, job_id)


def _nested_body(texts) -> bytes:
    return json.dumps({"data": [{"data": {"text": t}} for t in texts]}).encode("utf-8")


def _task_texts(db, project_id):
    from project_models import Task

    return sorted(
        t.data["text"] for t in db.query(Task).filter(Task.project_id == project_id)
    )


def _assert_imported(outcome, job):
    assert job.error_message is None, job.error_message
    assert job.status == "completed"
    assert job.duplicate_of_job_id is None
    assert outcome["status"] == "completed", outcome
    assert not outcome.get("no_op")


def _assert_no_op(outcome, job, prior):
    assert job.error_message is None, job.error_message
    assert job.status == "completed"
    assert job.progress == 100
    assert job.duplicate_of_job_id == prior.id
    assert job.project_id == prior.project_id
    assert job.payload_sha256 == prior.payload_sha256
    assert job.idempotency_key == prior.idempotency_key
    assert job.format == prior.format
    assert job.result["no_op"] is True
    assert job.result["project_id"] == prior.project_id
    assert job.result["duplicate_of"]["job_id"] == prior.id
    assert job.result["duplicate_of"]["payload_sha256"] == prior.payload_sha256
    assert outcome == {
        "status": "completed",
        "job_id": job.id,
        "project_id": prior.project_id,
        "byte_size": job.byte_size,
        "no_op": True,
        "duplicate_of_job_id": prior.id,
    }


def test_nested_import_records_hash_and_manifest(
    db_conn, make_user, make_project, storage, jobs
):
    user = make_user()
    target = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")
    body = _nested_body(["alpha", "beta"])
    key = _stage(storage, body, "tasks.json")
    declared = {
        "converter": "synthetic@1",
        "files": [{"path": "a.jsonl", "sha256": "0" * 64}],
    }

    outcome, job = _import(
        db_conn,
        jobs,
        user,
        key,
        project_id=target.id,
        source_manifest={"declared": declared},
    )

    _assert_imported(outcome, job)
    assert job.payload_sha256 == hashlib.sha256(body).hexdigest()
    assert job.byte_size == len(body)
    assert len(job.idempotency_key) == 64
    assert job.source_manifest == {
        "version": 1,
        "payload": {"sha256": job.payload_sha256, "byte_size": len(body)},
        "source": {"kind": "upload", "object_key": key, "filename": "tasks.json"},
        "target": {"kind": "project", "project_id": target.id},
        "import": {"mode": "nested", "model_id_map": {}, "reimport": False},
        "declared": declared,
    }


def test_reimport_of_the_same_payload_is_a_no_op(
    db_conn, make_user, make_project, storage, jobs
):
    user = make_user()
    target = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")
    body = _nested_body(["alpha", "beta"])

    first_outcome, first = _import(
        db_conn, jobs, user, _stage(storage, body, "tasks.json"), project_id=target.id
    )
    _assert_imported(first_outcome, first)
    assert _task_texts(db_conn, target.id) == ["alpha", "beta"]

    # The same bytes, uploaded again under another name.
    outcome, repeat = _import(
        db_conn, jobs, user, _stage(storage, body, "copy.json"), project_id=target.id
    )

    _assert_no_op(outcome, repeat, first)
    assert _task_texts(db_conn, target.id) == ["alpha", "beta"]
    assert repeat.source_manifest["source"]["filename"] == "copy.json"

    # A third repeat still points at the import that wrote the rows.
    outcome, third = _import(
        db_conn, jobs, user, _stage(storage, body, "tasks.json"), project_id=target.id
    )
    _assert_no_op(outcome, third, first)
    assert _task_texts(db_conn, target.id) == ["alpha", "beta"]


def test_changed_payload_is_a_new_import_with_another_hash(
    db_conn, make_user, make_project, storage, jobs
):
    user = make_user()
    target = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")

    _o, first = _import(
        db_conn,
        jobs,
        user,
        _stage(storage, _nested_body(["alpha", "beta"]), "tasks.json"),
        project_id=target.id,
    )
    outcome, changed = _import(
        db_conn,
        jobs,
        user,
        _stage(storage, _nested_body(["alpha", "beta", "gamma"]), "tasks.json"),
        project_id=target.id,
    )

    _assert_imported(outcome, changed)
    assert changed.payload_sha256 != first.payload_sha256
    assert changed.idempotency_key != first.idempotency_key
    assert changed.result["created_tasks"] == 3
    assert _task_texts(db_conn, target.id) == [
        "alpha",
        "alpha",
        "beta",
        "beta",
        "gamma",
    ]


def test_same_payload_into_another_project_is_imported(
    db_conn, make_user, make_project, storage, jobs
):
    user = make_user()
    one = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")
    two = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")
    body = _nested_body(["alpha"])

    _o, first = _import(
        db_conn, jobs, user, _stage(storage, body, "t.json"), project_id=one.id
    )
    outcome, other = _import(
        db_conn, jobs, user, _stage(storage, body, "t.json"), project_id=two.id
    )

    _assert_imported(outcome, other)
    assert other.payload_sha256 == first.payload_sha256
    assert other.idempotency_key != first.idempotency_key
    assert _task_texts(db_conn, two.id) == ["alpha"]


def test_reimport_flag_imports_the_same_payload_again(
    db_conn, make_user, make_project, storage, jobs
):
    user = make_user()
    target = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")
    body = _nested_body(["alpha"])

    _o, first = _import(
        db_conn, jobs, user, _stage(storage, body, "t.json"), project_id=target.id
    )
    outcome, again = _import(
        db_conn,
        jobs,
        user,
        _stage(storage, body, "t.json"),
        project_id=target.id,
        reimport=True,
    )

    _assert_imported(outcome, again)
    assert again.idempotency_key == first.idempotency_key
    assert again.source_manifest["import"]["reimport"] is True
    assert _task_texts(db_conn, target.id) == ["alpha", "alpha"]

    # A plain repeat afterwards is a no-op of the latest import.
    outcome, repeat = _import(
        db_conn, jobs, user, _stage(storage, body, "t.json"), project_id=target.id
    )
    _assert_no_op(outcome, repeat, again)
    assert _task_texts(db_conn, target.id) == ["alpha", "alpha"]


def _comprehensive_body(title: str) -> bytes:
    """A minimal synthetic full-project export (the create-new format)."""
    return json.dumps(
        {
            "format_version": "1.0",
            "project": {
                "id": _uid(),
                "title": title,
                "label_config": '<View><Text name="text" value="$text"/></View>',
            },
            "tasks": [
                {"id": _uid(), "inner_id": i + 1, "data": {"text": f"full {i}"}}
                for i in range(3)
            ],
        }
    ).encode("utf-8")


def test_create_new_import_repeated_returns_the_earlier_project(
    db_conn, make_user, storage, jobs
):
    from project_models import Project

    user = make_user()
    title = f"Prov full {uuid.uuid4().hex[:8]}"
    jobs["titles"].update({title, f"{title} (1)"})
    body = _comprehensive_body(title)

    first_outcome, first = _import(db_conn, jobs, user, _stage(storage, body, "p.json"))
    _assert_imported(first_outcome, first)
    assert first.format == "comprehensive"
    assert first.source_manifest["target"] == {
        "kind": "new_project",
        "requested_by": user.id,
        "organization_id": None,
        "organization_group_id": None,
    }

    outcome, repeat = _import(db_conn, jobs, user, _stage(storage, body, "p.json"))

    _assert_no_op(outcome, repeat, first)
    assert repeat.result["project_title"] == first.result["project_title"]
    assert repeat.result["project_url"] == first.result["project_url"]
    created = db_conn.query(Project).filter(Project.title.like(f"{title}%")).all()
    assert [p.id for p in created] == [first.project_id]

    # Once the earlier project is deleted, the same file creates a new one.
    project = db_conn.query(Project).filter(Project.id == first.project_id).one()
    project.deleted_at = datetime.now(timezone.utc)
    db_conn.commit()

    outcome, fresh = _import(db_conn, jobs, user, _stage(storage, body, "p.json"))
    _assert_imported(outcome, fresh)
    assert fresh.project_id not in (None, first.project_id)


def test_create_new_import_by_another_user_is_imported(
    db_conn, make_user, storage, jobs
):
    one, two = make_user(), make_user()
    title = f"Prov full {uuid.uuid4().hex[:8]}"
    jobs["titles"].update({title, f"{title} (1)"})
    body = _comprehensive_body(title)

    _o, first = _import(db_conn, jobs, one, _stage(storage, body, "p.json"))
    outcome, other = _import(db_conn, jobs, two, _stage(storage, body, "p.json"))

    _assert_imported(outcome, other)
    assert other.project_id != first.project_id


def test_failed_import_keeps_provenance_and_blocks_nothing(
    db_conn, make_user, make_project, storage, jobs
):
    user = make_user()
    target = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")
    body = b'{"data": [{"data": '  # truncated JSON

    outcome, failed = _import(
        db_conn, jobs, user, _stage(storage, body, "t.json"), project_id=target.id
    )

    assert outcome["status"] == "error"
    assert failed.status == "failed"
    assert failed.payload_sha256 == hashlib.sha256(body).hexdigest()
    assert failed.source_manifest["payload"]["byte_size"] == len(body)

    # The same broken payload fails again instead of passing as a repeat.
    outcome, again = _import(
        db_conn, jobs, user, _stage(storage, body, "t.json"), project_id=target.id
    )
    assert outcome["status"] == "error"
    assert again.status == "failed"
    assert again.duplicate_of_job_id is None
    assert _task_texts(db_conn, target.id) == []


def test_identical_imports_at_the_same_time_write_once(
    db_conn, make_user, make_project, storage, jobs
):
    """The first import holds the key's advisory lock until it commits; the
    second waits on it, then finds the first one completed and is a no-op."""
    import import_stream
    from sqlalchemy import text

    user = make_user()
    target = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")
    body = _nested_body(["alpha", "beta"])
    first_id = _new_job(db_conn, jobs, user, _stage(storage, body, "a.json"), target.id)
    second_id = _new_job(
        db_conn, jobs, user, _stage(storage, body, "b.json"), target.id
    )

    real_driver = import_stream.run_nested_import
    entered, release = threading.Event(), threading.Event()

    def _held_driver(*args, **kwargs):
        entered.set()
        assert release.wait(30), "the test never released the first import"
        return real_driver(*args, **kwargs)

    outcomes = {}

    def _run(job_id):
        outcomes[job_id] = tasks.import_project(job_id)

    with patch.object(import_stream, "run_nested_import", _held_driver):
        first = threading.Thread(target=_run, args=(first_id,))
        first.start()
        assert entered.wait(30), "the first import never reached its driver"
        second = threading.Thread(target=_run, args=(second_id,))
        second.start()

        # Wait until the second import is blocked on the advisory lock.
        deadline = time.monotonic() + 30
        while True:
            db_conn.rollback()
            waiting = db_conn.execute(
                text(
                    "SELECT count(*) FROM pg_locks "
                    "WHERE locktype = 'advisory' AND NOT granted"
                )
            ).scalar()
            if waiting:
                break
            assert second.is_alive(), outcomes.get(second_id)
            assert time.monotonic() < deadline, "the second import never waited"
            time.sleep(0.05)

        release.set()
        first.join(60)
        second.join(60)

    assert not first.is_alive() and not second.is_alive()
    first_job, second_job = _load(db_conn, first_id), _load(db_conn, second_id)
    _assert_imported(outcomes[first_id], first_job)
    _assert_no_op(outcomes[second_id], second_job, first_job)
    assert _task_texts(db_conn, target.id) == ["alpha", "beta"]


def test_waiting_longer_than_the_lock_timeout_is_a_retryable_conflict(
    db_conn, make_user, make_project, storage, jobs
):
    """While another transaction holds the key's lock past the worker's
    lock_timeout (shortened here), the import fails with the retryable 409
    import_conflict, keeps its provenance and writes nothing."""
    import import_provenance as provenance
    from sqlalchemy import text

    user = make_user()
    target = make_project(created_by=user.id, title=f"Prov {_uid()[:8]}")
    body = _nested_body(["alpha"])
    key = provenance.idempotency_key(
        provenance.build_manifest(
            payload_sha256=hashlib.sha256(body).hexdigest(),
            byte_size=len(body),
            object_key="imports/x/t.json",
            source_connection_id=None,
            target=provenance.project_target(target.id),
            mode="nested",
        )
    )
    real_lock = provenance.lock_import_key

    def _short_wait(db, import_key):
        db.execute(text("SET LOCAL lock_timeout = '200ms'"))
        real_lock(db, import_key)

    job_id = _new_job(db_conn, jobs, user, _stage(storage, body, "t.json"), target.id)
    provenance.lock_import_key(db_conn, key)
    try:
        with patch.object(provenance, "lock_import_key", _short_wait):
            outcome = tasks.import_project(job_id)
    finally:
        db_conn.rollback()

    job = _load(db_conn, job_id)
    assert outcome["status"] == "error"
    assert job.status == "failed"
    assert job.error_message.startswith("409: import_conflict:")
    assert job.idempotency_key == key
    assert job.payload_sha256 == hashlib.sha256(body).hexdigest()
    assert _task_texts(db_conn, target.id) == []
