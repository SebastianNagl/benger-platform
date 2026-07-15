"""Behavioral tests for the task-metadata update endpoints.

Target: ``services/api/routers/projects/tasks/metadata_ops.py`` — the single-
and bulk-task metadata PATCH endpoints (Label-Studio-aligned meta merge/replace).
Drives the real async HTTP stack with seeded rows and asserts on the response
and the persisted ``Task.meta``.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Project, Task

BASE = "/api/projects"


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id, username=db_user.username, email=db_user.email, name=db_user.name,
        is_superadmin=db_user.is_superadmin, is_active=True, email_verified=True,
        created_at=getattr(db_user, "created_at", None) or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _mk_user(db, *, superadmin=True) -> User:
    u = User(
        id=_uid(), username=f"u-{_uid()[:8]}", email=f"{_uid()[:8]}@e.com", name="U",
        is_superadmin=superadmin, is_active=True, email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _mk_project(db, owner) -> Project:
    p = Project(id=_uid(), title="P", created_by=owner.id, is_private=True)
    db.add(p)
    await db.flush()
    return p


async def _mk_task(db, project, *, meta=None, inner_id=1) -> Task:
    t = Task(id=_uid(), project_id=project.id, data={"x": "y"}, inner_id=inner_id, meta=meta)
    db.add(t)
    await db.flush()
    return t


async def _reload_meta(db, task_id):
    row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()
    return row.meta


@pytest.mark.integration
class TestSingleMetadata:
    @pytest.mark.asyncio
    async def test_merge_into_existing(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t = await _mk_task(async_test_db, p, meta={"a": 1, "keep": True})
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.patch(
                f"{BASE}/tasks/{t.id}/metadata", json={"a": 2, "b": "new"}
            )
        assert r.status_code == 200, r.text
        assert r.json()["meta"] == {"a": 2, "keep": True, "b": "new"}
        assert await _reload_meta(async_test_db, t.id) == {"a": 2, "keep": True, "b": "new"}

    @pytest.mark.asyncio
    async def test_replace_when_merge_false(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t = await _mk_task(async_test_db, p, meta={"old": "gone"})
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.patch(
                f"{BASE}/tasks/{t.id}/metadata?merge=false", json={"only": "this"}
            )
        assert r.status_code == 200, r.text
        assert r.json()["meta"] == {"only": "this"}

    @pytest.mark.asyncio
    async def test_merge_when_meta_is_null(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t = await _mk_task(async_test_db, p, meta=None)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.patch(
                f"{BASE}/tasks/{t.id}/metadata", json={"tags": ["bgb"]}
            )
        assert r.status_code == 200, r.text
        assert r.json()["meta"] == {"tags": ["bgb"]}

    @pytest.mark.asyncio
    async def test_task_404(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.patch(
                f"{BASE}/tasks/missing-{_uid()}/metadata", json={"a": 1}
            )
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        outsider = await _mk_user(async_test_db, superadmin=False)
        p = await _mk_project(async_test_db, owner)
        t = await _mk_task(async_test_db, p)
        await async_test_db.commit()
        with _as_user(outsider):
            r = await async_test_client.patch(
                f"{BASE}/tasks/{t.id}/metadata", json={"a": 1}
            )
        assert r.status_code == 403, r.text


@pytest.mark.integration
class TestBulkMetadata:
    @pytest.mark.asyncio
    async def test_bulk_merge(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t1 = await _mk_task(async_test_db, p, meta={"a": 1}, inner_id=1)
        t2 = await _mk_task(async_test_db, p, meta=None, inner_id=2)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.patch(
                f"{BASE}/tasks/bulk-metadata",
                json={"task_ids": [t1.id, t2.id], "metadata": {"reviewed": True}},
            )
        assert r.status_code == 200, r.text
        assert r.json()["updated_count"] == 2
        assert await _reload_meta(async_test_db, t1.id) == {"a": 1, "reviewed": True}
        assert await _reload_meta(async_test_db, t2.id) == {"reviewed": True}

    @pytest.mark.asyncio
    async def test_bulk_replace(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        t1 = await _mk_task(async_test_db, p, meta={"old": 1}, inner_id=1)
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.patch(
                f"{BASE}/tasks/bulk-metadata?merge=false",
                json={"task_ids": [t1.id], "metadata": {"fresh": "v"}},
            )
        assert r.status_code == 200, r.text
        assert await _reload_meta(async_test_db, t1.id) == {"fresh": "v"}

    @pytest.mark.asyncio
    async def test_bulk_no_tasks_found_404(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        await async_test_db.commit()
        with _as_user(owner):
            r = await async_test_client.patch(
                f"{BASE}/tasks/bulk-metadata",
                json={"task_ids": [f"missing-{_uid()}"], "metadata": {"a": 1}},
            )
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_bulk_access_denied_403(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        outsider = await _mk_user(async_test_db, superadmin=False)
        p = await _mk_project(async_test_db, owner)
        t = await _mk_task(async_test_db, p)
        await async_test_db.commit()
        with _as_user(outsider):
            r = await async_test_client.patch(
                f"{BASE}/tasks/bulk-metadata",
                json={"task_ids": [t.id], "metadata": {"a": 1}},
            )
        assert r.status_code == 403, r.text
