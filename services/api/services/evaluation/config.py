"""
Answer type detection and evaluation configuration system for BenGER.

This module implements the comprehensive evaluation configuration system (Issue #483) that:
- Automatically detects answer types from Label Studio label_config XML
- Maps answer types to applicable evaluation methods
- Manages project evaluation configurations
- Supports configurable metric parameters with sensible defaults
"""

import logging
import xml.etree.ElementTree as ET
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class AnswerType(Enum):
    """Enumeration of all possible answer types detected from label configurations."""

    BINARY = "binary"  # Yes/No, True/False
    SINGLE_CHOICE = "single_choice"  # Radio buttons, single selection
    MULTIPLE_CHOICE = "multiple_choice"  # Checkboxes, multiple selections
    NUMERIC = "numeric"  # Number input, rating scales
    RATING = "rating"  # Star ratings, Likert scales
    RANKING = "ranking"  # Order/rank items
    SHORT_TEXT = "short_text"  # Single line text, <50 words
    LONG_TEXT = "long_text"  # Multi-line text, essays
    STRUCTURED_TEXT = "structured_text"  # JSON, XML, formatted output
    SPAN_SELECTION = "span_selection"  # Text highlighting, NER
    TAXONOMY = "taxonomy"  # Hierarchical classification
    CUSTOM = "custom"  # Unknown/custom control types


