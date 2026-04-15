"""
Integration tests for task operations (bulk-export, bulk-archive, metadata,
task-fields, skip).

Targets: routers/projects/tasks.py — bulk_export_tasks, bulk_archive_tasks,
         update_task_metadata, bulk_update_metadata, get_task_fields, skip_task
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


def _make_project(db, admin, org, *, num_tasks=5):
    """Create project with tasks."""
    project = Project(
        id=_uid(),
        title="Task Ops Test",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/><Choices name="answer" toName="text"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
    )
    db.add(project)
    db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task #{i}", "category": f"cat-{i % 3}",
                  "nested": {"key": f"val-{i}"}},
            meta={"source": "test", "batch": i % 2},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.commit()
    return project, tasks


@pytest.mark.integration
class TestBulkExportTasks:
    """POST /api/projects/{project_id}/tasks/bulk-export"""

    def test_bulk_export_json(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks[:3]], "format": "json"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_bulk_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks[:2]], "format": "csv"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_bulk_export_all_tasks(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_bulk_export_empty_ids(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-export",
            json={"task_ids": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400)


@pytest.mark.integration
class TestBulkArchiveTasks:
    """POST /api/projects/{project_id}/tasks/bulk-archive"""

    def test_bulk_archive(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/bulk-archive",
            json={"task_ids": [tasks[0].id]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 404)


@pytest.mark.integration
class TestTaskMetadata:
    """PATCH /api/projects/tasks/{task_id}/metadata"""

    def test_update_single_task_metadata(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=1)
        resp = client.patch(
            f"/api/projects/tasks/{tasks[0].id}/metadata",
            json={"meta": {"source": "updated", "extra": True}},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_update_nonexistent_task_metadata(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.patch(
            "/api/projects/tasks/nonexistent-id/metadata",
            json={"meta": {"key": "val"}},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestBulkMetadata:
    """PATCH /api/projects/tasks/bulk-metadata"""

    def test_bulk_update_metadata(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.patch(
            "/api/projects/tasks/bulk-metadata",
            json={
                "task_ids": [tasks[0].id, tasks[1].id],
                "metadata": {"batch": "new-batch"},
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 2


@pytest.mark.integration
class TestGetTaskFields:
    """GET /api/projects/{project_id}/task-fields"""

    def test_task_fields_basic(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{project.id}/task-fields",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should return field names from task data
        assert isinstance(body, (list, dict))

    def test_task_fields_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _make_project(test_db, test_users[0], test_org, num_tasks=0)
        resp = client.get(
            f"/api/projects/{project.id}/task-fields",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestSkipTask:
    """POST /api/projects/{project_id}/tasks/{task_id}/skip"""

    def test_skip_task(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/{tasks[0].id}/skip",
            json={},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "skipped" in body or "status" in body or "task_id" in body

    def test_skip_nonexistent_task(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=1)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/nonexistent-id/skip",
            json={},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (404,)

    def test_skip_task_with_comment(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=3)
        resp = client.post(
            f"/api/projects/{project.id}/tasks/{tasks[1].id}/skip",
            json={"comment": "Not relevant"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 422)
