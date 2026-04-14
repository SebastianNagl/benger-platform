"""
Unit tests for evaluation results helper functions and endpoint logic.
Covers _extract_primary_score and core result aggregation paths.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from routers.evaluations.results import _extract_primary_score


class TestExtractPrimaryScore:
    """Tests for _extract_primary_score priority logic."""

    def test_returns_none_for_none_metrics(self):
        assert _extract_primary_score(None) is None

    def test_returns_none_for_empty_metrics(self):
        assert _extract_primary_score({}) is None

    def test_priority_1_llm_judge_custom(self):
        metrics = {
            "llm_judge_custom": 0.85,
            "score": 0.6,
        }
        assert _extract_primary_score(metrics) == 0.85

    def test_priority_1_custom_non_numeric_skipped(self):
        metrics = {
            "llm_judge_custom": "not_a_number",
            "score": 0.6,
        }
        assert _extract_primary_score(metrics) == 0.6

    def test_priority_2_generic_llm_judge_key(self):
        metrics = {
            "llm_judge_coherence": 0.88,
            "score": 0.5,
        }
        assert _extract_primary_score(metrics) == 0.88

    def test_priority_4_skips_suffixed_keys(self):
        metrics = {
            "llm_judge_test_response": "some text",
            "llm_judge_test_passed": True,
            "llm_judge_test_details": {"info": "data"},
            "llm_judge_test_raw": 42,
            "score": 0.7,
        }
        assert _extract_primary_score(metrics) == 0.7

    def test_priority_4_numeric_llm_judge_not_suffixed(self):
        metrics = {
            "llm_judge_accuracy": 0.95,
        }
        assert _extract_primary_score(metrics) == 0.95

    def test_priority_5_score_key(self):
        metrics = {"score": 0.82}
        assert _extract_primary_score(metrics) == 0.82

    def test_priority_5_overall_score_key(self):
        metrics = {"overall_score": 0.77}
        assert _extract_primary_score(metrics) == 0.77

    def test_score_preferred_over_overall_score(self):
        metrics = {"score": 0.8, "overall_score": 0.9}
        assert _extract_primary_score(metrics) == 0.8

    def test_returns_none_when_all_non_numeric(self):
        metrics = {"accuracy": "high", "quality": "good"}
        assert _extract_primary_score(metrics) is None

    def test_zero_is_valid(self):
        metrics = {"score": 0}
        assert _extract_primary_score(metrics) == 0

    def test_negative_score(self):
        metrics = {"score": -0.5}
        assert _extract_primary_score(metrics) == -0.5


class TestEvaluationConfigDerivation:
    """Tests for _derive_evaluation_configs_from_selected_methods."""

    def test_basic_derivation(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "answer": {
                "automated": ["bleu", "rouge"],
                "field_mapping": {
                    "prediction_field": "pred_answer",
                    "reference_field": "ref_answer",
                },
            }
        }
        configs = _derive_evaluation_configs_from_selected_methods(selected_methods)
        assert len(configs) == 2
        assert configs[0]["metric"] == "bleu"
        assert configs[0]["prediction_fields"] == ["pred_answer"]
        assert configs[0]["reference_fields"] == ["ref_answer"]
        assert configs[0]["enabled"] is True

    def test_empty_selected_methods(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        assert _derive_evaluation_configs_from_selected_methods({}) == []

    def test_non_dict_selections_skipped(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {"field1": "not_a_dict"}
        assert _derive_evaluation_configs_from_selected_methods(selected_methods) == []

    def test_object_format_metric(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "text": {
                "automated": [
                    {"name": "bert_score", "parameters": {"model": "deberta"}},
                ],
                "field_mapping": {
                    "prediction_field": "gen_text",
                    "reference_field": "gold_text",
                },
            }
        }
        configs = _derive_evaluation_configs_from_selected_methods(selected_methods)
        assert len(configs) == 1
        assert configs[0]["metric"] == "bert_score"
        assert configs[0]["metric_parameters"] == {"model": "deberta"}

    def test_default_field_mapping(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "answer": {
                "automated": ["exact_match"],
            }
        }
        configs = _derive_evaluation_configs_from_selected_methods(selected_methods)
        assert len(configs) == 1
        assert configs[0]["prediction_fields"] == ["answer"]
        assert configs[0]["reference_fields"] == ["answer"]

    def test_empty_metric_name_skipped(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "field": {
                "automated": [{"name": "", "parameters": {}}],
            }
        }
        assert _derive_evaluation_configs_from_selected_methods(selected_methods) == []

    def test_none_metric_raises(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "field": {
                "automated": [None],
            }
        }
        # None is neither str nor dict, so .get() call raises AttributeError
        with pytest.raises(AttributeError):
            _derive_evaluation_configs_from_selected_methods(selected_methods)

    def test_display_name_formatting(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "field": {
                "automated": ["bert_score"],
            }
        }
        configs = _derive_evaluation_configs_from_selected_methods(selected_methods)
        assert configs[0]["display_name"] == "Bert Score"

    def test_id_format(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "my_field": {
                "automated": ["exact_match"],
            }
        }
        configs = _derive_evaluation_configs_from_selected_methods(selected_methods)
        assert configs[0]["id"] == "my_field_exact_match"

    def test_no_automated_key(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "field": {
                "human": ["likert_scale"],
            }
        }
        configs = _derive_evaluation_configs_from_selected_methods(selected_methods)
        assert configs == []

    def test_multiple_fields(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        selected_methods = {
            "answer": {
                "automated": ["bleu"],
                "field_mapping": {"prediction_field": "a", "reference_field": "b"},
            },
            "summary": {
                "automated": ["rouge"],
                "field_mapping": {"prediction_field": "c", "reference_field": "d"},
            },
        }
        configs = _derive_evaluation_configs_from_selected_methods(selected_methods)
        assert len(configs) == 2
        metrics = {c["metric"] for c in configs}
        assert metrics == {"bleu", "rouge"}


class TestExtractMetricName:
    """Tests for extract_metric_name helper."""

    def test_string_metric(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name("bleu") == "bleu"

    def test_dict_metric(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name({"name": "rouge", "parameters": {}}) == "rouge"

    def test_dict_without_name(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name({"parameters": {}}) == ""

    def test_none_metric(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name(None) == ""

    def test_numeric_metric(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name(42) == ""

    def test_empty_string(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name("") == ""

    def test_empty_dict(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name({}) == ""


class TestSerializerFunctions:
    """Tests for routers.projects.serializers functions."""

    def test_isoformat_with_datetime(self):
        from routers.projects.serializers import _isoformat

        dt = datetime(2025, 1, 15, 10, 30, 0)
        assert _isoformat(dt) == "2025-01-15T10:30:00"

    def test_isoformat_with_none(self):
        from routers.projects.serializers import _isoformat

        assert _isoformat(None) is None

    def test_serialize_task_data_mode(self):
        from routers.projects.serializers import serialize_task

        task = Mock()
        task.id = "task-1"
        task.inner_id = 1
        task.data = {"text": "hello"}
        task.meta = {}
        task.is_labeled = False
        task.created_at = datetime(2025, 1, 1)
        task.updated_at = None

        result = serialize_task(task, mode="data")
        assert result["id"] == "task-1"
        assert "project_id" not in result

    def test_serialize_task_full_mode(self):
        from routers.projects.serializers import serialize_task

        task = Mock()
        task.id = "task-1"
        task.inner_id = 1
        task.data = {"text": "hello"}
        task.meta = {}
        task.is_labeled = True
        task.created_at = datetime(2025, 1, 1)
        task.updated_at = None
        task.project_id = "proj-1"
        task.created_by = "user-1"
        task.updated_by = None
        task.total_annotations = 3
        task.cancelled_annotations = 0
        task.comment_count = 0
        task.unresolved_comment_count = 0
        task.last_comment_updated_at = None
        task.comment_authors = []
        task.file_upload_id = None

        result = serialize_task(task, mode="full", total_generations=5)
        assert result["project_id"] == "proj-1"
        assert result["total_generations"] == 5

    def test_serialize_annotation_data_mode(self):
        from routers.projects.serializers import serialize_annotation

        ann = Mock()
        ann.id = "ann-1"
        ann.result = [{"from_name": "label", "value": {"text": ["hello"]}}]
        ann.completed_by = "user-1"
        ann.created_at = datetime(2025, 1, 1)
        ann.updated_at = None
        ann.was_cancelled = False
        ann.ground_truth = False
        ann.lead_time = 30.5
        ann.active_duration_ms = 25000
        ann.focused_duration_ms = 20000
        ann.tab_switches = 1
        ann.reviewed_by = None
        ann.reviewed_at = None
        ann.review_result = None

        result = serialize_annotation(ann, mode="data")
        assert result["id"] == "ann-1"
        assert result["questionnaire_response"] is None
        assert "task_id" not in result

    def test_serialize_annotation_data_mode_with_questionnaire(self):
        from routers.projects.serializers import serialize_annotation

        ann = Mock()
        ann.id = "ann-1"
        ann.result = []
        ann.completed_by = "user-1"
        ann.created_at = datetime(2025, 1, 1)
        ann.updated_at = None
        ann.was_cancelled = False
        ann.ground_truth = False
        ann.lead_time = 10.0
        ann.active_duration_ms = None
        ann.focused_duration_ms = None
        ann.tab_switches = 0
        ann.reviewed_by = None
        ann.reviewed_at = None
        ann.review_result = None

        qr = Mock()
        qr.result = {"q1": "answer1"}
        qr.created_at = datetime(2025, 2, 1)

        result = serialize_annotation(ann, mode="data", questionnaire_response=qr)
        assert result["questionnaire_response"]["result"] == {"q1": "answer1"}

    def test_serialize_annotation_full_mode(self):
        from routers.projects.serializers import serialize_annotation

        ann = Mock()
        ann.id = "ann-1"
        ann.result = []
        ann.completed_by = "user-1"
        ann.created_at = datetime(2025, 1, 1)
        ann.updated_at = None
        ann.was_cancelled = False
        ann.ground_truth = False
        ann.lead_time = 10.0
        ann.active_duration_ms = None
        ann.focused_duration_ms = None
        ann.tab_switches = 0
        ann.reviewed_by = None
        ann.reviewed_at = None
        ann.review_result = None
        ann.task_id = "task-1"
        ann.project_id = "proj-1"
        ann.draft = None
        ann.prediction_scores = None
        ann.auto_submitted = False

        result = serialize_annotation(ann, mode="full")
        assert result["task_id"] == "task-1"
        assert result["project_id"] == "proj-1"

    def test_serialize_generation_data_mode(self):
        from routers.projects.serializers import serialize_generation

        gen = Mock()
        gen.id = "gen-1"
        gen.model_id = "gpt-4o"
        gen.response_content = "Generated text"
        gen.case_data = {"input": "question"}
        gen.created_at = datetime(2025, 1, 1)
        gen.response_metadata = {}

        result = serialize_generation(gen, mode="data")
        assert result["evaluations"] == []

    def test_serialize_generation_data_mode_with_evals(self):
        from routers.projects.serializers import serialize_generation

        gen = Mock()
        gen.id = "gen-1"
        gen.model_id = "gpt-4o"
        gen.response_content = "Generated text"
        gen.case_data = {}
        gen.created_at = datetime(2025, 1, 1)
        gen.response_metadata = {}

        evals = [{"metric": "bleu", "score": 0.8}]
        result = serialize_generation(gen, mode="data", evaluations=evals)
        assert result["evaluations"] == evals

    def test_serialize_generation_full_mode(self):
        from routers.projects.serializers import serialize_generation

        gen = Mock()
        gen.id = "gen-1"
        gen.model_id = "gpt-4o"
        gen.response_content = "Generated text"
        gen.case_data = {}
        gen.created_at = datetime(2025, 1, 1)
        gen.response_metadata = {}
        gen.generation_id = "resp-gen-1"
        gen.task_id = "task-1"
        gen.usage_stats = {"tokens": 100}
        gen.status = "success"
        gen.error_message = None

        result = serialize_generation(gen, mode="full")
        assert result["generation_id"] == "resp-gen-1"
        assert result["task_id"] == "task-1"

    def test_serialize_task_evaluation_data_mode(self):
        from routers.projects.serializers import serialize_task_evaluation

        te = Mock()
        te.id = "te-1"
        te.annotation_id = "ann-1"
        te.field_name = "config1:answer"
        te.answer_type = "text"
        te.ground_truth = {"value": "correct"}
        te.prediction = {"value": "predicted"}
        te.metrics = {"bleu": 0.8}
        te.passed = True
        te.confidence_score = 0.9
        te.error_message = None
        te.processing_time_ms = 150
        te.created_at = datetime(2025, 1, 1)
        te.evaluation_id = "eval-1"

        eval_run = Mock()
        eval_run.model_id = "gpt-4o"

        lookup = {("eval-1", "config1"): "claude-sonnet-4"}

        result = serialize_task_evaluation(
            te, mode="data", eval_run=eval_run, judge_model_lookup=lookup
        )
        assert result["evaluated_model"] == "gpt-4o"
        assert result["judge_model"] == "claude-sonnet-4"

    def test_serialize_task_evaluation_full_mode(self):
        from routers.projects.serializers import serialize_task_evaluation

        te = Mock()
        te.id = "te-1"
        te.annotation_id = "ann-1"
        te.field_name = "answer"
        te.answer_type = "text"
        te.ground_truth = {}
        te.prediction = {}
        te.metrics = {}
        te.passed = True
        te.confidence_score = None
        te.error_message = None
        te.processing_time_ms = None
        te.created_at = datetime(2025, 1, 1)
        te.evaluation_id = "eval-1"
        te.task_id = "task-1"
        te.generation_id = "gen-1"

        result = serialize_task_evaluation(te, mode="full")
        assert result["evaluation_id"] == "eval-1"
        assert result["task_id"] == "task-1"

    def test_serialize_evaluation_run_data_mode(self):
        from routers.projects.serializers import serialize_evaluation_run

        er = Mock()
        er.id = "er-1"
        er.model_id = "gpt-4o"
        er.evaluation_type_ids = ["bleu"]
        er.metrics = {"bleu": 0.8}
        er.status = "completed"
        er.samples_evaluated = 50
        er.created_at = datetime(2025, 1, 1)
        er.completed_at = datetime(2025, 1, 1)
        er.eval_metadata = {}
        er.error_message = None
        er.has_sample_results = True
        er.created_by = "user-1"

        result = serialize_evaluation_run(er, mode="data")
        assert result["eval_metadata"] == {}
        assert result["has_sample_results"] is True
        assert "project_id" not in result

    def test_serialize_evaluation_run_full_mode(self):
        from routers.projects.serializers import serialize_evaluation_run

        er = Mock()
        er.id = "er-1"
        er.model_id = "gpt-4o"
        er.evaluation_type_ids = ["bleu"]
        er.metrics = {}
        er.status = "pending"
        er.samples_evaluated = 0
        er.created_at = datetime(2025, 1, 1)
        er.completed_at = None
        er.eval_metadata = {}
        er.error_message = None
        er.created_by = "user-1"
        er.project_id = "proj-1"
        er.task_id = "task-1"

        result = serialize_evaluation_run(er, mode="full")
        assert result["project_id"] == "proj-1"
        assert result["task_id"] == "task-1"


class TestBuildJudgeModelLookup:
    """Tests for build_judge_model_lookup."""

    def test_new_format_judge_models(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = Mock()
        er.id = "er-1"
        er.eval_metadata = {
            "judge_models": {"config1": "claude-sonnet-4", "config2": "gpt-4o"},
            "evaluation_configs": [],
        }
        result = build_judge_model_lookup([er])
        assert result[("er-1", "config1")] == "claude-sonnet-4"
        assert result[("er-1", "config2")] == "gpt-4o"

    def test_old_format_evaluation_configs(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = Mock()
        er.id = "er-1"
        er.eval_metadata = {
            "evaluation_configs": [
                {"id": "cfg1", "metric_parameters": {"judge_model": "gpt-4o"}},
            ],
        }
        result = build_judge_model_lookup([er])
        assert result[("er-1", "cfg1")] == "gpt-4o"

    def test_new_format_takes_precedence(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = Mock()
        er.id = "er-1"
        er.eval_metadata = {
            "judge_models": {"cfg1": "claude-sonnet-4"},
            "evaluation_configs": [
                {"id": "cfg1", "metric_parameters": {"judge_model": "gpt-4o"}},
            ],
        }
        result = build_judge_model_lookup([er])
        assert result[("er-1", "cfg1")] == "claude-sonnet-4"

    def test_empty_metadata(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = Mock()
        er.id = "er-1"
        er.eval_metadata = {}
        result = build_judge_model_lookup([er])
        assert result == {}

    def test_none_metadata(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = Mock()
        er.id = "er-1"
        er.eval_metadata = None
        result = build_judge_model_lookup([er])
        assert result == {}

    def test_no_metric_parameters(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = Mock()
        er.id = "er-1"
        er.eval_metadata = {
            "evaluation_configs": [
                {"id": "cfg1"},
            ],
        }
        result = build_judge_model_lookup([er])
        assert result == {}

    def test_multiple_evaluation_runs(self):
        from routers.projects.serializers import build_judge_model_lookup

        er1 = Mock()
        er1.id = "er-1"
        er1.eval_metadata = {
            "judge_models": {"cfg1": "model-a"},
            "evaluation_configs": [],
        }
        er2 = Mock()
        er2.id = "er-2"
        er2.eval_metadata = {
            "evaluation_configs": [
                {"id": "cfg2", "metric_parameters": {"judge_model": "model-b"}},
            ],
        }
        result = build_judge_model_lookup([er1, er2])
        assert result[("er-1", "cfg1")] == "model-a"
        assert result[("er-2", "cfg2")] == "model-b"


class TestBuildEvaluationIndexes:
    """Tests for build_evaluation_indexes."""

    def test_basic_indexing(self):
        from routers.projects.serializers import build_evaluation_indexes

        te1 = Mock(task_id="t1", generation_id="g1")
        te2 = Mock(task_id="t1", generation_id=None)
        te3 = Mock(task_id="t2", generation_id="g2")

        by_task, by_gen = build_evaluation_indexes([te1, te2, te3])

        assert len(by_task["t1"]) == 2
        assert len(by_task["t2"]) == 1
        assert len(by_gen["g1"]) == 1
        assert "g2" in by_gen
        assert None not in by_gen

    def test_empty_list(self):
        from routers.projects.serializers import build_evaluation_indexes

        by_task, by_gen = build_evaluation_indexes([])
        assert by_task == {}
        assert by_gen == {}
