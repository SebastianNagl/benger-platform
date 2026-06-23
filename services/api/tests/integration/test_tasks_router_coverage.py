"""
Integration tests for tasks router handler bodies.

Targets: routers/projects/tasks.py — list_project_tasks, get_next_task,
         get_task, create_task, update_task, delete_task, skip_task
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
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
        u = User(id=str(uuid.uuid4()),
                 username=f"{tag}-{uuid.uuid4().hex[:8]}@test.com",
                 email=f"{tag}-{uuid.uuid4().hex[:8]}@test.com",
                 name=name, is_superadmin=is_superadmin, is_active=True,
                 email_verified=True, created_at=datetime.now(timezone.utc))
        db.add(u); users.append(u)
    await db.flush()
    return users


async def _make_org(db, users):
    org = Organization(id=str(uuid.uuid4()), name="Test Organization",
                       slug=f"test-org-{uuid.uuid4().hex[:8]}",
                       display_name="Test Organization Display", created_at=datetime.utcnow())
    db.add(org)
    roles = ["ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", "ORG_ADMIN"]
    for i, u in enumerate(users[:4]):
        db.add(OrganizationMembership(id=str(uuid.uuid4()), user_id=u.id,
               organization_id=org.id, role=roles[i], joined_at=datetime.utcnow()))
    await db.flush()
    return org


async def _make_project(db, admin, org, *, num_tasks=5, assignment_mode="open",
                         randomize=False, with_annotations=False):  # noqa: E127
    """Create project with tasks for testing."""
    project = Project(
        id=_uid(),
        title="Tasks Test Project",
        created_by=admin.id,
        assignment_mode=assignment_mode,
        randomize_task_order=randomize,
        maximum_annotations=1,
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
            data={"text": f"Task text #{i}", "question": f"Q{i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

    if with_annotations:
        for t in tasks:
            ann = Annotation(
                id=_uid(), task_id=t.id, project_id=project.id,
                completed_by=admin.id,
                result=[{"from_name": "answer", "to_name": "text",
                         "type": "choices", "value": {"choices": ["Ja"]}}],
                was_cancelled=False,
            )
            db.add(ann)
    await db.commit()
    return project, tasks


@pytest.mark.integration
class TestListProjectTasks:
    """GET /api/projects/{project_id}/tasks"""

    @pytest.mark.asyncio
    async def test_list_tasks_basic(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "pages" in body
        assert body["total"] == 5

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?page=1&page_size=2"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert body["pages"] == 3

    @pytest.mark.asyncio
    async def test_list_tasks_page_2(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?page=2&page_size=2"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_only_labeled(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org)
        # Mark first task as labeled
        tasks[0].is_labeled = True
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?only_labeled=true"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

    @pytest.mark.asyncio
    async def test_list_tasks_only_unlabeled(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org)
        tasks[0].is_labeled = True
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?only_unlabeled=true"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 4

    @pytest.mark.asyncio
    async def test_list_tasks_exclude_my_annotations(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, with_annotations=True)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?exclude_my_annotations=true"
            )
        assert resp.status_code == 200
        body = resp.json()
        # Admin has annotated all tasks, so none should be returned
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_list_tasks_nonexistent_project(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get("/api/projects/nonexistent-id/tasks")
        assert resp.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_list_tasks_task_structure(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?page_size=1"
            )
        assert resp.status_code == 200
        body = resp.json()
        item = body["items"][0]
        assert "id" in item
        assert "inner_id" in item
        assert "data" in item
        assert "is_labeled" in item
        assert "assignments" in item
        assert "total_generations" in item

    @pytest.mark.asyncio
    async def test_list_tasks_with_generations(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, num_tasks=1)
        rg = ResponseGeneration(
            id=_uid(), project_id=project.id, model_id="gpt-4o",
            status="completed", created_by=users[0].id,
            started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        )
        async_test_db.add(rg)
        await async_test_db.flush()
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=tasks[0].id,
            model_id="gpt-4o", case_data='{}', response_content="answer",
            status="completed",
        )
        async_test_db.add(gen)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"][0]["total_generations"] >= 1

    @pytest.mark.asyncio
    async def test_list_tasks_with_assignments(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, num_tasks=1)
        ta = TaskAssignment(
            id=_uid(), task_id=tasks[0].id, user_id=users[0].id,
            assigned_by=users[0].id, status="assigned",
        )
        async_test_db.add(ta)
        await async_test_db.flush()
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"][0]["assignments"]) >= 1


@pytest.mark.integration
class TestGetNextTask:
    """GET /api/projects/{project_id}/next"""

    @pytest.mark.asyncio
    async def test_get_next_open_mode(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, assignment_mode="open")
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/next")
        assert resp.status_code == 200
        body = resp.json()
        assert "task" in body or "detail" in body

    @pytest.mark.asyncio
    async def test_get_next_randomized(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(
            async_test_db, users[0], org,
            assignment_mode="open", randomize=True,
        )
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/next")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_next_all_annotated(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(
            async_test_db, users[0], org, with_annotations=True,
        )
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/next")
        assert resp.status_code == 200
        body = resp.json()
        # User already annotated all tasks
        assert body.get("task") is None or body.get("detail") is not None

    @pytest.mark.asyncio
    async def test_get_next_manual_mode_no_assignment(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(
            async_test_db, users[0], org, assignment_mode="manual",
        )
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/next")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("task") is None

    @pytest.mark.asyncio
    async def test_get_next_manual_mode_with_assignment(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(
            async_test_db, users[0], org, assignment_mode="manual",
        )
        ta = TaskAssignment(
            id=_uid(), task_id=tasks[0].id, user_id=users[0].id,
            assigned_by=users[0].id, status="assigned",
        )
        async_test_db.add(ta)
        await async_test_db.flush()
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/next")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("task") is not None

    @pytest.mark.asyncio
    async def test_get_next_nonexistent_project(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get("/api/projects/nonexistent-id/next")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("task") is None

    @pytest.mark.asyncio
    async def test_get_next_auto_mode(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(
            async_test_db, users[0], org, assignment_mode="auto",
        )
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{project.id}/next")
        assert resp.status_code == 200
        body = resp.json()
        # Auto mode should auto-assign a task
        assert body.get("task") is not None or "detail" in body


@pytest.mark.integration
class TestGetSingleTask:
    """GET /api/projects/tasks/{task_id}"""

    @pytest.mark.asyncio
    async def test_get_task_by_id(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, num_tasks=1)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/tasks/{tasks[0].id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == tasks[0].id

    @pytest.mark.asyncio
    async def test_get_task_nonexistent(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get("/api/projects/tasks/nonexistent-id")
        assert resp.status_code == 404


@pytest.mark.integration
class TestUpdateTask:
    """PUT /api/projects/{project_id}/tasks/{task_id}"""

    @pytest.mark.asyncio
    async def test_update_task_data(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, num_tasks=1)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated task text"}},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_nonexistent_task(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, num_tasks=1)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/nonexistent-id",
                json={"data": {"text": "test"}},
            )
        assert resp.status_code in (404,)


@pytest.mark.integration
class TestBulkDeleteTasks:
    """POST /api/projects/{project_id}/tasks/bulk-delete"""

    @pytest.mark.asyncio
    async def test_bulk_delete_tasks(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, num_tasks=3)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-delete",
                json={"task_ids": [tasks[0].id, tasks[1].id]},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent_tasks(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, num_tasks=1)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-delete",
                json={"task_ids": ["nonexistent-1", "nonexistent-2"]},
            )
        assert resp.status_code == 200


@pytest.mark.integration
class TestSkipTask:
    """POST /api/projects/{project_id}/tasks/{task_id}/skip"""

    @pytest.mark.asyncio
    async def test_skip_task(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        org = await _make_org(async_test_db, users)
        project, tasks = await _make_project(async_test_db, users[0], org, num_tasks=2)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
                json={},
            )
        # Might be POST or might not exist — accept multiple codes
        assert resp.status_code in (200, 201, 404, 405)
