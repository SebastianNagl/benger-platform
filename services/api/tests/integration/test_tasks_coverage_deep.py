"""
Integration tests targeting uncovered handler body code in routers/projects/tasks.py.

Covers lines: 69-225 (list_project_tasks), 257-557 (get_next_task),
576-618 (get_task), 637-665 (update_task_metadata), 686-723 (bulk_update_metadata),
754-847 (update_task_data), 860-909 (bulk_delete_tasks), 928-1087 (bulk_export_tasks),
1117-1166 (bulk_archive), 1191-1225 (skip_task), 1254-1301 (extract_fields),
1333-1368 (get_task_data_fields)
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    Organization,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    PostAnnotationResponse,
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
        title=kwargs.get("title", f"Tasks {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        assignment_mode=kwargs.get("assignment_mode", "open"),
        randomize_task_order=kwargs.get("randomize_task_order", False),
        maximum_annotations=kwargs.get("maximum_annotations", 0),
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


def _tasks(db, project, admin, count=3):
    tasks = []
    for i in range(count):
        t = Task(
            id=_uid(),
            project_id=project.id,
            data={"text": f"Task text #{i}", "category": f"cat_{i % 3}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotations(db, project, tasks, user_id, lead_time=10.0, cancelled=False):
    anns = []
    for t in tasks:
        ann = Annotation(
            id=_uid(),
            task_id=t.id,
            project_id=project.id,
            completed_by=user_id,
            result=[{
                "from_name": "answer", "to_name": "text",
                "type": "choices", "value": {"choices": ["Ja"]},
            }],
            was_cancelled=cancelled,
            lead_time=lead_time,
        )
        db.add(ann)
        anns.append(ann)
    db.flush()
    return anns


def _generations(db, project, tasks, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by="admin-test-id",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(rg)
    db.flush()
    gens = []
    for i, t in enumerate(tasks):
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id,
            model_id=model_id, case_data=json.dumps(t.data),
            response_content=f"Generated answer #{i}",
            label_config_version="v1", status="completed",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()
    return gens


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# LIST PROJECT TASKS (lines 69-225)
# ===================================================================

@pytest.mark.integration
class TestListProjectTasks:
    """Cover list_project_tasks handler body."""

    def test_list_tasks_basic(self, client, test_db, test_users, auth_headers, test_org):
        """List tasks for a project."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5

    def test_list_tasks_pagination(self, client, test_db, test_users, auth_headers, test_org):
        """List tasks with pagination."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=10)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?page=1&page_size=3",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert len(data["items"]) == 3
        assert data["page"] == 1

    def test_list_tasks_only_labeled(self, client, test_db, test_users, auth_headers, test_org):
        """List only labeled tasks."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        tasks[0].is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_labeled=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_list_tasks_only_unlabeled(self, client, test_db, test_users, auth_headers, test_org):
        """List only unlabeled tasks."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?only_unlabeled=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3

    def test_list_tasks_exclude_my_annotations(self, client, test_db, test_users, auth_headers, test_org):
        """List tasks excluding ones I have annotated."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _annotations(test_db, p, tasks[:2], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_list_tasks_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        """List tasks that have generation counts."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _generations(test_db, p, tasks)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert "total_generations" in item

    def test_list_tasks_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """List tasks for non-existent project."""
        resp = client.get(
            f"/api/projects/{_uid()}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_list_tasks_with_assignments(self, client, test_db, test_users, auth_headers, test_org):
        """List tasks that have task assignments."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        for t in tasks[:2]:
            assign = TaskAssignment(
                id=_uid(), task_id=t.id, user_id=test_users[1].id,
                assigned_by=test_users[0].id, status="assigned",
            )
            test_db.add(assign)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3


# ===================================================================
# GET NEXT TASK (lines 257-557)
# ===================================================================

@pytest.mark.integration
class TestGetNextTask:
    """Cover get_next_task handler body for different assignment modes."""

    def test_next_task_open_mode(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task in open mode."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="open")
        _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None
        assert data["total_tasks"] == 5

    def test_next_task_all_annotated(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task when all tasks are annotated by current user."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="open")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None

    def test_next_task_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task for non-existent project."""
        resp = client.get(
            f"/api/projects/{_uid()}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None

    def test_next_task_manual_mode_no_assignments(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task in manual mode with no assignments."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is None

    def test_next_task_manual_mode_with_assignment(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task in manual mode with a task assigned."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        assign = TaskAssignment(
            id=_uid(), task_id=tasks[0].id, user_id=test_users[0].id,
            assigned_by=test_users[0].id, status="assigned",
        )
        test_db.add(assign)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None

    def test_next_task_auto_mode(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task in auto mode creates assignment on the fly."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="auto")
        _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None

    def test_next_task_auto_mode_resume_existing(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task in auto mode resumes existing assignment."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="auto")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        assign = TaskAssignment(
            id=_uid(), task_id=tasks[1].id, user_id=test_users[0].id,
            assigned_by=test_users[0].id, status="in_progress",
        )
        test_db.add(assign)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task"] is not None

    def test_next_task_randomized_order(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task with randomized order."""
        p = _project(test_db, test_users[0], test_org, randomize_task_order=True)
        _tasks(test_db, p, test_users[0], count=10)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["task"] is not None

    def test_next_task_with_metrics(self, client, test_db, test_users, auth_headers, test_org):
        """Get next task returns user-specific completion metrics."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _annotations(test_db, p, tasks[:2], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "user_completed_tasks" in data
        assert data["total_tasks"] == 5

    def test_next_task_auto_mode_max_annotations(self, client, test_db, test_users, auth_headers, test_org):
        """Auto mode respects maximum_annotations setting."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="auto", maximum_annotations=1)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        # Annotate all by another user
        _annotations(test_db, p, tasks, test_users[1].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        # All tasks at max, so should be None
        data = resp.json()
        assert data["task"] is None


# ===================================================================
# GET TASK (lines 576-618)
# ===================================================================

@pytest.mark.integration
class TestGetTask:
    """Cover get_task handler body."""

    def test_get_task_detail(self, client, test_db, test_users, auth_headers, test_org):
        """Get task detail."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tasks[0].id
        assert "data" in data
        assert "meta" in data

    def test_get_task_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Get non-existent task."""
        resp = client.get(
            f"/api/projects/tasks/{_uid()}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_get_task_with_generation_count(self, client, test_db, test_users, auth_headers, test_org):
        """Get task that has generations."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        _generations(test_db, p, tasks)
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["total_generations"] >= 1


# ===================================================================
# UPDATE TASK METADATA (lines 637-665)
# ===================================================================

@pytest.mark.integration
class TestUpdateTaskMetadata:
    """Cover update_task_metadata handler body."""

    def test_update_metadata_merge(self, client, test_db, test_users, auth_headers, test_org):
        """Update task metadata with merge mode."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        tasks[0].meta = {"existing": "value"}
        test_db.commit()

        resp = client.patch(
            f"/api/projects/tasks/{tasks[0].id}/metadata?merge=true",
            json={"new_key": "new_value"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["existing"] == "value"
        assert data["meta"]["new_key"] == "new_value"

    def test_update_metadata_replace(self, client, test_db, test_users, auth_headers, test_org):
        """Update task metadata with replace mode."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        tasks[0].meta = {"old_key": "old_value"}
        test_db.commit()

        resp = client.patch(
            f"/api/projects/tasks/{tasks[0].id}/metadata?merge=false",
            json={"replaced": "data"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "old_key" not in data["meta"]
        assert data["meta"]["replaced"] == "data"

    def test_update_metadata_null_meta(self, client, test_db, test_users, auth_headers, test_org):
        """Update metadata when task has null meta."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        tasks[0].meta = None
        test_db.commit()

        resp = client.patch(
            f"/api/projects/tasks/{tasks[0].id}/metadata?merge=true",
            json={"key": "value"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_update_metadata_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Update metadata for non-existent task."""
        resp = client.patch(
            f"/api/projects/tasks/{_uid()}/metadata",
            json={"key": "value"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# BULK UPDATE TASK METADATA (lines 686-723)
# ===================================================================

@pytest.mark.integration
class TestBulkUpdateTaskMetadata:
    """Cover bulk_update_task_metadata handler body."""

    def test_bulk_metadata_merge(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk update metadata for multiple tasks."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/tasks/bulk-metadata?merge=true",
            json={
                "task_ids": [t.id for t in tasks],
                "metadata": {"tag": "important"},
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 3

    def test_bulk_metadata_replace(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk replace metadata."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/tasks/bulk-metadata?merge=false",
            json={
                "task_ids": [t.id for t in tasks],
                "metadata": {"replaced": True},
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_metadata_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk update with non-existent task IDs."""
        resp = client.patch(
            f"/api/projects/tasks/bulk-metadata",
            json={
                "task_ids": [_uid()],
                "metadata": {"key": "val"},
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# UPDATE TASK DATA (lines 754-847)
# ===================================================================

@pytest.mark.integration
class TestUpdateTaskData:
    """Cover update_task_data handler body."""

    def test_update_task_data(self, client, test_db, test_users, auth_headers, test_org):
        """Update task data as admin."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Updated text"}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["text"] == "Updated text"

    def test_update_task_data_non_admin(self, client, test_db, test_users, auth_headers, test_org):
        """Non-admin cannot update task data."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Updated"}},
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403

    def test_update_task_data_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Update non-existent task."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{_uid()}",
            json={"data": {"text": "test"}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_update_task_data_no_data_field(self, client, test_db, test_users, auth_headers, test_org):
        """Update task with no data field should fail."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}",
            json={"data": {}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_update_task_data_creates_audit_log(self, client, test_db, test_users, auth_headers, test_org):
        """Update task data creates audit log entry."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Audited update"}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "audit_log" in data["meta"]

    def test_update_task_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Update task in non-existent project."""
        resp = client.put(
            f"/api/projects/{_uid()}/tasks/{_uid()}",
            json={"data": {"text": "test"}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# BULK DELETE TASKS (lines 860-909)
# ===================================================================

@pytest.mark.integration
class TestBulkDeleteTasks:
    """Cover bulk_delete_tasks handler body."""

    def test_bulk_delete(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk delete tasks."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": [tasks[0].id, tasks[1].id]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    def test_bulk_delete_nonexistent_tasks(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk delete with non-existent task IDs."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": [_uid(), _uid()]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0

    def test_bulk_delete_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk delete in non-existent project."""
        resp = client.post(
            f"/api/projects/{_uid()}/tasks/bulk-delete",
            json={"task_ids": [_uid()]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# BULK EXPORT TASKS (lines 928-1087)
# ===================================================================

@pytest.mark.integration
class TestBulkExportTasks:
    """Cover bulk_export_tasks handler body."""

    def test_bulk_export_json(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export tasks as JSON."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "json"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_csv(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export tasks as CSV."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "csv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_with_generations_and_evals(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export tasks with full data graph."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        gens = _generations(test_db, p, tasks)
        er = EvaluationRun(
            id=_uid(), project_id=p.id, model_id="gpt-4o",
            evaluation_type_ids=["accuracy"], metrics={"accuracy": 0.9},
            status="completed", samples_evaluated=3,
            created_by=test_users[0].id,
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(er)
        test_db.flush()
        for i, t in enumerate(tasks):
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id, task_id=t.id,
                generation_id=gens[i].id, field_name="answer",
                answer_type="choices", ground_truth={"value": "Ja"},
                prediction={"value": "Ja"}, metrics={"accuracy": 1.0}, passed=True,
            )
            test_db.add(te)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "json"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_tsv_format(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export tasks in TSV format."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-export",
            json={"task_ids": [t.id for t in tasks], "format": "tsv"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_export_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk export in non-existent project."""
        resp = client.post(
            f"/api/projects/{_uid()}/tasks/bulk-export",
            json={"task_ids": [_uid()]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# BULK ARCHIVE TASKS (lines 1117-1166)
# ===================================================================

@pytest.mark.integration
class TestBulkArchiveTasks:
    """Cover bulk_archive_tasks handler body."""

    def test_bulk_archive(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk archive tasks."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-archive",
            json={"task_ids": [tasks[0].id, tasks[1].id]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_bulk_archive_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk archive in non-existent project."""
        resp = client.post(
            f"/api/projects/{_uid()}/tasks/bulk-archive",
            json={"task_ids": [_uid()]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# SKIP TASK (lines 1191-1225)
# ===================================================================

@pytest.mark.integration
class TestSkipTask:
    """Cover skip_task handler body."""

    def test_skip_task(self, client, test_db, test_users, auth_headers, test_org):
        """Skip a task."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
            json={"comment": "Too difficult"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_skip_task_no_comment(self, client, test_db, test_users, auth_headers, test_org):
        """Skip a task without comment."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
            json={},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_skip_task_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Skip non-existent task."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{_uid()}/skip",
            json={},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# TASK FIELDS (lines 1254-1368)
# ===================================================================

@pytest.mark.integration
class TestTaskDataFields:
    """Cover get_task_data_fields handler body."""

    def test_get_task_fields(self, client, test_db, test_users, auth_headers, test_org):
        """Get task data fields for a project."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "fields" in data

    def test_get_task_fields_nested_data(self, client, test_db, test_users, auth_headers, test_org):
        """Get task fields with nested data structures."""
        p = _project(test_db, test_users[0], test_org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "hello", "metadata": {"source": "corpus", "year": 2024}},
            inner_id=1, created_by=test_users[0].id,
        )
        test_db.add(t)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_get_task_fields_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        """Get task fields for a project with no tasks."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_get_task_fields_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Get task fields for non-existent project."""
        resp = client.get(
            f"/api/projects/{_uid()}/task-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404
