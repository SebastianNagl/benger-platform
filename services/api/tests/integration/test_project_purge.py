"""Project purge: a background job that removes every row of the project.

The API queues a ``project_purge_jobs`` row and the worker runs
``project_purge.run_project_purge_job``; these tests stand in for the worker
by running the same function on the test session.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm.attributes import set_committed_value

import project_purge
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ProjectPurgeJob,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import Annotation, Project, Task
from project_purge import PurgeAborted, purge_project_data, run_project_purge_job
from routers.projects.crud import _supersede_if_stale
from tests.integration.test_participant_tier import _as_user, _project, _user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@contextmanager
def queue_stub(fail: bool = False):
    """Stand-in for the Celery queue: records the purge job ids sent."""
    sent = []

    def _send(name, args=None, **_kw):
        if fail:
            raise ConnectionError("broker down")
        assert name == "tasks.purge_project"
        sent.append(args[0])
        return SimpleNamespace(id=f"celery-{args[0]}")

    with patch("routers.projects.crud.send_task_safe", side_effect=_send):
        yield sent


async def run_purge(db, job_id, task_batch=10):
    """Run the worker's purge job on the test session."""
    return await db.run_sync(
        lambda s: run_project_purge_job(s, job_id, task_batch=task_batch)
    )


async def _seed_generated_project(db, owner, *, tasks=3, deleted=False):
    """A project with, per task, one generation job, one generation, one
    annotation and one task evaluation of that generation, plus one
    project-level generation job (no task) with its own generation."""
    p = await _project(db, owner, tasks=tasks)
    task_ids = (await db.execute(select(Task.id).where(Task.project_id == p.id))).scalars().all()
    run = EvaluationRun(
        id=str(uuid.uuid4()), project_id=p.id, model_id="gpt-4o",
        evaluation_type_ids=["llm_judge"], metrics={}, status="completed",
        created_by=owner.id,
    )
    db.add(run)
    await db.flush()
    judge = EvaluationJudgeRun(id=str(uuid.uuid4()), evaluation_id=run.id, status="completed")
    db.add(judge)
    project_job = ResponseGeneration(
        id=str(uuid.uuid4()), project_id=p.id, task_id=None, model_id="gpt-4o",
        status="completed", created_by=owner.id,
    )
    db.add(project_job)
    await db.flush()
    for task_id in task_ids:
        rg = ResponseGeneration(
            id=str(uuid.uuid4()), project_id=p.id, task_id=task_id, model_id="gpt-4o",
            status="completed", created_by=owner.id,
        )
        db.add(rg)
        await db.flush()
        gen = Generation(
            id=str(uuid.uuid4()), generation_id=rg.id, task_id=task_id,
            model_id="gpt-4o", case_data="Fall", response_content="Antwort", run_index=0,
        )
        db.add(gen)
        await db.flush()
        db.add(Annotation(
            id=str(uuid.uuid4()), task_id=task_id, project_id=p.id,
            completed_by=owner.id, result=[{"v": 1}],
        ))
        db.add(TaskEvaluation(
            id=str(uuid.uuid4()), evaluation_id=run.id, judge_run_id=judge.id,
            task_id=task_id, generation_id=gen.id, field_name="answer",
            answer_type="text", ground_truth={"v": "a"}, prediction={"v": "b"},
            metrics={"score": 1}, passed=True,
        ))
    # The project-level job fans out into a generation of the first task.
    db.add(Generation(
        id=str(uuid.uuid4()), generation_id=project_job.id, task_id=task_ids[0],
        model_id="gpt-4o", case_data="Fall", response_content="Antwort", run_index=0,
    ))
    if deleted:
        p.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return p, task_ids


