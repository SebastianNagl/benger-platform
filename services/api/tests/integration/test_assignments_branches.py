"""Branch-coverage integration tests for the task-assignment router.

Targets the error/edge paths in
``services/api/routers/projects/assignments.py`` that the happy-path suite in
``test_task_assignments.py`` does not exercise:

- ``assign_tasks``: no-membership 403, notification fan-out (priority + notes
  paths in the message body), round-robin / random / load-balanced create paths
  with persisted-state assertions.
- ``list_task_assignments``: task-not-in-project 404, access-denied 403, empty
  list, assignee name/email enrichment.
- ``remove_task_assignment``: assignment-not-found 404, persisted deletion +
  removal notification, non-member 403.
- ``get_my_tasks``: project-not-found 404, ``search`` ILIKE filter branch,
  ``has_feedback`` community-edition (empty-set) branch, empty result set.

Every test calls the endpoint through the ``client`` fixture, asserts the HTTP
status + response JSON, and verifies persisted DB state via ``test_db``.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List

import pytest
from sqlalchemy.orm import Session

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Notification, User
from project_models import (
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    """Override ``require_user`` to return an auth User matching the seeded DB
    user. The migrated ``list_task_assignments`` handler runs on the async DB
    lane, so it authenticates via this override rather than the sync
    token-based auth (which can't see the async test transaction)."""
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


@pytest.fixture(scope="function")
def assignment_project(test_db: Session, test_users: List[User], test_org):
    """Project with org link, 4 member users, and 6 tasks.

    Mirrors the fixture in test_task_assignments.py so endpoint behaviour is
    identical, but kept local so this module is self-contained.
    """
    project = Project(
        id=str(uuid.uuid4()),
        title="Branch Coverage Assignment Project",
        description="Project for assignment branch coverage",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=test_users[0].id,
        is_published=True,
        assignment_mode="manual",
    )
    test_db.add(project)
    test_db.flush()

    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project.id,
        organization_id=test_org.id,
        assigned_by=test_users[0].id,
    )
    test_db.add(project_org)

    roles = ["admin", "contributor", "annotator", "admin"]
    for i, user in enumerate(test_users[:4]):
        test_db.add(
            ProjectMember(
                id=str(uuid.uuid4()),
                project_id=project.id,
                user_id=user.id,
                role=roles[i],
                is_active=True,
            )
        )

    tasks = []
    for i in range(6):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Branch task {i + 1} unique-term-{i}"},
            created_by=test_users[0].id,
            updated_by=test_users[0].id,
        )
        test_db.add(task)
        tasks.append(task)

    test_db.commit()

    return {
        "project": project,
        "tasks": tasks,
        "users": {
            "admin": test_users[0],
            "contributor": test_users[1],
            "annotator": test_users[2],
            "org_admin": test_users[3],
        },
    }


# ---------------------------------------------------------------------------
# assign_tasks — permission + notification fan-out branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAssignPermissionAndNotification:
    def test_non_member_user_without_membership_forbidden(
        self, client, auth_headers, test_db, test_users
    ):
        """A non-superadmin with NO org membership on the project gets 403.

        Exercises the branch where ``user_with_memberships`` exists but no
        membership matches the project orgs, so ``user_role`` stays None.
        """
        # Standalone project with no org link → annotator (member of test_org
        # only) has no membership tying them to this project's orgs.
        project = Project(
            id=str(uuid.uuid4()),
            title="Orphan Project",
            created_by=test_users[0].id,
            is_published=True,
        )
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=1,
            data={"text": "x"},
            created_by=test_users[0].id,
        )
        test_db.add(project)
        test_db.add(task)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={
                "task_ids": [task.id],
                "user_ids": [test_users[2].id],
                "distribution": "manual",
            },
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403
        assert "assign tasks" in resp.json()["detail"]

        # No assignment persisted.
        count = (
            test_db.query(TaskAssignment)
            .filter(TaskAssignment.task_id == task.id)
            .count()
        )
        assert count == 0

    def test_assign_with_priority_and_notes_creates_notification(
        self, client, auth_headers, assignment_project, test_db
    ):
        """Assign with priority>0 and notes → assignment persisted + notification
        row created (exercises the notification fan-out, priority and notes
        branches of the message body)."""
        p = assignment_project
        annotator = p["users"]["annotator"]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": [p["tasks"][0].id],
                "user_ids": [annotator.id],
                "distribution": "manual",
                "priority": 5,
                "notes": "Please prioritise this case",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["assignments_created"] == 1
        assert body["distribution"] == "manual"

        # Assignment persisted with the priority + notes we sent.
        assignment = (
            test_db.query(TaskAssignment)
            .filter(
                TaskAssignment.task_id == p["tasks"][0].id,
                TaskAssignment.user_id == annotator.id,
            )
            .first()
        )
        assert assignment is not None
        assert assignment.priority == 5
        assert assignment.notes == "Please prioritise this case"
        assert assignment.status == "assigned"

        # Notification fan-out persisted a row for the assignee.
        notif_count = (
            test_db.query(Notification)
            .filter(Notification.user_id == annotator.id)
            .count()
        )
        assert notif_count >= 1


