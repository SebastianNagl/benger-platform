"""
Tests for Base Evaluator functionality.

Tests cover the base evaluator interface, evaluation configuration,
and common evaluation utilities.
"""

from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from ml_evaluation.base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult


class TestEvaluationConfig:
    """Test the EvaluationConfig class."""

    def test_evaluation_config_creation(self):
        """Test creating evaluation configuration."""
        config = EvaluationConfig(
            metrics=["accuracy", "f1"],
            model_config={"type": "test"},
            evaluation_params={"param": "value"},
        )

        assert config.metrics == ["accuracy", "f1"]
        assert config.model_config == {"type": "test"}
        assert config.evaluation_params == {"param": "value"}

    def test_evaluation_config_defaults(self):
        """Test evaluation configuration with default values."""
        config = EvaluationConfig(metrics=["accuracy"], model_config={})

        assert config.metrics == ["accuracy"]
        assert config.model_config == {}
        assert config.evaluation_params == {}


class TestEvaluationResult:
    """Test the EvaluationResult class."""

    def test_evaluation_result_success(self):
        """Test successful evaluation result."""
        result = EvaluationResult(
            metrics={"accuracy": 0.85, "f1": 0.82},
            metadata={"samples": 100},
            samples_evaluated=100,
        )

        assert result.success is True
        assert result.error is None
        assert result.metrics == {"accuracy": 0.85, "f1": 0.82}
        assert result.metadata == {"samples": 100}
        assert result.samples_evaluated == 100

    def test_evaluation_result_with_error(self):
        """Test evaluation result with error."""
        result = EvaluationResult(
            metrics={}, metadata={}, error="Evaluation failed", samples_evaluated=0
        )

        assert result.success is False
        assert result.error == "Evaluation failed"
        assert result.metrics == {}
        assert result.samples_evaluated == 0

    def test_evaluation_result_defaults(self):
        """Test evaluation result with default values."""
        result = EvaluationResult(metrics={"accuracy": 0.9}, metadata={}, samples_evaluated=50)

        assert result.success is True
        assert result.error is None
        assert result.metadata == {}


class ConcreteEvaluator(BaseEvaluator):
    """Concrete implementation of BaseEvaluator for testing."""

    def __init__(self, task_type: str = "test"):
        super().__init__(task_type)
        self.supported_metrics = ["accuracy", "precision", "recall", "f1"]

    def get_supported_metrics(self) -> List[str]:
        return self.supported_metrics

    def validate_model_config(self, model_config: Dict[str, Any]) -> bool:
        # Simple validation - requires model_type field
        return "model_type" in model_config

    def extract_ground_truth(self, task_instance: Dict[str, Any]):
        return task_instance.get("ground_truth")

    def extract_predictions(self, task_instance: Dict[str, Any], model_id: str):
        predictions = task_instance.get("predictions", {})
        return predictions.get(model_id)

    def compute_metrics(
        self, ground_truth: List[str], predictions: List[str], metrics: List[str]
    ) -> Dict[str, float]:
        # Simple mock metrics computation
        results = {}
        for metric in metrics:
            if metric == "accuracy":
                results[metric] = 0.85
            elif metric == "precision":
                results[metric] = 0.80
            elif metric == "recall":
                results[metric] = 0.90
            elif metric == "f1":
                results[metric] = 0.85
            else:
                results[metric] = 0.0
        return results

    def evaluate(
        self, model_id: str, task_data: List[Dict[str, Any]], config: EvaluationConfig
    ) -> EvaluationResult:
        # Simple mock evaluation
        self.log_evaluation_start(model_id, config)

        # Validate model config
        if not self.validate_model_config(config.model_config):
            return EvaluationResult(
                metrics={},
                metadata={},
                error="Invalid model configuration",
                samples_evaluated=0,
            )

        # Extract data
        ground_truth = []
        predictions = []

        for task in task_data:
            gt = self.extract_ground_truth(task)
            pred = self.extract_predictions(task, model_id)

            if gt is not None and pred is not None:
                ground_truth.append(str(gt))
                predictions.append(str(pred))

        if not ground_truth:
            return EvaluationResult(
                metrics={},
                metadata={},
                error="No valid data found",
                samples_evaluated=0,
            )

        # Compute metrics
        metrics = self.compute_metrics(ground_truth, predictions, config.metrics)

        result = EvaluationResult(
            metrics=metrics,
            metadata={"model_id": model_id, "task_type": self.task_type},
            samples_evaluated=len(ground_truth),
        )

        self.log_evaluation_end(result)
        return result


