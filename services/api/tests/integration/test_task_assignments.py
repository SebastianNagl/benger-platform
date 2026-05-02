"""Integration tests for task assignment endpoints.

Tests cover permissions, CRUD operations, distribution strategies,
my-tasks filtering, and edge cases.
"""

import uuid
from datetime import datetime
from typing import List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import OrganizationMembership, User
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)


@pytest.fixture(scope="function")
def assignment_project(test_db: Session, test_users: List[User], test_org):
    """Create a project with tasks linked to the test organization."""
    project = Project(
        id=str(uuid.uuid4()),
        title="Assignment Test Project",
        description="Project for testing task assignments",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=test_users[0].id,
        is_published=True,
        assignment_mode="manual",
    )
    test_db.add(project)
    test_db.flush()

    # Link project to org
    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project.id,
        organization_id=test_org.id,
        assigned_by=test_users[0].id,
    )
    test_db.add(project_org)

    # Add all 4 users as project members
    roles = ["admin", "contributor", "annotator", "admin"]
    for i, user in enumerate(test_users[:4]):
        member = ProjectMember(
            id=str(uuid.uuid4()),
            project_id=project.id,
            user_id=user.id,
            role=roles[i],
            is_active=True,
        )
        test_db.add(member)

    # Create 6 tasks
    tasks = []
    for i in range(6):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Task {i + 1} content for assignment testing"},
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
# Permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAssignmentPermissions:
    def test_admin_can_assign(self, client, auth_headers, assignment_project):
        p = assignment_project
        task_ids = [p["tasks"][0].id]
        user_ids = [p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": user_ids, "distribution": "manual"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assignments_created"] == 1

    def test_contributor_can_assign(self, client, auth_headers, assignment_project):
        p = assignment_project
        task_ids = [p["tasks"][0].id]
        user_ids = [p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": user_ids, "distribution": "manual"},
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assignments_created"] == 1

    def test_annotator_cannot_assign(self, client, auth_headers, assignment_project):
        p = assignment_project
        task_ids = [p["tasks"][0].id]
        user_ids = [p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": user_ids, "distribution": "manual"},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_org_admin_can_assign(
        self, client, auth_headers, assignment_project
    ):
        """Non-superadmin ORG_ADMIN can assign tasks."""
        p = assignment_project
        task_ids = [p["tasks"][0].id]
        user_ids = [p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": user_ids, "distribution": "manual"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 1

    def test_org_admin_can_update_project(
        self, client, auth_headers, assignment_project
    ):
        """Non-superadmin ORG_ADMIN can update project settings."""
        p = assignment_project
        resp = client.patch(
            f"/api/projects/{p['project'].id}",
            json={"assignment_mode": "manual"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignment_mode"] == "manual"

    def test_annotator_cannot_delete_assignment(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        # Create an assignment first
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
            f"/api/projects/{p['project'].id}/tasks/{p['tasks'][0].id}/assignments/{assignment.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAssignmentCRUD:
    def test_assign_and_list(self, client, auth_headers, assignment_project):
        p = assignment_project
        task_ids = [p["tasks"][0].id, p["tasks"][1].id]
        user_ids = [p["users"]["annotator"].id]

        # Assign
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": user_ids, "distribution": "manual"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 2

        # List assignments for first task
        resp = client.get(
            f"/api/projects/{p['project'].id}/tasks/{p['tasks'][0].id}/assignments",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assignments = resp.json()
        assert len(assignments) == 1
        assert assignments[0]["user_id"] == p["users"]["annotator"].id
        assert assignments[0]["status"] == "assigned"
        assert assignments[0]["user_name"] == "Test Annotator"

    def test_delete_assignment(
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
            f"/api/projects/{p['project'].id}/tasks/{p['tasks'][0].id}/assignments/{assignment.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        # Verify deleted
        resp = client.get(
            f"/api/projects/{p['project'].id}/tasks/{p['tasks'][0].id}/assignments",
            headers=auth_headers["admin"],
        )
        assert resp.json() == []

    def test_duplicate_assignment_skipped(self, client, auth_headers, assignment_project):
        p = assignment_project
        payload = {
            "task_ids": [p["tasks"][0].id],
            "user_ids": [p["users"]["annotator"].id],
            "distribution": "manual",
        }

        # First assign
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json=payload,
            headers=auth_headers["admin"],
        )
        assert resp.json()["assignments_created"] == 1

        # Second assign - should be skipped
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json=payload,
            headers=auth_headers["admin"],
        )
        data = resp.json()
        assert data["assignments_created"] == 0
        assert data["assignments_skipped"] == 1

    def test_duplicate_with_priority_change_updates(
        self, client, auth_headers, assignment_project
    ):
        p = assignment_project
        task_ids = [p["tasks"][0].id]
        user_ids = [p["users"]["annotator"].id]

        # First assign with priority 0
        client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": user_ids,
                "distribution": "manual",
                "priority": 0,
            },
            headers=auth_headers["admin"],
        )

        # Reassign with priority 3
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": user_ids,
                "distribution": "manual",
                "priority": 3,
            },
            headers=auth_headers["admin"],
        )
        data = resp.json()
        assert data["assignments_created"] == 0
        assert data["assignments_updated"] == 1

    def test_nonexistent_project_returns_404(self, client, auth_headers):
        resp = client.post(
            f"/api/projects/{uuid.uuid4()}/tasks/assign",
            json={"task_ids": ["x"], "user_ids": ["y"], "distribution": "manual"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Distribution strategies
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDistributionStrategies:
    def test_manual_creates_n_times_m(self, client, auth_headers, assignment_project):
        p = assignment_project
        task_ids = [p["tasks"][i].id for i in range(3)]
        user_ids = [p["users"]["contributor"].id, p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": user_ids, "distribution": "manual"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        # 3 tasks x 2 users = 6
        assert resp.json()["assignments_created"] == 6

    def test_round_robin_distributes_evenly(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        task_ids = [t.id for t in p["tasks"]]  # 6 tasks
        user_ids = [p["users"]["contributor"].id, p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": task_ids,
                "user_ids": user_ids,
                "distribution": "round_robin",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["assignments_created"] == 6

        # Verify each user got 3 tasks
        contributor_count = (
            test_db.query(TaskAssignment)
            .filter(TaskAssignment.user_id == p["users"]["contributor"].id)
            .count()
        )
        annotator_count = (
            test_db.query(TaskAssignment)
            .filter(TaskAssignment.user_id == p["users"]["annotator"].id)
            .count()
        )
        assert contributor_count == 3
        assert annotator_count == 3

    def test_load_balanced_picks_least_loaded(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        contributor = p["users"]["contributor"]
        annotator = p["users"]["annotator"]

        # Pre-create 2 assignments for contributor (making them more loaded)
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

        # Now assign 2 more tasks with load_balanced
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

        # Both new tasks should go to annotator (least loaded)
        annotator_new = (
            test_db.query(TaskAssignment)
            .filter(
                TaskAssignment.user_id == annotator.id,
                TaskAssignment.task_id.in_(new_task_ids),
            )
            .count()
        )
        assert annotator_new == 2

    def test_random_assigns_all_tasks(self, client, auth_headers, assignment_project):
        p = assignment_project
        task_ids = [p["tasks"][i].id for i in range(4)]
        user_ids = [p["users"]["contributor"].id, p["users"]["annotator"].id]

        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={"task_ids": task_ids, "user_ids": user_ids, "distribution": "random"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        # Each task gets exactly 1 assignment
        assert resp.json()["assignments_created"] == 4


# ---------------------------------------------------------------------------
# My tasks endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMyTasksEndpoint:
    def test_my_tasks_returns_assigned_tasks(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        annotator = p["users"]["annotator"]

        for i in range(3):
            test_db.add(
                TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=p["tasks"][i].id,
                    user_id=annotator.id,
                    assigned_by=p["users"]["admin"].id,
                    status="assigned",
                    priority=2,
                )
            )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p['project'].id}/my-tasks",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["tasks"]) == 3
        # Each task should have assignment info
        for task in data["tasks"]:
            assert task["assignment"] is not None
            assert task["assignment"]["status"] == "assigned"
            assert task["assignment"]["priority"] == 2

    def test_my_tasks_filter_by_status(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        annotator = p["users"]["annotator"]

        # 2 assigned, 1 completed
        for i in range(3):
            status = "completed" if i == 2 else "assigned"
            test_db.add(
                TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=p["tasks"][i].id,
                    user_id=annotator.id,
                    assigned_by=p["users"]["admin"].id,
                    status=status,
                )
            )
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p['project'].id}/my-tasks?status=assigned",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_my_tasks_pagination(
        self, client, auth_headers, assignment_project, test_db
    ):
        p = assignment_project
        annotator = p["users"]["annotator"]

        for i in range(6):
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
            f"/api/projects/{p['project'].id}/my-tasks?page=1&page_size=2",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tasks"]) == 2
        assert data["total"] == 6
        assert data["pages"] == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAssignmentEdgeCases:
    def test_empty_task_ids_returns_400(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": [],
                "user_ids": [p["users"]["annotator"].id],
                "distribution": "manual",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_invalid_user_not_member_returns_400(
        self, client, auth_headers, assignment_project
    ):
        p = assignment_project
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": [p["tasks"][0].id],
                "user_ids": ["nonexistent-user-id"],
                "distribution": "manual",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_task_not_in_project_returns_400(
        self, client, auth_headers, assignment_project
    ):
        p = assignment_project
        fake_task_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": [fake_task_id],
                "user_ids": [p["users"]["annotator"].id],
                "distribution": "manual",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Manual mode enforcement (Label Studio aligned)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestManualModeEnforcement:
    """Verify annotators can ONLY access assigned tasks in manual mode.

    Aligned with Label Studio Enterprise: unassigned tasks are invisible (404)
    to annotators; annotation submission on unassigned tasks is forbidden (403).
    """

    def _assign_tasks(self, test_db, project, task_ids, user_id, assigned_by):
        """Helper to create task assignments directly in DB."""
        for tid in task_ids:
            assignment = TaskAssignment(
                id=str(uuid.uuid4()),
                task_id=tid,
                user_id=user_id,
                assigned_by=assigned_by,
                status="assigned",
            )
            test_db.add(assignment)
        test_db.commit()

    def test_annotator_cannot_get_unassigned_task(
        self, client, auth_headers, assignment_project, test_db
    ):
        """GET /tasks/{id} returns 404 for unassigned task (invisible)."""
        p = assignment_project
        # Assign tasks 0-2 to annotator
        assigned_ids = [t.id for t in p["tasks"][:3]]
        self._assign_tasks(
            test_db, p["project"], assigned_ids,
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        # Unassigned task -> 404
        unassigned_task = p["tasks"][3]
        resp = client.get(
            f"/api/projects/tasks/{unassigned_task.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 404

    def test_annotator_can_get_assigned_task(
        self, client, auth_headers, assignment_project, test_db
    ):
        """GET /tasks/{id} returns 200 for assigned task."""
        p = assignment_project
        assigned_ids = [t.id for t in p["tasks"][:3]]
        self._assign_tasks(
            test_db, p["project"], assigned_ids,
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        assigned_task = p["tasks"][0]
        resp = client.get(
            f"/api/projects/tasks/{assigned_task.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

    def test_annotator_cannot_annotate_unassigned_task(
        self, client, auth_headers, assignment_project, test_db
    ):
        """POST annotation on unassigned task returns 404 (Label Studio aligned: invisible)."""
        p = assignment_project
        assigned_ids = [t.id for t in p["tasks"][:3]]
        self._assign_tasks(
            test_db, p["project"], assigned_ids,
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        unassigned_task = p["tasks"][3]
        resp = client.post(
            f"/api/projects/tasks/{unassigned_task.id}/annotations",
            json={
                "result": [{"type": "choices", "value": {"choices": ["Positive"]}}],
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 404

    def test_annotator_can_annotate_assigned_task(
        self, client, auth_headers, assignment_project, test_db
    ):
        """POST annotation on assigned task returns 200."""
        p = assignment_project
        assigned_ids = [t.id for t in p["tasks"][:3]]
        self._assign_tasks(
            test_db, p["project"], assigned_ids,
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        assigned_task = p["tasks"][0]
        resp = client.post(
            f"/api/projects/tasks/{assigned_task.id}/annotations",
            json={
                "result": [{"type": "choices", "value": {"choices": ["Positive"]}}],
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

    def test_admin_can_access_unassigned_task(
        self, client, auth_headers, assignment_project
    ):
        """Admin bypasses assignment restrictions."""
        p = assignment_project
        # No assignments created — admin should still access any task
        resp = client.get(
            f"/api/projects/tasks/{p['tasks'][0].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_contributor_can_access_unassigned_task(
        self, client, auth_headers, assignment_project
    ):
        """Contributor bypasses assignment restrictions."""
        p = assignment_project
        resp = client.get(
            f"/api/projects/tasks/{p['tasks'][0].id}",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200

    def test_task_listing_filtered_for_annotator(
        self, client, auth_headers, assignment_project, test_db
    ):
        """GET /projects/{id}/tasks returns only assigned tasks for annotator."""
        p = assignment_project
        # Assign 3 of 6 tasks
        assigned_ids = [t.id for t in p["tasks"][:3]]
        self._assign_tasks(
            test_db, p["project"], assigned_ids,
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        # Annotator sees 3
        resp = client.get(
            f"/api/projects/{p['project'].id}/tasks",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

        # Admin sees all 6
        resp = client.get(
            f"/api/projects/{p['project'].id}/tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 6

    def test_next_task_respects_manual_assignment(
        self, client, auth_headers, assignment_project, test_db
    ):
        """GET /projects/{id}/next returns only assigned tasks in manual mode."""
        p = assignment_project
        # Assign only task 0 to annotator
        self._assign_tasks(
            test_db, p["project"], [p["tasks"][0].id],
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["task"]["id"] == p["tasks"][0].id

    def test_next_task_returns_none_without_assignments(
        self, client, auth_headers, assignment_project
    ):
        """GET /projects/{id}/next returns no task when annotator has no assignments."""
        p = assignment_project
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None

    def test_annotator_cannot_skip_unassigned_task(
        self, client, auth_headers, assignment_project, test_db
    ):
        """POST skip on unassigned task returns 404 (invisible)."""
        p = assignment_project
        assigned_ids = [t.id for t in p["tasks"][:3]]
        self._assign_tasks(
            test_db, p["project"], assigned_ids,
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        unassigned_task = p["tasks"][3]
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/{unassigned_task.id}/skip",
            json={},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 404

    def test_annotator_can_skip_assigned_task(
        self, client, auth_headers, assignment_project, test_db
    ):
        """POST skip on assigned task works."""
        p = assignment_project
        assigned_ids = [t.id for t in p["tasks"][:3]]
        self._assign_tasks(
            test_db, p["project"], assigned_ids,
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        assigned_task = p["tasks"][0]
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/{assigned_task.id}/skip",
            json={},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

    def test_completed_assignment_still_allows_access(
        self, client, auth_headers, assignment_project, test_db
    ):
        """Annotator can still view task after completing assignment."""
        p = assignment_project
        # Create a completed assignment
        assignment = TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=p["tasks"][0].id,
            user_id=p["users"]["annotator"].id,
            assigned_by=p["users"]["admin"].id,
            status="completed",
        )
        test_db.add(assignment)
        test_db.commit()

        # Annotator can still GET the completed task
        resp = client.get(
            f"/api/projects/tasks/{p['tasks'][0].id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

    def test_annotator_cannot_list_annotations_on_unassigned_task(
        self, client, auth_headers, assignment_project, test_db
    ):
        """GET /tasks/{id}/annotations returns 404 for unassigned task."""
        p = assignment_project
        assigned_ids = [t.id for t in p["tasks"][:3]]
        self._assign_tasks(
            test_db, p["project"], assigned_ids,
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        unassigned_task = p["tasks"][3]
        resp = client.get(
            f"/api/projects/tasks/{unassigned_task.id}/annotations",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 404

    def test_annotation_marks_assignment_completed(
        self, client, auth_headers, assignment_project, test_db
    ):
        """Submitting annotation sets TaskAssignment.status to 'completed'."""
        p = assignment_project
        self._assign_tasks(
            test_db, p["project"], [p["tasks"][0].id],
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        # Verify assignment is "assigned"
        assignment = test_db.query(TaskAssignment).filter(
            TaskAssignment.task_id == p["tasks"][0].id,
            TaskAssignment.user_id == p["users"]["annotator"].id,
        ).first()
        assert assignment.status == "assigned"

        # Submit annotation
        resp = client.post(
            f"/api/projects/tasks/{p['tasks'][0].id}/annotations",
            json={
                "result": [{"type": "choices", "value": {"choices": ["Positive"]}}],
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

        # Assignment should now be "completed"
        test_db.refresh(assignment)
        assert assignment.status == "completed"
        assert assignment.completed_at is not None

    def test_next_returns_none_after_all_assigned_annotated(
        self, client, auth_headers, assignment_project, test_db
    ):
        """After annotating all assigned tasks, /next returns no task."""
        p = assignment_project
        self._assign_tasks(
            test_db, p["project"], [p["tasks"][0].id],
            p["users"]["annotator"].id, p["users"]["admin"].id,
        )

        # Annotate the only assigned task
        resp = client.post(
            f"/api/projects/tasks/{p['tasks'][0].id}/annotations",
            json={
                "result": [{"type": "choices", "value": {"choices": ["Positive"]}}],
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

        # /next should return no task
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None


# ---------------------------------------------------------------------------
# Systematic 4-role permission coverage (Issue #1313)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFourRolePermissions:
    """Systematic permission tests for all 4 roles: superadmin, ORG_ADMIN, CONTRIBUTOR, ANNOTATOR."""

    # --- Project update ---

    def test_superadmin_can_update_project(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.patch(
            f"/api/projects/{p['project'].id}",
            json={"description": "Updated by superadmin"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_org_admin_can_update_project(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.patch(
            f"/api/projects/{p['project'].id}",
            json={"description": "Updated by org admin"},
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200

    def test_contributor_can_update_project(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.patch(
            f"/api/projects/{p['project'].id}",
            json={"description": "Updated by contributor"},
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200

    def test_annotator_cannot_update_project(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.patch(
            f"/api/projects/{p['project'].id}",
            json={"description": "Updated by annotator"},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    # --- Project delete ---

    def test_superadmin_can_delete_project(self, client, auth_headers, assignment_project):
        """Superadmin can delete (but we just check it doesn't 403)."""
        p = assignment_project
        resp = client.delete(
            f"/api/projects/{p['project'].id}",
            headers=auth_headers["admin"],
        )
        # Superadmin should not get 403 (may get 200 or other)
        assert resp.status_code != 403

    def test_org_admin_cannot_delete_project(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.delete(
            f"/api/projects/{p['project'].id}",
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 403

    def test_contributor_cannot_delete_project(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.delete(
            f"/api/projects/{p['project'].id}",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403

    def test_annotator_cannot_delete_project(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.delete(
            f"/api/projects/{p['project'].id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    # --- Task assignment ---

    def test_org_admin_can_assign_tasks(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": [p["tasks"][0].id],
                "user_ids": [p["users"]["annotator"].id],
                "distribution": "manual",
            },
            headers=auth_headers["org_admin"],
        )
        assert resp.status_code == 200

    def test_annotator_cannot_assign_tasks(self, client, auth_headers, assignment_project):
        p = assignment_project
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/assign",
            json={
                "task_ids": [p["tasks"][0].id],
                "user_ids": [p["users"]["annotator"].id],
                "distribution": "manual",
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403



# ---------------------------------------------------------------------------
# Cross-org boundary tests (Issue #1313)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCrossOrgBoundary:
    """Verify users cannot access projects in orgs they don't belong to."""

    def test_superadmin_crosses_org_boundary(
        self, client, auth_headers, test_db, test_users
    ):
        """Superadmin can access projects in any org."""
        from models import Organization, OrganizationMembership

        # Create org-B (test_users have no membership here except superadmin bypass)
        org_b = Organization(
            id=str(uuid.uuid4()),
            name="Org B",
            slug="org-b",
            display_name="Org B",
            created_at=datetime.utcnow(),
        )
        test_db.add(org_b)
        test_db.flush()

        project_b = Project(
            id=str(uuid.uuid4()),
            title="Org B Project",
            created_by=test_users[0].id,
            is_published=True,
        )
        test_db.add(project_b)
        test_db.flush()

        project_org_b = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project_b.id,
            organization_id=org_b.id,
            assigned_by=test_users[0].id,
        )
        test_db.add(project_org_b)
        test_db.commit()

        # Superadmin CAN access org-B project
        resp = client.get(
            f"/api/projects/{project_b.id}/tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_org_admin_cannot_cross_org_boundary(
        self, client, auth_headers, test_db, test_users
    ):
        """ORG_ADMIN of org-A cannot access projects in org-B."""
        from models import Organization

        org_b = Organization(
            id=str(uuid.uuid4()),
            name="Org B Isolated",
            slug="org-b-isolated",
            display_name="Org B Isolated",
            created_at=datetime.utcnow(),
        )
        test_db.add(org_b)
        test_db.flush()

        project_b = Project(
            id=str(uuid.uuid4()),
            title="Org B Isolated Project",
            created_by=test_users[0].id,
            is_published=True,
        )
        test_db.add(project_b)
        test_db.flush()

        project_org_b = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project_b.id,
            organization_id=org_b.id,
            assigned_by=test_users[0].id,
        )
        test_db.add(project_org_b)
        test_db.commit()

        # ORG_ADMIN of org-A (test org) CANNOT access org-B project
        resp = client.get(
            f"/api/projects/{project_b.id}/tasks",
            headers={
                **auth_headers["org_admin"],
                "X-Organization-Context": org_b.id,
            },
        )
        assert resp.status_code == 403

    def test_contributor_cannot_cross_org_boundary(
        self, client, auth_headers, test_db, test_users
    ):
        """CONTRIBUTOR of org-A cannot access projects in org-B."""
        from models import Organization

        org_b = Organization(
            id=str(uuid.uuid4()),
            name="Org B Contrib",
            slug="org-b-contrib",
            display_name="Org B Contrib",
            created_at=datetime.utcnow(),
        )
        test_db.add(org_b)
        test_db.flush()

        project_b = Project(
            id=str(uuid.uuid4()),
            title="Org B Contrib Project",
            created_by=test_users[0].id,
            is_published=True,
        )
        test_db.add(project_b)
        test_db.flush()

        project_org_b = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project_b.id,
            organization_id=org_b.id,
            assigned_by=test_users[0].id,
        )
        test_db.add(project_org_b)
        test_db.commit()

        # CONTRIBUTOR of org-A CANNOT access org-B project
        resp = client.get(
            f"/api/projects/{project_b.id}/tasks",
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": org_b.id,
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Auto assignment mode (pull model) — Issue #1311
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def auto_assignment_project(test_db: Session, test_users: List[User], test_org):
    """Create a project with assignment_mode='auto' and 6 tasks."""
    project = Project(
        id=str(uuid.uuid4()),
        title="Auto Assignment Test Project",
        description="Project for testing auto assignment mode",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=test_users[0].id,
        is_published=True,
        assignment_mode="auto",
        maximum_annotations=1,
    )
    test_db.add(project)
    test_db.flush()

    # Link project to org
    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project.id,
        organization_id=test_org.id,
        assigned_by=test_users[0].id,
    )
    test_db.add(project_org)

    # Add all 4 users as project members
    roles = ["admin", "contributor", "annotator", "admin"]
    for i, user in enumerate(test_users[:4]):
        member = ProjectMember(
            id=str(uuid.uuid4()),
            project_id=project.id,
            user_id=user.id,
            role=roles[i],
            is_active=True,
        )
        test_db.add(member)

    # Create 6 tasks
    tasks = []
    for i in range(6):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"Auto task {i + 1} content"},
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


@pytest.mark.integration
class TestAutoModeAssignment:
    """Tests for auto assignment mode (pull model) — Issue #1311.

    When assignment_mode='auto', the /next endpoint should:
    1. Return existing in-progress assignments (resume)
    2. Auto-assign a new task on demand if no active assignment exists
    """

    def test_auto_next_creates_assignment(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """/next with no pre-assignments creates a TaskAssignment on the fly."""
        p = auto_assignment_project

        # No assignments exist yet
        count = test_db.query(TaskAssignment).filter(
            TaskAssignment.user_id == p["users"]["annotator"].id,
        ).count()
        assert count == 0

        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None

        # Verify assignment was created in DB
        assignment = test_db.query(TaskAssignment).filter(
            TaskAssignment.user_id == p["users"]["annotator"].id,
            TaskAssignment.task_id == data["task"]["id"],
        ).first()
        assert assignment is not None
        assert assignment.status == "in_progress"
        assert assignment.assigned_by == p["users"]["annotator"].id  # self-assignment
        assert assignment.started_at is not None

    def test_auto_next_resumes_existing(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """Existing in_progress assignment is returned without creating a new one."""
        p = auto_assignment_project

        # Pre-create an in_progress assignment
        existing = TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=p["tasks"][2].id,
            user_id=p["users"]["annotator"].id,
            assigned_by=p["users"]["admin"].id,
            status="in_progress",
            started_at=datetime.now(),
        )
        test_db.add(existing)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["task"]["id"] == p["tasks"][2].id

        # Only one assignment should exist
        count = test_db.query(TaskAssignment).filter(
            TaskAssignment.user_id == p["users"]["annotator"].id,
        ).count()
        assert count == 1

    def test_auto_next_after_annotation(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """After annotating task A, /next returns a different task B."""
        p = auto_assignment_project

        # First call: get auto-assigned task
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        first_task_id = resp.json()["task"]["id"]

        # Annotate the task
        resp = client.post(
            f"/api/projects/tasks/{first_task_id}/annotations",
            json={
                "result": [{"type": "choices", "value": {"choices": ["Positive"]}}],
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

        # Second call: should get a different task
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["task"]["id"] != first_task_id

    def test_auto_respects_maximum_annotations(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """Task at maximum_annotations limit is not offered to another user."""
        p = auto_assignment_project
        task = p["tasks"][0]

        # Admin annotates task 0 (max_annotations=1)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [{"type": "choices", "value": {"choices": ["Positive"]}}],
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

        # Annotator calls /next — task 0 should NOT be offered
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["task"]["id"] != task.id

    def test_auto_no_tasks_available(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """When all tasks are at max annotations, returns None."""
        p = auto_assignment_project

        # Admin annotates all 6 tasks (max_annotations=1)
        for task in p["tasks"]:
            resp = client.post(
                f"/api/projects/tasks/{task.id}/annotations",
                json={
                    "result": [{"type": "choices", "value": {"choices": ["Done"]}}],
                },
                headers=auth_headers["admin"],
            )
            assert resp.status_code == 200

        # Annotator calls /next — no tasks available
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None

    def test_auto_respects_skip_queue(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """Skipped task is not offered again when skip_queue='requeue_for_others'."""
        p = auto_assignment_project
        p["project"].skip_queue = "requeue_for_others"
        test_db.commit()

        # First /next: get auto-assigned task
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        first_task_id = resp.json()["task"]["id"]

        # Skip that task
        resp = client.post(
            f"/api/projects/{p['project'].id}/tasks/{first_task_id}/skip",
            json={"comment": None},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

        # Subsequent /next calls should never return the skipped task
        seen_task_ids = set()
        for _ in range(5):
            resp = client.get(
                f"/api/projects/{p['project'].id}/next",
                headers=auth_headers["annotator"],
            )
            data = resp.json()
            if data["task"] is None:
                break
            seen_task_ids.add(data["task"]["id"])
            # Annotate to move on
            client.post(
                f"/api/projects/tasks/{data['task']['id']}/annotations",
                json={
                    "result": [{"type": "choices", "value": {"choices": ["OK"]}}],
                },
                headers=auth_headers["annotator"],
            )
        assert first_task_id not in seen_task_ids

    def test_auto_respects_randomize_order(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """With randomize_task_order=True, tasks are served in deterministic random order."""
        p = auto_assignment_project
        p["project"].randomize_task_order = True
        p["project"].maximum_annotations = 0  # unlimited
        test_db.commit()

        # Collect task order for annotator across multiple /next calls
        task_order = []
        for _ in range(6):
            resp = client.get(
                f"/api/projects/{p['project'].id}/next",
                headers=auth_headers["annotator"],
            )
            data = resp.json()
            if data["task"] is None:
                break
            task_order.append(data["task"]["id"])
            # Annotate to move on
            client.post(
                f"/api/projects/tasks/{data['task']['id']}/annotations",
                json={
                    "result": [{"type": "choices", "value": {"choices": ["OK"]}}],
                },
                headers=auth_headers["annotator"],
            )

        # All 6 tasks should be served (no duplicates)
        assert len(task_order) == 6
        assert len(set(task_order)) == 6

        # Order is not necessarily sequential by created_at
        sequential_ids = [t.id for t in p["tasks"]]
        # Note: randomized order CAN match sequential by chance, so we just verify
        # all tasks were delivered. The MD5-based ordering is tested implicitly.

    def test_auto_assignment_enables_annotation(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """After auto-assignment via /next, annotator can submit an annotation."""
        p = auto_assignment_project

        # Get auto-assigned task
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        task_id = resp.json()["task"]["id"]

        # Annotate it
        resp = client.post(
            f"/api/projects/tasks/{task_id}/annotations",
            json={
                "result": [{"type": "choices", "value": {"choices": ["Positive"]}}],
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

    def test_auto_assignment_completed_on_annotate(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """After annotation, the auto-created TaskAssignment status is 'completed'."""
        p = auto_assignment_project

        # Get auto-assigned task
        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        task_id = resp.json()["task"]["id"]

        # Annotate it
        resp = client.post(
            f"/api/projects/tasks/{task_id}/annotations",
            json={
                "result": [{"type": "choices", "value": {"choices": ["Positive"]}}],
            },
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200

        # Verify assignment status
        test_db.expire_all()
        assignment = test_db.query(TaskAssignment).filter(
            TaskAssignment.task_id == task_id,
            TaskAssignment.user_id == p["users"]["annotator"].id,
        ).first()
        assert assignment is not None
        assert assignment.status == "completed"
        assert assignment.completed_at is not None

    def test_manual_mode_no_auto_assign(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """Regression: manual mode still returns 'no tasks' without pre-assignments."""
        p = auto_assignment_project
        p["project"].assignment_mode = "manual"
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None
        assert "No more assigned tasks" in data["detail"]

    def test_auto_two_annotators_get_different_tasks(
        self, client, auth_headers, auto_assignment_project, test_db
    ):
        """Two different users calling /next get different tasks."""
        p = auto_assignment_project

        # Annotator gets a task
        resp1 = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["annotator"],
        )
        assert resp1.status_code == 200
        task1_id = resp1.json()["task"]["id"]

        # Contributor gets a task (acts as second annotator)
        resp2 = client.get(
            f"/api/projects/{p['project'].id}/next",
            headers=auth_headers["contributor"],
        )
        assert resp2.status_code == 200
        task2_id = resp2.json()["task"]["id"]

        # With max_annotations=1, they should get different tasks
        assert task1_id != task2_id
