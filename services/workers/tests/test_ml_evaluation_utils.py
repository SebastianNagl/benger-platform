"""Tests for ml_evaluation/utils.py - pure utility functions.

Covers:
- safe_divide
- normalize_metric_name
- format_metrics_for_display
- validate_evaluation_request
- create_evaluation_metadata
- extract_task_type_from_label_config
- merge_evaluation_results
- export_evaluation_results
- filter_tasks_with_model_predictions
- EvaluationTimer
"""

import json
import os
import sys
import tempfile
import time

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.utils import (
    EvaluationTimer,
    create_evaluation_metadata,
    export_evaluation_results,
    extract_task_type_from_label_config,
    filter_tasks_with_model_predictions,
    format_metrics_for_display,
    merge_evaluation_results,
    normalize_metric_name,
    safe_divide,
    validate_evaluation_request,
)


# ---------------------------------------------------------------------------
# safe_divide
# ---------------------------------------------------------------------------

class TestSafeDivide:

    def test_normal_division(self):
        assert safe_divide(10, 2) == 5.0

    def test_divide_by_zero_default(self):
        assert safe_divide(10, 0) == 0.0

    def test_divide_by_zero_custom_default(self):
        assert safe_divide(10, 0, default=-1.0) == -1.0

    def test_zero_numerator(self):
        assert safe_divide(0, 5) == 0.0

    def test_float_division(self):
        assert abs(safe_divide(1, 3) - 0.3333333333) < 1e-6

    def test_negative_values(self):
        assert safe_divide(-10, 2) == -5.0


# ---------------------------------------------------------------------------
# normalize_metric_name
# ---------------------------------------------------------------------------

class TestNormalizeMetricName:

    def test_lowercase(self):
        assert normalize_metric_name("BLEU") == "bleu"

    def test_dash_to_underscore(self):
        assert normalize_metric_name("bert-score") == "bert_score"

    def test_space_to_underscore(self):
        assert normalize_metric_name("exact match") == "exact_match"

    def test_combined(self):
        assert normalize_metric_name("BERT-Score F1") == "bert_score_f1"

    def test_already_normalized(self):
        assert normalize_metric_name("accuracy") == "accuracy"

    def test_empty_string(self):
        assert normalize_metric_name("") == ""


# ---------------------------------------------------------------------------
# format_metrics_for_display
# ---------------------------------------------------------------------------

class TestFormatMetricsForDisplay:

    def test_default_precision(self):
        result = format_metrics_for_display({"accuracy": 0.95678})
        assert result["accuracy"] == "0.957"

    def test_custom_precision(self):
        result = format_metrics_for_display({"f1": 0.8}, precision=2)
        assert result["f1"] == "0.80"

    def test_integer_value(self):
        result = format_metrics_for_display({"count": 42})
        assert result["count"] == "42.000"

    def test_non_numeric_value(self):
        result = format_metrics_for_display({"label": "test"})
        assert result["label"] == "test"

    def test_empty_dict(self):
        assert format_metrics_for_display({}) == {}

    def test_multiple_metrics(self):
        metrics = {"accuracy": 0.95, "f1": 0.87, "recall": 0.90}
        result = format_metrics_for_display(metrics, precision=2)
        assert result["accuracy"] == "0.95"
        assert result["f1"] == "0.87"
        assert result["recall"] == "0.90"


# ---------------------------------------------------------------------------
# validate_evaluation_request
# ---------------------------------------------------------------------------

class TestValidateEvaluationRequest:

    def test_valid_request(self):
        valid, msg = validate_evaluation_request(
            task_id="t1", model_id="m1", metrics=["accuracy"],
            supported_task_types=[], supported_metrics={},
        )
        assert valid
        assert msg == ""

    def test_missing_task_id(self):
        valid, msg = validate_evaluation_request(
            task_id="", model_id="m1", metrics=["accuracy"],
            supported_task_types=[], supported_metrics={},
        )
        assert not valid
        assert "Task ID" in msg

    def test_missing_model_id(self):
        valid, msg = validate_evaluation_request(
            task_id="t1", model_id="", metrics=["accuracy"],
            supported_task_types=[], supported_metrics={},
        )
        assert not valid
        assert "Model ID" in msg

    def test_missing_metrics(self):
        valid, msg = validate_evaluation_request(
            task_id="t1", model_id="m1", metrics=[],
            supported_task_types=[], supported_metrics={},
        )
        assert not valid
        assert "metric" in msg.lower()


