"""
Integration tests for /api/auth/me endpoint
Tests full authentication flow including session persistence
GitHub Issue #310
"""

import pytest
from sqlalchemy.orm import Session

from auth_module.service import create_access_token
from models import User as DBUser


@pytest.fixture
def test_user(test_db: Session):
    """Create a test user in the database"""
    from auth_module.user_service import get_password_hash

    user = DBUser(
        id="integration-test-user-id",
        username="testuser",
        email="test@integration.com",
        name="Integration Test User",
        hashed_password=get_password_hash("testpassword123"),
        is_superadmin=False,
        is_active=True,
        email_verified=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    """Create authentication headers with valid JWT"""
    token_data = {
        "sub": test_user.username,
        "user_id": test_user.id,
        "is_superadmin": test_user.is_superadmin,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


class TestAuthMeIntegration:
    """Integration tests for /api/auth/me endpoint"""

    def test_login_returns_user_data_not_jwt_claims(self, client, test_user):
        """Test that login endpoint returns user data in response"""
        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "testpassword123"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response includes user object
        assert "user" in data
        user_data = data["user"]

        # Verify user object has correct structure
        assert user_data["id"] == test_user.id
        assert user_data["username"] == test_user.username
        assert user_data["email"] == test_user.email
        assert user_data["name"] == test_user.name
        assert "created_at" in user_data

        # Verify it's not JWT claims
        assert "sub" not in user_data
        assert "exp" not in user_data
        assert "user_id" not in user_data  # User object uses 'id', not 'user_id'

    def test_me_endpoint_returns_user_from_database(self, client, test_user, auth_headers):
        """Test that /me endpoint returns user from database, not JWT claims"""
        response = client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Verify response is user object from database
        assert data["id"] == test_user.id
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email
        assert data["name"] == test_user.name
        assert data["is_superadmin"] == test_user.is_superadmin
        assert data["is_active"] == test_user.is_active
        assert "created_at" in data

        # Ensure it's NOT JWT claims
        assert "sub" not in data
        assert "exp" not in data
        assert "user_id" not in data  # User model uses 'id'

    def test_me_endpoint_with_cookie_auth(self, client, test_user):
        """Test that /me endpoint works with HttpOnly cookie authentication"""
        # Login to get cookies
        login_response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "testpassword123"},
        )
        assert login_response.status_code == 200

        # Extract cookies from login response
        cookies = login_response.cookies

        # Call /me endpoint with cookies
        response = client.get("/api/auth/me", cookies=cookies)

        assert response.status_code == 200
        data = response.json()

        # Verify user data from database
        assert data["id"] == test_user.id
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email

    def test_me_endpoint_fails_without_auth(self, client):
        """Test that /me endpoint returns 401 without authentication"""
        response = client.get("/api/auth/me")

        assert response.status_code == 401
        assert "detail" in response.json()

    def test_me_endpoint_fails_with_invalid_token(self, client):
        """Test that /me endpoint returns 401 with invalid token"""
        headers = {"Authorization": "Bearer invalid-token"}
        response = client.get("/api/auth/me", headers=headers)

        assert response.status_code == 401

    def test_me_endpoint_handles_user_data_changes(
        self, client, test_user, auth_headers, test_db
    ):
        """Test that /me endpoint reflects database changes"""
        # Get initial user data
        response1 = client.get("/api/auth/me", headers=auth_headers)
        assert response1.status_code == 200
        initial_data = response1.json()
        assert initial_data["name"] == "Integration Test User"

        # Update user in database
        test_user.name = "Updated Name"
        test_user.email = "updated@integration.com"
        test_db.commit()

        # Get updated user data - should reflect database changes
        response2 = client.get("/api/auth/me", headers=auth_headers)
        assert response2.status_code == 200
        updated_data = response2.json()

        # Verify changes are reflected
        assert updated_data["name"] == "Updated Name"
        assert updated_data["email"] == "updated@integration.com"
        assert updated_data["id"] == test_user.id  # ID should remain the same

    def test_session_persistence_after_refresh(self, client, test_user):
        """Test that session persists after page refresh (cookie-based auth)"""
        # Step 1: Login
        login_response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "testpassword123"},
        )
        assert login_response.status_code == 200
        cookies = login_response.cookies

        # Step 2: Access protected endpoint with cookies
        me_response1 = client.get("/api/auth/me", cookies=cookies)
        assert me_response1.status_code == 200

        # Step 3: Simulate page refresh - new request with same cookies
        me_response2 = client.get("/api/auth/me", cookies=cookies)
        assert me_response2.status_code == 200

        # Step 4: Verify data consistency
        data1 = me_response1.json()
        data2 = me_response2.json()

        assert data1["id"] == data2["id"]
        assert data1["username"] == data2["username"]
        assert data1 == data2  # Should be identical

    def test_me_endpoint_response_validation(self, client, test_user, auth_headers):
        """Test that /me endpoint response passes Pydantic validation"""
        response = client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # All required fields must be present
        required_fields = [
            "id",
            "username",
            "email",
            "name",
            "is_superadmin",
            "is_active",
            "created_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify field types
        assert isinstance(data["id"], str)
        assert isinstance(data["username"], str)
        assert isinstance(data["email"], str)
        assert isinstance(data["name"], str)
        assert isinstance(data["is_superadmin"], bool)
        assert isinstance(data["is_active"], bool)
        assert isinstance(data["created_at"], str)  # ISO format datetime string
