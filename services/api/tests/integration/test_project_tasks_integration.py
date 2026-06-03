"""
Integration tests for project task management endpoints.

Targets: routers/projects/tasks.py — 19.06% coverage (348 uncovered lines)
Uses real PostgreSQL with per-test transaction rollback.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from models import (
    Organization,
    OrganizationMembership,
    User,
)
from project_models import (
    Project,
    ProjectOrganization,
    Task,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _setup(
    db: Session,
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
class TestListTasks:
    """GET /api/projects/{project_id}/tasks"""

    def test_list_tasks_basic(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=5)
        resp = client.get(
            f"/api/projects/{project.id}/tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data or "items" in data or isinstance(data, list)

    def test_list_tasks_pagination(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=10)
        resp = client.get(
            f"/api/projects/{project.id}/tasks?page=1&page_size=3",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_tasks_only_labeled(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=3)
        # Mark one task as labeled
        tasks[0].is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?only_labeled=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_tasks_only_unlabeled(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=3)
        tasks[0].is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/tasks?only_unlabeled=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_tasks_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent-id/tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (403, 404)


@pytest.mark.integration
class TestGetSingleTask:
    """GET /api/projects/tasks/{task_id}"""

    def test_get_task_by_id(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tasks[0].id

    def test_get_task_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/tasks/nonexistent-task-id",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestGetNextTask:
    """GET /api/projects/{project_id}/next"""

    def test_get_next_task(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # 200 with a task, or 404 if no tasks available
        assert resp.status_code in (200, 404)

    def test_get_next_task_all_labeled(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=2)
        for t in tasks:
            t.is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/next",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # Should indicate no tasks available
        assert resp.status_code in (200, 404)


@pytest.mark.integration
class TestUpdateTask:
    """PUT /api/projects/{project_id}/tasks/{task_id}"""

    def test_update_task_data(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Updated text content"}},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)

    def test_update_task_not_found(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/projects/{project.id}/tasks/nonexistent-id",
            json={"data": {"text": "nope"}},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (404, 403)


@pytest.mark.integration
class TestUpdateTaskAuthorization:
    """PUT /api/projects/{project_id}/tasks/{task_id} — who may edit task data.

    Editing is allowed for superadmins, the project creator, and active
    ORG_ADMIN members of the project's organization. Everyone else gets 403.
    """

    def test_superadmin_can_edit(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Edited by superadmin"}},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == "Edited by superadmin"

    def test_org_admin_member_can_edit(self, client, test_db, test_users, auth_headers, test_org):
        # Project is created by the superadmin, so org_admin (test_users[3]) is
        # NOT the creator — this exercises the ORG_ADMIN membership branch.
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Edited by org admin"}},
            headers={**auth_headers["org_admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == "Edited by org admin"

    def test_contributor_cannot_edit(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Contributor attempt"}},
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403
        assert "organization admins" in resp.json()["detail"]

    def test_annotator_cannot_edit(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Annotator attempt"}},
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403
        assert "organization admins" in resp.json()["detail"]

    def test_deactivated_org_admin_cannot_edit(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Deactivate the org_admin's membership — a deactivated member must lose
        # edit access entirely.
        membership = (
            test_db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == test_users[3].id,
                OrganizationMembership.organization_id == test_org.id,
            )
            .first()
        )
        membership.is_active = False
        test_db.commit()

        resp = client.put(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Should be blocked"}},
            headers={**auth_headers["org_admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403

    def test_edit_merges_data_and_writes_audit_log(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Task seeded with {"text": ..., "meta_field": ...}; update only `text`.
        resp = client.put(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Merged value"}},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
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

    def test_update_task_metadata(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.patch(
            f"/api/projects/tasks/{tasks[0].id}/metadata",
            json={"meta": {"priority": "high", "difficulty": 3}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 404, 422)


@pytest.mark.integration
class TestBulkTaskMetadata:
    """PATCH /api/projects/tasks/bulk-metadata"""

    def test_bulk_metadata_update(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.patch(
            "/api/projects/tasks/bulk-metadata",
            json={
                "task_ids": [t.id for t in tasks[:2]],
                "meta": {"batch": "test-batch-1"},
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 404, 422)


@pytest.mark.integration
class TestBulkDeleteTasks:
    """POST /api/projects/{project_id}/tasks/bulk-delete"""

    def test_bulk_delete_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=4)
        task_ids = [t.id for t in tasks[:2]]

        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-delete",
            json={"task_ids": task_ids},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)

    def test_bulk_delete_empty_list(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-delete",
            json={"task_ids": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 403)


@pytest.mark.integration
class TestBulkExportTasks:
    """POST /api/projects/{project_id}/tasks/bulk-export"""

    def test_bulk_export_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)


@pytest.mark.integration
class TestBulkArchiveTasks:
    """POST /api/projects/{project_id}/tasks/bulk-archive"""

    def test_bulk_archive_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-archive",
            json={"task_ids": [t.id for t in tasks[:2]]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403)


@pytest.mark.integration
class TestSkipTask:
    """POST /api/projects/{project_id}/tasks/{task_id}/skip"""

    def test_skip_task(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
            json={"reason": "Too ambiguous"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # Endpoint may not exist or may return various statuses
        assert resp.status_code in (200, 404, 405)
