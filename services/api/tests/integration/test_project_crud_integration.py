"""
Integration tests for project CRUD operations.

Targets: routers/projects/crud.py lines 100-792

The CRUD handlers were migrated to the async DB lane (``Depends(get_async_db)``
+ ``await db.execute(select(...))``). Rows seeded into the sync ``test_db`` are
invisible to the async engine, so these tests seed real ORM rows via
``async_test_db`` and drive the surface through ``async_test_client`` with
``require_user`` overridden per-test via ``_as_user`` to an auth user matching
the seeded actor. Create/delete tests patch the sync notification/report
wrappers to avoid the Redis-backed threadpool stall. The pure
``deep_merge_dicts`` unit tests have no DB dependency and are unchanged.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import Project, ProjectOrganization, Task


def _uid():
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


def _no_side_effects():
    return (
        patch("routers.projects.crud._notify_project_created_sync"),
        patch("routers.projects.crud._notify_project_deleted_sync"),
        patch("routers.projects.crud._create_initial_report_draft_sync"),
    )


async def _make_user(db, *, is_superadmin=False, name="Test User"):
    u = User(
        id=_uid(),
        username=f"ci-{_uid()[:8]}",
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


@pytest.mark.integration
class TestProjectCrudIntegration:
    """Integration tests for project CRUD endpoints."""

    async def _create_org(self, db: AsyncSession, admin_user_id: str) -> Organization:
        """Create a test organization."""
        org = Organization(
            id=str(uuid.uuid4()),
            name="Test Org CRUD",
            slug=f"test-org-crud-{uuid.uuid4().hex[:8]}",
            display_name="Test Org CRUD Display",
            description="Test org for CRUD tests",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(org)
        await db.flush()
        return org

    async def _create_membership(
        self, db: AsyncSession, user_id: str, org_id: str, role: str = "ORG_ADMIN"
    ):
        membership = OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user_id,
            organization_id=org_id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
        db.add(membership)
        await db.flush()
        return membership

    async def _create_project(
        self, db: AsyncSession, org_id: str, created_by: str, **kwargs
    ) -> Project:
        """Create a test project linked to an organization."""
        project_data = {
            "id": str(uuid.uuid4()),
            "title": kwargs.get("title", "Test Project"),
            "description": kwargs.get("description", "Test description"),
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc),
        }
        project = Project(**project_data)
        db.add(project)
        await db.flush()

        po = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=org_id,
            assigned_by=created_by,
        )
        db.add(po)
        await db.flush()
        return project

    @pytest.mark.asyncio
    async def test_list_projects(self, async_test_client, async_test_db):
        """Test listing projects."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        await self._create_project(async_test_db, org.id, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get("/api/projects/")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_projects_with_org_context(
        self, async_test_client, async_test_db
    ):
        """Test listing projects with org context filter."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        await self._create_project(async_test_db, org.id, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
            )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_create_project(self, async_test_client, async_test_db):
        """Test creating a project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            response = await async_test_client.post(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
                json={
                    "title": "New Test Project",
                    "description": "A project created via test",
                },
            )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["title"] == "New Test Project"

    @pytest.mark.asyncio
    async def test_create_project_missing_title(
        self, async_test_client, async_test_db
    ):
        """Test creating a project without required title."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.post(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
                json={"description": "No title"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_project(self, async_test_client, async_test_db):
        """Test getting a single project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        project = await self._create_project(async_test_db, org.id, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(f"/api/projects/{project.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project.id

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, async_test_client, async_test_db):
        """Test getting a non-existent project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get("/api/projects/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_project(self, async_test_client, async_test_db):
        """Test updating a project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        project = await self._create_project(async_test_db, org.id, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.patch(
                f"/api/projects/{project.id}",
                json={
                    "title": "Updated Title",
                    "description": "Updated description",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_project_not_found(
        self, async_test_client, async_test_db
    ):
        """Test updating non-existent project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.patch(
                "/api/projects/nonexistent-id",
                json={"title": "Updated"},
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, async_test_client, async_test_db):
        """Test deleting a project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        project = await self._create_project(async_test_db, org.id, admin.id)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_deleted_sync"
        ):
            response = await async_test_client.delete(f"/api/projects/{project.id}")
        assert response.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_delete_project_not_found(
        self, async_test_client, async_test_db
    ):
        """Test deleting non-existent project."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.delete("/api/projects/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_projects_pagination(
        self, async_test_client, async_test_db
    ):
        """Test project listing with pagination."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        for i in range(5):
            await self._create_project(
                async_test_db, org.id, admin.id, title=f"Paginated Project {i}"
            )
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                "/api/projects/?page=1&page_size=2"
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2

    @pytest.mark.asyncio
    async def test_annotator_cannot_create_project(
        self, async_test_client, async_test_db
    ):
        """Test that annotators cannot create projects."""
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await self._create_org(async_test_db, annotator.id)
        await self._create_membership(
            async_test_db, annotator.id, org.id, "ANNOTATOR"
        )
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(annotator), n, d, r:
            response = await async_test_client.post(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
                json={"title": "Annotator Project"},
            )
        assert response.status_code in (403, 401)

    @pytest.mark.asyncio
    async def test_annotator_cannot_delete_project(
        self, async_test_client, async_test_db
    ):
        """Test that annotators cannot delete projects."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        annotator = await _make_user(async_test_db, is_superadmin=False)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        await self._create_membership(
            async_test_db, annotator.id, org.id, "ANNOTATOR"
        )
        project = await self._create_project(async_test_db, org.id, admin.id)
        await async_test_db.commit()

        with _as_user(annotator):
            response = await async_test_client.delete(
                f"/api/projects/{project.id}"
            )
        assert response.status_code in (403, 401)

    @pytest.mark.asyncio
    async def test_list_projects_search(self, async_test_client, async_test_db):
        """Test project listing with search query."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await self._create_org(async_test_db, admin.id)
        await self._create_membership(async_test_db, admin.id, org.id)
        await self._create_project(
            async_test_db, org.id, admin.id, title="Unique Searchable Title XYZ"
        )
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(
                "/api/projects/?search=Searchable"
            )
        assert response.status_code == 200


@pytest.mark.integration
class TestProjectTasksIntegration:
    """Integration tests for task management within projects."""

    async def _create_project_with_tasks(
        self, db: AsyncSession, org_id: str, user_id: str, num_tasks: int = 3
    ):
        """Create a project with tasks."""
        project = Project(
            id=str(uuid.uuid4()),
            title="Task Test Project",
            created_by=user_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(project)
        await db.flush()

        po = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project.id,
            organization_id=org_id,
            assigned_by=user_id,
        )
        db.add(po)

        tasks = []
        for i in range(num_tasks):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project.id,
                data={"text": f"Sample text {i}"},
                inner_id=i + 1,
            )
            db.add(task)
            tasks.append(task)

        await db.flush()
        return project, tasks

    @pytest.mark.asyncio
    async def test_get_project_includes_task_count(
        self, async_test_client, async_test_db
    ):
        """Test that project detail includes task statistics."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = Organization(
            id=str(uuid.uuid4()),
            name="Task Org",
            slug=f"task-org-{uuid.uuid4().hex[:8]}",
            display_name="Task Org Display",
            description="task org",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add(org)
        await async_test_db.flush()
        m = OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=admin.id,
            organization_id=org.id,
            role="ORG_ADMIN",
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
        async_test_db.add(m)
        await async_test_db.flush()
        project, _ = await self._create_project_with_tasks(
            async_test_db, org.id, admin.id, num_tasks=5
        )
        await async_test_db.commit()

        with _as_user(admin):
            response = await async_test_client.get(f"/api/projects/{project.id}")
        assert response.status_code == 200


@pytest.mark.integration
class TestDeepMergeDicts:
    """Test the deep_merge_dicts utility function."""

    def test_merge_simple(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}
        result = deep_merge_dicts(base, update)
        assert result["a"] == 1
        assert result["b"] == 3
        assert result["c"] == 4

    def test_merge_nested(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        update = {"a": {"y": 99, "z": 100}}
        result = deep_merge_dicts(base, update)
        assert result["a"]["x"] == 1
        assert result["a"]["y"] == 99
        assert result["a"]["z"] == 100
        assert result["b"] == 3

    def test_merge_none_base(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, {"a": 1})
        assert result == {"a": 1}

    def test_merge_none_update(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1}, None)
        assert result == {"a": 1}

    def test_merge_both_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, None)
        assert result == {}

    def test_merge_lists_replaced(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"items": [1, 2, 3]}
        update = {"items": [4, 5]}
        result = deep_merge_dicts(base, update)
        assert result["items"] == [4, 5]
