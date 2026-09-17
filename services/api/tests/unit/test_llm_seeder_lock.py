"""The llm_models seed is safe when several processes run it at once.

Every uvicorn worker (and every replica) runs ``initialize_llm_models`` at
startup when llm_models.yaml changed. Two of them used to both find a model
missing, both INSERT it, and the second one crashed its api container on
``llm_models_pkey`` (psycopg2 UniqueViolation, seen on staging). The seed
now holds a transaction-scoped Postgres advisory lock
(``database.LLM_SEED_LOCK_ID``).

The race test runs two real, committing seeds against a scratch copy of
``llm_models`` in its own schema, so the shared test tables stay untouched.
A barrier makes both seeds reach the first existence check together, which
is exactly the interleaving that crashed without the lock.
"""

from __future__ import annotations

import threading
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import database
from database import LLM_SEED_LOCK_ID, initialize_llm_models

JOIN_TIMEOUT = 90


@pytest.fixture(scope="module", autouse=True)
def _ensure_byom_schema():
    """Same backstop as test_llm_seeder_custom_safe: long-lived test DBs may
    predate the BYOM columns the ORM model carries."""
    from tests.fixtures.database import _get_engine
    from tests.utils.byom_schema import ensure_byom_llm_schema

    engine, _ = _get_engine()
    ensure_byom_llm_schema(engine)
    yield


@pytest.fixture
def scratch_sessions():
    """A session factory whose connections see only a private, empty copy
    of ``llm_models`` (own schema first on the search_path). Real commits,
    dropped afterwards."""
    from tests.fixtures.database import _get_engine

    engine, _ = _get_engine()
    schema = f"llm_seed_race_{uuid.uuid4().hex[:10]}"
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(
            text(
                f'CREATE TABLE "{schema}".llm_models '
                "(LIKE public.llm_models INCLUDING ALL)"
            )
        )

    race_engine = create_engine(
        engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )

    @event.listens_for(race_engine, "connect")
    def _scratch_search_path(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}", public')
        cursor.close()
        dbapi_connection.commit()

    factory = sessionmaker(bind=race_engine, autoflush=True)
    try:
        yield SimpleNamespace(factory=factory, schema=schema)
    finally:
        race_engine.dispose()
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _run_seeds(factory, count):
    results: dict[int, int] = {}
    errors: list[BaseException] = []

    def run(index):
        session = factory()
        try:
            results[index] = initialize_llm_models(session)
        except BaseException as exc:  # noqa: BLE001 - reported below
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    threads = [
        threading.Thread(target=run, args=(i,), daemon=True) for i in range(count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(JOIN_TIMEOUT)
    assert not any(t.is_alive() for t in threads), "a seed never finished"
    return results, errors


class TestConcurrentSeed:
    def test_two_seeds_at_once_do_not_collide(self, scratch_sessions, monkeypatch):
        from seeds.llm_models_loader import load_catalog

        catalog_size = len(load_catalog().models)
        assert catalog_size > 0

        # Both seeds wait here before their first existence check. Without
        # the lock they both pass, both insert, and the second one fails on
        # the primary key. With the lock the second seed never gets here
        # while the first holds the lock, so the barrier times out, the first
        # seed commits, and the second one finds every row.
        barrier = threading.Barrier(2, timeout=2)
        seen = threading.local()
        real_upsert = database._upsert_llm_model

        def upsert_after_both_arrived(db, model_data):
            if not getattr(seen, "done", False):
                seen.done = True
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            return real_upsert(db, model_data)

        monkeypatch.setattr(database, "_upsert_llm_model", upsert_after_both_arrived)

        results, errors = _run_seeds(scratch_sessions.factory, 2)

        assert errors == []
        assert sorted(results.values()) == [0, catalog_size]
        with scratch_sessions.factory() as session:
            rows = session.execute(text("SELECT count(*) FROM llm_models")).scalar()
        assert rows == catalog_size

    def test_seed_waits_for_a_lock_held_elsewhere(self, scratch_sessions):
        holder = scratch_sessions.factory()
        holder.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": LLM_SEED_LOCK_ID}
        )
        finished = threading.Event()
        errors: list[BaseException] = []

        def run():
            session = scratch_sessions.factory()
            try:
                initialize_llm_models(session)
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)
            finally:
                session.close()
                finished.set()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            # Still waiting while the other connection holds the lock.
            assert not finished.wait(1.5)
        finally:
            holder.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": LLM_SEED_LOCK_ID}
            )
            holder.close()
        thread.join(JOIN_TIMEOUT)
        assert finished.is_set()
        assert errors == []

    def test_the_lock_ends_with_the_seed_transaction(self, scratch_sessions):
        session = scratch_sessions.factory()
        try:
            initialize_llm_models(session)
        finally:
            session.close()

        probe = scratch_sessions.factory()
        try:
            got = probe.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": LLM_SEED_LOCK_ID}
            ).scalar()
            assert got is True
            probe.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": LLM_SEED_LOCK_ID}
            )
        finally:
            probe.close()


class TestLockHelper:
    def test_other_databases_run_unlocked(self):
        calls = []
        fake = SimpleNamespace(
            get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
            execute=lambda *args, **kwargs: calls.append(args),
        )

        database._lock_llm_seed(fake)

        assert calls == []

    def test_postgres_takes_the_transaction_lock_with_a_longer_timeout(self):
        statements = []
        fake = SimpleNamespace(
            get_bind=lambda: SimpleNamespace(
                dialect=SimpleNamespace(name="postgresql")
            ),
            execute=lambda stmt, params=None: statements.append(
                (str(stmt), params)
            ),
        )

        database._lock_llm_seed(fake)

        assert statements == [
            (
                f"SET LOCAL statement_timeout = {database.LLM_SEED_LOCK_TIMEOUT_MS}",
                None,
            ),
            ("SELECT pg_advisory_xact_lock(:key)", {"key": LLM_SEED_LOCK_ID}),
        ]
