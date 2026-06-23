"""Classification / multi-label / regression metric-family computations.

Extracted from ``SampleEvaluator``. Each function takes the evaluator
instance ``ev`` as its first parameter so it can call sibling helpers
(e.g. ``ev._to_set``) and preserve behavior byte-for-byte.

``_to_set`` lives here (its canonical home) and is also consumed by the
ranking family via ``ev._to_set`` — the class shim re-routes, so there is a
single source of truth.
"""

import json
from typing import Any, Dict, Optional


def compute_numeric_metric(ev, metric_name: str, gt: Any, pred: Any) -> float:
    """Compute numeric evaluation metrics including r2 and correlation"""
    try:
        gt_val = float(gt)
        pred_val = float(pred)

        if metric_name == "mae":
            return abs(gt_val - pred_val)
        elif metric_name == "rmse":
            # Per-sample RMSE is the absolute error (sqrt of squared error for n=1).
            # RMSE = sqrt(1/n * sum(errors²)), for n=1: sqrt(error²) = |error|
            # NOTE: For aggregate RMSE, collect squared errors and use sqrt(mean).
            # Returning absolute error here for per-sample interpretability.
            import math

            return math.sqrt((gt_val - pred_val) ** 2)  # = abs(gt_val - pred_val)
        elif metric_name == "mape":
            if gt_val == 0:
                return 100.0 if pred_val != 0 else 0.0
            return abs((gt_val - pred_val) / gt_val) * 100
        elif metric_name == "r2":
            # R² (coefficient of determination) is an aggregate-only metric.
            # It measures variance explained and requires multiple samples.
            # Reference: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.r2_score.html
            raise RuntimeError(
                "R² score is an aggregate-only metric and cannot be computed per-sample. "
                "Use sklearn.metrics.r2_score at the aggregate level."
            )
        elif metric_name == "correlation":
            # Pearson correlation is an aggregate-only metric.
            # It measures linear relationship and requires multiple paired observations.
            # Reference: scipy.stats.pearsonr
            raise RuntimeError(
                "Pearson correlation is an aggregate-only metric and cannot be computed per-sample. "
                "Use scipy.stats.pearsonr at the aggregate level."
            )

    except (ValueError, TypeError):
        return 0.0  # Return 0 for invalid numeric conversion

    return 0.0


def compute_classification_metric(
    ev, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Compute classification metrics for single sample.
    For single samples, these are binary (correct/incorrect).
    True metrics are computed at aggregate level.
    """
    # For single sample classification, treat as binary correct/incorrect
    is_correct = gt == pred

    if metric_name in ["precision", "recall", "f1"]:
        # For single sample: 1.0 if correct (TP), 0.0 if wrong
        return 1.0 if is_correct else 0.0

    elif metric_name == "cohen_kappa":
        # For single sample, return accuracy equivalent
        return 1.0 if is_correct else 0.0

    return 1.0 if is_correct else 0.0


def compute_set_metric(ev, metric_name: str, gt: Any, pred: Any) -> float:
    """
    Compute set-based metrics for multi-label classification.
    Handles list/set comparisons.
    """
    # Convert to sets for comparison
    gt_set = ev._to_set(gt)
    pred_set = ev._to_set(pred)

    if metric_name == "jaccard":
        # Jaccard similarity = |intersection| / |union|
        if not gt_set and not pred_set:
            return 1.0  # Both empty = perfect match
        if not gt_set or not pred_set:
            return 0.0
        intersection = len(gt_set & pred_set)
        union = len(gt_set | pred_set)
        return intersection / union if union > 0 else 0.0

    elif metric_name == "hamming_loss":
        # Hamming loss = fraction of wrong labels
        # For sets, count symmetric difference
        if not gt_set and not pred_set:
            return 0.0  # No loss if both empty
        all_labels = gt_set | pred_set
        if not all_labels:
            return 0.0
        symmetric_diff = len(gt_set ^ pred_set)
        return symmetric_diff / len(all_labels)

    elif metric_name == "subset_accuracy":
        # Exact match of entire set
        return 1.0 if gt_set == pred_set else 0.0

    return 0.0


def to_set(ev, value: Any) -> set:
    """Convert a value to a set for comparison"""
    if isinstance(value, set):
        return value
    elif isinstance(value, (list, tuple)):
        return set(value)
    elif isinstance(value, str):
        # Try to parse as list
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return set(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
        # Treat as single-element set
        return {value}
    elif value is None:
        return set()
    else:
        return {value}


def compute_token_f1(ev, gt: Any, pred: Any) -> float:
    """
    Compute token-level F1 score.
    Treats text as bag of tokens and computes F1.
    """
    gt_str = str(gt).lower()
    pred_str = str(pred).lower()

    gt_tokens = set(gt_str.split())
    pred_tokens = set(pred_str.split())

    if not gt_tokens and not pred_tokens:
        return 1.0
    if not gt_tokens or not pred_tokens:
        return 0.0

    intersection = len(gt_tokens & pred_tokens)

    precision = intersection / len(pred_tokens) if pred_tokens else 0.0
    recall = intersection / len(gt_tokens) if gt_tokens else 0.0

    if precision + recall == 0:
        return 0.0

    f1 = 2 * (precision * recall) / (precision + recall)
    return f1
