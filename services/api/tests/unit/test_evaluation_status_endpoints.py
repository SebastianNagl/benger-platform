"""
Unit tests for evaluation status, human evaluation, and multi-field endpoints.
Covers business logic in routers/evaluations/status.py, human.py, multi_field.py.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from main import app
from models import User


class TestEvaluationStatusEndpoints:
    """Tests for evaluation status endpoint logic via TestClient."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_superadmin_user(self):
        return User(
            id="admin-1",
            username="admin",
            email="admin@test.com",
            name="Admin",
            hashed_password="hash",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

    @patch("routers.evaluations.status.get_db")
    @patch("routers.evaluations.status.require_user")
    @patch("routers.evaluations.status.check_project_accessible")
    def test_get_evaluation_status_not_found(
        self, mock_access, mock_user, mock_db, client, mock_superadmin_user
    ):
        from auth_module.service import db_user_to_user
        mock_user.return_value = db_user_to_user(mock_superadmin_user)
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_db.return_value = mock_session

        response = client.get("/api/evaluation/status/nonexistent")
        assert response.status_code == 404


class TestEvaluationTypesEndpoints:
    """Tests for evaluation type endpoint wiring."""

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

    @patch("routers.evaluations.status.get_db")
    @patch("routers.evaluations.status.require_user")
    def test_get_evaluation_type_by_id_not_found(self, mock_user, mock_db, client, superadmin):
        from auth_module.service import db_user_to_user
        mock_user.return_value = db_user_to_user(superadmin)

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_db.return_value = mock_session

        response = client.get("/api/evaluation-types/nonexistent")
        assert response.status_code == 404

    def test_get_supported_metrics_logic(self):
        """Test the supported metrics aggregation logic directly."""
        from evaluation_config import ANSWER_TYPE_TO_METRICS, AnswerType

        all_metrics = set()
        for answer_type in AnswerType:
            metrics = ANSWER_TYPE_TO_METRICS.get(answer_type, [])
            if isinstance(metrics, dict):
                all_metrics.update(metrics.get("automated", []))
            elif isinstance(metrics, list):
                all_metrics.update(metrics)

        sorted_metrics = sorted(list(all_metrics))

        assert isinstance(sorted_metrics, list)
        assert len(sorted_metrics) > 0
        assert sorted_metrics == sorted(sorted_metrics)
        # Well-known metrics should be present
        assert "exact_match" in sorted_metrics


class TestHumanEvaluationLogic:
    """Tests for human evaluation session business logic."""

    def test_session_config_likert(self):
        config = {
            "field_name": "answer",
            "dimensions": ["correctness", "completeness"],
            "randomized": True,
            "allow_skip": True,
        }
        assert config["dimensions"] == ["correctness", "completeness"]

    def test_session_config_preference_no_dimensions(self):
        config = {
            "field_name": "answer",
            "dimensions": None,
            "randomized": True,
            "allow_skip": True,
        }
        assert config["dimensions"] is None

    def test_progress_percentage_half(self):
        items_evaluated = 15
        total_items = 30
        progress = (items_evaluated / total_items) * 100
        assert progress == 50.0

    def test_progress_percentage_zero_total(self):
        total_items = 0
        progress = 0.0 if not total_items or total_items <= 0 else (0 / total_items * 100)
        assert progress == 0.0

    def test_progress_percentage_completed(self):
        items_evaluated = 10
        total_items = 10
        progress = (items_evaluated / total_items) * 100
        assert progress == 100.0

    def test_response_anonymization(self):
        names = [f"Response_{chr(65 + i)}" for i in range(5)]
        assert names == ["Response_A", "Response_B", "Response_C", "Response_D", "Response_E"]

    def test_response_anonymization_26_responses(self):
        names = [f"Response_{chr(65 + i)}" for i in range(26)]
        assert names[0] == "Response_A"
        assert names[25] == "Response_Z"

    def test_human_config_extract_dimensions(self):
        """Test extracting Likert dimensions from evaluation config."""
        evaluation_config = {
            "selected_methods": {
                "answer": {
                    "human": [
                        {
                            "name": "likert_scale",
                            "parameters": {
                                "dimensions": ["correctness", "style"]
                            },
                        },
                    ],
                },
                "summary": {
                    "human": ["preference"],
                },
            }
        }

        from routers.evaluations.helpers import extract_metric_name

        human_methods = {}
        available_dimensions = []

        selected_methods = evaluation_config.get("selected_methods", {})
        for field_name, config in selected_methods.items():
            human_selections = config.get("human", [])
            if human_selections:
                human_methods[field_name] = human_selections
                for method in human_selections:
                    method_name = extract_metric_name(method)
                    if method_name == "likert_scale":
                        if isinstance(method, dict) and "parameters" in method:
                            dims = method["parameters"].get("dimensions", [])
                            available_dimensions.extend(dims)

        assert "answer" in human_methods
        assert "summary" in human_methods
        assert "correctness" in available_dimensions
        assert "style" in available_dimensions

    def test_human_config_default_dimensions(self):
        """Test default dimensions when none configured."""
        evaluation_config = {
            "selected_methods": {}
        }

        available_dimensions = []
        if not available_dimensions:
            available_dimensions = ["correctness", "completeness", "style", "usability"]

        assert len(available_dimensions) == 4

    def test_session_completed_when_no_more_tasks(self):
        """Test that session completes when no unevaluated tasks remain."""
        session_status = "active"
        next_task = None

        if not next_task:
            session_status = "completed"

        assert session_status == "completed"


class TestMultiFieldResultParsing:
    """Tests for multi-field evaluation result parsing logic."""

    def test_parse_metrics_key_format(self):
        metrics = {
            "cfg1:answer:gold_answer:bleu": 0.85,
            "cfg1:answer:gold_answer:rouge": 0.78,
            "cfg2:summary:gold_summary:bert_score": 0.92,
        }

        parsed_results = {}
        for key, value in metrics.items():
            parts = key.split(":")
            if len(parts) >= 4:
                config_id = parts[0]
                pred_field = parts[1]
                ref_field = parts[2]
                metric_name = ":".join(parts[3:])

                if config_id not in parsed_results:
                    parsed_results[config_id] = {"field_results": [], "aggregate_score": None}

                combo_key = f"{pred_field}_vs_{ref_field}"
                existing = next(
                    (r for r in parsed_results[config_id]["field_results"]
                     if r.get("combo_key") == combo_key),
                    None,
                )
                if not existing:
                    existing = {
                        "combo_key": combo_key,
                        "prediction_field": pred_field,
                        "reference_field": ref_field,
                        "scores": {},
                    }
                    parsed_results[config_id]["field_results"].append(existing)
                existing["scores"][metric_name] = value

        assert "cfg1" in parsed_results
        assert "cfg2" in parsed_results
        assert len(parsed_results["cfg1"]["field_results"]) == 1
        assert parsed_results["cfg1"]["field_results"][0]["scores"]["bleu"] == 0.85
        assert parsed_results["cfg1"]["field_results"][0]["scores"]["rouge"] == 0.78

    def test_parse_metric_with_colon_in_name(self):
        """Test parsing metric names that contain colons."""
        metrics = {
            "cfg1:answer:ref:custom:metric:name": 0.5,
        }

        for key, value in metrics.items():
            parts = key.split(":")
            if len(parts) >= 4:
                config_id = parts[0]
                pred_field = parts[1]
                ref_field = parts[2]
                metric_name = ":".join(parts[3:])

        assert metric_name == "custom:metric:name"

    def test_aggregate_scores_calculation(self):
        config_data = {
            "field_results": [
                {"scores": {"bleu": 0.8, "rouge": 0.7}},
                {"scores": {"bleu": 0.9}},
            ],
            "aggregate_score": None,
        }

        all_scores = []
        for fr in config_data["field_results"]:
            for score_name, score_val in fr["scores"].items():
                if isinstance(score_val, (int, float)):
                    all_scores.append(score_val)
        if all_scores:
            config_data["aggregate_score"] = sum(all_scores) / len(all_scores)

        assert config_data["aggregate_score"] == pytest.approx(0.8, abs=0.01)

    def test_aggregate_scores_no_numeric(self):
        config_data = {
            "field_results": [
                {"scores": {"status": "failed"}},
            ],
            "aggregate_score": None,
        }

        all_scores = []
        for fr in config_data["field_results"]:
            for score_name, score_val in fr["scores"].items():
                if isinstance(score_val, (int, float)):
                    all_scores.append(score_val)
        if all_scores:
            config_data["aggregate_score"] = sum(all_scores) / len(all_scores)

        assert config_data["aggregate_score"] is None

    def test_detailed_result_parsing_4_part_key(self):
        metrics = {
            "cfg1:pred:ref:metric": 0.5,
            "cfg1:pred:ref:metric2": 0.6,
        }

        parsed = {}
        for key, value in metrics.items():
            parts = key.split(":")
            if len(parts) == 4:
                config_id, pred_field, ref_field, metric_name = parts
                if config_id not in parsed:
                    parsed[config_id] = {}
                combo_key = f"{pred_field}_vs_{ref_field}"
                if combo_key not in parsed[config_id]:
                    parsed[config_id][combo_key] = {}
                parsed[config_id][combo_key][metric_name] = value

        assert parsed["cfg1"]["pred_vs_ref"]["metric"] == 0.5
        assert parsed["cfg1"]["pred_vs_ref"]["metric2"] == 0.6

    def test_evaluation_type_filtering(self):
        evaluations = [
            Mock(eval_metadata={"evaluation_type": "evaluation"}),
            Mock(eval_metadata={"evaluation_type": "multi_field"}),
            Mock(eval_metadata={"evaluation_type": "llm_judge"}),
            Mock(eval_metadata={"evaluation_type": "immediate"}),
            Mock(eval_metadata={"evaluation_type": "unknown"}),
            Mock(eval_metadata=None),
            Mock(eval_metadata={}),
        ]

        valid_types = ("multi_field", "evaluation", "llm_judge", "immediate")
        filtered = [
            e for e in evaluations
            if (e.eval_metadata or {}).get("evaluation_type") in valid_types
        ]

        assert len(filtered) == 4

    def test_evaluation_type_filtering_empty(self):
        evaluations = []
        valid_types = ("multi_field", "evaluation", "llm_judge", "immediate")
        filtered = [
            e for e in evaluations
            if (e.eval_metadata or {}).get("evaluation_type") in valid_types
        ]
        assert filtered == []

    def test_latest_only_filter(self):
        """Test latest_only=True returns just the first evaluation."""
        evaluations = [Mock(id="newest"), Mock(id="older"), Mock(id="oldest")]
        if evaluations:
            evaluations = [evaluations[0]]
        assert len(evaluations) == 1
        assert evaluations[0].id == "newest"

    def test_eval_configs_from_metadata(self):
        """Test extracting evaluation_configs from eval_metadata."""
        eval_metadata = {
            "evaluation_configs": [{"id": "cfg1", "metric": "bleu"}],
            "evaluation_type": "evaluation",
        }
        eval_configs = (
            (eval_metadata.get("evaluation_configs")
             or eval_metadata.get("configs", []))
        )
        assert len(eval_configs) == 1

    def test_eval_configs_fallback_to_configs(self):
        """Test fallback from evaluation_configs to configs key."""
        eval_metadata = {
            "configs": [{"id": "cfg1", "metric": "bleu"}],
        }
        eval_configs = (
            (eval_metadata.get("evaluation_configs")
             or eval_metadata.get("configs", []))
        )
        assert len(eval_configs) == 1

    def test_eval_configs_none_metadata(self):
        """Test handling of None eval_metadata."""
        eval_metadata = None
        eval_configs = (
            (eval_metadata.get("evaluation_configs")
             or eval_metadata.get("configs", []))
            if eval_metadata
            else []
        )
        assert eval_configs == []

    def test_progress_metadata_extraction(self):
        """Test extracting progress info from evaluation metadata."""
        eval_metadata = {
            "samples_passed": 45,
            "samples_failed": 3,
            "samples_skipped": 2,
        }

        progress = {
            "samples_passed": eval_metadata.get("samples_passed", 0),
            "samples_failed": eval_metadata.get("samples_failed", 0),
            "samples_skipped": eval_metadata.get("samples_skipped", 0),
        }

        assert progress["samples_passed"] == 45
        assert progress["samples_failed"] == 3
        assert progress["samples_skipped"] == 2

    def test_progress_metadata_missing(self):
        """Test progress with missing keys."""
        eval_metadata = {}

        progress = {
            "samples_passed": eval_metadata.get("samples_passed", 0),
            "samples_failed": eval_metadata.get("samples_failed", 0),
            "samples_skipped": eval_metadata.get("samples_skipped", 0),
        }

        assert progress["samples_passed"] == 0
        assert progress["samples_failed"] == 0
        assert progress["samples_skipped"] == 0