async def _count(db, model, *where):
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def _assert_gone(db, project_id, task_ids):
    assert (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none() is None
    assert await _count(db, Task, Task.project_id == project_id) == 0
    assert await _count(db, Annotation, Annotation.project_id == project_id) == 0
    assert await _count(db, TaskEvaluation, TaskEvaluation.task_id.in_(task_ids)) == 0
    assert await _count(db, EvaluationRun, EvaluationRun.project_id == project_id) == 0
    assert await _count(db, ResponseGeneration, ResponseGeneration.project_id == project_id) == 0
    assert await _count(db, Generation, Generation.task_id.in_(task_ids)) == 0


async def test_purge_job_removes_generations_and_generation_jobs(async_test_client, async_test_db):
    """F1: the purge used to leave the project's generation jobs and
    generations behind (no FK to tasks/projects, and the purge deleted only
    tasks and the project)."""
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, task_ids = await _seed_generated_project(db, owner, tasks=5)
    other, other_tasks = await _seed_generated_project(db, owner, tasks=1)

    with _as_user(owner):
        assert (await async_test_client.delete(f"/api/projects/{p.id}")).status_code == 200
    with _as_user(admin), queue_stub() as sent:
        r = await async_test_client.delete(f"/api/projects/{p.id}/purge")
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "pending" and body["project_id"] == p.id
        assert body["project_title"] == p.title
        assert sent == [body["job_id"]]
        # Nothing is deleted before the worker runs.
        assert await _count(db, Task, Task.project_id == p.id) == 5

        outcome = await run_purge(db, body["job_id"], task_batch=2)
        assert outcome["status"] == "completed", outcome

        r = await async_test_client.get(f"/api/projects/{p.id}/purge-jobs/{body['job_id']}")
        assert r.status_code == 200
        done = r.json()
        assert done["status"] == "completed" and done["progress"] == 100
        assert done["result"] == {
            "tasks": 5, "task_evaluations": 5, "generations": 6,
            "generation_jobs": 6, "projects": 1,
        }

    await _assert_gone(db, p.id, task_ids)
    # The other project keeps everything.
    assert await _count(db, ResponseGeneration, ResponseGeneration.project_id == other.id) == 2
    assert await _count(db, Generation, Generation.task_id.in_(other_tasks)) == 2
    assert await _count(db, TaskEvaluation, TaskEvaluation.task_id.in_(other_tasks)) == 1


async def test_purge_progress_is_recorded_per_batch(async_test_db):
    db = async_test_db
    owner = await _user(db)
    p, _ = await _seed_generated_project(db, owner, tasks=5, deleted=True)
    seen = []

    def _purge(s):
        return purge_project_data(
            s, p.id, task_batch=2, on_batch=lambda done, total: seen.append((done, total))
        )

    counts = await db.run_sync(_purge)
    assert seen == [(2, 5), (4, 5), (5, 5)]
    assert counts["tasks"] == 5 and counts["projects"] == 1


async def test_purge_refuses_a_live_project_and_accepts_a_gone_one(async_test_db):
    db = async_test_db
    owner = await _user(db)
    live, _ = await _seed_generated_project(db, owner, tasks=1)
    live_id = live.id  # the rollback inside the purge expires the ORM rows
    with pytest.raises(PurgeAborted):
        await db.run_sync(lambda s: purge_project_data(s, live_id))
    assert await _count(db, Task, Task.project_id == live_id) == 1
    counts = await db.run_sync(lambda s: purge_project_data(s, "no-such-project"))
    assert counts["projects"] == 0 and counts["tasks"] == 0


async def test_purge_job_fails_when_the_project_was_restored(async_test_client, async_test_db):
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, _ = await _seed_generated_project(db, owner, tasks=2, deleted=True)
    pid = p.id  # the rollback inside the purge expires the ORM rows
    with _as_user(admin), queue_stub():
        job_id = (await async_test_client.delete(f"/api/projects/{pid}/purge")).json()["job_id"]
    # A restore that slipped in before the job row existed (the API refuses
    # one once a purge was requested, so set it directly).
    await db.execute(update(Project).where(Project.id == pid).values(deleted_at=None))
    await db.commit()

    outcome = await run_purge(db, job_id)
    assert outcome["status"] == "failed"
    job = (await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.id == job_id))).scalar_one()
    await db.refresh(job)
    assert job.status == "failed" and "not soft-deleted" in job.error_message
    assert await _count(db, Task, Task.project_id == pid) == 2
    # A finished job is never run again.
    assert (await run_purge(db, job_id))["status"] == "skipped"


