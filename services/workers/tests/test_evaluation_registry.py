"""
Tests for Evaluation Registry functionality.

Tests cover evaluator registration, discovery, and management
within the ML evaluation system.
"""

from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from ml_evaluation.base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult
from ml_evaluation.registry import EvaluatorRegistry


class MockEvaluator(BaseEvaluator):
    """Mock evaluator for testing purposes."""

    def __init__(self, task_type: str = "mock"):
        super().__init__(task_type)
        self.supported_metrics = ["mock_metric1", "mock_metric2"]

    def get_supported_metrics(self) -> List[str]:
        return self.supported_metrics

    def validate_model_config(self, model_config: Dict[str, Any]) -> bool:
        return "model_type" in model_config

    def extract_ground_truth(self, task_instance: Dict[str, Any]):
        return task_instance.get("ground_truth")

    def extract_predictions(self, task_instance: Dict[str, Any], model_id: str):
        return task_instance.get("predictions", {}).get(model_id)

    def compute_metrics(
        self, ground_truth: List[str], predictions: List[str], metrics: List[str]
    ) -> Dict[str, float]:
        return {metric: 0.85 for metric in metrics}

    def evaluate(
        self, model_id: str, task_data: List[Dict[str, Any]], config: EvaluationConfig
    ) -> EvaluationResult:
        return EvaluationResult(
            metrics={"mock_metric1": 0.85},
            metadata={"model_id": model_id},
            samples_evaluated=len(task_data),
        )


class AnotherMockEvaluator(BaseEvaluator):
    """Another mock evaluator for testing multiple registrations."""

    def __init__(self, task_type: str = "another_mock"):
        super().__init__(task_type)
        self.supported_metrics = ["another_metric"]

    def get_supported_metrics(self) -> List[str]:
        return self.supported_metrics

    def validate_model_config(self, model_config: Dict[str, Any]) -> bool:
        return True  # Always valid for testing

    def extract_ground_truth(self, task_instance: Dict[str, Any]):
        return task_instance.get("ground_truth")

    def extract_predictions(self, task_instance: Dict[str, Any], model_id: str):
        return task_instance.get("predictions", {}).get(model_id)

    def compute_metrics(
        self, ground_truth: List[str], predictions: List[str], metrics: List[str]
    ) -> Dict[str, float]:
        return {metric: 0.90 for metric in metrics}

    def evaluate(
        self, model_id: str, task_data: List[Dict[str, Any]], config: EvaluationConfig
    ) -> EvaluationResult:
        return EvaluationResult(
            metrics={"another_metric": 0.90},
            metadata={"model_id": model_id},
            samples_evaluated=len(task_data),
        )


class InvalidEvaluator:
    """Invalid evaluator that doesn't inherit from BaseEvaluator."""


