"""
Coverage boost tests for task management endpoints.

Targets specific branches in routers/projects/tasks/*:
- list_project_tasks with various filters
- get_task_detail (GET /tasks/{task_id})
- update task (PUT /{project_id}/tasks/{task_id})
- bulk-delete / bulk-export / bulk-archive
- get_next_task with various conditions
- skip_task
- task-fields

The list/get/update/metadata/bulk-delete/bulk-archive/skip/next/task-fields
handlers were migrated to the async DB lane (``async def`` +
``db: AsyncSession = Depends(get_async_db)`` + ``await db.execute(select(...))``),
so the old sync ``client`` + ``test_db`` + ``auth_headers`` pattern no longer
reaches them: a row committed in the sync ``test_db`` transaction is invisible
to the async handler's ``async_test_db`` transaction. These now seed real rows
via ``async_test_db`` and drive the surface through ``async_test_client`` inside
``_as_user(acting_user)``; the asserted status codes are unchanged.

``bulk_export_tasks`` (export.py) stays on the SYNC lane — its test keeps the
sync ``client`` + ``test_db`` fixtures.
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


async def _make_users(db):
    """Create 4 permission-level users mirroring the sync ``test_users`` layout:
    [0] admin (superadmin), [1] contributor, [2] annotator, [3] org_admin.
    """
    specs = [
        ("Test Admin", True, "admin"),
        ("Test Contributor", False, "contributor"),
        ("Test Annotator", False, "annotator"),
        ("Test Org Admin", False, "orgadmin"),
    ]
    users = []
    for name, is_superadmin, tag in specs:
        u = User(
            id=_uid(),
            username=f"{tag}-{_uid()[:8]}@test.com",
            email=f"{tag}-{_uid()[:8]}@test.com",
            name=name,
            is_superadmin=is_superadmin,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(u)
        users.append(u)
    await db.flush()
    return users


async def _setup(db, users, assignment_mode="open", **project_kwargs):
    """Create a project with org setup (mirror of the old sync helper)."""
    org = Organization(
        id=_uid(),
        name="Task Org",
        slug=f"task-org-{uuid.uuid4().hex[:8]}",
        display_name="Task Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    await db.flush()

    pid = _uid()
    # Let explicit project_kwargs override the defaults below (e.g. a test that
    # wants randomize_task_order=True) instead of colliding on the keyword.
    project_kwargs.setdefault("min_annotations_per_task", 1)
    project_kwargs.setdefault("maximum_annotations", 3)
    project_kwargs.setdefault("randomize_task_order", False)
    p = Project(
        id=pid,
        title="Task Project",
        created_by=users[0].id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode=assignment_mode,
        **project_kwargs,
    )
    db.add(p)
    await db.flush()

    for i, user in enumerate(users[:4]):
        db.add(OrganizationMembership(
            id=_uid(),
            user_id=user.id,
            organization_id=org.id,
            role="ORG_ADMIN" if i == 0 else ("CONTRIBUTOR" if i == 1 else "ANNOTATOR"),
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=_uid(),
        project_id=pid,
        organization_id=org.id,
        assigned_by=users[0].id,
    ))
    await db.commit()

    return p, org


async def _make_task(db, project_id, inner_id=1, is_labeled=False, data=None):
    tid = _uid()
    t = Task(
        id=tid,
        project_id=project_id,
        data=data or {"text": f"task-{inner_id}"},
        inner_id=inner_id,
        is_labeled=is_labeled,
    )
    db.add(t)
    await db.commit()
    return t


class TestListProjectTasks:
    """Test list_project_tasks endpoint."""

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_tasks_with_data(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        for i in range(3):
            await _make_task(async_test_db, p.id, inner_id=i + 1)

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/tasks")
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    @pytest.mark.asyncio
    async def test_list_tasks_only_labeled(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        await _make_task(async_test_db, p.id, inner_id=1, is_labeled=True)
        await _make_task(async_test_db, p.id, inner_id=2, is_labeled=False)

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_labeled=true"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_tasks_only_unlabeled(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        await _make_task(async_test_db, p.id, inner_id=1, is_labeled=True)
        await _make_task(async_test_db, p.id, inner_id=2, is_labeled=False)

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?only_unlabeled=true"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        for i in range(5):
            await _make_task(async_test_db, p.id, inner_id=i + 1)

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?page=1&page_size=2"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_size"] == 2

    @pytest.mark.asyncio
    async def test_list_tasks_project_not_found(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get("/api/projects/nonexistent/tasks")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_tasks_exclude_my_annotations(
        self, async_test_client, async_test_db
    ):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        t1 = await _make_task(async_test_db, p.id, inner_id=1)
        t2 = await _make_task(async_test_db, p.id, inner_id=2)  # noqa: F841

        # Annotate t1 as admin
        async_test_db.add(Annotation(
            id=_uid(),
            task_id=t1.id,
            project_id=p.id,
            completed_by=users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["mine"]}}],
            was_cancelled=False,
        ))
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{p.id}/tasks?exclude_my_annotations=true"
            )
        assert resp.status_code == 200


class TestGetTaskDetail:
    """Test get_task_detail endpoint (GET /tasks/{task_id})."""

    @pytest.mark.asyncio
    async def test_get_task_basic(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        t = await _make_task(async_test_db, p.id, inner_id=1)

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/tasks/{t.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == t.id

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get("/api/projects/tasks/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_with_annotations(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        t = await _make_task(async_test_db, p.id, inner_id=1)

        async_test_db.add(Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=p.id,
            completed_by=users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["data"]}}],
            was_cancelled=False,
        ))
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/tasks/{t.id}")
        assert resp.status_code == 200


class TestUpdateTask:
    """Test update_task endpoint (PUT /{project_id}/tasks/{task_id})."""

    @pytest.mark.asyncio
    async def test_update_task_data(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        t = await _make_task(async_test_db, p.id, inner_id=1)

        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/{t.id}",
                json={"data": {"text": "updated text"}},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{p.id}/tasks/nonexistent",
                json={"data": {"text": "x"}},
            )
        assert resp.status_code == 404


class TestBulkDeleteTasks:
    """Test bulk-delete endpoint."""

    @pytest.mark.asyncio
    async def test_batch_delete_tasks(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        tasks = [await _make_task(async_test_db, p.id, inner_id=i) for i in range(3)]
        task_ids = [t.id for t in tasks]

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": task_ids},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_batch_delete_no_tasks(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-delete",
                json={"task_ids": []},
            )
        assert resp.status_code in [200, 400]


class TestBulkExportTasks:
    """Test bulk-export endpoint.

    ``bulk_export_tasks`` is still a sync ``def`` handler on ``Depends(get_db)``,
    so this test keeps the sync ``client`` + ``test_db`` + ``auth_headers``
    fixtures.
    """

    def test_bulk_export_tasks(self, client, auth_headers, test_db, test_users):
        import uuid as _uuid
        from datetime import datetime as _dt

        org = Organization(
            id=str(_uuid.uuid4()),
            name="Task Org",
            slug=f"task-org-{_uuid.uuid4().hex[:8]}",
            display_name="Task Org",
            created_at=_dt.utcnow(),
        )
        test_db.add(org)
        test_db.commit()
        pid = str(_uuid.uuid4())
        p = Project(
            id=pid,
            title="Task Project",
            created_by=test_users[0].id,
            is_private=False,
            label_config="<View><Text name='text' value='$text'/></View>",
            assignment_mode="open",
        )
        test_db.add(p)
        test_db.add(ProjectOrganization(
            id=str(_uuid.uuid4()),
            project_id=pid,
            organization_id=org.id,
            assigned_by=test_users[0].id,
        ))
        test_db.commit()
        tasks = []
        for i in range(2):
            t = Task(
                id=str(_uuid.uuid4()),
                project_id=pid,
                data={"text": f"task-{i}"},
                inner_id=i,
            )
            test_db.add(t)
            tasks.append(t)
        test_db.commit()
        task_ids = [t.id for t in tasks]

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": task_ids},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


class TestBulkArchiveTasks:
    """Test bulk-archive endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_archive_tasks(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        tasks = [await _make_task(async_test_db, p.id, inner_id=i) for i in range(2)]
        task_ids = [t.id for t in tasks]

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/bulk-archive",
                json={"task_ids": task_ids, "archive": True},
            )
        assert resp.status_code == 200


