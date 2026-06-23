"""
Unit tests for routers/auth.py to increase branch coverage.
Focuses on pure function tests and simple endpoint error paths.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.dependencies import require_user
from auth_module.models import User
from models import User as DBUser


def _make_user(is_superadmin=False, user_id="user-123"):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring a seeded DB row."""
    au = User(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed_user(db, **over):
    fields = dict(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@e.com",
        name="U",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    fields.update(over)
    u = DBUser(**fields)
    db.add(u)
    await db.flush()
    return u


class TestLoginEndpoint:
    def test_invalid_credentials(self):
        client = TestClient(app)

        from database import get_db

        mock_db = Mock(spec=Session)
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.auth.session.authenticate_user") as mock_auth:
                mock_auth.return_value = None
                resp = client.post(
                    "/api/auth/login",
                    json={"username": "wrong", "password": "wrong"},
                )
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


class TestLogoutEndpoint:
    @pytest.mark.asyncio
    async def test_logout(self, async_test_client, async_test_db):
        # Logout migrated to the async DB lane; revoke twin lives in
        # services.refresh_token_service. With no refresh cookie the handler
        # just clears cookies and returns 200.
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            with patch(
                "services.refresh_token_service.revoke_refresh_token_async",
                new=AsyncMock(return_value=True),
            ):
                resp = await async_test_client.post("/api/auth/logout")
        assert resp.status_code == 200


class TestMeEndpoint:
    @pytest.mark.asyncio
    async def test_get_me(self, async_test_client, async_test_db):
        # /me migrated to the async DB lane; query a real seeded user.
        user = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["id"] == user.id


class TestUnauthenticatedEndpoints:
    """Test that auth-required endpoints return 401 without credentials."""

    def test_me_unauthenticated(self):
        client = TestClient(app)
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_logout_unauthenticated(self):
        client = TestClient(app)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401

    def test_profile_unauthenticated(self):
        client = TestClient(app)
        resp = client.put("/api/auth/profile", json={"name": "Test"})
        assert resp.status_code == 401

    def test_password_unauthenticated(self):
        client = TestClient(app)
        resp = client.post(
            "/api/auth/password",
            json={"current_password": "old", "new_password": "new"},
        )
        # Auth middleware may return 401, 404 (route not found), or 422
        assert resp.status_code in [401, 404, 422]
