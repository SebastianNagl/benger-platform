"""Hierarchical classification metric-family computations.

Covers hierarchical_f1 / path_accuracy / lca_accuracy and the hierarchy-path
parser. Extracted from ``SampleEvaluator``. ``levenshtein_distance`` lives
here (its canonical home) and is also consumed by the lexical family
(edit_distance) via ``ev._levenshtein_distance`` — the class shim re-routes.
"""

import json
from typing import Any, Dict, List, Optional


def compute_hierarchical_metric(
    ev, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Compute hierarchical classification metrics.
    Handles tree-structured label hierarchies.
    """
    if parameters is None:
        parameters = {}

    if metric_name == "hierarchical_f1":
        # Parse hierarchical paths
        gt_path = ev._parse_hierarchy_path(gt)
        pred_path = ev._parse_hierarchy_path(pred)

        if not gt_path and not pred_path:
            return 1.0
        if not gt_path or not pred_path:
            return 0.0

        # Calculate overlap considering hierarchy
        gt_ancestors = set()
        pred_ancestors = set()

        # Build ancestor sets (path from root to label)
        for i in range(len(gt_path)):
            gt_ancestors.add(tuple(gt_path[: i + 1]))
        for i in range(len(pred_path)):
            pred_ancestors.add(tuple(pred_path[: i + 1]))

        # F1 on ancestor sets
        intersection = len(gt_ancestors & pred_ancestors)
        precision = intersection / len(pred_ancestors) if pred_ancestors else 0.0
        recall = intersection / len(gt_ancestors) if gt_ancestors else 0.0

        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)

    elif metric_name == "path_accuracy":
        return ev._compute_path_accuracy(gt, pred, parameters)

    elif metric_name == "lca_accuracy":
        return ev._compute_lca_accuracy(gt, pred, parameters)

    return 0.0


def parse_hierarchy_path(ev, value: Any) -> List[str]:
    """Parse a hierarchical label path"""
    if isinstance(value, list):
        return [str(v) for v in value]
    elif isinstance(value, str):
        # Try JSON first
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        # Try delimiter-separated (/, >, ::)
        for delim in ['/', '>', '::', ' > ', ' / ']:
            if delim in value:
                return [v.strip() for v in value.split(delim) if v.strip()]
        return [value]
    elif value is None:
        return []
    else:
        return [str(value)]


def levenshtein_distance(ev, s1: str, s2: str) -> int:
    """Compute Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return ev._levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # j+1 instead of j since previous_row and current_row are one character longer than s2
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def compute_path_accuracy(
    ev, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Full hierarchical path matching.
    For TAXONOMY annotation type.

    Compares full path from root to leaf with support for level weights.
    Deeper matches are worth more.

    Args:
        gt: Ground truth path (e.g., "Law > Civil > Contract > Breach")
        pred: Predicted path
        parameters: Optional parameters
            - level_weights: List of weights for each level (default: linear increasing)
            - normalize: If True, normalize score by max possible (default: True)

    Returns:
        Score (0.0-1.0) based on hierarchical path matching
    """
    if parameters is None:
        parameters = {}

    normalize = parameters.get("normalize", True)

    # Parse hierarchical paths
    gt_path = ev._parse_hierarchy_path(gt)
    pred_path = ev._parse_hierarchy_path(pred)

    if not gt_path and not pred_path:
        return 1.0
    if not gt_path or not pred_path:
        return 0.0

    # Get level weights (default: increasing weights for deeper levels)
    max_depth = max(len(gt_path), len(pred_path))
    default_weights = [i + 1 for i in range(max_depth)]  # 1, 2, 3, 4, ...
    level_weights = parameters.get("level_weights", default_weights)

    # Ensure we have enough weights
    while len(level_weights) < max_depth:
        level_weights.append(level_weights[-1] + 1 if level_weights else 1)

    # Calculate weighted matching score
    matching_score = 0.0
    max_possible_score = 0.0

    for i in range(max_depth):
        weight = level_weights[i]
        max_possible_score += weight

        if i < len(gt_path) and i < len(pred_path):
            if gt_path[i] == pred_path[i]:
                matching_score += weight
            else:
                # Path diverged - no credit for remaining levels
                break

    if normalize:
        return matching_score / max_possible_score if max_possible_score > 0 else 0.0
    else:
        return matching_score


def compute_lca_accuracy(
    ev, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Lowest Common Ancestor proximity scoring.
    For TAXONOMY annotation type.

    Finds LCA in taxonomy tree and scores based on proximity to actual node.
    Closer LCA = higher score.

    Args:
        gt: Ground truth path
        pred: Predicted path
        parameters: Optional parameters
            - decay_rate: How quickly score decreases with distance (default: 0.5)
            - min_score: Minimum score for any common ancestor (default: 0.1)

    Returns:
        Score (0.0-1.0) based on LCA proximity
    """
    if parameters is None:
        parameters = {}

    decay_rate = parameters.get("decay_rate", 0.5)
    min_score = parameters.get("min_score", 0.1)

    # Parse hierarchical paths
    gt_path = ev._parse_hierarchy_path(gt)
    pred_path = ev._parse_hierarchy_path(pred)

    if not gt_path and not pred_path:
        return 1.0
    if not gt_path or not pred_path:
        return 0.0

    # Exact match
    if gt_path == pred_path:
        return 1.0

    # Find LCA depth (last matching level)
    lca_depth = 0
    for i in range(min(len(gt_path), len(pred_path))):
        if gt_path[i] == pred_path[i]:
            lca_depth = i + 1
        else:
            break

    # No common ancestor
    if lca_depth == 0:
        return 0.0

    # Calculate distance from LCA to ground truth node
    distance_to_gt = len(gt_path) - lca_depth

    # Score based on distance with exponential decay
    # LCA at depth d, GT at depth d+k: score = decay_rate^k
    score = decay_rate**distance_to_gt

    # Apply minimum score threshold
    return max(score, min_score)
