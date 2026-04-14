"""Integration tests for skip_queue project setting.

Tests verify that the task listing and next-task endpoints correctly filter
out skipped tasks based on the project's skip_queue mode:
  - requeue_for_me: skipped tasks stay visible to the same user
  - requeue_for_others: skipped tasks hidden from skipping user, visible to others
  - ignore_skipped: skipped tasks hidden from all users
"""

import uuid
from typing import List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import User
from project_models import (
    Project,
    ProjectMember,
    ProjectOrganization,
    SkippedTask,
    Task,
)


def _create_skip_queue_project(
    test_db: Session,
    test_users: List[User],
    test_org,
    skip_queue: str = "requeue_for_others",
    num_tasks: int = 4,
):
    """Create a project with tasks and skip_queue setting."""
    project = Project(
        id=str(uuid.uuid4()),
        title=f"Skip Queue Test ({skip_queue})",
        description="Project for testing skip_queue filtering",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=test_users[0].id,
        is_published=True,
        assignment_mode="open",
        skip_queue=skip_queue,
    )
    test_db.add(project)
    test_db.flush()

    # Link to org
    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project.id,
        organization_id=test_org.id,
        assigned_by=test_users[0].id,
    )
    test_db.add(project_org)

    # Add users as project members
    roles = ["admin", "contributor", "annotator"]
    for i, user in enumerate(test_users[:3]):
        member = ProjectMember(
            id=str(uuid.uuid4()),
            project_id=project.id,
            user_id=user.id,
            role=roles[i],
            is_active=True,
        )
        test_db.add(member)

    # Create tasks
    tasks = []
    for i in range(num_tasks):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Task {i + 1} for skip_queue={skip_queue}"},
            created_by=test_users[0].id,
            updated_by=test_users[0].id,
        )
        test_db.add(task)
        tasks.append(task)

    test_db.commit()
    return {
        "project": project,
        "tasks": tasks,
        "admin": test_users[0],
        "contributor": test_users[1],
        "annotator": test_users[2],
    }


def _skip_task(test_db: Session, task_id: str, project_id: str, user_id: str):
    """Create a SkippedTask record directly in the DB."""
    skip = SkippedTask(
        id=str(uuid.uuid4()),
        task_id=task_id,
        project_id=project_id,
        skipped_by=user_id,
    )
    test_db.add(skip)
    test_db.commit()
    return skip


