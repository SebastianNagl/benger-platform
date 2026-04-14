"""
Coverage boost tests for annotation endpoints.

Targets specific branches in routers/projects/annotations.py:
- create_annotation with various conditions
- list_task_annotations with all_users filter
- update_annotation with was_cancelled status changes
- Timer session integration
- Maximum annotations limit
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership
from project_models import (
    Annotation,
    AnnotationTimerSession,
    Project,
    ProjectOrganization,
    Task,
    TaskAssignment,
)


def _setup_project_with_task(db, user_id, **project_kwargs):
    """Create a project with one task."""
    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title="Test Annotation Project",
        created_by=user_id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        maximum_annotations=3,
        min_annotations_per_task=1,
        assignment_mode="open",
        **project_kwargs,
    )
    db.add(p)
    db.commit()

    # Create org and assignment so the project is accessible
    org = Organization(
        id=str(uuid.uuid4()),
        name="Ann Org",
        slug=f"ann-org-{uuid.uuid4().hex[:8]}",
        display_name="Ann Org",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()

    db.add(OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=user_id,
        organization_id=org.id,
        role="ORG_ADMIN",
        joined_at=datetime.utcnow(),
    ))
    db.add(ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=pid,
        organization_id=org.id,
        assigned_by=user_id,
    ))
    db.commit()

    tid = str(uuid.uuid4())
    t = Task(
        id=tid, project_id=pid, data={"text": "test data"}, inner_id=1
    )
    db.add(t)
    db.commit()

    return p, t, org


class TestCreateAnnotation:
    """Test create_annotation endpoint."""

    def test_create_annotation_basic(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["hello"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == t.id
        assert data["was_cancelled"] is False

    def test_create_cancelled_annotation(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["x"]}}],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] is True

    def test_create_annotation_task_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/projects/tasks/nonexistent/annotations",
            json={"result": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_create_annotation_with_timing_data(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["y"]}}],
                "lead_time": 45.5,
                "active_duration_ms": 40000,
                "focused_duration_ms": 35000,
                "tab_switches": 2,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_duration_ms"] == 40000
        assert data["tab_switches"] == 2

    def test_create_annotation_with_instruction_variant(
        self, client, auth_headers, test_db, test_users
    ):
        p, t, org = _setup_project_with_task(
            test_db,
            test_users[0].id,
            conditional_instructions=[
                {"id": "variant-1", "content": "Normal instructions", "weight": 50, "ai_allowed": False},
                {"id": "variant-2", "content": "AI instructions", "weight": 50, "ai_allowed": True},
            ],
        )
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["z"]}}],
                "instruction_variant": "variant-2",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_assisted"] is True

    def test_create_annotation_non_ai_variant(
        self, client, auth_headers, test_db, test_users
    ):
        p, t, org = _setup_project_with_task(
            test_db,
            test_users[0].id,
            conditional_instructions=[
                {"id": "variant-1", "content": "Normal", "weight": 100, "ai_allowed": False},
            ],
        )
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["w"]}}],
                "instruction_variant": "variant-1",
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["ai_assisted"] is False

    def test_create_auto_submitted_annotation(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["auto"]}}],
                "auto_submitted": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["auto_submitted"] is True

    def test_create_duplicate_auto_submitted_returns_existing(
        self, client, auth_headers, test_db, test_users
    ):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        # First auto-submit
        resp1 = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["first"]}}],
                "auto_submitted": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp1.status_code == 200
        first_id = resp1.json()["id"]

        # Second auto-submit should return the same
        resp2 = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["second"]}}],
                "auto_submitted": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp2.status_code == 200
        assert resp2.json()["id"] == first_id

    def test_create_annotation_with_timer_session(
        self, client, auth_headers, test_db, test_users
    ):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        # Create a timer session
        session = AnnotationTimerSession(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=p.id,
            user_id=test_users[0].id,
            started_at=datetime.now(timezone.utc) - timedelta(seconds=30),
            time_limit_seconds=300,
            is_strict=False,
        )
        test_db.add(session)
        test_db.commit()

        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={
                "result": [{"from_name": "text", "to_name": "text", "type": "textarea", "value": {"text": ["timer"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        # Timer session should now be completed
        test_db.refresh(session)
        assert session.completed_at is not None

    def test_create_annotation_empty_result(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        resp = client.post(
            f"/api/projects/tasks/{t.id}/annotations",
            json={"result": []},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200


class TestListAnnotations:
    """Test list_task_annotations endpoint."""

    def test_list_annotations_own_only(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        # Create annotation
        ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["own"]}}],
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{t.id}/annotations",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_annotations_all_users(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        # Add membership for contributor
        test_db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=test_users[1].id,
            organization_id=org.id,
            role="CONTRIBUTOR",
            joined_at=datetime.utcnow(),
        ))
        test_db.commit()

        for uid in [test_users[0].id, test_users[1].id]:
            ann = Annotation(
                id=str(uuid.uuid4()),
                task_id=t.id,
                project_id=p.id,
                completed_by=uid,
                result=[{"from_name": "text", "type": "textarea", "value": {"text": [f"by-{uid}"]}}],
            )
            test_db.add(ann)
        test_db.commit()

        resp = client.get(
            f"/api/projects/tasks/{t.id}/annotations?all_users=true",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_list_annotations_task_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/tasks/nonexistent/annotations",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestUpdateAnnotation:
    """Test update_annotation endpoint."""

    def test_update_annotation_result(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["old"]}}],
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/annotations/{ann.id}",
            json={
                "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["new"]}}],
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_update_annotation_cancel(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["cancel"]}}],
            was_cancelled=False,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/annotations/{ann.id}",
            json={
                "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["cancel"]}}],
                "was_cancelled": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] is True

    def test_update_annotation_uncancel(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["uncancel"]}}],
            was_cancelled=True,
        )
        test_db.add(ann)
        t.cancelled_annotations = 1
        test_db.commit()

        resp = client.patch(
            f"/api/projects/annotations/{ann.id}",
            json={
                "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["uncancel"]}}],
                "was_cancelled": False,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
        assert resp.json()["was_cancelled"] is False

    def test_update_annotation_not_found(self, client, auth_headers):
        resp = client.patch(
            "/api/projects/annotations/nonexistent",
            json={"result": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_annotation_not_owner(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        # Add contributor membership
        test_db.add(OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=test_users[1].id,
            organization_id=org.id,
            role="CONTRIBUTOR",
            joined_at=datetime.utcnow(),
        ))
        test_db.commit()

        ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["owned"]}}],
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/annotations/{ann.id}",
            json={"result": [{"from_name": "text", "type": "textarea", "value": {"text": ["stolen"]}}]},
            headers={**auth_headers["contributor"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 403

    def test_update_annotation_lead_time(self, client, auth_headers, test_db, test_users):
        p, t, org = _setup_project_with_task(test_db, test_users[0].id)
        ann = Annotation(
            id=str(uuid.uuid4()),
            task_id=t.id,
            project_id=p.id,
            completed_by=test_users[0].id,
            result=[{"from_name": "text", "type": "textarea", "value": {"text": ["time"]}}],
            lead_time=10.0,
        )
        test_db.add(ann)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/annotations/{ann.id}",
            json={
                "result": [{"from_name": "text", "type": "textarea", "value": {"text": ["time"]}}],
                "lead_time": 25.5,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200
