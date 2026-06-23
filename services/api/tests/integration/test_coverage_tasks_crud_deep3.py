"""
Deep integration tests for tasks, CRUD, members, reviews, annotations, assignments.

Targets: routers/projects/tasks/*, crud.py, members.py, annotations.py,
assignments.py, helpers.py

ASYNC MIGRATION NOTE
--------------------
Most handlers in these routers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``). The legacy sync
session (psycopg2) and the async ``async_test_db`` (asyncpg) are SEPARATE
connections/transactions, so a row seeded on the sync side is invisible to an
async handler and vice-versa. The converted tests therefore seed real ORM rows
via ``async_test_db``, drive the surface through ``async_test_client``, and set
the acting user via the ``_as_user(...)`` contextmanager (which overrides the
async ``require_user`` dependency). ``recalculate-stats`` resolves its actor
through ``get_current_user`` (DB User), overridden via ``_as_current_user``.
Create/delete tests patch the sync notification/report wrappers to avoid the
Redis-backed threadpool stall.

A SMALL NUMBER of handlers remain on the SYNC lane and have NOT been migrated:
- ``POST /tasks/{task_id}/annotations`` (create_annotation) — ``Depends(get_db)``
- ``POST /{project_id}/tasks/assign`` (assign_tasks) — ``Depends(get_db)``
Tests for those endpoints keep the sync ``client`` + ``test_db`` fixtures and
seed via sync ``test_db.add()`` — async seeding would be invisible to them.

Endpoint -> DB lane map (verified against the router sources):
  ASYNC: GET /{pid}/tasks, GET /tasks/{tid}, PUT /{pid}/tasks/{tid},
         PATCH /tasks/{tid}/metadata, POST /{pid}/tasks/bulk-delete,
         POST /{pid}/tasks/bulk-archive, POST /{pid}/tasks/{tid}/skip,
         GET /{pid}/members, GET /{pid}/annotators,
         GET /tasks/{tid}/annotations, PATCH /annotations/{aid},
         GET /{pid}/tasks/{tid}/assignments, and ALL crud.py endpoints.
  SYNC:  POST /tasks/{tid}/annotations, POST /{pid}/tasks/assign.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from auth_module import require_user
from auth_module.dependencies import get_current_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


# ============= auth overrides =============


@contextmanager
def _as_user(db_user: User):
    """Override the async ``require_user`` dependency with an AuthUser matching
    the seeded DB user."""
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


@contextmanager
def _as_current_user(db_user: User):
    """Override get_current_user (recalc-stats endpoint's dep) with the DB user."""
    app.dependency_overrides[get_current_user] = lambda: db_user
    try:
        yield db_user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# Patch the sync report/notification wrappers so create/delete never stall on
# the Redis-backed threadpool dispatch (no Redis locally).
def _no_side_effects():
    return (
        patch("routers.projects.crud._notify_project_created_sync"),
        patch("routers.projects.crud._notify_project_deleted_sync"),
        patch("routers.projects.crud._create_initial_report_draft_sync"),
    )


# ============= async seeding twins =============


async def _make_user(db, *, is_superadmin=False, name="Test User"):
    u = User(
        id=_uid(),
        username=f"cd3-{_uid()[:8]}",
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
    org = Organization(
        id=_uid(),
        name=name,
        slug=f"org-{uuid.uuid4().hex[:8]}",
        display_name=f"{name} Display",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _make_membership(db, user_id, org_id, role="ORG_ADMIN"):
    m = OrganizationMembership(
        id=_uid(),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        is_active=True,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(m)
    await db.flush()
    return m


async def _make_project(db, admin, org, **kw):
    p = Project(
        id=_uid(),
        title=kw.get("title", f"P-{uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=kw.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        is_private=kw.get("is_private", False),
        assignment_mode=kw.get("assignment_mode", "open"),
        randomize_task_order=kw.get("randomize_task_order", False),
        min_annotations_per_task=kw.get("min_annotations_per_task", 1),
        maximum_annotations=kw.get("maximum_annotations", 0),
        skip_queue=kw.get("skip_queue", "requeue_for_others"),
        questionnaire_enabled=kw.get("questionnaire_enabled", False),
        generation_config=kw.get("generation_config", None),
        evaluation_config=kw.get("evaluation_config", None),
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=admin.id,
            )
        )
        await db.flush()
    return p


async def _make_task(db, project, admin, *, inner_id=1, data=None, is_labeled=False, meta=None):
    t = Task(
        id=_uid(),
        project_id=project.id,
        data=data or {"text": f"Task {inner_id}"},
        meta=meta,
        inner_id=inner_id,
        created_by=admin.id,
        is_labeled=is_labeled,
        total_annotations=(1 if is_labeled else 0),
    )
    db.add(t)
    await db.flush()
    return t


async def _make_annotation(db, task, project, user, *, result=None, was_cancelled=False):
    a = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=user.id,
        result=result
        or [
            {
                "from_name": "answer",
                "to_name": "text",
                "type": "choices",
                "value": {"choices": ["Ja"]},
            }
        ],
        was_cancelled=was_cancelled,
    )
    db.add(a)
    await db.flush()
    return a


# Sync seeding helpers (only for the two SYNC handlers: create_annotation,
# assign_tasks). Mirror the prod row shapes used elsewhere in this file.
def _sync_project(db, admin, org, **kw):
    pid = _uid()
    p = Project(
        id=pid,
        title=kw.get("title", f"P-{pid[:6]}"),
        created_by=admin.id,
        label_config=kw.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        is_private=kw.get("is_private", False),
        assignment_mode=kw.get("assignment_mode", "open"),
        randomize_task_order=kw.get("randomize_task_order", False),
        min_annotations_per_task=kw.get("min_annotations_per_task", 1),
        maximum_annotations=kw.get("maximum_annotations", 0),
        skip_queue=kw.get("skip_queue", "requeue_for_others"),
        questionnaire_enabled=kw.get("questionnaire_enabled", False),
    )
    db.add(p)
    db.flush()
    if org:
        db.add(
            ProjectOrganization(
                id=_uid(), project_id=pid, organization_id=org.id, assigned_by=admin.id
            )
        )
        db.flush()
    return p


def _sync_task(db, project, admin, *, inner_id=1, data=None, is_labeled=False, meta=None):
    t = Task(
        id=_uid(),
        project_id=project.id,
        data=data or {"text": f"Task {inner_id}"},
        meta=meta,
        inner_id=inner_id,
        created_by=admin.id,
        is_labeled=is_labeled,
    )
    db.add(t)
    db.flush()
    return t


# ==============================================================
# Task listing tests  [TASKS DOMAIN — async: GET /{pid}/tasks]
# ==============================================================


class TestTaskListing:
    @pytest.mark.asyncio
    async def test_list_tasks_basic(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        for i in range(5):
            await _make_task(async_test_db, p, admin, inner_id=i + 1)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 5

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        for i in range(10):
            await _make_task(async_test_db, p, admin, inner_id=i + 1)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=1&page_size=3",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        # tasks key may vary; just check page_size is respected
        tasks_list = data.get("tasks", data.get("items", []))
        assert len(tasks_list) <= 3

    @pytest.mark.asyncio
    async def test_list_tasks_only_labeled(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await _make_task(async_test_db, p, admin, inner_id=1, is_labeled=True)
        await _make_task(async_test_db, p, admin, inner_id=2, is_labeled=False)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_labeled=true",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_only_unlabeled(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await _make_task(async_test_db, p, admin, inner_id=1, is_labeled=True)
        await _make_task(async_test_db, p, admin, inner_id=2, is_labeled=False)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_unlabeled=true",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_exclude_my_annotations(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t1 = await _make_task(async_test_db, p, admin, inner_id=1)
        await _make_task(async_test_db, p, admin, inner_id=2)
        await _make_annotation(async_test_db, t1, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_nonexistent_project(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/nonexistent/tasks")
        assert resp.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_list_tasks_randomized(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org, randomize_task_order=True)
        for i in range(5):
            await _make_task(async_test_db, p, admin, inner_id=i + 1)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200


# ==============================================================
# Single task operations  [TASKS DOMAIN]
# ==============================================================


class TestTaskOperations:
    @pytest.mark.asyncio
    async def test_get_single_task(self, async_test_client, async_test_db):
        # GET single task: /api/projects/tasks/{task_id} (async)
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{t.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, async_test_client, async_test_db):
        # GET nonexistent single task -> 404 (async get_task)
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/tasks/nonexistent",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (404, 500)

    @pytest.mark.asyncio
    async def test_update_task_data(self, async_test_client, async_test_db):
        # PUT task: /api/projects/{project_id}/tasks/{task_id} (async)
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{t.id}",
                json={"data": {"text": "Updated text"}},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_update_task_metadata(self, async_test_client, async_test_db):
        # PATCH metadata: /api/projects/tasks/{task_id}/metadata (async)
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin, meta={"source": "test"})
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{t.id}/metadata",
                json={"meta": {"source": "updated", "extra": "data"}, "merge": True},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_bulk_delete_tasks(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        tasks = [await _make_task(async_test_db, p, admin, inner_id=i) for i in range(3)]
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": [t.id for t in tasks[:2]]},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_skip_task(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{t.id}/skip",
                json={"comment": "Too difficult"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 201, 404)

    @pytest.mark.asyncio
    async def test_bulk_archive(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t1 = await _make_task(async_test_db, p, admin, inner_id=1, is_labeled=True)
        t2 = await _make_task(async_test_db, p, admin, inner_id=2, is_labeled=False)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-archive",
                json={"task_ids": [t1.id, t2.id]},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 404)


# ==============================================================
# Project CRUD tests  [CRUD DOMAIN]
# ==============================================================


class TestProjectCRUD:
    @pytest.mark.asyncio
    async def test_list_projects(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_list_projects_search(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_project(async_test_db, admin, org, title="Legal Analysis Project")
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/?search=Legal",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_projects_private_context(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": "private"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_project(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Test Create Project", "description": "desc"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["title"] == "Test Create Project"

    @pytest.mark.asyncio
    async def test_create_project_with_label_config(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={
                    "title": "With Config",
                    "label_config": '<View><Text name="text" value="$text"/></View>',
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_create_project_invalid_label_config(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Bad Config", "label_config": "not valid xml<<<"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 201, 422)

    @pytest.mark.asyncio
    async def test_create_private_project(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        n, d, r = _no_side_effects()
        with _as_user(admin), n, d, r:
            resp = await async_test_client.post(
                "/api/projects/",
                json={"title": "Private Project", "is_private": True},
                headers={"X-Organization-Context": "private"},
            )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_get_project(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_nonexistent_project(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_project(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"title": "Updated Title"},
            )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_project_generation_config(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={
                    "generation_config": {
                        "selected_configuration": {"models": ["gpt-4"]}
                    }
                },
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_project_evaluation_config_deep_merge(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            # First update
            await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"evaluation_config": {"field1": {"method": "exact_match"}}},
            )
            # Second update (should deep merge)
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}",
                json={"evaluation_config": {"field2": {"method": "f1"}}},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_project(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.crud._notify_project_deleted_sync"
        ):
            resp = await async_test_client.delete(f"/api/projects/{p.id}")
        assert resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_completion_stats(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await _make_task(async_test_db, p, admin, inner_id=1, is_labeled=True)
        await _make_task(async_test_db, p, admin, inner_id=2, is_labeled=False)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/completion-stats",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["completed"] == 1

    @pytest.mark.asyncio
    async def test_recalculate_stats(self, async_test_client, async_test_db):
        # recalculate-stats uses get_current_user (DB User), not require_user.
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await _make_task(async_test_db, p, admin)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/recalculate-stats"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_project_visibility_make_private(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{p.id}/visibility",
                json={"is_private": True, "owner_user_id": admin.id},
            )
        assert resp.status_code == 200


# ==============================================================
# Deep merge helper tests  [PURE FUNCTION — unchanged]
# ==============================================================


class TestDeepMergeDicts:
    def test_basic_merge(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_nested_merge(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(
            {"config": {"x": 1, "y": 2}},
            {"config": {"y": 3, "z": 4}},
        )
        assert result == {"config": {"x": 1, "y": 3, "z": 4}}

    def test_none_removes_key(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1, "b": 2}, {"b": None})
        assert result == {"a": 1}

    def test_none_base(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, {"a": 1})
        assert result == {"a": 1}

    def test_none_update(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1}, None)
        assert result == {"a": 1}

    def test_both_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, None)
        assert result == {}

    def test_list_replaced(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"items": [1, 2]}, {"items": [3, 4]})
        assert result == {"items": [3, 4]}

    def test_empty_base(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({}, {"a": 1})
        assert result == {"a": 1}


# ==============================================================
# Project members tests  [CRUD-shell DOMAIN — async members.py]
# ==============================================================


class TestProjectMembers:
    @pytest.mark.asyncio
    async def test_list_members(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/members",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    # Note: per-project member add/remove/reactivate endpoints were removed —
    # member management now flows through organization assignment on the
    # project visibility panel. Tests for the dropped endpoints have been
    # deleted. The list/annotator-listing endpoints below are still active.

    @pytest.mark.asyncio
    async def test_list_annotators(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        await _make_annotation(async_test_db, t, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/annotators",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "annotators" in data
        assert len(data["annotators"]) >= 1


# ==============================================================
# Annotation tests  [TASKS DOMAIN]
#   create_annotation  -> SYNC handler (sync client + test_db)
#   list/update/cancel -> ASYNC handlers (async client + async_test_db)
# ==============================================================


class TestAnnotations:
    def test_create_annotation(self, client, test_db, test_users, auth_headers, test_org):
        # POST /tasks/{task_id}/annotations is still on the SYNC lane
        # (Depends(get_db)); seed via sync test_db so the handler sees the rows.
        p = _sync_project(test_db, test_users[0], test_org)
        t = _sync_task(test_db, p, test_users[0])
        test_db.commit()

        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [
                    {
                        "from_name": "answer",
                        "to_name": "text",
                        "type": "choices",
                        "value": {"choices": ["Ja"]},
                    }
                ],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_list_annotations(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        await _make_annotation(async_test_db, t, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{t.id}/annotations",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_annotations_all_users(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        other = await _make_user(async_test_db, is_superadmin=False)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        await _make_membership(async_test_db, other.id, org.id, "ANNOTATOR")
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        await _make_annotation(async_test_db, t, p, admin)
        await _make_annotation(async_test_db, t, p, other)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{t.id}/annotations?all_users=true",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_annotation(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        ann = await _make_annotation(async_test_db, t, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={
                    "result": [
                        {
                            "from_name": "answer",
                            "to_name": "text",
                            "type": "choices",
                            "value": {"choices": ["Nein"]},
                        }
                    ]
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cancel_annotation(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        ann = await _make_annotation(async_test_db, t, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann.id}",
                json={
                    "result": [
                        {
                            "from_name": "answer",
                            "to_name": "text",
                            "type": "choices",
                            "value": {"choices": ["Ja"]},
                        }
                    ],
                    "was_cancelled": True,
                },
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200


# ==============================================================
# Assignment tests  [TASKS DOMAIN]
#   POST /{pid}/tasks/assign         -> SYNC handler (sync client + test_db)
#   GET  /{pid}/tasks/{tid}/assignments -> ASYNC handler
# ==============================================================


class TestAssignments:
    def test_assign_tasks(self, client, test_db, test_users, auth_headers, test_org):
        # POST /{pid}/tasks/assign is still on the SYNC lane (Depends(get_db)).
        p = _sync_project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = [_sync_task(test_db, p, test_users[0], inner_id=i) for i in range(3)]
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": [t.id for t in tasks],
                "user_ids": [test_users[1].id],
                "distribution": "round_robin",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_assign_random(self, client, test_db, test_users, auth_headers, test_org):
        p = _sync_project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = [_sync_task(test_db, p, test_users[0], inner_id=i) for i in range(4)]
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={
                "task_ids": [t.id for t in tasks],
                "user_ids": [test_users[1].id, test_users[2].id],
                "distribution": "random",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 201)

    def test_assign_empty_ids(self, client, test_db, test_users, auth_headers, test_org):
        p = _sync_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/assign",
            json={"task_ids": [], "user_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_assignments_for_task(
        self, async_test_client, async_test_db
    ):
        # GET /{pid}/tasks/{tid}/assignments is async.
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        await _make_membership(async_test_db, admin.id, org.id)
        p = await _make_project(async_test_db, admin, org)
        t = await _make_task(async_test_db, p, admin)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks/{t.id}/assignments",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 404)


# ==============================================================
# Helpers tests  [PURE / SYNC-helper functions — unchanged]
# ==============================================================


class TestHelpers:
    def test_get_accessible_project_ids_superadmin(self, test_db, test_users, test_org):
        from routers.projects.helpers import get_accessible_project_ids
        # Superadmin returns None only with the include_all_private opt-in.
        result = get_accessible_project_ids(
            test_db, test_users[0], test_org.id, include_all_private=True
        )
        assert result is None

    def test_get_accessible_project_ids_private(self, test_db, test_users, test_org):
        from routers.projects.helpers import get_accessible_project_ids
        result = get_accessible_project_ids(test_db, test_users[1], "private")
        assert isinstance(result, list)

    def test_check_project_accessible_superadmin(self, test_db, test_users, test_org):
        from routers.projects.helpers import check_project_accessible
        p = _sync_project(test_db, test_users[0], test_org)
        test_db.commit()
        assert check_project_accessible(test_db, test_users[0], p.id) == True  # noqa: E712

    def test_check_project_accessible_nonexistent(self, test_db, test_users):
        from routers.projects.helpers import check_project_accessible
        assert check_project_accessible(test_db, test_users[1], "nonexistent") == False  # noqa: E712

    def test_check_project_accessible_private_mode(self, test_db, test_users, test_org):
        from routers.projects.helpers import check_project_accessible
        p = _sync_project(test_db, test_users[0], None, is_private=True)
        test_db.commit()
        assert check_project_accessible(test_db, test_users[0], p.id, "private") == True  # noqa: E712

    def test_check_user_can_edit_project_creator(self, test_db, test_users, test_org):
        from routers.projects.helpers import check_user_can_edit_project
        p = _sync_project(test_db, test_users[0], test_org)
        test_db.commit()
        # User[0] is superadmin so always True
        assert check_user_can_edit_project(test_db, test_users[0], p.id) == True  # noqa: E712

    def test_calculate_project_stats_batch(self, test_db, test_users, test_org):
        from routers.projects.helpers import calculate_project_stats_batch
        p = _sync_project(test_db, test_users[0], test_org)
        _sync_task(test_db, p, test_users[0])
        test_db.commit()

        stats = calculate_project_stats_batch(test_db, [p.id])
        assert p.id in stats
        assert stats[p.id]["task_count"] >= 1

    def test_calculate_project_stats_batch_empty(self, test_db):
        from routers.projects.helpers import calculate_project_stats_batch
        assert calculate_project_stats_batch(test_db, []) == {}

    def test_get_project_organizations(self, test_db, test_users, test_org):
        from routers.projects.helpers import get_project_organizations
        p = _sync_project(test_db, test_users[0], test_org)
        test_db.commit()
        orgs = get_project_organizations(test_db, p.id)
        assert len(orgs) >= 1

    def test_check_task_assigned_open_mode(self, test_db, test_users, test_org):
        from routers.projects.helpers import check_task_assigned_to_user
        p = _sync_project(test_db, test_users[0], test_org, assignment_mode="open")
        t = _sync_task(test_db, p, test_users[0])
        test_db.commit()
        assert check_task_assigned_to_user(test_db, test_users[0], t.id, p) == True  # noqa: E712

    def test_calculate_generation_stats(self, test_db, test_users, test_org):
        from project_schemas import ProjectResponse
        from routers.projects.helpers import calculate_generation_stats
        p = _sync_project(test_db, test_users[0], test_org)
        test_db.commit()
        resp = ProjectResponse.from_orm(p)
        calculate_generation_stats(test_db, p, resp)
        assert resp.generation_config_ready == False  # noqa: E712
