"""Integration tests for skip_queue project setting.

Tests verify that the task listing and next-task endpoints correctly filter
out skipped tasks based on the project's skip_queue mode:
  - requeue_for_me: skipped tasks stay visible to the same user
  - requeue_for_others: skipped tasks hidden from skipping user, visible to others
  - ignore_skipped: skipped tasks hidden from all users

All endpoints exercised here are on the async DB lane
(``Depends(get_async_db)``): the task listing (``GET
/api/projects/{id}/tasks``), next-task (``GET /api/projects/{id}/next``),
skip (``POST /api/projects/{id}/tasks/{task_id}/skip``), and the project
GET/PATCH (``crud.py``). They are therefore seeded via ``async_test_db`` and
driven through ``async_test_client``; ``require_user`` is overridden per actor
via ``_as_user`` so the handler's async session sees the seeded rows (the sync
auth dependency can't see the async test transaction).

Acting users are seeded as superadmins so ``check_project_accessible_async``
short-circuits True without org-context plumbing. With ``assignment_mode="open"``
the annotator-assignment filter never triggers regardless of role, and skip
filtering is keyed purely on ``current_user.id`` — distinct identities are all
the assertions need to model "admin skips, contributor/other still sees".
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import (
    Project,
    ProjectMember,
    ProjectOrganization,
    SkippedTask,
    Task,
)

pytestmark = pytest.mark.asyncio


def _uid():
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


async def _make_user(db):
    u = User(
        id=_uid(),
        username=f"skipq-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Skip Queue User",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, creator_id):
    from models import Organization

    org = Organization(
        id=_uid(),
        name=f"skipq-org-{_uid()[:8]}",
        slug=f"skipq-org-{_uid()[:8]}",
        display_name="Skip Queue Org",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    return org


async def _create_skip_queue_project(
    db,
    users: List[User],
    org,
    skip_queue: str = "requeue_for_others",
    num_tasks: int = 4,
):
    """Create a project with tasks and skip_queue setting (async-seeded)."""
    project = Project(
        id=_uid(),
        title=f"Skip Queue Test ({skip_queue})",
        description="Project for testing skip_queue filtering",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=users[0].id,
        is_published=True,
        assignment_mode="open",
        skip_queue=skip_queue,
    )
    db.add(project)
    await db.flush()

    # Link to org
    project_org = ProjectOrganization(
        id=_uid(),
        project_id=project.id,
        organization_id=org.id,
        assigned_by=users[0].id,
    )
    db.add(project_org)

    # Add users as project members
    roles = ["admin", "contributor", "annotator"]
    for i, user in enumerate(users[:3]):
        member = ProjectMember(
            id=_uid(),
            project_id=project.id,
            user_id=user.id,
            role=roles[i],
            is_active=True,
        )
        db.add(member)

    # Create tasks
    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Task {i + 1} for skip_queue={skip_queue}"},
            created_by=users[0].id,
            updated_by=users[0].id,
        )
        db.add(task)
        tasks.append(task)

    await db.flush()
    return {
        "project": project,
        "tasks": tasks,
        "admin": users[0],
        "contributor": users[1],
        "annotator": users[2],
    }


async def _skip_task(db, task_id: str, project_id: str, user_id: str):
    """Create a SkippedTask record directly in the DB (async-seeded)."""
    skip = SkippedTask(
        id=_uid(),
        task_id=task_id,
        project_id=project_id,
        skipped_by=user_id,
    )
    db.add(skip)
    await db.flush()
    return skip


async def _seed_users(db):
    """Three distinct superadmin actors (admin, contributor, annotator)."""
    return [await _make_user(db) for _ in range(3)]


@pytest.mark.integration
class TestSkipQueueTaskListing:
    """Test that GET /api/projects/{id}/tasks respects skip_queue when exclude_my_annotations=true."""

    async def test_requeue_for_me_shows_skipped_tasks(
        self, async_test_client, async_test_db
    ):
        """With requeue_for_me, the user's own skipped tasks remain visible."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="requeue_for_me"
        )
        # Admin skips task 0
        await _skip_task(
            async_test_db, data["tasks"][0].id, data["project"].id, data["admin"].id
        )
        await async_test_db.commit()

        with _as_user(data["admin"]):
            resp = await async_test_client.get(
                f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true"
            )
        assert resp.status_code == 200
        task_ids = {t["id"] for t in resp.json()["items"]}

        # All 4 tasks should be returned (skipped task is requeued for me)
        assert data["tasks"][0].id in task_ids
        assert len(task_ids) == 4

    async def test_requeue_for_others_hides_from_skipper(
        self, async_test_client, async_test_db
    ):
        """With requeue_for_others, skipped task is hidden from the user who skipped it."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="requeue_for_others"
        )
        await _skip_task(
            async_test_db, data["tasks"][0].id, data["project"].id, data["admin"].id
        )
        await async_test_db.commit()

        with _as_user(data["admin"]):
            resp = await async_test_client.get(
                f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true"
            )
        assert resp.status_code == 200
        task_ids = {t["id"] for t in resp.json()["items"]}

        # Skipped task should NOT appear for the user who skipped it
        assert data["tasks"][0].id not in task_ids
        assert len(task_ids) == 3

    async def test_requeue_for_others_visible_to_other_users(
        self, async_test_client, async_test_db
    ):
        """With requeue_for_others, skipped task remains visible to other users."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="requeue_for_others"
        )
        # Admin skips task 0
        await _skip_task(
            async_test_db, data["tasks"][0].id, data["project"].id, data["admin"].id
        )
        await async_test_db.commit()

        # Contributor should still see the skipped task
        with _as_user(data["contributor"]):
            resp = await async_test_client.get(
                f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true"
            )
        assert resp.status_code == 200
        task_ids = {t["id"] for t in resp.json()["items"]}

        assert data["tasks"][0].id in task_ids
        assert len(task_ids) == 4

    async def test_ignore_skipped_hides_from_all_users(
        self, async_test_client, async_test_db
    ):
        """With ignore_skipped, a skipped task is hidden from ALL users."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="ignore_skipped"
        )
        # Admin skips task 0
        await _skip_task(
            async_test_db, data["tasks"][0].id, data["project"].id, data["admin"].id
        )
        await async_test_db.commit()

        # Admin should not see it
        with _as_user(data["admin"]):
            resp_admin = await async_test_client.get(
                f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true"
            )
        assert resp_admin.status_code == 200
        admin_task_ids = {t["id"] for t in resp_admin.json()["items"]}
        assert data["tasks"][0].id not in admin_task_ids
        assert len(admin_task_ids) == 3

        # Contributor should also not see it
        with _as_user(data["contributor"]):
            resp_contrib = await async_test_client.get(
                f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true"
            )
        assert resp_contrib.status_code == 200
        contrib_task_ids = {t["id"] for t in resp_contrib.json()["items"]}
        assert data["tasks"][0].id not in contrib_task_ids
        assert len(contrib_task_ids) == 3


@pytest.mark.integration
class TestSkipQueueNextTask:
    """Test that GET /api/projects/{id}/next respects skip_queue."""

    async def test_requeue_for_me_returns_skipped_task(
        self, async_test_client, async_test_db
    ):
        """With requeue_for_me, next-task can return a previously skipped task."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="requeue_for_me", num_tasks=1
        )
        # Skip the only task
        await _skip_task(
            async_test_db, data["tasks"][0].id, data["project"].id, data["admin"].id
        )
        await async_test_db.commit()

        with _as_user(data["admin"]):
            resp = await async_test_client.get(
                f"/api/projects/{data['project'].id}/next"
            )
        assert resp.status_code == 200
        body = resp.json()
        # Should still return the task (requeued for me)
        assert body.get("task") is not None
        assert body["task"]["id"] == data["tasks"][0].id

    async def test_requeue_for_others_skips_for_skipper(
        self, async_test_client, async_test_db
    ):
        """With requeue_for_others, next-task excludes skipped task for the skipper."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="requeue_for_others", num_tasks=2
        )
        # Admin skips task 0
        await _skip_task(
            async_test_db, data["tasks"][0].id, data["project"].id, data["admin"].id
        )
        await async_test_db.commit()

        with _as_user(data["admin"]):
            resp = await async_test_client.get(
                f"/api/projects/{data['project'].id}/next"
            )
        assert resp.status_code == 200
        body = resp.json()
        # Should return task 1, not task 0
        assert body.get("task") is not None
        assert body["task"]["id"] != data["tasks"][0].id

    async def test_requeue_for_others_available_for_other_user(
        self, async_test_client, async_test_db
    ):
        """With requeue_for_others, next-task still returns skipped task for other users."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="requeue_for_others", num_tasks=1
        )
        await _skip_task(
            async_test_db, data["tasks"][0].id, data["project"].id, data["admin"].id
        )
        await async_test_db.commit()

        # Admin gets no tasks
        with _as_user(data["admin"]):
            resp_admin = await async_test_client.get(
                f"/api/projects/{data['project'].id}/next"
            )
        assert resp_admin.json().get("task") is None

        # Contributor still gets the task
        with _as_user(data["contributor"]):
            resp_contrib = await async_test_client.get(
                f"/api/projects/{data['project'].id}/next"
            )
        assert resp_contrib.status_code == 200
        assert resp_contrib.json()["task"]["id"] == data["tasks"][0].id

    async def test_ignore_skipped_hides_from_everyone(
        self, async_test_client, async_test_db
    ):
        """With ignore_skipped, next-task excludes skipped task for ALL users."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="ignore_skipped", num_tasks=1
        )
        await _skip_task(
            async_test_db, data["tasks"][0].id, data["project"].id, data["admin"].id
        )
        await async_test_db.commit()

        # Admin gets no tasks
        with _as_user(data["admin"]):
            resp_admin = await async_test_client.get(
                f"/api/projects/{data['project'].id}/next"
            )
        assert resp_admin.json().get("task") is None

        # Contributor also gets no tasks
        with _as_user(data["contributor"]):
            resp_contrib = await async_test_client.get(
                f"/api/projects/{data['project'].id}/next"
            )
        assert resp_contrib.json().get("task") is None

    async def test_skip_queue_via_api_endpoint(
        self, async_test_client, async_test_db
    ):
        """Test the full skip flow: skip via API, then verify next-task respects it."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(
            async_test_db, users, org, skip_queue="requeue_for_others", num_tasks=2
        )
        await async_test_db.commit()

        # Skip task 0 via the API endpoint
        with _as_user(data["admin"]):
            resp_skip = await async_test_client.post(
                f"/api/projects/{data['project'].id}/tasks/{data['tasks'][0].id}/skip",
                json={"comment": None},
            )
        assert resp_skip.status_code == 200

        # Admin should get task 1 (not 0)
        with _as_user(data["admin"]):
            resp_next = await async_test_client.get(
                f"/api/projects/{data['project'].id}/next"
            )
        assert resp_next.status_code == 200
        assert resp_next.json()["task"]["id"] == data["tasks"][1].id

        # Contributor should get task 0 (admin's skip doesn't affect them)
        with _as_user(data["contributor"]):
            resp_contrib = await async_test_client.get(
                f"/api/projects/{data['project'].id}/next"
            )
        assert resp_contrib.status_code == 200
        assert resp_contrib.json()["task"]["id"] == data["tasks"][0].id


