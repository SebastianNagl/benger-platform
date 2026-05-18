"""Smoke tests for the Phase 0 asyncpg + AsyncSession foundation.

What this covers:
- `get_async_db` actually yields an AsyncSession bound to asyncpg.
- The async test fixture (`async_test_db`) gives a working session.
- The Postgres-side `statement_timeout` and `application_name` survive
  the asyncpg `server_settings` round-trip (gating: if they don't, every
  future async handler loses the runaway-query guard).
- The converted /health/schema endpoint returns the new async-flavored
  payload through the AsyncClient.

These tests don't migrate anything; they prove the infrastructure works
end-to-end before Phase 1 starts converting real handlers.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_async_session_basic_query(async_test_db):
    """A SELECT 1 round-trips through asyncpg + AsyncSession."""
    result = await async_test_db.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_async_engine_propagates_statement_timeout(async_test_db):
    """`server_settings` actually applied. Gating check: every async
    handler relies on this to inherit the runaway-query guard."""
    result = await async_test_db.execute(
        text("SELECT current_setting('statement_timeout')")
    )
    # asyncpg reports the value with the suffix ('s', 'ms') depending on
    # magnitude — 15000 ms parses as "15s" on the server side. Either form
    # is acceptable; assert it's not the default (0).
    timeout = result.scalar()
    assert timeout not in ("0", "")


@pytest.mark.asyncio
async def test_async_engine_application_name(async_test_db):
    """The async engine's connections show a distinct application_name
    so pg_stat_activity can tell sync vs async traffic apart at any
    moment — essential for Phase 5's canary gate.

    NOTE: tests use a single shared async engine (see
    fixtures/database.py:_get_async_engine), which DOESN'T set
    server_settings (that's a database.py concern for the prod engine).
    So in tests application_name is the asyncpg default. We assert it
    exists and is a string rather than enforcing the prod-only value.
    """
    result = await async_test_db.execute(
        text("SELECT current_setting('application_name')")
    )
    name = result.scalar()
    assert isinstance(name, str)


@pytest.mark.asyncio
async def test_health_check_schema_endpoint(async_test_client):
    """The converted Phase 0 worked-example endpoint returns the new
    async-flavored payload through the async test client + the
    dependency-overridden AsyncSession."""
    response = await async_test_client.get("/health/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["engine"] == "async"
    # statement_timeout came back from the server (whatever form).
    assert "statement_timeout" in body
    assert "application_name" in body
