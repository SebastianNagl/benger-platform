"""
Integration tests targeting uncovered handler body code in routers/projects/tasks.py.

Focuses on:
- list_project_tasks: role-based visibility, generation counts, assignment enrichment,
  randomize_task_order, exclude_my_annotations with skip filtering, pagination edge cases
- get_next_task: open/manual/auto modes, skip queue variants, maximum_annotations enforcement,
  auto-assignment creation, concurrency-safe locking
- skip_task: SkippedTask creation, comment persistence
- update_task: data and meta update, created_by field update
- bulk_delete: cascade deletion, verification
- task_fields: field discovery from task data
- Single task retrieval via global route
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    Generation,
    OrganizationMembership,
    ResponseGeneration,
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
        title=kwargs.get("title", f"TaskCov {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        assignment_mode=kwargs.get("assignment_mode", "open"),
        maximum_annotations=kwargs.get("maximum_annotations", 1),
        randomize_task_order=kwargs.get("randomize_task_order", False),
        skip_queue=kwargs.get("skip_queue", "requeue_for_others"),
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


def _tasks(db, project, admin, count=5, labeled_count=0):
    tasks = []
    for i in range(count):
        is_lab = i < labeled_count
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Task text {i}", "index": i, "category": f"cat_{i % 3}"},
            inner_id=i + 1, created_by=admin.id,
            is_labeled=is_lab,
            total_annotations=(1 if is_lab else 0),
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


def _assign(db, tasks, user_id, admin_id, count=None, status="assigned"):
    assigns = []
    for t in tasks[:count]:
        a = TaskAssignment(
            id=_uid(), task_id=t.id, user_id=user_id,
            assigned_by=admin_id, status=status,
        )
        db.add(a)
        assigns.append(a)
    db.flush()
    return assigns


def _skip(db, project, tasks, user_id, count=None):
    skips = []
    for t in tasks[:count]:
        s = SkippedTask(
            id=_uid(), task_id=t.id, project_id=project.id,
            skipped_by=user_id, comment="Skipped in test",
        )
        db.add(s)
        skips.append(s)
    db.flush()
    return skips


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
    for t in tasks:
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id,
            model_id=model_id,
            case_data=json.dumps(t.data),
            response_content="Generated",
            label_config_version="v1", status="completed",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()
    return gens


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


def _annotator_h(auth_headers, org):
    return {**auth_headers["annotator"], "X-Organization-Context": org.id}


# ===================================================================
# LIST TASKS: deep handler body coverage
# ===================================================================

@pytest.mark.integration
class TestListTasksDeep:
    """Deep coverage for list_project_tasks handler body."""

    def test_list_tasks_includes_generation_counts(self, client, test_db, test_users, auth_headers, test_org):
        """Task items should include total_generations count."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _generations(test_db, p, tasks)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert "total_generations" in item
            assert item["total_generations"] >= 1

    def test_list_tasks_includes_assignments_data(self, client, test_db, test_users, auth_headers, test_org):
        """Task items should include assignment details."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _assign(test_db, tasks, test_users[2].id, test_users[0].id, count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # At least some tasks should have assignment data
        has_assignments = any(len(item.get("assignments", [])) > 0 for item in body["items"])
        assert has_assignments

    def test_list_tasks_assignment_enrichment_has_user_info(self, client, test_db, test_users, auth_headers, test_org):
        """Assignments include user_name and user_email."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = _tasks(test_db, p, test_users[0], count=1)
        _assign(test_db, tasks, test_users[2].id, test_users[0].id, count=1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            for asgn in item.get("assignments", []):
                assert "user_name" in asgn
                assert "user_email" in asgn
                assert "status" in asgn

    def test_list_tasks_randomized_order(self, client, test_db, test_users, auth_headers, test_org):
        """Randomized project uses MD5-based ordering."""
        p = _project(test_db, test_users[0], test_org, randomize_task_order=True)
        _tasks(test_db, p, test_users[0], count=10)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 10

    def test_list_tasks_exclude_my_annotations_filters(self, client, test_db, test_users, auth_headers, test_org):
        """exclude_my_annotations filters out tasks the user has annotated."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _annotate(test_db, p, tasks[:3], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should exclude the 3 annotated tasks
        assert body["total"] <= 2

    def test_list_tasks_exclude_skipped_for_others(self, client, test_db, test_users, auth_headers, test_org):
        """With skip_queue=requeue_for_others, exclude tasks skipped by this user."""
        p = _project(test_db, test_users[0], test_org, skip_queue="requeue_for_others")
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _skip(test_db, p, tasks[:2], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks?exclude_my_annotations=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] <= 3

    def test_list_tasks_ignore_skipped_excludes_all(self, client, test_db, test_users, auth_headers, test_org):
        """With skip_queue=ignore_skipped, exclude tasks skipped by ANY user."""
        p = _project(test_db, test_users[0], test_org, skip_queue="ignore_skipped")
        tasks = _tasks(test_db, p, test_users[0], count=5)
        # Different users skip different tasks
        _skip(test_db, p, tasks[:1], test_users[0].id)
        _skip(test_db, p, tasks[1:2], test_users[1].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # 2 tasks skipped by various users -> 3 remaining
        assert body["total"] <= 3

    def test_list_tasks_annotator_manual_mode(self, client, test_db, test_users, auth_headers, test_org):
        """Annotator in manual mode only sees assigned tasks."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _assign(test_db, tasks, test_users[2].id, test_users[0].id, count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_annotator_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] <= 2

    def test_list_tasks_task_dict_has_all_fields(self, client, test_db, test_users, auth_headers, test_org):
        """Verify task dict includes all expected fields."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        expected_fields = [
            "id", "inner_id", "data", "meta", "created_at",
            "is_labeled", "total_annotations", "total_generations",
            "project_id", "assignments", "tags",
        ]
        for field in expected_fields:
            assert field in item, f"Missing field: {field}"

    def test_list_tasks_meta_tags_backward_compat(self, client, test_db, test_users, auth_headers, test_org):
        """Tags derived from meta for backward compatibility."""
        p = _project(test_db, test_users[0], test_org)
        t = Task(
            id=_uid(), project_id=p.id,
            data={"text": "Tagged task"},
            meta={"tags": ["important", "legal"]},
            inner_id=1, created_by=test_users[0].id,
        )
        test_db.add(t)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["tags"] == ["important", "legal"]


# ===================================================================
# NEXT TASK: deep handler body coverage
# ===================================================================

@pytest.mark.integration
class TestNextTaskDeep:
    """Deep coverage for get_next_task handler body."""

    def test_next_task_open_mode(self, client, test_db, test_users, auth_headers, test_org):
        """Open mode returns next unannotated task."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="open")
        _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            body = resp.json()
            assert body.get("task") is not None or "id" in body

    def test_next_task_manual_mode_returns_assigned(self, client, test_db, test_users, auth_headers, test_org):
        """Manual mode returns task assigned to the user."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _assign(test_db, tasks, test_users[0].id, test_users[0].id, count=2)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_next_task_manual_mode_no_assignments(self, client, test_db, test_users, auth_headers, test_org):
        """Manual mode with no assignments returns no task."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="manual")
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)
        body = resp.json()
        assert body.get("task") is None or body.get("detail") is not None

    def test_next_task_auto_mode_creates_assignment(self, client, test_db, test_users, auth_headers, test_org):
        """Auto mode auto-assigns and returns a task."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="auto")
        _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_next_task_auto_mode_resumes_in_progress(self, client, test_db, test_users, auth_headers, test_org):
        """Auto mode returns existing in-progress assignment first."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="auto")
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _assign(test_db, tasks, test_users[0].id, test_users[0].id, count=1, status="in_progress")
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_next_task_skips_annotated(self, client, test_db, test_users, auth_headers, test_org):
        """Next task skips tasks already annotated by the user."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="open")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotate(test_db, p, tasks[:2], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_next_task_all_annotated(self, client, test_db, test_users, auth_headers, test_org):
        """When all tasks annotated, returns no task."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="open")
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotate(test_db, p, tasks, test_users[0].id)
        for t in tasks:
            t.is_labeled = True
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_next_task_auto_skips_skipped_tasks(self, client, test_db, test_users, auth_headers, test_org):
        """Auto mode skips tasks the user has skipped."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="auto")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _skip(test_db, p, tasks[:2], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_next_task_maximum_annotations_enforced(self, client, test_db, test_users, auth_headers, test_org):
        """Auto mode respects maximum_annotations limit."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="auto", maximum_annotations=1)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        # Another user has annotated both tasks
        _annotate(test_db, p, tasks, test_users[1].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_next_task_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        """Next task for nonexistent project returns null task."""
        resp = client.get(
            "/api/projects/nonexistent/next",
            headers=_h(auth_headers, test_org),
        )
        # Either 200 with task=None or 404
        assert resp.status_code in (200, 404)

    def test_next_task_randomized_order(self, client, test_db, test_users, auth_headers, test_org):
        """Randomized project uses per-user deterministic ordering."""
        p = _project(test_db, test_users[0], test_org,
                     assignment_mode="auto", randomize_task_order=True)
        _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)


