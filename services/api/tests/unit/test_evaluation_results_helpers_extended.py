"""
Unit tests for evaluation results internal helpers.

"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TestEvaluationConfigHelper:
    """Test _derive_evaluation_configs_from_selected_methods helper."""

    def test_empty_selected_methods(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        result = _derive_evaluation_configs_from_selected_methods({})
        assert result == []

    def test_single_field_single_metric(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["bleu"],
                "field_mapping": {
                    "prediction_field": "gen_answer",
                    "reference_field": "ref_answer",
                },
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 1
        assert result[0]["metric"] == "bleu"
        assert result[0]["prediction_fields"] == ["gen_answer"]
        assert result[0]["reference_fields"] == ["ref_answer"]
        assert result[0]["enabled"] is True

    def test_multiple_metrics(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["bleu", "rouge"],
                "field_mapping": {},
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 2
        metric_names = [r["metric"] for r in result]
        assert "bleu" in metric_names
        assert "rouge" in metric_names

    def test_dict_format_metric_with_parameters(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": [{"name": "bleu", "parameters": {"max_order": 2}}],
                "field_mapping": {},
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 1
        assert result[0]["metric"] == "bleu"
        assert result[0]["metric_parameters"] == {"max_order": 2}

    def test_non_dict_selection_skipped(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": "not a dict"
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert result == []

    def test_no_field_mapping_defaults_to_field_name(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["exact_match"],
                "field_mapping": {},
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert result[0]["prediction_fields"] == ["answer"]
        assert result[0]["reference_fields"] == ["answer"]

    def test_empty_metric_name_skipped(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": [{"name": "", "parameters": {}}],
                "field_mapping": {},
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert result == []

    def test_display_name_formatting(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["exact_match"],
                "field_mapping": {},
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert result[0]["display_name"] == "Exact Match"

    def test_multiple_fields(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {"automated": ["bleu"], "field_mapping": {}},
            "summary": {"automated": ["rouge"], "field_mapping": {}},
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 2


class TestExtractMetricName:
    """Test extract_metric_name helper."""

    def test_string_input(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name("bleu") == "bleu"

    def test_dict_input(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name({"name": "rouge", "parameters": {}}) == "rouge"

    def test_dict_without_name(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name({"parameters": {}}) == ""

    def test_none_input(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name(None) == ""

    def test_int_input(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name(42) == ""

    def test_empty_string(self):
        from routers.evaluations.helpers import extract_metric_name
        assert extract_metric_name("") == ""
