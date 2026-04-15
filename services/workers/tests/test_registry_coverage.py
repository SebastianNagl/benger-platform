"""Coverage tests for ml_evaluation/registry.py.

Tests: EvaluatorRegistry register, get_evaluator, create_evaluator,
get_supported_task_types, get_supported_metrics, is_task_type_supported,
unregister, list_evaluators, validate_evaluator_compatibility.
"""

import sys
import os

import pytest

workers_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, workers_root)

from ml_evaluation.registry import EvaluatorRegistry
from ml_evaluation.base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult


class DummyEvaluator(BaseEvaluator):
    def evaluate(self, model_id, task_data, config):
        return EvaluationResult(metrics={}, metadata={})

    def get_supported_metrics(self):
        return ["accuracy", "f1"]

    def validate_model_config(self, model_config):
        return "model" in model_config


class BrokenEvaluator(BaseEvaluator):
    """Evaluator that raises on instantiation with wrong args."""
    def __init__(self, task_type):
        super().__init__(task_type)
        raise RuntimeError("broken")

    def evaluate(self, model_id, task_data, config):
        return EvaluationResult(metrics={}, metadata={})

    def get_supported_metrics(self):
        return []

    def validate_model_config(self, model_config):
        return False


class TestEvaluatorRegistry:
    def setup_method(self):
        self.registry = EvaluatorRegistry()

    def test_register_and_get(self):
        self.registry.register("qa", DummyEvaluator)
        assert self.registry.get_evaluator("qa") == DummyEvaluator

    def test_register_invalid_class(self):
        with pytest.raises(ValueError):
            self.registry.register("qa", str)

    def test_register_override(self):
        self.registry.register("qa", DummyEvaluator)
        self.registry.register("qa", DummyEvaluator)  # Should log warning
        assert self.registry.get_evaluator("qa") == DummyEvaluator

    def test_get_evaluator_not_found(self):
        assert self.registry.get_evaluator("nonexistent") is None

    def test_create_evaluator(self):
        self.registry.register("qa", DummyEvaluator)
        evaluator = self.registry.create_evaluator("qa")
        assert isinstance(evaluator, DummyEvaluator)

    def test_create_evaluator_not_found(self):
        assert self.registry.create_evaluator("nonexistent") is None

    def test_create_evaluator_fails(self):
        self.registry.register("broken", BrokenEvaluator)
        assert self.registry.create_evaluator("broken") is None

    def test_get_supported_task_types(self):
        self.registry.register("qa", DummyEvaluator)
        self.registry.register("classification", DummyEvaluator)
        types = self.registry.get_supported_task_types()
        assert "qa" in types
        assert "classification" in types

    def test_get_supported_metrics(self):
        self.registry.register("qa", DummyEvaluator)
        metrics = self.registry.get_supported_metrics("qa")
        assert "accuracy" in metrics
        assert "f1" in metrics

    def test_get_supported_metrics_not_found(self):
        metrics = self.registry.get_supported_metrics("nonexistent")
        assert metrics == []

    def test_get_supported_metrics_broken(self):
        self.registry.register("broken", BrokenEvaluator)
        metrics = self.registry.get_supported_metrics("broken")
        assert metrics == []

    def test_is_task_type_supported(self):
        self.registry.register("qa", DummyEvaluator)
        assert self.registry.is_task_type_supported("qa") is True
        assert self.registry.is_task_type_supported("other") is False

    def test_unregister(self):
        self.registry.register("qa", DummyEvaluator)
        result = self.registry.unregister("qa")
        assert result is True
        assert self.registry.get_evaluator("qa") is None

    def test_unregister_not_found(self):
        result = self.registry.unregister("nonexistent")
        assert result is False

    def test_list_evaluators(self):
        self.registry.register("qa", DummyEvaluator)
        listing = self.registry.list_evaluators()
        assert listing == {"qa": "DummyEvaluator"}

    def test_validate_evaluator_compatibility_valid(self):
        self.registry.register("qa", DummyEvaluator)
        assert self.registry.validate_evaluator_compatibility("qa", {"model": "gpt"}) is True

    def test_validate_evaluator_compatibility_invalid(self):
        self.registry.register("qa", DummyEvaluator)
        assert self.registry.validate_evaluator_compatibility("qa", {}) is False

    def test_validate_evaluator_compatibility_not_found(self):
        assert self.registry.validate_evaluator_compatibility("nonexistent", {}) is False

    def test_validate_evaluator_compatibility_broken(self):
        self.registry.register("broken", BrokenEvaluator)
        assert self.registry.validate_evaluator_compatibility("broken", {}) is False
