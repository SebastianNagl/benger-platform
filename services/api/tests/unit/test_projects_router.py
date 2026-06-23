"""
Comprehensive tests for the projects router endpoints.
Tests the current router architecture mounted at /api/projects/*.

The CRUD handlers were migrated to the async DB lane (``Depends(get_async_db)``
+ ``await db.execute(select(...))``), so the old ``get_db``-Mock / query-chain
pattern no longer reaches the handlers. These tests seed real ORM rows via
``async_test_db`` and drive the surface through ``async_test_client``;
``require_user`` is overridden per-test via ``_as_user`` to an auth User
matching the seeded owner. Auth-only / 422-validation / route-existence tests
that never reach the async DB keep their original lightweight ``TestClient``
form.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, User
from project_models import Project, ProjectOrganization


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
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


async def _make_user(db, *, is_superadmin=False, name="Test User"):
    u = User(
        id=_uid(),
        username=f"pr-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Test Org"):
    org = Organization(id=_uid(), name=name, slug=f"org-{_uid()[:8]}")
    db.add(org)
    await db.flush()
    return org


async def _make_project(
    db,
    *,
    created_by: str,
    title="Test Project",
    description="Test project description",
    is_private=True,
    is_public=False,
    label_config="<View></View>",
):
    p = Project(
        id=_uid(),
        title=title,
        description=description,
        created_by=created_by,
        label_config=label_config,
        is_private=is_private,
        is_public=is_public,
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    return p


class TestProjectsRouter:
    """Test projects router endpoints mounted at /api/projects/"""

    @pytest.fixture
    def client(self):
        """Create test client (sync, used only by auth/route tests)."""
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_list_projects_success(self, async_test_client, async_test_db):
        """Test listing projects at /api/projects/"""
        user = await _make_user(async_test_db)
        await _make_project(async_test_db, created_by=user.id, title="Legal Project")
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get("/api/projects/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        # The user's own private project is visible.
        assert any(p["title"] == "Legal Project" for p in data["items"])

    @pytest.mark.asyncio
    async def test_list_projects_with_pagination(self, async_test_client, async_test_db):
        """Test listing projects with pagination parameters"""
        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get(
                "/api/projects/", params={"page": 2, "page_size": 50}
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 50

    @pytest.mark.asyncio
    async def test_list_projects_with_search_filter(self, async_test_client, async_test_db):
        """Test listing projects with search filter"""
        user = await _make_user(async_test_db)
        await _make_project(async_test_db, created_by=user.id, title="Legal matters")
        await _make_project(async_test_db, created_by=user.id, title="Unrelated topic")
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get("/api/projects/", params={"search": "legal"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        titles = [p["title"] for p in data["items"]]
        assert "Legal matters" in titles
        assert "Unrelated topic" not in titles

    @pytest.mark.asyncio
    async def test_list_projects_with_archived_filter(self, async_test_client, async_test_db):
        """Test listing projects with is_archived filter"""
        user = await _make_user(async_test_db)
        await _make_project(async_test_db, created_by=user.id)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get(
                "/api/projects/", params={"is_archived": True}
            )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_list_projects_superadmin_default_narrow(
        self, async_test_client, async_test_db
    ):
        """Smoke test: /api/projects/ as a superadmin without the
        include_all_private flag must still return 200 (with the narrowed
        list). Real visibility behavior is covered end-to-end in
        tests/integration/test_projects_superadmin_visibility.py."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get("/api/projects/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data

    def test_list_projects_requires_authentication(self, client):
        """Test that listing projects requires authentication"""
        response = client.get("/api/projects/")
        # Should require authentication
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_project_success(self, async_test_client, async_test_db):
        """Test getting single project by ID at /api/projects/{project_id}"""
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(f"/api/projects/{project.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == project.id

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, async_test_client, async_test_db):
        """Test getting non-existent project"""
        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.get("/api/projects/nonexistent-project")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_project_access_denied(self, async_test_client, async_test_db):
        """Test access denied for a private project the user doesn't own.

        The endpoint returns 403 (project exists, access control denies it).
        """
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=owner.id, is_private=True
        )
        await async_test_db.commit()

        with _as_user(other):
            response = await async_test_client.get(f"/api/projects/{project.id}")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_project_success(self, async_test_client, async_test_db):
        """Test creating project at /api/projects/ with superadmin.

        Private (default) path: no org context header => private project.
        """
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        project_data = {"title": "New Project", "description": "A new test project"}
        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_created_sync"
        ), patch("routers.projects.crud._create_initial_report_draft_sync"):
            response = await async_test_client.post("/api/projects/", json=project_data)

        assert response.status_code in [200, 201]
        body = response.json()
        assert body["title"] == "New Project"
        # The project was persisted.
        row = (
            await async_test_db.execute(select(Project).where(Project.id == body["id"]))
        ).scalar_one_or_none()
        assert row is not None
        assert row.title == "New Project"
        assert row.created_by == admin.id

    @pytest.mark.asyncio
    async def test_create_project_invalid_data(self, async_test_client, async_test_db):
        """Test creating project with invalid data (missing title) → 422.

        Validation rejects before reaching the DB, but we still drive it through
        the async client under an authenticated user.
        """
        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.post(
                "/api/projects/", json={"description": "Missing title"}
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_project_success(self, async_test_client, async_test_db):
        """Test updating project at /api/projects/{project_id}"""
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id)
        await async_test_db.commit()

        update_data = {
            "title": "Updated Project Title",
            "description": "Updated description",
        }
        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/projects/{project.id}", json=update_data
            )

        assert response.status_code == 200
        assert response.json()["title"] == "Updated Project Title"
        # Persisted change re-queried (translates the old commit-assert).
        await async_test_db.refresh(project)
        assert project.title == "Updated Project Title"
        assert project.description == "Updated description"

    @pytest.mark.asyncio
    async def test_delete_project_success(self, async_test_client, async_test_db):
        """Test deleting project at /api/projects/{project_id}"""
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        project_id = project.id
        await async_test_db.commit()

        with _as_user(admin), patch("routers.projects.crud._notify_project_deleted_sync"):
            response = await async_test_client.delete(f"/api/projects/{project_id}")

        assert response.status_code in [200, 204]
        # Row is gone.
        row = (
            await async_test_db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        assert row is None


class TestPrivateProjectDeletion:
    """Test that private project creators can delete their own projects."""

    @pytest.mark.asyncio
    async def test_delete_private_project_by_creator(
        self, async_test_client, async_test_db
    ):
        """Private project creator should be able to delete their project."""
        creator = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=creator.id, is_private=True
        )
        project_id = project.id
        await async_test_db.commit()

        with _as_user(creator), patch("routers.projects.crud._notify_project_deleted_sync"):
            response = await async_test_client.delete(f"/api/projects/{project_id}")

        assert response.status_code in [200, 204]
        row = (
            await async_test_db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_delete_private_project_by_other_user_blocked(
        self, async_test_client, async_test_db
    ):
        """Non-creator non-superadmin should NOT be able to delete a private project."""
        creator = await _make_user(async_test_db)
        other_user = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=creator.id, is_private=True
        )
        project_id = project.id
        await async_test_db.commit()

        with _as_user(other_user):
            response = await async_test_client.delete(f"/api/projects/{project_id}")

        assert response.status_code == 403
        # Row still present (not deleted).
        row = (
            await async_test_db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        assert row is not None

    @pytest.mark.asyncio
    async def test_delete_org_project_by_regular_user_blocked(
        self, async_test_client, async_test_db
    ):
        """Non-superadmin should NOT be able to delete an org project."""
        regular_user = await _make_user(async_test_db)
        # Org project (not private) created by the regular user. The delete
        # guard only allows superadmins, or creators of *private* projects.
        project = await _make_project(
            async_test_db, created_by=regular_user.id, is_private=False
        )
        project_id = project.id
        await async_test_db.commit()

        with _as_user(regular_user):
            response = await async_test_client.delete(f"/api/projects/{project_id}")

        assert response.status_code == 403


@pytest.mark.integration
class TestProjectsRouterIntegration:
    """Integration tests for projects router"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_projects_endpoints_require_authentication(self, client):
        """Test that project endpoints require authentication"""
        from main import app

        # Ensure no authentication dependencies are overridden
        app.dependency_overrides.clear()

        endpoints = [
            ("GET", "/api/projects/"),
            ("POST", "/api/projects/", {"title": "Test"}),
            ("GET", "/api/projects/test-project"),
            ("PATCH", "/api/projects/test-project", {"title": "Updated"}),  # Use PATCH, not PUT
            ("DELETE", "/api/projects/test-project"),
        ]

        for method, endpoint, *json_data in endpoints:
            kwargs = {}
            if json_data:
                kwargs["json"] = json_data[0]

            response = client.request(method, endpoint, **kwargs)
            # Should require authentication - endpoints should return 401/403 without valid auth
            # Some endpoints might also return 405 for unsupported methods before auth check
            assert response.status_code in [
                401,
                403,
                405,
                422,
            ]  # 422 for validation, 405 for method not allowed

    def test_projects_endpoints_request_validation(self, client):
        """Test that project endpoints reject invalid requests"""
        from main import app

        # Ensure no dependencies are overridden for this validation test
        app.dependency_overrides.clear()

        # Test create with invalid JSON - auth middleware may reject before validation
        response = client.post("/api/projects/", data="invalid")
        assert response.status_code in [401, 422]

        # Test update with invalid JSON
        response = client.patch("/api/projects/test-project", data="invalid")  # Use PATCH, not PUT
        assert response.status_code in [
            401,
            422,
            404,
            405,
        ]

    # test_projects_endpoints_handle_missing_dependencies removed:
    # Accepted every status code including 500/503, testing nothing meaningful.
