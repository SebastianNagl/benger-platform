"""
Utility Functions for ML Evaluation

Common utility functions shared across different evaluators.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


def load_task_data_from_label_studio(
    project_id: int, api_url: str, api_key: str
) -> List[Dict[str, Any]]:
    """
    Load task data from Label Studio API.

    Args:
        project_id: Label Studio project ID
        api_url: Label Studio API URL
        api_key: Label Studio API key

    Returns:
        List of task instances with annotations and predictions
    """
    try:
        headers = {"Authorization": f"Token {api_key}"}

        # Get tasks with annotations and predictions
        url = f"{api_url}/projects/{project_id}/tasks"
        params = {
            "include": "annotations,predictions",
            "page_size": 1000,  # Adjust as needed
        }

        with httpx.Client() as client:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            tasks = data.get("results", []) if isinstance(data, dict) else data

            logger.info(f"Loaded {len(tasks)} tasks from Label Studio project {project_id}")
            return tasks

    except Exception as e:
        logger.error(f"Failed to load task data from Label Studio: {e}")
        return []


def filter_tasks_with_model_predictions(
    tasks: List[Dict[str, Any]], model_id: str
) -> List[Dict[str, Any]]:
    """
    Filter tasks that have predictions from a specific model.

    Args:
        tasks: List of task instances
        model_id: Model ID to filter by

    Returns:
        Filtered list of tasks with model predictions
    """
    filtered_tasks = []

    for task in tasks:
        predictions = task.get("predictions", [])
        has_model_prediction = any(
            p.get("model_version") == model_id or p.get("model_id") == model_id for p in predictions
        )

        if has_model_prediction and task.get("annotations"):
            filtered_tasks.append(task)

    logger.info(f"Filtered {len(filtered_tasks)} tasks with predictions from model {model_id}")
    return filtered_tasks


def validate_evaluation_request(
    task_id: str,
    model_id: str,
    metrics: List[str],
    supported_task_types: List[str],
    supported_metrics: Dict[str, List[str]],
) -> tuple[bool, str]:
    """
    Validate an evaluation request.

    Args:
        task_id: Task ID to evaluate
        model_id: Model ID to evaluate
        metrics: Requested metrics
        supported_task_types: List of supported task types
        supported_metrics: Dict mapping task types to supported metrics

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not task_id:
        return False, "Task ID is required"

    if not model_id:
        return False, "Model ID is required"

    if not metrics:
        return False, "At least one metric is required"

    # Additional validation can be added here
    return True, ""


