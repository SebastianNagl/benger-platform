"""
Integration tests for task operations (bulk-export, bulk-archive, metadata,
task-fields, skip).

Targets: routers/projects/tasks/ — bulk_export_tasks, bulk_archive_tasks,
         update_task_metadata, bulk_update_metadata, get_task_fields, skip_task

MIXED async/sync file: ``bulk_export_tasks`` is still a sync ``def`` handler on
``Depends(get_db)`` so its tests keep the sync ``client`` + ``test_db``
fixtures. Every other handler here was migrated to the async DB lane
(``Depends(get_async_db)``), so those tests seed rows via ``async_test_db`` and
drive the HTTP surface through ``async_test_client``, overriding ``require_user``
to the acting user (the sync auth dependency can't see the async test
transaction).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import (
    Project,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Sync seeding (used only by the still-sync bulk-export handler tests).
# ---------------------------------------------------------------------------


def _make_project(db, admin, org, *, num_tasks=5):
    """Create project with tasks (sync)."""
    project = Project(
        id=_uid(),
        title="Task Ops Test",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task #{i}", "category": f"cat-{i % 3}",
                  "nested": {"key": f"val-{i}"}},
            meta={"source": "test", "batch": i % 2},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.commit()
    return project, tasks


# ---------------------------------------------------------------------------
# Async auth override + seeding (used by the migrated handlers).
# ---------------------------------------------------------------------------


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


async def _make_admin(db) -> User:
    u = User(
        id=_uid(),
        username=f"admin-{_uid()[:8]}@test.com",
        email=f"admin-{_uid()[:8]}@test.com",
        name="Test Admin",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, admin) -> Organization:
    org = Organization(
        id=_uid(),
        name="Test Organization",
        slug=f"test-org-{_uid()[:8]}",
        display_name="Test Organization Display",
        description="A test organization for testing",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=admin.id,
            organization_id=org.id,
            role=OrganizationRole.ORG_ADMIN,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return org


async def _make_project_async(db, admin, org, *, num_tasks=5):
    project = Project(
        id=_uid(),
        title="Task Ops Test",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    await db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    await db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task #{i}", "category": f"cat-{i % 3}",
                  "nested": {"key": f"val-{i}"}},
            meta={"source": "test", "batch": i % 2},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.commit()
    return project, tasks


@pytest_asyncio.fixture(scope="function")
async def admin_org(async_test_db):
    """Seed a superadmin + org (with membership) once per test."""
    admin = await _make_admin(async_test_db)
    org = await _make_org(async_test_db, admin)
    await async_test_db.commit()
    return admin, org


def _ctx(org):
    return {"X-Organization-Context": org.id}


@pytest.mark.integration
class TestBulkExportTasks:
    """POST /api/projects/{project_id}/tasks/bulk-export

    ``bulk_export_tasks`` is still a sync ``def`` handler on ``Depends(get_db)``,
    so these tests keep the sync ``client`` + ``test_db`` fixtures.
    """

    def test_bulk_export_json(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks[:3]], "format": "json"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_bulk_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks[:2]], "format": "csv"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_bulk_export_all_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_bulk_export_empty_ids(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400)


@pytest.mark.integration
class TestBulkArchiveTasks:
    """POST /api/projects/{project_id}/tasks/bulk-archive"""

    @pytest.mark.asyncio
    async def test_bulk_archive(self, async_test_client, async_test_db, admin_org):
        admin, org = admin_org
        project, tasks = await _make_project_async(
            async_test_db, admin, org, num_tasks=3
        )
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-archive",
                json={"task_ids": [tasks[0].id]},
                headers=_ctx(org),
            )
        assert resp.status_code in (200, 400, 404)


@pytest.mark.integration
class TestTaskMetadata:
    """PATCH /api/projects/tasks/{task_id}/metadata"""

    @pytest.mark.asyncio
    async def test_update_single_task_metadata(
        self, async_test_client, async_test_db, admin_org
    ):
        admin, org = admin_org
        project, tasks = await _make_project_async(
            async_test_db, admin, org, num_tasks=1
        )
        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{tasks[0].id}/metadata",
                json={"meta": {"source": "updated", "extra": True}},
                headers=_ctx(org),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_nonexistent_task_metadata(
        self, async_test_client, async_test_db, admin_org
    ):
        admin, org = admin_org
        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/tasks/nonexistent-id/metadata",
                json={"meta": {"key": "val"}},
                headers=_ctx(org),
            )
        assert resp.status_code == 404


@pytest.mark.integration
class TestBulkMetadata:
    """PATCH /api/projects/tasks/bulk-metadata"""

    @pytest.mark.asyncio
    async def test_bulk_update_metadata(
        self, async_test_client, async_test_db, admin_org
    ):
        admin, org = admin_org
        project, tasks = await _make_project_async(
            async_test_db, admin, org, num_tasks=3
        )
        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata",
                json={
                    "task_ids": [tasks[0].id, tasks[1].id],
                    "metadata": {"batch": "new-batch"},
                },
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 2


@pytest.mark.integration
class TestGetTaskFields:
    """GET /api/projects/{project_id}/task-fields"""

    @pytest.mark.asyncio
    async def test_task_fields_basic(self, async_test_client, async_test_db, admin_org):
        admin, org = admin_org
        project, tasks = await _make_project_async(async_test_db, admin, org)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/task-fields",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        # Should return field names from task data
        assert isinstance(body, (list, dict))

    @pytest.mark.asyncio
    async def test_task_fields_empty_project(
        self, async_test_client, async_test_db, admin_org
    ):
        admin, org = admin_org
        project, _ = await _make_project_async(async_test_db, admin, org, num_tasks=0)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/task-fields",
                headers=_ctx(org),
            )
        assert resp.status_code == 200


@pytest.mark.integration
class TestSkipTask:
    """POST /api/projects/{project_id}/tasks/{task_id}/skip"""

    @pytest.mark.asyncio
    async def test_skip_task(self, async_test_client, async_test_db, admin_org):
        admin, org = admin_org
        project, tasks = await _make_project_async(
            async_test_db, admin, org, num_tasks=3
        )
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
                json={},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "skipped" in body or "status" in body or "task_id" in body

    @pytest.mark.asyncio
    async def test_skip_nonexistent_task(
        self, async_test_client, async_test_db, admin_org
    ):
        admin, org = admin_org
        project, tasks = await _make_project_async(
            async_test_db, admin, org, num_tasks=1
        )
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/nonexistent-id/skip",
                json={},
                headers=_ctx(org),
            )
        assert resp.status_code in (404,)

    @pytest.mark.asyncio
    async def test_skip_task_with_comment(
        self, async_test_client, async_test_db, admin_org
    ):
        admin, org = admin_org
        project, tasks = await _make_project_async(
            async_test_db, admin, org, num_tasks=3
        )
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{tasks[1].id}/skip",
                json={"comment": "Not relevant"},
                headers=_ctx(org),
            )
        assert resp.status_code in (200, 422)
