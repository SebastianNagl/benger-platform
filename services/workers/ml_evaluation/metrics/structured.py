"""Structured-data metric-family computations.

Covers json_accuracy / schema_validation / field_accuracy / partial_match.
Extracted from ``SampleEvaluator``. ``partial_match`` reaches into the span
family via ``ev._parse_spans`` / ``ev._spans_label_compatible`` /
``ev._calculate_span_overlap`` / ``ev._optimal_span_matching`` (their
canonical home), and the JSON helpers (``parse_json`` / ``json_field_accuracy``
/ ``compare_json_fields``) live here.
"""

import json
from typing import Any, Dict, Optional

import jsonschema


def compute_structured_metric(
    ev, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Compute structured data metrics for JSON and schema validation.
    """
    if parameters is None:
        parameters = {}

    if metric_name == "json_accuracy":
        # Parse both as JSON and compare
        try:
            gt_json = ev._parse_json(gt)
            pred_json = ev._parse_json(pred)

            if gt_json is None and pred_json is None:
                return 1.0  # Both not JSON
            if gt_json is None or pred_json is None:
                return 0.0  # One is JSON, other is not

            # Compare JSON structures
            return ev._json_field_accuracy(gt_json, pred_json)
        except Exception:
            return 0.0

    elif metric_name == "schema_validation":
        # Validate prediction against a schema
        schema = parameters.get("schema")
        if not schema:
            # No schema provided, just check if valid JSON
            try:
                pred_json = ev._parse_json(pred)
                return 1.0 if pred_json is not None else 0.0
            except Exception:
                return 0.0

        try:
            pred_json = ev._parse_json(pred)
            if pred_json is None:
                return 0.0
            jsonschema.validate(pred_json, schema)
            return 1.0  # Valid
        except jsonschema.ValidationError:
            return 0.0  # Invalid
        except jsonschema.SchemaError as e:
            raise RuntimeError(f"Invalid JSON schema: {e}")
        except Exception as e:
            raise RuntimeError(f"Schema validation failed: {e}")

    return 0.0


def parse_json(ev, value: Any) -> Optional[Any]:
    """Parse a value as JSON"""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def json_field_accuracy(ev, gt_json: Any, pred_json: Any) -> float:
    """Calculate field-level accuracy for JSON structures"""
    if type(gt_json) != type(pred_json):
        return 0.0

    if isinstance(gt_json, dict):
        if not gt_json:
            return 1.0 if not pred_json else 0.0

        all_keys = set(gt_json.keys()) | set(pred_json.keys())
        matching_keys = 0
        for key in all_keys:
            if key in gt_json and key in pred_json:
                if gt_json[key] == pred_json[key]:
                    matching_keys += 1
                elif isinstance(gt_json[key], (dict, list)):
                    matching_keys += ev._json_field_accuracy(gt_json[key], pred_json[key])
        return matching_keys / len(all_keys) if all_keys else 1.0

    elif isinstance(gt_json, list):
        if not gt_json:
            return 1.0 if not pred_json else 0.0
        if len(gt_json) != len(pred_json):
            return 0.0
        matching = sum(1 for g, p in zip(gt_json, pred_json) if g == p)
        return matching / len(gt_json)

    else:
        return 1.0 if gt_json == pred_json else 0.0


def compute_field_accuracy(
    ev, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    JSON field-level comparison with nested support.
    For STRUCTURED_TEXT annotation type.

    Compares JSON fields between prediction and ground truth with support for
    nested objects and path matching. Returns accuracy as percentage of matching fields.

    Args:
        gt: Ground truth JSON (dict/string)
        pred: Predicted JSON (dict/string)
        parameters: Optional parameters
            - ignore_keys: List of keys to ignore in comparison (default: [])
            - strict_types: If True, enforce type matching (default: False)

    Returns:
        Accuracy score (0.0-1.0) representing percentage of matching fields
    """
    if parameters is None:
        parameters = {}

    ignore_keys = set(parameters.get("ignore_keys", []))
    strict_types = parameters.get("strict_types", False)

    # Parse as JSON
    gt_json = ev._parse_json(gt)
    pred_json = ev._parse_json(pred)

    # Handle non-JSON cases
    if gt_json is None and pred_json is None:
        return 1.0
    if gt_json is None or pred_json is None:
        return 0.0

    return ev._compare_json_fields(gt_json, pred_json, ignore_keys, strict_types)


def compare_json_fields(
    ev, gt_obj: Any, pred_obj: Any, ignore_keys: set, strict_types: bool, path: str = ""
) -> float:
    """Recursively compare JSON fields with path tracking"""
    # Type mismatch
    if type(gt_obj) != type(pred_obj):
        return 0.0

    if isinstance(gt_obj, dict):
        if not gt_obj and not pred_obj:
            return 1.0

        # Get all keys (excluding ignored)
        all_keys = (set(gt_obj.keys()) | set(pred_obj.keys())) - ignore_keys
        if not all_keys:
            return 1.0

        matching_score = 0.0
        for key in all_keys:
            key_path = f"{path}.{key}" if path else key

            # Both missing
            if key not in gt_obj and key not in pred_obj:
                matching_score += 1.0
            # One missing
            elif key not in gt_obj or key not in pred_obj:
                matching_score += 0.0
            # Both present
            else:
                gt_val = gt_obj[key]
                pred_val = pred_obj[key]

                # Type checking if strict
                if strict_types and type(gt_val) != type(pred_val):
                    matching_score += 0.0
                # Recursive comparison for nested structures
                elif isinstance(gt_val, (dict, list)):
                    matching_score += ev._compare_json_fields(
                        gt_val, pred_val, ignore_keys, strict_types, key_path
                    )
                # Direct value comparison
                else:
                    matching_score += 1.0 if gt_val == pred_val else 0.0

        return matching_score / len(all_keys)

    elif isinstance(gt_obj, list):
        if not gt_obj and not pred_obj:
            return 1.0
        if len(gt_obj) != len(pred_obj):
            return 0.0

        matching_score = sum(
            ev._compare_json_fields(g, p, ignore_keys, strict_types, f"{path}[{i}]")
            for i, (g, p) in enumerate(zip(gt_obj, pred_obj))
        )
        return matching_score / len(gt_obj)

    else:
        # Primitive values
        return 1.0 if gt_obj == pred_obj else 0.0


def compute_partial_match(
    ev, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Fuzzy span matching with partial credit.
    For SPAN_SELECTION annotation type.

    Calculates partial overlap between spans with partial credit based on
    character-level overlap. Not just binary match.

    Args:
        gt: Ground truth span(s)
        pred: Predicted span(s)
        parameters: Optional parameters
            - min_overlap: Minimum overlap to consider (default: 0.0)
            - mode: 'best' or 'average' matching (default: 'best')

    Returns:
        Score (0.0-1.0) based on character-level overlap
    """
    if parameters is None:
        parameters = {}

    min_overlap = parameters.get("min_overlap", 0.0)
    mode = parameters.get("mode", "best")

    # Parse spans
    gt_spans = ev._parse_spans(gt)
    pred_spans = ev._parse_spans(pred)

    if not gt_spans and not pred_spans:
        return 1.0
    if not gt_spans or not pred_spans:
        return 0.0

    if mode == "average":
        # Average overlap with all label-compatible predicted spans per GT span
        overlap_scores = []
        for gt_span in gt_spans:
            compatible = [p for p in pred_spans if ev._spans_label_compatible(gt_span, p)]
            if not compatible:
                overlap_scores.append(0.0)
                continue
            total_overlap = sum(
                ev._calculate_span_overlap(gt_span, pred_span) for pred_span in compatible
            )
            avg_overlap = total_overlap / len(compatible)
            overlap_scores.append(avg_overlap if avg_overlap >= min_overlap else 0.0)
        return sum(overlap_scores) / len(overlap_scores) if overlap_scores else 0.0

    # Default: optimal bipartite matching
    def overlap_fn(gt_span, pred_span):
        overlap = ev._calculate_span_overlap(gt_span, pred_span)
        return overlap if overlap >= min_overlap else 0.0

    total_overlap = ev._optimal_span_matching(gt_spans, pred_spans, overlap_fn)
    return total_overlap / len(gt_spans) if gt_spans else 0.0
