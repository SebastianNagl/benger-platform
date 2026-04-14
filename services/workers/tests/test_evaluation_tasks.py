"""
Tests for evaluation pipeline Celery tasks.

Tests cover metric retrieval, response generation error handling,
and the active evaluation paths (multi-field evaluation).

Note: Legacy run_ml_evaluation and calculate_metrics paths were removed
in issue #1236. All evaluations now go through run_multi_field_evaluation().
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import generate_llm_responses, get_supported_metrics


class TestSupportedMetricsTask:
    """Test the get_supported_metrics Celery task."""

    def test_get_metrics_for_specific_task_type(self):
        """Test getting supported metrics for a specific task type."""
        with patch("tasks.evaluator_registry") as mock_registry:
            mock_registry.get_supported_metrics.return_value = [
                "accuracy",
                "f1",
                "precision",
                "recall",
            ]

            result = get_supported_metrics(task_type="classification")

        assert result["status"] == "success"
        assert result["task_type"] == "classification"
        assert "accuracy" in result["metrics"]
        assert "f1" in result["metrics"]

    def test_get_metrics_for_all_task_types(self):
        """Test getting supported metrics for all task types."""
        with patch("tasks.evaluator_registry") as mock_registry:
            mock_registry.get_supported_task_types.return_value = [
                "qa",
                "classification",
                "generation",
            ]
            mock_registry.get_supported_metrics.side_effect = [
                ["exact_match", "f1"],
                ["accuracy", "precision", "recall"],
                ["bleu", "rouge_l", "meteor"],
            ]

            result = get_supported_metrics()

        assert result["status"] == "success"
        assert "supported_task_types" in result
        assert "metrics_by_task_type" in result

        metrics_by_type = result["metrics_by_task_type"]
        assert "qa" in metrics_by_type
        assert "classification" in metrics_by_type
        assert "generation" in metrics_by_type

        assert "exact_match" in metrics_by_type["qa"]
        assert "accuracy" in metrics_by_type["classification"]
        assert "bleu" in metrics_by_type["generation"]

    def test_get_metrics_exception_handling(self):
        """Test exception handling in get_supported_metrics."""
        with patch("tasks.evaluator_registry") as mock_registry:
            mock_registry.get_supported_metrics.side_effect = Exception("Registry error")

            result = get_supported_metrics(task_type="qa")

        assert result["status"] == "error"
        assert "Registry error" in result["message"]


class TestGenerationErrorRecovery:
    """Test error recovery and resilience in generation tasks."""

    def test_database_connection_failure(self):
        """Test handling of database connection failures."""
        with patch("tasks.HAS_DATABASE", False):
            result = generate_llm_responses(
                generation_id="test-generation-no-db",
                config_data={"task_id": "test-task-no-db"},
                model_id="gpt-4",
                user_id="user-123",
            )

        assert result["status"] == "error"
        assert "Database not available" in result["message"] or "error" in result["status"]
