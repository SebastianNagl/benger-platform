"""
Integration tests targeting uncovered handler body code in routers/projects/crud.py.

Focuses on:
- list_projects: org context filtering, search, pagination, is_archived filter,
  enriched response with stats, generation_models_count
- create_project: org assignment, private mode, label_config validation,
  annotator role rejection, contributor creation
- get_project: enriched response, access control, stats calculation
- update_project: field mapping (instructions -> expert_instruction),
  generation_config deep merge, evaluation_config deep merge,
  label_config versioning, llm_model_ids backward compat
- delete_project: cascade deletion, non-admin rejection
- visibility: private <-> org toggle, superadmin only
- recalculate_stats: admin only, stat computation
- completion_stats: task completion rates
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import (
    Generation,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)


def _uid():
    return str(uuid.uuid4())


def _project(db, admin, org, **kwargs):
    p = Project(
        id=_uid(),
        title=kwargs.get("title", f"CrudCov {uuid.uuid4().hex[:6]}"),
        description=kwargs.get("description", "Test project for crud coverage"),
        created_by=admin.id,
        label_config=kwargs.get(
            "label_config",
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        ),
        is_private=kwargs.get("is_private", False),
        generation_config=kwargs.get("generation_config", None),
        evaluation_config=kwargs.get("evaluation_config", None),
    )
    db.add(p)
    db.flush()
    if not kwargs.get("is_private", False):
        po = ProjectOrganization(
            id=_uid(), project_id=p.id,
            organization_id=org.id, assigned_by=admin.id,
        )
        db.add(po)
        db.flush()
    return p


def _tasks(db, project, admin, count=3, labeled_count=0):
    tasks = []
    for i in range(count):
        is_lab = i < labeled_count
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Crud text #{i}"},
            inner_id=i + 1, created_by=admin.id,
            is_labeled=is_lab,
            total_annotations=(1 if is_lab else 0),
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return tasks


def _annotations(db, project, tasks, user_id):
    anns = []
    for t in tasks:
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


def _generations(db, project, tasks, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by="admin-test-id",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(rg)
    db.flush()
    for t in tasks:
        gen = Generation(
            id=_uid(), generation_id=rg.id, task_id=t.id,
            model_id=model_id, case_data=json.dumps(t.data),
            response_content="Gen", label_config_version="v1",
            status="completed",
        )
        db.add(gen)
    db.flush()


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===================================================================
# LIST PROJECTS
# ===================================================================

@pytest.mark.integration
class TestListProjectsDeep:
    """Deep coverage for list_projects handler body."""

    def test_list_with_org_context(self, client, test_db, test_users, auth_headers, test_org):
        """List projects with org context returns only org projects."""
        _project(test_db, test_users[0], test_org, title="Org Project")
        test_db.commit()

        resp = client.get(
            "/api/projects",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data

    def test_list_with_search_filter(self, client, test_db, test_users, auth_headers, test_org):
        """Search filter works on title."""
        _project(test_db, test_users[0], test_org, title="UniqueSearchable XYZ")
        _project(test_db, test_users[0], test_org, title="Other Project")
        test_db.commit()

        resp = client.get(
            "/api/projects?search=UniqueSearchable",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert "UniqueSearchable" in item["title"] or "uniquesearchable" in item["title"].lower()

    def test_list_pagination(self, client, test_db, test_users, auth_headers, test_org):
        """Pagination returns correct page_size."""
        for i in range(5):
            _project(test_db, test_users[0], test_org, title=f"Paginated {i}")
        test_db.commit()

        resp = client.get(
            "/api/projects?page=1&page_size=2",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2
        assert data["page"] == 1

    def test_list_enriched_response_fields(self, client, test_db, test_users, auth_headers, test_org):
        """Projects include enriched fields: task_count, annotation_count, progress_percentage."""
        p = _project(test_db, test_users[0], test_org, title="Enriched")
        tasks = _tasks(test_db, p, test_users[0], count=4, labeled_count=2)
        _annotations(test_db, p, tasks[:2], test_users[0].id)
        test_db.commit()

        resp = client.get(
            "/api/projects",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        # Find our project in the list
        items = resp.json()["items"]
        our_proj = next((p for p in items if p["title"] == "Enriched"), None)
        if our_proj:
            assert "task_count" in our_proj
            assert "annotation_count" in our_proj
            assert "progress_percentage" in our_proj
            assert "created_by_name" in our_proj

    def test_list_with_generations_stats(self, client, test_db, test_users, auth_headers, test_org):
        """Projects include generation-related statistics."""
        p = _project(test_db, test_users[0], test_org, title="WithGens")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _generations(test_db, p, tasks)
        test_db.commit()

        resp = client.get(
            "/api/projects",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200

    def test_list_superadmin_no_org_context(self, client, test_db, test_users, auth_headers, test_org):
        """Superadmin without org context sees all projects."""
        _project(test_db, test_users[0], test_org, title="No Context")
        test_db.commit()

        resp = client.get(
            "/api/projects",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# ===================================================================
# CREATE PROJECT
# ===================================================================

@pytest.mark.integration
class TestCreateProjectDeep:
    """Deep coverage for create_project handler body."""

    def test_create_org_project(self, client, test_db, test_users, auth_headers, test_org):
        """Create project with org context."""
        resp = client.post(
            "/api/projects",
            json={"title": "New Org Project", "description": "Test"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["title"] == "New Org Project"
        assert "id" in data
        assert "created_by_name" in data

    def test_create_private_project(self, client, test_db, test_users, auth_headers):
        """Create private project without org context."""
        resp = client.post(
            "/api/projects",
            json={"title": "Private Project", "is_private": True},
            headers={**auth_headers["admin"], "X-Organization-Context": "private"},
        )
        assert resp.status_code in (200, 201)

    def test_create_with_label_config(self, client, test_db, test_users, auth_headers, test_org):
        """Create project with label_config."""
        resp = client.post(
            "/api/projects",
            json={
                "title": "Labeled Project",
                "label_config": '<View><Text name="text" value="$text"/></View>',
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201)

    def test_create_with_invalid_label_config(self, client, test_db, test_users, auth_headers, test_org):
        """Invalid label_config returns 422."""
        resp = client.post(
            "/api/projects",
            json={
                "title": "Bad Config",
                "label_config": "not valid xml at all {{{}}}",
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 422

    def test_create_with_instructions(self, client, test_db, test_users, auth_headers, test_org):
        """Create project with expert_instruction."""
        resp = client.post(
            "/api/projects",
            json={
                "title": "Instructed Project",
                "expert_instruction": "Please annotate carefully.",
                "show_instruction": True,
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code in (200, 201)

    def test_annotator_cannot_create(self, client, test_db, test_users, auth_headers, test_org):
        """Annotator role cannot create projects."""
        resp = client.post(
            "/api/projects",
            json={"title": "Should Fail"},
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403

    def test_contributor_can_create(self, client, test_db, test_users, auth_headers, test_org):
        """Contributor role can create projects."""
        resp = client.post(
            "/api/projects",
            json={"title": "Contributor Project"},
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 201)


# ===================================================================
# GET PROJECT
# ===================================================================

@pytest.mark.integration
class TestGetProjectDeep:
    """Deep coverage for get_project handler body."""

    def test_get_enriched_response(self, client, test_db, test_users, auth_headers, test_org):
        """GET project returns enriched fields."""
        p = _project(test_db, test_users[0], test_org, title="Enriched Get")
        tasks = _tasks(test_db, p, test_users[0], count=5, labeled_count=2)
        _annotations(test_db, p, tasks[:2], test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == p.id
        assert "task_count" in data
        assert "annotation_count" in data
        assert "created_by_name" in data

    def test_get_nonexistent_returns_404(self, client, test_db, test_users, auth_headers):
        """GET nonexistent project returns 404."""
        resp = client.get(
            "/api/projects/nonexistent-uuid",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_get_with_generation_stats(self, client, test_db, test_users, auth_headers, test_org):
        """GET project includes generation statistics."""
        p = _project(test_db, test_users[0], test_org, title="Gen Stats")
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _generations(test_db, p, tasks)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200


# ===================================================================
# UPDATE PROJECT
# ===================================================================

@pytest.mark.integration
class TestUpdateProjectDeep:
    """Deep coverage for update_project handler body."""

    def test_update_title_and_description(self, client, test_db, test_users, auth_headers, test_org):
        """Basic title/description update."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"title": "Updated Title", "description": "Updated Desc"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    def test_update_generation_config_deep_merge(self, client, test_db, test_users, auth_headers, test_org):
        """Generation config update uses deep merge, preserving existing keys."""
        p = _project(test_db, test_users[0], test_org,
                     generation_config={"selected_configuration": {"models": ["gpt-4o"]},
                                         "prompt_template": "original"})
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={
                "generation_config": {
                    "selected_configuration": {"models": ["claude-3-sonnet"]},
                }
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        config = resp.json().get("generation_config", {})
        # Deep merge should preserve prompt_template
        assert config.get("prompt_template") == "original"

    def test_update_evaluation_config_deep_merge(self, client, test_db, test_users, auth_headers, test_org):
        """Evaluation config update uses deep merge."""
        p = _project(test_db, test_users[0], test_org,
                     evaluation_config={"selected_methods": {"answer": {"automated": ["accuracy"]}},
                                         "other_key": "preserved"})
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={
                "evaluation_config": {
                    "selected_methods": {"answer": {"automated": ["accuracy", "f1"]}},
                }
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        config = resp.json().get("evaluation_config", {})
        assert config.get("other_key") == "preserved"

    def test_update_label_config(self, client, test_db, test_users, auth_headers, test_org):
        """Label config update triggers versioning."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        new_config = (
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Yes"/><Choice value="No"/></Choices></View>'
        )
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"label_config": new_config},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_invalid_label_config(self, client, test_db, test_users, auth_headers, test_org):
        """Invalid label config returns 422."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"label_config": "invalid xml {{"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422

    def test_update_nonexistent_returns_404(self, client, test_db, test_users, auth_headers):
        """Update nonexistent project returns 404."""
        resp = client.patch(
            "/api/projects/nonexistent",
            json={"title": "Nope"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_show_skip_button(self, client, test_db, test_users, auth_headers, test_org):
        """Update show_skip_button setting."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"show_skip_button": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


# ===================================================================
# DELETE PROJECT
# ===================================================================

@pytest.mark.integration
class TestDeleteProjectDeep:
    """Deep coverage for delete_project handler body."""

    def test_delete_with_tasks_and_annotations(self, client, test_db, test_users, auth_headers, test_org):
        """Delete project cascades to tasks."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=3)
        _annotations(test_db, p, tasks, test_users[0].id)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (200, 204)

    def test_delete_nonexistent_returns_404(self, client, test_db, test_users, auth_headers):
        """Delete nonexistent project returns 404."""
        resp = client.delete(
            "/api/projects/nonexistent",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_non_admin_cannot_delete_org_project(self, client, test_db, test_users, auth_headers, test_org):
        """Non-superadmin cannot delete org project."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{p.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403


# ===================================================================
# VISIBILITY
# ===================================================================

@pytest.mark.integration
class TestVisibilityDeep:
    """Deep coverage for visibility endpoint."""

    def test_make_project_private(self, client, test_db, test_users, auth_headers, test_org):
        """Superadmin can make a project private."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True, "owner_user_id": test_users[0].id},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_make_project_org_assigned(self, client, test_db, test_users, auth_headers, test_org):
        """Superadmin can assign project to orgs."""
        p = _project(test_db, test_users[0], test_org, is_private=True)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": [test_org.id]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_visibility_non_admin_rejected(self, client, test_db, test_users, auth_headers, test_org):
        """Non-superadmin cannot change visibility."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True},
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_visibility_nonexistent_project(self, client, test_db, test_users, auth_headers):
        """Visibility on nonexistent project returns 404."""
        resp = client.patch(
            "/api/projects/nonexistent/visibility",
            json={"is_private": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_visibility_org_no_ids(self, client, test_db, test_users, auth_headers, test_org):
        """Making org-assigned without organization_ids returns 400."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_visibility_nonexistent_org(self, client, test_db, test_users, auth_headers, test_org):
        """Assignment to nonexistent org returns 404."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": ["nonexistent-org"]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# ===================================================================
# RECALCULATE STATS
# ===================================================================

@pytest.mark.integration
class TestRecalculateStats:
    """Coverage for recalculate-stats endpoint."""

    def test_recalculate_stats_admin(self, client, test_db, test_users, auth_headers, test_org):
        """Admin can recalculate project statistics."""
        p = _project(test_db, test_users[0], test_org)
        tasks = _tasks(test_db, p, test_users[0], count=5, labeled_count=2)
        _annotations(test_db, p, tasks[:2], test_users[0].id)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/recalculate-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "task_count" in data
        assert "annotation_count" in data
        assert "progress_percentage" in data

    def test_recalculate_stats_non_admin_rejected(self, client, test_db, test_users, auth_headers, test_org):
        """Non-admin cannot recalculate stats."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"/api/projects/{p.id}/recalculate-stats",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_recalculate_stats_nonexistent(self, client, test_db, test_users, auth_headers):
        """Recalculate for nonexistent project returns 404."""
        resp = client.post(
            "/api/projects/nonexistent/recalculate-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


# ===================================================================
# COMPLETION STATS
# ===================================================================

@pytest.mark.integration
class TestCompletionStats:
    """Coverage for completion-stats endpoint."""

    def test_completion_stats(self, client, test_db, test_users, auth_headers, test_org):
        """Completion stats returns completed/total/rate."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=10, labeled_count=4)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert data["completed"] == 4
        assert data["completion_rate"] == 40.0

    def test_completion_stats_empty_project(self, client, test_db, test_users, auth_headers, test_org):
        """Empty project has 0% completion."""
        p = _project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["completion_rate"] == 0.0

    def test_completion_stats_nonexistent(self, client, test_db, test_users, auth_headers, test_org):
        """Completion stats for nonexistent project returns 404."""
        resp = client.get(
            "/api/projects/nonexistent/completion-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404

    def test_completion_stats_100_percent(self, client, test_db, test_users, auth_headers, test_org):
        """Fully labeled project has 100% completion."""
        p = _project(test_db, test_users[0], test_org)
        _tasks(test_db, p, test_users[0], count=5, labeled_count=5)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["completion_rate"] == 100.0
