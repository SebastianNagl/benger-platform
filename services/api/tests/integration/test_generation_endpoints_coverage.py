"""
Integration tests for generation endpoints.

Targets: routers/projects/generation.py — get_generation_config, update_generation_config,
         clear_generation_config, get_project_generation_status

The router was migrated to the async DB lane (``Depends(get_async_db)``), so these
tests seed real rows through the ``async_test_db`` AsyncSession and drive the HTTP
surface through ``async_test_client`` — the sync ``client``/``test_db`` fixtures only
override ``get_db`` (not ``get_async_db``), so rows written there are invisible to the
migrated handler's async connection.

Auth: ``require_user`` is a sync dependency and cannot see rows seeded into the async
test transaction, so it's overridden per-test to return an auth ``User`` built from a
seeded superadmin DB user. ``is_superadmin=True`` short-circuits both
``auth_service.check_project_access_async`` and ``check_project_accessible_async``, so
the real authz path runs and passes trivially.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, ResponseGeneration, User
from project_models import Project, ProjectOrganization, Task


def _uid():
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


async def _make_org(db, admin):
    org = Organization(
        id=_uid(),
        name=f"Org {uuid.uuid4().hex[:6]}",
        display_name=f"Org {uuid.uuid4().hex[:6]}",
        slug=f"org-{uuid.uuid4().hex[:8]}",
    )
    db.add(org)
    await db.flush()
    return org


async def _make_project(db, admin, org, *, generation_config=None, with_generations=False):
    """Create a project for generation testing."""
    project = Project(
        id=_uid(),
        title="Generation Test",
        created_by=admin.id,
        generation_config=generation_config,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    await db.flush()

    po = ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    )
    db.add(po)
    await db.flush()

    t = Task(
        id=_uid(), project_id=project.id,
        data={"text": "Gen task"}, inner_id=1, created_by=admin.id,
    )
    db.add(t)
    await db.flush()

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

    await db.commit()
    return project, generations


@pytest.mark.integration
@pytest.mark.asyncio
class TestGetGenerationConfig:
    """GET /api/projects/{project_id}/generation-config"""

    async def test_get_config_no_config(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, admin)
        project, _ = await _make_project(async_test_db, admin, org)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/generation-config",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "available_options" in body

    async def test_get_config_with_config(self, async_test_client, async_test_db):
        config = {
            "selected_configuration": {
                "models": ["gpt-4o"],
                "temperature": 0.7,
            }
        }
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, admin)
        project, _ = await _make_project(async_test_db, admin, org, generation_config=config)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/generation-config",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "available_options" in body
        assert "selected_configuration" in body
        assert body["selected_configuration"]["models"] == ["gpt-4o"]

    async def test_get_config_nonexistent_project(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/nonexistent/generation-config",
            )
        assert resp.status_code in (403, 404)

    async def test_get_config_contributor(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, admin)
        project, _ = await _make_project(async_test_db, admin, org)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/generation-config",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestUpdateGenerationConfig:
    """PUT /api/projects/{project_id}/generation-config"""

    async def test_update_config(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, admin)
        project, _ = await _make_project(async_test_db, admin, org)
        new_config = {
            "selected_configuration": {"models": ["gpt-4o"], "temperature": 0.5},
        }
        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/generation-config",
                json=new_config,
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body
        assert "config" in body

    async def test_update_config_nonexistent(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.put(
                "/api/projects/nonexistent/generation-config",
                json={"test": True},
            )
        assert resp.status_code in (403, 404)


@pytest.mark.integration
@pytest.mark.asyncio
class TestClearGenerationConfig:
    """DELETE /api/projects/{project_id}/generation-config"""

    async def test_clear_config(self, async_test_client, async_test_db):
        config = {"selected_configuration": {"models": ["gpt-4o"]}}
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, admin)
        project, _ = await _make_project(async_test_db, admin, org, generation_config=config)
        with _as_user(admin):
            resp = await async_test_client.delete(
                f"/api/projects/{project.id}/generation-config",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 204

    async def test_clear_config_nonexistent(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete(
                "/api/projects/nonexistent/generation-config",
            )
        assert resp.status_code in (403, 404)


@pytest.mark.integration
@pytest.mark.asyncio
class TestGetGenerationStatus:
    """GET /api/projects/{project_id}/generation-status"""

    async def test_generation_status_no_generations(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, admin)
        project, _ = await _make_project(async_test_db, admin, org, with_generations=False)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/generation-status",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["generations"] == []
        assert body["is_running"] == False  # noqa: E712
        assert body["latest_status"] is None

    async def test_generation_status_with_generations(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        org = await _make_org(async_test_db, admin)
        project, gens = await _make_project(async_test_db, admin, org, with_generations=True)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/generation-status",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["generations"]) >= 3
        assert body["is_running"] == True  # We have a 'running' generation  # noqa: E712
        for g in body["generations"]:
            assert "id" in g
            assert "model_id" in g
            assert "status" in g

    async def test_generation_status_nonexistent(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(
                "/api/projects/nonexistent/generation-status",
            )
        assert resp.status_code in (403, 404)
