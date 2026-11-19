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
                project.id, auth_outsider, async_test_db
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


class TestNormalizePromptStructures:
    """Test _normalize_prompt_structures (pure) — issue #292."""

    def test_dict_passthrough(self):
        from routers.prompt_structures import _normalize_prompt_structures

        value = {"s1": {"name": "S1"}}
        assert _normalize_prompt_structures(value) is value

    def test_list_keyed_by_key_then_name_then_index(self):
        from routers.prompt_structures import _normalize_prompt_structures

        result = _normalize_prompt_structures(
            [
                {"key": "k1", "name": "First", "system_prompt": "s"},
                {"name": "Second", "system_prompt": "s"},
                {"system_prompt": "s"},
            ]
        )
        assert set(result) == {"k1", "Second", "2"}
        # the key field is lifted out of the entry, not duplicated inside it
        assert "key" not in result["k1"]

    def test_non_dict_entries_dropped(self):
        from routers.prompt_structures import _normalize_prompt_structures

        result = _normalize_prompt_structures(["garbage", {"name": "ok"}])
        assert set(result) == {"ok"}

    def test_scalar_becomes_empty_dict(self):
        from routers.prompt_structures import _normalize_prompt_structures

        assert _normalize_prompt_structures(None) == {}
        assert _normalize_prompt_structures("oops") == {}

    def test_ensure_normalizes_list_shape(self):
        from routers.prompt_structures import ensure_generation_config_structure

        project = Mock()
        project.generation_config = {
            "prompt_structures": [{"name": "default", "template": "t"}]
        }
        ensure_generation_config_structure(project)
        assert isinstance(project.generation_config["prompt_structures"], dict)


class TestListShapedPromptStructures:
    """Regression tests for issue #292 — list-shaped legacy data must not 500."""

    @pytest.mark.asyncio
    async def test_list_endpoint_with_legacy_list_shape(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        # Exact shape observed in the reproduction project: entries carry
        # legacy fields and do not match PromptStructureBase at all.
        project = await _make_project(
            async_test_db,
            creator,
            generation_config={
                "prompt_structures": [
                    {
                        "name": "default",
                        "template": "Answer the following: {{text}}",
                        "is_active": True,
                    }
                ]
            },
        )
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures"
            )
        # 200 with the unmappable legacy entry skipped — never a 500
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {}

    @pytest.mark.asyncio
    async def test_list_endpoint_with_valid_list_entries(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db,
            creator,
            generation_config={
                "prompt_structures": [
                    {
                        "key": "s1",
                        "name": "S1",
                        "system_prompt": "sys",
                        "instruction_prompt": "inst",
                    }
                ]
            },
        )
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["s1"]["name"] == "S1"
        assert data["s1"]["key"] == "s1"

    @pytest.mark.asyncio
    async def test_list_endpoint_skips_invalid_dict_entry(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db,
            creator,
            generation_config={
                "prompt_structures": {
                    "good": {
                        "name": "Good",
                        "system_prompt": "sys",
                        "instruction_prompt": "inst",
                    },
                    "bad": {"template": "legacy-only fields"},
                }
            },
        )
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures"
            )
        assert response.status_code == status.HTTP_200_OK
        assert set(response.json()) == {"good"}

    @pytest.mark.asyncio
    async def test_get_structure_malformed_entry_is_404(
        self, async_test_client, async_test_db
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db,
            creator,
            generation_config={
                "prompt_structures": {"bad": {"template": "legacy-only fields"}}
            },
        )
        await async_test_db.commit()

        with _as_user(creator):
            response = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures/bad"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND


ANSWER_LABEL_CONFIG = (
    '<View><Text name="akte" value="$akte"/>'
    '<Number name="anteil" toName="akte"/><TextArea name="begruendung" toName="akte"/></View>'
)