@pytest.mark.integration
class TestSkipQueueProjectSetting:
    """Test that skip_queue can be read and updated via the project API."""

    async def test_default_skip_queue_value(
        self, async_test_client, async_test_db
    ):
        """New projects should default to requeue_for_others."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(async_test_db, users, org)
        await async_test_db.commit()

        with _as_user(data["admin"]):
            resp = await async_test_client.get(
                f"/api/projects/{data['project'].id}"
            )
        assert resp.status_code == 200
        assert resp.json()["skip_queue"] == "requeue_for_others"

    async def test_update_skip_queue(
        self, async_test_client, async_test_db
    ):
        """skip_queue can be updated via PATCH."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(async_test_db, users, org)
        await async_test_db.commit()

        with _as_user(data["admin"]):
            resp = await async_test_client.patch(
                f"/api/projects/{data['project'].id}",
                json={"skip_queue": "ignore_skipped"},
            )
        assert resp.status_code == 200
        assert resp.json()["skip_queue"] == "ignore_skipped"

    async def test_invalid_skip_queue_rejected(
        self, async_test_client, async_test_db
    ):
        """Invalid skip_queue values should be rejected."""
        users = await _seed_users(async_test_db)
        org = await _make_org(async_test_db, users[0].id)
        data = await _create_skip_queue_project(async_test_db, users, org)
        await async_test_db.commit()

        with _as_user(data["admin"]):
            resp = await async_test_client.patch(
                f"/api/projects/{data['project'].id}",
                json={"skip_queue": "invalid_value"},
            )
        assert resp.status_code == 422
