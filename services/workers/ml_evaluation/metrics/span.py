"""Span / sequence-labeling metric-family computations.

Covers span_exact_match / iou / boundary_accuracy and the span parsing and
matching helpers. Extracted from ``SampleEvaluator``. The span parse/match
helpers are the canonical home of these utilities; the structured family
(partial_match) reaches them via ``ev._parse_spans`` etc.
"""

import json
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.optimize import linear_sum_assignment


def compute_span_metric(ev, metric_name: str, gt: Any, pred: Any) -> float:
    """
    Compute span-based metrics for sequence labeling.
    Handles start/end positions for text spans.
    """
    # Parse span information
    gt_spans = ev._parse_spans(gt)
    pred_spans = ev._parse_spans(pred)

    if metric_name == "exact_match":
        # Exact span boundary match
        return 1.0 if gt_spans == pred_spans else 0.0

    elif metric_name == "iou":
        # Intersection over Union for spans with optimal bipartite matching
        if not gt_spans and not pred_spans:
            return 1.0
        if not gt_spans or not pred_spans:
            return 0.0

        total_iou = ev._optimal_span_matching(
            gt_spans, pred_spans, ev._span_iou
        )
        return total_iou / max(len(gt_spans), len(pred_spans))

    return 0.0


def parse_spans(ev, value: Any) -> List[Dict[str, Any]]:
    """Parse span information from various formats, preserving labels when present."""
    if isinstance(value, list):
        spans = []
        for item in value:
            if isinstance(item, dict) and 'start' in item and 'end' in item:
                span: Dict[str, Any] = {'start': int(item['start']), 'end': int(item['end'])}
                # Preserve labels for label-aware matching
                if 'labels' in item and isinstance(item['labels'], list):
                    span['labels'] = item['labels']
                elif 'label' in item and item['label']:
                    span['labels'] = [item['label']] if isinstance(item['label'], str) else item['label']
                spans.append(span)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                spans.append({'start': int(item[0]), 'end': int(item[1])})
        return spans
    elif isinstance(value, dict) and 'start' in value and 'end' in value:
        span = {'start': int(value['start']), 'end': int(value['end'])}
        if 'labels' in value and isinstance(value['labels'], list):
            span['labels'] = value['labels']
        elif 'label' in value and value['label']:
            span['labels'] = [value['label']] if isinstance(value['label'], str) else value['label']
        return [span]
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            return ev._parse_spans(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def spans_label_compatible(ev, gt_span: Dict[str, Any], pred_span: Dict[str, Any]) -> bool:
    """Check if two spans have compatible labels.

    Returns True if labels overlap or if either side has no labels
    (backwards compatible with position-only data).
    """
    gt_labels = set(gt_span.get('labels', []))
    pred_labels = set(pred_span.get('labels', []))
    if not gt_labels or not pred_labels:
        return True  # No labels = position-only matching
    return bool(gt_labels & pred_labels)


def optimal_span_matching(
    ev,
    gt_spans: List[Dict[str, Any]],
    pred_spans: List[Dict[str, Any]],
    score_fn,
) -> float:
    """Optimal bipartite matching between GT and pred spans using Hungarian algorithm.

    Uses scipy.optimize.linear_sum_assignment for optimal assignment.
    Only matches spans with compatible labels.

    Args:
        gt_spans: Ground truth spans
        pred_spans: Predicted spans
        score_fn: Function(span1, span2) -> float score (higher is better)

    Returns:
        Total score across optimal matches
    """
    n_gt = len(gt_spans)
    n_pred = len(pred_spans)

    # Build score matrix
    score_matrix = np.zeros((n_gt, n_pred))
    for i, gt_span in enumerate(gt_spans):
        for j, pred_span in enumerate(pred_spans):
            if ev._spans_label_compatible(gt_span, pred_span):
                score_matrix[i][j] = score_fn(gt_span, pred_span)

    # Hungarian algorithm minimizes cost, so negate scores
    row_ind, col_ind = linear_sum_assignment(-score_matrix)
    return float(score_matrix[row_ind, col_ind].sum())


def span_iou(ev, span1: Dict[str, Any], span2: Dict[str, Any]) -> float:
    """Calculate IoU for two spans"""
    start1, end1 = span1['start'], span1['end']
    start2, end2 = span2['start'], span2['end']

    # Calculate intersection
    inter_start = max(start1, start2)
    inter_end = min(end1, end2)
    intersection = max(0, inter_end - inter_start)

    # Calculate union
    union = (end1 - start1) + (end2 - start2) - intersection

    return intersection / union if union > 0 else 0.0


def calculate_span_overlap(ev, span1: Dict[str, Any], span2: Dict[str, Any]) -> float:
    """
    Calculate character-level overlap between two spans.

    Returns overlap ratio relative to the ground truth span length.
    """
    start1, end1 = span1["start"], span1["end"]
    start2, end2 = span2["start"], span2["end"]

    # Calculate intersection
    inter_start = max(start1, start2)
    inter_end = min(end1, end2)
    intersection = max(0, inter_end - inter_start)

    # Calculate overlap ratio relative to ground truth span
    gt_length = end1 - start1
    if gt_length == 0:
        return 1.0 if intersection > 0 else 0.0

    return intersection / gt_length


def compute_boundary_accuracy(
    ev, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Boundary-only comparison for spans.
    For SPAN_SELECTION annotation type.

    Only compares start/end positions:
    - Score 0.5 for matching start OR end
    - Score 1.0 for matching both start AND end

    Args:
        gt: Ground truth span(s)
        pred: Predicted span(s)
        parameters: Optional parameters
            - tolerance: Boundary tolerance in characters (default: 0)
            - mode: 'strict' or 'lenient' matching (default: 'strict')

    Returns:
        Score (0.0-1.0) based on boundary matching
    """
    if parameters is None:
        parameters = {}

    tolerance = parameters.get("tolerance", 0)
    mode = parameters.get("mode", "strict")

    # Parse spans
    gt_spans = ev._parse_spans(gt)
    pred_spans = ev._parse_spans(pred)

    if not gt_spans and not pred_spans:
        return 1.0
    if not gt_spans or not pred_spans:
        return 0.0

    def boundary_fn(gt_span, pred_span):
        return ev._calculate_boundary_score(gt_span, pred_span, tolerance)

    if mode == "lenient":
        # Return max score across any label-compatible match
        best_scores = []
        for gt_span in gt_spans:
            best_score = 0.0
            for pred_span in pred_spans:
                if ev._spans_label_compatible(gt_span, pred_span):
                    score = boundary_fn(gt_span, pred_span)
                    best_score = max(best_score, score)
            best_scores.append(best_score)
        return max(best_scores) if best_scores else 0.0
    else:  # strict - use optimal bipartite matching
        total_score = ev._optimal_span_matching(gt_spans, pred_spans, boundary_fn)
        return total_score / len(gt_spans) if gt_spans else 0.0


def calculate_boundary_score(
    ev, gt_span: Dict[str, Any], pred_span: Dict[str, Any], tolerance: int
) -> float:
    """
    Calculate boundary matching score between two spans.

    Returns:
        0.0: No boundaries match
        0.5: One boundary matches (start OR end)
        1.0: Both boundaries match (start AND end)
    """
    start_match = abs(gt_span["start"] - pred_span["start"]) <= tolerance
    end_match = abs(gt_span["end"] - pred_span["end"]) <= tolerance

    if start_match and end_match:
        return 1.0
    elif start_match or end_match:
        return 0.5
    else:
        return 0.0
