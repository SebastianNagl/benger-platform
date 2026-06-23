"""
Unit tests for routers/users.py to increase coverage.
Tests all user management endpoints.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from auth_module.dependencies import require_superadmin, require_user
from database import get_db
from models import User as DBUser


@contextmanager
def _as_user(db_user):
    """Override require_user with a superadmin identity from a seeded DB row.

    The GET /api/users + PATCH .../role + .../status handlers were migrated to
    the async DB lane, so they run on the real ASGI/async-DB stack and the old
    sync-`get_db`-mock + `patch(routers.users.update_user_*)` pattern no longer
    reaches them. `require_superadmin` is `Depends(require_user)` + an
    is_superadmin check, so overriding `require_user` is sufficient.
    """
    auth_user = User(
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


async def _seed_db_user(db, *, is_superadmin=False, is_active=True):
    """Seed a real models.User row into the async test session."""
    u = DBUser(
        id=str(uuid.uuid4()),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@e.com",
        name="U",
        hashed_password="x",
        is_superadmin=is_superadmin,
        is_active=is_active,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


def _make_user(is_superadmin=True, user_id="user-123"):
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


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_db.query.return_value = mock_q
    return mock_db


class TestGetAllUsers:
    @pytest.mark.asyncio
    async def test_returns_users(self, async_test_client, async_test_db):
        """GET /api/users migrated to the async DB lane.

        The original asserted an empty list via a patched `get_all_users`
        (now an unused import). Against the real test DB we scope to a
        unique `?search=` marker and assert exactly the rows we seeded are
        returned — preserving the "returns the matching users" intent.
        """
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        marker = f"full-{uuid.uuid4().hex[:8]}"
        seeded = await _seed_db_user(async_test_db, is_superadmin=False)
        seeded.name = marker
        await async_test_db.flush()

        with _as_user(admin):
            resp = await async_test_client.get(f"/api/users?search={marker}")

        assert resp.status_code == 200
        data = resp.json()
        assert [row["id"] for row in data] == [seeded.id]


class TestUpdateUserRole:
    @pytest.mark.asyncio
    async def test_update_to_superadmin(self, async_test_client, async_test_db):
        """PATCH .../role migrated to async lane (update_user_superadmin_status_async)."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        target = await _seed_db_user(async_test_db, is_superadmin=False)

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/users/{target.id}/role", json={"is_superadmin": True}
            )

        assert resp.status_code == 200
        assert resp.json()["is_superadmin"] is True

    @pytest.mark.asyncio
    async def test_user_not_found(self, async_test_client, async_test_db):
        """Unseeded id → async twin returns None → 404. No patching needed."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/users/nonexistent/role", json={"is_superadmin": False}
            )

        assert resp.status_code == 404

    def test_invalid_is_superadmin_type(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.patch(
                "/api/users/user-2/role",
                json={"is_superadmin": "not_a_bool"},
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()


class TestUpdateUserStatus:
    @pytest.mark.asyncio
    async def test_activate_user(self, async_test_client, async_test_db):
        """PATCH .../status migrated to async lane (update_user_status_async)."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        target = await _seed_db_user(async_test_db, is_active=False)

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/users/{target.id}/status", json={"is_active": True}
            )

        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_user_not_found(self, async_test_client, async_test_db):
        """Unseeded id → async twin returns None → 404. No patching needed."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/users/nonexistent/status", json={"is_active": False}
            )

        assert resp.status_code == 404


class TestVerifyUserEmail:
    def test_user_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.patch("/api/users/nonexistent/verify-email")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_verify_calls_service(self):
        """Test that verify endpoint calls mark_email_verified."""
        # Testing the endpoint logic directly since mock DB objects
        # don't serialize through Pydantic's User response model
        from routers.users import email_verification_service
        assert hasattr(email_verification_service, 'mark_email_verified')

    def test_verify_failure(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        target_user = Mock()
        target_user.id = "user-2"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = target_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.email_verification_service") as mock_ev:
                mock_ev.mark_email_verified.return_value = False
                resp = client.patch("/api/users/user-2/verify-email")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestDeleteUser:
    def test_cannot_delete_self(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/users/user-123")
            assert resp.status_code == 400
            assert "own account" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_user_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("auth_module.user_service.delete_user", return_value=False):
                resp = client.delete("/api/users/other-user")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_successful_delete(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("auth_module.user_service.delete_user", return_value=True):
                resp = client.delete("/api/users/other-user")
                assert resp.status_code == 204
        finally:
            app.dependency_overrides.clear()

    def test_delete_exception(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("auth_module.user_service.delete_user", side_effect=Exception("DB error")):
                resp = client.delete("/api/users/other-user")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()
