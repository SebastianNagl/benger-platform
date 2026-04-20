"""Coverage tests for ml_evaluation/utils.py.

Tests: filter_tasks_with_model_predictions, validate_evaluation_request,
create_evaluation_metadata, safe_divide, normalize_metric_name,
format_metrics_for_display, extract_task_type_from_label_config,
merge_evaluation_results, export_evaluation_results, EvaluationTimer.
"""

import json
import sys
import os
import tempfile
import time

import pytest

workers_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, workers_root)

from ml_evaluation.utils import (
    filter_tasks_with_model_predictions,
    validate_evaluation_request,
    create_evaluation_metadata,
    safe_divide,
    normalize_metric_name,
    format_metrics_for_display,
    extract_task_type_from_label_config,
    merge_evaluation_results,
    export_evaluation_results,
    EvaluationTimer,
)


class TestFilterTasksWithModelPredictions:
    def test_filter_matching(self):
        tasks = [
            {
                "predictions": [{"model_version": "gpt-4"}],
                "annotations": [{"result": []}],
            }
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 1

    def test_filter_model_id_key(self):
        tasks = [
            {
                "predictions": [{"model_id": "gpt-4"}],
                "annotations": [{"result": []}],
            }
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 1

    def test_no_match(self):
        tasks = [
            {
                "predictions": [{"model_version": "claude"}],
                "annotations": [{"result": []}],
            }
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 0

    def test_no_annotations(self):
        tasks = [
            {
                "predictions": [{"model_version": "gpt-4"}],
            }
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 0

    def test_empty_annotations(self):
        tasks = [
            {
                "predictions": [{"model_version": "gpt-4"}],
                "annotations": [],
            }
        ]
        result = filter_tasks_with_model_predictions(tasks, "gpt-4")
        assert len(result) == 0

    def test_empty_tasks(self):
        result = filter_tasks_with_model_predictions([], "gpt-4")
        assert len(result) == 0


class TestValidateEvaluationRequest:
    def test_valid(self):
        valid, msg = validate_evaluation_request("t1", "m1", ["accuracy"], [], {})
        assert valid is True
        assert msg == ""

    def test_missing_task_id(self):
        valid, msg = validate_evaluation_request("", "m1", ["accuracy"], [], {})
        assert valid is False
        assert "Task ID" in msg

    def test_missing_model_id(self):
        valid, msg = validate_evaluation_request("t1", "", ["accuracy"], [], {})
        assert valid is False
        assert "Model ID" in msg

    def test_missing_metrics(self):
        valid, msg = validate_evaluation_request("t1", "m1", [], [], {})
        assert valid is False
        assert "metric" in msg


class TestCreateEvaluationMetadata:
    def test_basic(self):
        meta = create_evaluation_metadata("qa", "gpt-4", 100, 90)
        assert meta["task_type"] == "qa"
        assert meta["model_id"] == "gpt-4"
        assert meta["total_samples"] == 100
        assert meta["valid_samples"] == 90
        assert meta["coverage"] == 0.9

    def test_zero_total(self):
        meta = create_evaluation_metadata("qa", "gpt-4", 0, 0)
        assert meta["coverage"] == 0.0

    def test_with_config(self):
        meta = create_evaluation_metadata("qa", "gpt-4", 10, 10, config={"extra": "data"})
        assert meta["extra"] == "data"

    def test_has_timestamp(self):
        meta = create_evaluation_metadata("qa", "gpt-4", 10, 10)
        assert "evaluation_timestamp" in meta


class TestSafeDivide:
    def test_normal(self):
        assert safe_divide(10, 2) == 5.0

    def test_zero_denominator(self):
        assert safe_divide(10, 0) == 0.0

    def test_custom_default(self):
        assert safe_divide(10, 0, default=-1.0) == -1.0

    def test_float_division(self):
        assert safe_divide(1, 3) == pytest.approx(0.333, abs=0.01)


class TestNormalizeMetricName:
    def test_lowercase(self):
        assert normalize_metric_name("BLEU") == "bleu"

    def test_hyphens(self):
        assert normalize_metric_name("bert-score") == "bert_score"

    def test_spaces(self):
        assert normalize_metric_name("F1 Score") == "f1_score"

    def test_combined(self):
        assert normalize_metric_name("F1-Score (Macro)") == "f1_score_(macro)"


class TestFormatMetricsForDisplay:
    def test_float_formatting(self):
        result = format_metrics_for_display({"accuracy": 0.9567})
        assert result["accuracy"] == "0.957"

    def test_int_formatting(self):
        result = format_metrics_for_display({"count": 5})
        assert result["count"] == "5.000"

    def test_custom_precision(self):
        result = format_metrics_for_display({"accuracy": 0.95}, precision=2)
        assert result["accuracy"] == "0.95"

    def test_non_numeric(self):
        result = format_metrics_for_display({"label": "good"})
        assert result["label"] == "good"


class TestExtractTaskTypeFromLabelConfig:
    def test_choices_text(self):
        config = '<View><Choices name="q" toName="text"><Choice value="A"/></Choices><Text name="text" value="$text"/></View>'
        assert extract_task_type_from_label_config(config) == "text_classification"

    def test_textarea_summary(self):
        config = '<View><TextArea name="summary" toName="text"/></View>'
        assert extract_task_type_from_label_config(config) == "summarization"

    def test_textarea_zusammenfassung(self):
        config = '<View><TextArea name="zusammenfassung" toName="text"/></View>'
        assert extract_task_type_from_label_config(config) == "summarization"

    def test_textarea_question(self):
        config = '<View><TextArea name="answer" toName="question"/></View>'
        assert extract_task_type_from_label_config(config) == "qa_reasoning"

    def test_textarea_frage(self):
        config = '<View><TextArea name="antwort" toName="frage"/></View>'
        assert extract_task_type_from_label_config(config) == "qa_reasoning"

    def test_default_fallback(self):
        config = '<View><Rating name="score" toName="text"/></View>'
        assert extract_task_type_from_label_config(config) == "text_classification"


class TestMergeEvaluationResults:
    def test_empty(self):
        assert merge_evaluation_results([]) == {}

    def test_single(self):
        result = [{"metrics": {"accuracy": 0.9}, "metadata": {"total_samples": 10}}]
        merged = merge_evaluation_results(result)
        assert merged == result[0]

    def test_multiple(self):
        results = [
            {"metrics": {"accuracy": 0.8}, "metadata": {"total_samples": 10, "valid_samples": 8}},
            {"metrics": {"accuracy": 0.9}, "metadata": {"total_samples": 20, "valid_samples": 18}},
        ]
        merged = merge_evaluation_results(results)
        assert merged["metrics"]["accuracy"] == pytest.approx(0.85)
        assert merged["metadata"]["total_samples"] == 30
        assert merged["metadata"]["valid_samples"] == 26

    def test_metadata_inherited(self):
        results = [
            {"metrics": {"accuracy": 0.8}, "metadata": {"total_samples": 10, "valid_samples": 8, "model_id": "gpt"}},
            {"metrics": {"accuracy": 0.9}, "metadata": {"total_samples": 20, "valid_samples": 18}},
        ]
        merged = merge_evaluation_results(results)
        assert merged["metadata"]["model_id"] == "gpt"


class TestExportEvaluationResults:
    def test_json_format(self):
        results = {"metrics": {"accuracy": 0.9}}
        output = export_evaluation_results(results, "json")
        parsed = json.loads(output)
        assert parsed["metrics"]["accuracy"] == 0.9

    def test_json_to_file(self):
        results = {"metrics": {"accuracy": 0.9}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            returned_path = export_evaluation_results(results, "json", path)
            assert returned_path == path
            with open(path) as f:
                content = json.load(f)
            assert content["metrics"]["accuracy"] == 0.9
        finally:
            os.unlink(path)

    def test_csv_format(self):
        results = {"metrics": {"accuracy": 0.9, "f1": 0.85}}
        output = export_evaluation_results(results, "csv")
        assert "metric,value" in output
        assert "accuracy" in output

    def test_csv_to_file(self):
        results = {"metrics": {"accuracy": 0.9}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            path = f.name
        try:
            returned_path = export_evaluation_results(results, "csv", path)
            assert returned_path == path
        finally:
            os.unlink(path)

    def test_dict_format(self):
        results = {"metrics": {"accuracy": 0.9}}
        output = export_evaluation_results(results, "dict")
        assert output == results

