"""Extended tests for ml_evaluation/base_evaluator.py - dataclasses and base methods.

Covers:
- EvaluationConfig
- EvaluationResult
- BaseEvaluator concrete method tests
"""

import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult


# ---------------------------------------------------------------------------
# EvaluationConfig
# ---------------------------------------------------------------------------

class TestEvaluationConfig:

    def test_default_evaluation_params(self):
        config = EvaluationConfig(metrics=["accuracy"], model_config={"model": "gpt-4"})
        assert config.evaluation_params == {}

    def test_custom_evaluation_params(self):
        config = EvaluationConfig(
            metrics=["f1"],
            model_config={"model": "gpt-4"},
            evaluation_params={"threshold": 0.5},
        )
        assert config.evaluation_params["threshold"] == 0.5

    def test_metrics_stored(self):
        config = EvaluationConfig(metrics=["accuracy", "f1"], model_config={})
        assert config.metrics == ["accuracy", "f1"]

    def test_model_config_stored(self):
        config = EvaluationConfig(metrics=[], model_config={"model": "llama"})
        assert config.model_config["model"] == "llama"


# ---------------------------------------------------------------------------
# EvaluationResult
# ---------------------------------------------------------------------------

class TestEvaluationResult:

    def test_success_result(self):
        result = EvaluationResult(
            metrics={"accuracy": 0.95},
            metadata={"model_id": "gpt-4"},
            samples_evaluated=100,
        )
        assert result.success is True
        assert result.error is None

    def test_error_result(self):
        result = EvaluationResult(
            metrics={},
            metadata={},
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_default_samples(self):
        result = EvaluationResult(metrics={}, metadata={})
        assert result.samples_evaluated == 0


# ---------------------------------------------------------------------------
# BaseEvaluator concrete methods (using a minimal subclass)
# ---------------------------------------------------------------------------

class DummyEvaluator(BaseEvaluator):
    """Minimal concrete implementation for testing base methods."""

    def evaluate(self, model_id, task_data, config):
        return EvaluationResult(metrics={"dummy": 1.0}, metadata={})

    def get_supported_metrics(self):
        return ["dummy"]

    def validate_model_config(self, model_config):
        return "model" in model_config


class TestBaseEvaluatorMethods:

    def setup_method(self):
        self.evaluator = DummyEvaluator("test_task")

    def test_task_type(self):
        assert self.evaluator.task_type == "test_task"

    def test_preprocess_task_data_passthrough(self):
        data = [{"id": 1}, {"id": 2}]
        assert self.evaluator.preprocess_task_data(data) == data

    def test_extract_ground_truth_with_annotations(self):
        task = {"annotations": [{"result": [{"value": "correct"}]}]}
        gt = self.evaluator.extract_ground_truth(task)
        assert gt == [{"value": "correct"}]

    def test_extract_ground_truth_no_annotations(self):
        task = {"annotations": []}
        gt = self.evaluator.extract_ground_truth(task)
        assert gt is None

    def test_extract_ground_truth_missing_key(self):
        task = {}
        gt = self.evaluator.extract_ground_truth(task)
        assert gt is None

    def test_extract_predictions_found(self):
        task = {
            "predictions": [
                {"model_version": "gpt-4", "result": [{"value": "pred"}]},
                {"model_version": "llama", "result": [{"value": "other"}]},
            ]
        }
        pred = self.evaluator.extract_predictions(task, "gpt-4")
        assert pred == [{"value": "pred"}]

    def test_extract_predictions_by_model_id(self):
        task = {
            "predictions": [
                {"model_id": "gpt-4", "result": [{"value": "pred"}]},
            ]
        }
        pred = self.evaluator.extract_predictions(task, "gpt-4")
        assert pred == [{"value": "pred"}]

    def test_extract_predictions_not_found(self):
        task = {"predictions": [{"model_version": "llama", "result": []}]}
        pred = self.evaluator.extract_predictions(task, "gpt-4")
        assert pred is None

    def test_extract_predictions_uses_latest(self):
        task = {
            "predictions": [
                {"model_version": "gpt-4", "result": [{"value": "old"}]},
                {"model_version": "gpt-4", "result": [{"value": "new"}]},
            ]
        }
        pred = self.evaluator.extract_predictions(task, "gpt-4")
        assert pred == [{"value": "new"}]

    def test_validate_data_compatibility_valid(self):
        data = [
            {"annotations": [{"result": []}], "predictions": [{"result": []}]},
        ]
        valid, msg = self.evaluator.validate_data_compatibility(data)
        assert valid
        assert msg == ""

    def test_validate_data_compatibility_empty(self):
        valid, msg = self.evaluator.validate_data_compatibility([])
        assert not valid
        assert "No task data" in msg

    def test_validate_data_compatibility_missing_annotations(self):
        data = [{"predictions": []}]
        valid, msg = self.evaluator.validate_data_compatibility(data)
        assert not valid
        assert "missing annotations" in msg

    def test_validate_data_compatibility_missing_predictions(self):
        data = [{"annotations": []}]
        valid, msg = self.evaluator.validate_data_compatibility(data)
        assert not valid
        assert "missing predictions" in msg

    def test_compute_metrics_not_implemented(self):
        with pytest.raises(NotImplementedError):
            self.evaluator.compute_metrics([], [], [])

    def test_validate_model_config(self):
        assert self.evaluator.validate_model_config({"model": "gpt-4"}) is True
        assert self.evaluator.validate_model_config({}) is False