class TestGetNextTask:
    """Test get_next_task endpoint."""

    @pytest.mark.asyncio
    async def test_next_task_basic(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        await _make_task(async_test_db, p.id, inner_id=1, is_labeled=False)

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_next_task_all_labeled(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        await _make_task(async_test_db, p.id, inner_id=1, is_labeled=True)

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_next_task_no_tasks(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_next_task_project_not_found(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        await async_test_db.commit()
        with _as_user(users[0]):
            resp = await async_test_client.get("/api/projects/nonexistent/next")
        # superadmin can access any project; the endpoint returns 200 with null task
        assert resp.status_code in [200, 404, 403]

    @pytest.mark.asyncio
    async def test_next_task_randomized(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users, randomize_task_order=True)
        for i in range(5):
            await _make_task(async_test_db, p.id, inner_id=i + 1, is_labeled=False)

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_next_task_manual_mode(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users, assignment_mode="manual")
        t = await _make_task(async_test_db, p.id, inner_id=1, is_labeled=False)
        # Assign task to admin
        async_test_db.add(TaskAssignment(
            id=_uid(),
            task_id=t.id,
            user_id=users[0].id,
            assigned_by=users[0].id,
            status="assigned",
        ))
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/next")
        assert resp.status_code == 200


class TestSkipTask:
    """Test skip_task endpoint."""

    @pytest.mark.asyncio
    async def test_skip_task_basic(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users, show_skip_button=True)
        t = await _make_task(async_test_db, p.id, inner_id=1)

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{t.id}/skip",
                json={},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_skip_task_with_comment(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(
            async_test_db, users, show_skip_button=True, require_comment_on_skip=True
        )
        t = await _make_task(async_test_db, p.id, inner_id=1)

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/{t.id}/skip",
                json={"comment": "Too difficult"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_skip_task_not_found(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{p.id}/tasks/nonexistent/skip",
                json={},
            )
        assert resp.status_code == 404


class TestTaskFields:
    """Test task-fields endpoint."""

    @pytest.mark.asyncio
    async def test_task_fields_basic(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        await _make_task(
            async_test_db, p.id, inner_id=1, data={"text": "hello", "category": "A"}
        )

        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_task_fields_empty(self, async_test_client, async_test_db):
        users = await _make_users(async_test_db)
        p, org = await _setup(async_test_db, users)
        with _as_user(users[0]):
            resp = await async_test_client.get(f"/api/projects/{p.id}/task-fields")
        assert resp.status_code == 200
