"""Project export/import jobs report what they committed, at any size.

The import drivers flush and ``expunge_all`` the session every
``_IMPORT_BATCH`` (200) rows to bound memory. The worker used to hold its
``ImportJob`` row in that same session across the driver call, so from 200
records on the row was detached when the worker set the final status: the
data was committed but the job ended ``failed`` with "ImportJob ... is not
bound to a Session". A client that trusts the status retries, and a retried
create-new import duplicates the project.

These tests drive the real ``tasks.export_project`` / ``tasks.import_project``
bodies against the real test Postgres and a local object storage, with more
rows than one batch, and check the job row against the database: a finished
job says ``completed`` with counts matching the rows written, a job that
fails part-way says ``failed`` with nothing written, and an error after the
commit leaves the job ``completed``.
"""

import csv
import io
import json
import os
import uuid
from unittest.mock import patch

import pytest

import tasks

pytestmark = [pytest.mark.integration, pytest.mark.database]

# Same value the drivers batch on: one full flush + expunge_all boundary plus
# a partial batch, so every driver hits the detach point at least once.
from import_stream import _IMPORT_BATCH  # noqa: E402

ROWS = _IMPORT_BATCH + 50


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
    """Create/track export + import jobs, and delete them (and the projects
    an import created) before the shared cleanup runs."""
    from models import ExportJob, ImportJob, Organization, OrgStorageConnection
    from project_models import Project

    state = {"user_ids": set(), "titles": set(), "orgs": [], "connections": []}

    yield state

    db_conn.rollback()
    if state["titles"]:
        created = [
            p for (p,) in db_conn.query(Project.id)
            .filter(Project.title.in_(state["titles"])).all()
        ]
        cleanup.project_ids.extend(p for p in created if p not in cleanup.project_ids)
    if state["user_ids"]:
        users = list(state["user_ids"])
        db_conn.query(ImportJob).filter(ImportJob.requested_by.in_(users)).delete(
            synchronize_session=False
        )
        db_conn.query(ExportJob).filter(ExportJob.requested_by.in_(users)).delete(
            synchronize_session=False
        )
    if state["connections"]:
        db_conn.query(OrgStorageConnection).filter(
            OrgStorageConnection.id.in_(state["connections"])
        ).delete(synchronize_session=False)
    if state["orgs"]:
        db_conn.query(Organization).filter(
            Organization.id.in_(state["orgs"])
        ).delete(synchronize_session=False)
    db_conn.commit()


def _project_with_tasks(db, cleanup, user, title, rows=ROWS):
    from project_models import Project, Task

    project = Project(id=_uid(), title=title, created_by=user.id)
    db.add(project)
    db.flush()
    for i in range(rows):
        db.add(Task(
            id=_uid(), project_id=project.id, inner_id=i + 1,
            data={"text": f"{title} task {i}"}, created_by=user.id,
        ))
    db.commit()
    cleanup.project_ids.append(project.id)
    return project


def _export(db, storage, jobs, project, user, fmt) -> bytes:
    from models import ExportJob

    job = ExportJob(
        id=_uid(), project_id=project.id, requested_by=user.id,
        format=fmt, status="pending",
    )
    db.add(job)
    db.commit()
    jobs["user_ids"].add(user.id)

    outcome = tasks.export_project(job.id)

    db.expire_all()
    job = db.query(ExportJob).filter(ExportJob.id == job.id).one()
    assert outcome["status"] == "completed", outcome
    assert (job.status, job.error_message, job.progress) == ("completed", None, 100)
    with open(os.path.join(storage.local_storage_path, job.object_key), "rb") as f:
        body = f.read()
    assert job.byte_size == len(body)
    return body


