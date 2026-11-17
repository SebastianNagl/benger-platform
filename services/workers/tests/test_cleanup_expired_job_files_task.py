"""The ``tasks.cleanup_expired_job_files`` beat task (F3).

The sweep itself (which files go, which stay) is tested against Postgres in
services/api/tests/integration/test_job_file_cleanup.py; here the Celery
wrapper, its daily schedule and its queue.
"""

import pytest
from celery.schedules import crontab

import celery_queues
import job_file_cleanup
import tasks


class _Session:
    closed = False

    def close(self):
        self.closed = True


def test_sweeps_with_the_object_storage_on_a_fresh_session(monkeypatch):
    from storage.object_storage import object_storage

    session = _Session()
    calls = []
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        job_file_cleanup,
        "cleanup_expired_job_files",
        lambda db, storage: calls.append((db, storage)) or {"exports": {}, "imports": {}},
    )
    assert tasks.cleanup_expired_job_files.run() == {"exports": {}, "imports": {}}
    assert calls == [(session, object_storage)] and session.closed


def test_closes_the_session_when_the_sweep_raises(monkeypatch):
    session = _Session()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    def _boom(db, storage):
        raise RuntimeError("db gone")

    monkeypatch.setattr(job_file_cleanup, "cleanup_expired_job_files", _boom)
    with pytest.raises(RuntimeError):
        tasks.cleanup_expired_job_files.run()
    assert session.closed


def test_scheduled_once_a_day_on_the_maintenance_queue():
    from worker_celery import app

    entries = [
        e for e in app.conf.beat_schedule.values()
        if e["task"] == "tasks.cleanup_expired_job_files"
    ]
    assert len(entries) == 1
    schedule = entries[0]["schedule"]
    assert isinstance(schedule, crontab)
    assert len(schedule.hour) == 1 and len(schedule.minute) == 1
    assert "tasks.cleanup_expired_job_files" in app.tasks
    assert celery_queues.queue_for("tasks.cleanup_expired_job_files") == celery_queues.MAINTENANCE
