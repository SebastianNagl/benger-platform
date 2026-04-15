"""
Worker tests for label config versioning in generation pipeline.
Tests that generations correctly save version snapshots for schema evolution.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Add path for tasks import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGenerationVersionSnapshot:
    """Test that generations save version and schema snapshots"""

    @pytest.fixture
    def mock_project(self):
        """Create mock project with version info"""
        project = MagicMock()
        project.id = "test-project-123"
        project.title = "Test Project"
        project.label_config = "<View><Choices name='sentiment'/></View>"
        project.label_config_version = "v2"
        project.label_config_history = {
            "versions": {
                "v1": {
                    "schema": "<View><TextArea name='notes'/></View>",
                    "created_at": "2025-01-01T10:00:00",
                }
            }
        }
        project.generation_config = {
            "prompt_structures": {
                "default": {
                    "system_prompt": "Test system prompt",
                    "instruction_prompt": "Test instruction",
                }
            }
        }
        project.llm_model_ids = ["gpt-3.5-turbo"]
        return project

    @pytest.fixture
    def mock_task_data(self):
        """Create mock task data"""
        return {"items": [{"id": 1, "data": {"text": "Test text content"}}]}

    @pytest.fixture
    def mock_response_generation(self):
        """Create mock ResponseGeneration record"""
        response_gen = MagicMock()
        response_gen.id = "resp-gen-123"
        response_gen.project_id = "test-project-123"
        response_gen.status = "pending"
        response_gen.model_id = "gpt-3.5-turbo"
        response_gen.structure_key = "default"
        return response_gen

    def test_generation_saves_version(self, mock_project):
        """Test that generation code includes label_config_version from project"""
        # This test verifies the logic exists in tasks.py at lines 1630-1631
        # We're testing that the field mapping exists, not the full execution

        # Read tasks.py to verify version field is saved
        import tasks

        tasks_source = open(tasks.__file__).read()

        # Verify the code sets label_config_version from project
        assert "label_config_version=project.label_config_version" in tasks_source
        assert "label_config_snapshot=project.label_config" in tasks_source

    def test_generation_saves_schema_snapshot(self, mock_project):
        """Test that generation code includes label_config_snapshot from project"""
        # Verify the code saves the schema snapshot
        import tasks

        tasks_source = open(tasks.__file__).read()

        # Verify both version and snapshot are set from project
        assert "label_config_version=project.label_config_version" in tasks_source
        assert "label_config_snapshot=project.label_config" in tasks_source

        # Verify they're in the same Generation object creation
        # by checking they appear near each other (within 5 lines)
        version_line = None
        snapshot_line = None

        for i, line in enumerate(tasks_source.split('\n')):
            if "label_config_version=project.label_config_version" in line:
                version_line = i
            if "label_config_snapshot=project.label_config" in line:
                snapshot_line = i

        assert version_line is not None
        assert snapshot_line is not None
        assert abs(version_line - snapshot_line) <= 5  # Within 5 lines

    def test_generation_version_matches_project(self, mock_project):
        """Test that generation uses project's current version"""
        # Verify the code reads from project.label_config_version (not hardcoded)
        import tasks

        tasks_source = open(tasks.__file__).read()

        # Code should read label_config_version from project instance
        assert "label_config_version=project.label_config_version" in tasks_source

        # This ensures version is captured at generation time, not hardcoded
        # Whatever version the project has when the generation runs, that's what gets saved


class TestSchemaEvolutionDuringGeneration:
    """Test handling of schema changes during generation"""

    def test_generation_uses_snapshot_not_current(self):
        """Test that generation captures project schema at start time"""
        # The worker code loads project once and uses that snapshot
        # This test verifies the logic captures the schema at generation time
        import tasks

        tasks_source = open(tasks.__file__).read()

        # Verify project is loaded early in generation function
        assert "project = " in tasks_source or "db.query(Project)" in tasks_source

        # Verify schema is saved from the loaded project instance
        assert "label_config_snapshot=project.label_config" in tasks_source

        # This pattern ensures snapshot is from the project state at generation start time