async def test_purge_request_while_live_returns_the_same_job_and_blocks_restore(
    async_test_client, async_test_db
):
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, _ = await _seed_generated_project(db, owner, tasks=1, deleted=True)
    with _as_user(admin), queue_stub() as sent:
        first = (await async_test_client.delete(f"/api/projects/{p.id}/purge")).json()
        # A pending job keeps its id; its message is sent again in case the
        # first one was lost.
        again = await async_test_client.delete(f"/api/projects/{p.id}/purge")
        assert again.status_code == 202 and again.json()["job_id"] == first["job_id"]
        assert again.json()["status"] == "pending"
        assert sent == [first["job_id"], first["job_id"]]

        r = await async_test_client.post(f"/api/projects/{p.id}/restore")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "purge_started"
        r = await async_test_client.post("/api/projects/bulk-restore", json={"project_ids": [p.id]})
        assert r.json()["restored"] == 0 and r.json()["failed"] == 1
        assert (await db.execute(select(Project.deleted_at).where(Project.id == p.id))).scalar_one() is not None

        # A running job is returned as is, without another message.
        await db.execute(
            update(ProjectPurgeJob)
            .where(ProjectPurgeJob.id == first["job_id"])
            .values(status="running")
        )
        await db.commit()
        running = (await async_test_client.delete(f"/api/projects/{p.id}/purge")).json()
        assert running["job_id"] == first["job_id"] and len(sent) == 2

        # A running job without progress for 30 minutes is dead: a new
        # request replaces it, and the old one is marked failed.
        await db.execute(
            update(ProjectPurgeJob)
            .where(ProjectPurgeJob.id == first["job_id"])
            .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=31))
        )
        await db.commit()
        replaced = (await async_test_client.delete(f"/api/projects/{p.id}/purge")).json()
        assert replaced["job_id"] != first["job_id"] and sent[-1] == replaced["job_id"]
        old = (await async_test_client.get(f"/api/projects/{p.id}/purge-jobs/{first['job_id']}")).json()
        assert old["status"] == "failed" and "Superseded" in old["error_message"]
        assert (await run_purge(db, first["job_id"]))["status"] == "skipped"


async def test_a_purge_job_runs_once_whatever_the_number_of_messages(
    async_test_client, async_test_db
):
    """A re-enqueued pending job and an acks_late redelivery both hand the
    worker a second message for the same job."""
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, task_ids = await _seed_generated_project(db, owner, tasks=2, deleted=True)
    pid = p.id
    with _as_user(admin), queue_stub():
        job_id = (await async_test_client.delete(f"/api/projects/{pid}/purge")).json()["job_id"]

    # Another copy has claimed the job and is still making progress.
    await db.execute(
        update(ProjectPurgeJob).where(ProjectPurgeJob.id == job_id).values(status="running")
    )
    await db.commit()
    outcome = await run_purge(db, job_id)
    assert outcome == {"status": "skipped", "job_id": job_id, "job_status": "running"}
    assert await _count(db, Task, Task.project_id == pid) == 2

    # That copy died: a redelivered message takes the job over and finishes it.
    await db.execute(
        update(ProjectPurgeJob)
        .where(ProjectPurgeJob.id == job_id)
        .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=31))
    )
    await db.commit()
    outcome = await run_purge(db, job_id)
    assert outcome["status"] == "completed", outcome
    assert outcome["result"]["tasks"] == 2 and outcome["result"]["projects"] == 1
    await _assert_gone(db, pid, task_ids)

    # A message arriving after the end changes nothing.
    assert (await run_purge(db, job_id))["status"] == "skipped"
    job = (await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.id == job_id))).scalar_one()
    await db.refresh(job)
    assert job.status == "completed" and job.result["tasks"] == 2


async def test_purge_queue_unavailable_marks_the_job_failed(async_test_client, async_test_db):
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, _ = await _seed_generated_project(db, owner, tasks=1, deleted=True)
    with _as_user(admin), queue_stub(fail=True):
        r = await async_test_client.delete(f"/api/projects/{p.id}/purge")
        assert r.status_code == 503
    job = (await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.project_id == p.id))).scalar_one()
    await db.refresh(job)
    assert job.status == "failed"
    # The failed job does not block a retry.
    with _as_user(admin), queue_stub() as sent:
        r = await async_test_client.delete(f"/api/projects/{p.id}/purge")
        assert r.status_code == 202 and r.json()["job_id"] != job.id and len(sent) == 1


