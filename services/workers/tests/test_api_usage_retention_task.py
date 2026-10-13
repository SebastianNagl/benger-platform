"""Retention beat task for the access-key usage log."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import tasks


class _FakeSession:
    def __init__(self, rowcounts):
        self.rowcounts = list(rowcounts)
        self.statements = []
        self.commits = 0
        self.closed = False
        self.rolled_back = False

    def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(rowcount=self.rowcounts.pop(0))

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _run(monkeypatch, rowcounts, **kwargs):
    session = _FakeSession(rowcounts)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    result = tasks.cleanup_api_key_usage_events.run(**kwargs)
    return session, result


def test_deletes_in_batches_until_a_short_batch(monkeypatch):
    monkeypatch.setattr(tasks, "API_USAGE_CLEANUP_BATCH", 2)
    session, result = _run(monkeypatch, [2, 2, 1])
    assert result["deleted"] == 5
    assert session.commits == 3 and session.closed


def test_retention_days_from_env(monkeypatch):
    monkeypatch.setenv("API_USAGE_RETENTION_DAYS", "30")
    before = datetime.now(timezone.utc)
    _session, result = _run(monkeypatch, [0])
    cutoff = datetime.fromisoformat(result["cutoff"])
    assert result["retention_days"] == 30
    assert abs((before - timedelta(days=30) - cutoff).total_seconds()) < 5


def test_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("API_USAGE_RETENTION_DAYS", "soon")
    _session, result = _run(monkeypatch, [0])
    assert result["retention_days"] == 400


def test_errors_roll_back_and_close(monkeypatch):
    class Boom(_FakeSession):
        def execute(self, stmt):
            raise RuntimeError("db down")

    session = Boom([])
    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)
    with pytest.raises(RuntimeError):
        tasks.cleanup_api_key_usage_events.run()
    assert session.rolled_back and session.closed


def test_delete_statement_targets_only_old_rows():
    from sqlalchemy.dialects import postgresql

    cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sql = str(
        tasks.build_delete_api_usage_batch(cutoff, 500).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert sql.startswith("DELETE FROM api_key_usage_events")
    assert "api_key_usage_events.created_at <" in sql
    assert "LIMIT 500" in sql


def test_scheduled_daily_and_routed():
    import celery_queues
    from worker_celery import app

    entry = app.conf.beat_schedule["cleanup-api-key-usage-events"]
    assert entry["task"] == "tasks.cleanup_api_key_usage_events"
    assert celery_queues.queue_for(entry["task"]) == celery_queues.MAINTENANCE
