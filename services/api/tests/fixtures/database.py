"""Database fixtures for BenGER API tests.

Uses the test PostgreSQL container (port 5433 local, test-db in Docker) with
per-test transaction rollback for isolation. Each test runs inside a SAVEPOINT
so session.commit() works normally, but the outer transaction is rolled back
after the test — no data leaks between tests.

Requires: `make test-start` to have the test PostgreSQL container running.
"""

import os
from typing import AsyncGenerator, Generator, List

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from database import Base, get_db
from main import app
from models import EvaluationType, User

# Module-level engine — reused across all tests for connection pooling
_engine = None
_SessionFactory = None


def _get_engine():
    global _engine, _SessionFactory
    if _engine is None:
        db_url = os.environ["DATABASE_URL"]
        _engine = create_engine(db_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
        _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine, _SessionFactory


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    """Create all tables once at session start."""
    engine, _ = _get_engine()
    try:
        Base.metadata.create_all(bind=engine)
        # `create_all` skips tables that already exist, which means partial
        # indexes added to existing tables (e.g. the singleton-human-run
        # unique index from migration 037) won't be created on a test DB
        # that was bootstrapped before the model picked them up. Force them
        # with an explicit CREATE INDEX IF NOT EXISTS so ON CONFLICT against
        # them resolves correctly even on long-lived test DB containers.
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_human_eval_run_per_project_metric "
                    "ON evaluation_runs (project_id, model_id) "
                    "WHERE model_id = 'human' "
                    "AND (eval_metadata ->> 'evaluation_type') = 'korrektur_falloesung'"
                )
            )
            # Migration 061: the korrektur_custom sibling of the index above.
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_human_eval_run_per_project_metric_custom "
                    "ON evaluation_runs (project_id, model_id) "
                    "WHERE model_id = 'human' "
                    "AND (eval_metadata ->> 'evaluation_type') = 'korrektur_custom'"
                )
            )
            # Migration 064: one active annotation per (task, user). Declared on
            # the Annotation model, but force it in idempotently too so a
            # long-lived test DB bootstrapped before it landed still gets the
            # backstop the IntegrityError path depends on.
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_annotations_active_task_user "
                    "ON annotations (task_id, completed_by) "
                    "WHERE was_cancelled = false"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE task_evaluations "
                    "ADD COLUMN IF NOT EXISTS created_by varchar "
                    "REFERENCES users(id) ON DELETE SET NULL"
                )
            )
            # Migration 045: research-data consent timestamp on users. Same
            # `create_all`-skips-existing-tables drift as the line above.
            conn.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN IF NOT EXISTS research_data_consent_accepted_at "
                    "TIMESTAMP WITH TIME ZONE"
                )
            )
            # Migration 063: pause/resume/retry lifecycle columns on
            # response_generations. Same create_all-skips-existing-tables
            # drift — a long-lived test DB bootstrapped before these landed
            # won't have them, so the generation router's success paths would
            # 500 on the missing columns. Force them in idempotently.
            conn.execute(
                text(
                    "ALTER TABLE response_generations "
                    "ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP WITH TIME ZONE"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE response_generations "
                    "ADD COLUMN IF NOT EXISTS resumed_at TIMESTAMP WITH TIME ZONE"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE response_generations "
                    "ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0"
                )
            )
            # dispatch_epoch: bumped per re-dispatch so resume/retry get fresh,
            # un-revoked deterministic task ids ({gen}:{run}:{epoch}).
            conn.execute(
                text(
                    "ALTER TABLE response_generations "
                    "ADD COLUMN IF NOT EXISTS dispatch_epoch INTEGER NOT NULL DEFAULT 0"
                )
            )
    except Exception as e:
        pytest.exit(
            f"Cannot connect to test PostgreSQL ({os.environ.get('DATABASE_URL')}). "
            f"Run 'make test-start' first. Error: {e}"
        )
    yield


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """Per-test database session with transaction rollback isolation.

    Each test runs inside a connection-level transaction. A SAVEPOINT allows
    session.commit() to work normally inside tests. After the test, the outer
    transaction is rolled back — all test data disappears cleanly.
    """
    engine, SessionFactory = _get_engine()

    connection = engine.connect()
    transaction = connection.begin()
    session = SessionFactory(bind=connection)

    # Begin a nested savepoint so test code can call session.commit()
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, trans):
        nonlocal nested
        if trans.nested and not trans._parent.nested:
            nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(test_db: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database dependency override."""

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    original_test_env = os.environ.get("TESTING")
    os.environ["TESTING"] = "true"

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        if original_test_env is None:
            os.environ.pop("TESTING", None)
        else:
            os.environ["TESTING"] = original_test_env


@pytest.fixture(scope="function")
def async_session(test_db: Session) -> Session:
    """Provide database session for async tests.

    NOTE: This is actually a sync session, but works with async HTTP tests.
    The tests can use this session directly since the FastAPI app uses sync DB operations.
    """
    return test_db


# ---- Async fixtures (Phase 0 of the asyncpg migration) ---------------------
#
# Real `AsyncSession`-bound fixture for endpoints that opted into the new
# `Depends(get_async_db)` dependency. Mirrors the sync `test_db` SAVEPOINT
# pattern — outer transaction held open, nested savepoint per
# session.commit(), outer transaction rolled back on teardown so tests stay
# isolated.
#
# The event-listener restart-savepoint trick uses `AsyncSession.sync_session`
# because the listener API still keys off the underlying sync Session.
# AsyncSession's commit drives the wrapped sync session's events, so this
# works the same way the sync fixture does — see SQLAlchemy docs "Joining a
# Session into an external Transaction (such as for test suites)" (async
# section).

def _build_async_engine():
    """Build a fresh async engine for the current test.

    Deliberately not cached: pytest-asyncio's default is one event loop
    per test. asyncpg connections bind to the loop they were created on,
    so a module-cached engine emits `RuntimeError: ... attached to a
    different loop` once a second test reuses pooled connections. A
    per-test engine sidesteps the whole loop-binding class of bug at the
    cost of one connection setup per test — negligible.

    Mirror the prod `server_settings` so tests that assert on
    statement_timeout / application_name exercise the same configured
    surface as production (with a test-distinct app name).
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    async_url = os.environ["ASYNC_DATABASE_URL"]
    return create_async_engine(
        async_url,
        pool_pre_ping=False,  # avoid the cross-loop ping bug entirely
        pool_size=1,
        max_overflow=2,
        connect_args={
            "server_settings": {
                "statement_timeout": "15000",
                "idle_in_transaction_session_timeout": "30000",
                "application_name": "benger-api-test-async",
            },
        },
    )


@pytest_asyncio.fixture(scope="function")
async def async_test_db():
    """Per-test AsyncSession bound to an outer transaction that rolls back
    on teardown. Test code calls `await session.commit()` freely; each
    commit only rolls the savepoint, not the outer transaction.
    """
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import AsyncSession

    async_engine = _build_async_engine()
    async with async_engine.connect() as conn:
        trans = await conn.begin()
        async_session = AsyncSession(bind=conn, expire_on_commit=False)
        savepoint = await conn.begin_nested()

        # AsyncSession exposes the underlying sync session via .sync_session
        # — that's where the event listener attaches.
        sync_session_obj = async_session.sync_session

        @event.listens_for(sync_session_obj, "after_transaction_end")
        def restart_savepoint(sess, transaction):
            nonlocal savepoint
            if transaction.nested and not transaction._parent.nested:
                # Start a new savepoint on the underlying sync connection
                # held by the AsyncConnection wrapper.
                savepoint = conn.sync_connection.begin_nested()

        try:
            yield async_session
        finally:
            await async_session.close()
            await trans.rollback()
    await async_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_test_client(async_test_db) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with dependency_overrides[get_async_db] wired to the
    async_test_db fixture so async handlers see the test transaction.

    Coexists with `async_client` (which serves the legacy sync-session
    async-HTTP path used by older tests). New async tests should prefer
    this fixture.
    """
    from database import get_async_db

    async def override_get_async_db():
        yield async_test_db

    app.dependency_overrides[get_async_db] = override_get_async_db

    original_test_env = os.environ.get("TESTING")
    os.environ["TESTING"] = "true"

    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://testserver")

    try:
        yield client
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        if original_test_env is None:
            os.environ.pop("TESTING", None)
        else:
            os.environ["TESTING"] = original_test_env


@pytest.fixture(scope="function")
def async_client(test_db: Session) -> Generator[AsyncClient, None, None]:
    """Create an async HTTP client for async tests."""

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    original_test_env = os.environ.get("TESTING")
    os.environ["TESTING"] = "true"

    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://testserver")

    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        if original_test_env is None:
            os.environ.pop("TESTING", None)
        else:
            os.environ["TESTING"] = original_test_env


# Alias for test_db to support both naming conventions
@pytest.fixture(scope="function")
def db(test_db: Session) -> Session:
    """Alias for test_db fixture to support both naming conventions."""
    return test_db


@pytest.fixture(scope="function")
def clean_database(test_db: Session) -> Session:
    """Clean the test database before each test."""
    test_db.rollback()
    return test_db


@pytest.fixture(scope="function")
def populated_database(
    test_db: Session,
    test_users: List[User],
    test_evaluation_types: List[EvaluationType],
) -> Session:
    """Database populated with test data."""
    from auth_module.user_service import init_demo_users

    init_demo_users(test_db)
    return test_db