class TestEvaluatorRegistry:
    """Test the EvaluatorRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create fresh registry for each test."""
        return EvaluatorRegistry()

    def test_registry_initialization(self, registry):
        """Test registry initialization."""
        assert len(registry.get_supported_task_types()) == 0
        assert registry.list_evaluators() == {}

    def test_register_evaluator_success(self, registry):
        """Test successful evaluator registration."""
        registry.register("mock_task", MockEvaluator)

        assert registry.is_task_type_supported("mock_task")
        assert "mock_task" in registry.get_supported_task_types()
        assert registry.get_evaluator("mock_task") == MockEvaluator

    def test_register_invalid_evaluator(self, registry):
        """Test registration of invalid evaluator class."""
        with pytest.raises(ValueError, match="must inherit from BaseEvaluator"):
            registry.register("invalid_task", InvalidEvaluator)

    def test_register_evaluator_override(self, registry):
        """Test overriding existing evaluator registration."""
        # Register first evaluator
        registry.register("task", MockEvaluator)
        assert registry.get_evaluator("task") == MockEvaluator

        # Override with second evaluator
        with patch("ml_evaluation.registry.logger") as mock_logger:
            registry.register("task", AnotherMockEvaluator)
            mock_logger.warning.assert_called_once()
            assert "Overriding existing evaluator" in mock_logger.warning.call_args[0][0]

        assert registry.get_evaluator("task") == AnotherMockEvaluator

    def test_get_nonexistent_evaluator(self, registry):
        """Test getting evaluator for nonexistent task type."""
        assert registry.get_evaluator("nonexistent") is None

    def test_create_evaluator_success(self, registry):
        """Test successful evaluator creation."""
        registry.register("mock_task", MockEvaluator)

        evaluator = registry.create_evaluator("mock_task")
        assert evaluator is not None
        assert isinstance(evaluator, MockEvaluator)
        assert evaluator.task_type == "mock_task"

    def test_create_evaluator_nonexistent(self, registry):
        """Test creating evaluator for nonexistent task type."""
        evaluator = registry.create_evaluator("nonexistent")
        assert evaluator is None

    def test_create_evaluator_exception(self, registry):
        """Test evaluator creation with exception during instantiation."""

        # Mock evaluator class that raises exception
        class FailingEvaluator(BaseEvaluator):
            def __init__(self, task_type):
                raise Exception("Initialization failed")

        registry.register("failing_task", FailingEvaluator)

        evaluator = registry.create_evaluator("failing_task")
        assert evaluator is None

    def test_get_supported_task_types(self, registry):
        """Test getting all supported task types."""
        registry.register("task1", MockEvaluator)
        registry.register("task2", AnotherMockEvaluator)

        task_types = registry.get_supported_task_types()
        assert "task1" in task_types
        assert "task2" in task_types
        assert len(task_types) == 2

    def test_get_supported_metrics_success(self, registry):
        """Test getting supported metrics for registered task type."""
        registry.register("mock_task", MockEvaluator)

        metrics = registry.get_supported_metrics("mock_task")
        assert metrics == ["mock_metric1", "mock_metric2"]

    def test_get_supported_metrics_nonexistent(self, registry):
        """Test getting supported metrics for nonexistent task type."""
        metrics = registry.get_supported_metrics("nonexistent")
        assert metrics == []

    def test_get_supported_metrics_exception(self, registry):
        """Test getting supported metrics when evaluator raises exception."""

        class FailingMetricsEvaluator(BaseEvaluator):
            def get_supported_metrics(self):
                raise Exception("Metrics failure")

        registry.register("failing_metrics", FailingMetricsEvaluator)

        metrics = registry.get_supported_metrics("failing_metrics")
        assert metrics == []

    def test_is_task_type_supported(self, registry):
        """Test checking if task type is supported."""
        assert not registry.is_task_type_supported("mock_task")

        registry.register("mock_task", MockEvaluator)
        assert registry.is_task_type_supported("mock_task")

    def test_unregister_success(self, registry):
        """Test successful evaluator unregistration."""
        registry.register("mock_task", MockEvaluator)
        assert registry.is_task_type_supported("mock_task")

        result = registry.unregister("mock_task")
        assert result is True
        assert not registry.is_task_type_supported("mock_task")

    def test_unregister_nonexistent(self, registry):
        """Test unregistering nonexistent evaluator."""
        result = registry.unregister("nonexistent")
        assert result is False

    def test_list_evaluators(self, registry):
        """Test listing all registered evaluators."""
        registry.register("task1", MockEvaluator)
        registry.register("task2", AnotherMockEvaluator)

        evaluators = registry.list_evaluators()
        assert evaluators == {"task1": "MockEvaluator", "task2": "AnotherMockEvaluator"}

    def test_validate_evaluator_compatibility_success(self, registry):
        """Test successful evaluator compatibility validation."""
        registry.register("mock_task", MockEvaluator)

        model_config = {"model_type": "test"}
        is_compatible = registry.validate_evaluator_compatibility("mock_task", model_config)
        assert is_compatible is True

    def test_validate_evaluator_compatibility_invalid_config(self, registry):
        """Test evaluator compatibility validation with invalid config."""
        registry.register("mock_task", MockEvaluator)

        model_config = {}  # Missing model_type
        is_compatible = registry.validate_evaluator_compatibility("mock_task", model_config)
        assert is_compatible is False

    def test_validate_evaluator_compatibility_nonexistent(self, registry):
        """Test evaluator compatibility validation for nonexistent task type."""
        model_config = {"model_type": "test"}
        is_compatible = registry.validate_evaluator_compatibility("nonexistent", model_config)
        assert is_compatible is False

    def test_validate_evaluator_compatibility_exception(self, registry):
        """Test evaluator compatibility validation with exception."""

        class FailingValidationEvaluator(BaseEvaluator):
            def validate_model_config(self, model_config):
                raise Exception("Validation failure")

        registry.register("failing_validation", FailingValidationEvaluator)

        model_config = {"model_type": "test"}
        is_compatible = registry.validate_evaluator_compatibility(
            "failing_validation", model_config
        )
        assert is_compatible is False


