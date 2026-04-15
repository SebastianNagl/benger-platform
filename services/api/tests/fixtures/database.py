"""Database fixtures for BenGER API tests.

Uses the test PostgreSQL container (port 5433 local, test-db in Docker) with
per-test transaction rollback for isolation. Each test runs inside a SAVEPOINT
so session.commit() works normally, but the outer transaction is rolled back
after the test — no data leaks between tests.

Requires: `make test-start` to have the test PostgreSQL container running.
"""

import os
from typing import Generator, List

import pytest
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
    from user_service import init_demo_users

    init_demo_users(test_db)
    return test_db
