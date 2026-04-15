"""
Integration tests for generation endpoints.

Targets: routers/projects/generation.py — get_generation_config, update_generation_config,
         clear_generation_config, get_project_generation_status
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from models import ResponseGeneration
from project_models import Project, ProjectOrganization, Task


def _uid():
    return str(uuid.uuid4())


def _make_project(db, admin, org, *, generation_config=None, with_generations=False):
    """Create a project for generation testing."""
    project = Project(
        id=_uid(),
        title="Generation Test",
        created_by=admin.id,
        generation_config=generation_config,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()

    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()

    t = Task(
        id=_uid(), project_id=project.id,
        data={"text": "Gen task"}, inner_id=1, created_by=admin.id,
    )
    db.add(t)
    db.flush()

    generations = []
    if with_generations:
        for model_id in ["gpt-4o", "claude-3-sonnet"]:
            rg = ResponseGeneration(
                id=_uid(),
                project_id=project.id,
                model_id=model_id,
                status="completed",
                created_by=admin.id,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(rg)
            generations.append(rg)
        # Add one running
        rg_running = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gemini-1.5-pro",
            status="running",
            created_by=admin.id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(rg_running)
        generations.append(rg_running)

    db.commit()
    return project, generations


@pytest.mark.integration
class TestGetGenerationConfig:
    """GET /api/projects/{project_id}/generation-config"""

    def test_get_config_no_config(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{project.id}/generation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "available_options" in body

    def test_get_config_with_config(self, client, test_db, test_users, auth_headers, test_org):
        config = {
            "selected_configuration": {
                "models": ["gpt-4o"],
                "temperature": 0.7,
            }
        }
        project, _ = _make_project(test_db, test_users[0], test_org, generation_config=config)
        resp = client.get(
            f"/api/projects/{project.id}/generation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "available_options" in body
        assert "selected_configuration" in body
        assert body["selected_configuration"]["models"] == ["gpt-4o"]

    def test_get_config_nonexistent_project(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/generation-config",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (403, 404)

    def test_get_config_contributor(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/projects/{project.id}/generation-config",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestUpdateGenerationConfig:
    """PUT /api/projects/{project_id}/generation-config"""

    def test_update_config(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _make_project(test_db, test_users[0], test_org)
        new_config = {
            "selected_configuration": {"models": ["gpt-4o"], "temperature": 0.5},
        }
        resp = client.put(
            f"/api/projects/{project.id}/generation-config",
            json=new_config,
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body
        assert "config" in body

    def test_update_config_nonexistent(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/projects/nonexistent/generation-config",
            json={"test": True},
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (403, 404)


@pytest.mark.integration
class TestClearGenerationConfig:
    """DELETE /api/projects/{project_id}/generation-config"""

    def test_clear_config(self, client, test_db, test_users, auth_headers, test_org):
        config = {"selected_configuration": {"models": ["gpt-4o"]}}
        project, _ = _make_project(test_db, test_users[0], test_org, generation_config=config)
        resp = client.delete(
            f"/api/projects/{project.id}/generation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 204

    def test_clear_config_nonexistent(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            "/api/projects/nonexistent/generation-config",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (403, 404)


@pytest.mark.integration
class TestGetGenerationStatus:
    """GET /api/projects/{project_id}/generation-status"""

    def test_generation_status_no_generations(self, client, test_db, test_users, auth_headers, test_org):
        project, _ = _make_project(test_db, test_users[0], test_org, with_generations=False)
        resp = client.get(
            f"/api/projects/{project.id}/generation-status",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["generations"] == []
        assert body["is_running"] is False
        assert body["latest_status"] is None

    def test_generation_status_with_generations(self, client, test_db, test_users, auth_headers, test_org):
        project, gens = _make_project(test_db, test_users[0], test_org, with_generations=True)
        resp = client.get(
            f"/api/projects/{project.id}/generation-status",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["generations"]) >= 3
        assert body["is_running"] is True  # We have a 'running' generation
        for g in body["generations"]:
            assert "id" in g
            assert "model_id" in g
            assert "status" in g

    def test_generation_status_nonexistent(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/projects/nonexistent/generation-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code in (403, 404)
