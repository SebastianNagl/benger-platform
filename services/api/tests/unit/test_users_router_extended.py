"""
Extended tests for users router - covering uncovered branches.

Targets: routers/users.py lines 32, 44-56, 68-72, 83-100, 111-132
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


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

    def test_get_all_users(self, client, mock_superadmin):
        """Test listing all users."""
        self._override_superadmin(mock_superadmin)

        user_list = [mock_superadmin]
        with patch("routers.users.get_all_users") as mock_get:
            mock_get.return_value = user_list
            self._override_db(Mock(spec=Session))
            try:
                response = client.get("/api/users")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert len(data) == 1
            finally:
                app.dependency_overrides.clear()

    def test_update_user_role_success(self, client, mock_superadmin):
        """Test updating user role."""
        self._override_superadmin(mock_superadmin)

        updated_user = User(
            id="target-user",
            username="target",
            email="target@test.com",
            name="Target",
            hashed_password="hashed",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

        with patch("routers.users.update_user_superadmin_status") as mock_update:
            mock_update.return_value = updated_user
            self._override_db(Mock(spec=Session))
            try:
                response = client.patch(
                    "/api/users/target-user/role",
                    json={"is_superadmin": True},
                )
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

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

    def test_update_user_role_not_found(self, client, mock_superadmin):
        """Test updating role for non-existent user."""
        self._override_superadmin(mock_superadmin)

        with patch("routers.users.update_user_superadmin_status") as mock_update:
            mock_update.return_value = None
            self._override_db(Mock(spec=Session))
            try:
                response = client.patch(
                    "/api/users/nonexistent/role",
                    json={"is_superadmin": False},
                )
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_update_user_status_success(self, client, mock_superadmin):
        """Test updating user active status."""
        self._override_superadmin(mock_superadmin)

        updated_user = User(
            id="target-user",
            username="target",
            email="target@test.com",
            name="Target",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=False,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

        with patch("routers.users.update_user_status") as mock_update:
            mock_update.return_value = updated_user
            self._override_db(Mock(spec=Session))
            try:
                response = client.patch(
                    "/api/users/target-user/status",
                    json={"is_active": False},
                )
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_update_user_status_not_found(self, client, mock_superadmin):
        """Test updating status for non-existent user."""
        self._override_superadmin(mock_superadmin)

        with patch("routers.users.update_user_status") as mock_update:
            mock_update.return_value = None
            self._override_db(Mock(spec=Session))
            try:
                response = client.patch(
                    "/api/users/nonexistent/status",
                    json={"is_active": False},
                )
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

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

        with patch("user_service.delete_user") as mock_delete:
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

        with patch("user_service.delete_user") as mock_delete:
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

        with patch("user_service.delete_user") as mock_delete:
            mock_delete.side_effect = RuntimeError("DB error")
            self._override_db(Mock(spec=Session))
            try:
                response = client.delete("/api/users/some-user")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()