async def test_a_purge_that_failed_half_way_blocks_restore_and_a_new_purge_finishes_it(
    async_test_client, async_test_db
):
    """The purge commits batch by batch, so a job that dies half way leaves
    a partial project: restoring it must be refused, and purging again must
    remove the rest."""
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, task_ids = await _seed_generated_project(db, owner, tasks=5, deleted=True)
    pid = p.id  # the rollback inside the purge expires the ORM rows
    with _as_user(admin), queue_stub():
        first = (await async_test_client.delete(f"/api/projects/{pid}/purge")).json()["job_id"]

    real_check = project_purge._locked_deleted_at
    calls = []

    def _dies_after_the_first_batch(s, project_id):
        calls.append(project_id)
        # Call 1 counts the tasks, call 2 opens batch 1, call 3 batch 2.
        if len(calls) == 3:
            raise ConnectionError("server closed the connection")
        return real_check(s, project_id)

    with patch("project_purge._locked_deleted_at", side_effect=_dies_after_the_first_batch):
        outcome = await run_purge(db, first, task_batch=2)
    assert outcome["status"] == "failed", outcome
    assert await _count(db, Task, Task.project_id == pid) == 3

    with _as_user(admin):
        r = await async_test_client.post(f"/api/projects/{pid}/restore")
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "purge_started"
        assert "cannot be undone" in detail["message"] and "Delete permanently" in detail["message"]
        r = await async_test_client.post("/api/projects/bulk-restore", json={"project_ids": [pid]})
        assert r.status_code == 200
        assert r.json() == {
            "restored": 0,
            "failed": 1,
            "failed_projects": [{"id": pid, "reason": detail["message"]}],
        }
    assert (await db.execute(select(Project.deleted_at).where(Project.id == pid))).scalar_one() is not None

    with _as_user(admin), queue_stub() as sent:
        r = await async_test_client.delete(f"/api/projects/{pid}/purge")
        assert r.status_code == 202, r.text
        retry = r.json()["job_id"]
        assert retry != first and sent == [retry]
        outcome = await run_purge(db, retry, task_batch=2)
        assert outcome["status"] == "completed", outcome
        assert outcome["result"]["tasks"] == 3 and outcome["result"]["projects"] == 1
    await _assert_gone(db, pid, task_ids)


async def test_a_stale_job_is_reported_failed_to_its_poll(async_test_client, async_test_db):
    """A running job whose worker died never finishes by itself; the client
    polls it until it is completed or failed. A pending job only waits for a
    free worker of the shared bulk queue, which can take long."""
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, _ = await _seed_generated_project(db, owner, tasks=1, deleted=True)
    with _as_user(admin), queue_stub():
        job_id = (await async_test_client.delete(f"/api/projects/{p.id}/purge")).json()["job_id"]
        url = f"/api/projects/{p.id}/purge-jobs/{job_id}"
        await db.execute(
            update(ProjectPurgeJob)
            .where(ProjectPurgeJob.id == job_id)
            .values(updated_at=datetime.now(timezone.utc) - timedelta(hours=3))
        )
        await db.commit()
        assert (await async_test_client.get(url)).json()["status"] == "pending"
        assert (await async_test_client.get(url)).json()["status"] == "pending"

        await db.execute(
            update(ProjectPurgeJob)
            .where(ProjectPurgeJob.id == job_id)
            .values(status="running", updated_at=datetime.now(timezone.utc) - timedelta(minutes=31))
        )
        await db.commit()
        polled = (await async_test_client.get(url)).json()
        assert polled["status"] == "failed" and "Superseded" in polled["error_message"]
    stored = (await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.id == job_id))).scalar_one()
    await db.refresh(stored)
    assert stored.status == "failed"
    assert (await run_purge(db, job_id))["status"] == "skipped"