@pytest.mark.integration
class TestSkipQueueTaskListing:
    """Test that GET /api/projects/{id}/tasks respects skip_queue when exclude_my_annotations=true."""

    def test_requeue_for_me_shows_skipped_tasks(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """With requeue_for_me, the user's own skipped tasks remain visible."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="requeue_for_me"
        )
        # Admin skips task 0
        _skip_task(test_db, data["tasks"][0].id, data["project"].id, data["admin"].id)

        resp = client.get(
            f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        task_ids = {t["id"] for t in resp.json()["items"]}

        # All 4 tasks should be returned (skipped task is requeued for me)
        assert data["tasks"][0].id in task_ids
        assert len(task_ids) == 4

    def test_requeue_for_others_hides_from_skipper(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """With requeue_for_others, skipped task is hidden from the user who skipped it."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="requeue_for_others"
        )
        _skip_task(test_db, data["tasks"][0].id, data["project"].id, data["admin"].id)

        resp = client.get(
            f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        task_ids = {t["id"] for t in resp.json()["items"]}

        # Skipped task should NOT appear for the user who skipped it
        assert data["tasks"][0].id not in task_ids
        assert len(task_ids) == 3

    def test_requeue_for_others_visible_to_other_users(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """With requeue_for_others, skipped task remains visible to other users."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="requeue_for_others"
        )
        # Admin skips task 0
        _skip_task(test_db, data["tasks"][0].id, data["project"].id, data["admin"].id)

        # Contributor should still see the skipped task
        resp = client.get(
            f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200
        task_ids = {t["id"] for t in resp.json()["items"]}

        assert data["tasks"][0].id in task_ids
        assert len(task_ids) == 4

    def test_ignore_skipped_hides_from_all_users(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """With ignore_skipped, a skipped task is hidden from ALL users."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="ignore_skipped"
        )
        # Admin skips task 0
        _skip_task(test_db, data["tasks"][0].id, data["project"].id, data["admin"].id)

        # Admin should not see it
        resp_admin = client.get(
            f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true",
            headers=auth_headers["admin"],
        )
        assert resp_admin.status_code == 200
        admin_task_ids = {t["id"] for t in resp_admin.json()["items"]}
        assert data["tasks"][0].id not in admin_task_ids
        assert len(admin_task_ids) == 3

        # Contributor should also not see it
        resp_contrib = client.get(
            f"/api/projects/{data['project'].id}/tasks?exclude_my_annotations=true",
            headers=auth_headers["contributor"],
        )
        assert resp_contrib.status_code == 200
        contrib_task_ids = {t["id"] for t in resp_contrib.json()["items"]}
        assert data["tasks"][0].id not in contrib_task_ids
        assert len(contrib_task_ids) == 3


@pytest.mark.integration
class TestSkipQueueNextTask:
    """Test that GET /api/projects/{id}/next respects skip_queue."""

    def test_requeue_for_me_returns_skipped_task(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """With requeue_for_me, next-task can return a previously skipped task."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="requeue_for_me", num_tasks=1
        )
        # Skip the only task
        _skip_task(test_db, data["tasks"][0].id, data["project"].id, data["admin"].id)

        resp = client.get(
            f"/api/projects/{data['project'].id}/next",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should still return the task (requeued for me)
        assert body.get("task") is not None
        assert body["task"]["id"] == data["tasks"][0].id

    def test_requeue_for_others_skips_for_skipper(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """With requeue_for_others, next-task excludes skipped task for the skipper."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="requeue_for_others", num_tasks=2
        )
        # Admin skips task 0
        _skip_task(test_db, data["tasks"][0].id, data["project"].id, data["admin"].id)

        resp = client.get(
            f"/api/projects/{data['project'].id}/next",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should return task 1, not task 0
        assert body.get("task") is not None
        assert body["task"]["id"] != data["tasks"][0].id

    def test_requeue_for_others_available_for_other_user(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """With requeue_for_others, next-task still returns skipped task for other users."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="requeue_for_others", num_tasks=1
        )
        _skip_task(test_db, data["tasks"][0].id, data["project"].id, data["admin"].id)

        # Admin gets no tasks
        resp_admin = client.get(
            f"/api/projects/{data['project'].id}/next",
            headers=auth_headers["admin"],
        )
        assert resp_admin.json().get("task") is None

        # Contributor still gets the task
        resp_contrib = client.get(
            f"/api/projects/{data['project'].id}/next",
            headers=auth_headers["contributor"],
        )
        assert resp_contrib.status_code == 200
        assert resp_contrib.json()["task"]["id"] == data["tasks"][0].id

    def test_ignore_skipped_hides_from_everyone(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """With ignore_skipped, next-task excludes skipped task for ALL users."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="ignore_skipped", num_tasks=1
        )
        _skip_task(test_db, data["tasks"][0].id, data["project"].id, data["admin"].id)

        # Admin gets no tasks
        resp_admin = client.get(
            f"/api/projects/{data['project'].id}/next",
            headers=auth_headers["admin"],
        )
        assert resp_admin.json().get("task") is None

        # Contributor also gets no tasks
        resp_contrib = client.get(
            f"/api/projects/{data['project'].id}/next",
            headers=auth_headers["contributor"],
        )
        assert resp_contrib.json().get("task") is None

    def test_skip_queue_via_api_endpoint(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Test the full skip flow: skip via API, then verify next-task respects it."""
        data = _create_skip_queue_project(
            test_db, test_users, test_org, skip_queue="requeue_for_others", num_tasks=2
        )

        # Skip task 0 via the API endpoint
        resp_skip = client.post(
            f"/api/projects/{data['project'].id}/tasks/{data['tasks'][0].id}/skip",
            json={"comment": None},
            headers=auth_headers["admin"],
        )
        assert resp_skip.status_code == 200

        # Admin should get task 1 (not 0)
        resp_next = client.get(
            f"/api/projects/{data['project'].id}/next",
            headers=auth_headers["admin"],
        )
        assert resp_next.status_code == 200
        assert resp_next.json()["task"]["id"] == data["tasks"][1].id

        # Contributor should get task 0 (admin's skip doesn't affect them)
        resp_contrib = client.get(
            f"/api/projects/{data['project'].id}/next",
            headers=auth_headers["contributor"],
        )
        assert resp_contrib.status_code == 200
        assert resp_contrib.json()["task"]["id"] == data["tasks"][0].id


@pytest.mark.integration
class TestSkipQueueProjectSetting:
    """Test that skip_queue can be read and updated via the project API."""

    def test_default_skip_queue_value(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """New projects should default to requeue_for_others."""
        data = _create_skip_queue_project(test_db, test_users, test_org)

        resp = client.get(
            f"/api/projects/{data['project'].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["skip_queue"] == "requeue_for_others"

    def test_update_skip_queue(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """skip_queue can be updated via PATCH."""
        data = _create_skip_queue_project(test_db, test_users, test_org)

        resp = client.patch(
            f"/api/projects/{data['project'].id}",
            json={"skip_queue": "ignore_skipped"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["skip_queue"] == "ignore_skipped"

    def test_invalid_skip_queue_rejected(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Invalid skip_queue values should be rejected."""
        data = _create_skip_queue_project(test_db, test_users, test_org)

        resp = client.patch(
            f"/api/projects/{data['project'].id}",
            json={"skip_queue": "invalid_value"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422