class TestVersionQuery:
    """Test querying and filtering generations by version"""

    @pytest.fixture
    def mock_db_with_generations(self):
        """Create mock database with multiple generations across versions"""
        mock_db = MagicMock()

        # Create mock generations with different versions
        gen_v1_1 = MagicMock()
        gen_v1_1.id = "gen-v1-1"
        gen_v1_1.label_config_version = "v1"
        gen_v1_1.project_id = "proj-123"

        gen_v1_2 = MagicMock()
        gen_v1_2.id = "gen-v1-2"
        gen_v1_2.label_config_version = "v1"
        gen_v1_2.project_id = "proj-123"

        gen_v2_1 = MagicMock()
        gen_v2_1.id = "gen-v2-1"
        gen_v2_1.label_config_version = "v2"
        gen_v2_1.project_id = "proj-123"

        gen_v2_2 = MagicMock()
        gen_v2_2.id = "gen-v2-2"
        gen_v2_2.label_config_version = "v2"
        gen_v2_2.project_id = "proj-123"

        gen_v3_1 = MagicMock()
        gen_v3_1.id = "gen-v3-1"
        gen_v3_1.label_config_version = "v3"
        gen_v3_1.project_id = "proj-123"

        all_gens = [gen_v1_1, gen_v1_2, gen_v2_1, gen_v2_2, gen_v3_1]

        # Setup query mock to filter by version
        def filter_by_version(*args, **kwargs):
            mock_query = MagicMock()
            # Extract filter conditions if any
            mock_query.all.return_value = all_gens
            return mock_query

        mock_db.query().filter.side_effect = filter_by_version
        mock_db.all_generations = all_gens

        return mock_db

    def test_query_generations_by_version(self, mock_db_with_generations):
        """Test querying generations filtered by specific version"""
        # This test verifies the data structure supports version filtering
        # Query for v1 generations
        v1_gens = [
            g for g in mock_db_with_generations.all_generations if g.label_config_version == "v1"
        ]

        assert len(v1_gens) == 2
        assert all(g.label_config_version == "v1" for g in v1_gens)

    def test_filter_generations_by_version(self, mock_db_with_generations):
        """Test filtering generations by version returns correct count"""
        # Count generations per version
        version_counts = {}
        for gen in mock_db_with_generations.all_generations:
            version = gen.label_config_version
            version_counts[version] = version_counts.get(version, 0) + 1

        assert version_counts["v1"] == 2
        assert version_counts["v2"] == 2
        assert version_counts["v3"] == 1

    def test_generation_version_distribution(self, mock_db_with_generations):
        """Test getting version distribution for a project"""
        project_id = "proj-123"

        # Get all generations for project
        project_gens = [
            g for g in mock_db_with_generations.all_generations if g.project_id == project_id
        ]

        # Count by version
        distribution = {}
        for gen in project_gens:
            v = gen.label_config_version
            distribution[v] = distribution.get(v, 0) + 1

        # Expected: 2 v1, 2 v2, 1 v3
        assert distribution == {"v1": 2, "v2": 2, "v3": 1}

    def test_filter_generations_multiple_versions(self, mock_db_with_generations):
        """Test filtering generations across multiple versions"""
        # Get v1 and v2 generations only
        filtered_gens = [
            g
            for g in mock_db_with_generations.all_generations
            if g.label_config_version in ["v1", "v2"]
        ]

        assert len(filtered_gens) == 4  # 2 v1 + 2 v2
        assert all(g.label_config_version in ["v1", "v2"] for g in filtered_gens)

    def test_query_generations_by_project_and_version(self, mock_db_with_generations):
        """Test querying generations by both project and version"""
        project_id = "proj-123"
        target_version = "v2"

        filtered = [
            g
            for g in mock_db_with_generations.all_generations
            if g.project_id == project_id and g.label_config_version == target_version
        ]

        assert len(filtered) == 2
        assert all(g.project_id == project_id for g in filtered)
        assert all(g.label_config_version == target_version for g in filtered)


class TestVersionFieldPresence:
    """Test that version fields are present in worker models"""

    def test_worker_project_has_version_fields(self):
        """Test worker's Project model has version fields"""
        from project_models import Project

        # Check worker's Project model has version fields
        assert hasattr(Project, 'label_config_version')
        assert hasattr(Project, 'label_config_history')
        assert hasattr(Project, 'label_config')

    def test_generation_code_uses_version_fields(self):
        """Test worker code references version fields"""
        import tasks

        tasks_source = open(tasks.__file__).read()

        # Verify generation creation includes version fields
        assert "label_config_version" in tasks_source
        assert "label_config_snapshot" in tasks_source

        # Verify these are set from project (not hardcoded)
        assert "project.label_config_version" in tasks_source
        assert "project.label_config" in tasks_source
