"""
Unit tests for routers/generation.py — covers endpoint access control and logic.

The generation router was migrated to the async DB lane
(``Depends(get_async_db)``), so these tests drive the migrated endpoints
through ``async_test_client`` + ``async_test_db`` (the sync ``db.query``-Mock
form can no longer reach a handler that does ``await db.execute(select(...))``).

Targets the 404-unknown-id guard branch of each of the six generation
mutation/status endpoints.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, is_superadmin=True) -> User:
    u = User(
        id=_uid(),
        username=f"gen-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Gen User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.commit()
    return u


class TestGetGenerationStatus:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.get(f"/api/generation/status/missing-{_uid()}")
        assert resp.status_code == 404


class TestStopGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.post(f"/api/generation/missing-{_uid()}/stop")
        assert resp.status_code == 404


class TestPauseGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.post(f"/api/generation/missing-{_uid()}/pause")
        assert resp.status_code == 404


class TestResumeGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.post(f"/api/generation/missing-{_uid()}/resume")
        assert resp.status_code == 404


class TestRetryGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.post(f"/api/generation/missing-{_uid()}/retry")
        assert resp.status_code == 404


class TestDeleteGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.delete(f"/api/generation/missing-{_uid()}")
        assert resp.status_code == 404