def _stage(storage, body: bytes, name: str) -> str:
    key = f"imports/{_uid()}/{name}"
    path = os.path.join(storage.local_storage_path, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return key


def _import(db, jobs, user, object_key, project_id=None, mode=None, **job_fields):
    from models import ImportJob

    job = ImportJob(
        id=_uid(), project_id=project_id, requested_by=user.id,
        object_key=object_key, status="pending", **job_fields,
    )
    db.add(job)
    db.commit()
    jobs["user_ids"].add(user.id)

    outcome = tasks.import_project(job.id, mode=mode)

    db.expire_all()
    return outcome, db.query(ImportJob).filter(ImportJob.id == job.id).one()


def _projects_titled(db, title_prefix):
    from project_models import Project

    return db.query(Project).filter(Project.title.like(f"{title_prefix}%")).all()


def _task_count(db, project_id):
    from project_models import Task

    return db.query(Task).filter(Task.project_id == project_id).count()


def _assert_completed(outcome, job):
    assert job.error_message is None, job.error_message
    assert job.status == "completed"
    assert job.progress == 100
    assert job.expires_at is not None
    assert outcome["status"] == "completed", outcome
    assert outcome["project_id"] == job.project_id


@pytest.mark.parametrize(
    "fmt", ["json", "csv", "label_studio", "comprehensive", "ndjson", "ndjson_gz"]
)
def test_export_of_a_large_project_reports_completed(
    db_conn, cleanup, make_user, storage, jobs, fmt,
):
    """The export streams under per-row expunges (``drain_expunge``), never
    ``expunge_all``; its job row stays bound and ends completed at any size."""
    user = make_user()
    source = _project_with_tasks(db_conn, cleanup, user, f"Export {fmt} {_uid()[:8]}")

    body = _export(db_conn, storage, jobs, source, user, fmt)

    if fmt == "ndjson_gz":
        import gzip

        body = gzip.decompress(body)
    assert body.count(b"task ") >= ROWS


@pytest.mark.parametrize("fmt", ["comprehensive", "ndjson"])
def test_create_new_import_of_a_large_export_reports_completed(
    db_conn, cleanup, make_user, storage, jobs, fmt,
):
    user = make_user()
    title = f"Status {fmt} {uuid.uuid4().hex[:8]}"
    jobs["titles"].update({title, f"{title} (1)"})
    source = _project_with_tasks(db_conn, cleanup, user, title)

    body = _export(db_conn, storage, jobs, source, user, fmt)
    outcome, job = _import(db_conn, jobs, user, _stage(storage, body, f"p.{fmt}"))

    _assert_completed(outcome, job)
    created = [p for p in _projects_titled(db_conn, title) if p.id != source.id]
    assert [p.id for p in created] == [job.project_id]
    assert _task_count(db_conn, job.project_id) == ROWS
    assert job.format == "comprehensive"
    assert job.result["project_id"] == job.project_id
    assert job.result["statistics"]["imported_counts"]["tasks"] == ROWS

    # An acks_late redelivery of the finished job must not import again.
    again = tasks.import_project(job.id)
    assert again["status"] == "skipped"
    assert len(_projects_titled(db_conn, title)) == 2


def _nested_body(rows=ROWS) -> bytes:
    """A Label-Studio style nested payload: the format of an import into an
    existing project from the Project data page."""
    return json.dumps(
        {"data": [{"data": {"text": f"nested {i}"}} for i in range(rows)]}
    ).encode("utf-8")


def test_nested_import_into_existing_project_reports_completed(
    db_conn, make_user, make_project, storage, jobs,
):
    user = make_user()
    target = make_project(created_by=user.id, title=f"Nested dst {_uid()[:8]}")

    outcome, job = _import(
        db_conn, jobs, user, _stage(storage, _nested_body(), "tasks.json"),
        project_id=target.id,
    )

    _assert_completed(outcome, job)
    assert job.project_id == target.id
    assert job.format == "nested"
    assert job.result["created_tasks"] == ROWS
    assert _task_count(db_conn, target.id) == ROWS


def test_cloud_tabular_import_reports_completed(
    db_conn, cleanup, make_user, make_project, storage, jobs,
):
    from models import Organization, OrgStorageConnection

    user = make_user()
    target = make_project(created_by=user.id, title=f"Tabular dst {_uid()[:8]}")
    org = Organization(
        id=_uid(), name="Tabular Org", display_name="Tabular Org",
        slug=f"tabular-{_uid()[:8]}",
    )
    db_conn.add(org)
    db_conn.flush()
    connection = OrgStorageConnection(
        id=_uid(), organization_id=org.id, name="bucket", bucket="b",
        encrypted_access_key="x", encrypted_secret_key="y",
    )
    db_conn.add(connection)
    db_conn.commit()
    jobs["orgs"].append(org.id)
    jobs["connections"].append(connection.id)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["text"])
    for i in range(ROWS):
        writer.writerow([f"row {i}"])
    body = out.getvalue().encode("utf-8")

    import org_storage_connection_service as svc

    with patch.object(svc, "head_object_size", return_value=len(body)), patch.object(
        svc, "download_to_fileobj", side_effect=lambda conn, key, f: f.write(body)
    ):
        outcome, job = _import(
            db_conn, jobs, user, "folder/rows.csv", project_id=target.id,
            source_connection_id=connection.id,
        )

    _assert_completed(outcome, job)
    assert job.format == "csv"
    assert job.result["created_tasks"] == ROWS
    assert _task_count(db_conn, target.id) == ROWS


