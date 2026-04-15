"""Unit tests for shared serialization functions."""

import os
import sys
from datetime import datetime
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from routers.projects.serializers import (
    build_evaluation_indexes,
    build_judge_model_lookup,
    serialize_annotation,
    serialize_evaluation_run,
    serialize_generation,
    serialize_task,
    serialize_task_evaluation,
)


def _mock_task(**overrides):
    t = Mock()
    t.id = "task-1"
    t.inner_id = 1
    t.project_id = "proj-1"
    t.data = {"text": "hello"}
    t.meta = {}
    t.is_labeled = True
    t.created_at = datetime(2026, 1, 1, 12, 0, 0)
    t.updated_at = datetime(2026, 1, 2, 12, 0, 0)
    t.created_by = "user-1"
    t.updated_by = "user-2"
    t.total_annotations = 2
    t.cancelled_annotations = 0
    t.comment_count = 1
    t.unresolved_comment_count = 0
    t.last_comment_updated_at = None
    t.comment_authors = []
    t.file_upload_id = None
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


def _mock_annotation(**overrides):
    a = Mock()
    a.id = "ann-1"
    a.task_id = "task-1"
    a.project_id = "proj-1"
    a.result = [{"from_name": "label", "value": {"choices": ["A"]}}]
    a.completed_by = "user-1"
    a.created_at = datetime(2026, 1, 1)
    a.updated_at = datetime(2026, 1, 2)
    a.was_cancelled = False
    a.ground_truth = False
    a.lead_time = 10.5
    a.active_duration_ms = 5000
    a.focused_duration_ms = 4000
    a.tab_switches = 1
    a.draft = None
    a.prediction_scores = None
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


def _mock_generation(**overrides):
    g = Mock()
    g.id = "gen-1"
    g.generation_id = "resp-gen-1"
    g.task_id = "task-1"
    g.model_id = "gpt-4o"
    g.response_content = "Response text"
    g.case_data = {"prompt": "test"}
    g.created_at = datetime(2026, 1, 3)
    g.response_metadata = {"tokens": 100}
    g.usage_stats = {"total_tokens": 100}
    g.status = "completed"
    g.error_message = None
    for k, v in overrides.items():
        setattr(g, k, v)
    return g


def _mock_task_evaluation(**overrides):
    te = Mock()
    te.id = "te-1"
    te.evaluation_id = "er-1"
    te.task_id = "task-1"
    te.generation_id = "gen-1"
    te.annotation_id = "ann-1"
    te.field_name = "cfg1:pred_field:ref_field"
    te.answer_type = "text"
    te.ground_truth = "expected"
    te.prediction = "actual"
    te.metrics = {"rouge1": 0.8}
    te.passed = True
    te.confidence_score = 0.95
    te.error_message = None
    te.processing_time_ms = 150
    te.created_at = datetime(2026, 1, 4)
    for k, v in overrides.items():
        setattr(te, k, v)
    return te


def _mock_evaluation_run(**overrides):
    er = Mock()
    er.id = "er-1"
    er.project_id = "proj-1"
    er.task_id = None
    er.model_id = "gpt-4o"
    er.evaluation_type_ids = ["rouge", "bleu"]
    er.metrics = {"rouge1": 0.8}
    er.status = "completed"
    er.samples_evaluated = 10
    er.created_at = datetime(2026, 1, 5)
    er.completed_at = datetime(2026, 1, 5, 1, 0)
    er.eval_metadata = {"judge_models": {"cfg1": "gpt-4o-judge"}}
    er.error_message = None
    er.has_sample_results = True
    er.created_by = "user-1"
    for k, v in overrides.items():
        setattr(er, k, v)
    return er


class TestSerializeTask:
    def test_data_mode_base_fields(self):
        task = _mock_task()
        result = serialize_task(task, mode="data")
        assert result["id"] == "task-1"
        assert result["inner_id"] == 1
        assert result["data"] == {"text": "hello"}
        assert result["is_labeled"] is True
        assert result["created_at"] == "2026-01-01T12:00:00"
        # Data mode should NOT have FK fields
        assert "project_id" not in result
        assert "created_by" not in result

    def test_full_mode_includes_fk_fields(self):
        task = _mock_task()
        result = serialize_task(task, mode="full", total_generations=3)
        assert result["project_id"] == "proj-1"
        assert result["created_by"] == "user-1"
        assert result["total_generations"] == 3
        assert result["file_upload_id"] is None

    def test_none_datetime_serialized_as_none(self):
        task = _mock_task(created_at=None)
        result = serialize_task(task, mode="data")
        assert result["created_at"] is None


class TestSerializeAnnotation:
    def test_data_mode_with_questionnaire(self):
        ann = _mock_annotation()
        qr = Mock()
        qr.result = [{"answer": "yes"}]
        qr.created_at = datetime(2026, 1, 2)
        result = serialize_annotation(ann, mode="data", questionnaire_response=qr)
        assert result["questionnaire_response"]["result"] == [{"answer": "yes"}]
        # Data mode should NOT have FK fields
        assert "task_id" not in result
        assert "project_id" not in result

    def test_data_mode_without_questionnaire(self):
        ann = _mock_annotation()
        result = serialize_annotation(ann, mode="data")
        assert result["questionnaire_response"] is None

    def test_full_mode_includes_fk_fields(self):
        ann = _mock_annotation()
        result = serialize_annotation(ann, mode="full")
        assert result["task_id"] == "task-1"
        assert result["project_id"] == "proj-1"
        assert result["draft"] is None
        assert "questionnaire_response" not in result


