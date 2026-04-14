"""
Comprehensive tests for the auth router endpoints.
Tests the current router architecture mounted at /api/auth/*.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User


class TestAuthRouter:
    """Test authentication router endpoints mounted at /api/auth/"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        """Create mock user for testing"""
        return User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            timezone="UTC",
            age=28,
            job="Software Developer",
            years_of_experience=5,
            legal_expertise_level="law_student",
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_admin_user(self):
        """Create mock admin user for testing"""
        return User(
            id="admin-user-123",
            username="admin",
            email="admin@example.com",
            name="Admin User",
            hashed_password="hashed_password_admin",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            timezone="UTC",
            age=35,
            job="System Administrator",
            years_of_experience=10,
            legal_expertise_level="practicing_lawyer",
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

    def test_login_success(self, client):
        """Test successful login at /api/auth/login"""
        with patch("routers.auth.authenticate_user") as mock_auth, patch(
            "routers.auth.create_tokens_with_refresh"
        ) as mock_create_tokens, patch("database.get_db") as mock_get_db:
            # Mock authenticated user
            mock_user = User(
                id="test-user",
                username="test",
                email="test@example.com",
                name="Test",
                hashed_password="hashed_password_test",
                is_superadmin=False,
                is_active=True,
                email_verified=True,
                created_at=datetime.now(timezone.utc),
            )
            mock_auth.return_value = mock_user

            # Mock token creation
            mock_token_response = Mock()
            mock_token_response.access_token = "test-access-token"
            mock_token_response.refresh_token = "test-refresh-token"
            mock_token_response.token_type = "bearer"
            mock_token_response.expires_in = 1800  # 30 minutes in seconds
            mock_token_response.user = mock_user
            mock_create_tokens.return_value = mock_token_response

            # Mock database session
            mock_db = Mock(spec=Session)
            mock_get_db.return_value = mock_db

            login_data = {"username": "test@example.com", "password": "password123"}

            response = client.post("/api/auth/login", json=login_data)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        with patch("routers.auth.authenticate_user") as mock_auth, patch(
            "database.get_db"
        ) as mock_get_db:
            mock_auth.return_value = None  # Authentication failed
            mock_get_db.return_value = Mock(spec=Session)

            login_data = {"username": "test@example.com", "password": "wrongpassword"}

            response = client.post("/api/auth/login", json=login_data)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_unverified_email(self, client):
        """Test login with unverified email"""
        with patch("routers.auth.authenticate_user") as mock_auth, patch(
            "database.get_db"
        ) as mock_get_db:
            # Mock unverified user
            unverified_user = User(
                id="test-user",
                username="test",
                email="test@example.com",
                name="Test",
                hashed_password="hashed_password_test",
                is_superadmin=False,
                is_active=True,
                email_verified=False,
                created_at=datetime.now(timezone.utc),
            )
            mock_auth.return_value = unverified_user
            mock_get_db.return_value = Mock(spec=Session)

            login_data = {"username": "test@example.com", "password": "password123"}

            response = client.post("/api/auth/login", json=login_data)
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "verification" in response.json()["detail"].lower()

    def test_logout_success(self, client, mock_user):
        """Test successful logout at /auth/logout"""
        from database import get_db
        from main import app
        from routers.auth import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.revoke_refresh_token") as mock_revoke:
            # Override dependencies
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                # Set cookies to simulate logged-in user
                client.cookies["refresh_token"] = "test-refresh-token"

                response = client.post("/api/auth/logout")

                assert response.status_code == status.HTTP_200_OK
                assert "successfully" in response.json()["message"].lower()
            finally:
                # Clean up overrides
                app.dependency_overrides.clear()

    def test_refresh_token_success(self, client, mock_user):
        """Test successful token refresh at /auth/refresh"""
        from database import get_db
        from main import app

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.auth.refresh_access_token") as mock_refresh:
            # Mock successful token refresh
            mock_token_response = Mock()
            mock_token_response.access_token = "new-access-token"
            mock_token_response.refresh_token = "new-refresh-token"
            mock_token_response.token_type = "bearer"
            mock_token_response.expires_in = 1800  # 30 minutes in seconds
            mock_token_response.user = mock_user  # Use the actual mock user
            mock_refresh.return_value = mock_token_response

            # Override dependencies
            app.dependency_overrides[get_db] = override_get_db

            try:
                # Set refresh token cookie
                client.cookies["refresh_token"] = "valid-refresh-token"

                response = client.post("/api/auth/refresh")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "access_token" in data
                assert data["access_token"] == "new-access-token"
            finally:
                app.dependency_overrides.clear()

    def test_refresh_token_missing(self, client):
        """Test token refresh without refresh token"""
        with patch("database.get_db") as mock_get_db:
            mock_get_db.return_value = Mock(spec=Session)

            # Don't set refresh token cookie
            response = client.post("/api/auth/refresh")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_verify_token_success(self, client, mock_user):
        """Test token verification at /auth/verify"""
        from main import app
        from routers.auth import require_user

        def override_require_user():
            return mock_user

        # Override dependencies
        app.dependency_overrides[require_user] = override_require_user

        try:
            response = client.get("/api/auth/verify")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["valid"] is True
            assert "user" in data
        finally:
            app.dependency_overrides.clear()

    def test_get_me_success(self, client, mock_user):
        """Test get current user at /auth/me"""
        from database import get_db
        from main import app
        from routers.auth import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        # Override dependencies
        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        # Patch get_user_primary_role to avoid database access
        with patch("routers.auth.get_user_primary_role") as mock_get_role:
            mock_get_role.return_value = "user"

            try:
                response = client.get("/api/auth/me")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["id"] == mock_user.id
                assert data["username"] == mock_user.username
                assert data["email"] == mock_user.email
            finally:
                app.dependency_overrides.clear()

    def test_get_profile_success(self, client, mock_user):
        """Test get user profile at /auth/profile"""
        from database import get_db
        from main import app
        from routers.auth import require_user

        def override_require_user():
            return mock_user

        # Create a mock db that returns mock_user when queried
        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        # Override dependencies
        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        # Patch get_user_primary_role to avoid database access
        with patch("routers.auth.get_user_primary_role") as mock_get_role:
            mock_get_role.return_value = "user"

            try:
                response = client.get("/api/auth/profile")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["id"] == mock_user.id
                assert data["username"] == mock_user.username
                assert data["email"] == mock_user.email
            finally:
                app.dependency_overrides.clear()

    def test_update_profile_success(self, client, mock_user):
        """Test update user profile at /auth/profile"""
        from database import get_db
        from main import app
        from routers.auth import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        # Mock successful update - create a complete updated user
        updated_user = User(
            id=mock_user.id,
            username=mock_user.username,
            email="test@example.com",
            name="Updated Name",
            hashed_password="hashed_password_test",
            is_superadmin=mock_user.is_superadmin,
            is_active=mock_user.is_active,
            email_verified=mock_user.email_verified,
            timezone="UTC",
            age=28,
            job="Software Developer",
            years_of_experience=5,
            legal_expertise_level="law_student",
            use_pseudonym=False,
            created_at=mock_user.created_at,
        )

        # Patch functions where the router imports them
        with patch("routers.auth.update_user_profile") as mock_update, patch(
            "routers.auth.get_user_primary_role"
        ) as mock_get_role:
            mock_update.return_value = updated_user
            mock_get_role.return_value = "user"

            # Override dependencies
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                update_data = {"name": "Updated Name", "email": "test@example.com"}

                response = client.put("/api/auth/profile", json=update_data)

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["name"] == "Updated Name"
            finally:
                app.dependency_overrides.clear()

    def test_change_password_success(self, client, mock_user):
        """Test change password at /auth/change-password"""
        from database import get_db
        from main import app
        from routers.auth import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        # Patch the change_user_password where the router imports it
        with patch("routers.auth.change_user_password") as mock_change:
            mock_change.return_value = True  # Success

            # Override dependencies
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                password_data = {
                    "current_password": "oldpass123",
                    "new_password": "newpass123",
                    "confirm_password": "newpass123",
                }

                response = client.post("/api/auth/change-password", json=password_data)

                assert response.status_code == status.HTTP_200_OK
                assert "successfully" in response.json()["message"].lower()
            finally:
                app.dependency_overrides.clear()

    def test_change_password_mismatch(self, client, mock_user):
        """Test change password with mismatched confirmation"""
        from database import get_db
        from main import app
        from routers.auth import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        # Override dependencies
        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            password_data = {
                "current_password": "oldpass123",
                "new_password": "newpass123",
                "confirm_password": "differentpass123",
            }

            response = client.post("/api/auth/change-password", json=password_data)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            app.dependency_overrides.clear()

    def test_verify_email_success(self, client):
        """Test email verification at /auth/verify-email/{token}"""
        with patch(
            "routers.auth.email_verification_service.verify_email_with_token"
        ) as mock_verify, patch("database.get_db") as mock_get_db:
            mock_verify.return_value = (True, "Email verified successfully")
            mock_get_db.return_value = Mock(spec=Session)

            response = client.post("/api/auth/verify-email/valid-token")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True

    def test_verify_email_invalid_token(self, client):
        """Test email verification with invalid token"""

        from database import get_db
        from main import app

        def override_get_db():
            return Mock(spec=Session)

        with patch(
            "routers.auth.email_verification_service.verify_email_with_token"
        ) as mock_verify:
            # Mock the service to return failure - this will trigger the 400->500 conversion
            mock_verify.return_value = (False, "Invalid token")

            # Override dependencies
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.post("/api/auth/verify-email/invalid-token")

                # The consolidated router properly returns 400 for invalid tokens
                assert response.status_code == status.HTTP_400_BAD_REQUEST
            finally:
                app.dependency_overrides.clear()

    def test_resend_verification_success(self, client, mock_user):
        """Test resend verification email at /auth/resend-verification"""
        from database import get_db
        from main import app

        # Create unverified user
        unverified_user = User(
            id=mock_user.id,
            username=mock_user.username,
            email=mock_user.email,
            name=mock_user.name,
            hashed_password=mock_user.hashed_password,
            is_superadmin=mock_user.is_superadmin,
            is_active=mock_user.is_active,
            email_verified=False,  # Key difference - not verified
            timezone="UTC",
            age=28,
            job="Software Developer",
            years_of_experience=5,
            legal_expertise_level="law_student",
            created_at=mock_user.created_at,
        )

        # Mock database to return unverified user
        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = unverified_user
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        # Use AsyncMock for the async email service call
        with patch(
            "routers.auth.email_verification_service.send_verification_email",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True

            # Override dependencies
            app.dependency_overrides[get_db] = override_get_db

            try:
                # Consolidated router requires email in request body
                response = client.post(
                    "/api/auth/resend-verification",
                    json={"email": mock_user.email},
                )

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "verification" in data["message"].lower()
            finally:
                app.dependency_overrides.clear()

    def test_resend_verification_already_verified(self, client, mock_user):
        """Test resend verification for already verified user"""
        from database import get_db
        from main import app

        # Mock database to return already-verified user
        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_user  # Already verified
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        # Override dependencies
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Consolidated router requires email in request body
            response = client.post(
                "/api/auth/resend-verification",
                json={"email": mock_user.email},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Consolidated router returns anti-enumeration message for all cases
            assert "message" in data
        finally:
            app.dependency_overrides.clear()


@pytest.mark.integration
class TestAuthRouterIntegration:
    """Integration tests for auth router with database"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_auth_endpoints_require_valid_request_format(self, client):
        """Test that auth endpoints properly validate request formats"""
        # Test login with missing fields
        response = client.post("/api/auth/login", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Test login with invalid JSON
        response = client.post("/api/auth/login", data="invalid")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_auth_endpoints_handle_missing_dependencies(self, client):
        """Test auth endpoints handle missing service dependencies gracefully"""
        from database import get_db
        from main import app

        def override_get_db():
            return Mock(spec=Session)

        # Mock authentication to fail gracefully rather than crash
        with patch("routers.auth.authenticate_user") as mock_auth:
            mock_auth.return_value = None  # Authentication failure

            # Override database dependency
            app.dependency_overrides[get_db] = override_get_db

            try:
                login_data = {"username": "test", "password": "test"}

                # Should handle gracefully - authentication should fail but not crash
                response = client.post("/api/auth/login", json=login_data)
                # Should return 401 for authentication failure
                assert response.status_code == status.HTTP_401_UNAUTHORIZED
            finally:
                app.dependency_overrides.clear()
