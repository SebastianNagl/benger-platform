"""
Unit tests for routers/tasks.py (global tasks) to increase branch coverage.
Covers list_all_tasks, bulk_assign, bulk_update_status, export_tasks.

The router was migrated to the async DB lane, so these tests seed real rows
via ``async_test_db`` and drive the HTTP surface through ``async_test_client``.
``require_user`` is overridden to return an auth User matching the seeded
actor; where the original tests patched ``get_user_accessible_projects`` to
pin the accessible scope, that patch is preserved (now returning an awaitable).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Project, Task


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


def _accessible(project_ids):
    """Build an async replacement for get_user_accessible_projects."""

    async def _impl(db, user):
        return list(project_ids)

    return _impl


async def _make_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"gt-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="GT User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, creator=None, *, title="GT Project"):
    if creator is None:
        creator = await _make_user(db)
    p = Project(
        id=_uid(),
        title=title,
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    await db.flush()
    return p


async def _make_task(db, project, creator, *, is_labeled=False, assigned_to=None, inner_id=1):
    t = Task(
        id=_uid(),
        project_id=project.id,
        data={"text": "sample"},
        meta={},
        inner_id=inner_id,
        is_labeled=is_labeled,
        assigned_to=assigned_to,
        created_by=creator.id,
        updated_by=creator.id,
    )
    db.add(t)
    await db.flush()
    return t


# ---------------------------------------------------------------------------
# List All Tasks
# ---------------------------------------------------------------------------


class TestListAllTasks:
    @pytest.mark.asyncio
    async def test_empty_results(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.get("/api/data/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_with_project_filter_no_access(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible(["p-2"])
        ):
            resp = await async_test_client.get("/api/data/?project_ids=p-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_with_status_filters(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            for status_filter in ["completed", "incomplete", "in_progress", "all"]:
                resp = await async_test_client.get(f"/api/data/?status={status_filter}")
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_with_search_and_date_filters(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.get(
                "/api/data/?search=test&assigned_to=user-1"
                "&date_from=2025-01-01T00:00:00&date_to=2025-12-31T23:59:59"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_with_sort_options(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.get("/api/data/?sort_by=created_at&sort_order=asc")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_with_invalid_sort_field(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.get("/api/data/?sort_by=nonexistent_field")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_task_with_org_name(self, async_test_client, async_test_db):
        """Happy path: a real task is serialized with project + org enrichment."""
        from models import Organization
        from project_models import ProjectOrganization

        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        org = Organization(
            id=_uid(),
            name="GT Org",
            slug=f"gt-org-{_uid()[:6]}",
            display_name="GT Org",
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add(org)
        await async_test_db.flush()
        async_test_db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=user.id,
            )
        )
        task = await _make_task(async_test_db, project, user)
        await async_test_db.commit()

        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.get("/api/data/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["id"] == task.id
        assert item["project"]["organization"] == "GT Org"
        assert item["annotations_count"] == 0


# ---------------------------------------------------------------------------
# get_user_accessible_projects
# ---------------------------------------------------------------------------


class TestGetUserAccessibleProjects:
    @pytest.mark.asyncio
    async def test_superadmin_gets_all(self, async_test_db):
        from routers.tasks import get_user_accessible_projects

        admin = await _make_user(async_test_db, is_superadmin=True)
        p1 = await _make_project(async_test_db, title="A")
        p2 = await _make_project(async_test_db, title="B")
        await async_test_db.commit()

        auth = AuthUser(
            id=admin.id,
            username=admin.username,
            email=admin.email,
            name=admin.name,
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=admin.created_at,
        )
        result = await get_user_accessible_projects(async_test_db, auth)
        assert p1.id in result
        assert p2.id in result

    @pytest.mark.asyncio
    async def test_regular_user_scoped(self, async_test_db):
        from routers.tasks import get_user_accessible_projects
        from project_models import ProjectMember

        user = await _make_user(async_test_db, is_superadmin=False)
        owner = await _make_user(async_test_db, is_superadmin=True)
        member_proj = await _make_project(async_test_db, title="Member")
        async_test_db.add(
            ProjectMember(
                id=_uid(),
                project_id=member_proj.id,
                user_id=user.id,
                role="ANNOTATOR",
            )
        )
        # A project the user is NOT a member of and not in its org.
        await _make_project(async_test_db, title="Unrelated")
        await async_test_db.commit()

        auth = AuthUser(
            id=user.id,
            username=user.username,
            email=user.email,
            name=user.name,
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=user.created_at,
        )
        result = await get_user_accessible_projects(async_test_db, auth)
        assert isinstance(result, list)
        assert member_proj.id in result


# ---------------------------------------------------------------------------
# Bulk Assign
# ---------------------------------------------------------------------------


class TestBulkAssign:
    @pytest.mark.asyncio
    async def test_no_access_to_some_tasks(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        task = await _make_task(async_test_db, project, user)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.post(
                "/api/data/bulk-assign?user_id=assignee-1",
                json=[task.id, "missing-task"],
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_assign_success(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        assignee = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db)
        task = await _make_task(async_test_db, project, user)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.post(
                f"/api/data/bulk-assign?user_id={assignee.id}",
                json=[task.id],
            )
        assert resp.status_code == 200
        assert "Successfully assigned" in resp.json()["message"]


# ---------------------------------------------------------------------------
# Bulk Update Status
# ---------------------------------------------------------------------------


class TestBulkUpdateStatus:
    @pytest.mark.asyncio
    async def test_no_access_to_some_tasks(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.post(
                "/api/data/bulk-update-status?is_labeled=true",
                json=["t-1"],
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_update_complete(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        task = await _make_task(async_test_db, project, user, is_labeled=False)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.post(
                "/api/data/bulk-update-status?is_labeled=true",
                json=[task.id],
            )
        assert resp.status_code == 200
        assert "completed" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_bulk_update_incomplete(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        task = await _make_task(async_test_db, project, user, is_labeled=True)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.post(
                "/api/data/bulk-update-status?is_labeled=false",
                json=[task.id],
            )
        assert resp.status_code == 200
        assert "incomplete" in resp.json()["message"]


# ---------------------------------------------------------------------------
# Export Tasks
# ---------------------------------------------------------------------------


class TestExportTasks:
    @pytest.mark.asyncio
    async def test_export_json(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, title="Test Project")
        await _make_task(async_test_db, project, user)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.post("/api/data/export?format=json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_export_csv(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        assignee = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, title="Test Project")
        await _make_task(
            async_test_db, project, user, is_labeled=True, assigned_to=assignee.id
        )
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.post("/api/data/export?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_export_with_task_ids(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.tasks.get_user_accessible_projects", _accessible([project.id])
        ):
            resp = await async_test_client.post(
                "/api/data/export?format=json",
                json=["t-1", "t-2"],
            )
        assert resp.status_code == 200
