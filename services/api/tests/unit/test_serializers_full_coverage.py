"""
Unit tests for routers/projects/serializers.py — targets uncovered lines 14-219.
Covers: serialize_task, serialize_annotation, serialize_generation,
serialize_task_evaluation, serialize_evaluation_run,
build_judge_model_lookup, build_evaluation_indexes.
"""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest


def _dt():
    return datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestSerializeTask:
    def test_data_mode(self):
        from routers.projects.serializers import serialize_task
        task = Mock()
        task.id = "t1"
        task.inner_id = 1
        task.data = {"text": "hello"}
        task.meta = {}
        task.is_labeled = True
        task.created_at = _dt()
        task.updated_at = None

        result = serialize_task(task, mode="data")
        assert result["id"] == "t1"
        assert "project_id" not in result
        assert result["is_labeled"] is True
        assert result["updated_at"] is None

    def test_full_mode(self):
        from routers.projects.serializers import serialize_task
        task = Mock()
        task.id = "t1"
        task.inner_id = 1
        task.data = {"text": "hello"}
        task.meta = {}
        task.is_labeled = False
        task.created_at = _dt()
        task.updated_at = _dt()
        task.project_id = "p1"
        task.created_by = "u1"
        task.updated_by = "u2"
        task.total_annotations = 5
        task.cancelled_annotations = 1
        task.comment_count = 0
        task.unresolved_comment_count = 0
        task.last_comment_updated_at = None
        task.comment_authors = []
        task.file_upload_id = None

        result = serialize_task(task, mode="full", total_generations=3)
        assert result["project_id"] == "p1"
        assert result["total_generations"] == 3
        assert result["total_annotations"] == 5


class TestSerializeAnnotation:
    def test_data_mode_with_questionnaire(self):
        from routers.projects.serializers import serialize_annotation
        ann = Mock()
        ann.id = "a1"
        ann.result = [{"from_name": "x"}]
        ann.completed_by = "u1"
        ann.created_at = _dt()
        ann.updated_at = None
        ann.was_cancelled = False
        ann.ground_truth = False
        ann.lead_time = 10.5
        ann.active_duration_ms = 10000
        ann.focused_duration_ms = 9000
        ann.tab_switches = 1
        ann.reviewed_by = None
        ann.reviewed_at = None
        ann.review_result = None

        qr = Mock()
        qr.result = {"q1": "a1"}
        qr.created_at = _dt()

        result = serialize_annotation(ann, mode="data", questionnaire_response=qr)
        assert result["questionnaire_response"]["result"] == {"q1": "a1"}

    def test_data_mode_no_questionnaire(self):
        from routers.projects.serializers import serialize_annotation
        ann = Mock()
        ann.id = "a1"
        ann.result = []
        ann.completed_by = "u1"
        ann.created_at = None
        ann.updated_at = None
        ann.was_cancelled = True
        ann.ground_truth = False
        ann.lead_time = None
        ann.active_duration_ms = None
        ann.focused_duration_ms = None
        ann.tab_switches = 0
        ann.reviewed_by = None
        ann.reviewed_at = None
        ann.review_result = None

        result = serialize_annotation(ann, mode="data")
        assert result["questionnaire_response"] is None
        assert result["was_cancelled"] is True

    def test_full_mode(self):
        from routers.projects.serializers import serialize_annotation
        ann = Mock()
        ann.id = "a1"
        ann.result = [{"x": 1}]
        ann.completed_by = "u1"
        ann.created_at = _dt()
        ann.updated_at = _dt()
        ann.was_cancelled = False
        ann.ground_truth = True
        ann.lead_time = 5.0
        ann.active_duration_ms = 5000
        ann.focused_duration_ms = 4500
        ann.tab_switches = 0
        ann.reviewed_by = "u2"
        ann.reviewed_at = _dt()
        ann.review_result = "approved"
        ann.task_id = "t1"
        ann.project_id = "p1"
        ann.draft = None
        ann.prediction_scores = None
        ann.auto_submitted = False

        result = serialize_annotation(ann, mode="full")
        assert "task_id" in result
        assert "project_id" in result
        assert "questionnaire_response" not in result


class TestSerializeGeneration:
    def test_data_mode(self):
        from routers.projects.serializers import serialize_generation
        gen = Mock()
        gen.id = "g1"
        gen.model_id = "gpt-4o"
        gen.response_content = "Some answer"
        gen.case_data = {}
        gen.created_at = _dt()
        gen.response_metadata = {"tokens": 100}

        evals = [{"metric": "accuracy", "score": 0.9}]
        result = serialize_generation(gen, mode="data", evaluations=evals)
        assert result["evaluations"] == evals
        assert "generation_id" not in result

    def test_data_mode_default_evaluations(self):
        from routers.projects.serializers import serialize_generation
        gen = Mock()
        gen.id = "g1"
        gen.model_id = "gpt-4o"
        gen.response_content = "test"
        gen.case_data = {}
        gen.created_at = None
        gen.response_metadata = None

        result = serialize_generation(gen, mode="data")
        assert result["evaluations"] == []

    def test_full_mode(self):
        from routers.projects.serializers import serialize_generation
        gen = Mock()
        gen.id = "g1"
        gen.model_id = "claude-3"
        gen.response_content = "response"
        gen.case_data = {}
        gen.created_at = _dt()
        gen.response_metadata = {}
        gen.generation_id = "gen-1"
        gen.task_id = "t1"
        gen.usage_stats = {"prompt_tokens": 50}
        gen.status = "completed"
        gen.error_message = None

        result = serialize_generation(gen, mode="full")
        assert result["generation_id"] == "gen-1"
        assert result["task_id"] == "t1"
        assert "evaluations" not in result