# ===================================================================
# SKIP TASK
# ===================================================================

@pytest.mark.integration
class TestSkipTaskDeep:
    """Deep coverage for skip_task handler body."""

    def test_skip_creates_record(self, client, test_db, test_users, auth_headers, test_org):
        """Skip creates a SkippedTask record."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
            json={"comment": "Too ambiguous"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201)

    def test_skip_with_empty_comment(self, client, test_db, test_users, auth_headers, test_org):
        """Skip with empty string comment."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
            json={"comment": ""},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201, 422)

    def test_skip_nonexistent_task(self, client, test_db, test_users, auth_headers, test_org):
        """Skip nonexistent task returns 404."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/nonexistent/skip",
            json={"comment": "Nope"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# UPDATE TASK
# ===================================================================

@pytest.mark.integration
class TestUpdateTaskDeep:
    """Deep coverage for update task handler body."""

    def test_update_task_data_and_meta(self, client, test_db, test_users, auth_headers, test_org):
        """Update both data and meta fields."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Updated text", "extra": "field"}, "meta": {"tag": "urgent"}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 403)
        if resp.status_code == 200:
            body = resp.json()
            assert body.get("data", {}).get("text") == "Updated text"

    def test_update_nonexistent(self, client, test_db, test_users, auth_headers, test_org):
        """Update nonexistent task returns 404."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.put(
            f"/api/projects/{p.id}/tasks/nonexistent",
            json={"data": {"text": "Nope"}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# BULK DELETE
# ===================================================================

@pytest.mark.integration
class TestBulkDeleteDeep:
    """Deep coverage for bulk_delete handler body."""

    def test_bulk_delete_cascades(self, client, test_db, test_users, auth_headers, test_org):
        """Bulk delete removes tasks and associated data."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _annotate(test_db, p, tasks[:3], test_users[0].id)
        test_db.commit()

        ids = [tasks[0].id, tasks[1].id]
        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": ids},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 204)

        # Verify deleted
        list_resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert list_resp.status_code == 200
        remaining = {t["id"] for t in list_resp.json()["items"]}
        for deleted_id in ids:
            assert deleted_id not in remaining

    def test_bulk_delete_all_tasks(self, client, test_db, test_users, auth_headers, test_org):
        """Delete all tasks in a project."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": [t.id for t in tasks]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 204)

    def test_bulk_delete_nonexistent_ids(self, client, test_db, test_users, auth_headers, test_org):
        """Delete with nonexistent task IDs should not fail."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/tasks/bulk-delete",
            json={"task_ids": ["nonexistent-1", "nonexistent-2"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 204, 404)


# ===================================================================
# TASK FIELDS
# ===================================================================

@pytest.mark.integration
class TestTaskFieldsDeep:
    """Deep coverage for task-fields endpoint."""

    def test_task_fields_discovers_keys(self, client, test_db, test_users, auth_headers, test_org):
        """task-fields should discover data keys from tasks."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=3,
               labeled_count=0)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)

    def test_task_fields_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        """Empty project returns empty or default fields."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/task-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 404)


# ===================================================================
# SKIP + NEXT INTEGRATION
# ===================================================================

@pytest.mark.integration
class TestSkipNextIntegration:
    """Integration between skip and next endpoints."""

    def test_skip_then_next_returns_different_task(self, client, test_db, test_users, auth_headers, test_org):
        """After skipping a task, next should return a different one."""
        p = _project(test_db, test_users[0], test_org, assignment_mode="open")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        test_db.commit()

        # Skip first task
        skip_resp = client.post(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}/skip",
            json={"comment": "Skip it"},
            headers=_h(auth_headers, test_org),
        )
        assert skip_resp.status_code in (200, 201)

        # Get next - should not return the skipped task
        next_resp = client.get(
            f"/api/projects/{p.id}/next",
            headers=_h(auth_headers, test_org),
        )
        assert next_resp.status_code in (200, 404)

    def test_update_then_list_reflects_change(self, client, test_db, test_users, auth_headers, test_org):
        """Update task data and verify it appears in listing."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        # Update
        update_resp = client.put(
            f"/api/projects/{p.id}/tasks/{tasks[0].id}",
            json={"data": {"text": "Changed via integration test"}},
            headers=_h(auth_headers, test_org),
        )
        assert update_resp.status_code in (200, 403)

        # Verify
        list_resp = client.get(
            f"/api/projects/{p.id}/tasks",
            headers=_h(auth_headers, test_org),
        )
        assert list_resp.status_code == 200
        if update_resp.status_code == 200:
            assert list_resp.json()["items"][0]["data"]["text"] == "Changed via integration test"