# Single source of truth for answer type to evaluation metrics mapping
# Flat list structure - all metrics available for each answer type
# The evaluation pipeline handles routing to appropriate evaluator (deterministic vs LLM judge)
ANSWER_TYPE_TO_METRICS = {
    AnswerType.BINARY: [
        "exact_match",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "cohen_kappa",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.SINGLE_CHOICE: [
        "exact_match",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "confusion_matrix",
        "cohen_kappa",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.MULTIPLE_CHOICE: [
        "jaccard",
        "hamming_loss",
        "subset_accuracy",
        "precision",
        "recall",
        "f1",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.NUMERIC: [
        "mae",
        "rmse",
        "mape",
        "r2",
        "correlation",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.RATING: [
        "mae",
        "rmse",
        "correlation",
        "cohen_kappa",
        "weighted_kappa",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.RANKING: [
        "spearman_correlation",
        "kendall_tau",
        "ndcg",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.SHORT_TEXT: [
        "exact_match",
        "bleu",
        "rouge",
        "edit_distance",
        "chrf",
        "moverscore",
        "semantic_similarity",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.LONG_TEXT: [
        "bleu",
        "rouge",
        "meteor",
        "chrf",
        "bertscore",
        "moverscore",
        "factcc",
        "qags",
        "semantic_similarity",
        "coherence",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.STRUCTURED_TEXT: [
        "json_accuracy",
        "schema_validation",
        "field_accuracy",
        "semantic_similarity",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.SPAN_SELECTION: [
        "span_exact_match",
        "iou",
        "partial_match",
        "boundary_accuracy",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.TAXONOMY: [
        "hierarchical_f1",
        "path_accuracy",
        "lca_accuracy",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
    AnswerType.CUSTOM: [
        # For unknown types, show all available metrics
        "exact_match",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "cohen_kappa",
        "jaccard",
        "hamming_loss",
        "subset_accuracy",
        "confusion_matrix",
        "mae",
        "rmse",
        "mape",
        "r2",
        "correlation",
        "weighted_kappa",
        "spearman_correlation",
        "kendall_tau",
        "ndcg",
        "bleu",
        "rouge",
        "meteor",
        "chrf",
        "bertscore",
        "moverscore",
        "factcc",
        "qags",
        "semantic_similarity",
        "edit_distance",
        "coherence",
        "json_accuracy",
        "schema_validation",
        "token_f1",
        "span_exact_match",
        "iou",
        "map",
        "hierarchical_f1",
        "llm_judge_classic",
        "llm_judge_custom",
    ],
}

# Extension point: extended package can register additional metrics per answer type
_extended_metrics: dict[str, list[str]] = {}


def register_extended_metrics(answer_type: str, metrics: list[str]):
    """Register additional metrics for an answer type (called by benger_extended)."""
    _extended_metrics.setdefault(answer_type, []).extend(metrics)


def get_metrics_for_answer_type(answer_type: AnswerType) -> list[str]:
    """Get all metrics for an answer type, including extended metrics."""
    base = ANSWER_TYPE_TO_METRICS.get(answer_type, [])
    extended = _extended_metrics.get(answer_type.value, [])
    return base + extended


class AnswerTypeDetector:
    """Detects answer types from Label Studio label configuration XML."""

    def __init__(self, label_config: str = ""):
        """
        Initialize the detector with a label configuration.

        Args:
            label_config: Label Studio configuration XML string
        """
        self.label_config = label_config

    def detect_answer_types(self) -> List[Dict[str, Any]]:
        """
        Detect answer types from the configured label configuration.

        Returns:
            List of detected answer types with their metadata
        """
        return self.detect_from_label_config(self.label_config)

    @staticmethod
    def detect_from_label_config(label_config: str) -> List[Dict[str, Any]]:
        """
        Detect answer types from Label Studio label configuration XML.

        Args:
            label_config: Label Studio configuration XML string

        Returns:
            List of detected answer types with their metadata
        """
        if not label_config:
            return []

        detected_types = []

        try:
            # Parse the XML configuration
            root = ET.fromstring(label_config)

            # Process each control tag in the configuration
            for element in root.iter():
                tag_name = element.tag.lower()
                name = element.get('name', '')
                to_name = element.get('toName', '')

                # Detect answer type based on control tag
                answer_type = AnswerTypeDetector._detect_type_from_tag(element)

                if answer_type:
                    result_dict = {
                        "name": name or f"{tag_name}_{len(detected_types)}",
                        "type": answer_type.value,
                        "tag": tag_name,
                        "to_name": to_name,
                        "element_attrs": dict(element.attrib),
                    }

                    # Add choice values for choice-based controls
                    if tag_name == "choices":
                        choice_elements = list(element.findall('.//Choice'))
                        choices = [c.get('value', '') for c in choice_elements]
                        result_dict["choices"] = choices

                    detected_types.append(result_dict)

            # If no specific types detected, mark as custom
            if not detected_types:
                detected_types.append(
                    {
                        "name": "custom_field",
                        "type": AnswerType.CUSTOM.value,
                        "tag": "unknown",
                        "to_name": "",
                        "element_attrs": {},
                    }
                )

        except ET.ParseError as e:
            logger.warning(f"Failed to parse label config XML: {e}")
            detected_types.append(
                {
                    "name": "parse_error",
                    "type": AnswerType.CUSTOM.value,
                    "tag": "error",
                    "to_name": "",
                    "element_attrs": {"error": str(e)},
                }
            )
        except Exception as e:
            logger.error(f"Unexpected error detecting answer types: {e}")
            detected_types.append(
                {
                    "name": "error",
                    "type": AnswerType.CUSTOM.value,
                    "tag": "error",
                    "to_name": "",
                    "element_attrs": {"error": str(e)},
                }
            )

        return detected_types

    @staticmethod
    def _detect_type_from_tag(element: ET.Element) -> Optional[AnswerType]:
        """
        Detect answer type from a specific XML element/tag.

        Args:
            element: XML element from label configuration

        Returns:
            Detected AnswerType or None
        """
        tag_name = element.tag.lower()

        # Check for specific control tags
        if tag_name == "choices":
            # Check if it's single or multiple choice
            choice_type = element.get('choice', 'single')
            multiple = element.get('multiple', 'false').lower() == 'true'

            if multiple or choice_type == 'multiple':
                return AnswerType.MULTIPLE_CHOICE
            else:
                # Check if it's binary (only 2 choices)
                choice_elements = list(element.findall('.//Choice'))
                if len(choice_elements) == 2:
                    # Check if choices look like binary options
                    values = [c.get('value', '').lower() for c in choice_elements]
                    binary_pairs = [
                        {'yes', 'no'},
                        {'true', 'false'},
                        {'ja', 'nein'},
                        {'1', '0'},
                        {'correct', 'incorrect'},
                        {'right', 'wrong'},
                    ]
                    if set(values) in binary_pairs:
                        return AnswerType.BINARY
                return AnswerType.SINGLE_CHOICE

        elif tag_name == "textarea":
            # Check max length or other hints
            max_length = element.get('maxSubmissions', '')
            rows = element.get('rows', '1')

            try:
                if int(rows) <= 5 or (max_length and int(max_length) < 200):
                    return AnswerType.SHORT_TEXT
            except (ValueError, TypeError):
                pass
            return AnswerType.LONG_TEXT

        elif tag_name == "text":
            # Plain text display, might be for text classification
            return None  # Not an input field

        elif tag_name == "number":
            return AnswerType.NUMERIC

        elif tag_name == "rating":
            return AnswerType.RATING

        elif tag_name == "ranker":
            return AnswerType.RANKING

        elif tag_name == "taxonomy":
            return AnswerType.TAXONOMY

        elif tag_name == "labels":
            # Used for span selection/NER
            return AnswerType.SPAN_SELECTION

        elif tag_name == "textfield":
            # Single line text input
            return AnswerType.SHORT_TEXT

        elif tag_name == "json":
            return AnswerType.STRUCTURED_TEXT

        return None


def lookup_available_methods(answer_types: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Look up all available evaluation methods for detected answer types.

    Args:
        answer_types: List of detected answer types

    Returns:
        Dictionary mapping field names to available evaluation methods
    """
    available_methods = {}

    for answer_type_info in answer_types:
        field_name = answer_type_info["name"]
        answer_type_str = answer_type_info["type"]

        # Convert string to enum
        try:
            answer_type = AnswerType(answer_type_str)
        except ValueError:
            answer_type = AnswerType.CUSTOM

        # Get metrics for this answer type (core + extended)
        metrics = get_metrics_for_answer_type(answer_type)

        available_methods[field_name] = {
            "type": answer_type.value,
            "tag": answer_type_info.get("tag", "unknown"),
            "to_name": answer_type_info.get("to_name", ""),
            "available_metrics": metrics,  # Flat list of all available metrics
            "enabled_metrics": [],  # Empty until user selects
        }

    return available_methods


def update_project_evaluation_config(
    project_id: str,
    label_config: str,
    existing_config: Optional[Dict[str, Any]] = None,
    label_config_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update or create evaluation configuration for a project based on its label_config.

    Args:
        project_id: The project ID
        label_config: Label Studio configuration XML
        existing_config: Existing evaluation config if any
        label_config_version: Version of the label config this was generated for

    Returns:
        Updated evaluation configuration
    """
    from datetime import datetime

    # Step 1: Detect answer types from label_config
    answer_types = AnswerTypeDetector.detect_from_label_config(label_config)

    # Step 2: Lookup all available methods for these types
    available_methods = lookup_available_methods(answer_types)

    # Step 3: Preserve existing selections if config exists
    selected_methods = {}
    if existing_config and "selected_methods" in existing_config:
        # Preserve selections for fields that still exist
        for field_name, selections in existing_config["selected_methods"].items():
            if field_name in available_methods:
                selected_methods[field_name] = selections

    # Step 4: Build the complete configuration
    evaluation_config = {
        "detected_answer_types": answer_types,
        "available_methods": available_methods,
        "selected_methods": selected_methods,
        "last_updated": datetime.now().isoformat(),
        "label_config_version": label_config_version,  # Track which version this was generated for
    }

    # Preserve extra keys from existing config (e.g. evaluation_configs)
    if existing_config:
        preserved_keys = set(existing_config.keys()) - set(evaluation_config.keys())
        for key in preserved_keys:
            evaluation_config[key] = existing_config[key]

    return evaluation_config


def get_selected_metrics_for_field(evaluation_config: Dict[str, Any], field_name: str) -> List[str]:
    """
    Get the selected evaluation metrics for a specific field.

    Args:
        evaluation_config: Project evaluation configuration
        field_name: Name of the field to get metrics for

    Returns:
        List of selected metric names
    """
    if not evaluation_config or "selected_methods" not in evaluation_config:
        return []

    field_selections = evaluation_config["selected_methods"].get(field_name, {})
    # Support both old format (dict with "metrics" key) and new format (list directly)
    if isinstance(field_selections, list):
        return field_selections
    return field_selections.get("metrics", [])


def validate_metric_selection(answer_type: str, metric_name: str) -> bool:
    """
    Validate if a metric is applicable for a given answer type.

    Args:
        answer_type: The answer type string
        metric_name: Name of the metric

    Returns:
        True if the metric is valid for the answer type
    """
    try:
        answer_type_enum = AnswerType(answer_type)
    except ValueError:
        answer_type_enum = AnswerType.CUSTOM

    available_metrics = get_metrics_for_answer_type(answer_type_enum)
    return metric_name in available_metrics


def get_available_methods_for_project(label_config: str) -> Dict[str, Any]:
    """
    Get available evaluation methods for a project based on its label configuration

    This function provides the interface expected by tests and serves as a wrapper
    around the core evaluation configuration logic.

    Args:
        label_config: Label Studio XML configuration string

    Returns:
        Dictionary containing detected answer types and available methods
    """
    if not label_config or not label_config.strip():
        return {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {},
            "last_updated": None,
        }

    try:
        detector = AnswerTypeDetector(label_config)
        answer_types = detector.detect_answer_types()

        # Filter out error entries for test compatibility
        valid_answer_types = [
            at for at in answer_types if at.get('tag') not in ['error', 'unknown']
        ]

        # If only error entries, return empty results
        if not valid_answer_types and answer_types:
            return {
                "detected_answer_types": [],
                "available_methods": {},
                "selected_methods": {},
                "last_updated": None,
            }

        available_methods = lookup_available_methods(valid_answer_types or answer_types)

        return {
            "detected_answer_types": valid_answer_types or answer_types,
            "available_methods": available_methods,
            "selected_methods": {},  # Empty by default
            "last_updated": None,
        }
    except Exception as e:
        logger.error(f"Error processing label configuration: {e}")
        return {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {},
            "last_updated": None,
        }


# Metric Parameter Configuration System
# Supports both simple ("bleu") and advanced ({"name": "bleu", "parameters": {...}}) formats


def get_metric_defaults(metric_name: str) -> Dict[str, Any]:
    """
    Get default parameters for a metric.

    Args:
        metric_name: Name of the metric

    Returns:
        Dictionary of default parameters
    """
    defaults = {
        "bleu": {
            "max_order": 4,
            "weights": [0.25, 0.25, 0.25, 0.25],
            "smoothing": "method1",
        },
        "rouge": {"variant": "rougeL", "use_stemmer": True},
        "meteor": {"alpha": 0.9, "beta": 3.0, "gamma": 0.5},
        "chrf": {"char_order": 6, "word_order": 0, "beta": 2},
    }
    return defaults.get(metric_name, {})


def normalize_metric_selection(selection: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize metric selection to standard format with parameters.

    Supports two formats:
    1. Simple: "bleu" -> {"name": "bleu", "parameters": {...defaults...}}
    2. Advanced: {"name": "bleu", "parameters": {"max_order": 2}}
       -> {"name": "bleu", "parameters": {merged with defaults}}

    Args:
        selection: Either a metric name string or dict with name and parameters

    Returns:
        Normalized dict with name and parameters (merged with defaults)
    """
    if isinstance(selection, str):
        # Simple format: use defaults
        return {"name": selection, "parameters": get_metric_defaults(selection)}

    # Advanced format: merge with defaults
    metric_name = selection.get("name", "")
    user_params = selection.get("parameters", {})

    # Get defaults and merge with user parameters
    defaults = get_metric_defaults(metric_name)
    merged_params = {**defaults, **user_params}

    return {"name": metric_name, "parameters": merged_params}


def normalize_selected_methods(selected_methods: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize all selected methods to include parameters.

    Args:
        selected_methods: Project's selected_methods configuration

    Returns:
        Normalized configuration with all metrics having parameters
    """
    normalized = {}

    for field_name, selections in selected_methods.items():
        # Handle both list format (new) and dict format (legacy)
        if isinstance(selections, list):
            # New flat format: list of metric names or metric configs
            normalized[field_name] = {
                "metrics": [normalize_metric_selection(m) for m in selections]
            }
        elif isinstance(selections, dict):
            # Legacy format with "automated" key or new format with "metrics" key
            metrics = selections.get("metrics", selections.get("automated", []))
            if isinstance(metrics, list):
                normalized[field_name] = {
                    "metrics": [normalize_metric_selection(m) for m in metrics]
                }
            else:
                normalized[field_name] = {"metrics": []}
        else:
            normalized[field_name] = {"metrics": []}

    return normalized


def get_metric_parameters(
    evaluation_config: Dict[str, Any], field_name: str, metric_name: str
) -> Dict[str, Any]:
    """
    Get the configured parameters for a specific metric.

    Args:
        evaluation_config: Project evaluation configuration
        field_name: Name of the field
        metric_name: Name of the metric

    Returns:
        Parameters dict (defaults if not configured)
    """
    if not evaluation_config or "selected_methods" not in evaluation_config:
        return get_metric_defaults(metric_name)

    field_selections = evaluation_config["selected_methods"].get(field_name, {})

    # Handle both list format and dict format
    if isinstance(field_selections, list):
        metrics = field_selections
    else:
        metrics = field_selections.get("metrics", field_selections.get("automated", []))

    # Find the metric in the list
    for metric in metrics:
        if isinstance(metric, dict) and metric.get("name") == metric_name:
            return metric.get("parameters", get_metric_defaults(metric_name))
        elif isinstance(metric, str) and metric == metric_name:
            return get_metric_defaults(metric_name)

    # Not found, return defaults
    return get_metric_defaults(metric_name)
