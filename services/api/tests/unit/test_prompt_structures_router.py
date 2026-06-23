"""Tests for prompt_structures router.

The router was migrated to the async DB lane (``Depends(get_async_db)``), so
the endpoint tests seed real projects via ``async_test_db`` and drive the HTTP
surface through ``async_test_client``. ``require_user`` (a sync dependency) is
overridden to return an auth ``User`` matching the seeded creator so the
async-only DB transaction stays the single source of truth.

Pure helpers (``validate_structure_key``, ``ensure_generation_config_structure``)
keep their fast, DB-free unit coverage. ``get_project_or_403`` is now an async
coroutine reading via ``db.execute`` and is exercised against the real async
session.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Project


BASE = "/api/projects"


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


async def _make_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"ps-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="PS User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, creator, *, generation_config=None):
    p = Project(
        id=_uid(),
        title=f"PS Project {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config=generation_config,
    )
    db.add(p)
    await db.flush()
    return p


class TestValidateStructureKey:
    """Test the validate_structure_key helper (pure)."""

    def test_valid_key(self):
        from routers.prompt_structures import validate_structure_key

        validate_structure_key("my_structure_1")

    def test_valid_key_with_hyphens(self):
        from routers.prompt_structures import validate_structure_key

        validate_structure_key("my-structure")

    def test_empty_key_raises(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(HTTPException) as exc_info:
            validate_structure_key("")
        assert exc_info.value.status_code == 400

    def test_too_long_key_raises(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(HTTPException) as exc_info:
            validate_structure_key("a" * 51)
        assert exc_info.value.status_code == 400

    def test_invalid_characters_raises(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(HTTPException) as exc_info:
            validate_structure_key("invalid key!")
        assert exc_info.value.status_code == 400

    def test_special_characters_raises(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(HTTPException) as exc_info:
            validate_structure_key("key/with/slashes")
        assert exc_info.value.status_code == 400


class TestEnsureGenerationConfigStructure:
    """Test ensure_generation_config_structure helper (pure)."""

    def test_none_config(self):
        from routers.prompt_structures import ensure_generation_config_structure

        project = Mock()
        project.generation_config = None
        ensure_generation_config_structure(project)
        assert project.generation_config != None  # noqa: E711
        assert "selected_configuration" in project.generation_config
        assert "prompt_structures" in project.generation_config

    def test_empty_config(self):
        from routers.prompt_structures import ensure_generation_config_structure

        project = Mock()
        project.generation_config = {}
        ensure_generation_config_structure(project)
        assert "selected_configuration" in project.generation_config
        assert "prompt_structures" in project.generation_config

    def test_partial_config(self):
        from routers.prompt_structures import ensure_generation_config_structure

        project = Mock()
        project.generation_config = {"selected_configuration": {"models": []}}
        ensure_generation_config_structure(project)
        assert "prompt_structures" in project.generation_config


class TestGetProjectOr403:
    """Test the async get_project_or_403 helper against the real async session."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.prompt_structures import get_project_or_403

        creator = await _make_user(async_test_db)
        await async_test_db.commit()
        # Handlers receive an auth User (Pydantic) from require_user, never the
        # ORM User — building the same shape here keeps the async membership
        # resolver off the lazy-load (sync-IO) path.
        auth = AuthUser(
            id=creator.id,
            username=creator.username,
            email=creator.email,
            name=creator.name,
            is_superadmin=creator.is_superadmin,
            is_active=True,
            email_verified=True,
            created_at=creator.created_at,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_project_or_403("no-such-project", auth, async_test_db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_permission(self, async_test_db):
        from routers.prompt_structures import get_project_or_403

        owner = await _make_user(async_test_db, is_superadmin=True)
        outsider = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(async_test_db, owner)
        await async_test_db.commit()

        auth_outsider = AuthUser(
            id=outsider.id,
            username=outsider.username,
            email=outsider.email,
            name=outsider.name,
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=outsider.created_at,
        )

        # Outsider (non-superadmin, not creator, no membership) → 403.
        with pytest.raises(HTTPException) as exc_info:
            await get_project_or_403(
                project.id, auth_outsider, async_test_db, org_context="private"
            )
        assert exc_info.value.status_code == 403


class TestPromptStructureEndpoints:
    """Test prompt structure CRUD endpoints through the async client."""

    @pytest.mark.asyncio
    async def test_create_structure(self, async_test_client, async_test_db):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, creator, generation_config={})
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.put(
                f"{BASE}/{project.id}/generation-config/structures/my_struct",
                json={
                    "name": "My Structure",
                    "system_prompt": "You are a legal expert.",
                    "instruction_prompt": "Analyze: {text}",
                },
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["key"] == "my_struct"

    @pytest.mark.asyncio
    async def test_delete_structure_not_found(self, async_test_client, async_test_db):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db, creator, generation_config={"prompt_structures": {}}
        )
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.delete(
                f"{BASE}/{project.id}/generation-config/structures/nonexistent"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_structure_removes_from_active(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db,
            creator,
            generation_config={
                "prompt_structures": {
                    "my_struct": {
                        "system_prompt": "test",
                        "name": "test",
                        "instruction_prompt": "test",
                    }
                },
                "selected_configuration": {
                    "active_structures": ["my_struct", "other"],
                    "models": [],
                },
            },
        )
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.delete(
                f"{BASE}/{project.id}/generation-config/structures/my_struct"
            )
        assert response.status_code == status.HTTP_200_OK
        # Re-read the project from the DB and confirm the active list was pruned.
        await async_test_db.refresh(project)
        assert (
            "my_struct"
            not in project.generation_config["selected_configuration"]["active_structures"]
        )

    @pytest.mark.asyncio
    async def test_set_active_structures_invalid_key(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db,
            creator,
            generation_config={"prompt_structures": {"existing": {}}},
        )
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.put(
                f"{BASE}/{project.id}/generation-config/structures",
                json=["nonexistent"],
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_list_structures_project_not_found(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.get(
                f"{BASE}/nonexistent/generation-config/structures"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_structure_not_found(self, async_test_client, async_test_db):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db, creator, generation_config={"prompt_structures": {}}
        )
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures/nonexistent"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_structure_no_permission(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db, is_superadmin=True)
        outsider = await _make_user(async_test_db, is_superadmin=False)
        project = await _make_project(
            async_test_db,
            owner,
            generation_config={"prompt_structures": {"my_struct": {}}},
        )
        await async_test_db.commit()

        with _as_user(outsider):
            response = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures/my_struct",
                headers={"X-Organization-Context": "private"},
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_list_and_get_structure_happy_path(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db,
            creator,
            generation_config={
                "prompt_structures": {
                    "s1": {
                        "name": "S1",
                        "system_prompt": "sys",
                        "instruction_prompt": "inst",
                    }
                }
            },
        )
        await async_test_db.commit()

        with _as_user(creator):
            list_resp = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures"
            )
            get_resp = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures/s1"
            )
        assert list_resp.status_code == status.HTTP_200_OK
        assert "s1" in list_resp.json()
        assert get_resp.status_code == status.HTTP_200_OK
        assert get_resp.json()["key"] == "s1"