@pytest.mark.flags_on("variant_experiments")
class TestAnswerFormatOptions:
    """The answer-format options of a structure: validated on write, shown
    as generation uses them, with the exact text a generation appends."""

    async def _project(self, db, generation_config=None):
        creator = await _make_user(db, is_superadmin=True)
        project = await _make_project(db, creator, generation_config=generation_config or {})
        project.label_config = ANSWER_LABEL_CONFIG
        await db.commit()
        return creator, project

    @pytest.mark.asyncio
    async def test_options_round_trip_and_preview(self, async_test_client, async_test_db):
        from generation_fidelity import schema_instruction

        creator, project = await self._project(async_test_db)
        url = f"{BASE}/{project.id}/generation-config/structures"
        with _as_user(creator):
            default = await async_test_client.put(
                f"{url}/default",
                json={"name": "D", "system_prompt": "Sys", "instruction_prompt": "$akte"},
            )
            fixed = await async_test_client.put(
                f"{url}/fixed",
                json={
                    "name": "F",
                    "system_prompt": "Sys",
                    "instruction_prompt": "$akte",
                    "append_schema_instruction": False,
                    "structured_output": "off",
                    "format_retry": {"message": "Bitte nur JSON."},
                    "answer_schema": {"fields": {"anteil": {"key": "anteil_{{name}}"}}},
                    "refusal_heuristic": {"pattern": "kann nicht"},
                },
            )
            listing = await async_test_client.get(url)
        assert default.status_code == 200 and fixed.status_code == 200
        body = listing.json()
        assert body["default"]["append_schema_instruction"] is True
        assert body["default"]["structured_output"] == "auto"
        # The preview is the worker's own text for the label config's fields.
        assert body["default"]["schema_instruction_preview"] == schema_instruction(
            ["anteil", "begruendung"]
        )
        assert body["fixed"]["schema_instruction_preview"] is None
        assert body["fixed"]["format_retry"] == {"message": "Bitte nur JSON."}
        assert body["fixed"]["refusal_heuristic"] == {
            "pattern": "kann nicht", "flags": "i", "window": 1500,
        }
        assert body["fixed"]["answer_schema"] == {
            "fields": {"anteil": {"key": "anteil_{{name}}"}}
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("options", [
        {"structured_output": "maybe"},
        {"format_retry": {"max": 1, "message": "x"}},
        {"format_retry": {"message": ""}},
        {"refusal_heuristic": {"pattern": "("}},
        {"answer_schema": {"fields": {"anteil": {}}}},
    ])
    async def test_invalid_options_are_refused(
        self, async_test_client, async_test_db, options
    ):
        creator, project = await self._project(async_test_db)
        with _as_user(creator):
            response = await async_test_client.put(
                f"{BASE}/{project.id}/generation-config/structures/bad",
                json={"name": "B", "system_prompt": "S", "instruction_prompt": "$akte", **options},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_a_stored_invalid_option_is_shown_as_generation_uses_it(
        self, async_test_client, async_test_db
    ):
        """An imported structure with an option that does not validate stays
        listed, with the default the worker falls back to."""
        creator, project = await self._project(async_test_db, {
            "prompt_structures": {
                "imported": {
                    "name": "I", "system_prompt": "S", "instruction_prompt": "$akte",
                    "append_schema_instruction": False,
                    "format_retry": {"message": ""},
                }
            }
        })
        with _as_user(creator):
            response = await async_test_client.get(
                f"{BASE}/{project.id}/generation-config/structures/imported"
            )
        assert response.status_code == 200
        data = response.json()
        assert data["format_retry"] is None
        assert data["append_schema_instruction"] is False
        assert data["schema_instruction_preview"] is None


@pytest.mark.flags_on("variant_experiments")
class TestGenerationRunsPerTaskCap:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("runs, expected", [(100, 200), (101, 422), (0, 422), (True, 422)])
    async def test_generation_config_runs_per_task_bound(
        self, async_test_client, async_test_db, runs, expected
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, creator, generation_config={})
        await async_test_db.commit()
        with _as_user(creator):
            response = await async_test_client.put(
                f"{BASE}/{project.id}/generation-config", json={"runs_per_task": runs}
            )
        assert response.status_code == expected

    @pytest.mark.flags_off("variant_experiments")
    @pytest.mark.asyncio
    @pytest.mark.parametrize("runs, expected", [(25, 200), (26, 422), (100, 422)])
    async def test_generation_config_runs_per_task_bound_without_variant_experiments(
        self, async_test_client, async_test_db, runs, expected
    ):
        creator = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, creator, generation_config={})
        await async_test_db.commit()
        with _as_user(creator):
            response = await async_test_client.put(
                f"{BASE}/{project.id}/generation-config", json={"runs_per_task": runs}
            )
        assert response.status_code == expected

    def test_trigger_request_bound(self):
        from pydantic import ValidationError

        from routers.generation_task_list import GenerationRequest

        assert GenerationRequest(mode="all", runs_per_task=100).runs_per_task == 100
        with pytest.raises(ValidationError):
            GenerationRequest(mode="all", runs_per_task=101)
