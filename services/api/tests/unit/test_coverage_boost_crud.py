"""
Coverage boost tests for project CRUD endpoints.

Targets specific branches in routers/projects/crud.py:
- list_projects with search, is_archived filters
- create_project with private vs org, label_config validation
- update_project with deep merge, label_config versioning
- delete_project with permission checks
- update_project_visibility
- recalculate_project_statistics
- get_project_completion_stats
"""

import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Organization, OrganizationMembership, User
from project_models import (
    Annotation,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
)


def _make_project(db, user_id, title="Test", is_private=False, **kwargs):
    pid = str(uuid.uuid4())
    p = Project(
        id=pid,
        title=title,
        created_by=user_id,
        is_private=is_private,
        label_config="<View><Text name='text' value='$text'/></View>",
        **kwargs,
    )
    db.add(p)
    db.commit()
    return p


def _make_task(db, project_id, is_labeled=False):
    tid = str(uuid.uuid4())
    t = Task(
        id=tid,
        project_id=project_id,
        data={"text": "hello"},
        inner_id=1,
        is_labeled=is_labeled,
    )
    db.add(t)
    db.commit()
    return t


def _make_org(db, user_id):
    org = Organization(
        id=str(uuid.uuid4()),
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
        display_name="Test Org Display",
        description="test",
        created_at=datetime.utcnow(),
    )
    db.add(org)
    db.commit()
    return org


def _make_membership(db, user_id, org_id, role="ORG_ADMIN"):
    m = OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=user_id,
        organization_id=org_id,
        role=role,
        joined_at=datetime.utcnow(),
    )
    db.add(m)
    db.commit()
    return m


def _assign_project_to_org(db, project_id, org_id, user_id):
    po = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project_id,
        organization_id=org_id,
        assigned_by=user_id,
    )
    db.add(po)
    db.commit()
    return po


