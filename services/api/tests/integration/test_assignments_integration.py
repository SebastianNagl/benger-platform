"""
Integration tests for task assignment endpoints.

Targets: routers/projects/assignments.py — 6.65% coverage (221 uncovered lines)
Uses real PostgreSQL with per-test transaction rollback.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
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
    """Override ``require_user`` to return an auth User matching the seeded DB
    user. ``list_task_assignments`` is on the async DB lane, so it authenticates
    via this override rather than the sync token-based auth (which can't see the
    async test transaction)."""
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


async def _make_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"asg-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Assign User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _setup_async(db, owner_id, *, num_tasks=4):
    """Async twin of ``_setup`` — project with tasks via ``async_test_db``."""
    project = Project(
        id=_uid(),
        title=f"Assign Test {uuid.uuid4().hex[:6]}",
        created_by=owner_id,
        label_config='<View><Text name="text" value="$text"/></View>',
        assignment_mode="manual",
    )
    db.add(project)
    await db.flush()
    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Assignment task #{i}"},
            inner_id=i + 1,
            created_by=owner_id,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()
    return project, tasks


def _setup(db, admin, org, *, num_tasks=4, users=None):
    """Create project with tasks, org link, and project members."""
    project = Project(
        id=_uid(),
        title=f"Assign Test {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        assignment_mode="manual",
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
            data={"text": f"Assignment task #{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(task)
        tasks.append(task)
    db.commit()
    return project, tasks


@pytest.mark.integration
class TestAssignTasks:
    """POST /api/projects/{project_id}/tasks/assign"""

    def test_manual_assign_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        annotator = test_users[2]  # annotator user

        resp = client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={
                "task_ids": [tasks[0].id, tasks[1].id],
                "user_ids": [annotator.id],
                "distribution": "manual",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assignments_created"] == 2

    def test_round_robin_assign(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=6)
        user_ids = [test_users[1].id, test_users[2].id]

        resp = client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={
                "task_ids": [t.id for t in tasks],
                "user_ids": user_ids,
                "distribution": "round_robin",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 6

    def test_random_assign(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=4)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={
                "task_ids": [t.id for t in tasks],
                "user_ids": [test_users[2].id],
                "distribution": "random",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 4

    def test_load_balanced_assign(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=4)
        user_ids = [test_users[1].id, test_users[2].id]
        resp = client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={
                "task_ids": [t.id for t in tasks],
                "user_ids": user_ids,
                "distribution": "load_balanced",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 4

    def test_assign_empty_task_ids(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={"task_ids": [], "user_ids": [test_users[2].id], "distribution": "manual"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_assign_empty_user_ids(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={"task_ids": [tasks[0].id], "user_ids": [], "distribution": "manual"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_assign_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.post(
            "/api/projects/nonexistent/tasks/assign",
            json={"task_ids": ["x"], "user_ids": ["y"], "distribution": "manual"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_assign_duplicate_is_idempotent(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        payload = {
            "task_ids": [tasks[0].id],
            "user_ids": [test_users[2].id],
            "distribution": "manual",
        }
        resp1 = client.post(f"/api/projects/{project.id}/tasks/assign", json=payload, headers=auth_headers["admin"])
        resp2 = client.post(f"/api/projects/{project.id}/tasks/assign", json=payload, headers=auth_headers["admin"])
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.json()["assignments_skipped"] >= 1

    def test_annotator_cannot_assign(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={"task_ids": [tasks[0].id], "user_ids": [test_users[2].id], "distribution": "manual"},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestListTaskAssignments:
    """GET /api/projects/{project_id}/tasks/{task_id}/assignments"""

    @pytest.mark.asyncio
    async def test_list_assignments(self, async_test_client, async_test_db):
        # list_task_assignments is on the async DB lane — seed + drive async.
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, tasks = await _setup_async(async_test_db, admin.id)
        annotator = await _make_user(async_test_db, is_superadmin=False)
        async_test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=tasks[0].id,
                user_id=annotator.id,
                assigned_by=admin.id,
                status="assigned",
            )
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks/{tasks[0].id}/assignments",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_assignments_nonexistent_task(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _setup(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{project.id}/tasks/nonexistent/assignments",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestRemoveAssignment:
    """DELETE /api/projects/{project_id}/tasks/{task_id}/assignments/{assignment_id}"""

    def test_remove_assignment(self, client, test_db, test_users, auth_headers, test_org):
        # remove_task_assignment is a SYNC handler (stays on get_db), so this
        # test stays sync. It previously fetched the assignment_id via the
        # now-async list_task_assignments GET (which the sync test_db
        # transaction is invisible to → 404). Seed the assignment directly via
        # test_db and DELETE it, keeping the whole test on the sync lane.
        project, tasks = _setup(test_db, test_users[0], test_org)
        assignment = TaskAssignment(
            id=_uid(),
            task_id=tasks[0].id,
            user_id=test_users[2].id,
            assigned_by=test_users[0].id,
            status="assigned",
        )
        test_db.add(assignment)
        test_db.commit()
        assignment_id = assignment.id

        # Remove
        resp = client.delete(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/assignments/{assignment_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

        # Row removed from DB.
        gone = (
            test_db.query(TaskAssignment)
            .filter(TaskAssignment.id == assignment_id)
            .first()
        )
        assert gone is None

    def test_remove_nonexistent_assignment(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.delete(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/assignments/nonexistent",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestMyTasks:
    """GET /api/projects/{project_id}/my-tasks"""

    def test_get_my_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Assign tasks to admin
        client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={"task_ids": [tasks[0].id], "user_ids": [test_users[0].id], "distribution": "manual"},
            headers=auth_headers["admin"],
        )

        resp = client.get(
            f"/api/projects/{project.id}/my-tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert "total" in data

    def test_get_my_tasks_with_status_filter(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={"task_ids": [tasks[0].id], "user_ids": [test_users[0].id], "distribution": "manual"},
            headers=auth_headers["admin"],
        )

        resp = client.get(
            f"/api/projects/{project.id}/my-tasks?status=assigned",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_get_my_tasks_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/my-tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def _open_project_with_task(self, db, admin, org, inner_id=1):
        project = Project(
            id=_uid(),
            title=f"Open {uuid.uuid4().hex[:6]}",
            created_by=admin.id,
            label_config='<View><Text name="text" value="$text"/></View>',
            assignment_mode="open",
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=org.id,
                assigned_by=admin.id,
            )
        )
        db.flush()
        task = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": "open task"},
            inner_id=inner_id,
            created_by=admin.id,
        )
        db.add(task)
        db.commit()
        return project, task

    def test_open_mode_annotated_task_appears(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Open mode: a task the user annotated (no TaskAssignment) is listed,
        with a null assignment. This is the core of surfacing open-mode work."""
        admin = test_users[0]
        project, task = self._open_project_with_task(test_db, admin, test_org)
        test_db.add(
            Annotation(
                id=_uid(),
                task_id=task.id,
                project_id=project.id,
                completed_by=admin.id,
                result=[],
                was_cancelled=False,
            )
        )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/my-tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        row = next((t for t in data["tasks"] if t["id"] == task.id), None)
        assert row is not None, "annotated open-mode task missing from my-tasks"
        assert row["assignment"] is None
        # Community edition has no extended hook -> badge flags are False.
        assert row["has_evaluation"] is False
        assert row["has_feedback"] is False

    def test_open_mode_untouched_task_absent(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A task that's neither assigned nor annotated by the user is NOT listed."""
        admin = test_users[0]
        project, task = self._open_project_with_task(test_db, admin, test_org)

        resp = client.get(
            f"/api/projects/{project.id}/my-tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        ids = [t["id"] for t in resp.json()["tasks"]]
        assert task.id not in ids

    def test_status_filter_excludes_annotation_only_tasks(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A status filter targets the assignment; annotation-only (un-assigned)
        tasks have no status and drop out when a status is selected."""
        admin = test_users[0]
        project, task = self._open_project_with_task(test_db, admin, test_org)
        test_db.add(
            Annotation(
                id=_uid(),
                task_id=task.id,
                project_id=project.id,
                completed_by=admin.id,
                result=[],
                was_cancelled=False,
            )
        )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/my-tasks?status=assigned",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        ids = [t["id"] for t in resp.json()["tasks"]]
        assert task.id not in ids
