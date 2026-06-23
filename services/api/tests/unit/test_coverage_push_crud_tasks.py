"""
Coverage push tests for CRUD, task, member, assignment, annotation, review,
timer, questionnaire, and serializer branches.

Targets uncovered branches across multiple routers.

Several endpoints exercised here (project CRUD, task listing/mutations,
member/assignment/annotation listing, questionnaire listing) have been migrated
to the async DB lane (``Depends(get_async_db)``). The sync ``client`` +
``test_db`` fixtures can't drive those handlers — the sync TestClient runs the
real async engine on a mismatched event loop and never sees the SAVEPOINT-scoped
test transaction. The tests that need to *see* seeded rows through the async
lane are therefore rewritten to use ``async_test_client`` + ``async_test_db``,
seed their rows directly via the async session, and override ``require_user``
through the ``_as_user`` context manager (the sync auth dependency can't see the
async test transaction). Tests whose endpoints are still on the sync lane
(assignment create, annotation create) and the pure-utility/serializer tests are
left on the original fixtures.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Organization,
    OrganizationMembership,
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
    """Override ``require_user`` to return an auth User matching ``db_user``.

    The sync auth dependency authenticates against its own session and cannot
    see rows seeded inside the async test transaction, so async-lane handlers
    get their authenticated user from this override instead of a Bearer token.
    """
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


async def _make_admin(db):
    """Seed a superadmin actor (mirrors the sync ``test_users[0]`` admin)."""
    u = User(
        id=_uid(),
        username=f"admin-{_uid()[:8]}@test.com",
        email=f"admin-{_uid()[:8]}@test.com",
        name="Async Test Admin",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_full_project_async(
    db,
    admin,
    *,
    questionnaire_enabled=False,
    num_tasks=3,
    is_private=False,
    assignment_mode="open",
    seed_membership=False,
):
    """Async twin of ``create_project_fixture``.

    Seeds an org, a project (owned by ``admin``), a ProjectOrganization link,
    ``num_tasks`` tasks, and (optionally) an org membership for ``admin`` so the
    members endpoint surfaces at least one member. Returns
    ``{"project", "tasks", "org"}`` like the sync helper.
    """
    org = Organization(
        id=_uid(),
        name=f"Project Org {uuid.uuid4().hex[:4]}",
        slug=f"proj-org-{uuid.uuid4().hex[:8]}",
        display_name="Project Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()

    project = Project(
        id=_uid(),
        title=f"Test Project {uuid.uuid4().hex[:6]}",
        description="Test project for coverage",
        created_by=admin.id,
        is_private=is_private,
        label_config="<View><Text name='text' value='$text'/><TextArea name='answer' toName='text'/></View>",
        assignment_mode=assignment_mode,
        questionnaire_enabled=questionnaire_enabled,
        min_annotations_per_task=1,
        maximum_annotations=2,
    )
    db.add(project)
    await db.flush()

    if seed_membership:
        db.add(OrganizationMembership(
            id=_uid(),
            user_id=admin.id,
            organization_id=org.id,
            role="ORG_ADMIN",
            joined_at=datetime.now(timezone.utc),
        ))

    db.add(ProjectOrganization(
        id=_uid(),
        project_id=project.id,
        organization_id=org.id,
        assigned_by=admin.id,
    ))
    await db.flush()

    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Task text {i}"},
            meta={"index": i},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()

    return {"project": project, "tasks": tasks, "org": org}


def create_project_fixture(db, users, questionnaire_enabled=False,
                          num_tasks=3, is_private=False,  # noqa: E128
                          assignment_mode="open"):  # noqa: E128
    """Create a complete project with org, membership, and tasks."""
    org = Organization(
        id=str(uuid.uuid4()),
        name=f"Project Org {uuid.uuid4().hex[:4]}",
        slug=f"proj-org-{uuid.uuid4().hex[:8]}",
        display_name="Project Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title=f"Test Project {uuid.uuid4().hex[:6]}",
        description="Test project for coverage",
        created_by=users[0].id,
        is_private=is_private,
        label_config="<View><Text name='text' value='$text'/><TextArea name='answer' toName='text'/></View>",
        assignment_mode=assignment_mode,
        questionnaire_enabled=questionnaire_enabled,
        min_annotations_per_task=1,
        maximum_annotations=2,
    )
    db.add(p)
    db.commit()

    for i, user in enumerate(users[:4]):
        role = "ORG_ADMIN" if i == 0 else ("CONTRIBUTOR" if i < 3 else "ANNOTATOR")
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=users[0].id,
    ))
    db.commit()

    tasks = []
    for i in range(num_tasks):
        tid = str(uuid.uuid4())
        task = Task(
            id=tid,
            project_id=pid,
            data={"text": f"Task text {i}"},
            meta={"index": i},
            inner_id=i + 1,
        )
        db.add(task)
        tasks.append(task)
    db.commit()

    return {"project": p, "tasks": tasks, "org": org}


def _setup_full_project(db, users, **kwargs):
    """Wrapper around create_project_fixture for backward compatibility."""
    return create_project_fixture(db, users, **kwargs)


# =================== CRUD Tests ===================

class TestProjectCrud:
    """Test project CRUD operations."""

    @pytest.mark.asyncio
    async def test_list_projects(self, async_test_client, async_test_db):
        # list_projects is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    @pytest.mark.asyncio
    async def test_list_projects_with_search(self, async_test_client, async_test_db):
        # list_projects is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        title = data["project"].title
        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/?search={title[:10]}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_projects_with_pagination(self, async_test_client, async_test_db):
        # list_projects is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/?page=1&page_size=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 1

    @pytest.mark.asyncio
    async def test_get_project(self, async_test_client, async_test_db):
        # get_project is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id
        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, async_test_client, async_test_db):
        # get_project is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_project(self, async_test_client, async_test_db):
        # create_project is async-lane (Depends(get_async_db)). Org-mode create
        # (X-Organization-Context set) needs an active ORG_ADMIN membership.
        admin = await _make_admin(async_test_db)
        org = Organization(
            id=_uid(),
            name="Create Project Org",
            slug=f"create-org-{uuid.uuid4().hex[:8]}",
            display_name="Create Project Org",
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add(org)
        await async_test_db.flush()

        async_test_db.add(OrganizationMembership(
            id=_uid(),
            user_id=admin.id,
            organization_id=org.id,
            role="ORG_ADMIN",
            joined_at=datetime.now(timezone.utc),
        ))
        await async_test_db.commit()

        # notify_project_created is invoked (by name) inside the handler's
        # _notify_project_created_sync; patching it at module scope intercepts
        # the org-mode notification path.
        with patch("routers.projects.crud.notify_project_created"):
            with _as_user(admin):
                resp = await async_test_client.post(
                    "/api/projects/",
                    json={
                        "title": f"New Project {uuid.uuid4().hex[:8]}",
                        "description": "A new test project",
                        "label_config": "<View><Text name='text' value='$text'/></View>",
                    },
                    headers={"X-Organization-Context": org.id},
                )
        assert resp.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_update_project(self, async_test_client, async_test_db):
        # update_project is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{pid}",
                json={"description": "Updated description"},
            )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_project_not_found(self, async_test_client, async_test_db):
        # update_project is async-lane; nonexistent id must 404.
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/nonexistent",
                json={"description": "test"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, async_test_client, async_test_db):
        # delete_project is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id

        with patch("routers.projects.crud.notify_project_deleted"):
            with _as_user(admin):
                resp = await async_test_client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, async_test_client, async_test_db):
        # delete_project is async-lane; nonexistent id must 404.
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with patch("routers.projects.crud.notify_project_deleted"):
            with _as_user(admin):
                resp = await async_test_client.delete("/api/projects/nonexistent")
        assert resp.status_code == 404


class TestDeepMergeDicts:
    """Test deep_merge_dicts utility."""

    def test_basic_merge(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}
        result = deep_merge_dicts(base, update)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"config": {"a": 1, "b": 2}}
        update = {"config": {"b": 3, "c": 4}}
        result = deep_merge_dicts(base, update)
        assert result == {"config": {"a": 1, "b": 3, "c": 4}}

    def test_none_removal(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"a": 1, "b": 2}
        update = {"b": None}
        result = deep_merge_dicts(base, update)
        assert result == {"a": 1}

    def test_base_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, {"a": 1})
        assert result == {"a": 1}

    def test_update_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({"a": 1}, None)
        assert result == {"a": 1}

    def test_both_none(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts(None, None)
        assert result == {}

    def test_list_replacement(self):
        from routers.projects.crud import deep_merge_dicts
        base = {"items": [1, 2]}
        update = {"items": [3, 4, 5]}
        result = deep_merge_dicts(base, update)
        assert result == {"items": [3, 4, 5]}

    def test_empty_base(self):
        from routers.projects.crud import deep_merge_dicts
        result = deep_merge_dicts({}, {"a": 1})
        assert result == {"a": 1}


# =================== Task Tests ===================

class TestTaskEndpoints:
    """Test task listing and management."""

    @pytest.mark.asyncio
    async def test_list_tasks(self, async_test_client, async_test_db):
        # list_project_tasks is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id

        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/{pid}/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(self, async_test_client, async_test_db):
        # list_project_tasks is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{pid}/tasks?page=1&page_size=2"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_only_labeled(self, async_test_client, async_test_db):
        # list_project_tasks is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        data["tasks"][0].is_labeled = True
        await async_test_db.commit()
        pid = data["project"].id

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{pid}/tasks?only_labeled=true"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_only_unlabeled(self, async_test_client, async_test_db):
        # list_project_tasks is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{pid}/tasks?only_unlabeled=true"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_not_found(self, async_test_client, async_test_db):
        # list_project_tasks is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/nonexistent/tasks")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_detail(self, async_test_client, async_test_db):
        # get_task is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        tid = data["tasks"][0].id

        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/tasks/{tid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_next_task(self, async_test_client, async_test_db):
        # get_next_task is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id
        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/{pid}/next")
        # 200 if task found, 404 if no tasks available
        assert resp.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_bulk_delete_tasks(self, async_test_client, async_test_db):
        # bulk_delete_tasks is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"][:2]]

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{pid}/tasks/bulk-delete",
                json={"task_ids": task_ids},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_skip_task(self, async_test_client, async_test_db):
        # skip_task is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        await async_test_db.commit()
        pid = data["project"].id
        tid = data["tasks"][0].id

        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{pid}/tasks/{tid}/skip",
                json={"comment": "Too complex"},
            )
        assert resp.status_code == 200


# =================== Member Tests ===================

class TestMemberEndpoints:
    """Test project member management."""

    @pytest.mark.asyncio
    async def test_list_members(self, async_test_client, async_test_db):
        # list_project_members is async-lane (Depends(get_async_db)). Seed an
        # org membership for the admin so the endpoint surfaces >= 1 member.
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(
            async_test_db, admin, seed_membership=True
        )
        await async_test_db.commit()
        pid = data["project"].id

        with _as_user(admin):
            resp = await async_test_client.get(f"/api/projects/{pid}/members")
        assert resp.status_code == 200
        members = resp.json()
        assert isinstance(members, list)
        assert len(members) >= 1

    @pytest.mark.asyncio
    async def test_list_members_not_found(self, async_test_client, async_test_db):
        # list_project_members is async-lane (Depends(get_async_db)).
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get("/api/projects/nonexistent/members")
        assert resp.status_code == 404


# =================== Assignment Tests ===================

class TestAssignmentEndpoints:
    """Test task assignment endpoints."""

    def test_assign_tasks_manual(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"][:2]]

        resp = client.post(
            f"/api/projects/{pid}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": [test_users[2].id],
                "distribution": "manual",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_assign_tasks_round_robin(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"]]

        resp = client.post(
            f"/api/projects/{pid}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": [test_users[1].id, test_users[2].id],
                "distribution": "round_robin",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_assign_tasks_random(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        task_ids = [t.id for t in data["tasks"]]

        resp = client.post(
            f"/api/projects/{pid}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": [test_users[1].id],
                "distribution": "random",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_assignments(self, async_test_client, async_test_db):
        # list_task_assignments is async-lane (Depends(get_async_db)). The
        # assignment is seeded via the async session (the create endpoint is on
        # the sync lane — direct write avoids a cross-lane HTTP call).
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(
            async_test_db, admin, assignment_mode="manual"
        )
        pid = data["project"].id
        tid = data["tasks"][0].id

        async_test_db.add(TaskAssignment(
            id=_uid(),
            task_id=tid,
            user_id=admin.id,
            assigned_by=admin.id,
            status="assigned",
        ))
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{pid}/tasks/{tid}/assignments"
            )
        assert resp.status_code == 200

    def test_unassign_task(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users, assignment_mode="manual")
        pid = data["project"].id
        tid = data["tasks"][0].id

        # Create assignment
        assignment_id = str(uuid.uuid4())
        test_db.add(TaskAssignment(
            id=assignment_id,
            task_id=tid,
            user_id=test_users[2].id,
            assigned_by=test_users[0].id,
            status="assigned",
        ))
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{pid}/tasks/{tid}/assignments/{assignment_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# =================== Annotation Tests ===================

class TestAnnotationEndpoints:
    """Test annotation creation and management."""

    def test_create_annotation(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        tid = data["tasks"][0].id

        resp = client.post(
            f"/api/projects/tasks/{tid}/annotations",
            json={
                "result": [{"from_name": "answer", "type": "textarea", "to_name": "text",
                            "value": {"text": ["My answer"]}}],
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_create_annotation_with_lead_time(self, client, test_users, test_db, auth_headers):
        data = _setup_full_project(test_db, test_users)
        tid = data["tasks"][1].id

        resp = client.post(
            f"/api/projects/tasks/{tid}/annotations",
            json={
                "result": [{"from_name": "answer", "type": "textarea", "to_name": "text",
                            "value": {"text": ["Another answer"]}}],
                "lead_time": 45.5,
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_create_annotation_task_not_found(self, client, test_users, test_db, auth_headers):
        resp = client.post(
            "/api/projects/tasks/nonexistent/annotations",
            json={"result": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_annotations(self, async_test_client, async_test_db):
        # list_task_annotations is async-lane (Depends(get_async_db)). The
        # annotation is seeded via the async session (the create endpoint is on
        # the sync lane). Default mode filters to the current user's own
        # annotations, so seed completed_by=admin.
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        pid = data["project"].id
        tid = data["tasks"][0].id

        async_test_db.add(Annotation(
            id=_uid(),
            task_id=tid,
            project_id=pid,
            result=[{"from_name": "answer", "type": "textarea", "value": {"text": ["test"]}}],
            completed_by=admin.id,
            was_cancelled=False,
        ))
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/tasks/{tid}/annotations"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_annotation(self, async_test_client, async_test_db):
        # update_annotation is async-lane (Depends(get_async_db)). Seed the
        # annotation via the async session, owned by the admin actor.
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(async_test_db, admin)
        pid = data["project"].id
        tid = data["tasks"][0].id

        ann_id = _uid()
        async_test_db.add(Annotation(
            id=ann_id,
            task_id=tid,
            project_id=pid,
            result=[{"from_name": "answer", "type": "textarea", "value": {"text": ["old"]}}],
            completed_by=admin.id,
            was_cancelled=False,
        ))
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/annotations/{ann_id}",
                json={
                    "result": [{"from_name": "answer", "type": "textarea", "value": {"text": ["updated"]}}],
                },
            )
        assert resp.status_code == 200


# =================== Review Tests ===================

class TestQuestionnaireEndpoints:
    """Test questionnaire endpoints."""

    @pytest.mark.asyncio
    async def test_list_questionnaire_responses(self, async_test_client, async_test_db):
        # list_questionnaire_responses is async-lane (require_project_access ->
        # get_async_db). Superadmin satisfies the min_role="edit" requirement.
        admin = await _make_admin(async_test_db)
        data = await _seed_full_project_async(
            async_test_db, admin, questionnaire_enabled=True
        )
        await async_test_db.commit()
        pid = data["project"].id

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{pid}/questionnaire-responses"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_questionnaire_responses_not_found(
        self, async_test_client, async_test_db
    ):
        # require_project_access (async-lane) 404s on a missing project.
        admin = await _make_admin(async_test_db)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/nonexistent/questionnaire-responses"
            )
        assert resp.status_code == 404


# =================== Serializer Tests ===================

class TestSerializers:
    """Test export serializer functions."""

    def test_serialize_task_data_mode(self):
        from routers.projects.serializers import serialize_task

        class FakeTask:
            id = "t1"
            inner_id = 1
            data = {"text": "hello"}
            meta = {"tags": ["a"]}
            is_labeled = True
            created_at = datetime(2024, 1, 1)
            updated_at = None

        result = serialize_task(FakeTask(), mode="data")
        assert result["id"] == "t1"
        assert "project_id" not in result

    def test_serialize_task_full_mode(self):
        from routers.projects.serializers import serialize_task

        class FakeTask:
            id = "t1"
            inner_id = 1
            data = {"text": "hello"}
            meta = None
            is_labeled = False
            created_at = datetime(2024, 1, 1)
            updated_at = datetime(2024, 1, 2)
            project_id = "p1"
            created_by = "u1"
            updated_by = None
            total_annotations = 2
            cancelled_annotations = 0
            comment_count = 1
            unresolved_comment_count = 0
            last_comment_updated_at = None
            comment_authors = None
            file_upload_id = None

        result = serialize_task(FakeTask(), mode="full", total_generations=5)
        assert result["project_id"] == "p1"
        assert result["total_generations"] == 5

    def test_serialize_annotation_data_mode(self):
        from routers.projects.serializers import serialize_annotation

        class FakeAnn:
            id = "a1"
            result = [{"type": "textarea"}]
            completed_by = "u1"
            created_at = datetime(2024, 1, 1)
            updated_at = None
            was_cancelled = False
            ground_truth = False
            lead_time = 30.5
            active_duration_ms = 25000
            focused_duration_ms = 20000
            tab_switches = 2
            # Round-trip fields (export-fidelity audit).
            auto_submitted = False
            instruction_variant = None
            ai_assisted = False
            reviewed_by = None
            reviewed_at = None
            review_result = None
            review_annotation = None
            review_comment = None

        result = serialize_annotation(FakeAnn(), mode="data")
        assert "questionnaire_response" in result
        assert result["questionnaire_response"] is None

    def test_serialize_annotation_full_mode(self):
        from routers.projects.serializers import serialize_annotation

        class FakeAnn:
            id = "a1"
            result = []
            completed_by = "u1"
            created_at = None
            updated_at = None
            was_cancelled = False
            ground_truth = True
            lead_time = None
            active_duration_ms = None
            focused_duration_ms = None
            tab_switches = None
            task_id = "t1"
            project_id = "p1"
            draft = {"partial": True}
            prediction_scores = None
            # Round-trip fields.
            auto_submitted = False
            instruction_variant = None
            ai_assisted = False
            reviewed_by = None
            reviewed_at = None
            review_result = None
            review_annotation = None
            review_comment = None

        result = serialize_annotation(FakeAnn(), mode="full")
        assert result["task_id"] == "t1"
        assert result["draft"] == {"partial": True}

    def test_serialize_generation_data_mode(self):
        from routers.projects.serializers import serialize_generation

        class FakeGen:
            id = "g1"
            model_id = "gpt-4o"
            response_content = "Generated text"
            case_data = '{"text": "input"}'
            created_at = datetime(2024, 1, 1)
            response_metadata = {"temperature": 0.5}

        result = serialize_generation(FakeGen(), mode="data", evaluations=[{"id": "e1"}])
        assert result["evaluations"] == [{"id": "e1"}]

    def test_serialize_generation_full_mode(self):
        from routers.projects.serializers import serialize_generation

        class FakeGen:
            id = "g1"
            model_id = "gpt-4o"
            response_content = "text"
            case_data = "{}"
            created_at = None
            response_metadata = None
            generation_id = "rg1"
            task_id = "t1"
            usage_stats = {"tokens": 100}
            status = "completed"
            error_message = None
            # Round-trip parse + label-config snapshot.
            parse_status = "pending"
            parse_error = None
            parsed_annotation = None
            parse_metadata = None
            label_config_version = None
            label_config_snapshot = None

        result = serialize_generation(FakeGen(), mode="full")
        assert result["generation_id"] == "rg1"
        assert result["usage_stats"] == {"tokens": 100}

    def test_serialize_task_evaluation_data_mode(self):
        from routers.projects.serializers import serialize_task_evaluation

        class FakeTE:
            id = "te1"
            annotation_id = None
            field_name = "config1:answer"
            answer_type = "text"
            ground_truth = {"value": "gt"}
            prediction = {"value": "pred"}
            metrics = {"bleu": 0.7}
            passed = True
            confidence_score = 0.9
            error_message = None
            processing_time_ms = 100
            created_at = datetime(2024, 1, 1)
            created_by = "u1"
            evaluation_id = "er1"
            judge_prompts_used = None
            judge_run_id = "jr-1"

        class FakeER:
            model_id = "gpt-4o"

        result = serialize_task_evaluation(
            FakeTE(), mode="data",
            eval_run=FakeER(),
            judge_model_lookup={"jr-1": "gpt-4o-judge"},
        )
        assert result["evaluated_model"] == "gpt-4o"
        assert result["judge_model"] == "gpt-4o-judge"
        assert result["evaluation_run_id"] == "er1"
        assert result["judge_run_id"] == "jr-1"

    def test_serialize_task_evaluation_full_mode(self):
        from routers.projects.serializers import serialize_task_evaluation

        class FakeTE:
            id = "te1"
            annotation_id = "a1"
            field_name = "answer"
            answer_type = "text"
            ground_truth = {"value": "gt"}
            prediction = {"value": "pred"}
            metrics = {"exact": 1.0}
            passed = True
            confidence_score = 0.95
            error_message = None
            processing_time_ms = 50
            created_at = None
            created_by = "u1"
            evaluation_id = "er1"
            task_id = "t1"
            generation_id = "g1"
            judge_prompts_used = None
            judge_run_id = None

        result = serialize_task_evaluation(FakeTE(), mode="full")
        assert result["evaluation_id"] == "er1"
        assert result["task_id"] == "t1"
        assert result["generation_id"] == "g1"

    def test_serialize_evaluation_run_data_mode(self):
        from routers.projects.serializers import serialize_evaluation_run

        class FakeER:
            id = "er1"
            model_id = "gpt-4o"
            evaluation_type_ids = ["test"]
            metrics = {"acc": 0.9}
            status = "completed"
            samples_evaluated = 10
            created_at = datetime(2024, 1, 1)
            completed_at = datetime(2024, 1, 1)
            eval_metadata = {"type": "automated"}
            error_message = None
            has_sample_results = True
            created_by = "u1"

        result = serialize_evaluation_run(FakeER(), mode="data")
        assert result["eval_metadata"] == {"type": "automated"}
        assert result["has_sample_results"] == True  # noqa: E712

    def test_serialize_evaluation_run_full_mode(self):
        from routers.projects.serializers import serialize_evaluation_run

        class FakeER:
            id = "er1"
            model_id = "gpt-4o"
            evaluation_type_ids = ["test"]
            metrics = {"acc": 0.9}
            status = "completed"
            samples_evaluated = 10
            created_at = None
            completed_at = None
            eval_metadata = None
            error_message = "test error"
            has_sample_results = False
            created_by = "u1"
            project_id = "p1"
            task_id = "t1"

        result = serialize_evaluation_run(FakeER(), mode="full")
        assert result["project_id"] == "p1"
        assert result["task_id"] == "t1"

    def test_build_judge_model_lookup_returns_judge_run_id_map(self):
        from routers.projects.serializers import build_judge_model_lookup
        from unittest.mock import Mock as _M

        class FakeER:
            id = "er1"
            eval_metadata = {}  # ignored now: lookup reads from evaluation_judge_runs

        ejr1 = _M(id="jr-1", evaluation_id="er1", judge_model_id="gpt-4o-judge")
        ejr2 = _M(id="jr-2", evaluation_id="er1", judge_model_id="claude-3-judge")
        db = _M()
        db.query.return_value.filter.return_value.all.return_value = [ejr1, ejr2]
        result = build_judge_model_lookup([FakeER()], db)
        assert result == {"jr-1": "gpt-4o-judge", "jr-2": "claude-3-judge"}

    def test_build_judge_model_lookup_empty(self):
        from routers.projects.serializers import build_judge_model_lookup
        from unittest.mock import Mock as _M

        # Empty runs short-circuits, no DB call needed
        assert build_judge_model_lookup([], _M()) == {}

    def test_build_evaluation_indexes(self):
        from routers.projects.serializers import build_evaluation_indexes

        class FakeTE:
            def __init__(self, task_id, gen_id):
                self.task_id = task_id
                self.generation_id = gen_id

        tes = [FakeTE("t1", "g1"), FakeTE("t1", None), FakeTE("t2", "g2")]
        by_task, by_gen = build_evaluation_indexes(tes)
        assert len(by_task["t1"]) == 2
        assert len(by_task["t2"]) == 1
        assert len(by_gen["g1"]) == 1
        assert "g2" in by_gen
        assert None not in by_gen
