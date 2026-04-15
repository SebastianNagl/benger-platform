"""
Evaluator Registry

This module manages the registration and discovery of ML evaluators.
"""

import logging
from typing import Any, Dict, List, Optional, Type

from .base_evaluator import BaseEvaluator

logger = logging.getLogger(__name__)


class EvaluatorRegistry:
    """
    Registry for ML evaluators.

    This class manages the registration and retrieval of evaluators
    for different task types.
    """

    def __init__(self):
        self._evaluators: Dict[str, Type[BaseEvaluator]] = {}

    def register(self, task_type: str, evaluator_class: Type[BaseEvaluator]):
        """
        Register an evaluator for a specific task type.

        Args:
            task_type: The task type this evaluator handles
            evaluator_class: The evaluator class to register

        Raises:
            ValueError: If the evaluator class is not a subclass of BaseEvaluator
        """
        if not issubclass(evaluator_class, BaseEvaluator):
            raise ValueError(
                f"Evaluator class {evaluator_class.__name__} must inherit from BaseEvaluator"
            )

        if task_type in self._evaluators:
            logger.warning(
                f"Overriding existing evaluator for task type '{task_type}'. "
                f"Previous: {self._evaluators[task_type].__name__}, "
                f"New: {evaluator_class.__name__}"
            )

        self._evaluators[task_type] = evaluator_class
        logger.info(f"Registered evaluator {evaluator_class.__name__} for task type '{task_type}'")

    def get_evaluator(self, task_type: str) -> Optional[Type[BaseEvaluator]]:
        """Get the evaluator class for a specific task type."""
        return self._evaluators.get(task_type)

    def create_evaluator(self, task_type: str) -> Optional[BaseEvaluator]:
        """Create an instance of the evaluator for a specific task type."""
        evaluator_class = self.get_evaluator(task_type)
        if evaluator_class is None:
            logger.error(f"No evaluator registered for task type '{task_type}'")
            return None

        try:
            return evaluator_class(task_type)
        except Exception as e:
            logger.error(f"Failed to create evaluator for task type '{task_type}': {e}")
            return None

    def get_supported_task_types(self) -> List[str]:
        """Get all supported task types."""
        return list(self._evaluators.keys())

    def get_supported_metrics(self, task_type: str) -> List[str]:
        """Get supported metrics for a specific task type."""
        evaluator = self.create_evaluator(task_type)
        if evaluator is None:
            return []

        try:
            return evaluator.get_supported_metrics()
        except Exception as e:
            logger.error(f"Failed to get supported metrics for task type '{task_type}': {e}")
            return []

    def is_task_type_supported(self, task_type: str) -> bool:
        """Check if a task type is supported."""
        return task_type in self._evaluators

    def unregister(self, task_type: str) -> bool:
        """Unregister an evaluator for a specific task type."""
        if task_type in self._evaluators:
            del self._evaluators[task_type]
            logger.info(f"Unregistered evaluator for task type '{task_type}'")
            return True
        return False

    def list_evaluators(self) -> Dict[str, str]:
        """List all registered evaluators."""
        return {
            task_type: evaluator_class.__name__
            for task_type, evaluator_class in self._evaluators.items()
        }

    def validate_evaluator_compatibility(self, task_type: str, model_config: Dict) -> bool:
        """Validate that an evaluator is compatible with a model configuration."""
        evaluator = self.create_evaluator(task_type)
        if evaluator is None:
            return False

        try:
            return evaluator.validate_model_config(model_config)
        except Exception as e:
            logger.error(f"Error validating model config for task type '{task_type}': {e}")
            return False
