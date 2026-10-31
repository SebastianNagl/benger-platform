"""Bounded retry of ``alembic upgrade`` on lock timeouts.

A migration on a hot table sets a 5 s ``lock_timeout``. Before the retry one
timeout failed the whole upgrade and sank the deploy, even when the blocking
transaction ended seconds later (2026-10-15).
"""

import os

import pytest
from sqlalchemy.exc import OperationalError

from utils import migration_lock_retry as mlr


class _PgError(Exception):
    def __init__(self, pgcode):
        super().__init__(f"pg error {pgcode}")
        self.pgcode = pgcode


def _wrapped(pgcode):
    return OperationalError("ALTER TABLE users ...", {}, _PgError(pgcode))


def test_retries_lock_timeouts_then_succeeds():
    calls, sleeps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise _wrapped("55P03")
        return "upgraded"

    result = mlr.run_with_lock_retry(
        flaky,
        attempts=6,
        delay_s=20,
        describe_holders=lambda: ["pid=42 app=<blank> state=idle in transaction"],
        sleep=sleeps.append,
    )
    assert result == "upgraded"
    assert len(calls) == 3
    assert sleeps == [20, 20]


def test_gives_up_after_the_last_attempt_with_the_original_error():
    sleeps = []
    err = _wrapped("55P03")

    def always_blocked():
        raise err

    with pytest.raises(OperationalError) as info:
        mlr.run_with_lock_retry(always_blocked, attempts=6, delay_s=20, sleep=sleeps.append)
    assert info.value is err
    assert sleeps == [20] * 5


def test_deadlocks_are_retried():
    calls = []

    def once_deadlocked():
        calls.append(1)
        if len(calls) == 1:
            raise _wrapped("40P01")
        return None

    mlr.run_with_lock_retry(once_deadlocked, attempts=2, delay_s=0, sleep=lambda s: None)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "exc",
    [_wrapped("42P01"), RuntimeError("boom"), ValueError("bad revision")],
)
def test_other_errors_fail_immediately(exc):
    calls = []

    def broken():
        calls.append(1)
        raise exc

    with pytest.raises(type(exc)):
        mlr.run_with_lock_retry(broken, attempts=6, delay_s=20, sleep=lambda s: None)
    assert len(calls) == 1


def test_pgcode_found_through_cause_chain():
    try:
        try:
            raise _PgError("55P03")
        except _PgError as inner:
            raise RuntimeError("alembic wrapper") from inner
    except RuntimeError as outer:
        assert mlr.is_retryable_lock_error(outer)


def test_defaults_are_six_attempts_twenty_seconds(monkeypatch):
    monkeypatch.delenv("MIGRATION_LOCK_RETRY_ATTEMPTS", raising=False)
    monkeypatch.delenv("MIGRATION_LOCK_RETRY_DELAY_S", raising=False)
    assert mlr.retry_settings() == (6, 20.0)
    monkeypatch.setenv("MIGRATION_LOCK_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("MIGRATION_LOCK_RETRY_DELAY_S", "0")
    assert mlr.retry_settings() == (2, 0.0)


def test_describe_lock_holders_skips_non_postgres():
    from sqlalchemy import create_engine

    assert mlr.describe_lock_holders(create_engine("sqlite://")) == []
    assert mlr.describe_lock_holders(None) == []


def test_env_py_runs_the_upgrade_through_the_retry():
    """env.py cannot be imported outside an alembic context, so check that
    the online path calls the retry wrapper (same approach as the logging
    guard test in test_database_migrations.py)."""
    env_py = os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "env.py")
    with open(env_py) as f:
        source = f.read()
    assert "run_with_lock_retry(" in source
    assert "benger-migrations" in source


@pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL") or "").startswith("postgresql"),
    reason="needs the Postgres test database",
)
def test_lock_holder_query_runs_on_postgres():
    from sqlalchemy import create_engine

    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        assert isinstance(mlr.describe_lock_holders(engine), list)
    finally:
        engine.dispose()