class TestSerializeTaskEvaluation:
    def test_data_mode_with_judge(self):
        from routers.projects.serializers import serialize_task_evaluation
        te = Mock()
        te.id = "te1"
        te.annotation_id = "a1"
        te.field_name = "cfg1:field_x"
        te.answer_type = "text"
        te.ground_truth = "expected"
        te.prediction = "actual"
        te.metrics = {"exact_match": 1.0}
        te.passed = True
        te.confidence_score = 0.95
        te.error_message = None
        te.processing_time_ms = 100
        te.created_at = _dt()
        te.evaluation_id = "er1"

        eval_run = Mock()
        eval_run.model_id = "gpt-4o"

        lookup = {("er1", "cfg1"): "gpt-4o-judge"}

        result = serialize_task_evaluation(
            te, mode="data", eval_run=eval_run, judge_model_lookup=lookup
        )
        assert result["evaluated_model"] == "gpt-4o"
        assert result["judge_model"] == "gpt-4o-judge"
        assert result["evaluation_run_id"] == "er1"

    def test_data_mode_no_config_id(self):
        from routers.projects.serializers import serialize_task_evaluation
        te = Mock()
        te.id = "te1"
        te.annotation_id = "a1"
        te.field_name = "simple_field"  # No colon -> no config_id
        te.answer_type = "text"
        te.ground_truth = "a"
        te.prediction = "b"
        te.metrics = {}
        te.passed = False
        te.confidence_score = None
        te.error_message = None
        te.processing_time_ms = 50
        te.created_at = None
        te.evaluation_id = "er1"

        result = serialize_task_evaluation(te, mode="data")
        assert result["judge_model"] is None

    def test_full_mode(self):
        from routers.projects.serializers import serialize_task_evaluation
        te = Mock()
        te.id = "te1"
        te.annotation_id = "a1"
        te.field_name = "field"
        te.answer_type = "text"
        te.ground_truth = "x"
        te.prediction = "y"
        te.metrics = {}
        te.passed = False
        te.confidence_score = None
        te.error_message = "err"
        te.processing_time_ms = 10
        te.created_at = _dt()
        te.evaluation_id = "er1"
        te.task_id = "t1"
        te.generation_id = "g1"

        result = serialize_task_evaluation(te, mode="full")
        assert "evaluation_id" in result
        assert "task_id" in result
        assert "generation_id" in result


class TestSerializeEvaluationRun:
    def test_data_mode(self):
        from routers.projects.serializers import serialize_evaluation_run
        er = Mock()
        er.id = "er1"
        er.model_id = "gpt-4o"
        er.evaluation_type_ids = ["exact_match"]
        er.metrics = {"accuracy": 0.9}
        er.status = "completed"
        er.samples_evaluated = 100
        er.created_at = _dt()
        er.completed_at = _dt()
        er.eval_metadata = {"key": "val"}
        er.error_message = None
        er.has_sample_results = True
        er.created_by = "u1"

        result = serialize_evaluation_run(er, mode="data")
        assert "eval_metadata" in result
        assert "project_id" not in result

    def test_full_mode(self):
        from routers.projects.serializers import serialize_evaluation_run
        er = Mock()
        er.id = "er1"
        er.model_id = "gpt-4o"
        er.evaluation_type_ids = []
        er.metrics = {}
        er.status = "pending"
        er.samples_evaluated = 0
        er.created_at = None
        er.completed_at = None
        er.eval_metadata = {}
        er.error_message = "failed"
        er.created_by = "u1"
        er.project_id = "p1"
        er.task_id = None

        result = serialize_evaluation_run(er, mode="full")
        assert result["project_id"] == "p1"


class TestBuildJudgeModelLookup:
    def test_new_format(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = Mock()
        er.id = "er1"
        er.eval_metadata = {
            "judge_models": {"cfg1": "gpt-4o-judge"},
            "evaluation_configs": [],
        }
        result = build_judge_model_lookup([er])
        assert result[("er1", "cfg1")] == "gpt-4o-judge"

    def test_old_format(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = Mock()
        er.id = "er1"
        er.eval_metadata = {
            "evaluation_configs": [
                {"id": "cfg1", "metric_parameters": {"judge_model": "claude-judge"}},
            ],
        }
        result = build_judge_model_lookup([er])
        assert result[("er1", "cfg1")] == "claude-judge"

    def test_empty(self):
        from routers.projects.serializers import build_judge_model_lookup
        result = build_judge_model_lookup([])
        assert result == {}

    def test_none_metadata(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = Mock()
        er.id = "er1"
        er.eval_metadata = None
        result = build_judge_model_lookup([er])
        assert result == {}


class TestBuildEvaluationIndexes:
    def test_basic_indexing(self):
        from routers.projects.serializers import build_evaluation_indexes
        te1 = Mock()
        te1.task_id = "t1"
        te1.generation_id = "g1"
        te2 = Mock()
        te2.task_id = "t1"
        te2.generation_id = None
        te3 = Mock()
        te3.task_id = "t2"
        te3.generation_id = "g2"

        by_task, by_gen = build_evaluation_indexes([te1, te2, te3])
        assert len(by_task["t1"]) == 2
        assert len(by_task["t2"]) == 1
        assert len(by_gen["g1"]) == 1
        assert "g2" in by_gen
        assert None not in by_gen

    def test_empty(self):
        from routers.projects.serializers import build_evaluation_indexes
        by_task, by_gen = build_evaluation_indexes([])
        assert by_task == {}
        assert by_gen == {}
