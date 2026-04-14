"""
Integration tests for generation_config deep merge functionality

Tests the project update endpoint to ensure it properly merges generation_config
updates instead of replacing the entire JSON field, preventing data loss.

Issue #818: Prevent model selection from resetting prompt structures selection
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from project_models import Project


@pytest.fixture
def auth_headers(test_user):
    """Get authentication headers for test user"""
    return {"Authorization": f"Bearer {test_user.token}"}


@pytest.fixture
def test_project(db: Session, test_user):
    """Create a test project for generation config testing"""
    project = Project(
        id="test-project-gen-config-818",
        title="Test Project for Issue #818",
        description="Project for testing generation_config deep merge",
        created_by=test_user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        generation_config={},  # Start with empty config
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def create_prompt_structure(
    client: TestClient, project_id: str, structure_key: str, auth_headers: dict
):
    """Helper to create a prompt structure for testing"""
    response = client.put(
        f"/api/projects/{project_id}/generation-config/structures/{structure_key}",
        json={
            "name": f"Test Structure {structure_key}",
            "description": f"Test structure for {structure_key}",
            "system_prompt": "You are a test assistant",
            "instruction_prompt": "Test instruction",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, f"Failed to create structure: {response.text}"
    return response


@pytest.mark.integration
def test_model_selection_preserves_prompt_structures(
    client: TestClient, auth_headers, test_project
):
    """
    Test that selecting models after prompts preserves prompt selection.

    This is the main bug scenario from Issue #818:
    1. User selects prompt structures
    2. User selects models
    3. Prompt structures should still be present (not reset to 0)
    """
    project_id = test_project.id

    # Step 0: Create prompt structures first
    create_prompt_structure(client, project_id, "structure1", auth_headers)
    create_prompt_structure(client, project_id, "structure2", auth_headers)

    # Step 1: Set prompt structures as active
    response = client.put(
        f"/api/projects/{project_id}/generation-config/structures",
        json=["structure1", "structure2"],
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Step 2: Now set models (this was causing prompts to be reset)
    response = client.patch(
        f"/api/projects/{project_id}",
        json={
            "generation_config": {"selected_configuration": {"models": ["gpt-4", "claude-3-opus"]}}
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Step 3: Verify BOTH models AND active_structures are preserved
    response = client.get(f"/api/projects/{project_id}", headers=auth_headers)
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
def test_prompt_selection_preserves_models(client: TestClient, auth_headers, test_project):
    """
    Test the reverse order: selecting prompts after models preserves model selection.

    This ensures the fix works bidirectionally.
    """
    project_id = test_project.id

    # Step 0: Create prompt structures
    create_prompt_structure(client, project_id, "structure1", auth_headers)
    create_prompt_structure(client, project_id, "structure2", auth_headers)

    # Step 1: Set models first
    response = client.patch(
        f"/api/projects/{project_id}",
        json={"generation_config": {"selected_configuration": {"models": ["gpt-4"]}}},
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Step 2: Now set prompt structures as active
    response = client.put(
        f"/api/projects/{project_id}/generation-config/structures",
        json=["structure1", "structure2"],
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Step 3: Verify BOTH are preserved
    response = client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    project = response.json()

    config = project["generation_config"]["selected_configuration"]

    assert config["models"] == ["gpt-4"], "Models should not be reset when prompts are updated"
    assert config["active_structures"] == [
        "structure1",
        "structure2",
    ], "Prompt structures should be saved"


@pytest.mark.integration
def test_rapid_sequential_updates_preserve_all_fields(
    client: TestClient, auth_headers, test_project
):
    """
    Test rapid sequential updates to ensure all fields are preserved.

    This simulates the real-world scenario where a user quickly updates
    multiple parts of the generation config.
    """
    project_id = test_project.id

    # Step 0: Create prompt structures
    create_prompt_structure(client, project_id, "s1", auth_headers)
    create_prompt_structure(client, project_id, "s2", auth_headers)
    create_prompt_structure(client, project_id, "s3", auth_headers)

    # Update 1: Set models
    response = client.patch(
        f"/api/projects/{project_id}",
        json={"generation_config": {"selected_configuration": {"models": ["gpt-4"]}}},
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Update 2: Set prompts as active (immediately after)
    response = client.put(
        f"/api/projects/{project_id}/generation-config/structures",
        json=["s1", "s2"],
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Update 3: Modify models (immediately after)
    response = client.patch(
        f"/api/projects/{project_id}",
        json={"generation_config": {"selected_configuration": {"models": ["claude-3"]}}},
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Update 4: Add more prompt structures
    response = client.put(
        f"/api/projects/{project_id}/generation-config/structures",
        json=["s1", "s2", "s3"],
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Verify all updates were preserved
    response = client.get(f"/api/projects/{project_id}", headers=auth_headers)
    project = response.json()
    config = project["generation_config"]["selected_configuration"]

    assert config["models"] == ["claude-3"], "Latest model update should be present"
    assert config["active_structures"] == [
        "s1",
        "s2",
        "s3",
    ], "Latest prompt structures should be present"


@pytest.mark.integration
def test_partial_generation_config_update_preserves_other_fields(
    client: TestClient, auth_headers, test_project
):
    """
    Test that updating one part of generation_config preserves other unrelated fields.
    """
    project_id = test_project.id

    # Step 0: Create prompt structure
    create_prompt_structure(client, project_id, "s1", auth_headers)

    # Set up initial state with multiple fields
    response = client.patch(
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
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Now update only active_structures
    response = client.put(
        f"/api/projects/{project_id}/generation-config/structures",
        json=["s1"],
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Verify all other fields are preserved
    response = client.get(f"/api/projects/{project_id}", headers=auth_headers)
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
def test_updating_non_generation_config_fields_preserves_generation_config(
    client: TestClient, auth_headers, test_project
):
    """
    Test that updating other project fields doesn't affect generation_config.
    """
    project_id = test_project.id

    # Step 0: Create prompt structures
    create_prompt_structure(client, project_id, "s1", auth_headers)
    create_prompt_structure(client, project_id, "s2", auth_headers)

    # Set up generation_config with models
    response = client.patch(
        f"/api/projects/{project_id}",
        json={"generation_config": {"selected_configuration": {"models": ["gpt-4"]}}},
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Set active structures
    response = client.put(
        f"/api/projects/{project_id}/generation-config/structures",
        json=["s1", "s2"],
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Update title and description (non-generation_config fields)
    response = client.patch(
        f"/api/projects/{project_id}",
        json={"title": "Updated Title", "description": "Updated description"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Verify generation_config is untouched
    response = client.get(f"/api/projects/{project_id}", headers=auth_headers)
    project = response.json()

    assert project["title"] == "Updated Title"
    assert project["description"] == "Updated description"

    config = project["generation_config"]["selected_configuration"]
    assert config["models"] == ["gpt-4"], "Models should be unchanged"
    assert config["active_structures"] == ["s1", "s2"], "Prompt structures should be unchanged"