def _copy_with_new_generations(db_conn, cleanup, storage, jobs, user, make_llm_model):
    """The round trip a merge serves: export a project, import the copy, add
    one generation per task there, and export the copy again."""
    from models import Generation, ResponseGeneration
    from project_models import Task

    title = f"Merge src {uuid.uuid4().hex[:8]}"
    jobs["titles"].update({title, f"{title} (1)"})
    original = _project_with_tasks(db_conn, cleanup, user, title)
    body = _export(db_conn, storage, jobs, original, user, "comprehensive")
    outcome, copy_job = _import(db_conn, jobs, user, _stage(storage, body, "a.json"))
    _assert_completed(outcome, copy_job)
    copy_id = copy_job.project_id

    model = make_llm_model()
    for (task_id,) in db_conn.query(Task.id).filter(Task.project_id == copy_id):
        rg = ResponseGeneration(
            id=_uid(), project_id=copy_id, task_id=task_id, model_id=model.id,
            status="completed", runs_requested=1, created_by=user.id,
        )
        db_conn.add(rg)
        db_conn.flush()
        db_conn.add(Generation(
            id=_uid(), generation_id=rg.id, task_id=task_id, model_id=model.id,
            case_data="{}", response_content=f"answer {task_id}",
            parse_status="success", run_index=0, status="completed",
        ))
    db_conn.commit()

    from project_models import Project

    copy = db_conn.query(Project).filter(Project.id == copy_id).one()
    return original, _export(db_conn, storage, jobs, copy, user, "comprehensive")


def _generation_count(db, project_id):
    from models import Generation
    from project_models import Task

    return (
        db.query(Generation)
        .join(Task, Task.id == Generation.task_id)
        .filter(Task.project_id == project_id)
        .count()
    )


def test_merge_import_of_a_large_export_reports_completed(
    db_conn, cleanup, make_user, make_llm_model, storage, jobs,
):
    user = make_user()
    original, body = _copy_with_new_generations(
        db_conn, cleanup, storage, jobs, user, make_llm_model
    )

    outcome, job = _import(
        db_conn, jobs, user, _stage(storage, body, "b.json"),
        project_id=original.id, mode="merge",
    )

    _assert_completed(outcome, job)
    assert job.format == "merge"
    stats = job.result["statistics"]
    assert stats["matched_tasks"] == ROWS
    assert stats["added_counts"]["generations"] == ROWS
    assert _generation_count(db_conn, original.id) == ROWS


