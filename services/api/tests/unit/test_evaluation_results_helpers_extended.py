"""
Unit tests for evaluation results internal helpers.

Targets: routers/evaluations/results.py — _get_task_preview, _metric_display_name,
_build_field_results, and Pydantic models.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TestGetTaskPreview:
    """Test _get_task_preview helper."""

    def test_none_data(self):
        from routers.evaluations.results import _get_task_preview
        assert _get_task_preview(None) == ""

    def test_empty_dict(self):
        from routers.evaluations.results import _get_task_preview
        assert _get_task_preview({}) == ""

    def test_input_key(self):
        from routers.evaluations.results import _get_task_preview
        assert _get_task_preview({"input": "Hello world"}) == "Hello world"

    def test_text_key(self):
        from routers.evaluations.results import _get_task_preview
        assert _get_task_preview({"text": "Some text"}) == "Some text"

    def test_question_key(self):
        from routers.evaluations.results import _get_task_preview
        assert _get_task_preview({"question": "What is X?"}) == "What is X?"

    def test_prompt_key(self):
        from routers.evaluations.results import _get_task_preview
        assert _get_task_preview({"prompt": "Explain Y"}) == "Explain Y"

    def test_content_key(self):
        from routers.evaluations.results import _get_task_preview
        assert _get_task_preview({"content": "Document content"}) == "Document content"

    def test_priority_order_input_first(self):
        from routers.evaluations.results import _get_task_preview
        data = {"input": "input val", "text": "text val", "question": "q val"}
        assert _get_task_preview(data) == "input val"

    def test_truncation_at_100_chars(self):
        from routers.evaluations.results import _get_task_preview
        long_text = "a" * 200
        result = _get_task_preview({"input": long_text})
        assert len(result) == 100

    def test_fallback_to_first_string_value(self):
        from routers.evaluations.results import _get_task_preview
        data = {"custom_field": "custom value"}
        assert _get_task_preview(data) == "custom value"

    def test_fallback_string_truncation(self):
        from routers.evaluations.results import _get_task_preview
        data = {"custom_field": "x" * 200}
        result = _get_task_preview(data)
        assert len(result) == 100

    def test_non_string_values_skipped(self):
        from routers.evaluations.results import _get_task_preview
        data = {"count": 42, "items": [1, 2, 3], "name": "test"}
        result = _get_task_preview(data)
        assert result == "test"

    def test_all_non_string_returns_empty(self):
        from routers.evaluations.results import _get_task_preview
        data = {"count": 42, "items": [1, 2, 3]}
        assert _get_task_preview(data) == ""


class TestMetricDisplayName:
    """Test _metric_display_name helper."""

    def test_basic_metric_name(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"accuracy": 0.95},
            field_name="answer",
        )
        result = _metric_display_name(record)
        assert result == "Accuracy"

    def test_underscore_to_title(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"exact_match": 0.88},
            field_name="answer",
        )
        result = _metric_display_name(record)
        assert result == "Exact Match"

    def test_skip_raw_score_key(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"raw_score": 0.5, "f1_score": 0.9},
            field_name="answer",
        )
        result = _metric_display_name(record)
        assert result == "F1 Score"

    def test_skip_error_key(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"error": True, "bleu": 0.75},
            field_name="answer",
        )
        result = _metric_display_name(record)
        assert result == "Bleu"

    def test_skip_details_suffix(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"llm_judge_details": {"x": 1}, "llm_judge_custom": 0.8},
            field_name="answer",
        )
        result = _metric_display_name(record)
        assert result == "Llm Judge Custom"

    def test_skip_raw_suffix(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"metric_raw": "raw data", "metric_score": 0.7},
            field_name="answer",
        )
        result = _metric_display_name(record)
        assert result == "Metric Score"

    def test_skip_passed_suffix(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"test_passed": True, "rouge": 0.6},
            field_name="answer",
        )
        result = _metric_display_name(record)
        assert result == "Rouge"

    def test_no_metrics_falls_to_field_name(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(metrics=None, field_name="custom_field")
        result = _metric_display_name(record)
        assert result == "custom_field"

    def test_empty_metrics_falls_to_field_name(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(metrics={}, field_name="answer")
        result = _metric_display_name(record)
        assert result == "answer"

    def test_no_numeric_metrics_falls_to_field_name(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"description": "text", "notes": "more text"},
            field_name="answer",
        )
        result = _metric_display_name(record)
        assert result == "answer"

    def test_none_field_name_returns_evaluation(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(metrics={}, field_name=None)
        result = _metric_display_name(record)
        assert result == "Evaluation"

    def test_all_skip_keys_no_field_name(self):
        from routers.evaluations.results import _metric_display_name
        record = SimpleNamespace(
            metrics={"raw_score": 0.5, "error": True, "metric_details": {}},
            field_name=None,
        )
        result = _metric_display_name(record)
        assert result == "Evaluation"


class TestBuildFieldResults:
    """Test _build_field_results helper."""

    def test_empty_records(self):
        from routers.evaluations.results import _build_field_results
        assert _build_field_results([]) == []

    def test_single_metric(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics={"accuracy": 0.95},
            field_name="answer",
            error_message=None,
            passed=True,
        )
        results = _build_field_results([record])
        assert len(results) == 1
        assert results[0].field_name == "answer"
        assert len(results[0].metrics) == 1
        assert results[0].metrics[0].metric_name == "accuracy"
        assert results[0].metrics[0].value == 0.95

    def test_error_record(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics={"error": True},
            field_name="answer",
            error_message="Model failed",
            passed=None,
        )
        results = _build_field_results([record])
        assert len(results) == 1
        assert results[0].metrics[0].metric_name == "error"
        assert results[0].metrics[0].display_name == "Error"
        assert "Model failed" in results[0].metrics[0].details["error"]

    def test_error_with_no_error_message(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics={"error": True},
            field_name="answer",
            error_message=None,
            passed=None,
        )
        results = _build_field_results([record])
        assert results[0].metrics[0].details["error"] == "Evaluation failed"

    def test_multiple_metrics(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics={"accuracy": 0.9, "f1": 0.85, "raw_score": 0.8},
            field_name="answer",
            error_message=None,
            passed=True,
        )
        results = _build_field_results([record])
        # raw_score should be skipped
        metric_names = [m.metric_name for m in results[0].metrics]
        assert "accuracy" in metric_names
        assert "f1" in metric_names
        assert "raw_score" not in metric_names

    def test_skip_details_suffix_metrics(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics={"bleu": 0.75, "bleu_details": {"n-gram": 4}},
            field_name="answer",
            error_message=None,
            passed=True,
        )
        results = _build_field_results([record])
        metric_names = [m.metric_name for m in results[0].metrics]
        assert "bleu" in metric_names
        assert "bleu_details" not in metric_names

    def test_metric_with_details(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics={"rouge": 0.65, "rouge_details": {"precision": 0.7}},
            field_name="answer",
            error_message=None,
            passed=True,
        )
        results = _build_field_results([record])
        rouge_metric = results[0].metrics[0]
        assert rouge_metric.details == {"precision": 0.7}

    def test_none_metrics(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics=None,
            field_name="answer",
            error_message=None,
            passed=None,
        )
        results = _build_field_results([record])
        # No metrics extracted, so empty result
        assert len(results) == 0

    def test_none_field_name_defaults(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics={"accuracy": 0.9},
            field_name=None,
            error_message=None,
            passed=True,
        )
        results = _build_field_results([record])
        assert results[0].field_name == "field"
        assert results[0].display_name == "Evaluation"

    def test_multiple_records(self):
        from routers.evaluations.results import _build_field_results
        records = [
            SimpleNamespace(
                metrics={"accuracy": 0.9},
                field_name="answer1",
                error_message=None,
                passed=True,
            ),
            SimpleNamespace(
                metrics={"bleu": 0.7},
                field_name="answer2",
                error_message=None,
                passed=True,
            ),
        ]
        results = _build_field_results(records)
        assert len(results) == 2
        assert results[0].field_name == "answer1"
        assert results[1].field_name == "answer2"

    def test_passed_is_none_for_error_records(self):
        from routers.evaluations.results import _build_field_results
        record = SimpleNamespace(
            metrics={"accuracy": 0.9, "error": True},
            field_name="answer",
            error_message="Some error",
            passed=True,
        )
        results = _build_field_results([record])
        # Should detect error and return error metric
        assert results[0].metrics[0].metric_name == "error"


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
