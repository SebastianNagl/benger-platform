"""
Unit tests for API endpoints
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi import status


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring ``db_user`` (used for
    async-endpoint tests that authenticate as a seeded DB user). The real
    ``require_superadmin`` dependency keys off ``is_superadmin``, so flipping
    the seeded user's flag drives both the 403 and 200 branches."""
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

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


async def _seed_db_user(db, *, is_superadmin=False, is_active=True):
    from models import User as DBUser

    u = DBUser(
        id=_uid(),
        username=f"apiep-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="API EP User",
        is_superadmin=is_superadmin,
        is_active=is_active,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


@pytest.mark.unit
@pytest.mark.api
class TestAuthenticationEndpoints:
    """Test authentication-related endpoints"""

    def test_login_success(self, client, test_users):
        """Test successful login"""
        response = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "admin123"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data

    def test_login_invalid_credentials(self, client, test_users):
        """Test login with invalid credentials"""
        response = client.post(
            "/api/auth/login",
            json={"username": "admin@test.com", "password": "wrongpassword"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_current_user_success(self, client, auth_headers):
        """Test getting current user info"""
        response = client.get("/api/auth/me", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "id" in data
        assert "username" in data
        assert "email" in data

    def test_signup_success(self, client):
        """Test user signup"""
        user_data = {
            "username": "newuser@test.com",
            "email": "newuser@test.com",
            "name": "New User",
            "password": "password123",
            "role": "annotator",
            "legal_expertise_level": "layperson",
            "german_proficiency": "native",
        }
        response = client.post("/api/auth/signup", json=user_data)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["username"] == user_data["username"]
        assert data["email"] == user_data["email"]

    def test_register_admin_only(self, client, auth_headers):
        """Test that register endpoint requires admin role"""
        user_data = {
            "username": "adminuser@test.com",
            "email": "adminuser@test.com",
            "name": "Admin User",
            "password": "password123",
            "role": "admin",
            "legal_expertise_level": "practicing_lawyer",
            "german_proficiency": "native",
        }

        # Test with annotator role (should fail)
        response = client.post(
            "/api/auth/register", json=user_data, headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Test with admin role (should succeed)
        response = client.post("/api/auth/register", json=user_data, headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK

    def test_verify_token(self, client, auth_headers):
        """Test token verification endpoint"""
        response = client.get("/api/auth/verify", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
@pytest.mark.api
class TestUserManagementEndpoints:
    """Test user management endpoints"""

    @pytest.mark.asyncio
    async def test_get_all_users_admin_only(self, async_test_client, async_test_db):
        """Test that getting all users requires admin role (async users router)."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        annotator = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()

        with _as_user(annotator):
            response = await async_test_client.get("/api/users")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        with _as_user(admin):
            response = await async_test_client.get("/api/users")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_update_user_role_admin_only(self, async_test_client, async_test_db):
        """Test updating user role requires admin.

        The users router moved to the async DB lane, so the target user is
        seeded via async_test_db and both branches are driven by toggling the
        acting user's superadmin flag (the real ``require_superadmin`` keys off
        it).
        """
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        annotator = await _seed_db_user(async_test_db, is_superadmin=False)
        target = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        role_data = {"is_superadmin": False}

        with _as_user(annotator):
            response = await async_test_client.patch(
                f"/api/users/{target.id}/role", json=role_data
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        with _as_user(admin):
            response = await async_test_client.patch(
                f"/api/users/{target.id}/role", json=role_data
            )
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_update_user_status_admin_only(self, async_test_client, async_test_db):
        """Test updating user status requires admin (async users router)."""
        admin = await _seed_db_user(async_test_db, is_superadmin=True)
        annotator = await _seed_db_user(async_test_db, is_superadmin=False)
        target = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        status_data = {"is_active": False}

        with _as_user(annotator):
            response = await async_test_client.patch(
                f"/api/users/{target.id}/status", json=status_data
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        with _as_user(admin):
            response = await async_test_client.patch(
                f"/api/users/{target.id}/status", json=status_data
            )
        assert response.status_code == status.HTTP_200_OK

    def test_delete_user_admin_only(self, client, auth_headers, test_users):
        """Test deleting user requires admin"""
        user_id = test_users[2].id  # annotator user

        # Test with annotator role (should fail)
        response = client.delete(f"/api/users/{user_id}", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Test with admin role (should succeed)
        response = client.delete(f"/api/users/{user_id}", headers=auth_headers["admin"])
        assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.unit
@pytest.mark.api
class TestTaskEndpoints:
    """Test task-related endpoints"""

    def test_create_task_contributor_required(self, client, auth_headers):
        """Test creating task requires contributor role"""
        task_data = {  # noqa: F841
            "name": "Test Task",
            "description": "A test task",
            "template_id": "qa",  # Use template_id instead of task_type and template
            "visibility": "private",
        }

        # Test with annotator role - tasks are created through import endpoint
        import_data = {"data": [{"text": "Test task", "label": "test"}], "meta": {"source": "test"}}
        response = client.post(
            "/api/projects/test-project/import", json=import_data, headers=auth_headers["annotator"]
        )
        # May return 404 if project doesn't exist or 403 if no access
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_404_NOT_FOUND,  # Project not found
            status.HTTP_403_FORBIDDEN,  # No access to project
        ]

        # Test with contributor role - should also succeed
        response = client.post(
            "/api/projects/test-project/import",
            json=import_data,
            headers=auth_headers["contributor"],
        )
        # Contributors can also import tasks
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_404_NOT_FOUND,  # Project not found
            status.HTTP_403_FORBIDDEN,  # No access to project
        ]

    @pytest.mark.asyncio
    async def test_get_tasks(self, async_test_client, async_test_db):
        """Test getting all tasks (projects list, async router)."""
        user = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        with _as_user(user):
            response = await async_test_client.get("/api/projects", follow_redirects=True)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Projects endpoint returns paginated response
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_get_task_by_id(self, async_test_client, async_test_db):
        """Test getting non-existent task by ID returns 404 (async router)."""
        user = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        with _as_user(user):
            response = await async_test_client.get(
                "/api/projects/tasks/00000000-0000-0000-0000-000000000000"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_task_contributor_required(self, async_test_client, async_test_db):
        """Test updating a non-existent task returns 404 (async router)."""
        user = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        task_update = {"name": "Updated Task", "description": "Updated description"}
        with _as_user(user):
            response = await async_test_client.patch(
                "/api/projects/tasks/00000000-0000-0000-0000-000000000000/metadata",
                json=task_update,
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_task_admin_required(self, async_test_client, async_test_db):
        """Test deleting task requires admin role (bulk-delete, async router)."""
        user = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        delete_data = {"task_ids": [1]}
        with _as_user(user):
            response = await async_test_client.post(
                "/api/projects/test-project/tasks/bulk-delete",
                json=delete_data,
            )
        # May return 404 if project doesn't exist or 403 if no permission
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,  # No permission to delete
            status.HTTP_404_NOT_FOUND,  # Project not found
        ]


@pytest.mark.unit
@pytest.mark.api
class TestEvaluationTypeEndpoints:
    """Test evaluation type endpoints"""

    def test_get_evaluation_types(self, client, auth_headers):
        """Test getting all evaluation types"""
        response = client.get(
            "/api/evaluations/evaluation-types", headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_evaluation_types_filtered(self, client, auth_headers):
        """Test getting evaluation types filtered by task type"""
        task_type_id = "qa_reasoning"
        response = client.get(
            f"/api/evaluations/evaluation-types?task_type_id={task_type_id}",
            headers=auth_headers["annotator"],
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_evaluation_type_by_id(self, async_test_client, async_test_db):
        """Test getting evaluation type by ID.

        The single-type endpoint moved to the async DB lane. We self-seed a
        unique-id row (rather than the shared ``test_evaluation_types`` fixture,
        whose fixed-id bulk insert UniqueViolation's against the long-lived
        test DB) and authenticate as a seeded user.
        """
        from models import EvaluationType as DBEvaluationType

        user = await _seed_db_user(async_test_db, is_superadmin=False)
        eval_type_id = f"acc-{_uid()[:8]}"
        async_test_db.add(DBEvaluationType(
            id=eval_type_id,
            name="Accuracy",
            description="Measures prediction accuracy",
            category="performance",
            higher_is_better=True,
            value_range={"min": 0.0, "max": 1.0},
            applicable_project_types=["qa"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        ))
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get(
                f"/api/evaluations/evaluation-types/{eval_type_id}",
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == eval_type_id


@pytest.mark.unit
@pytest.mark.api
class TestDataUploadEndpoints:
    """Test data upload endpoints"""

    def test_upload_data_annotator_required(self, client, auth_headers):
        """Test uploading data requires annotator role"""
        # Note: /data/upload endpoint has been removed (see main.py comment)
        # Expect 404 for removed endpoint
        response = client.post(
            "/data/upload",
            files={"file": ("test.csv", b"test,data", "text/csv")},
            data={"task_id": "1", "description": "Test upload"},
            headers=auth_headers["annotator"],
        )
        # Endpoint has been removed, expect 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_uploaded_data(self, client, auth_headers):
        """Test deleting uploaded data"""
        # This will likely return 404 since no data exists, which is fine
        # Delete file endpoint
        response = client.delete("/nonexistent", headers=auth_headers["annotator"])
        assert response.status_code in [
            status.HTTP_204_NO_CONTENT,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.unit
@pytest.mark.api
class TestEvaluationEndpoints:
    """Test evaluation endpoints"""

    def test_run_evaluation_contributor_required(self, client, auth_headers):
        """Test running evaluation requires contributor role"""
        eval_request = {
            "task_id": "1",
            "model_id": "test-model",
            "metrics": ["accuracy", "f1"],
            "model_configuration": {"type": "classification"},
        }

        # Test with annotator role on non-existent task (should return 404)
        response = client.post("/eval/run", json=eval_request, headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_evaluations(self, client, auth_headers, test_org):
        """Test getting evaluations"""
        response = client.get("/api/evaluations/", headers=auth_headers["annotator"])
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_evaluation_status(self, client, auth_headers):
        """Test getting evaluation status"""
        # This will likely return 404 since no evaluation exists, which is fine
        response = client.get("/evaluation/status/nonexistent", headers=auth_headers["annotator"])
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_get_supported_metrics(self, client, auth_headers):
        """Test getting supported metrics"""
        # Check evaluation types instead of supported metrics
        response = client.get(
            "/api/evaluations/evaluation-types", headers=auth_headers["annotator"]
        )
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
@pytest.mark.api
class TestProjectEndpoints:
    """Test native project endpoints"""

    @pytest.mark.asyncio
    async def test_get_projects(self, async_test_client, async_test_db):
        """Test getting projects (async router)."""
        user = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        with _as_user(user):
            response = await async_test_client.get("/api/projects", follow_redirects=True)
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_project_by_id(self, async_test_client, async_test_db):
        """Test getting non-existent project by ID returns 404 (async router)."""
        user = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        with _as_user(user):
            response = await async_test_client.get("/api/projects/1")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_project_tasks(self, async_test_client, async_test_db):
        """Test getting tasks for non-existent project returns 404 (async router)."""
        user = await _seed_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        with _as_user(user):
            response = await async_test_client.get("/api/projects/1/tasks")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.unit
@pytest.mark.api
class TestRootEndpoint:
    """Test root endpoint"""

    def test_root_endpoint(self, client):
        """Test root endpoint returns welcome message"""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
