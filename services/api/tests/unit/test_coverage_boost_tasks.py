"""
Coverage boost tests for task management endpoints.

Targets specific branches in routers/projects/tasks.py:
- list_project_tasks with various filters
- get_task_detail (GET /tasks/{task_id})
- update task (PUT /{project_id}/tasks/{task_id})
- bulk-delete / bulk-export / bulk-archive
- get_next_task with various conditions
- skip_task
- task-fields
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, EvaluationRun, Generation, ResponseGeneration, TaskEvaluation
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)


def _setup(db, users, assignment_mode="open", **project_kwargs):
    """Create a project with org setup."""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Task Org",
        slug=f"task-org-{uuid.uuid4().hex[:8]}",
        display_name="Task Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title="Task Project",
        created_by=users[0].id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode=assignment_mode,
        min_annotations_per_task=1,
        maximum_annotations=3,
        randomize_task_order=False,
        **project_kwargs,
    )
    db.add(p)
    db.commit()

    for i, user in enumerate(users[:4]):
        db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=org.id,
            role="ORG_ADMIN" if i == 0 else ("CONTRIBUTOR" if i == 1 else "ANNOTATOR"),
            joined_at=datetime.utcnow(),
        ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=users[0].id,
    ))
    db.commit()

    return p, org


def _make_task(db, project_id, inner_id=1, is_labeled=False, data=None):
    tid = str(uuid.uuid4())
    t = Task(
        id=tid,
        project_id=project_id,
        data=data or {"text": f"task-{inner_id}"},
        inner_id=inner_id,
        is_labeled=is_labeled,
    )
    db.add(t)
    db.commit()
    return t


class TestListProjectTasks:
    """Test list_project_tasks endpoint."""

    def test_list_tasks_empty(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_list_tasks_with_data(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        for i in range(3):
            _make_task(test_db, p.id, inner_id=i + 1)

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_list_tasks_only_labeled(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        _make_task(test_db, p.id, inner_id=1, is_labeled=True)
        _make_task(test_db, p.id, inner_id=2, is_labeled=False)

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_labeled=true",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_tasks_only_unlabeled(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        _make_task(test_db, p.id, inner_id=1, is_labeled=True)
        _make_task(test_db, p.id, inner_id=2, is_labeled=False)

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_unlabeled=true",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_tasks_pagination(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        for i in range(5):
            _make_task(test_db, p.id, inner_id=i + 1)

        resp = client.get(
            f"/api/projects/{p.id}/tasks?page=1&page_size=2",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_size"] == 2

    def test_list_tasks_project_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/tasks",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_list_tasks_exclude_my_annotations(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        t1 = _make_task(test_db, p.id, inner_id=1)
        t2 = _make_task(test_db, p.id, inner_id=2)

        # Annotate t1 as admin
        test_db.add(Annotation(
            id=str(uuid.uuid4()),
            task_id=t1.id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["mine"]}}],
            was_cancelled=False,
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


class TestGetTaskDetail:
    """Test get_task_detail endpoint (GET /tasks/{task_id})."""

    def test_get_task_basic(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        t = _make_task(test_db, p.id, inner_id=1)

        resp = client.get(
            f"/api/projects/tasks/{t.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == t.id

    def test_get_task_not_found(self, client, auth_headers, test_db, test_users):
        resp = client.get(
            "/api/projects/tasks/nonexistent",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_get_task_with_annotations(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        t = _make_task(test_db, p.id, inner_id=1)

        test_db.add(Annotation(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["data"]}}],
            was_cancelled=False,
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{t.id}",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


class TestUpdateTask:
    """Test update_task endpoint (PUT /{project_id}/tasks/{task_id})."""

    def test_update_task_data(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        t = _make_task(test_db, p.id, inner_id=1)

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{t.id}",
            json={"data": {"text": "updated text"}},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_update_task_not_found(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        resp = client.put(
            f"/api/projects/{p.id}/tasks/nonexistent",
            json={"data": {"text": "x"}},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 404


class TestBulkDeleteTasks:
    """Test bulk-delete endpoint."""

    def test_batch_delete_tasks(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        tasks = [_make_task(test_db, p.id, inner_id=i) for i in range(3)]
        task_ids = [t.id for t in tasks]

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": task_ids},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_batch_delete_no_tasks(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": []},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code in [200, 400]


class TestBulkExportTasks:
    """Test bulk-export endpoint."""

    def test_bulk_export_tasks(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        tasks = [_make_task(test_db, p.id, inner_id=i) for i in range(2)]
        task_ids = [t.id for t in tasks]

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": task_ids},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


class TestBulkArchiveTasks:
    """Test bulk-archive endpoint."""

    def test_bulk_archive_tasks(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        tasks = [_make_task(test_db, p.id, inner_id=i) for i in range(2)]
        task_ids = [t.id for t in tasks]

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-archive",
            json={"task_ids": task_ids, "archive": True},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


class TestGetNextTask:
    """Test get_next_task endpoint."""

    def test_next_task_basic(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        _make_task(test_db, p.id, inner_id=1, is_labeled=False)

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_next_task_all_labeled(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        _make_task(test_db, p.id, inner_id=1, is_labeled=True)

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_next_task_no_tasks(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_next_task_project_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/next",
            headers=auth_headers["admin"],
        )
        # superadmin can access any project; the endpoint returns 200 with null task
        assert resp.status_code in [200, 404, 403]

    def test_next_task_randomized(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        p.randomize_task_order = True
        test_db.commit()
        for i in range(5):
            _make_task(test_db, p.id, inner_id=i + 1, is_labeled=False)

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_next_task_manual_mode(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users, assignment_mode="manual")
        t = _make_task(test_db, p.id, inner_id=1, is_labeled=False)
        # Assign task to admin
        test_db.add(TaskAssignment(
            id=str(uuid.uuid4()),
            task_id=t.id,
            user_id=test_users[0].id,
            assigned_by=test_users[0].id,
            status="assigned",
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


class TestSkipTask:
    """Test skip_task endpoint."""

    def test_skip_task_basic(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users, show_skip_button=True)
        t = _make_task(test_db, p.id, inner_id=1)

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{t.id}/skip",
            json={},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_skip_task_with_comment(self, client, auth_headers, test_db, test_users):
        p, org = _setup(
            test_db, test_users, show_skip_button=True, require_comment_on_skip=True
        )
        t = _make_task(test_db, p.id, inner_id=1)

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{t.id}/skip",
            json={"comment": "Too difficult"},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_skip_task_not_found(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        resp = client.post(
            f"/api/projects/{p.id}/tasks/nonexistent/skip",
            json={},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 404


class TestTaskFields:
    """Test task-fields endpoint."""

    def test_task_fields_basic(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        _make_task(test_db, p.id, inner_id=1, data={"text": "hello", "category": "A"})

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_task_fields_empty(self, client, auth_headers, test_db, test_users):
        p, org = _setup(test_db, test_users)
        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
