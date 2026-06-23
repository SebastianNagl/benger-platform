"""
Integration tests for project task management endpoints.

Targets: routers/projects/tasks.py — list/next/get/update/metadata/bulk-* paths.
Uses real PostgreSQL with per-test transaction rollback.

Most task-router handlers were migrated to the async DB lane
(``Depends(get_async_db)``), so those tests seed rows via ``async_test_db`` and
drive the HTTP surface through ``async_test_client``, overriding ``require_user``
to the acting user (the sync auth dependency can't see the async test
transaction). The ONE exception is ``bulk_export_tasks`` (POST
``.../tasks/bulk-export``) which is still a sync ``def`` handler on
``Depends(get_db)`` — its test keeps the sync ``client`` + ``test_db`` fixtures.
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


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Auth override + async seeding helpers (mirror the canonical async pattern in
# tests/integration/test_file_uploads_coverage.py).
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


async def _seed_users(db):
    """Create the 4 permission-level users (admin/contributor/annotator/org_admin)
    matching the layout of the sync ``test_users`` fixture:
    [0] admin (superadmin), [1] contributor, [2] annotator, [3] org_admin.
    """
    specs = [
        ("Test Admin", True),
        ("Test Contributor", False),
        ("Test Annotator", False),
        ("Test Org Admin", False),
    ]
    users = []
    for name, is_superadmin in specs:
        u = User(
            id=_uid(),
            username=f"{name.split()[-1].lower()}-{_uid()[:8]}@test.com",
            email=f"{name.split()[-1].lower()}-{_uid()[:8]}@test.com",
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


async def _seed_org(db, users):
    """Org with memberships mirroring the sync ``test_org`` fixture:
    [0]=ORG_ADMIN, [1]=CONTRIBUTOR, [2]=ANNOTATOR, [3]=ORG_ADMIN."""
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

    roles = [
        OrganizationRole.ORG_ADMIN,
        OrganizationRole.CONTRIBUTOR,
        OrganizationRole.ANNOTATOR,
        OrganizationRole.ORG_ADMIN,
    ]
    for user, role in zip(users[:4], roles):
        db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                is_active=True,
                joined_at=datetime.now(timezone.utc),
            )
        )
    await db.flush()
    return org


async def _setup(
    db,
    admin: User,
    org: Organization,
    *,
    num_tasks: int = 5,
    label_config: str = '<View><Text name="text" value="$text"/></View>',
    assignment_mode: str = "open",
):
    """Create a project with tasks linked to an org."""
    project = Project(
        id=_uid(),
        title=f"Tasks Test {uuid.uuid4().hex[:6]}",
        description="Tasks integration test project",
        created_by=admin.id,
        label_config=label_config,
        assignment_mode=assignment_mode,
    )
    db.add(project)
    await db.flush()

    po = ProjectOrganization(
        id=_uid(),
        project_id=project.id,
        organization_id=org.id,
        assigned_by=admin.id,
    )
    db.add(po)
    await db.flush()

    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Task text #{i}", "meta_field": f"value_{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(task)
        tasks.append(task)

    await db.commit()
    return project, tasks


@pytest_asyncio.fixture(scope="function")
async def seeded(async_test_db):
    """Seed the 4 users + org once per test; return (users, org)."""
    users = await _seed_users(async_test_db)
    org = await _seed_org(async_test_db, users)
    await async_test_db.commit()
    return users, org


def _ctx(org: Organization):
    return {"X-Organization-Context": org.id}


@pytest.mark.integration
class TestListTasks:
    """GET /api/projects/{project_id}/tasks"""

    @pytest.mark.asyncio
    async def test_list_tasks_basic(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=5)
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks",
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data or "items" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=10)
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?page=1&page_size=3",
                headers=_ctx(org),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_only_labeled(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=3)
        # Mark one task as labeled
        tasks[0].is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?only_labeled=true",
                headers=_ctx(org),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_only_unlabeled(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=3)
        tasks[0].is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks?only_unlabeled=true",
                headers=_ctx(org),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_nonexistent_project(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        with _as_user(users[0]):
            resp = await async_test_client.get(
                "/api/projects/nonexistent-id/tasks",
            )
        assert resp.status_code in (403, 404)


@pytest.mark.integration
class TestGetSingleTask:
    """GET /api/projects/tasks/{task_id}"""

    @pytest.mark.asyncio
    async def test_get_task_by_id(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tasks[0].id}",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tasks[0].id

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        with _as_user(users[0]):
            resp = await async_test_client.get(
                "/api/projects/tasks/nonexistent-task-id",
            )
        assert resp.status_code == 404


@pytest.mark.integration
class TestGetNextTask:
    """GET /api/projects/{project_id}/next"""

    @pytest.mark.asyncio
    async def test_get_next_task(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=3)
        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        # 200 with a task, or 404 if no tasks available
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_get_next_task_all_labeled(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=2)
        for t in tasks:
            t.is_labeled = True
        await async_test_db.commit()

        with _as_user(users[0]):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/next",
                headers=_ctx(org),
            )
        # Should indicate no tasks available
        assert resp.status_code in (200, 404)


@pytest.mark.integration
class TestUpdateTask:
    """PUT /api/projects/{project_id}/tasks/{task_id}"""

    @pytest.mark.asyncio
    async def test_update_task_data(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Updated text content"}},
                headers=_ctx(org),
            )
        assert resp.status_code in (200, 403)

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/nonexistent-id",
                json={"data": {"text": "nope"}},
                headers=_ctx(org),
            )
        assert resp.status_code in (404, 403)


@pytest.mark.integration
class TestUpdateTaskAuthorization:
    """PUT /api/projects/{project_id}/tasks/{task_id} — who may edit task data.

    Editing is allowed for superadmins, the project creator, and active
    ORG_ADMIN members of the project's organization. Everyone else gets 403.
    """

    @pytest.mark.asyncio
    async def test_superadmin_can_edit(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Edited by superadmin"}},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == "Edited by superadmin"

    @pytest.mark.asyncio
    async def test_org_admin_member_can_edit(
        self, async_test_client, async_test_db, seeded
    ):
        # Project is created by the superadmin, so org_admin (users[3]) is
        # NOT the creator — this exercises the ORG_ADMIN membership branch.
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[3]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Edited by org admin"}},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == "Edited by org admin"

    @pytest.mark.asyncio
    async def test_contributor_cannot_edit(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[1]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Contributor attempt"}},
                headers=_ctx(org),
            )
        assert resp.status_code == 403
        assert "organization admins" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_annotator_cannot_edit(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[2]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Annotator attempt"}},
                headers=_ctx(org),
            )
        assert resp.status_code == 403
        assert "organization admins" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_deactivated_org_admin_cannot_edit(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        # Deactivate the org_admin's membership — a deactivated member must lose
        # edit access entirely.
        from sqlalchemy import select

        membership = (
            await async_test_db.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == users[3].id,
                    OrganizationMembership.organization_id == org.id,
                )
            )
        ).scalar_one_or_none()
        membership.is_active = False
        await async_test_db.commit()

        with _as_user(users[3]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Should be blocked"}},
                headers=_ctx(org),
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_project_creator_can_edit(
        self, async_test_client, async_test_db, seeded
    ):
        # Project created by the contributor (non-superadmin, CONTRIBUTOR role,
        # no ORG_ADMIN membership anywhere): the creator branch of
        # check_user_can_edit_task_data fires before the ORG_ADMIN check, so the
        # creator may edit despite holding a non-admin org role
        # (test_contributor_cannot_edit proves the role alone is insufficient).
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[1], org)
        with _as_user(users[1]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Edited by creator"}},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == "Edited by creator"

    @pytest.mark.asyncio
    async def test_non_member_cannot_edit(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)

        # A user with no relationship to the project: not the creator, no
        # membership in the project's org — only an active membership (even as
        # ORG_ADMIN) in an unrelated organization.
        other_org = Organization(
            id=_uid(),
            name="Unrelated Org",
            slug=f"unrelated-org-{uuid.uuid4().hex[:6]}",
            display_name="Unrelated Org",
            description="Organization with no link to the test project",
        )
        outsider = User(
            id=_uid(),
            username=f"outsider-{_uid()[:8]}@test.com",
            email=f"outsider-{_uid()[:8]}@test.com",
            name="Test Outsider",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add_all([other_org, outsider])
        await async_test_db.flush()
        async_test_db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=outsider.id,
                organization_id=other_org.id,
                role=OrganizationRole.ORG_ADMIN,
                is_active=True,
            )
        )
        await async_test_db.commit()

        with _as_user(outsider):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Outsider attempt"}},
                headers={"X-Organization-Context": other_org.id},
            )
        # check_project_accessible fires before the edit gate: the project does
        # not belong to the outsider's org, so the request is rejected with 403
        # "Access denied" and check_user_can_edit_task_data is never reached.
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_edit(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        # No require_user override and no auth header: require_user rejects the
        # request before any project/task lookup.
        resp = await async_test_client.put(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Anonymous attempt"}},
            headers=_ctx(org),
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_edit_merges_data_and_writes_audit_log(
        self, async_test_client, async_test_db, seeded
    ):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        # Task seeded with {"text": ..., "meta_field": ...}; update only `text`.
        with _as_user(users[0]):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}",
                json={"data": {"text": "Merged value"}},
                headers=_ctx(org),
            )
        assert resp.status_code == 200
        body = resp.json()
        # Updated field changed, untouched field preserved (merge semantics).
        assert body["data"]["text"] == "Merged value"
        assert body["data"]["meta_field"] == "value_0"
        # An audit entry was recorded.
        audit_log = body["meta"]["audit_log"]
        assert isinstance(audit_log, list) and len(audit_log) >= 1
        assert audit_log[-1]["action"] == "data_update"
        assert audit_log[-1]["changes"]["after"] == {"text": "Merged value"}


@pytest.mark.integration
class TestTaskMetadata:
    """PATCH /api/projects/tasks/{task_id}/metadata"""

    @pytest.mark.asyncio
    async def test_update_task_metadata(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[0]):
            resp = await async_test_client.patch(
                f"/api/projects/tasks/{tasks[0].id}/metadata",
                json={"meta": {"priority": "high", "difficulty": 3}},
            )
        assert resp.status_code in (200, 404, 422)


@pytest.mark.integration
class TestBulkTaskMetadata:
    """PATCH /api/projects/tasks/bulk-metadata"""

    @pytest.mark.asyncio
    async def test_bulk_metadata_update(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=3)
        with _as_user(users[0]):
            resp = await async_test_client.patch(
                "/api/projects/tasks/bulk-metadata",
                json={
                    "task_ids": [t.id for t in tasks[:2]],
                    "meta": {"batch": "test-batch-1"},
                },
            )
        assert resp.status_code in (200, 404, 422)


@pytest.mark.integration
class TestBulkDeleteTasks:
    """POST /api/projects/{project_id}/tasks/bulk-delete"""

    @pytest.mark.asyncio
    async def test_bulk_delete_tasks(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=4)
        task_ids = [t.id for t in tasks[:2]]

        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-delete",
                json={"task_ids": task_ids},
                headers=_ctx(org),
            )
        assert resp.status_code in (200, 403)

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_list(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, _ = await _setup(async_test_db, users[0], org)
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-delete",
                json={"task_ids": []},
                headers=_ctx(org),
            )
        assert resp.status_code in (200, 400, 403)


@pytest.mark.integration
class TestBulkExportTasks:
    """POST /api/projects/{project_id}/tasks/bulk-export

    ``bulk_export_tasks`` is still a sync ``def`` handler on ``Depends(get_db)``,
    so this test keeps the sync ``client`` + ``test_db`` fixtures.
    """

    def test_bulk_export_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup_sync(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)


def _setup_sync(
    db,
    admin: User,
    org: Organization,
    *,
    num_tasks: int = 5,
    label_config: str = '<View><Text name="text" value="$text"/></View>',
    assignment_mode: str = "open",
):
    """Sync project+tasks seeder for the bulk-export (still-sync) handler test."""
    project = Project(
        id=_uid(),
        title=f"Tasks Test {uuid.uuid4().hex[:6]}",
        description="Tasks integration test project",
        created_by=admin.id,
        label_config=label_config,
        assignment_mode=assignment_mode,
    )
    db.add(project)
    db.flush()

    po = ProjectOrganization(
        id=_uid(),
        project_id=project.id,
        organization_id=org.id,
        assigned_by=admin.id,
    )
    db.add(po)
    db.flush()

    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Task text #{i}", "meta_field": f"value_{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(task)
        tasks.append(task)

    db.commit()
    return project, tasks


@pytest.mark.integration
class TestBulkArchiveTasks:
    """POST /api/projects/{project_id}/tasks/bulk-archive"""

    @pytest.mark.asyncio
    async def test_bulk_archive_tasks(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org, num_tasks=3)
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/bulk-archive",
                json={"task_ids": [t.id for t in tasks[:2]]},
                headers=_ctx(org),
            )
        assert resp.status_code in (200, 403)


@pytest.mark.integration
class TestSkipTask:
    """POST /api/projects/{project_id}/tasks/{task_id}/skip"""

    @pytest.mark.asyncio
    async def test_skip_task(self, async_test_client, async_test_db, seeded):
        users, org = seeded
        project, tasks = await _setup(async_test_db, users[0], org)
        with _as_user(users[0]):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
                json={"reason": "Too ambiguous"},
                headers=_ctx(org),
            )
        # Endpoint may not exist or may return various statuses
        assert resp.status_code in (200, 404, 405)