def test_create_new_import_failing_part_way_writes_nothing(
    db_conn, cleanup, make_user, storage, jobs,
):
    import import_stream

    user = make_user()
    title = f"Fail new {uuid.uuid4().hex[:8]}"
    jobs["titles"].update({title, f"{title} (1)"})
    source = _project_with_tasks(db_conn, cleanup, user, title)
    body = _export(db_conn, storage, jobs, source, user, "comprehensive")

    real_insert = import_stream._insert_task
    seen = {"n": 0}

    def _insert_then_fail(ctx, task_data):
        seen["n"] += 1
        if seen["n"] == ROWS - 10:  # past the first flush + expunge_all
            raise RuntimeError("disk full")
        real_insert(ctx, task_data)

    with patch.object(import_stream, "_insert_task", _insert_then_fail):
        outcome, job = _import(db_conn, jobs, user, _stage(storage, body, "f.json"))

    assert seen["n"] == ROWS - 10
    assert outcome["status"] == "error"
    assert job.status == "failed"
    assert job.error_message == "disk full"
    assert job.project_id is None
    assert job.result is None
    assert [p.id for p in _projects_titled(db_conn, title)] == [source.id]


def test_merge_failing_part_way_writes_nothing(
    db_conn, cleanup, make_user, make_llm_model, storage, jobs,
):
    import import_stream

    user = make_user()
    original, body = _copy_with_new_generations(
        db_conn, cleanup, storage, jobs, user, make_llm_model
    )

    real_merge = import_stream._MERGE_DISPATCH["generation"]
    seen = {"n": 0}

    def _merge_then_fail(ctx, state, rec):
        seen["n"] += 1
        if seen["n"] == ROWS - 10:
            raise RuntimeError("connection lost")
        real_merge(ctx, state, rec)

    with patch.dict(import_stream._MERGE_DISPATCH, {"generation": _merge_then_fail}):
        outcome, job = _import(
            db_conn, jobs, user, _stage(storage, body, "g.json"),
            project_id=original.id, mode="merge",
        )

    assert seen["n"] == ROWS - 10
    assert outcome["status"] == "error"
    assert (job.status, job.error_message) == ("failed", "connection lost")
    assert job.result is None
    assert _generation_count(db_conn, original.id) == 0


def test_error_after_the_commit_does_not_flip_a_completed_job_to_failed(
    db_conn, make_user, make_project, storage, jobs,
):
    """The final status commits with the data. Anything that goes wrong after
    that commit cannot change what was written, so it must not relabel the
    job failed (which would invite a duplicating retry)."""
    user = make_user()
    target = make_project(created_by=user.id, title=f"Post dst {_uid()[:8]}")
    body = _nested_body()

    def _publish(channel, payload):
        if payload.get("status") == "completed":
            raise RuntimeError("redis gone")

    with patch.object(tasks, "_publish_progress", side_effect=_publish):
        outcome, job = _import(
            db_conn, jobs, user, _stage(storage, body, "t.json"), project_id=target.id
        )

    assert (job.status, job.error_message) == ("completed", None)
    assert outcome["status"] == "completed"
    assert _task_count(db_conn, target.id) == ROWS


def test_driver_error_after_the_commit_keeps_the_created_project_completed(
    db_conn, cleanup, make_user, storage, jobs,
):
    """Same rule inside the driver: the create-new import's notification runs
    after its commit, so a failure there leaves a completed job pointing at
    the project that was created."""
    import import_stream

    user = make_user()
    title = f"Notify {uuid.uuid4().hex[:8]}"
    jobs["titles"].update({title, f"{title} (1)"})
    source = _project_with_tasks(db_conn, cleanup, user, title)
    body = _export(db_conn, storage, jobs, source, user, "comprehensive")

    with patch.object(
        import_stream, "_notify_project_imported", side_effect=RuntimeError("smtp down")
    ):
        outcome, job = _import(db_conn, jobs, user, _stage(storage, body, "n.json"))

    _assert_completed(outcome, job)
    created = [p for p in _projects_titled(db_conn, title) if p.id != source.id]
    assert [p.id for p in created] == [job.project_id]
    assert _task_count(db_conn, job.project_id) == ROWS
