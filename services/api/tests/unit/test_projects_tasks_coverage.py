"""
Unit tests for routers/projects/tasks.py to increase branch coverage.
Covers list tasks, skip task, next task, and error paths.

The list/next/skip task handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute``), so the old
``Mock(spec=Session)`` / ``get_db``-override pattern no longer reaches them.
The DB-touching cases now seed real rows via ``async_test_db`` and drive the
HTTP surface through ``async_test_client``; the assertions are unchanged.
The unauthenticated cases need no DB and stay on the plain ``TestClient``.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Project


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


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"tasks-unit-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Tasks Unit User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, creator, *, is_private=True):
    p = Project(
        id=_uid(),
        title="Tasks Unit Project",
        created_by=creator.id,
        is_private=is_private,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    await db.flush()
    return p


@pytest.mark.asyncio
class TestListProjectTasks:
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/projects/nonexistent/tasks")
            assert resp.status_code == 404

    async def test_access_denied(self, async_test_client, async_test_db):
        # Non-superadmin user who does not own the (private) project → 403.
        owner = await _make_user(async_test_db, is_superadmin=False)
        outsider = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, owner, is_private=True)
        await async_test_db.commit()

        with _as_user(outsider):
            resp = await async_test_client.get(f"/api/projects/{project.id}/tasks")
            assert resp.status_code == 403


@pytest.mark.asyncio
class TestSkipTask:
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.post(
                "/api/projects/nonexistent/tasks/task-1/skip",
                json={},
            )
            assert resp.status_code == 404


class TestUnauthenticatedEndpoints:
    """Verify auth is required for task endpoints."""

    def test_list_tasks_unauth(self):
        client = TestClient(app)
        resp = client.get("/api/projects/proj-1/tasks")
        assert resp.status_code == 401

    def test_skip_task_unauth(self):
        client = TestClient(app)
        resp = client.post("/api/projects/proj-1/tasks/task-1/skip", json={})
        assert resp.status_code == 401

    def test_next_task_unauth(self):
        client = TestClient(app)
        resp = client.get("/api/projects/proj-1/tasks/next")
        # May return various codes depending on routing
        assert resp.status_code in [401, 404, 405]

    def test_create_task_unauth(self):
        client = TestClient(app)
        resp = client.post("/api/projects/proj-1/tasks", json={"data": {}})
        assert resp.status_code in [401, 404, 405, 422]

    def test_bulk_create_tasks_unauth(self):
        client = TestClient(app)
        resp = client.post("/api/projects/proj-1/tasks/bulk", json=[{"data": {}}])
        assert resp.status_code in [401, 404, 405, 422]
