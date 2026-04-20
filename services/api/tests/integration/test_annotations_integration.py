"""
Integration tests for annotation management endpoints.

Targets: routers/projects/annotations.py — 8.91% coverage (118 uncovered lines)
Uses real PostgreSQL with per-test transaction rollback.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import Organization, User
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _setup(db, admin, org, *, num_tasks=2, assignment_mode="open", max_annotations=10,
           min_annotations_per_task=1, conditional_instructions=None):
    """Create project with tasks linked to org."""
    project = Project(
        id=_uid(),
        title=f"Ann Test {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        assignment_mode=assignment_mode,
        maximum_annotations=max_annotations,
        min_annotations_per_task=min_annotations_per_task,
        conditional_instructions=conditional_instructions,
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
            data={"text": f"Annotate me #{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(task)
        tasks.append(task)
    db.commit()
    return project, tasks


@pytest.mark.integration
class TestCreateAnnotation:
    """POST /api/projects/tasks/{task_id}/annotations"""

    def test_create_annotation_success(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [
                    {"from_name": "text", "to_name": "text", "type": "textarea",
                     "value": {"text": ["Test annotation"]}}
                ],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == tasks[0].id
        assert data["result"] is not None

    def test_create_annotation_task_not_found(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/tasks/nonexistent-task/annotations",
            json={"result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["x"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 404

    def test_create_cancelled_annotation(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["cancel"]}}],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] is True

    def test_create_annotation_with_enhanced_timing(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["timed"]}}],
                "lead_time": 45.5,
                "active_duration_ms": 40000,
                "focused_duration_ms": 35000,
                "tab_switches": 3,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active_duration_ms") == 40000
        assert data.get("tab_switches") == 3

    def test_create_annotation_with_instruction_variant(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(
            test_db, test_users[0], test_org,
            conditional_instructions=[
                {"id": "variant-1", "content": "Do this", "weight": 1, "ai_allowed": True},
                {"id": "variant-2", "content": "Do that", "weight": 1, "ai_allowed": False},
            ],
        )
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["ai"]}}],
                "instruction_variant": "variant-1",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["instruction_variant"] == "variant-1"
        assert data["ai_assisted"] is True

    def test_annotation_marks_task_labeled(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org, min_annotations_per_task=1)
        resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["done"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        # Check task is labeled
        test_db.refresh(tasks[0])
        assert tasks[0].is_labeled is True


@pytest.mark.integration
class TestListAnnotations:
    """GET /api/projects/tasks/{task_id}/annotations"""

    def test_list_annotations_empty(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_annotations_after_create(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Create annotation
        client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={"result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["x"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # List
        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_list_annotations_all_users(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Create annotation as admin
        client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={"result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["admin"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # List all users
        resp = client.get(
            f"/api/projects/tasks/{tasks[0].id}/annotations?all_users=true",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_list_annotations_task_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/tasks/nonexistent/annotations",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestUpdateAnnotation:
    """PATCH /api/projects/annotations/{annotation_id}"""

    def test_update_annotation_result(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Create
        create_resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={"result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["original"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        ann_id = create_resp.json()["id"]

        # Update
        resp = client.patch(
            f"/api/projects/annotations/{ann_id}",
            json={"result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["updated"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_update_annotation_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.patch(
            "/api/projects/annotations/nonexistent-ann-id",
            json={"result": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_annotation_cancel_status(self, client, test_db, test_users, auth_headers, test_org):
        project, tasks = _setup(test_db, test_users[0], test_org)
        # Create non-cancelled annotation
        create_resp = client.post(
            f"/api/projects/tasks/{tasks[0].id}/annotations",
            json={"result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["cancel me"]}}]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        ann_id = create_resp.json()["id"]

        # Cancel it
        resp = client.patch(
            f"/api/projects/annotations/{ann_id}",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["cancel me"]}}],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] is True
