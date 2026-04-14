"""Extended tests for ml_evaluation/registry.py - evaluator registration.

Covers edge cases and methods not covered in test_evaluation_registry.py:
- register override warning
- unregister
- list_evaluators
- is_task_type_supported
- get_evaluator returns None for unknown
- create_evaluator returns None for unknown
- get_supported_metrics for unknown type
"""

import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult
from ml_evaluation.registry import EvaluatorRegistry


class DummyEvaluatorA(BaseEvaluator):
    def evaluate(self, model_id, task_data, config):
        return EvaluationResult(metrics={}, metadata={})

    def get_supported_metrics(self):
        return ["metric_a"]

    def validate_model_config(self, model_config):
        return True


class DummyEvaluatorB(BaseEvaluator):
    def evaluate(self, model_id, task_data, config):
        return EvaluationResult(metrics={}, metadata={})

    def get_supported_metrics(self):
        return ["metric_b"]

    def validate_model_config(self, model_config):
        return True


class TestRegistryExtended:

    def setup_method(self):
        self.registry = EvaluatorRegistry()

    def test_register_and_get(self):
        self.registry.register("task_a", DummyEvaluatorA)
        assert self.registry.get_evaluator("task_a") == DummyEvaluatorA

    def test_register_override(self):
        self.registry.register("task_a", DummyEvaluatorA)
        self.registry.register("task_a", DummyEvaluatorB)
        assert self.registry.get_evaluator("task_a") == DummyEvaluatorB

    def test_register_invalid_class_raises(self):
        with pytest.raises(ValueError):
            self.registry.register("task_a", dict)

    def test_get_evaluator_unknown(self):
        assert self.registry.get_evaluator("nonexistent") is None

    def test_create_evaluator(self):
        self.registry.register("task_a", DummyEvaluatorA)
        evaluator = self.registry.create_evaluator("task_a")
        assert isinstance(evaluator, DummyEvaluatorA)
        assert evaluator.task_type == "task_a"

    def test_create_evaluator_unknown(self):
        assert self.registry.create_evaluator("nonexistent") is None

    def test_get_supported_task_types(self):
        self.registry.register("type_a", DummyEvaluatorA)
        self.registry.register("type_b", DummyEvaluatorB)
        types = self.registry.get_supported_task_types()
        assert "type_a" in types
        assert "type_b" in types

    def test_get_supported_metrics(self):
        self.registry.register("task_a", DummyEvaluatorA)
        metrics = self.registry.get_supported_metrics("task_a")
        assert metrics == ["metric_a"]

    def test_get_supported_metrics_unknown(self):
        assert self.registry.get_supported_metrics("nonexistent") == []

    def test_is_task_type_supported(self):
        self.registry.register("task_a", DummyEvaluatorA)
        assert self.registry.is_task_type_supported("task_a") is True
        assert self.registry.is_task_type_supported("nonexistent") is False

    def test_unregister(self):
        self.registry.register("task_a", DummyEvaluatorA)
        assert self.registry.unregister("task_a") is True
        assert self.registry.get_evaluator("task_a") is None

    def test_unregister_nonexistent(self):
        assert self.registry.unregister("nonexistent") is False

    def test_list_evaluators(self):
        self.registry.register("task_a", DummyEvaluatorA)
        self.registry.register("task_b", DummyEvaluatorB)
        listing = self.registry.list_evaluators()
        assert listing["task_a"] == "DummyEvaluatorA"
        assert listing["task_b"] == "DummyEvaluatorB"

    def test_list_evaluators_empty(self):
        assert self.registry.list_evaluators() == {}

    def test_validate_evaluator_compatibility(self):
        self.registry.register("task_a", DummyEvaluatorA)
        assert self.registry.validate_evaluator_compatibility("task_a", {}) is True

    def test_validate_evaluator_compatibility_unknown(self):
        assert self.registry.validate_evaluator_compatibility("unknown", {}) is False