class TestEvaluatorRegistryIntegration:
    """Integration tests for EvaluatorRegistry."""

    @pytest.fixture
    def registry(self):
        """Create registry with pre-registered evaluators."""
        registry = EvaluatorRegistry()
        registry.register("qa", MockEvaluator)
        registry.register("classification", AnotherMockEvaluator)
        return registry

    def test_multiple_evaluator_workflow(self, registry):
        """Test workflow with multiple registered evaluators."""
        # Check initial state
        task_types = registry.get_supported_task_types()
        assert "qa" in task_types
        assert "classification" in task_types

        # Test QA evaluator
        qa_evaluator = registry.create_evaluator("qa")
        assert qa_evaluator is not None
        assert isinstance(qa_evaluator, MockEvaluator)

        qa_metrics = registry.get_supported_metrics("qa")
        assert "mock_metric1" in qa_metrics

        # Test classification evaluator
        clf_evaluator = registry.create_evaluator("classification")
        assert clf_evaluator is not None
        assert isinstance(clf_evaluator, AnotherMockEvaluator)

        clf_metrics = registry.get_supported_metrics("classification")
        assert "another_metric" in clf_metrics

    def test_evaluator_replacement_workflow(self, registry):
        """Test replacing an evaluator and ensuring it works correctly."""
        # Initial evaluator
        registry.create_evaluator("qa")
        original_metrics = registry.get_supported_metrics("qa")

        # Replace with different evaluator
        registry.register("qa", AnotherMockEvaluator)

        # Test new evaluator
        new_evaluator = registry.create_evaluator("qa")
        new_metrics = registry.get_supported_metrics("qa")

        assert isinstance(new_evaluator, AnotherMockEvaluator)
        assert new_metrics != original_metrics
        assert "another_metric" in new_metrics

    def test_registry_state_consistency(self, registry):
        """Test that registry maintains consistent state across operations."""
        initial_count = len(registry.get_supported_task_types())

        # Add evaluator
        registry.register("new_task", MockEvaluator)
        assert len(registry.get_supported_task_types()) == initial_count + 1

        # Remove evaluator
        registry.unregister("new_task")
        assert len(registry.get_supported_task_types()) == initial_count

        # Check original evaluators still exist
        assert registry.is_task_type_supported("qa")
        assert registry.is_task_type_supported("classification")

    def test_concurrent_access_simulation(self, registry):
        """Test simulated concurrent access to registry."""
        # Simulate multiple operations happening in sequence
        operations = [
            ("register", "temp1", MockEvaluator),
            ("create", "qa", None),
            ("metrics", "classification", None),
            ("register", "temp2", AnotherMockEvaluator),
            ("unregister", "temp1", None),
            ("create", "temp2", None),
        ]

        for op, task_type, evaluator_class in operations:
            if op == "register":
                registry.register(task_type, evaluator_class)
            elif op == "create":
                evaluator = registry.create_evaluator(task_type)
                assert evaluator is not None or task_type == "temp1"  # temp1 gets unregistered
            elif op == "metrics":
                metrics = registry.get_supported_metrics(task_type)
                assert len(metrics) > 0
            elif op == "unregister":
                registry.unregister(task_type)

        # Verify final state
        assert registry.is_task_type_supported("qa")
        assert registry.is_task_type_supported("classification")
        assert registry.is_task_type_supported("temp2")
        assert not registry.is_task_type_supported("temp1")


class TestEvaluatorRegistryEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def registry(self):
        """Create fresh registry for each test."""
        return EvaluatorRegistry()

    def test_register_none_evaluator(self, registry):
        """Test registering None as evaluator."""
        with pytest.raises(TypeError):
            registry.register("none_task", None)

    def test_register_empty_task_type(self, registry):
        """Test registering with empty task type."""
        registry.register("", MockEvaluator)
        assert registry.is_task_type_supported("")

        evaluator = registry.create_evaluator("")
        assert evaluator is not None

    def test_register_special_characters_task_type(self, registry):
        """Test registering with special characters in task type."""
        special_task_types = [
            "task-with-hyphens",
            "task_with_underscores",
            "task.with.dots",
            "task with spaces",
            "task@with#symbols",
        ]

        for task_type in special_task_types:
            registry.register(task_type, MockEvaluator)
            assert registry.is_task_type_supported(task_type)

            evaluator = registry.create_evaluator(task_type)
            assert evaluator is not None

    def test_case_sensitive_task_types(self, registry):
        """Test that task types are case sensitive."""
        registry.register("CamelCase", MockEvaluator)
        registry.register("camelcase", AnotherMockEvaluator)

        assert registry.is_task_type_supported("CamelCase")
        assert registry.is_task_type_supported("camelcase")
        assert not registry.is_task_type_supported("CAMELCASE")

        evaluator1 = registry.create_evaluator("CamelCase")
        evaluator2 = registry.create_evaluator("camelcase")

        assert isinstance(evaluator1, MockEvaluator)
        assert isinstance(evaluator2, AnotherMockEvaluator)

    def test_unicode_task_types(self, registry):
        """Test registering with Unicode task types."""
        unicode_task_types = [
            "tâsk_ümläuts",
            "задача_кириллица",
            "タスク_日本語",
            "🎯_emoji_task",
        ]

        for task_type in unicode_task_types:
            registry.register(task_type, MockEvaluator)
            assert registry.is_task_type_supported(task_type)

    def test_very_long_task_type(self, registry):
        """Test registering with very long task type."""
        long_task_type = "very_long_task_type_" * 100

        registry.register(long_task_type, MockEvaluator)
        assert registry.is_task_type_supported(long_task_type)

        evaluator = registry.create_evaluator(long_task_type)
        assert evaluator is not None


if __name__ == "__main__":
    pytest.main([__file__])
