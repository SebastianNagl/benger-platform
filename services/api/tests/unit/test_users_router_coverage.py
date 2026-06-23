"""
Unit tests for routers/users.py to increase branch coverage.
Covers all user management endpoints.
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
    the async DB lane; overriding `require_user` (which `require_superadmin`
    depends on) satisfies the superadmin gate via the row's is_superadmin.
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


def _make_admin(user_id="admin-123"):
    return User(
        id=user_id,
        username="admin",
        email="admin@example.com",
        name="Admin User",
        hashed_password="hashed",
        is_superadmin=True,
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
        """GET /api/users migrated to async lane; assert it returns 200 and
        includes a seeded row (scoped via `?search=`)."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        marker = f"cov-{uuid.uuid4().hex[:8]}"
        seeded = await _seed_db_user(async_test_db, is_superadmin=False)
        seeded.name = marker
        await async_test_db.flush()

        with _as_user(admin):
            resp = await async_test_client.get(f"/api/users?search={marker}")

        assert resp.status_code == 200
        assert [row["id"] for row in resp.json()] == [seeded.id]


class TestUpdateUserRole:
    def test_non_boolean_is_superadmin(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.patch(
                "/api/users/user-1/role",
                json={"is_superadmin": "not_a_bool"},
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_user_not_found(self, async_test_client, async_test_db):
        """Unseeded id → async twin returns None → 404."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/users/user-1/role", json={"is_superadmin": True}
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_role_success(self, async_test_client, async_test_db):
        """PATCH .../role migrated to async lane."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        target = await _seed_db_user(async_test_db, is_superadmin=False)
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/users/{target.id}/role", json={"is_superadmin": True}
            )
        assert resp.status_code == 200
        assert resp.json()["is_superadmin"] is True


class TestUpdateUserStatus:
    @pytest.mark.asyncio
    async def test_user_not_found(self, async_test_client, async_test_db):
        """Unseeded id → async twin returns None → 404."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/users/user-1/status", json={"is_active": False}
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_status_success(self, async_test_client, async_test_db):
        """PATCH .../status migrated to async lane."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        target = await _seed_db_user(async_test_db, is_active=True)
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/users/{target.id}/status", json={"is_active": False}
            )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


class TestVerifyUserEmail:
    def test_user_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.patch("/api/users/nonexistent/verify-email")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_verification_failure(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-1"
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.email_verification_service") as mock_evs:
                mock_evs.mark_email_verified.return_value = False
                resp = client.patch("/api/users/user-1/verify-email")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_verification_success(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-1"
        db_user.username = "testuser"
        db_user.email = "test@example.com"
        db_user.name = "Test"
        db_user.hashed_password = "hashed"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.email_verified = True
        db_user.created_at = datetime.now(timezone.utc)
        db_user.organizations = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.email_verification_service") as mock_evs:
                mock_evs.mark_email_verified.return_value = True
                resp = client.patch("/api/users/user-1/verify-email")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestDeleteUser:
    def test_delete_self(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/users/admin-123")
            assert resp.status_code == 400
            assert "Cannot delete your own" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_user_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("auth_module.user_service.delete_user", return_value=False):
                resp = client.delete("/api/users/user-1")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_delete_success(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("auth_module.user_service.delete_user", return_value=True):
                resp = client.delete("/api/users/user-1")
                assert resp.status_code == 204
        finally:
            app.dependency_overrides.clear()

    def test_delete_unexpected_error(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("auth_module.user_service.delete_user", side_effect=Exception("DB error")):
                resp = client.delete("/api/users/user-1")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()
