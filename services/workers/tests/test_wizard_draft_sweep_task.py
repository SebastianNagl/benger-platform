"""Beat task of the stale-draft sweep (creation-wizard drafts, CORE 2.55).

The selection and the conditional stamp are pinned in the API suite
(``tests/integration/test_wizard_draft_sweep.py``) against the shared
``wizard_drafts`` module; here the worker wiring: the task calls that module
with a session it closes and a sender that publishes ``tasks.purge_project``,
and beat runs it daily on the maintenance queue.
"""

from types import SimpleNamespace

import pytest

import tasks


class _Session:
    def __init__(self):
        self.closed = False
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_the_task_runs_the_shared_sweep_and_publishes_purges(monkeypatch):
    import wizard_drafts

    session = _Session()
    published = []
    calls = []

    def sweep(db, send):
        calls.append(db)
        send("job-1")
        return {"stamped": ["p-1"], "purge_queued": ["p-1"]}

    def send_task(name, args=None, **_kw):
        published.append((name, args))
        return SimpleNamespace(id="celery-1")

    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(wizard_drafts, "purge_stale_wizard_drafts", sweep)
    monkeypatch.setattr(tasks.app, "send_task", send_task)
    result = tasks.purge_stale_wizard_drafts.run()
    assert result == {"stamped": ["p-1"], "purge_queued": ["p-1"]}
    assert calls == [session] and session.closed
    assert published == [("tasks.purge_project", ["job-1"])]


def test_a_failing_sweep_rolls_back_and_closes(monkeypatch):
    import wizard_drafts

    session = _Session()

    def sweep(db, send):
        raise RuntimeError("db down")

    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    monkeypatch.setattr(wizard_drafts, "purge_stale_wizard_drafts", sweep)
    with pytest.raises(RuntimeError):
        tasks.purge_stale_wizard_drafts.run()
    assert session.rolled_back and session.closed


def test_scheduled_daily_and_routed():
    import celery_queues
    from worker_celery import app

    entry = app.conf.beat_schedule["purge-stale-wizard-drafts"]
    assert entry["task"] == "tasks.purge_stale_wizard_drafts"
    assert celery_queues.queue_for(entry["task"]) == celery_queues.MAINTENANCE
    assert "options" not in entry
