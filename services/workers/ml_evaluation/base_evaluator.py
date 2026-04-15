"""
Base Evaluator Abstract Class

All ML evaluators must inherit from this class and implement the required methods.
This ensures a consistent interface for all evaluation implementations.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EvaluationConfig:
    """Configuration for evaluation runs"""

    metrics: List[str]
    model_config: Dict[str, Any]
    evaluation_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.evaluation_params is None:
            self.evaluation_params = {}


@dataclass
class EvaluationResult:
    """Standardized evaluation result"""

    metrics: Dict[str, float]
    metadata: Dict[str, Any]
    error: Optional[str] = None
    samples_evaluated: int = 0

    @property
    def success(self) -> bool:
        return self.error is None


class BaseEvaluator(ABC):
    """
    Abstract base class for all ML evaluators.

    ML engineers should inherit from this class and implement the required methods
    to create custom evaluation logic for their models.
    """

    def __init__(self, task_type: str):
        """
        Initialize the evaluator.

        Args:
            task_type: The type of task this evaluator handles (e.g., 'text_classification')
        """
        self.task_type = task_type
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def evaluate(
        self, model_id: str, task_data: List[Dict[str, Any]], config: EvaluationConfig
    ) -> EvaluationResult:
        """
        Evaluate a model on the given task data.

        Args:
            model_id: Identifier for the model to evaluate
            task_data: List of task instances with annotations and predictions
            config: Evaluation configuration including metrics and parameters

        Returns:
            EvaluationResult with computed metrics and metadata
        """

    @abstractmethod
    def get_supported_metrics(self) -> List[str]:
        """
        Return list of metrics this evaluator supports.

        Returns:
            List of metric names (e.g., ['accuracy', 'f1', 'precision', 'recall'])
        """

    @abstractmethod
    def validate_model_config(self, model_config: Dict[str, Any]) -> bool:
        """
        Validate that the model configuration is compatible with this evaluator.

        Args:
            model_config: Model configuration dictionary

        Returns:
            True if configuration is valid, False otherwise
        """

    def preprocess_task_data(self, task_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Preprocess task data before evaluation.

        Override this method if you need custom preprocessing.

        Args:
            task_data: Raw task data from Label Studio

        Returns:
            Preprocessed task data
        """
        return task_data

    def extract_ground_truth(self, task_instance: Dict[str, Any]) -> Any:
        """
        Extract ground truth labels from a task instance.

        Override this method for custom ground truth extraction.

        Args:
            task_instance: Single task instance with annotations

        Returns:
            Ground truth label(s)
        """
        annotations = task_instance.get("annotations", [])
        if not annotations:
            return None

        # Use the first annotation as ground truth
        annotation = annotations[0]
        return annotation.get("result", [])

    def extract_predictions(self, task_instance: Dict[str, Any], model_id: str) -> Any:
        """
        Extract model predictions from a task instance.

        Override this method for custom prediction extraction.

        Args:
            task_instance: Single task instance with predictions
            model_id: ID of the model to extract predictions for

        Returns:
            Model prediction(s)
        """
        predictions = task_instance.get("predictions", [])
        model_predictions = [
            p
            for p in predictions
            if p.get("model_version") == model_id or p.get("model_id") == model_id
        ]

        if not model_predictions:
            return None

        # Use the latest prediction
        latest_prediction = model_predictions[-1]
        return latest_prediction.get("result", [])

    def compute_metrics(
        self, ground_truth: List[Any], predictions: List[Any], metrics: List[str]
    ) -> Dict[str, float]:
        """
        Compute evaluation metrics.

        Override this method to implement custom metric computation.

        Args:
            ground_truth: List of ground truth labels
            predictions: List of model predictions
            metrics: List of metrics to compute

        Returns:
            Dictionary mapping metric names to values
        """
        raise NotImplementedError("Subclasses must implement compute_metrics")

    def validate_data_compatibility(self, task_data: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Validate that the task data is compatible with this evaluator.

        Args:
            task_data: Task data to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not task_data:
            return False, "No task data provided"

        # Check if tasks have required fields
        for i, task in enumerate(task_data):
            if "annotations" not in task:
                return False, f"Task {i} missing annotations"
            if "predictions" not in task:
                return False, f"Task {i} missing predictions"

        return True, ""

    def log_evaluation_start(self, model_id: str, config: EvaluationConfig):
        """Log evaluation start."""
        self.logger.info(
            f"Starting {self.task_type} evaluation for model {model_id} "
            f"with metrics: {config.metrics}"
        )

    def log_evaluation_end(self, result: EvaluationResult):
        """Log evaluation completion."""
        if result.success:
            self.logger.info(
                f"Evaluation completed successfully. "
                f"Evaluated {result.samples_evaluated} samples. "
                f"Metrics: {result.metrics}"
            )
        else:
            self.logger.error(f"Evaluation failed: {result.error}")
