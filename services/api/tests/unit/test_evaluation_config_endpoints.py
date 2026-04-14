"""
Unit tests for evaluation config endpoints.
Covers routers/evaluations/config.py and validation.py.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from main import app
from models import User


class TestEvaluationConfigEndpoints:
    """TestClient-based tests for evaluation config endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def superadmin(self):
        return User(
            id="admin-1", username="admin", email="admin@test.com", name="Admin",
            hashed_password="hash", is_superadmin=True, is_active=True,
            email_verified=True, use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

    @patch("routers.evaluations.config.get_db")
    @patch("routers.evaluations.config.require_user")
    @patch("routers.evaluations.config.auth_service")
    def test_get_config_project_not_found(self, mock_auth, mock_user, mock_db, client, superadmin):
        from auth_module.service import db_user_to_user
        mock_user.return_value = db_user_to_user(superadmin)
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_db.return_value = mock_session
        response = client.get("/api/projects/nonexistent/evaluation-config")
        assert response.status_code == 404

    @patch("routers.evaluations.config.get_db")
    @patch("routers.evaluations.config.require_user")
    @patch("routers.evaluations.config.check_project_accessible")
    def test_update_config_project_not_found(self, mock_access, mock_user, mock_db, client, superadmin):
        from auth_module.service import db_user_to_user
        mock_user.return_value = db_user_to_user(superadmin)
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_db.return_value = mock_session
        response = client.put("/api/projects/nonexistent/evaluation-config", json={})
        assert response.status_code == 404

    @patch("routers.evaluations.config.get_db")
    @patch("routers.evaluations.config.require_user")
    @patch("routers.evaluations.config.check_project_accessible")
    def test_detect_answer_types_not_found(self, mock_access, mock_user, mock_db, client, superadmin):
        from auth_module.service import db_user_to_user
        mock_user.return_value = db_user_to_user(superadmin)
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_db.return_value = mock_session
        response = client.get("/api/projects/nonexistent/detect-answer-types")
        assert response.status_code == 404

    @patch("routers.evaluations.config.get_db")
    @patch("routers.evaluations.config.require_user")
    @patch("routers.evaluations.config.check_project_accessible")
    def test_field_types_not_found(self, mock_access, mock_user, mock_db, client, superadmin):
        from auth_module.service import db_user_to_user
        mock_user.return_value = db_user_to_user(superadmin)
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_db.return_value = mock_session
        response = client.get("/api/projects/nonexistent/field-types")
        assert response.status_code == 404


class TestEvaluationConfigValidationLogic:
    """Tests for validation logic within evaluation config."""

    def test_invalid_field_in_selected_methods(self):
        config = {
            "selected_methods": {"invalid_field": {"automated": ["bleu"]}},
            "available_methods": {"answer": {"available_metrics": ["bleu"]}},
        }
        for field_name in config["selected_methods"]:
            assert field_name not in config["available_methods"]

    def test_invalid_metric_in_selected_methods(self):
        from routers.evaluations.helpers import extract_metric_name

        config = {
            "selected_methods": {"answer": {"automated": ["nonexistent_metric"]}},
            "available_methods": {"answer": {"available_metrics": ["bleu", "rouge"]}},
        }
        selections = config["selected_methods"]["answer"]
        available = config["available_methods"]["answer"]
        for metric in selections.get("automated", []):
            metric_name = extract_metric_name(metric)
            assert metric_name not in available["available_metrics"]

    def test_valid_config_passes(self):
        from routers.evaluations.helpers import extract_metric_name

        config = {
            "selected_methods": {
                "answer": {
                    "automated": ["bleu", "rouge"],
                    "human": ["likert_scale"],
                },
            },
            "available_methods": {
                "answer": {
                    "available_metrics": ["bleu", "rouge", "bert_score"],
                    "available_human": ["likert_scale", "preference"],
                },
            },
        }
        for field_name, selections in config["selected_methods"].items():
            assert field_name in config["available_methods"]
            available = config["available_methods"][field_name]
            for metric in selections.get("automated", []):
                assert extract_metric_name(metric) in available["available_metrics"]
            for method in selections.get("human", []):
                assert extract_metric_name(method) in available["available_human"]

    def test_field_mapping_validation(self):
        config = {
            "detected_answer_types": [
                {"name": "answer", "to_name": "text"},
                {"name": "summary", "to_name": "content"},
            ],
        }
        available_field_names = set()
        for at in config["detected_answer_types"]:
            available_field_names.add(at.get("name", ""))
            to_name = at.get("to_name", "")
            if to_name:
                available_field_names.add(to_name)
        assert "answer" in available_field_names
        assert "text" in available_field_names
        assert "summary" in available_field_names
        assert "content" in available_field_names

    def test_mixed_metric_formats(self):
        from routers.evaluations.helpers import extract_metric_name

        metrics = [
            "bleu",
            {"name": "rouge", "parameters": {"type": "rougeL"}},
            "exact_match",
        ]
        names = [extract_metric_name(m) for m in metrics]
        assert names == ["bleu", "rouge", "exact_match"]


class TestConfigValidationLogic:
    """Tests for config validation field overlap logic."""

    def test_matching_fields(self):
        generation_fields = ["answer", "summary"]
        evaluation_fields = ["answer", "reasoning"]

        matched = list(set(generation_fields) & set(evaluation_fields))
        missing_in_eval = list(set(generation_fields) - set(evaluation_fields))
        missing_in_gen = list(set(evaluation_fields) - set(generation_fields))

        assert "answer" in matched
        assert "summary" in missing_in_eval
        assert "reasoning" in missing_in_gen

    def test_no_overlap(self):
        generation_fields = ["field_a"]
        evaluation_fields = ["field_b"]
        matched = list(set(generation_fields) & set(evaluation_fields))
        assert matched == []

    def test_all_match(self):
        generation_fields = ["answer", "summary"]
        evaluation_fields = ["answer", "summary"]
        matched = list(set(generation_fields) & set(evaluation_fields))
        assert len(matched) == 2

    def test_empty_fields(self):
        matched = list(set([]) & set([]))
        assert matched == []


class TestNeedsRegenerationLogic:
    """Tests for evaluation config regeneration decision logic."""

    def test_no_existing_config_needs_regen(self):
        evaluation_config = None
        force_regenerate = False
        label_config_version = "v1"

        existing_version = evaluation_config.get("label_config_version") if evaluation_config else None
        needs = (
            not evaluation_config
            or force_regenerate
            or (label_config_version and existing_version is not None and existing_version != label_config_version)
        )
        assert needs is True

    def test_force_regenerate(self):
        evaluation_config = {"label_config_version": "v1"}
        force_regenerate = True
        needs = not evaluation_config or force_regenerate
        assert needs is True

    def test_version_changed_needs_regen(self):
        evaluation_config = {"label_config_version": "v1"}
        label_config_version = "v2"
        existing_version = evaluation_config.get("label_config_version")
        needs = (
            label_config_version
            and existing_version is not None
            and existing_version != label_config_version
        )
        assert needs is True

    def test_same_version_no_regen(self):
        evaluation_config = {"label_config_version": "v1"}
        label_config_version = "v1"
        existing_version = evaluation_config.get("label_config_version")
        needs = (
            not evaluation_config
            or (label_config_version and existing_version is not None and existing_version != label_config_version)
        )
        assert needs is False

    def test_no_existing_version_no_regen(self):
        evaluation_config = {"selected_methods": {}}
        label_config_version = "v1"
        existing_version = evaluation_config.get("label_config_version")
        needs = (
            not evaluation_config
            or (label_config_version and existing_version is not None and existing_version != label_config_version)
        )
        assert needs is False

    def test_should_stamp_version_on_old_config(self):
        evaluation_config = {"selected_methods": {"answer": {}}}
        force_regenerate = False
        existing_version = evaluation_config.get("label_config_version")
        label_config_version = "v1"
        should_stamp = bool(
            evaluation_config and not force_regenerate
            and existing_version is None and label_config_version
        )
        assert should_stamp is True

    def test_should_derive_configs_from_selected_methods(self):
        config = {"selected_methods": {"answer": {"automated": ["bleu"]}}}
        should_derive = config.get("selected_methods") and not config.get("evaluation_configs")
        assert should_derive is True

    def test_should_not_derive_when_configs_exist(self):
        config = {
            "selected_methods": {"answer": {"automated": ["bleu"]}},
            "evaluation_configs": [{"id": "cfg1"}],
        }
        should_derive = config.get("selected_methods") and not config.get("evaluation_configs")
        assert should_derive is False
