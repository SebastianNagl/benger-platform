"""
Integration tests for task assignment endpoints.

Targets: routers/projects/assignments.py — 6.65% coverage (221 uncovered lines)
Uses real PostgreSQL with per-test transaction rollback.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User
from project_models import (
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _uid() -> str:
    return str(uuid.uuid4())


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

    def test_list_assignments(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Assign first
        client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={"task_ids": [tasks[0].id], "user_ids": [test_users[2].id], "distribution": "manual"},
            headers=auth_headers["admin"],
        )

        resp = client.get(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/assignments",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
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
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Assign
        client.post(
            f"/api/projects/{project.id}/tasks/assign",
            json={"task_ids": [tasks[0].id], "user_ids": [test_users[2].id], "distribution": "manual"},
            headers=auth_headers["admin"],
        )
        # Get assignment ID
        list_resp = client.get(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/assignments",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assignment_id = list_resp.json()[0]["id"]

        # Remove
        resp = client.delete(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/assignments/{assignment_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_remove_nonexistent_assignment(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.delete(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/assignments/nonexistent",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestProjectWorkload:
    """GET /api/projects/{project_id}/workload"""

    def test_get_workload(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{project.id}/workload",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "annotators" in data
        assert "stats" in data

    def test_workload_annotator_denied(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _setup(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{project.id}/workload",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


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
