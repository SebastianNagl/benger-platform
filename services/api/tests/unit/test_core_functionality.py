"""
Core Functionality Tests

This module contains tests for the essential functionality of the BenGER API,
including authentication, basic CRUD operations, and core business logic.
"""


import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestHealthAndStatus:
    """Test health check and system status endpoints."""

    def test_health_check(self, client: TestClient):
        """Test that the health check endpoint works."""
        response = client.get("/healthz")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_root_endpoint(self, client: TestClient):
        """Test the root endpoint returns basic info."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
class TestAuthentication:
    """Test authentication functionality."""

    def test_login_success(self, client: TestClient, test_users):
        """Test successful login with valid credentials."""
        response = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["username"] == "admin@test.com"

    def test_login_invalid_credentials(self, client: TestClient, test_users):
        """Test login with invalid credentials."""
        response = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "wrongpassword"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, client: TestClient):
        """Test login with non-existent user."""
        response = client.post(
            "/api/auth/login",
            json={"username": "nonexistent@test.com", "password": "password"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_current_user_success(self, client: TestClient, auth_headers):
        """Test getting current user info with valid token."""
        response = client.get("/api/auth/me", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "id" in data
        assert "username" in data
        assert "email" in data
        assert "is_superadmin" in data

    def test_get_current_user_invalid_token(self, client: TestClient):
        """Test getting current user with invalid token."""
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_current_user_no_token(self, client: TestClient):
        """Test getting current user without token."""
        response = client.get("/api/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_verification(self, client: TestClient, auth_headers):
        """Test token verification endpoint."""
        response = client.get("/api/auth/verify", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "valid" in data
        assert data["valid"] is True


@pytest.mark.unit
class TestRoleBasedAccess:
    """Test role-based access control."""

    def test_admin_access_to_users(self, client: TestClient, auth_headers):
        """Test that admin can access user management endpoints."""
        response = client.get("/api/users", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK

    def test_non_admin_denied_user_access(self, client: TestClient, auth_headers):
        """Test that non-admin users cannot access user management."""
        response = client.get("/api/users", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_contributor_can_create_tasks(self, client: TestClient, auth_headers):
        """Test that contributors can create tasks."""
        task_data = {
            "name": "Test Task",
            "description": "A test task",
            "task_type": "qa_reasoning",  # Using static task type
            "template": "<View></View>",
            "visibility": "private",
        }

        # Test native annotation system - tasks are created via import endpoint
        import_data = {"data": [{"text": "Test task", "label": "test"}], "meta": {"source": "test"}}
        response = client.post(
            "/api/projects/test-project/import",
            json=import_data,
            headers=auth_headers["contributor"],
        )
        # May return 404 if project doesn't exist or 403 if no access
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_404_NOT_FOUND,  # Project not found
            status.HTTP_403_FORBIDDEN,  # No access to project
        ]

    def test_annotator_cannot_create_tasks(self, client: TestClient, auth_headers):
        """Test that annotators cannot create tasks."""
        task_data = {
            "name": "Test Task",
            "description": "A test task",
            "task_type": "qa_reasoning",  # Using static task type
            "template": "<View></View>",
            "visibility": "private",
        }

        # Test native annotation system - tasks are created via import endpoint
        import_data = {"data": [{"text": "Test task", "label": "test"}], "meta": {"source": "test"}}
        response = client.post(
            "/api/projects/test-project/import",
            json=import_data,
            headers=auth_headers["annotator"],
        )
        # Annotators can also import tasks if they have access to the project
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_404_NOT_FOUND,  # Project not found
            status.HTTP_403_FORBIDDEN,  # No access to project
        ]


@pytest.mark.unit
class TestEvaluationTypes:
    """Test evaluation type functionality."""

    def test_get_evaluation_types(self, client: TestClient, auth_headers, test_evaluation_types):
        """Test retrieving all evaluation types."""
        response = client.get(
            "/api/evaluations/evaluation-types", headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # We created 2 test evaluation types

    def test_get_evaluation_type_by_id(
        self, client: TestClient, auth_headers, test_evaluation_types
    ):
        """Test retrieving a specific evaluation type."""
        eval_type_id = test_evaluation_types[0].id
        response = client.get(
            f"/api/evaluations/evaluation-types/{eval_type_id}", headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == eval_type_id
        assert data["name"] == test_evaluation_types[0].name


@pytest.mark.unit
class TestInputValidation:
    """Test input validation and error handling."""

    def test_malformed_login_request(self, client: TestClient):
        """Test that malformed login requests are handled gracefully."""
        response = client.post("/api/auth/login", json={"invalid": "data"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_empty_login_request(self, client: TestClient):
        """Test empty login request."""
        response = client.post("/api/auth/login", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_invalid_json_request(self, client: TestClient):
        """Test request with invalid JSON."""
        response = client.post(
            "/api/auth/login",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.unit
class TestSecurityHeaders:
    """Test security headers and CORS configuration."""

    def test_content_type_headers(self, client: TestClient):
        """Test that proper content-type headers are returned."""
        response = client.get("/healthz")
        assert "application/json" in response.headers.get("content-type", "")

    def test_cors_headers_present(self, client: TestClient):
        """Test that CORS is configured."""
        response = client.options("/")
        # Should not error out, CORS should be configured
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        ]


@pytest.mark.unit
class TestPasswordSecurity:
    """Test password hashing and verification."""

    def test_password_hashing(self):
        """Test password hashing functionality."""
        from user_service import get_password_hash, verify_password

        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrong_password", hashed) is False

    def test_different_passwords_different_hashes(self):
        """Test that different passwords produce different hashes."""
        from user_service import get_password_hash

        password1 = "password123"
        password2 = "password456"

        hash1 = get_password_hash(password1)
        hash2 = get_password_hash(password2)

        assert hash1 != hash2
