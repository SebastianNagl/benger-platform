"""Coverage tests for ml_evaluation/base_evaluator.py.

Tests: EvaluationConfig, EvaluationResult, BaseEvaluator methods.
"""

import sys
import os

workers_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, workers_root)

from ml_evaluation.base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult


class TestEvaluationConfig:
    def test_default_params(self):
        config = EvaluationConfig(metrics=["accuracy"], model_config={"model": "gpt"})
        assert config.evaluation_params == {}

    def test_explicit_params(self):
        config = EvaluationConfig(
            metrics=["accuracy"],
            model_config={"model": "gpt"},
            evaluation_params={"threshold": 0.5},
        )
        assert config.evaluation_params == {"threshold": 0.5}


class TestEvaluationResult:
    def test_success(self):
        result = EvaluationResult(metrics={"accuracy": 0.9}, metadata={}, samples_evaluated=10)
        assert result.success is True

    def test_failure(self):
        result = EvaluationResult(metrics={}, metadata={}, error="Something failed")
        assert result.success is False

    def test_default_samples(self):
        result = EvaluationResult(metrics={}, metadata={})
        assert result.samples_evaluated == 0


class ConcreteEvaluator(BaseEvaluator):
    """Concrete implementation for testing."""
    def evaluate(self, model_id, task_data, config):
        return EvaluationResult(
            metrics={"accuracy": 1.0},
            metadata={"model": model_id},
            samples_evaluated=len(task_data),
        )

    def get_supported_metrics(self):
        return ["accuracy", "f1"]

    def validate_model_config(self, model_config):
        return "model" in model_config


class TestBaseEvaluatorMethods:
    def setup_method(self):
        self.evaluator = ConcreteEvaluator("text_classification")

    def test_task_type(self):
        assert self.evaluator.task_type == "text_classification"

    def test_preprocess_passthrough(self):
        data = [{"id": 1}]
        assert self.evaluator.preprocess_task_data(data) == data

    def test_extract_ground_truth_with_annotations(self):
        task = {"annotations": [{"result": ["label_a"]}]}
        assert self.evaluator.extract_ground_truth(task) == ["label_a"]

    def test_extract_ground_truth_no_annotations(self):
        task = {"annotations": []}
        assert self.evaluator.extract_ground_truth(task) is None

    def test_extract_ground_truth_missing_key(self):
        task = {}
        assert self.evaluator.extract_ground_truth(task) is None

    def test_extract_predictions_found(self):
        task = {
            "predictions": [
                {"model_version": "gpt-4", "result": ["pred"]},
            ]
        }
        assert self.evaluator.extract_predictions(task, "gpt-4") == ["pred"]

    def test_extract_predictions_model_id(self):
        task = {
            "predictions": [
                {"model_id": "gpt-4", "result": ["pred"]},
            ]
        }
        assert self.evaluator.extract_predictions(task, "gpt-4") == ["pred"]

    def test_extract_predictions_not_found(self):
        task = {"predictions": [{"model_version": "claude", "result": ["pred"]}]}
        assert self.evaluator.extract_predictions(task, "gpt-4") is None

    def test_extract_predictions_empty(self):
        task = {"predictions": []}
        assert self.evaluator.extract_predictions(task, "gpt-4") is None

    def test_extract_predictions_latest(self):
        task = {
            "predictions": [
                {"model_version": "gpt-4", "result": ["old"]},
                {"model_version": "gpt-4", "result": ["new"]},
            ]
        }
        assert self.evaluator.extract_predictions(task, "gpt-4") == ["new"]

    def test_compute_metrics_raises(self):
        import pytest
        with pytest.raises(NotImplementedError):
            self.evaluator.compute_metrics([], [], [])

    def test_validate_data_empty(self):
        valid, msg = self.evaluator.validate_data_compatibility([])
        assert valid is False
        assert "No task data" in msg

    def test_validate_data_missing_annotations(self):
        valid, msg = self.evaluator.validate_data_compatibility([{"predictions": []}])
        assert valid is False
        assert "annotations" in msg

    def test_validate_data_missing_predictions(self):
        valid, msg = self.evaluator.validate_data_compatibility([{"annotations": []}])
        assert valid is False
        assert "predictions" in msg

    def test_validate_data_valid(self):
        valid, msg = self.evaluator.validate_data_compatibility(
            [{"annotations": [], "predictions": []}]
        )
        assert valid is True
        assert msg == ""

    def test_log_evaluation_start(self):
        config = EvaluationConfig(metrics=["accuracy"], model_config={})
        self.evaluator.log_evaluation_start("gpt-4", config)  # Should not raise

    def test_log_evaluation_end_success(self):
        result = EvaluationResult(metrics={"accuracy": 0.9}, metadata={}, samples_evaluated=10)
        self.evaluator.log_evaluation_end(result)  # Should not raise

    def test_log_evaluation_end_failure(self):
        result = EvaluationResult(metrics={}, metadata={}, error="Failed")
        self.evaluator.log_evaluation_end(result)  # Should not raise