async def test_a_supersede_racing_a_fresh_reclaim_leaves_the_job_running(
    async_test_client, async_test_db
):
    """The API read the job as stale, then a redelivered message reclaimed it
    before the API wrote its verdict: the job stays with that worker, and a
    new request starts no second purge of the project."""
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, _ = await _seed_generated_project(db, owner, tasks=1, deleted=True)
    with _as_user(admin), queue_stub():
        job_id = (await async_test_client.delete(f"/api/projects/{p.id}/purge")).json()["job_id"]
    # The worker's reclaim: running, with fresh progress.
    await db.execute(
        update(ProjectPurgeJob).where(ProjectPurgeJob.id == job_id).values(status="running")
    )
    await db.commit()
    job = (await db.execute(select(ProjectPurgeJob).where(ProjectPurgeJob.id == job_id))).scalar_one()
    # What the API had read just before the reclaim.
    set_committed_value(job, "updated_at", datetime.now(timezone.utc) - timedelta(minutes=31))

    assert await _supersede_if_stale(db, job) is False
    assert job.status == "running" and job.error_message is None

    with _as_user(admin), queue_stub() as sent:
        r = await async_test_client.delete(f"/api/projects/{p.id}/purge")
        assert r.status_code == 202 and r.json()["job_id"] == job_id and sent == []
        polled = (await async_test_client.get(f"/api/projects/{p.id}/purge-jobs/{job_id}")).json()
        assert polled["status"] == "running"
    assert await _count(db, ProjectPurgeJob, ProjectPurgeJob.project_id == p.id) == 1


async def test_purge_job_status_access(async_test_client, async_test_db):
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p, _ = await _seed_generated_project(db, owner, tasks=1, deleted=True)
    with _as_user(admin), queue_stub():
        job_id = (await async_test_client.delete(f"/api/projects/{p.id}/purge")).json()["job_id"]
        assert (await async_test_client.get(f"/api/projects/other/purge-jobs/{job_id}")).status_code == 404
        assert (await async_test_client.get(f"/api/projects/{p.id}/purge-jobs/nope")).status_code == 404
    with _as_user(owner):
        assert (await async_test_client.get(f"/api/projects/{p.id}/purge-jobs/{job_id}")).status_code == 403


async def test_bulk_purge_queues_one_job_per_deleted_project(async_test_client, async_test_db):
    db = async_test_db
    owner = await _user(db)
    admin = await _user(db, superadmin=True)
    p1, t1 = await _seed_generated_project(db, owner, tasks=2, deleted=True)
    p2, t2 = await _seed_generated_project(db, owner, tasks=1, deleted=True)
    live, _ = await _seed_generated_project(db, owner, tasks=1)
    with _as_user(admin), queue_stub() as sent:
        r = await async_test_client.post(
            "/api/projects/bulk-purge", json={"project_ids": [p1.id, p2.id, live.id, "missing"]}
        )
        assert r.status_code == 202, r.text
        body = r.json()
    assert body["queued"] == 2 and body["failed"] == 2
    assert {f["reason"] for f in body["failed_projects"]} == {"Not soft-deleted", "Project not found"}
    assert sorted(j["project_id"] for j in body["jobs"]) == sorted([p1.id, p2.id])
    assert sorted(sent) == sorted(j["job_id"] for j in body["jobs"])
    for job in body["jobs"]:
        assert (await run_purge(db, job["job_id"]))["status"] == "completed"
    await _assert_gone(db, p1.id, t1)
    await _assert_gone(db, p2.id, t2)
    assert await _count(db, Task, Task.project_id == live.id) == 1


async def test_task_delete_cascades_to_its_generations(async_test_client, async_test_db):
    """Since migration 140 a deleted task takes its generation jobs and
    generations along, whatever path deletes it."""
    db = async_test_db
    owner = await _user(db)
    p, task_ids = await _seed_generated_project(db, owner, tasks=2)
    with _as_user(owner):
        r = await async_test_client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete", json={"task_ids": [task_ids[1]]}
        )
        assert r.status_code == 200, r.text
    assert await _count(db, Generation, Generation.task_id == task_ids[1]) == 0
    assert await _count(db, ResponseGeneration, ResponseGeneration.task_id == task_ids[1]) == 0
    assert await _count(db, Generation, Generation.task_id == task_ids[0]) == 2

    # Deleting a generation job takes its generations along too.
    project_job = (await db.execute(
        select(ResponseGeneration.id).where(
            ResponseGeneration.project_id == p.id, ResponseGeneration.task_id.is_(None)
        )
    )).scalar_one()
    await db.execute(delete(ResponseGeneration).where(ResponseGeneration.id == project_job))
    await db.commit()
    assert await _count(db, Generation, Generation.generation_id == project_job) == 0
