"""
Comprehensive tests for the users router endpoints.
Tests the current router architecture mounted at /api/users/*.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


class TestUsersRouter:
    """Test users router endpoints mounted at /api/users/"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_regular_user(self):
        """Create mock regular user for testing"""
        return User(
            id="regular-user-123",
            username="regular",
            email="regular@example.com",
            name="Regular User",
            hashed_password="hashed_password_regular",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_superadmin_user(self):
        """Create mock superadmin user for testing"""
        return User(
            id="admin-user-123",
            username="admin",
            email="admin@example.com",
            name="Admin User",
            hashed_password="hashed_password_admin",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_users_list(self, mock_regular_user, mock_superadmin_user):
        """Create mock list of users"""
        return [mock_superadmin_user, mock_regular_user]

    def test_get_all_users_success_as_superadmin(
        self, client, mock_superadmin_user, mock_users_list
    ):
        """Test getting all users as superadmin at /api/users"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.users.get_all_users") as mock_get_users:
            mock_get_users.return_value = mock_users_list

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/api/users")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert isinstance(data, list)
                assert len(data) == 2
            finally:
                # Clean up overrides
                app.dependency_overrides.clear()

    def test_get_all_users_forbidden_as_regular_user(self, client, mock_regular_user):
        """Test that getting all users is forbidden for regular users"""
        from fastapi import HTTPException

        from database import get_db
        from main import app
        from routers.users import require_superadmin

        def override_require_superadmin():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )

        def override_get_db():
            return Mock(spec=Session)

        # Override dependencies using the proven pattern
        app.dependency_overrides[require_superadmin] = override_require_superadmin
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/users")
            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()

    def test_update_user_role_success_as_superadmin(
        self, client, mock_superadmin_user, mock_regular_user
    ):
        """Test updating user role as superadmin at /api/users/{user_id}/role"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        mock_db = Mock(spec=Session)

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return mock_db

        with patch("routers.users.update_user_superadmin_status") as mock_update_role:
            # Mock successful role update
            updated_user = mock_regular_user
            updated_user.is_superadmin = True
            mock_update_role.return_value = updated_user

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                role_data = {"is_superadmin": True}
                response = client.patch("/api/users/regular-user-123/role", json=role_data)

                assert response.status_code == status.HTTP_200_OK
                mock_update_role.assert_called_once_with(mock_db, "regular-user-123", True)
            finally:
                app.dependency_overrides.clear()

    def test_update_user_role_invalid_data(self, client, mock_superadmin_user):
        """Test updating user role with invalid data"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return Mock(spec=Session)

        # Override dependencies
        app.dependency_overrides[require_superadmin] = override_require_superadmin
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Invalid data - is_superadmin should be boolean
            role_data = {"is_superadmin": "invalid"}
            response = client.patch("/api/users/regular-user-123/role", json=role_data)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()

    def test_update_user_role_user_not_found(self, client, mock_superadmin_user):
        """Test updating role for non-existent user"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.users.update_user_superadmin_status") as mock_update_role:
            mock_update_role.return_value = None  # User not found

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                role_data = {"is_superadmin": True}
                response = client.patch("/api/users/nonexistent-user/role", json=role_data)

                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_update_user_status_success_as_superadmin(
        self, client, mock_superadmin_user, mock_regular_user
    ):
        """Test updating user status as superadmin at /api/users/{user_id}/status"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        mock_db = Mock(spec=Session)

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return mock_db

        with patch("routers.users.update_user_status") as mock_update_status:
            # Mock successful status update
            updated_user = mock_regular_user
            updated_user.is_active = False
            mock_update_status.return_value = updated_user

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                status_data = {"is_active": False}
                response = client.patch("/api/users/regular-user-123/status", json=status_data)

                assert response.status_code == status.HTTP_200_OK
                mock_update_status.assert_called_once_with(mock_db, "regular-user-123", False)
            finally:
                app.dependency_overrides.clear()

    def test_update_user_status_user_not_found(self, client, mock_superadmin_user):
        """Test updating status for non-existent user"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.users.update_user_status") as mock_update_status:
            mock_update_status.return_value = None  # User not found

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                status_data = {"is_active": False}
                response = client.patch("/api/users/nonexistent-user/status", json=status_data)

                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_verify_user_email_success_as_superadmin(
        self, client, mock_superadmin_user, mock_regular_user
    ):
        """Test manually verifying user email as superadmin at /api/users/{user_id}/verify-email"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        mock_db = Mock(spec=Session)

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return mock_db

        with patch("routers.users.email_verification_service.mark_email_verified") as mock_verify:
            # Mock user exists in database
            mock_db_user = Mock()
            mock_db_user.id = "regular-user-123"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_db_user

            # Mock successful verification
            mock_verify.return_value = True

            # Mock updated user after verification
            verified_user = mock_regular_user
            verified_user.email_verified = True
            # Second call returns updated user
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                mock_db_user,
                verified_user,
            ]

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.patch("/api/users/regular-user-123/verify-email")

                assert response.status_code == status.HTTP_200_OK
                mock_verify.assert_called_once_with(
                    db=mock_db,
                    user_id="regular-user-123",
                    verified_by_id=mock_superadmin_user.id,
                    method="admin",
                )
            finally:
                app.dependency_overrides.clear()

    def test_verify_user_email_user_not_found(self, client, mock_superadmin_user):
        """Test verifying email for non-existent user"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        mock_db = Mock(spec=Session)

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return mock_db

        # Mock user not found in database
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Override dependencies
        app.dependency_overrides[require_superadmin] = override_require_superadmin
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.patch("/api/users/nonexistent-user/verify-email")

            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    def test_verify_user_email_service_failure(self, client, mock_superadmin_user):
        """Test email verification when service fails"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        mock_db = Mock(spec=Session)

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return mock_db

        with patch("routers.users.email_verification_service.mark_email_verified") as mock_verify:
            # Mock user exists
            mock_db_user = Mock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_db_user

            # Mock verification service failure
            mock_verify.return_value = False

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.patch("/api/users/regular-user-123/verify-email")

                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    def test_delete_user_success_as_superadmin(self, client, mock_superadmin_user):
        """Test deleting user as superadmin at /api/users/{user_id}"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        mock_db = Mock(spec=Session)

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return mock_db

        with patch("user_service.delete_user") as mock_delete_user:
            mock_delete_user.return_value = True  # Successful deletion

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.delete("/api/users/regular-user-123")

                assert response.status_code == status.HTTP_204_NO_CONTENT
                mock_delete_user.assert_called_once_with(mock_db, "regular-user-123")
            finally:
                app.dependency_overrides.clear()

    def test_delete_user_self_deletion_forbidden(self, client, mock_superadmin_user):
        """Test that admin cannot delete their own account"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return Mock(spec=Session)

        # Override dependencies
        app.dependency_overrides[require_superadmin] = override_require_superadmin
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Try to delete own account
            response = client.delete(f"/api/users/{mock_superadmin_user.id}")

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Cannot delete your own account" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_delete_user_not_found(self, client, mock_superadmin_user):
        """Test deleting non-existent user"""
        from database import get_db
        from main import app
        from routers.users import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("user_service.delete_user") as mock_delete_user:
            mock_delete_user.return_value = False  # User not found

            # Override dependencies
            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.delete("/api/users/nonexistent-user")

                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_users_endpoints_require_superadmin(self, client, mock_regular_user):
        """Test that all users endpoints require superadmin role"""
        from fastapi import HTTPException

        from database import get_db
        from main import app
        from routers.users import require_superadmin

        def override_require_superadmin():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )

        def override_get_db():
            return Mock(spec=Session)

        endpoints = [
            ("GET", "/api/users"),
            ("PATCH", "/api/users/test-user/role", {"is_superadmin": False}),
            ("PATCH", "/api/users/test-user/status", {"is_active": True}),
            ("PATCH", "/api/users/test-user/verify-email"),
            ("DELETE", "/api/users/test-user"),
        ]

        # Override dependencies
        app.dependency_overrides[require_superadmin] = override_require_superadmin
        app.dependency_overrides[get_db] = override_get_db

        try:
            for method, endpoint, *json_data in endpoints:
                kwargs = {}
                if json_data:
                    kwargs["json"] = json_data[0]

                response = client.request(method, endpoint, **kwargs)
                assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()


@pytest.mark.integration
class TestUsersRouterIntegration:
    """Integration tests for users router"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_users_endpoints_request_validation(self, client):
        """Test that users endpoints reject invalid requests"""
        # Test role update with invalid JSON - auth middleware may reject before validation
        response = client.patch("/api/users/test-user/role", data="invalid")
        assert response.status_code in [401, 422]

        # Test status update with invalid JSON
        response = client.patch("/api/users/test-user/status", data="invalid")
        assert response.status_code in [401, 422]

    # test_users_endpoints_handle_missing_dependencies removed:
    # Accepted every status code including 500/503, testing nothing meaningful.