class TestListProjects:
    """Test list_projects with various filters."""

    def test_list_projects_no_projects(self, client, auth_headers):
        resp = client.get("/api/projects/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0

    def test_list_projects_with_search(self, client, auth_headers, test_db, test_users):
        _make_project(test_db, test_users[0].id, title="Unique Alpha Search")
        _make_project(test_db, test_users[0].id, title="Unique Beta Search")

        resp = client.get(
            "/api/projects/?search=Alpha",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        titles = [p["title"] for p in data["items"]]
        assert any("Alpha" in t for t in titles)

    def test_list_projects_with_is_archived_false(self, client, auth_headers, test_db, test_users):
        _make_project(test_db, test_users[0].id, title="Archived Test")
        resp = client.get(
            "/api/projects/?is_archived=false",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_list_projects_with_pagination(self, client, auth_headers, test_db, test_users):
        for i in range(5):
            _make_project(test_db, test_users[0].id, title=f"Page Test {i}")

        resp = client.get(
            "/api/projects/?page=1&page_size=2",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_size"] == 2

    def test_list_projects_with_org_context(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, test_users[0].id)
        _make_membership(test_db, test_users[0].id, org.id)
        p = _make_project(test_db, test_users[0].id, title="Org Project")
        _assign_project_to_org(test_db, p.id, org.id, test_users[0].id)

        resp = client.get(
            "/api/projects/",
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_list_projects_private_context(self, client, auth_headers, test_db, test_users):
        _make_project(test_db, test_users[0].id, title="Private P", is_private=True)
        resp = client.get(
            "/api/projects/",
            headers={**auth_headers["admin"], "X-Organization-Context": "private"},
        )
        assert resp.status_code == 200


class TestCreateProject:
    """Test create_project with different input variations."""

    def test_create_private_project(self, client, auth_headers):
        resp = client.post(
            "/api/projects/",
            json={
                "title": "Private Project",
                "description": "A private test project",
                "is_private": True,
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Private Project"
        assert data["is_private"] is True

    def test_create_project_no_org_header_makes_private(self, client, auth_headers):
        resp = client.post(
            "/api/projects/",
            json={"title": "No Header Project"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_create_project_with_org_context(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, test_users[0].id)
        _make_membership(test_db, test_users[0].id, org.id, "ORG_ADMIN")

        resp = client.post(
            "/api/projects/",
            json={"title": "Org Project Create"},
            headers={**auth_headers["admin"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 200

    def test_create_project_with_label_config(self, client, auth_headers):
        resp = client.post(
            "/api/projects/",
            json={
                "title": "With Label Config",
                "label_config": "<View><Text name='text' value='$text'/></View>",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_create_project_invalid_label_config(self, client, auth_headers):
        resp = client.post(
            "/api/projects/",
            json={
                "title": "Bad Config",
                "label_config": "not valid xml at all <<<",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422

    def test_create_project_with_instructions(self, client, auth_headers):
        resp = client.post(
            "/api/projects/",
            json={
                "title": "With Instructions",
                "expert_instruction": "Annotate carefully",
                "show_instruction": True,
                "show_skip_button": False,
                "enable_empty_annotation": False,
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["show_skip_button"] is False

    def test_create_project_annotator_forbidden_in_org(
        self, client, auth_headers, test_db, test_users
    ):
        org = _make_org(test_db, test_users[0].id)
        _make_membership(test_db, test_users[2].id, org.id, "ANNOTATOR")

        resp = client.post(
            "/api/projects/",
            json={"title": "Annotator Try"},
            headers={**auth_headers["annotator"], "X-Organization-Context": org.id},
        )
        assert resp.status_code == 403


class TestGetProject:
    """Test get_project with various access scenarios."""

    def test_get_project_success(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Get Me")
        resp = client.get(f"/api/projects/{p.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get Me"

    def test_get_project_not_found(self, client, auth_headers):
        resp = client.get("/api/projects/nonexistent-id", headers=auth_headers["admin"])
        assert resp.status_code == 404

    def test_get_project_with_tasks(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="With Tasks")
        _make_task(test_db, p.id, is_labeled=False)
        _make_task(test_db, p.id, is_labeled=True)

        resp = client.get(f"/api/projects/{p.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_count"] == 2
        assert data["completed_tasks_count"] == 1


class TestUpdateProject:
    """Test update_project with various field updates."""

    def test_update_title(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Old Title")
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"title": "New Title"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    def test_update_project_not_found(self, client, auth_headers):
        resp = client.patch(
            "/api/projects/nonexistent",
            json={"title": "X"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_update_generation_config_deep_merge(self, client, auth_headers, test_db, test_users):
        p = _make_project(
            test_db,
            test_users[0].id,
            title="Deep Merge",
            generation_config={"selected_configuration": {"models": ["gpt-4o"]}},
        )
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={
                "generation_config": {
                    "selected_configuration": {"parameters": {"temperature": 0.5}}
                }
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        gc = data.get("generation_config", {})
        sc = gc.get("selected_configuration", {})
        assert "gpt-4o" in sc.get("models", [])
        assert sc.get("parameters", {}).get("temperature") == 0.5

    def test_update_evaluation_config_deep_merge(self, client, auth_headers, test_db, test_users):
        p = _make_project(
            test_db,
            test_users[0].id,
            title="Eval Merge",
            evaluation_config={"default_temperature": 0.2},
        )
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"evaluation_config": {"new_field": "value"}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        ec = data.get("evaluation_config", {})
        assert ec.get("default_temperature") == 0.2
        assert ec.get("new_field") == "value"

    def test_update_instructions_alias(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Instr Update")
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"instructions": "New instructions"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["expert_instruction"] == "New instructions"

    def test_update_label_config(self, client, auth_headers, test_db, test_users):
        p = _make_project(
            test_db,
            test_users[0].id,
            title="Label Update",
        )
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={
                "label_config": "<View><Text name='text' value='$text'/><Choices name='c' toName='text'><Choice value='A'/></Choices></View>"
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200

    def test_update_invalid_label_config(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Bad Update")
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"label_config": "<<<not valid>>>"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 422

    def test_update_questionnaire_config(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Questionnaire")
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={
                "questionnaire_enabled": True,
                "questionnaire_config": "<View><Rating name='r' toName='text'/></View>",
            },
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["questionnaire_enabled"] is True

    def test_update_skip_queue(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Skip Queue")
        resp = client.patch(
            f"/api/projects/{p.id}",
            json={"skip_queue": "requeue_for_me"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200


class TestDeleteProject:
    """Test delete_project with various permission scenarios."""

    def test_delete_project_superadmin(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Delete Me")
        resp = client.delete(f"/api/projects/{p.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200

    def test_delete_project_not_found(self, client, auth_headers):
        resp = client.delete("/api/projects/nonexistent", headers=auth_headers["admin"])
        assert resp.status_code == 404

    def test_delete_private_project_by_creator(self, client, auth_headers, test_db, test_users):
        p = _make_project(
            test_db, test_users[1].id, title="Private Delete", is_private=True
        )
        resp = client.delete(f"/api/projects/{p.id}", headers=auth_headers["contributor"])
        assert resp.status_code == 200

    def test_delete_project_non_creator_non_superadmin_forbidden(
        self, client, auth_headers, test_db, test_users
    ):
        p = _make_project(test_db, test_users[0].id, title="No Delete")
        resp = client.delete(f"/api/projects/{p.id}", headers=auth_headers["contributor"])
        assert resp.status_code == 403

    def test_delete_project_with_tasks_and_members(
        self, client, auth_headers, test_db, test_users
    ):
        p = _make_project(test_db, test_users[0].id, title="Full Delete")
        _make_task(test_db, p.id)
        pm = ProjectMember(
            id=str(uuid.uuid4()),
            project_id=p.id,
            user_id=test_users[1].id,
            role="ANNOTATOR",
            assigned_by=test_users[0].id,
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.delete(f"/api/projects/{p.id}", headers=auth_headers["admin"])
        assert resp.status_code == 200


class TestUpdateProjectVisibility:
    """Test update_project_visibility endpoint."""

    def test_make_project_private(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, test_users[0].id)
        _make_membership(test_db, test_users[0].id, org.id)
        p = _make_project(test_db, test_users[0].id, title="Vis Test")
        _assign_project_to_org(test_db, p.id, org.id, test_users[0].id)

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True, "owner_user_id": test_users[0].id},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["is_private"] is True

    def test_make_project_org_assigned(self, client, auth_headers, test_db, test_users):
        org = _make_org(test_db, test_users[0].id)
        _make_membership(test_db, test_users[0].id, org.id)
        p = _make_project(test_db, test_users[0].id, title="Org Assign", is_private=True)

        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": [org.id]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert resp.json()["is_private"] is False

    def test_visibility_change_not_superadmin(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="No Vis")
        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True},
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403

    def test_visibility_project_not_found(self, client, auth_headers):
        resp = client.patch(
            "/api/projects/nonexistent/visibility",
            json={"is_private": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_visibility_no_orgs_provided(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="No Orgs")
        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": []},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 400

    def test_visibility_invalid_org_id(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Invalid Org")
        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": False, "organization_ids": ["nonexistent-org"]},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_visibility_invalid_owner(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Invalid Owner")
        resp = client.patch(
            f"/api/projects/{p.id}/visibility",
            json={"is_private": True, "owner_user_id": "nonexistent-user"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestRecalculateStats:
    """Test recalculate_project_statistics endpoint."""

    def test_recalculate_success(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Recalc")
        _make_task(test_db, p.id, is_labeled=True)
        _make_task(test_db, p.id, is_labeled=False)

        resp = client.post(
            f"/api/projects/{p.id}/recalculate-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_count"] == 2
        assert data["completed_tasks_count"] == 1

    def test_recalculate_not_superadmin(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Recalc NoAdmin")
        resp = client.post(
            f"/api/projects/{p.id}/recalculate-stats",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 403

    def test_recalculate_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/projects/nonexistent/recalculate-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


class TestCompletionStats:
    """Test get_project_completion_stats endpoint."""

    def test_completion_stats_no_tasks(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Empty")
        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["completed"] == 0
        assert data["completion_rate"] == 0.0

    def test_completion_stats_partial(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="Partial")
        _make_task(test_db, p.id, is_labeled=True)
        _make_task(test_db, p.id, is_labeled=False)
        _make_task(test_db, p.id, is_labeled=False)

        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["completed"] == 1
        assert abs(data["completion_rate"] - 33.33) < 1

    def test_completion_stats_all_complete(self, client, auth_headers, test_db, test_users):
        p = _make_project(test_db, test_users[0].id, title="All Done")
        _make_task(test_db, p.id, is_labeled=True)
        _make_task(test_db, p.id, is_labeled=True)

        resp = client.get(
            f"/api/projects/{p.id}/completion-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["completion_rate"] == 100.0

    def test_completion_stats_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/completion-stats",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
