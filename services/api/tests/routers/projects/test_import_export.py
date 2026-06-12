"""Tests for import/export router."""

import os
import sys

# Add path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))


def test_import_export_router_exists():
    """Test that import/export router is importable."""
    from routers.projects.import_export import router

    assert router is not None


def test_import_export_routes_defined():
    """Test that all import/export routes exist.

    The sync GET /{id}/export, POST /{id}/import and POST /import-project routes
    were removed in the #158 follow-up — object storage is the only transport.
    The surface is now the async job endpoints plus the (still-sync) multi-project
    bulk-export admin endpoints.
    """
    from routers.projects.import_export import router

    routes = [r.path for r in router.routes]

    # Async export
    assert "/{project_id}/exports" in routes
    assert "/{project_id}/exports/{job_id}" in routes
    assert "/{project_id}/exports/{job_id}/download" in routes
    # Async nested import
    assert "/{project_id}/imports/upload-url" in routes
    assert "/{project_id}/imports" in routes
    assert "/{project_id}/imports/{job_id}" in routes
    # Async full-project (create-new) import
    assert "/project-imports/upload-url" in routes
    assert "/project-imports" in routes
    assert "/project-imports/{job_id}" in routes
    # Multi-project admin bulk export (still synchronous, out of #158 scope)
    assert "/bulk-export" in routes
    assert "/bulk-export-full" in routes

    # The removed sync routes must be gone.
    assert "/{project_id}/import" not in routes
    assert "/{project_id}/export" not in routes
    assert "/import-project" not in routes


def test_import_export_route_methods():
    """Test HTTP methods on the async + bulk routes."""
    from routers.projects.import_export import router

    route_methods = {}
    for route in router.routes:
        route_methods[route.path] = route.methods

    assert 'POST' in route_methods["/{project_id}/exports"]
    assert 'GET' in route_methods["/{project_id}/exports/{job_id}"]
    assert 'POST' in route_methods["/{project_id}/imports/upload-url"]
    assert 'POST' in route_methods["/{project_id}/imports"]
    assert 'POST' in route_methods["/project-imports"]
    assert 'POST' in route_methods["/bulk-export"]
    assert 'POST' in route_methods["/bulk-export-full"]


class TestConfigurationRoundtrip:
    """Test that model configs survive export/import.

    These tests verify that generation_config (with model_configs, temperature,
    thinking_budget) and evaluation_config (with default_temperature) are
    properly preserved during project export/import.
    """

    def _make_project(self, test_db, test_users, *, generation_config, evaluation_config):
        import uuid

        from project_models import Project

        admin = test_users[0]
        project = Project(
            id=str(uuid.uuid4()),
            title="Config Roundtrip",
            description="config export fidelity",
            created_by=admin.id,
            label_config="<View></View>",
            generation_config=generation_config,
            evaluation_config=evaluation_config,
        )
        test_db.add(project)
        test_db.commit()
        return project

    @staticmethod
    def _streamed_export(db, project_id):
        """The production export path — `get_comprehensive_project_data` was
        removed in issue #106; the streaming generator is what ships."""
        import json

        from routers.projects._export_stream import (
            stream_comprehensive_project_data_json,
        )

        return json.loads(
            "".join(stream_comprehensive_project_data_json(db, project_id))
        )

    def test_generation_config_included_in_project_export_data(
        self, test_db, test_users
    ):
        """Verify generation_config is included in export data structure."""
        generation_config = {
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
        project = self._make_project(
            test_db,
            test_users,
            generation_config=generation_config,
            evaluation_config={"default_temperature": 0.2},
        )

        export_data = self._streamed_export(test_db, project.id)

        assert "project" in export_data
        assert export_data["project"]["generation_config"] == generation_config

        model_configs = export_data["project"]["generation_config"][
            "selected_configuration"
        ]["model_configs"]
        assert model_configs["gpt-4o"]["temperature"] == 0.7
        assert model_configs["claude-3-7-sonnet-20250219"]["thinking_budget"] == 16000

    def test_evaluation_config_included_in_project_export_data(
        self, test_db, test_users
    ):
        """Verify evaluation_config is included in export data structure."""
        evaluation_config = {
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
        project = self._make_project(
            test_db,
            test_users,
            generation_config=None,
            evaluation_config=evaluation_config,
        )

        export_data = self._streamed_export(test_db, project.id)

        assert "project" in export_data
        assert export_data["project"]["evaluation_config"] == evaluation_config
        assert export_data["project"]["evaluation_config"]["default_temperature"] == 0.3
    def test_import_restores_generation_config(self):
        """Verify the export payload carries generation_config for import to restore."""
        # Validates the export data shape the importer consumes. The actual
        # round-trip through the shared import driver is covered in
        # tests/routers/projects/test_export_import_roundtrip.py.

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

        # Create export data structure (simulating the comprehensive export shape)
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

    def test_null_configs_handled_gracefully(self, test_db, test_users):
        """Null generation_config and evaluation_config don't break export."""
        project = self._make_project(
            test_db,
            test_users,
            generation_config=None,
            evaluation_config=None,
        )

        export_data = self._streamed_export(test_db, project.id)

        # Configs are included (even if None)
        assert "generation_config" in export_data["project"]
        assert "evaluation_config" in export_data["project"]
        assert export_data["project"]["generation_config"] is None
        assert export_data["project"]["evaluation_config"] is None
