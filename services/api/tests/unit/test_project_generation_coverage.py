"""
Unit tests for routers/projects/generation.py.

The generation router was migrated to the async DB lane
(``Depends(get_async_db)``), so these tests call the handlers directly with a
real ``AsyncSession`` (``async_test_db``) seeding real ``Project`` /
``ResponseGeneration`` rows. The access helpers (``auth_service`` and
``check_project_accessible``) are not under test here and are patched as
``AsyncMock``. The handlers' own logic — config read/write/clear, the
generation-status shaping — runs for real. Assertions are unchanged.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from models import ResponseGeneration as DBResponseGeneration, User
from project_models import Project


def _uid() -> str:
    return str(uuid.uuid4())


async def _make_user(db):
    u = User(
        id=_uid(),
        username=f"g-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Gen User",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, *, created_by, generation_config=None):
    p = Project(
        id=_uid(),
        title="Gen Project",
        created_by=created_by,
        generation_config=generation_config,
    )
    db.add(p)
    await db.flush()
    return p


def _auth_allow(allow=True):
    return patch(
        "routers.projects.generation.auth_service.check_project_access_async",
        new=AsyncMock(return_value=allow),
    )


@pytest.mark.asyncio
class TestGetGenerationConfig:

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_project_not_found(self, mock_org, async_test_db):
        from routers.projects.generation import get_generation_config

        await async_test_db.commit()
        request = Mock()
        user = Mock()
        with _auth_allow(True):
            with pytest.raises(HTTPException) as exc_info:
                await get_generation_config("p-missing", request, async_test_db, user)
        assert exc_info.value.status_code == 404

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_no_permission(self, mock_org, async_test_db):
        from routers.projects.generation import get_generation_config

        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id)
        await async_test_db.commit()
        request = Mock()
        with _auth_allow(False):
            with pytest.raises(HTTPException) as exc_info:
                await get_generation_config(project.id, request, async_test_db, user)
        assert exc_info.value.status_code == 403

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_no_config_returns_defaults(self, mock_org, async_test_db):
        from routers.projects.generation import get_generation_config

        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id, generation_config=None)
        await async_test_db.commit()
        request = Mock()
        with _auth_allow(True):
            result = await get_generation_config(project.id, request, async_test_db, user)
        assert "available_options" in result
        assert "selected_configuration" not in result

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_with_config_returns_selected(self, mock_org, async_test_db):
        from routers.projects.generation import get_generation_config

        user = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db,
            created_by=user.id,
            generation_config={"selected_configuration": {"models": ["gpt-4o"]}},
        )
        await async_test_db.commit()
        request = Mock()
        with _auth_allow(True):
            result = await get_generation_config(project.id, request, async_test_db, user)
        assert result["selected_configuration"] == {"models": ["gpt-4o"]}


@pytest.mark.asyncio
class TestUpdateGenerationConfig:

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_success(self, mock_org, async_test_db):
        from routers.projects.generation import update_generation_config

        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id, generation_config={})
        await async_test_db.commit()
        request = Mock()
        config = {"selected_configuration": {"models": ["gpt-4o"]}}
        with _auth_allow(True):
            result = await update_generation_config(project.id, config, request, async_test_db, user)
        assert result["message"] == "Generation configuration updated successfully"
        assert project.generation_config == config

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_no_permission(self, mock_org, async_test_db):
        from routers.projects.generation import update_generation_config

        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id)
        await async_test_db.commit()
        request = Mock()
        with _auth_allow(False):
            with pytest.raises(HTTPException) as exc_info:
                await update_generation_config(project.id, {}, request, async_test_db, user)
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
class TestClearGenerationConfig:

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_success(self, mock_org, async_test_db):
        from routers.projects.generation import clear_generation_config

        user = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=user.id, generation_config={"old": "config"}
        )
        await async_test_db.commit()
        request = Mock()
        with _auth_allow(True):
            await clear_generation_config(project.id, request, async_test_db, user)
        assert project.generation_config == None  # noqa: E711

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_project_not_found(self, mock_org, async_test_db):
        from routers.projects.generation import clear_generation_config

        await async_test_db.commit()
        request = Mock()
        user = Mock()
        with _auth_allow(True):
            with pytest.raises(HTTPException) as exc_info:
                await clear_generation_config("p-missing", request, async_test_db, user)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
class TestGetProjectGenerationStatus:

    @patch("routers.projects.generation.check_project_accessible_async", new_callable=AsyncMock)
    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_no_generations(self, mock_org, mock_access, async_test_db):
        from routers.projects.generation import get_project_generation_status

        mock_access.return_value = True
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id)
        await async_test_db.commit()
        request = Mock()

        result = await get_project_generation_status(project.id, request, async_test_db, user)
        assert result["generations"] == []
        assert result["is_running"] == False  # noqa: E712

    @patch("routers.projects.generation.check_project_accessible_async", new_callable=AsyncMock)
    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    async def test_with_running_generation(self, mock_org, mock_access, async_test_db):
        from routers.projects.generation import get_project_generation_status

        mock_access.return_value = True
        user = await _make_user(async_test_db)
        project = await _make_project(async_test_db, created_by=user.id)
        async_test_db.add(
            DBResponseGeneration(
                id=_uid(),
                project_id=project.id,
                model_id="gpt-4o",
                created_by=user.id,
                status="running",
                started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                completed_at=None,
                error_message=None,
            )
        )
        await async_test_db.commit()
        request = Mock()

        result = await get_project_generation_status(project.id, request, async_test_db, user)
        assert result["is_running"] == True  # noqa: E712
        assert result["latest_status"] == "running"
        assert len(result["generations"]) == 1
