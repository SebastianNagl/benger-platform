"""The ``tasks.purge_project`` Celery wrapper around the shared purge runner.

The runner itself (batched deletes, job lifecycle) is tested against Postgres
in services/api/tests/integration/test_project_purge.py.
"""

import pytest

import celery_queues
import project_purge
import tasks


class _Session:
    closed = False

    def close(self):
        self.closed = True


def test_runs_the_job_on_a_fresh_session_and_closes_it(monkeypatch):
    session = _Session()
    calls = []
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        project_purge,
        "run_project_purge_job",
        lambda db, job_id: calls.append((db, job_id)) or {"status": "completed"},
    )
    assert tasks.purge_project.run("job-1") == {"status": "completed"}
    assert calls == [(session, "job-1")] and session.closed


def test_closes_the_session_when_the_runner_raises(monkeypatch):
    session = _Session()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    def _boom(db, job_id):
        raise RuntimeError("db gone")

    monkeypatch.setattr(project_purge, "run_project_purge_job", _boom)
    with pytest.raises(RuntimeError):
        tasks.purge_project.run("job-1")
    assert session.closed


def test_purge_runs_on_the_bulk_queue_with_its_time_limits():
    assert celery_queues.queue_for("tasks.purge_project") == celery_queues.BULK
    assert celery_queues.time_limits_for("tasks.purge_project") == celery_queues.QUEUE_TIME_LIMITS[
        celery_queues.BULK
    ]