class TestSerializeGeneration:
    def test_data_mode_with_evaluations(self):
        gen = _mock_generation()
        evals = [{"id": "te-1", "field_name": "f1", "passed": True}]
        result = serialize_generation(gen, mode="data", evaluations=evals)
        assert result["evaluations"] == evals
        assert "generation_id" not in result
        assert "usage_stats" not in result

    def test_data_mode_default_empty_evaluations(self):
        gen = _mock_generation()
        result = serialize_generation(gen, mode="data")
        assert result["evaluations"] == []

    def test_full_mode_includes_fk_fields(self):
        gen = _mock_generation()
        result = serialize_generation(gen, mode="full")
        assert result["generation_id"] == "resp-gen-1"
        assert result["task_id"] == "task-1"
        assert result["usage_stats"] == {"total_tokens": 100}
        assert result["status"] == "completed"
        assert "evaluations" not in result


class TestSerializeTaskEvaluation:
    def test_data_mode_with_denormalized_fields(self):
        te = _mock_task_evaluation()
        er = _mock_evaluation_run()
        lookup = {("er-1", "cfg1"): "gpt-4o-judge"}
        result = serialize_task_evaluation(
            te, mode="data", eval_run=er, judge_model_lookup=lookup,
        )
        assert result["evaluation_run_id"] == "er-1"
        assert result["evaluated_model"] == "gpt-4o"
        assert result["judge_model"] == "gpt-4o-judge"
        assert result["annotation_id"] == "ann-1"
        # Data mode should NOT have raw FK fields
        assert "evaluation_id" not in result
        assert "task_id" not in result
        assert "generation_id" not in result

    def test_data_mode_no_config_id_in_field_name(self):
        te = _mock_task_evaluation(field_name="simple_field")
        result = serialize_task_evaluation(te, mode="data")
        assert result["judge_model"] is None

    def test_full_mode_includes_fk_fields(self):
        te = _mock_task_evaluation()
        result = serialize_task_evaluation(te, mode="full")
        assert result["evaluation_id"] == "er-1"
        assert result["task_id"] == "task-1"
        assert result["generation_id"] == "gen-1"
        assert "evaluation_run_id" not in result
        assert "evaluated_model" not in result


class TestSerializeEvaluationRun:
    def test_data_mode(self):
        er = _mock_evaluation_run()
        result = serialize_evaluation_run(er, mode="data")
        assert result["has_sample_results"] is True
        assert result["eval_metadata"] == {"judge_models": {"cfg1": "gpt-4o-judge"}}
        assert "project_id" not in result
        assert "task_id" not in result

    def test_full_mode(self):
        er = _mock_evaluation_run()
        result = serialize_evaluation_run(er, mode="full")
        assert result["project_id"] == "proj-1"
        assert result["task_id"] is None
        assert result["eval_metadata"] == {"judge_models": {"cfg1": "gpt-4o-judge"}}
        assert "has_sample_results" not in result


class TestBuildJudgeModelLookup:
    def test_new_format(self):
        er = _mock_evaluation_run(
            eval_metadata={"judge_models": {"cfg1": "gpt-4o", "cfg2": "claude-3"}}
        )
        lookup = build_judge_model_lookup([er])
        assert lookup[("er-1", "cfg1")] == "gpt-4o"
        assert lookup[("er-1", "cfg2")] == "claude-3"

    def test_old_format(self):
        er = _mock_evaluation_run(eval_metadata={
            "evaluation_configs": [
                {"id": "cfg1", "metric_parameters": {"judge_model": "gpt-4o"}}
            ]
        })
        lookup = build_judge_model_lookup([er])
        assert lookup[("er-1", "cfg1")] == "gpt-4o"

    def test_new_format_takes_precedence(self):
        er = _mock_evaluation_run(eval_metadata={
            "judge_models": {"cfg1": "new-model"},
            "evaluation_configs": [
                {"id": "cfg1", "metric_parameters": {"judge_model": "old-model"}}
            ]
        })
        lookup = build_judge_model_lookup([er])
        assert lookup[("er-1", "cfg1")] == "new-model"

    def test_empty_runs(self):
        assert build_judge_model_lookup([]) == {}

    def test_no_metadata(self):
        er = _mock_evaluation_run(eval_metadata=None)
        assert build_judge_model_lookup([er]) == {}


class TestBuildEvaluationIndexes:
    def test_indexes_built_correctly(self):
        te1 = _mock_task_evaluation(id="te-1", task_id="t1", generation_id="g1")
        te2 = _mock_task_evaluation(id="te-2", task_id="t1", generation_id=None)
        te3 = _mock_task_evaluation(id="te-3", task_id="t2", generation_id="g2")

        te_by_task, te_by_generation = build_evaluation_indexes([te1, te2, te3])

        assert len(te_by_task["t1"]) == 2
        assert len(te_by_task["t2"]) == 1
        assert len(te_by_generation["g1"]) == 1
        assert len(te_by_generation["g2"]) == 1
        assert "None" not in te_by_generation  # None key should not be present

    def test_empty_input(self):
        te_by_task, te_by_generation = build_evaluation_indexes([])
        assert te_by_task == {}
        assert te_by_generation == {}