# ---------------------------------------------------------------------------
# create_evaluation_metadata
# ---------------------------------------------------------------------------

class TestCreateEvaluationMetadata:

    def test_basic_metadata(self):
        result = create_evaluation_metadata("qa", "gpt-4", 100, 90)
        assert result["task_type"] == "qa"
        assert result["model_id"] == "gpt-4"
        assert result["total_samples"] == 100
        assert result["valid_samples"] == 90
        assert abs(result["coverage"] - 0.9) < 1e-6
        assert "evaluation_timestamp" in result

    def test_zero_total_samples(self):
        result = create_evaluation_metadata("qa", "m", 0, 0)
        assert result["coverage"] == 0.0

    def test_with_config(self):
        result = create_evaluation_metadata("qa", "m", 10, 10, config={"threshold": 0.5})
        assert result["threshold"] == 0.5

    def test_config_none(self):
        result = create_evaluation_metadata("qa", "m", 10, 10)
        assert "threshold" not in result


# ---------------------------------------------------------------------------
# extract_task_type_from_label_config
# ---------------------------------------------------------------------------

class TestExtractTaskTypeFromLabelConfig:

    def test_text_classification(self):
        config = "<View><Text name='t'/><Choices name='c' toName='t'><Choice value='a'/></Choices></View>"
        assert extract_task_type_from_label_config(config) == "text_classification"

    def test_summarization(self):
        config = "<View><Text name='text'/><TextArea name='summary' toName='text'/></View>"
        assert extract_task_type_from_label_config(config) == "summarization"

    def test_summarization_german(self):
        config = "<View><Text name='text'/><TextArea name='zusammenfassung' toName='text'/></View>"
        assert extract_task_type_from_label_config(config) == "summarization"

    def test_qa_reasoning(self):
        config = "<View><Text name='question'/><TextArea name='answer' toName='question'/></View>"
        assert extract_task_type_from_label_config(config) == "qa_reasoning"

    def test_qa_reasoning_german(self):
        config = "<View><Text name='frage'/><TextArea name='antwort' toName='frage'/></View>"
        assert extract_task_type_from_label_config(config) == "qa_reasoning"

    def test_default_fallback(self):
        config = "<View><Rating name='r'/></View>"
        assert extract_task_type_from_label_config(config) == "text_classification"


# ---------------------------------------------------------------------------
# filter_tasks_with_model_predictions
# ---------------------------------------------------------------------------

