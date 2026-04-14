"""
Pytest configuration and shared fixtures for BenGER API tests.

Fixtures are organized in tests/fixtures/:
  - database.py:   test_db, client, async_client, async_session, db, clean_database, populated_database
  - users.py:      test_users, test_user, auth_headers
  - evaluation.py: test_evaluation_types, test_org, test_org_with_members, sample_evaluation_data,
                   security_test_data, performance_config
  - mocks.py:      mock_celery, mock_redis (autouse), mock_redis_async
"""

import asyncio
import os
import sys
from typing import Generator

import pytest

# Add parent directory to Python path to import from services/api
api_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if api_path not in sys.path:
    sys.path.insert(0, api_path)
# Also ensure /app is in path for Docker environment
if '/app' not in sys.path:
    sys.path.insert(0, '/app')
# Add shared directory to Python path for shared services
shared_path = os.path.join(api_path, '..', 'shared')
if os.path.exists(shared_path) and shared_path not in sys.path:
    sys.path.insert(0, shared_path)

# Set test environment variables before importing modules
# Use test PostgreSQL: Docker sets DATABASE_URI, local dev uses localhost:5433
_pg_test_url = os.environ.get("DATABASE_URI") or os.environ.get("DATABASE_URL")
if not _pg_test_url or "sqlite" in _pg_test_url:
    _pg_test_url = "postgresql://postgres:postgres_test@localhost:5433/test_benger"
os.environ["DATABASE_URL"] = _pg_test_url
os.environ["ASYNC_DATABASE_URL"] = _pg_test_url.replace("postgresql://", "postgresql+asyncpg://", 1)
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

# Register fixture modules — pytest discovers all fixtures from these modules
pytest_plugins = [
    "tests.fixtures.database",
    "tests.fixtures.users",
    "tests.fixtures.evaluation",
    "tests.fixtures.mocks",
]


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