class TestBaseEvaluator:
    """Test the BaseEvaluator abstract class."""

    @pytest.fixture
    def evaluator(self):
        """Create concrete evaluator instance for testing."""
        return ConcreteEvaluator()

    def test_evaluator_initialization(self, evaluator):
        """Test evaluator initialization."""
        assert evaluator.task_type == "test"
        assert evaluator.logger is not None
        assert evaluator.get_supported_metrics() == [
            "accuracy",
            "precision",
            "recall",
            "f1",
        ]

    def test_validate_data_compatibility_valid(self, evaluator):
        """Test data compatibility validation with valid data."""
        task_data = [
            {
                "id": 1,
                "data": {"question": "Test?"},
                "annotations": [],
                "predictions": [],
            },
            {
                "id": 2,
                "data": {"question": "Test2?"},
                "annotations": [],
                "predictions": [],
            },
        ]

        is_valid, error_msg = evaluator.validate_data_compatibility(task_data)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_data_compatibility_empty(self, evaluator):
        """Test data compatibility validation with empty data."""
        is_valid, error_msg = evaluator.validate_data_compatibility([])
        assert is_valid is False
        assert "No task data provided" in error_msg

    def test_validate_data_compatibility_malformed(self, evaluator):
        """Test data compatibility validation with malformed data."""
        malformed_data = [
            {"id": 1},  # Missing required fields
            "invalid_structure",  # Not a dictionary
        ]

        is_valid, error_msg = evaluator.validate_data_compatibility(malformed_data)
        assert is_valid is False
        assert "missing" in error_msg.lower()

    def test_log_evaluation_start(self, evaluator):
        """Test evaluation start logging."""
        config = EvaluationConfig(metrics=["accuracy"], model_config={})

        with patch.object(evaluator.logger, "info") as mock_log:
            evaluator.log_evaluation_start("test-model", config)
            mock_log.assert_called_once()

            # Check log message contains relevant info
            log_call = mock_log.call_args[0][0]
            assert "test-model" in log_call
            assert "accuracy" in log_call

    def test_log_evaluation_end_success(self, evaluator):
        """Test evaluation end logging for successful result."""
        result = EvaluationResult(metrics={"accuracy": 0.85}, metadata={}, samples_evaluated=100)

        with patch.object(evaluator.logger, "info") as mock_log:
            evaluator.log_evaluation_end(result)
            mock_log.assert_called_once()

            log_call = mock_log.call_args[0][0]
            assert "successful" in log_call.lower()
            assert "0.85" in log_call
            assert "100" in log_call

    def test_log_evaluation_end_error(self, evaluator):
        """Test evaluation end logging for error result."""
        result = EvaluationResult(metrics={}, metadata={}, error="Test error", samples_evaluated=0)

        with patch.object(evaluator.logger, "error") as mock_log:
            evaluator.log_evaluation_end(result)
            mock_log.assert_called_once()

            log_call = mock_log.call_args[0][0]
            assert "Test error" in log_call

    def test_evaluation_integration(self, evaluator):
        """Test full evaluation workflow."""
        task_data = [
            {
                "id": 1,
                "ground_truth": "answer1",
                "predictions": {"test-model": "prediction1"},
            },
            {
                "id": 2,
                "ground_truth": "answer2",
                "predictions": {"test-model": "prediction2"},
            },
        ]

        config = EvaluationConfig(metrics=["accuracy", "f1"], model_config={"model_type": "test"})

        result = evaluator.evaluate("test-model", task_data, config)

        assert result.success is True
        assert result.error is None
        assert result.samples_evaluated == 2
        assert "accuracy" in result.metrics
        assert "f1" in result.metrics
        assert result.metrics["accuracy"] == 0.85
        assert result.metrics["f1"] == 0.85

    def test_evaluation_invalid_config(self, evaluator):
        """Test evaluation with invalid configuration."""
        task_data = [
            {
                "id": 1,
                "ground_truth": "answer1",
                "predictions": {"test-model": "prediction1"},
            }
        ]

        config = EvaluationConfig(
            metrics=["accuracy"], model_config={}  # Missing required model_type
        )

        result = evaluator.evaluate("test-model", task_data, config)

        assert result.success is False
        assert "Invalid model configuration" in result.error
        assert result.samples_evaluated == 0

    def test_evaluation_no_valid_data(self, evaluator):
        """Test evaluation with no valid ground truth/prediction pairs."""
        task_data = [
            {
                "id": 1,
                "ground_truth": "answer1",
                "predictions": {},  # No predictions for test-model
            },
            {
                "id": 2,
                "ground_truth": None,  # No ground truth
                "predictions": {"test-model": "prediction2"},
            },
        ]

        config = EvaluationConfig(metrics=["accuracy"], model_config={"model_type": "test"})

        result = evaluator.evaluate("test-model", task_data, config)

        assert result.success is False
        assert "No valid data found" in result.error
        assert result.samples_evaluated == 0