class TestFilterTasksWithModelPredictions:

    def test_filters_by_model_version(self):
        tasks = [
            {
                "id": 1,
                "annotations": [{"result": []}],
                "predictions": [{"model_version": "gpt-4", "result": []}],
            },
            {
                "id": 2,
                "annotations": [{"result": []}],
                "predictions": [{"model_version": "llama", "result": []}],
            },
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_filters_by_model_id(self):
        tasks = [
            {
                "id": 1,
                "annotations": [{"result": []}],
                "predictions": [{"model_id": "gpt-4", "result": []}],
            },
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 1

    def test_requires_annotations(self):
        tasks = [
            {
                "id": 1,
                "annotations": [],
                "predictions": [{"model_version": "gpt-4", "result": []}],
            },
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 0

    def test_no_matching_predictions(self):
        tasks = [
            {
                "id": 1,
                "annotations": [{"result": []}],
                "predictions": [{"model_version": "llama", "result": []}],
            },
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 0

    def test_empty_tasks(self):
        assert filter_tasks_with_model_predictions([], "gpt-4") == []


# ---------------------------------------------------------------------------
# merge_evaluation_results
# ---------------------------------------------------------------------------

class TestMergeEvaluationResults:

    def test_empty_list(self):
        assert merge_evaluation_results([]) == {}

    def test_single_result(self):
        result = {"metrics": {"accuracy": 0.9}, "metadata": {"total_samples": 10}}
        merged = merge_evaluation_results([result])
        assert merged == result

    def test_two_results_averaged(self):
        results = [
            {"metrics": {"accuracy": 0.8}, "metadata": {"total_samples": 10, "valid_samples": 8}},
            {"metrics": {"accuracy": 0.9}, "metadata": {"total_samples": 10, "valid_samples": 9}},
        ]
        merged = merge_evaluation_results(results)
        assert abs(merged["metrics"]["accuracy"] - 0.85) < 1e-6
        assert merged["metadata"]["total_samples"] == 20
        assert merged["metadata"]["valid_samples"] == 17
        assert merged["metadata"]["num_evaluations"] == 2

    def test_multiple_metrics_averaged(self):
        results = [
            {"metrics": {"accuracy": 0.8, "f1": 0.7}, "metadata": {"total_samples": 5, "valid_samples": 5}},
            {"metrics": {"accuracy": 0.9, "f1": 0.9}, "metadata": {"total_samples": 5, "valid_samples": 5}},
        ]
        merged = merge_evaluation_results(results)
        assert abs(merged["metrics"]["accuracy"] - 0.85) < 1e-6
        assert abs(merged["metrics"]["f1"] - 0.8) < 1e-6

    def test_preserves_first_result_metadata(self):
        results = [
            {"metrics": {"a": 1}, "metadata": {"total_samples": 5, "valid_samples": 5, "model_id": "gpt-4"}},
            {"metrics": {"a": 2}, "metadata": {"total_samples": 5, "valid_samples": 5}},
        ]
        merged = merge_evaluation_results(results)
        assert merged["metadata"]["model_id"] == "gpt-4"


# ---------------------------------------------------------------------------
# export_evaluation_results
# ---------------------------------------------------------------------------

class TestExportEvaluationResults:

    def test_json_format_string(self):
        results = {"metrics": {"accuracy": 0.9}}
        output = export_evaluation_results(results, output_format="json")
        parsed = json.loads(output)
        assert parsed["metrics"]["accuracy"] == 0.9

    def test_json_format_file(self):
        results = {"metrics": {"accuracy": 0.9}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            returned_path = export_evaluation_results(results, output_format="json", output_path=path)
            assert returned_path == path
            with open(path) as f:
                data = json.load(f)
            assert data["metrics"]["accuracy"] == 0.9
        finally:
            os.unlink(path)

    def test_csv_format_string(self):
        results = {"metrics": {"accuracy": 0.9, "f1": 0.85}}
        output = export_evaluation_results(results, output_format="csv")
        assert "accuracy" in output
        assert "0.9" in output
        assert "f1" in output

    def test_csv_format_file(self):
        results = {"metrics": {"accuracy": 0.9}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            path = f.name
        try:
            returned_path = export_evaluation_results(results, output_format="csv", output_path=path)
            assert returned_path == path
        finally:
            os.unlink(path)

    def test_dict_format(self):
        results = {"metrics": {"accuracy": 0.9}}
        output = export_evaluation_results(results, output_format="dict")
        assert output is results


# ---------------------------------------------------------------------------
# EvaluationTimer
# ---------------------------------------------------------------------------

class TestEvaluationTimer:

    def test_context_manager_sets_times(self):
        with EvaluationTimer("test_op") as timer:
            pass
        assert timer.start_time is not None
        assert timer.end_time is not None
        assert timer.duration_seconds is not None
        assert timer.duration_seconds >= 0

    def test_duration_none_before_exit(self):
        timer = EvaluationTimer("test")
        assert timer.duration_seconds is None

    def test_custom_operation_name(self):
        timer = EvaluationTimer("custom_eval")
        assert timer.operation_name == "custom_eval"

    def test_default_operation_name(self):
        timer = EvaluationTimer()
        assert timer.operation_name == "evaluation"

    def test_exception_still_records_end_time(self):
        timer = EvaluationTimer("failing_op")
        with pytest.raises(ValueError):
            with timer:
                raise ValueError("test error")
        assert timer.end_time is not None
        assert timer.duration_seconds is not None
