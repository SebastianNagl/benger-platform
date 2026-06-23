"""
Extended tests for users router - covering uncovered branches.

Targets: routers/users.py lines 32, 44-56, 68-72, 83-100, 111-132
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User


@contextmanager
def _as_user(db_user):
    """Override require_user with a superadmin identity from a seeded DB row.

    GET /api/users + PATCH .../role + .../status were migrated to the async
    DB lane; overriding `require_user` (which `require_superadmin` depends on)
    satisfies the superadmin gate via the seeded row's is_superadmin.
    """
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


async def _seed_user(db, *, is_superadmin=False, is_active=True):
    """Seed a real models.User row into the async test session."""
    u = User(
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


class TestUsersRouterExtended:
    """Test user management endpoints covering all branches."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_superadmin(self):
        return User(
            id="admin-users",
            username="usersadmin",
            email="usersadmin@test.com",
            name="Users Admin",
            hashed_password="hashed",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    def _override_superadmin(self, mock_superadmin):
        from auth_module.dependencies import require_superadmin

        def override():
            return mock_superadmin
        app.dependency_overrides[require_superadmin] = override

    def _override_db(self, mock_db):
        from database import get_db

        def override():
            return mock_db
        app.dependency_overrides[get_db] = override

    @pytest.mark.asyncio
    async def test_get_all_users(self, async_test_client, async_test_db):
        """Test listing all users.

        Migrated to the async DB lane (queries DBUser directly). The original
        asserted exactly one row against a mocked DB; against the real test DB
        we scope to a unique `?search=` marker and assert the single seeded
        match comes back — preserving the "len == 1" intent.
        """
        admin = await _seed_user(async_test_db, is_superadmin=True)
        marker = f"ext-{uuid.uuid4().hex[:8]}"
        seeded = await _seed_user(async_test_db, is_superadmin=False)
        seeded.name = marker
        await async_test_db.flush()

        with _as_user(admin):
            response = await async_test_client.get(f"/api/users?search={marker}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == seeded.id

    @pytest.mark.asyncio
    async def test_update_user_role_success(self, async_test_client, async_test_db):
        """Test updating user role (migrated to async lane)."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        target = await _seed_user(async_test_db, is_superadmin=False)

        with _as_user(admin):
            response = await async_test_client.patch(
                f"/api/users/{target.id}/role", json={"is_superadmin": True}
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_superadmin"] is True

    def test_update_user_role_invalid_value(self, client, mock_superadmin):
        """Test updating user role with non-boolean value."""
        self._override_superadmin(mock_superadmin)
        self._override_db(Mock(spec=Session))
        try:
            response = client.patch(
                "/api/users/target-user/role",
                json={"is_superadmin": "not_boolean"},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_user_role_not_found(self, async_test_client, async_test_db):
        """Unseeded id → async twin returns None → 404 (no patching)."""
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            response = await async_test_client.patch(
                "/api/users/nonexistent/role", json={"is_superadmin": False}
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_user_status_success(self, async_test_client, async_test_db):
        """Test updating user active status (migrated to async lane)."""
        admin = await _seed_user(async_test_db, is_superadmin=True)
        target = await _seed_user(async_test_db, is_active=True)

        with _as_user(admin):
            response = await async_test_client.patch(
                f"/api/users/{target.id}/status", json={"is_active": False}
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_user_status_not_found(self, async_test_client, async_test_db):
        """Unseeded id → async twin returns None → 404 (no patching)."""
        admin = await _seed_user(async_test_db, is_superadmin=True)

        with _as_user(admin):
            response = await async_test_client.patch(
                "/api/users/nonexistent/status", json={"is_active": False}
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_verify_user_email_success(self, client, mock_superadmin):
        """Test admin verifying user email."""
        self._override_superadmin(mock_superadmin)

        target_user = User(
            id="target-user",
            username="target",
            email="target@test.com",
            name="Target",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = target_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with patch("routers.users.email_verification_service") as mock_evs:
            mock_evs.mark_email_verified.return_value = True
            self._override_db(mock_db)
            try:
                response = client.patch("/api/users/target-user/verify-email")
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_verify_user_email_not_found(self, client, mock_superadmin):
        """Test admin verifying email for non-existent user."""
        self._override_superadmin(mock_superadmin)

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = None
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        self._override_db(mock_db)
        try:
            response = client.patch("/api/users/nonexistent/verify-email")
            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    def test_verify_user_email_service_failure(self, client, mock_superadmin):
        """Test admin verifying email when service fails."""
        self._override_superadmin(mock_superadmin)

        mock_db = Mock(spec=Session)
        target_user = Mock()
        target_user.id = "target-user"

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = target_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with patch("routers.users.email_verification_service") as mock_evs:
            mock_evs.mark_email_verified.return_value = False
            self._override_db(mock_db)
            try:
                response = client.patch("/api/users/target-user/verify-email")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    def test_delete_user_success(self, client, mock_superadmin):
        """Test deleting a user."""
        self._override_superadmin(mock_superadmin)

        with patch("auth_module.user_service.delete_user") as mock_delete:
            mock_delete.return_value = True
            self._override_db(Mock(spec=Session))
            try:
                response = client.delete("/api/users/other-user-id")
                assert response.status_code == status.HTTP_204_NO_CONTENT
            finally:
                app.dependency_overrides.clear()

    def test_delete_user_self(self, client, mock_superadmin):
        """Test deleting own account is prevented."""
        self._override_superadmin(mock_superadmin)
        self._override_db(Mock(spec=Session))
        try:
            response = client.delete(f"/api/users/{mock_superadmin.id}")
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "own account" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_delete_user_not_found(self, client, mock_superadmin):
        """Test deleting non-existent user."""
        self._override_superadmin(mock_superadmin)

        with patch("auth_module.user_service.delete_user") as mock_delete:
            mock_delete.return_value = False
            self._override_db(Mock(spec=Session))
            try:
                response = client.delete("/api/users/nonexistent")
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_delete_user_unexpected_error(self, client, mock_superadmin):
        """Test deleting user with unexpected error."""
        self._override_superadmin(mock_superadmin)

        with patch("auth_module.user_service.delete_user") as mock_delete:
            mock_delete.side_effect = RuntimeError("DB error")
            self._override_db(Mock(spec=Session))
            try:
                response = client.delete("/api/users/some-user")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()
