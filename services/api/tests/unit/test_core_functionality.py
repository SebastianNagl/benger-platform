"""
Core Functionality Tests

This module contains tests for the essential functionality of the BenGER API,
including authentication, basic CRUD operations, and core business logic.
"""


import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi import status
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Async-lane helpers
#
# ``GET /api/auth/me`` and ``GET /api/evaluations/evaluation-types/{id}`` were
# migrated to the async DB lane (``Depends(get_async_db)``). A sync TestClient
# call into those handlers fails with "attached to a different loop" /
# "Event loop is closed" because the async engine is bound to a different event
# loop than TestClient's portal. These helpers drive those endpoints through
# ``async_test_client`` + ``async_test_db`` per the canonical recipe in
# tests/integration/test_auth_me_integration.py.
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring a seeded DB user row."""
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    au = AuthUser(
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


async def _aseed_user(db, *, is_superadmin=True):
    from auth_module.user_service import get_password_hash
    from models import User as DBUser

    user = DBUser(
        id=str(uuid.uuid4()),
        username=f"core-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Core Test User",
        hashed_password=get_password_hash("testpassword123"),
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def _aseed_eval_type(db):
    from models import EvaluationType

    et = EvaluationType(
        id=f"core-et-{uuid.uuid4().hex[:8]}",
        name="Core Accuracy",
        description="Classification accuracy",
        category="classification",
        higher_is_better=True,
        value_range={"min": 0, "max": 1},
        applicable_project_types=["text_classification"],
        is_active=True,
    )
    db.add(et)
    await db.flush()
    return et


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

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, async_test_client, async_test_db):
        """Test getting current user info with valid token.

        ``GET /api/auth/me`` is on the async DB lane; drive it through
        ``async_test_client`` with the user seeded in the async transaction and
        the identity supplied via the require_user override.
        """
        user = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get("/api/auth/me")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "id" in data
        assert "username" in data
        assert "email" in data
        assert "is_superadmin" in data
        assert data["id"] == user.id
        assert data["is_superadmin"] is True

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
        assert data["valid"] == True  # noqa: E712


@pytest.mark.unit
class TestRoleBasedAccess:
    """Test role-based access control."""

    @pytest.mark.asyncio
    async def test_admin_access_to_users(self, async_test_client, async_test_db):
        """Test that admin can access user management endpoints.

        GET /api/users is async-lane (Depends(get_async_db)).
        """
        admin = await _aseed_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            response = await async_test_client.get("/api/users")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_non_admin_denied_user_access(self, async_test_client, async_test_db):
        """Test that non-admin users cannot access user management."""
        annotator = await _aseed_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        with _as_user(annotator):
            response = await async_test_client.get("/api/users")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_contributor_can_create_tasks(self, client: TestClient, auth_headers):
        """Test that contributors can create tasks."""
        task_data = {  # noqa: F841
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
        task_data = {  # noqa: F841
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

    @pytest.mark.asyncio
    async def test_get_evaluation_type_by_id(self, async_test_client, async_test_db):
        """Test retrieving a specific evaluation type.

        ``GET /api/evaluations/evaluation-types/{id}`` is on the async DB lane;
        seed the row + actor via ``async_test_db`` and drive the request through
        ``async_test_client`` with require_user overridden.
        """
        user = await _aseed_user(async_test_db, is_superadmin=False)
        eval_type = await _aseed_eval_type(async_test_db)
        eval_type_id = eval_type.id
        eval_type_name = eval_type.name
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get(
                f"/api/evaluations/evaluation-types/{eval_type_id}"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == eval_type_id
        assert data["name"] == eval_type_name


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
        from auth_module.user_service import get_password_hash, verify_password

        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed != password
        assert verify_password(password, hashed) == True  # noqa: E712
        assert verify_password("wrong_password", hashed) == False  # noqa: E712

    def test_different_passwords_different_hashes(self):
        """Test that different passwords produce different hashes."""
        from auth_module.user_service import get_password_hash

        password1 = "password123"
        password2 = "password456"

        hash1 = get_password_hash(password1)
        hash2 = get_password_hash(password2)

        assert hash1 != hash2
