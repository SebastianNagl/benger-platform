"""Ranking metric-family computations.

Extracted from ``SampleEvaluator``. ``compute_ranking_metric`` calls the
sibling helpers ``ev._to_list`` / ``ev._to_set``; ``to_list`` is the
canonical home of ``_to_list`` (also used elsewhere via ``ev._to_list``).
"""

import json
from typing import Any, List, Optional

import numpy as np
from scipy.stats import kendalltau, spearmanr
from sklearn.metrics import ndcg_score


def compute_ranking_metric(
    ev, metric_name: str, gt: Any, pred: Any, parameters: Optional[dict] = None
) -> float:
    """
    Compute ranking metrics.
    For single samples, these are approximations - true metrics computed at aggregate level.
    """
    if parameters is None:
        parameters = {}

    if metric_name == "weighted_kappa":
        # Weighted Cohen's Kappa is an aggregate-only metric.
        # It measures inter-rater agreement across multiple observations.
        # Reference: sklearn.metrics.cohen_kappa_score(weights='quadratic')
        raise RuntimeError(
            "Weighted Kappa is an aggregate-only metric and cannot be computed per-sample. "
            "Use sklearn.metrics.cohen_kappa_score(weights='quadratic') at the aggregate level."
        )

    elif metric_name == "spearman":
        # For single sample, use rank comparison
        try:
            gt_list = ev._to_list(gt)
            pred_list = ev._to_list(pred)
            if gt_list == pred_list:
                return 1.0
            if len(gt_list) != len(pred_list):
                return 0.0
            if len(gt_list) > 1:
                corr, _ = spearmanr(gt_list, pred_list)
                return max(0.0, corr) if not np.isnan(corr) else 0.0
            # Single element lists have perfect correlation
            return 1.0
        except Exception as e:
            raise RuntimeError(f"Spearman correlation failed: {e}")

    elif metric_name == "kendall":
        # Kendall's tau
        try:
            gt_list = ev._to_list(gt)
            pred_list = ev._to_list(pred)
            if gt_list == pred_list:
                return 1.0
            if len(gt_list) != len(pred_list):
                return 0.0
            if len(gt_list) > 1:
                tau, _ = kendalltau(gt_list, pred_list)
                return max(0.0, tau) if not np.isnan(tau) else 0.0
            # Single element lists have perfect correlation
            return 1.0
        except Exception as e:
            raise RuntimeError(f"Kendall tau correlation failed: {e}")

    elif metric_name == "ndcg":
        # NDCG for relevance ranking
        try:
            gt_list = ev._to_list(gt)
            pred_list = ev._to_list(pred)
            if not gt_list or not pred_list:
                return 1.0 if gt_list == pred_list else 0.0
            # Reshape for sklearn
            gt_arr = np.array([gt_list])
            pred_arr = np.array([pred_list])
            return ndcg_score(gt_arr, pred_arr)
        except Exception as e:
            raise RuntimeError(f"NDCG score computation failed: {e}")

    elif metric_name == "map":
        # Mean Average Precision
        try:
            gt_set = ev._to_set(gt)
            pred_list = ev._to_list(pred)
            if not gt_set or not pred_list:
                return 1.0 if not gt_set and not pred_list else 0.0
            # Calculate AP
            hits = 0
            sum_precisions = 0.0
            for i, item in enumerate(pred_list):
                if item in gt_set:
                    hits += 1
                    sum_precisions += hits / (i + 1)
            return sum_precisions / len(gt_set) if gt_set else 0.0
        except Exception:
            return 1.0 if gt == pred else 0.0

    return 0.0


def to_list(ev, value: Any) -> List[Any]:
    """Convert a value to a list for ranking comparisons"""
    if isinstance(value, list):
        return value
    elif isinstance(value, (tuple, set)):
        return list(value)
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        # Try comma-separated
        if ',' in value:
            return [v.strip() for v in value.split(',')]
        return [value]
    elif value is None:
        return []
    else:
        return [value]
