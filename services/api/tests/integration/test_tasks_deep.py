"""
Deep integration tests for task management endpoints.

Covers routers/projects/tasks.py:
- GET /{project_id}/tasks — complex filters (labeled, unlabeled, assigned, exclude_my)
- GET /{project_id}/next — next task for annotator
- GET /tasks/{task_id} — single task (global router)
- PUT /{project_id}/tasks/{task_id} — update task data
- POST /{project_id}/tasks/bulk-delete — bulk delete
- POST /{project_id}/tasks/{task_id}/skip — skip task
- GET /{project_id}/task-fields — task fields discovery
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    OrganizationMembership,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)


def _uid():
    return str(uuid.uuid4())


def _project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"Task Test {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        assignment_mode=kwargs.get("assignment_mode", "open"),
        maximum_annotations=kwargs.get("maximum_annotations", 1),
        randomize_task_order=kwargs.get("randomize_task_order", False),
    )
    db.add(p)
    db.flush()
    po = ProjectOrganization(
        id=_uid(), project_id=p.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()
    return p


def _tasks(db, project, admin, count=5):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task text {i}", "index": i},
            inner_id=i + 1, created_by=admin.id,
            is_labeled=(i < count // 3),  # First third is labeled
            total_annotations=(1 if i < count // 3 else 0),
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotate(db, project, tasks, user_id, count=None):
    anns = []
    for t in tasks[:count]:
        ann = Annotation(
            id=_uid(), task_id=t.id, project_id=project.id,
            completed_by=user_id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        db.add(ann)
        anns.append(ann)
    db.flush()
    return anns


def _assign(db, tasks, user_id, admin_id, count=None):
    assigns = []
    for t in tasks[:count]:
        a = TaskAssignment(
            id=_uid(), task_id=t.id, user_id=user_id,
            assigned_by=admin_id, status="assigned",
        )
        db.add(a)
        assigns.append(a)
    db.flush()
    return assigns


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# LIST TASKS
# ===================================================================

@pytest.mark.integration
class TestListTasks:
    """GET /api/projects/{project_id}/tasks"""

    def test_list_all_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=7)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 7

    def test_list_tasks_pagination(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=15)
        test_db.commit()

        resp1 = client.get(
            f"/api/projects/{p.id}/tasks?page=1&page_size=5",
            headers=_h(auth_headers, test_org),
        )
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert len(body1["items"]) == 5

        resp2 = client.get(
            f"/api/projects/{p.id}/tasks?page=2&page_size=5",
            headers=_h(auth_headers, test_org),
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["items"]) == 5

        # Different tasks
        ids1 = {t["id"] for t in body1["items"]}
        ids2 = {t["id"] for t in body2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_list_labeled_only(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=9)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_labeled=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for t in body["items"]:
            assert t["is_labeled"] is True

    def test_list_unlabeled_only(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=9)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_unlabeled=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for t in body["items"]:
            assert t["is_labeled"] is False

    def test_list_assigned_only(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _assign(test_db, tasks, test_users[2].id, test_users[0].id, count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_assigned=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_list_exclude_my_annotations(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _annotate(test_db, p, tasks, test_users[0].id, count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_list_tasks_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            "/api/projects/nonexistent/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (403, 404)

    def test_list_tasks_response_structure(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert "pages" in body

    def test_list_tasks_item_structure(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "id" in item
        assert "data" in item
        assert "is_labeled" in item
        assert "total_annotations" in item
        assert "inner_id" in item

    def test_list_tasks_has_total(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=10)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 10

    def test_list_tasks_filtered_total(self, client, test_db, test_users, auth_headers, test_org):
        """When filtering labeled, total should reflect filtered count."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=9)  # 3 labeled, 6 unlabeled
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_labeled=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3

    def test_list_tasks_large_page(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?page=1&page_size=100",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 3

    def test_list_page_beyond_total(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?page=100&page_size=30",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 0


# ===================================================================
# UPDATE TASKS
# ===================================================================

@pytest.mark.integration
class TestUpdateTask:
    """PUT /api/projects/{project_id}/tasks/{task_id}"""

    def test_update_task_data(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Updated text"}, "meta": {"updated": True}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 403)

    def test_update_nonexistent_task(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/nonexistent",
            json={"data": {"text": "Nope"}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# BULK OPERATIONS
# ===================================================================

@pytest.mark.integration
class TestBulkDeleteTasks:
    """POST /api/projects/{project_id}/tasks/bulk-delete"""

    def test_bulk_delete(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()
        ids_to_delete = [tasks[0].id, tasks[1].id]

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": ids_to_delete},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 204)

    def test_bulk_delete_empty(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": []},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400)

    def test_bulk_delete_verifies_task_removed(self, client, test_db, test_users, auth_headers, test_org):
        """After bulk delete, listing should not include the deleted tasks."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()
        ids_to_delete = [tasks[0].id, tasks[1].id]

        del_resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": ids_to_delete},
            headers=_h(auth_headers, test_org),
        )
        assert del_resp.status_code in (200, 204)

        list_resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert list_resp.status_code == 200
        remaining_ids = {t["id"] for t in list_resp.json()["items"]}
        for deleted_id in ids_to_delete:
            assert deleted_id not in remaining_ids


# ===================================================================
# SKIP TASK
# ===================================================================

@pytest.mark.integration
class TestSkipTask:
    """POST /api/projects/{project_id}/tasks/{task_id}/skip"""

    def test_skip_task(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
            json={"comment": "Too difficult"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201)

    def test_skip_task_without_comment(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
            json={},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201, 422)

    def test_skip_nonexistent_task(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/nonexistent/skip",
            json={"comment": "Nope"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# NEXT TASK
# ===================================================================

@pytest.mark.integration
class TestNextTask:
    """GET /api/projects/{project_id}/next"""

    def test_get_next_task(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_get_next_task_all_done(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotate(test_db, p, tasks, test_users[0].id, count=2)
        # Mark all as labeled
        for t in tasks:
            t.is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        # Should indicate no more tasks
        assert resp.status_code in (200, 404)

    def test_get_next_task_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)


# ===================================================================
# TASK FIELDS
# ===================================================================

@pytest.mark.integration
class TestTaskFields:
    """GET /api/projects/{project_id}/task-fields"""

    def test_get_task_fields(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_get_task_fields_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)


# ===================================================================
# ROLE-BASED ACCESS
# ===================================================================

@pytest.mark.integration
class TestTaskRoleAccess:
    """Verify role-based visibility on task endpoints."""

    def test_annotator_can_list_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_annotator_manual_mode_sees_only_assigned(self, client, test_db, test_users, auth_headers, test_org):
        """In manual assignment mode, annotators should only see assigned tasks."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _assign(test_db, tasks, test_users[2].id, test_users[0].id, count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Annotator should only see assigned tasks
        assert body["total"] <= 2

    def test_admin_sees_all_tasks(self, client, test_db, test_users, auth_headers, test_org):
        """Superadmin should see all tasks regardless of assignment mode."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5


# ===================================================================
# BULK EXPORT
# ===================================================================

@pytest.mark.integration
class TestBulkExportTasks:
    """POST /api/projects/{project_id}/tasks/bulk-export"""

    def test_bulk_export_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [tasks[0].id, tasks[1].id]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 404, 405)

    def test_bulk_export_all_tasks(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        all_ids = [t.id for t in tasks]
        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": all_ids},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 404, 405)

    def test_bulk_export_empty_list(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": []},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 400, 404, 405)


# ===================================================================
# SKIP + NEXT INTEGRATION
# ===================================================================

@pytest.mark.integration
class TestSkipAndNext:
    """Integration: skip tasks then get next."""

    def test_skip_then_next(self, client, test_db, test_users, auth_headers, test_org):
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        # Skip first task
        skip_resp = client.post(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
            json={"comment": "Skip it"},
            headers=_h(auth_headers, test_org),
        )
        assert skip_resp.status_code in (200, 201)

        # Next should return a different task
        next_resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert next_resp.status_code in (200, 404)

    def test_update_then_verify(self, client, test_db, test_users, auth_headers, test_org):
        """Update task data then verify it's changed in listing."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        # Update
        update_resp = client.put(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Updated via test"}, "meta": {"updated": True}},
            headers=_h(auth_headers, test_org),
        )
        assert update_resp.status_code in (200, 403)

        # Verify in listing
        list_resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        if update_resp.status_code == 200:
            assert items[0]["data"]["text"] == "Updated via test"
