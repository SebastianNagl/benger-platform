"""
Integration tests for generation-related endpoints.

Targets:
- routers/projects/generation.py — 25.00% (40 uncovered)
- routers/generation.py — 19.62% (221 uncovered)
- routers/generation_task_list.py — 33.89% (156 uncovered)

``routers/projects/generation.py`` was migrated to the async DB lane
(``Depends(get_async_db)``), so the classes that hit its endpoints
(``TestProjectGenerationConfig`` / ``TestGenerationStatus``) seed real rows
through the ``async_test_db`` AsyncSession and drive the HTTP surface through
``async_test_client``. ``require_user`` is overridden per-test to a seeded
superadmin DB user (``is_superadmin=True`` short-circuits the async access
checks). ``TestGenerationRouter`` hits the generation-task-list router
(``/api/generation-tasks/...``), which was also migrated to the async DB lane,
so it uses the same ``async_test_client`` / ``async_test_db`` fixtures.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
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


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"gen-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Gen User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db):
    org = Organization(
        id=_uid(),
        name=f"Org {uuid.uuid4().hex[:6]}",
        display_name=f"Org {uuid.uuid4().hex[:6]}",
        slug=f"org-{uuid.uuid4().hex[:8]}",
    )
    db.add(org)
    await db.flush()
    return org


async def _setup_async(db, admin, org, *, num_tasks=3, generation_config=None, with_generations=False):
    """Create project with tasks and optional generations (async DB lane)."""
    project = Project(
        id=_uid(),
        title=f"Gen Test {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config=generation_config,
    )
    db.add(project)
    await db.flush()

    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    await db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=project.id,
            data={"text": f"Gen text #{i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()

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
        await db.flush()

        for i, t in enumerate(tasks):
            gen = Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=t.id,
                model_id="gpt-4o",
                run_index=i,
                case_data=f'{{"text": "Case data for {t.id}"}}',
                response_content=f"Generated response for {t.id}",
                label_config_version="v1",
                status="completed",
            )
            db.add(gen)
            generations.append(gen)
        await db.flush()

    await db.commit()
    return project, tasks, generations


@pytest.mark.integration
@pytest.mark.asyncio
class TestProjectGenerationConfig:
    """Tests for project-level generation config endpoints."""

    async def test_get_generation_config(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project, _, _ = await _setup_async(
            async_test_db, admin, org,
            generation_config={"selected_configuration": {"models": ["gpt-4o"]}},
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE_PROJECT}/{project.id}/generation-config",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "available_options" in data

    async def test_get_generation_config_empty(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project, _, _ = await _setup_async(async_test_db, admin, org)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE_PROJECT}/{project.id}/generation-config",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    async def test_update_generation_config(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project, _, _ = await _setup_async(async_test_db, admin, org)
        with _as_user(admin):
            resp = await async_test_client.put(
                f"{BASE_PROJECT}/{project.id}/generation-config",
                json={"selected_configuration": {"models": ["gpt-4o"], "temperature": 0.7}},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200

    async def test_clear_generation_config(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project, _, _ = await _setup_async(
            async_test_db, admin, org,
            generation_config={"selected_configuration": {"models": ["gpt-4o"]}},
        )
        with _as_user(admin):
            resp = await async_test_client.delete(
                f"{BASE_PROJECT}/{project.id}/generation-config",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 204

    async def test_generation_config_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE_PROJECT}/nonexistent/generation-config",
            )
        assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestGenerationStatus:
    """Tests for project generation status endpoint."""

    async def test_get_generation_status_with_gens(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project, _, _ = await _setup_async(async_test_db, admin, org, with_generations=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE_PROJECT}/{project.id}/generation-status",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "generations" in data
        assert "is_running" in data

    async def test_get_generation_status_empty(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project, _, _ = await _setup_async(async_test_db, admin, org, with_generations=False)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE_PROJECT}/{project.id}/generation-status",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["generations"] == []
        assert data["is_running"] == False  # noqa: E712

    async def test_get_generation_status_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                f"{BASE_PROJECT}/nonexistent/generation-status",
            )
        assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestGenerationRouter:
    """Tests for the generation-task-list router (``/api/generation-tasks/...``).

    ``routers/generation_task_list.py`` was migrated to the async DB lane
    (``Depends(get_async_db)``), so these seed real rows through
    ``async_test_db`` and drive the HTTP surface via ``async_test_client``;
    ``require_user`` is overridden to a seeded superadmin (short-circuits the
    async access checks).
    """

    async def test_list_generations(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        project, _, _ = await _setup_async(
            async_test_db, admin, org, with_generations=True
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project.id}/task-status",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code in (200, 403, 404)

    async def test_legacy_null_structure_key_visible_with_configured_structures(
        self, async_test_client, async_test_db
    ):
        """Legacy responses (structure_key=NULL) must be visible when prompt structures are configured."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        config = {
            "selected_configuration": {"models": ["gpt-4o"]},
            "prompt_structures": {"default": {"system_prompt": "You are helpful."}},
        }
        project, tasks, _ = await _setup_async(
            async_test_db, admin, org, generation_config=config
        )

        # Create a legacy response with structure_key=NULL (pre-structure era)
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id="gpt-4o",
            task_id=tasks[0].id,
            status="completed",
            structure_key=None,
            created_by=admin.id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        async_test_db.add(rg)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project.id}/task-status",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()

        # The legacy NULL response should appear under the "default" structure
        task_statuses = data["tasks"][0]["generation_status"]["gpt-4o"]
        assert len(task_statuses) > 0
        assert task_statuses[0]["status"] == "completed"

    async def test_exact_structure_key_preferred_over_null_fallback(
        self, async_test_client, async_test_db
    ):
        """Exact structure_key match takes priority over NULL legacy response."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db)
        config = {
            "selected_configuration": {"models": ["gpt-4o"]},
            "prompt_structures": {"default": {"system_prompt": "You are helpful."}},
        }
        project, tasks, _ = await _setup_async(
            async_test_db, admin, org, generation_config=config
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
            created_by=admin.id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        async_test_db.add(rg_null)
        await async_test_db.flush()

        # Create exact-match response (newer)
        rg_exact_id = _uid()
        rg_exact = ResponseGeneration(
            id=rg_exact_id,
            project_id=project.id,
            model_id="gpt-4o",
            task_id=tasks[0].id,
            status="completed",
            structure_key="default",
            result="new structured response",
            created_by=admin.id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        async_test_db.add(rg_exact)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/generation-tasks/projects/{project.id}/task-status",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        data = resp.json()

        task_statuses = data["tasks"][0]["generation_status"]["gpt-4o"]
        assert len(task_statuses) > 0
        # The exact-match response should be returned, not the legacy NULL one
        assert task_statuses[0]["generation_id"] == rg_exact_id

    # start_generation tested in test_remaining_router_endpoints.py::TestGenerationStatusEndpoints
