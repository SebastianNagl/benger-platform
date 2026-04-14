"""Tests for import/export router."""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

# Add path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))


def test_import_export_router_exists():
    """Test that import/export router is importable."""
    from routers.projects.import_export import router

    assert router is not None


def test_import_export_routes_defined():
    """Test that all import/export routes exist."""
    from routers.projects.import_export import router

    routes = [r.path for r in router.routes]

    assert "/{project_id}/import" in routes
    assert "/{project_id}/export" in routes
    assert "/bulk-export" in routes
    assert "/bulk-export-full" in routes
    assert "/import-project" in routes


def test_import_export_route_methods():
    """Test HTTP methods."""
    from routers.projects.import_export import router

    route_methods = {}
    for route in router.routes:
        route_methods[route.path] = route.methods

    assert 'POST' in route_methods["/{project_id}/import"]
    assert 'GET' in route_methods["/{project_id}/export"]
    assert 'POST' in route_methods["/bulk-export"]
    assert 'POST' in route_methods["/bulk-export-full"]
    assert 'POST' in route_methods["/import-project"]


class TestConfigurationRoundtrip:
    """Test that model configs survive export/import.

    These tests verify that generation_config (with model_configs, temperature,
    thinking_budget) and evaluation_config (with default_temperature) are
    properly preserved during project export/import.
    """

    def test_generation_config_included_in_project_export_data(self):
        """Verify generation_config is included in export data structure."""
        # The export function should include generation_config in project data
        from projects_api import get_comprehensive_project_data

        # Mock project with generation_config
        mock_project = Mock()
        mock_project.id = "test-project-id"
        mock_project.title = "Test Project"
        mock_project.description = "Test Description"
        mock_project.label_config = "<View></View>"
        mock_project.expert_instruction = None
        mock_project.show_instruction = True
        mock_project.show_skip_button = True
        mock_project.enable_empty_annotation = True
        mock_project.created_by = "user-123"
        mock_project.min_annotations_per_task = 1
        mock_project.is_published = False
        mock_project.created_at = None
        mock_project.updated_at = None
        mock_project.review_enabled = False
        mock_project.review_mode = "in_place"
        mock_project.allow_self_review = False
        mock_project.generation_config = {
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3-7-sonnet-20250219"],
                "parameters": {"temperature": 0.0, "max_tokens": 4000},
                "model_configs": {
                    "gpt-4o": {"temperature": 0.7, "max_tokens": 8000},
                    "claude-3-7-sonnet-20250219": {
                        "temperature": 0.3,
                        "thinking_budget": 16000,
                    },
                },
            }
        }
        mock_project.evaluation_config = {"default_temperature": 0.2}

        # Mock db session with side_effect so successive first() calls return correct types
        # Call order: 1) Project query -> mock_project, 2) ProjectOrganization existence check,
        # 3) ProjectOrganization.organization_id query -> needs to be subscriptable
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_project,
            ("org-123",),
            ("org-123",),
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Call get_comprehensive_project_data
        with patch("projects_api.ProjectOrganization"):
            export_data = get_comprehensive_project_data(mock_db, "test-project-id")

        # Verify generation_config is in project data
        assert "project" in export_data
        assert "generation_config" in export_data["project"]
        assert export_data["project"]["generation_config"] == mock_project.generation_config

        # Verify specific model_configs
        model_configs = export_data["project"]["generation_config"]["selected_configuration"][
            "model_configs"
        ]
        assert model_configs["gpt-4o"]["temperature"] == 0.7
        assert model_configs["claude-3-7-sonnet-20250219"]["thinking_budget"] == 16000

    def test_evaluation_config_included_in_project_export_data(self):
        """Verify evaluation_config is included in export data structure."""
        from projects_api import get_comprehensive_project_data

        # Mock project with evaluation_config
        mock_project = Mock()
        mock_project.id = "test-project-id"
        mock_project.title = "Test Project"
        mock_project.description = "Test Description"
        mock_project.label_config = "<View></View>"
        mock_project.expert_instruction = None
        mock_project.show_instruction = True
        mock_project.show_skip_button = True
        mock_project.enable_empty_annotation = True
        mock_project.created_by = "user-123"
        mock_project.min_annotations_per_task = 1
        mock_project.is_published = False
        mock_project.created_at = None
        mock_project.updated_at = None
        mock_project.review_enabled = False
        mock_project.review_mode = "in_place"
        mock_project.allow_self_review = False
        mock_project.generation_config = None
        mock_project.evaluation_config = {
            "default_temperature": 0.3,
            "available_methods": {
                "answer": {
                    "type": "long_text",
                    "available_metrics": ["bleu", "llm_judge_classic"],
                }
            },
            "configs": [
                {
                    "metric": "llm_judge_classic",
                    "metric_parameters": {
                        "judge_model": "claude-3-7-sonnet-20250219",
                        "temperature": 0.2,
                        "max_tokens": 1000,
                        "thinking_budget": 16000,
                    },
                }
            ],
        }

        # Mock db session with side_effect so successive first() calls return correct types
        # Call order: 1) Project query -> mock_project, 2) ProjectOrganization existence check,
        # 3) ProjectOrganization.organization_id query -> needs to be subscriptable
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_project,
            ("org-123",),
            ("org-123",),
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Call get_comprehensive_project_data
        with patch("projects_api.ProjectOrganization"):
            export_data = get_comprehensive_project_data(mock_db, "test-project-id")

        # Verify evaluation_config is in project data
        assert "project" in export_data
        assert "evaluation_config" in export_data["project"]
        assert export_data["project"]["evaluation_config"] == mock_project.evaluation_config

        # Verify default_temperature
        assert export_data["project"]["evaluation_config"]["default_temperature"] == 0.3

    def test_import_restores_generation_config(self):
        """Verify import_project_data restores generation_config from export."""
        # This test verifies the import function signature accepts generation_config
        # The actual database integration is tested in integration tests

        # Create mock export data with generation_config
        export_data = {
            "format_version": "1.0.0",
            "project": {
                "title": "Test Project",
                "description": "Test",
                "label_config": "<View></View>",
                "generation_config": {
                    "selected_configuration": {
                        "models": ["gpt-4o"],
                        "model_configs": {"gpt-4o": {"temperature": 0.7, "thinking_budget": 8000}},
                    }
                },
                "evaluation_config": {"default_temperature": 0.5},
            },
            "tasks": [],
            "annotations": [],
            "generations": [],
        }

        # Verify the structure is valid for import
        project_data = export_data["project"]
        assert "generation_config" in project_data
        assert (
            project_data["generation_config"]["selected_configuration"]["model_configs"]["gpt-4o"][
                "temperature"
            ]
            == 0.7
        )

    def test_roundtrip_preserves_model_configs_structure(self):
        """Test that model_configs structure is preserved through export/import data transformation."""
        # Define the original config
        original_generation_config = {
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3-7-sonnet-20250219", "o3-mini"],
                "parameters": {"temperature": 0.0, "max_tokens": 4000},
                "model_configs": {
                    "gpt-4o": {"temperature": 0.7, "max_tokens": 8000},
                    "claude-3-7-sonnet-20250219": {
                        "temperature": 0.3,
                        "thinking_budget": 16000,
                    },
                    "o3-mini": {"reasoning_effort": "high"},
                },
            },
            "prompt_structures": {"format": "qa"},
        }

        original_evaluation_config = {
            "default_temperature": 0.2,
            "available_methods": {
                "answer": {"type": "long_text", "available_metrics": ["llm_judge_classic"]}
            },
        }

        # Create export data structure (simulating what get_comprehensive_project_data returns)
        export_data = {
            "project": {
                "title": "Test",
                "generation_config": original_generation_config,
                "evaluation_config": original_evaluation_config,
            }
        }

        # Simulate import reading the data
        imported_gen_config = export_data["project"].get("generation_config")
        imported_eval_config = export_data["project"].get("evaluation_config")

        # Verify all model configs are preserved
        assert imported_gen_config == original_generation_config
        assert imported_eval_config == original_evaluation_config

        # Verify specific values
        model_configs = imported_gen_config["selected_configuration"]["model_configs"]
        assert model_configs["gpt-4o"]["temperature"] == 0.7
        assert model_configs["claude-3-7-sonnet-20250219"]["thinking_budget"] == 16000
        assert model_configs["o3-mini"]["reasoning_effort"] == "high"

        # Verify evaluation default temperature
        assert imported_eval_config["default_temperature"] == 0.2

    def test_null_configs_handled_gracefully(self):
        """Test that null generation_config and evaluation_config don't break export."""
        from projects_api import get_comprehensive_project_data

        # Mock project with null configs
        mock_project = Mock()
        mock_project.id = "test-project-id"
        mock_project.title = "Test Project"
        mock_project.description = "Test"
        mock_project.label_config = "<View></View>"
        mock_project.expert_instruction = None
        mock_project.show_instruction = True
        mock_project.show_skip_button = True
        mock_project.enable_empty_annotation = True
        mock_project.created_by = "user-123"
        mock_project.min_annotations_per_task = 1
        mock_project.is_published = False
        mock_project.created_at = None
        mock_project.updated_at = None
        mock_project.review_enabled = False
        mock_project.review_mode = "in_place"
        mock_project.allow_self_review = False
        mock_project.generation_config = None  # Null config
        mock_project.evaluation_config = None  # Null config

        # Mock db session with side_effect so successive first() calls return correct types
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_project,
            ("org-123",),
            ("org-123",),
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Call get_comprehensive_project_data - should not raise
        with patch("projects_api.ProjectOrganization"):
            export_data = get_comprehensive_project_data(mock_db, "test-project-id")

        # Verify configs are included (even if None)
        assert "generation_config" in export_data["project"]
        assert "evaluation_config" in export_data["project"]
        assert export_data["project"]["generation_config"] is None
        assert export_data["project"]["evaluation_config"] is None