def create_evaluation_metadata(
    task_type: str,
    model_id: str,
    total_samples: int,
    valid_samples: int,
    config: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Create standardized evaluation metadata.

    Args:
        task_type: Type of task evaluated
        model_id: Model that was evaluated
        total_samples: Total number of samples in dataset
        valid_samples: Number of samples that could be evaluated
        config: Additional configuration metadata

    Returns:
        Metadata dictionary
    """
    metadata = {
        "task_type": task_type,
        "model_id": model_id,
        "total_samples": total_samples,
        "valid_samples": valid_samples,
        "evaluation_timestamp": datetime.now().isoformat(),
        "coverage": valid_samples / total_samples if total_samples > 0 else 0.0,
    }

    if config:
        metadata.update(config)

    return metadata


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if denominator is zero.

    Args:
        numerator: Numerator
        denominator: Denominator
        default: Default value if division by zero

    Returns:
        Division result or default
    """
    return numerator / denominator if denominator != 0 else default


def normalize_metric_name(metric_name: str) -> str:
    """
    Normalize metric names to a standard format.

    Args:
        metric_name: Original metric name

    Returns:
        Normalized metric name
    """
    return metric_name.lower().replace("-", "_").replace(" ", "_")


def format_metrics_for_display(metrics: Dict[str, float], precision: int = 3) -> Dict[str, str]:
    """
    Format metrics for display with consistent precision.

    Args:
        metrics: Dictionary of metric values
        precision: Number of decimal places

    Returns:
        Dictionary of formatted metric strings
    """
    formatted = {}
    for name, value in metrics.items():
        if isinstance(value, (int, float)):
            formatted[name] = f"{value:.{precision}f}"
        else:
            formatted[name] = str(value)

    return formatted


def log_evaluation_summary(
    model_id: str,
    task_type: str,
    metrics: Dict[str, float],
    samples_evaluated: int,
    duration_seconds: float = None,
):
    """
    Log a summary of evaluation results.

    Args:
        model_id: Model that was evaluated
        task_type: Type of task
        metrics: Computed metrics
        samples_evaluated: Number of samples evaluated
        duration_seconds: Evaluation duration in seconds
    """
    summary = f"Evaluation Summary - Model: {model_id}, Task: {task_type}"
    summary += f", Samples: {samples_evaluated}"

    if duration_seconds:
        summary += f", Duration: {duration_seconds:.2f}s"

    summary += f", Metrics: {format_metrics_for_display(metrics)}"

    logger.info(summary)


def extract_task_type_from_label_config(label_config: str) -> Optional[str]:
    """
    Extract task type from Label Studio label configuration.

    Args:
        label_config: Label Studio label configuration XML

    Returns:
        Inferred task type or None
    """
    try:
        # Simple heuristics based on label config content
        config_lower = label_config.lower()

        if "choices" in config_lower and "text" in config_lower:
            return "text_classification"
        elif "textarea" in config_lower and (
            "summary" in config_lower or "zusammenfassung" in config_lower
        ):
            return "summarization"
        elif "textarea" in config_lower and ("question" in config_lower or "frage" in config_lower):
            return "qa_reasoning"
        else:
            # Default fallback
            return "text_classification"

    except Exception as e:
        logger.warning(f"Could not extract task type from label config: {e}")
        return None


def merge_evaluation_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge multiple evaluation results into a single summary.

    Args:
        results: List of evaluation result dictionaries

    Returns:
        Merged evaluation result
    """
    if not results:
        return {}

    if len(results) == 1:
        return results[0]

    # Merge metrics by averaging
    all_metrics = {}
    for result in results:
        metrics = result.get("metrics", {})
        for metric_name, value in metrics.items():
            if metric_name not in all_metrics:
                all_metrics[metric_name] = []
            all_metrics[metric_name].append(value)

    averaged_metrics = {name: sum(values) / len(values) for name, values in all_metrics.items()}

    # Merge metadata
    merged_metadata = {
        "total_samples": sum(r.get("metadata", {}).get("total_samples", 0) for r in results),
        "valid_samples": sum(r.get("metadata", {}).get("valid_samples", 0) for r in results),
        "num_evaluations": len(results),
    }

    # Take metadata from first result for other fields
    if results[0].get("metadata"):
        for key, value in results[0]["metadata"].items():
            if key not in merged_metadata:
                merged_metadata[key] = value

    return {
        "metrics": averaged_metrics,
        "metadata": merged_metadata,
        "samples_evaluated": merged_metadata["valid_samples"],
    }


def export_evaluation_results(
    results: Dict[str, Any],
    output_format: str = "json",
    output_path: Optional[str] = None,
) -> Union[str, Dict[str, Any]]:
    """
    Export evaluation results in different formats.

    Args:
        results: Evaluation results dictionary
        output_format: Output format ("json", "csv", "dict")
        output_path: Optional file path to save results

    Returns:
        Formatted results or file path
    """
    if output_format == "json":
        json_str = json.dumps(results, indent=2, ensure_ascii=False)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_str)
            return output_path
        else:
            return json_str

    elif output_format == "csv":
        # Simple CSV export for metrics
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["metric", "value"])

        # Write metrics
        metrics = results.get("metrics", {})
        for metric_name, value in metrics.items():
            writer.writerow([metric_name, value])

        csv_content = output.getvalue()
        output.close()

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(csv_content)
            return output_path
        else:
            return csv_content

    else:  # dict format
        return results


class EvaluationTimer:
    """Context manager for timing evaluations."""

    def __init__(self, operation_name: str = "evaluation"):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = datetime.now()
        logger.info(f"Starting {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()

        if exc_type is None:
            logger.info(f"Completed {self.operation_name} in {duration:.2f} seconds")
        else:
            logger.error(f"Failed {self.operation_name} after {duration:.2f} seconds: {exc_val}")

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get duration in seconds if timing is complete."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