# ---------------------------------------------------------------------------
# assign_tasks — distribution create paths (persisted-state assertions)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAssignDistributionPersistence:
    def test_round_robin_persists_alternating_users(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        task_ids = [t.id for t in p["tasks"][:4]]
        users = [p["users"]["contributor"].id, p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": users, "distribution": "round_robin"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 4

        # Exactly 4 task-level assignments persisted across the two users.
        persisted = (
            test_db.query(TaskAssignment)
            .filter(TaskAssignment.task_id.in_(task_ids))
            .all()
        )
        assert len(persisted) == 4
        assert {a.user_id for a in persisted} == set(users)

    def test_random_persists_one_per_task(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        task_ids = [t.id for t in p["tasks"][:3]]
        users = [p["users"]["contributor"].id, p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": users, "distribution": "random"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 3

        for tid in task_ids:
            cnt = (
                test_db.query(TaskAssignment)
                .filter(TaskAssignment.task_id == tid)
                .count()
            )
            assert cnt == 1

    def test_load_balanced_routes_to_least_loaded(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        contributor = p["users"]["contributor"]
        annotator = p["users"]["annotator"]

        # Pre-load contributor with 2 active assignments.
        for i in range(2):
            test_db.add(
                TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=p["tasks"][i].id,
                    user_id=contributor.id,
                    assigned_by=p["users"]["admin"].id,
                    status="assigned",
                )
            )
        test_db.commit()

        new_task_ids = [p["tasks"][2].id, p["tasks"][3].id]
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": new_task_ids,
                "user_ids": [contributor.id, annotator.id],
                "distribution": "load_balanced",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 2

        # Both new tasks routed to the least-loaded annotator.
        annotator_new = (
            test_db.query(TaskAssignment)
            .filter(
                TaskAssignment.user_id == annotator.id,
                TaskAssignment.task_id.in_(new_task_ids),
            )
            .count()
        )
        assert annotator_new == 2


# ---------------------------------------------------------------------------
# list_task_assignments — error + enrichment branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListAssignments:
    """``list_task_assignments`` was migrated to the async DB lane
    (``Depends(get_async_db)``), so these seed via ``async_test_db`` and drive
    the endpoint through ``async_test_client``, with ``require_user`` overridden
    per-test via ``_as_user``."""

    async def _seed_project_with_task(self, db, owner_id):
        project = Project(
            id=_uid(),
            title="Branch Coverage Assignment Project",
            description="Project for assignment branch coverage",
            label_config='<View><Text name="text" value="$text"/></View>',
            created_by=owner_id,
            is_published=True,
            assignment_mode="manual",
        )
        db.add(project)
        await db.flush()
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=1,
            data={"text": "Branch task unique-term-0"},
            created_by=owner_id,
            updated_by=owner_id,
        )
        db.add(task)
        await db.flush()
        return project, task

    @pytest.mark.asyncio
    async def test_task_not_in_project_returns_404(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, _task = await self._seed_project_with_task(async_test_db, admin.id)
        await async_test_db.commit()

        missing_task = _uid()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks/{missing_task}/assignments",
            )
        assert resp.status_code == 404
        assert "Task not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_access_denied_for_outsider_returns_403(
        self, async_test_client, async_test_db
    ):
        """A non-superadmin, non-member outsider gets 403 from the real async
        ``check_project_accessible_async`` gate. The project belongs to a
        DIFFERENT owner and an org the outsider is NOT a member of."""
        from models import Organization

        owner = await _make_user(async_test_db, is_superadmin=False)
        # Separate org the outsider does NOT belong to.
        other_org = Organization(
            id=_uid(),
            name="Outsider Org",
            slug=f"outsider-org-{_uid()[:8]}",
            display_name="Outsider Org",
        )
        async_test_db.add(other_org)
        await async_test_db.flush()

        project = Project(
            id=_uid(),
            title="Outsider Project",
            created_by=owner.id,
            is_published=True,
        )
        async_test_db.add(project)
        await async_test_db.flush()
        async_test_db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=other_org.id,
                assigned_by=owner.id,
            )
        )
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=1,
            data={"text": "x"},
            created_by=owner.id,
        )
        async_test_db.add(task)

        # Real non-superadmin, non-member outsider.
        outsider = await _make_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()

        with _as_user(outsider):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks/{task.id}/assignments",
                headers={"X-Organization-Context": other_org.id},
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_empty_assignments_returns_empty_list(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, task = await self._seed_project_with_task(async_test_db, admin.id)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks/{task.id}/assignments",
            )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_enriches_with_user_name_and_email(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project, task = await self._seed_project_with_task(async_test_db, admin.id)
        # Real assignee with name/email so the bulk user-fetch enriches them.
        annotator = await _make_user(async_test_db, is_superadmin=False)
        async_test_db.add(
            TaskAssignment(
                id=_uid(),
                task_id=task.id,
                user_id=annotator.id,
                assigned_by=admin.id,
                status="assigned",
                priority=3,
            )
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/tasks/{task.id}/assignments",
            )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["user_id"] == annotator.id
        assert rows[0]["user_name"] == annotator.name
        assert rows[0]["user_email"] == annotator.email
        assert rows[0]["priority"] == 3
        assert rows[0]["status"] == "assigned"


# ---------------------------------------------------------------------------
# remove_task_assignment — error + persisted-deletion branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRemoveAssignment:
    def test_remove_nonexistent_assignment_returns_404(
        self, client, auth_headers, assignment_project
    ):
        p = assignment_project
        resp = client.delete(
            f"/api/projects/{p['project'].id}/tasks/{p['tasks'][0].id}"
            f"/assignments/{uuid.uuid4()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Assignment not found"

    def test_remove_deletes_row_and_creates_notification(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        annotator = p["users"]["annotator"]
        assignment = TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=p["tasks"][0].id,
            user_id=annotator.id,
            assigned_by=p["users"]["admin"].id,
            status="assigned",
        )
        test_db.add(assignment)
        test_db.commit()
        assignment_id = assignment.id

        resp = client.delete(
            f"/api/projects/{p['project'].id}/tasks/{p['tasks'][0].id}"
            f"/assignments/{assignment_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        # Row removed from DB.
        gone = (
            test_db.query(TaskAssignment)
            .filter(TaskAssignment.id == assignment_id)
            .first()
        )
        assert gone is None

        # Removal notification persisted for the affected user.
        notif_count = (
            test_db.query(Notification)
            .filter(Notification.user_id == annotator.id)
            .count()
        )
        assert notif_count >= 1

    def test_annotator_cannot_remove_returns_403(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        assignment = TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=p["tasks"][0].id,
            user_id=p["users"]["annotator"].id,
            assigned_by=p["users"]["admin"].id,
            status="assigned",
        )
        test_db.add(assignment)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p['project'].id}/tasks/{p['tasks'][0].id}"
            f"/assignments/{assignment.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403
        assert "remove assignments" in resp.json()["detail"]

        # Assignment still present (not deleted).
        still_there = (
            test_db.query(TaskAssignment)
            .filter(TaskAssignment.id == assignment.id)
            .first()
        )
        assert still_there is not None


# ---------------------------------------------------------------------------
# get_my_tasks — error + filter branches
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMyTasksBranches:
    def test_project_not_found_returns_404(self, client, auth_headers):
        resp = client.get(
            f"/api/projects/{uuid.uuid4()}/my-tasks",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Project not found"

    def test_no_assignments_returns_empty_page(
        self, client, auth_headers, assignment_project
    ):
        p = assignment_project
        resp = client.get(
            f"/api/projects/{p['project'].id}/my-tasks",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["tasks"] == []
        assert data["pages"] == 0

    def test_search_filter_narrows_results(
        self, client, auth_headers, assignment_project, test_db
    ):
        """The ``search`` ILIKE branch matches task JSON data. Task i carries
        the term ``unique-term-i`` in its data, so searching for one term
        returns exactly that assigned task."""
        p = assignment_project
        annotator = p["users"]["annotator"]

        # Assign tasks 0, 1, 2 to the annotator.
        for i in range(3):
            test_db.add(
                TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=p["tasks"][i].id,
                    user_id=annotator.id,
                    assigned_by=p["users"]["admin"].id,
                    status="assigned",
                )
            )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p['project'].id}/my-tasks?search=unique-term-1",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["tasks"][0]["id"] == p["tasks"][1].id
        # has_feedback is the community-edition (no extended) empty-set branch.
        assert data["tasks"][0]["has_feedback"] is False
        assert data["tasks"][0]["assignment"]["status"] == "assigned"

    def test_status_filter_only_matching(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        annotator = p["users"]["annotator"]
        # 2 assigned, 1 completed.
        for i in range(3):
            test_db.add(
                TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=p["tasks"][i].id,
                    user_id=annotator.id,
                    assigned_by=p["users"]["admin"].id,
                    status="completed" if i == 2 else "assigned",
                )
            )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p['project'].id}/my-tasks?status=completed",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["tasks"][0]["assignment"]["status"] == "completed"