class TestBaseEvaluatorEdgeCases:
    """Test edge cases and error conditions in BaseEvaluator."""

    @pytest.fixture
    def evaluator(self):
        """Create concrete evaluator instance for testing."""
        return ConcreteEvaluator()

    def test_very_large_dataset(self, evaluator):
        """Test evaluation with very large dataset."""
        # Create large dataset
        task_data = []
        for i in range(1000):
            task_data.append(
                {
                    "id": i,
                    "ground_truth": f"answer{i}",
                    "predictions": {"test-model": f"prediction{i}"},
                }
            )

        config = EvaluationConfig(metrics=["accuracy"], model_config={"model_type": "test"})

        result = evaluator.evaluate("test-model", task_data, config)

        assert result.success is True
        assert result.samples_evaluated == 1000

    def test_unsupported_metrics(self, evaluator):
        """Test evaluation with unsupported metrics."""
        task_data = [
            {
                "id": 1,
                "ground_truth": "answer1",
                "predictions": {"test-model": "prediction1"},
            }
        ]

        config = EvaluationConfig(
            metrics=["unsupported_metric"], model_config={"model_type": "test"}
        )

        result = evaluator.evaluate("test-model", task_data, config)

        # Should still succeed but metric will be 0.0
        assert result.success is True
        assert result.metrics["unsupported_metric"] == 0.0

    def test_mixed_data_types(self, evaluator):
        """Test evaluation with mixed data types."""
        task_data = [
            {
                "id": 1,
                "ground_truth": 123,  # Integer
                "predictions": {"test-model": "123"},  # String
            },
            {
                "id": 2,
                "ground_truth": ["list", "answer"],  # List
                "predictions": {"test-model": "list answer"},  # String
            },
        ]

        config = EvaluationConfig(metrics=["accuracy"], model_config={"model_type": "test"})

        result = evaluator.evaluate("test-model", task_data, config)

        # Should handle type conversion to strings
        assert result.success is True
        assert result.samples_evaluated == 2

    def test_unicode_and_special_characters(self, evaluator):
        """Test evaluation with Unicode and special characters."""
        task_data = [
            {
                "id": 1,
                "ground_truth": "Tëst äñswer with émojis 🎯",
                "predictions": {"test-model": "Test answer with emojis 🎯"},
            }
        ]

        config = EvaluationConfig(metrics=["accuracy"], model_config={"model_type": "test"})

        result = evaluator.evaluate("test-model", task_data, config)

        assert result.success is True
        assert result.samples_evaluated == 1

    def test_memory_efficiency(self, evaluator):
        """Test that evaluation doesn't consume excessive memory."""
        # This is a placeholder for memory efficiency testing
        # In practice, you might use memory profiling tools

        # Create moderately large dataset
        task_data = []
        for i in range(100):
            task_data.append(
                {
                    "id": i,
                    "ground_truth": "answer " * 100,  # Long strings
                    "predictions": {"test-model": "prediction " * 100},
                }
            )

        config = EvaluationConfig(
            metrics=["accuracy", "precision", "recall", "f1"],
            model_config={"model_type": "test"},
        )

        # Should complete without memory errors
        result = evaluator.evaluate("test-model", task_data, config)
        assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__])
