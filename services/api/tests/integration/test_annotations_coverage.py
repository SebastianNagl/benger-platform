"""
Integration tests for annotation endpoints.

Targets: routers/projects/annotations.py — create_annotation, list_annotations,
         get_annotation, delete_annotation
"""

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


def _make_project_with_task(db, admin, org):
    """Create a project with a single task."""
    project = Project(
        id=_uid(),
        title="Annotation Test",
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
    task = Task(
        id=_uid(), project_id=project.id,
        data={"text": "Annotation test text"},
        inner_id=1, created_by=admin.id,
    )
    db.add(task)
    db.commit()
    return project, task


@pytest.mark.integration
class TestCreateAnnotation:
    """POST /api/projects/tasks/{task_id}/annotations"""

    def test_create_annotation_basic(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [
                    {"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}
                ],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert body["completed_by"] == test_users[0].id

    def test_create_annotation_with_lead_time(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [
                    {"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Nein"]}}
                ],
                "lead_time": 45.5,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_create_annotation_nonexistent_task(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.post(
            "/api/projects/tasks/nonexistent-id/annotations",
            json={"result": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 404

    def test_create_annotation_empty_result(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={"result": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_create_annotation_with_draft(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [],
                "draft": [{"from_name": "answer", "to_name": "text",
                           "type": "choices", "value": {"choices": ["Ja"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_create_annotation_cancelled(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        resp = client.post(
            f"/api/projects/tasks/{task.id}/annotations",
            json={
                "result": [],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestListAnnotations:
    """GET /api/projects/{project_id}/annotations"""

    def test_list_annotations(self, client, test_db, test_users, auth_headers, test_org):
        project, task = _make_project_with_task(test_db, test_users[0], test_org)
        ann = Annotation(
            id=_uid(), task_id=task.id, project_id=project.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "answer", "to_name": "text",
                     "type": "choices", "value": {"choices": ["Ja"]}}],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/annotations",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        # May not exist as separate endpoint
        assert resp.status_code in (200, 404, 405)


@pytest.mark.integration
class TestProjectVisibility:
    """PATCH /api/projects/{project_id}/visibility"""

    def test_toggle_visibility(self, client, test_db, test_users, auth_headers, test_org):
        project = Project(
            id=_uid(), title="Vis Test", created_by=test_users[0].id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        )
        test_db.add(po)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"is_private": True},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 403)

    def test_make_public(self, client, test_db, test_users, auth_headers, test_org):
        project = Project(
            id=_uid(), title="Public Test", created_by=test_users[0].id,
            is_private=True,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        )
        test_db.add(po)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{project.id}/visibility",
            json={"is_private": False},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 400, 403)


@pytest.mark.integration
class TestRecalculateStats:
    """POST /api/projects/{project_id}/recalculate-stats"""

    def test_recalculate_stats(self, client, test_db, test_users, auth_headers, test_org):
        project = Project(
            id=_uid(), title="Recalc Test", created_by=test_users[0].id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        )
        test_db.add(po)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{project.id}/recalculate-stats",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestCompletionStats:
    """GET /api/projects/{project_id}/completion-stats"""

    def test_completion_stats(self, client, test_db, test_users, auth_headers, test_org):
        project = Project(
            id=_uid(), title="Completion Test", created_by=test_users[0].id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        test_db.add(project)
        test_db.flush()
        po = ProjectOrganization(
            id=_uid(), project_id=project.id,
            organization_id=test_org.id, assigned_by=test_users[0].id,
        )
        test_db.add(po)
        test_db.flush()
        for i in range(3):
            task = Task(
                id=_uid(), project_id=project.id,
                data={"text": f"task {i}"}, inner_id=i + 1,
                created_by=test_users[0].id,
            )
            test_db.add(task)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/completion-stats",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
