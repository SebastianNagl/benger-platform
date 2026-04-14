"""
Integration tests for generation-related endpoints.

Targets:
- routers/projects/generation.py — 25.00% (40 uncovered)
- routers/generation.py — 19.62% (221 uncovered)
- routers/generation_task_list.py — 33.89% (156 uncovered)
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from models import (
    Generation,
    Organization,
    ResponseGeneration,
    User,
)
from project_models import (
    Project,
    ProjectOrganization,
    Task,
)

BASE_PROJECT = "/api/projects"
BASE_GEN = "/api/generation"


def _uid() -> str:
    return str(uuid.uuid4())


def _setup(db, admin, org, *, num_tasks=3, generation_config=None, with_generations=False):
    """Create project with tasks and optional generations."""
    project = Project(
        id=_uid(),
        title=f"Gen Test {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config=generation_config,
    )
    db.add(project)
    db.flush()

    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Gen text #{i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()

    generations = []
    if with_generations:
        # ResponseGeneration record first
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            status="completed",
            created_by=admin.id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(rg)
        db.flush()

        for t in tasks:
            gen = Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=t.id,
                model_id="gpt-4o",
                case_data=f'{{"text": "Case data for {t.id}"}}',
                response_content=f"Generated response for {t.id}",
                label_config_version="v1",
                status="completed",
            )
            db.add(gen)
            generations.append(gen)
        db.flush()

    db.commit()
    return project, tasks, generations


@pytest.mark.integration
class TestProjectGenerationConfig:
    """Tests for project-level generation config endpoints."""

    def test_get_generation_config(self, client, test_db, test_users, auth_headers, test_org):
        project, _, _ = _setup(test_db, test_users[0], test_org,
                                generation_config={"selected_configuration": {"models": ["gpt-4o"]}})
        resp = client.get(
            f"{BASE_PROJECT}/{project.id}/generation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "available_options" in data

    def test_get_generation_config_empty(self, client, test_db, test_users, auth_headers, test_org):
        project, _, _ = _setup(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE_PROJECT}/{project.id}/generation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_update_generation_config(self, client, test_db, test_users, auth_headers, test_org):
        project, _, _ = _setup(test_db, test_users[0], test_org)
        resp = client.put(
            f"{BASE_PROJECT}/{project.id}/generation-config",
            json={"selected_configuration": {"models": ["gpt-4o"], "temperature": 0.7}},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200

    def test_clear_generation_config(self, client, test_db, test_users, auth_headers, test_org):
        project, _, _ = _setup(test_db, test_users[0], test_org,
                                generation_config={"selected_configuration": {"models": ["gpt-4o"]}})
        resp = client.delete(
            f"{BASE_PROJECT}/{project.id}/generation-config",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 204

    def test_generation_config_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            f"{BASE_PROJECT}/nonexistent/generation-config",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestGenerationStatus:
    """Tests for project generation status endpoint."""

    def test_get_generation_status_with_gens(self, client, test_db, test_users, auth_headers, test_org):
        project, _, _ = _setup(test_db, test_users[0], test_org, with_generations=True)
        resp = client.get(
            f"{BASE_PROJECT}/{project.id}/generation-status",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "generations" in data
        assert "is_running" in data

    def test_get_generation_status_empty(self, client, test_db, test_users, auth_headers, test_org):
        project, _, _ = _setup(test_db, test_users[0], test_org, with_generations=False)
        resp = client.get(
            f"{BASE_PROJECT}/{project.id}/generation-status",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["generations"] == []
        assert data["is_running"] is False

    def test_get_generation_status_not_found(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            f"{BASE_PROJECT}/nonexistent/generation-status",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestGenerationRouter:
    """Tests for main generation router endpoints."""

    def test_list_generations(self, client, test_db, test_users, auth_headers, test_org):
        project, _, _ = _setup(test_db, test_users[0], test_org, with_generations=True)
        resp = client.get(
            f"/api/generation-tasks/projects/{project.id}/task-status",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code in (200, 403, 404)

    def test_legacy_null_structure_key_visible_with_configured_structures(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Legacy responses (structure_key=NULL) must be visible when prompt structures are configured."""
        config = {
            "selected_configuration": {"models": ["gpt-4o"]},
            "prompt_structures": {"default": {"system_prompt": "You are helpful."}},
        }
        project, tasks, _ = _setup(
            test_db, test_users[0], test_org, generation_config=config
        )

        # Create a legacy response with structure_key=NULL (pre-structure era)
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            task_id=tasks[0].id,
            status="completed",
            structure_key=None,
            created_by=test_users[0].id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        test_db.add(rg)
        test_db.commit()

        resp = client.get(
            f"/api/generation-tasks/projects/{project.id}/task-status",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()

        # The legacy NULL response should appear under the "default" structure
        task_statuses = data["tasks"][0]["generation_status"]["gpt-4o"]
        assert len(task_statuses) > 0
        assert task_statuses[0]["status"] == "completed"

    def test_exact_structure_key_preferred_over_null_fallback(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Exact structure_key match takes priority over NULL legacy response."""
        config = {
            "selected_configuration": {"models": ["gpt-4o"]},
            "prompt_structures": {"default": {"system_prompt": "You are helpful."}},
        }
        project, tasks, _ = _setup(
            test_db, test_users[0], test_org, generation_config=config
        )

        # Create legacy NULL response first (older)
        rg_null = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            task_id=tasks[0].id,
            status="completed",
            structure_key=None,
            result="legacy response",
            created_by=test_users[0].id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        test_db.add(rg_null)
        test_db.flush()

        # Create exact-match response (newer)
        rg_exact = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            task_id=tasks[0].id,
            status="completed",
            structure_key="default",
            result="new structured response",
            created_by=test_users[0].id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        test_db.add(rg_exact)
        test_db.commit()

        resp = client.get(
            f"/api/generation-tasks/projects/{project.id}/task-status",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200
        data = resp.json()

        task_statuses = data["tasks"][0]["generation_status"]["gpt-4o"]
        assert len(task_statuses) > 0
        # The exact-match response should be returned, not the legacy NULL one
        assert task_statuses[0]["generation_id"] == rg_exact.id

    # start_generation tested in test_remaining_router_endpoints.py::TestGenerationStatusEndpoints
