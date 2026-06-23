"""
Integration tests for generation_config deep merge functionality

Tests the project update endpoint to ensure it properly merges generation_config
updates instead of replacing the entire JSON field, preventing data loss.

Issue #818: Prevent model selection from resetting prompt structures selection

NOTE: the project PATCH endpoint (``routers/projects/crud.py``) was migrated to
the async DB lane, so the test drives it through ``async_test_client`` /
``async_test_db``. The prompt-structure side-effects (creating a structure,
marking it active) are applied as direct async-DB writes that mirror exactly
what the structures router persists — keeping the merge assertions on a single
shared async transaction.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from models import User
from project_models import Project


@contextmanager
def _as_user(db_user):
    """Override require_user with an AuthUser mirroring ``db_user``."""
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

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


async def _make_owner(db) -> User:
    owner = User(
        id=str(uuid.uuid4()),
        username=f"gen-merge-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Gen Merge Owner",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(owner)
    await db.flush()
    return owner


async def _make_project(db, owner) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        title="Test Project for Issue #818",
        description="Project for testing generation_config deep merge",
        created_by=owner.id,
        is_private=False,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config={},  # Start with empty config
    )
    db.add(project)
    await db.commit()
    return project


def _ensure_gen_config_shape(project: Project) -> None:
    """Mirror routers.prompt_structures.ensure_generation_config_structure."""
    if project.generation_config is None:
        project.generation_config = {}
    if "selected_configuration" not in project.generation_config:
        project.generation_config["selected_configuration"] = {
            "models": [],
            "active_structures": [],
        }
    if "prompt_structures" not in project.generation_config:
        project.generation_config["prompt_structures"] = {}


async def create_prompt_structure(db, project_id: str, structure_key: str):
    """Persist a prompt structure exactly as the (async) structures router would
    — directly on the shared async transaction so the downstream PATCH / GET
    assertions see it."""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    _ensure_gen_config_shape(project)
    project.generation_config["prompt_structures"][structure_key] = {
        "name": f"Test Structure {structure_key}",
        "description": f"Test structure for {structure_key}",
        "system_prompt": "You are a test assistant",
        "instruction_prompt": "Test instruction",
    }
    flag_modified(project, "generation_config")
    await db.commit()


async def set_active_structures(db, project_id: str, structure_keys: list):
    """Mirror PUT /generation-config/structures (set active) as a direct write."""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    _ensure_gen_config_shape(project)
    available = project.generation_config.get("prompt_structures", {})
    for key in structure_keys:
        assert key in available, f"structure '{key}' must exist before activating"
    project.generation_config["selected_configuration"]["active_structures"] = list(
        structure_keys
    )
    flag_modified(project, "generation_config")
    await db.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_model_selection_preserves_prompt_structures(
    async_test_client, async_test_db
):
    """
    Test that selecting models after prompts preserves prompt selection.

    This is the main bug scenario from Issue #818:
    1. User selects prompt structures
    2. User selects models
    3. Prompt structures should still be present (not reset to 0)
    """
    owner = await _make_owner(async_test_db)
    project = await _make_project(async_test_db, owner)
    project_id = project.id

    # Step 0: Create prompt structures first
    await create_prompt_structure(async_test_db, project_id, "structure1")
    await create_prompt_structure(async_test_db, project_id, "structure2")

    # Step 1: Set prompt structures as active
    await set_active_structures(async_test_db, project_id, ["structure1", "structure2"])

    with _as_user(owner):
        # Step 2: Now set models (this was causing prompts to be reset)
        response = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={
                "generation_config": {
                    "selected_configuration": {"models": ["gpt-4", "claude-3-opus"]}
                }
            },
        )
        assert response.status_code == 200

        # Step 3: Verify BOTH models AND active_structures are preserved
        response = await async_test_client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    project = response.json()

    config = project["generation_config"]["selected_configuration"]

    # The bug was that active_structures would be missing here
    assert "models" in config, "Models should be present"
    assert config["models"] == ["gpt-4", "claude-3-opus"], "Models should be saved correctly"

    assert (
        "active_structures" in config
    ), "Active structures should still be present (Issue #818 fix)"
    assert config["active_structures"] == [
        "structure1",
        "structure2",
    ], "Prompt structures should not be reset"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prompt_selection_preserves_models(async_test_client, async_test_db):
    """
    Test the reverse order: selecting prompts after models preserves model selection.

    This ensures the fix works bidirectionally.
    """
    owner = await _make_owner(async_test_db)
    project = await _make_project(async_test_db, owner)
    project_id = project.id

    # Step 0: Create prompt structures
    await create_prompt_structure(async_test_db, project_id, "structure1")
    await create_prompt_structure(async_test_db, project_id, "structure2")

    with _as_user(owner):
        # Step 1: Set models first
        response = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={"generation_config": {"selected_configuration": {"models": ["gpt-4"]}}},
        )
        assert response.status_code == 200

    # Step 2: Now set prompt structures as active
    await set_active_structures(async_test_db, project_id, ["structure1", "structure2"])

    with _as_user(owner):
        # Step 3: Verify BOTH are preserved
        response = await async_test_client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    project = response.json()

    config = project["generation_config"]["selected_configuration"]

    assert config["models"] == ["gpt-4"], "Models should not be reset when prompts are updated"
    assert config["active_structures"] == [
        "structure1",
        "structure2",
    ], "Prompt structures should be saved"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rapid_sequential_updates_preserve_all_fields(
    async_test_client, async_test_db
):
    """
    Test rapid sequential updates to ensure all fields are preserved.

    This simulates the real-world scenario where a user quickly updates
    multiple parts of the generation config.
    """
    owner = await _make_owner(async_test_db)
    project = await _make_project(async_test_db, owner)
    project_id = project.id

    # Step 0: Create prompt structures
    await create_prompt_structure(async_test_db, project_id, "s1")
    await create_prompt_structure(async_test_db, project_id, "s2")
    await create_prompt_structure(async_test_db, project_id, "s3")

    with _as_user(owner):
        # Update 1: Set models
        response = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={"generation_config": {"selected_configuration": {"models": ["gpt-4"]}}},
        )
        assert response.status_code == 200

    # Update 2: Set prompts as active (immediately after)
    await set_active_structures(async_test_db, project_id, ["s1", "s2"])

    with _as_user(owner):
        # Update 3: Modify models (immediately after)
        response = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={"generation_config": {"selected_configuration": {"models": ["claude-3"]}}},
        )
        assert response.status_code == 200

    # Update 4: Add more prompt structures
    await set_active_structures(async_test_db, project_id, ["s1", "s2", "s3"])

    with _as_user(owner):
        # Verify all updates were preserved
        response = await async_test_client.get(f"/api/projects/{project_id}")
    project = response.json()
    config = project["generation_config"]["selected_configuration"]

    assert config["models"] == ["claude-3"], "Latest model update should be present"
    assert config["active_structures"] == [
        "s1",
        "s2",
        "s3",
    ], "Latest prompt structures should be present"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_partial_generation_config_update_preserves_other_fields(
    async_test_client, async_test_db
):
    """
    Test that updating one part of generation_config preserves other unrelated fields.
    """
    owner = await _make_owner(async_test_db)
    project = await _make_project(async_test_db, owner)
    project_id = project.id

    # Step 0: Create prompt structure
    await create_prompt_structure(async_test_db, project_id, "s1")

    with _as_user(owner):
        # Set up initial state with multiple fields
        response = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={
                "generation_config": {
                    "selected_configuration": {
                        "models": ["gpt-4"],
                        "parameters": {"temperature": 0.7, "max_tokens": 1500},
                        "presentation_mode": "auto",
                    },
                    "other_config": "preserved",
                }
            },
        )
        assert response.status_code == 200

    # Now update only active_structures
    await set_active_structures(async_test_db, project_id, ["s1"])

    with _as_user(owner):
        # Verify all other fields are preserved
        response = await async_test_client.get(f"/api/projects/{project_id}")
    project = response.json()
    config = project["generation_config"]

    assert config["selected_configuration"]["models"] == ["gpt-4"], "Models should be preserved"
    assert (
        config["selected_configuration"]["parameters"]["temperature"] == 0.7
    ), "Parameters should be preserved"
    assert (
        config["selected_configuration"]["parameters"]["max_tokens"] == 1500
    ), "Max tokens should be preserved"
    assert (
        config["selected_configuration"]["presentation_mode"] == "auto"
    ), "Presentation mode should be preserved"
    assert config["other_config"] == "preserved", "Top-level fields should be preserved"
    assert config["selected_configuration"]["active_structures"] == [
        "s1"
    ], "New field should be added"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_updating_non_generation_config_fields_preserves_generation_config(
    async_test_client, async_test_db
):
    """
    Test that updating other project fields doesn't affect generation_config.
    """
    owner = await _make_owner(async_test_db)
    project = await _make_project(async_test_db, owner)
    project_id = project.id

    # Step 0: Create prompt structures
    await create_prompt_structure(async_test_db, project_id, "s1")
    await create_prompt_structure(async_test_db, project_id, "s2")

    with _as_user(owner):
        # Set up generation_config with models
        response = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={"generation_config": {"selected_configuration": {"models": ["gpt-4"]}}},
        )
        assert response.status_code == 200

    # Set active structures
    await set_active_structures(async_test_db, project_id, ["s1", "s2"])

    with _as_user(owner):
        # Update title and description (non-generation_config fields)
        response = await async_test_client.patch(
            f"/api/projects/{project_id}",
            json={"title": "Updated Title", "description": "Updated description"},
        )
        assert response.status_code == 200

        # Verify generation_config is untouched
        response = await async_test_client.get(f"/api/projects/{project_id}")
    project = response.json()

    assert project["title"] == "Updated Title"
    assert project["description"] == "Updated description"

    config = project["generation_config"]["selected_configuration"]
    assert config["models"] == ["gpt-4"], "Models should be unchanged"
    assert config["active_structures"] == ["s1", "s2"], "Prompt structures should be unchanged"
