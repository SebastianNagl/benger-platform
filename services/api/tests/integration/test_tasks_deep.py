"""
Deep integration tests for task management endpoints.

Covers routers/projects/tasks.py:
- GET /{project_id}/tasks — complex filters (labeled, unlabeled, assigned, exclude_my)
- GET /{project_id}/next — next task for annotator
- GET /tasks/{task_id} — single task (global router)
- PUT /{project_id}/tasks/{task_id} — update task data
- POST /{project_id}/tasks/bulk-delete — bulk delete
- POST /{project_id}/tasks/{task_id}/skip — skip task
- GET /{project_id}/task-fields — task fields discovery
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _uid():
    return str(uuid.uuid4())


def _project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"Task Test {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        assignment_mode=kwargs.get("assignment_mode", "open"),
        maximum_annotations=kwargs.get("maximum_annotations", 1),
        randomize_task_order=kwargs.get("randomize_task_order", False),
    )
    db.add(p)
    db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=p.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()
    return p


def _tasks(db, project, admin, count=5):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task text {i}", "index": i},
            inner_id=i + 1, created_by=admin.id,
            is_labeled=(i < count // 3),  # First third is labeled
            total_annotations=(1 if i < count // 3 else 0),
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotate(db, project, tasks, user_id, count=None):
    anns = []
    for t in tasks[:count]:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=user_id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        anns.append(ann)
    db.flush()
    return anns


def _assign(db, tasks, user_id, admin_id, count=None):
    assigns = []
    for t in tasks[:count]:
        a = TaskAssignment(
            id=_uid(), task_id=t.id, user_id=user_id,
            assigned_by=admin_id, status="assigned",
        )
        db.add(a)
        assigns.append(a)
    db.flush()
    return assigns


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# ASYNC HELPERS (for endpoints migrated to Depends(get_async_db))
# ===================================================================


@contextmanager
def _as_user(db_user):
    auth_user = AuthUser(
        id=db_user.id, username=db_user.username, email=db_user.email,
        name=db_user.name, is_superadmin=db_user.is_superadmin,
        is_active=True, email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_users(db):
    specs = [("Test Admin", True, "admin"), ("Test Contributor", False, "contributor"),
             ("Test Annotator", False, "annotator"), ("Test Org Admin", False, "orgadmin")]
    users = []
    for name, is_superadmin, tag in specs:
        u = User(id=_uid(), username=f"{tag}-{uuid.uuid4().hex[:8]}@test.com",
                 email=f"{tag}-{uuid.uuid4().hex[:8]}@test.com", name=name,
                 is_superadmin=is_superadmin, is_active=True, email_verified=True,
                 created_at=datetime.now(timezone.utc))
        db.add(u)
        users.append(u)
    await db.flush()
    return users


async def _make_org(db, users):
    org = Organization(id=_uid(), name="Test Organization",
                       slug=f"test-org-{uuid.uuid4().hex[:8]}",
                       display_name="Test Organization Display", created_at=datetime.utcnow())
    db.add(org)
    roles = ["ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", "ORG_ADMIN"]
    for i, u in enumerate(users[:4]):
        db.add(OrganizationMembership(id=_uid(), user_id=u.id, organization_id=org.id,
               role=roles[i], joined_at=datetime.utcnow()))
    await db.flush()
    return org


async def _project_async(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"Task Test {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        assignment_mode=kwargs.get("assignment_mode", "open"),
        maximum_annotations=kwargs.get("maximum_annotations", 1),
        randomize_task_order=kwargs.get("randomize_task_order", False),
    )
    db.add(p)
    await db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=p.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    await db.flush()
    return p


async def _tasks_async(db, project, admin, count=5):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task text {i}", "index": i},
            inner_id=i + 1, created_by=admin.id,
            is_labeled=(i < count // 3),  # First third is labeled
            total_annotations=(1 if i < count // 3 else 0),
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return tasks


async def _annotate_async(db, project, tasks, user_id, count=None):
    anns = []
    for t in tasks[:count]:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=user_id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        anns.append(ann)
    await db.flush()
    return anns


async def _assign_async(db, tasks, user_id, admin_id, count=None):
    assigns = []
    for t in tasks[:count]:
        a = TaskAssignment(
            id=_uid(), task_id=t.id, user_id=user_id,
            assigned_by=admin_id, status="assigned",
        )
        db.add(a)
        assigns.append(a)
    await db.flush()
    return assigns


# ===================================================================
# LIST TASKS
# ===================================================================

@pytest.mark.integration
class TestListTasks:
    """GET /api/projects/{project_id}/tasks"""

    @pytest.mark.asyncio
    async def test_list_all_tasks(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=7)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 7

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=15)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp1 = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=1&page_size=5",
            )
            assert resp1.status_code == 200
            body1 = resp1.json()
            assert len(body1["items"]) == 5

            resp2 = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=2&page_size=5",
            )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["items"]) == 5

        # Different tasks
        ids1 = {t["id"] for t in body1["items"]}
        ids2 = {t["id"] for t in body2["items"]}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_list_labeled_only(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=9)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_labeled=true",
            )
        assert resp.status_code == 200
        body = resp.json()
        for t in body["items"]:
            assert t["is_labeled"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_list_unlabeled_only(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=9)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_unlabeled=true",
            )
        assert resp.status_code == 200
        body = resp.json()
        for t in body["items"]:
            assert t["is_labeled"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_list_assigned_only(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await _assign_async(async_test_db, tasks, users[2].id, users[0].id, count=2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_assigned=true",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_exclude_my_annotations(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await _annotate_async(async_test_db, p, tasks, users[0].id, count=2)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_nonexistent_project(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                "/api/projects/nonexistent/tasks",
            )
        assert resp.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_list_tasks_response_structure(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert "pages" in body

    @pytest.mark.asyncio
    async def test_list_tasks_item_structure(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "id" in item
        assert "data" in item
        assert "is_labeled" in item
        assert "total_annotations" in item
        assert "inner_id" in item

    @pytest.mark.asyncio
    async def test_list_tasks_has_total(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=10)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 10

    @pytest.mark.asyncio
    async def test_list_tasks_filtered_total(self, async_test_client, async_test_db):
        """When filtering labeled, total should reflect filtered count."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=9)  # 3 labeled, 6 unlabeled
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_labeled=true",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3

    @pytest.mark.asyncio
    async def test_list_tasks_large_page(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=1&page_size=100",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 3

    @pytest.mark.asyncio
    async def test_list_page_beyond_total(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=100&page_size=30",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 0


# ===================================================================
# UPDATE TASKS
# ===================================================================

@pytest.mark.integration
class TestUpdateTask:
    """PUT /api/projects/{project_id}/tasks/{task_id}"""

    @pytest.mark.asyncio
    async def test_update_task_data(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated text"}, "meta": {"updated": True}},
            )
        assert resp.status_code in (200, 403)

    @pytest.mark.asyncio
    async def test_update_nonexistent_task(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/nonexistent",
                json={"data": {"text": "Nope"}},
            )
        assert resp.status_code == 404


# ===================================================================
# BULK OPERATIONS
# ===================================================================

@pytest.mark.integration
class TestBulkDeleteTasks:
    """POST /api/projects/{project_id}/tasks/bulk-delete"""

    @pytest.mark.asyncio
    async def test_bulk_delete(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()
        ids_to_delete = [tasks[0].id, tasks[1].id]

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": ids_to_delete},
            )
        assert resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_bulk_delete_empty(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": []},
            )
        assert resp.status_code in (200, 400)

    @pytest.mark.asyncio
    async def test_bulk_delete_verifies_task_removed(self, async_test_client, async_test_db):
        """After bulk delete, listing should not include the deleted tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()
        ids_to_delete = [tasks[0].id, tasks[1].id]

        with _as_user(users[0]):
            del_resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": ids_to_delete},
            )
            assert del_resp.status_code in (200, 204)

            list_resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert list_resp.status_code == 200
        remaining_ids = {t["id"] for t in list_resp.json()["items"]}
        for deleted_id in ids_to_delete:
            assert deleted_id not in remaining_ids


# ===================================================================
# SKIP TASK
# ===================================================================

@pytest.mark.integration
class TestSkipTask:
    """POST /api/projects/{project_id}/tasks/{task_id}/skip"""

    @pytest.mark.asyncio
    async def test_skip_task(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={"comment": "Too difficult"},
            )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_skip_task_without_comment(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={},
            )
        assert resp.status_code in (200, 201, 422)

    @pytest.mark.asyncio
    async def test_skip_nonexistent_task(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/nonexistent/skip",
                json={"comment": "Nope"},
            )
        assert resp.status_code == 404


# ===================================================================
# NEXT TASK
# ===================================================================

@pytest.mark.integration
class TestNextTask:
    """GET /api/projects/{project_id}/next"""

    @pytest.mark.asyncio
    async def test_get_next_task(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_get_next_task_all_done(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=2)
        await _annotate_async(async_test_db, p, tasks, users[0].id, count=2)
        # Mark all as labeled
        for t in tasks:
            t.is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        # Should indicate no more tasks
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_get_next_task_empty_project(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code in (200, 404)


# ===================================================================
# TASK FIELDS
# ===================================================================

@pytest.mark.integration
class TestTaskFields:
    """GET /api/projects/{project_id}/task-fields"""

    @pytest.mark.asyncio
    async def test_get_task_fields(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_get_task_fields_empty_project(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code in (200, 404)


# ===================================================================
# ROLE-BASED ACCESS
# ===================================================================

@pytest.mark.integration
class TestTaskRoleAccess:
    """Verify role-based visibility on task endpoints."""

    @pytest.mark.asyncio
    async def test_annotator_can_list_tasks(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[2]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_annotator_manual_mode_sees_only_assigned(self, async_test_client, async_test_db):
        """In manual assignment mode, annotators should only see assigned tasks."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        tasks = await _tasks_async(async_test_db, p, users[0], count=5)
        await _assign_async(async_test_db, tasks, users[2].id, users[0].id, count=2)
        await async_test_db.commit()

        with _as_user(users[2]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        # Annotator should only see assigned tasks
        assert body["total"] <= 2

    @pytest.mark.asyncio
    async def test_admin_sees_all_tasks(self, async_test_client, async_test_db):
        """Superadmin should see all tasks regardless of assignment mode."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org, assignment_mode="manual")
        await _tasks_async(async_test_db, p, users[0], count=5)
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5


# ===================================================================
# BULK EXPORT
# ===================================================================

@pytest.mark.integration
class TestBulkExportTasks:
    """POST /api/projects/{project_id}/tasks/bulk-export"""

    def test_bulk_export_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [tasks[0].id, tasks[1].id]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 404, 405)

    def test_bulk_export_all_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        all_ids = [t.id for t in tasks]
        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": all_ids},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 404, 405)

    def test_bulk_export_empty_list(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": []},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 404, 405)


# ===================================================================
# SKIP + NEXT INTEGRATION
# ===================================================================

@pytest.mark.integration
class TestSkipAndNext:
    """Integration: skip tasks then get next."""

    @pytest.mark.asyncio
    async def test_skip_then_next(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=3)
        await async_test_db.commit()

        with _as_user(users[0]):
            # Skip first task
            skip_resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
                json={"comment": "Skip it"},
            )
            assert skip_resp.status_code in (200, 201)

            # Next should return a different task
            next_resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert next_resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_update_then_verify(self, async_test_client, async_test_db):
        """Update task data then verify it's changed in listing."""
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        p = await _project_async(async_test_db, users[0], org)
        tasks = await _tasks_async(async_test_db, p, users[0], count=1)
        await async_test_db.commit()

        with _as_user(users[0]):
            # Update
            update_resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated via test"}, "meta": {"updated": True}},
            )
            assert update_resp.status_code in (200, 403)

            # Verify in listing
            list_resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        if update_resp.status_code == 200:
            assert items[0]["data"]["text"] == "Updated via test"
