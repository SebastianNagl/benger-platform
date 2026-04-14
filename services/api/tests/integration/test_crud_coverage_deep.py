"""
Integration tests targeting uncovered handler body code in routers/projects/crud.py.

Covers lines: 100-197 (list_projects), 217-348 (create_project),
366-398 (get_project), 410-542 (update_project), 553-614 (delete_project),
630-711 (update_project_visibility), 727-746 (recalculate_stats), 772-792 (completion_stats)
"""

import json
import uuid

import pytest
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


def _project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"Crud {uuid.uuid4().hex[:6]}"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        is_private=kwargs.get("is_private", False),
        description=kwargs.get("description", "Test project"),
    )
    db.add(p)
    db.flush()
    po = ProjectOrganization(
        id=_uid(),
        project_id=p.id,
        organization_id=org.id,
        assigned_by=admin.id,
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
            data={"text": f"Task text #{i}"},
            inner_id=i + 1,
            created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotations(db, project, tasks, user_id, lead_time=10.0):
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
            was_cancelled=False,
            lead_time=lead_time,
        )
        db.add(ann)
        anns.append(ann)
    db.flush()
    return anns


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# LIST PROJECTS (lines 100-197)
# ===================================================================

@pytest.mark.integration
class TestListProjects:
    """Cover list_projects handler body."""

    def test_list_projects_with_org_context(self, client, test_db, test_users, auth_headers, test_org):
        """List projects with organization context header."""
        p = _project(test_db, test_users[0], test_org, title="List Test 1")
        _tasks(test_db, p, test_users[0], count=5)
        test_db.commit()

        resp = client.get(
            "/api/projects/",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 1

    def test_list_projects_with_search(self, client, test_db, test_users, auth_headers, test_org):
        """List projects with search filter."""
        p = _project(test_db, test_users[0], test_org, title="UniqueSearchableTitle99")
        _tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.get(
            "/api/projects/?search=UniqueSearchableTitle99",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_list_projects_pagination(self, client, test_db, test_users, auth_headers, test_org):
        """List projects with pagination params."""
        for i in range(3):
            p = _project(test_db, test_users[0], test_org, title=f"Page Test {i}")
            _tasks(test_db, p, test_users[0], count=1)
        test_db.commit()

        resp = client.get(
            "/api/projects/?page=1&page_size=2",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_projects_empty_org(self, client, test_db, test_users, auth_headers, test_org):
        """List projects with archived filter."""
        resp = client.get(
            "/api/projects/?is_archived=false",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_list_projects_private_context(self, client, test_db, test_users, auth_headers, test_org):
        """List private projects."""
        resp = client.get(
            "/api/projects/",
            headers={**auth_headers["admin"], "X-Organization-Context": "private"},
        )
        assert resp.status_code == 200


# ===================================================================
# CREATE PROJECT (lines 217-348)
# ===================================================================

@pytest.mark.integration
class TestCreateProject:
    """Cover create_project handler body."""

    def test_create_project_with_org_context(self, client, test_db, test_users, auth_headers, test_org):
        """Create a project assigned to an organization."""
        resp = client.post(
            "/api/projects/",
            json={
                "title": "Created via API",
                "description": "Integration test project",
                "label_config": '<View><Text name="text" value="$text"/></View>',
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Created via API"

    def test_create_private_project(self, client, test_db, test_users, auth_headers, test_org):
        """Create a private project."""
        resp = client.post(
            "/api/projects/",
            json={
                "title": "Private Project Test",
                "is_private": True,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": "private"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Private Project Test"

    def test_create_project_with_all_fields(self, client, test_db, test_users, auth_headers, test_org):
        """Create project with all optional fields."""
        resp = client.post(
            "/api/projects/",
            json={
                "title": "Full Fields Project",
                "description": "A project with all fields",
                "label_config": '<View><Text name="text" value="$text"/>'
                               '<Choices name="answer" toName="text">'
                               '<Choice value="A"/><Choice value="B"/></Choices></View>',
                "expert_instruction": "Read carefully",
                "show_instruction": True,
                "show_skip_button": True,
                "enable_empty_annotation": False,
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["expert_instruction"] == "Read carefully"

    def test_create_project_invalid_label_config(self, client, test_db, test_users, auth_headers, test_org):
        """Create project with invalid label config should fail."""
        resp = client.post(
            "/api/projects/",
            json={
                "title": "Bad Config Project",
                "label_config": "<Invalid>Not valid XML",
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (422, 400)

    def test_create_project_annotator_denied(self, client, test_db, test_users, auth_headers, test_org):
        """Annotator should not be able to create projects."""
        resp = client.post(
            "/api/projects/",
            json={"title": "Annotator Project"},
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403


# ===================================================================
# GET PROJECT (lines 366-398)
# ===================================================================

@pytest.mark.integration
class TestGetProject:
    """Cover get_project handler body."""

    def test_get_project_detail(self, client, test_db, test_users, auth_headers, test_org):
        """Get project detail with enriched response."""
        p = _project(test_db, test_users[0], test_org, title="Detail Test")
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _annotations(test_db, p, tasks[:3], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Detail Test"
        assert data["task_count"] == 5

    def test_get_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Get non-existent project."""
        resp = client.get(
            f"/api/projects/{_uid()}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_get_project_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        """Get project that has generation data."""
        from datetime import datetime, timezone
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        rg = ResponseGeneration(
            id=_uid(), project_id=p.id, model_id="gpt-4o",
            status="completed", created_by=test_users[0].id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        test_db.add(rg)
        test_db.flush()
        for t in tasks:
            gen = Generation(
                id=_uid(), generation_id=rg.id, task_id=t.id,
                model_id="gpt-4o", case_data="{}", response_content="answer",
                label_config_version="v1", status="completed",
            )
            test_db.add(gen)
        test_db.commit()

        resp = client.get(f"/api/projects/{p.id}", headers=_h(auth_headers, test_org))
        assert resp.status_code == 200


# ===================================================================
# UPDATE PROJECT (lines 410-542)
# ===================================================================

@pytest.mark.integration
class TestUpdateProject:
    """Cover update_project handler body."""

    def test_update_project_title(self, client, test_db, test_users, auth_headers, test_org):
        """Update project title."""
        p = _project(test_db, test_users[0], test_org, title="Old Title")
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"title": "New Title"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    def test_update_project_description(self, client, test_db, test_users, auth_headers, test_org):
        """Update project description."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"description": "Updated description"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_update_project_label_config(self, client, test_db, test_users, auth_headers, test_org):
        """Update project label config triggers versioning."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        new_config = (
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="A"/><Choice value="B"/><Choice value="C"/></Choices></View>'
        )
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"label_config": new_config},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_update_project_instructions_mapping(self, client, test_db, test_users, auth_headers, test_org):
        """Update project with 'instructions' field maps to expert_instruction."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"instructions": "New instructions for annotators"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["expert_instruction"] == "New instructions for annotators"

    def test_update_project_generation_config(self, client, test_db, test_users, auth_headers, test_org):
        """Update project generation_config with deep merge."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"generation_config": {"selected_configuration": {"models": ["gpt-4o"]}}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_update_project_evaluation_config(self, client, test_db, test_users, auth_headers, test_org):
        """Update project evaluation_config with deep merge."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"evaluation_config": {"metrics": ["accuracy"]}},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_update_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Update non-existent project."""
        resp = client.patch(
            f"/api/projects/{_uid()}",
            json={"title": "nope"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_update_project_show_skip_button(self, client, test_db, test_users, auth_headers, test_org):
        """Update project skip button setting."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"show_skip_button": True, "enable_empty_annotation": True},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_update_project_disable_time_limit(self, client, test_db, test_users, auth_headers, test_org):
        """Disabling time limit also disables strict timer."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"annotation_time_limit_enabled": False},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200


# ===================================================================
# DELETE PROJECT (lines 553-614)
# ===================================================================

@pytest.mark.integration
class TestDeleteProject:
    """Cover delete_project handler body."""

    def test_delete_project_as_admin(self, client, test_db, test_users, auth_headers, test_org):
        """Admin can delete a project."""
        p = _project(test_db, test_users[0], test_org, title="To Delete")
        _tasks(test_db, p, test_users[0], count=2)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_delete_project_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Delete non-existent project."""
        resp = client.delete(
            f"/api/projects/{_uid()}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_delete_project_non_admin_denied(self, client, test_db, test_users, auth_headers, test_org):
        """Non-admin cannot delete org project."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403

    def test_delete_project_with_annotations(self, client, test_db, test_users, auth_headers, test_org):
        """Delete project that has annotations."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=2)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200


# ===================================================================
# UPDATE VISIBILITY (lines 630-711)
# ===================================================================

@pytest.mark.integration
class TestUpdateVisibility:
    """Cover update_project_visibility handler body."""

    def test_make_project_private(self, client, test_db, test_users, auth_headers, test_org):
        """Make an org project private."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True, "owner_user_id": test_users[0].id},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_make_project_org_assigned(self, client, test_db, test_users, auth_headers, test_org):
        """Make a private project org-assigned."""
        # Create private project first
        p = Project(
            id=_uid(), title="Private to Org", created_by=test_users[0].id,
            is_private=True,
        )
        test_db.add(p)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": [test_org.id]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_visibility_nonexistent_project(self, client, test_db, test_users, auth_headers, test_org):
        """Update visibility for non-existent project."""
        resp = client.patch(
            f"/api/projects/{_uid()}/visibility",
            json={"is_private": True},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_visibility_no_org_ids_for_public(self, client, test_db, test_users, auth_headers, test_org):
        """Making project public without org IDs should fail."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": []},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400

    def test_visibility_non_admin_denied(self, client, test_db, test_users, auth_headers, test_org):
        """Non-superadmin cannot change visibility."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True},
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403

    def test_visibility_invalid_owner(self, client, test_db, test_users, auth_headers, test_org):
        """Make private with non-existent owner."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True, "owner_user_id": _uid()},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_visibility_invalid_org(self, client, test_db, test_users, auth_headers, test_org):
        """Make public with non-existent org."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": [_uid()]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404


# ===================================================================
# RECALCULATE STATS (lines 727-746)
# ===================================================================

@pytest.mark.integration
class TestRecalculateStats:
    """Cover recalculate_project_statistics handler."""

    def test_recalculate_stats(self, client, test_db, test_users, auth_headers, test_org):
        """Recalculate stats for a project with data."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5)
        _annotations(test_db, p, tasks[:3], test_users[0].id)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/recalculate-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_count"] == 5

    def test_recalculate_stats_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Recalculate stats for non-existent project."""
        resp = client.post(
            f"/api/projects/{_uid()}/recalculate-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_recalculate_stats_non_admin(self, client, test_db, test_users, auth_headers, test_org):
        """Non-admin cannot recalculate stats."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/recalculate-stats",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403


# ===================================================================
# COMPLETION STATS (lines 772-792)
# ===================================================================

@pytest.mark.integration
class TestCompletionStats:
    """Cover get_project_completion_stats handler."""

    def test_completion_stats(self, client, test_db, test_users, auth_headers, test_org):
        """Get completion stats for a project."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=10)
        _annotations(test_db, p, tasks[:6], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_completion_stats_not_found(self, client, test_db, test_users, auth_headers, test_org):
        """Completion stats for non-existent project."""
        resp = client.get(
            f"/api/projects/{_uid()}/completion-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_completion_stats_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        """Completion stats for project with no tasks."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
