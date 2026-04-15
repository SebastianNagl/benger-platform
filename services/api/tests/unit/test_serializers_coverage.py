"""
Unit tests for routers/projects/serializers.py — coverage for uncovered branches.

Tests serialize_task, serialize_annotation, serialize_generation,
serialize_task_evaluation, serialize_evaluation_run, build_judge_model_lookup,
build_evaluation_indexes.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest


def _mock_dt():
    return datetime(2026, 1, 15, 12, 0, 0)


class TestIsoformat:
    def test_with_datetime(self):
        from routers.projects.serializers import _isoformat
        dt = _mock_dt()
        assert _isoformat(dt) == dt.isoformat()

    def test_with_none(self):
        from routers.projects.serializers import _isoformat
        assert _isoformat(None) is None


class TestSerializeTask:
    def _mock_task(self, **overrides):
        defaults = {
            "id": "t1", "inner_id": 1, "data": {"text": "hello"},
            "meta": {}, "is_labeled": False,
            "created_at": _mock_dt(), "updated_at": _mock_dt(),
            "project_id": "p1", "created_by": "u1", "updated_by": None,
            "total_annotations": 0, "cancelled_annotations": 0,
            "comment_count": 0, "unresolved_comment_count": 0,
            "last_comment_updated_at": None, "comment_authors": None,
            "file_upload_id": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_data_mode(self):
        from routers.projects.serializers import serialize_task
        task = self._mock_task()
        d = serialize_task(task, mode="data")
        assert d["id"] == "t1"
        assert "project_id" not in d

    def test_full_mode(self):
        from routers.projects.serializers import serialize_task
        task = self._mock_task()
        d = serialize_task(task, mode="full", total_generations=5)
        assert d["project_id"] == "p1"
        assert d["total_generations"] == 5
        assert d["created_by"] == "u1"


class TestSerializeAnnotation:
    def _mock_ann(self, **overrides):
        defaults = {
            "id": "a1", "result": [{"type": "choices"}],
            "completed_by": "u1",
            "created_at": _mock_dt(), "updated_at": _mock_dt(),
            "was_cancelled": False, "ground_truth": False,
            "lead_time": 10.5, "active_duration_ms": 5000,
            "focused_duration_ms": 4000, "tab_switches": 2,
            "task_id": "t1", "project_id": "p1", "draft": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_data_mode_no_questionnaire(self):
        from routers.projects.serializers import serialize_annotation
        ann = self._mock_ann()
        d = serialize_annotation(ann, mode="data")
        assert d["questionnaire_response"] is None

    def test_data_mode_with_questionnaire(self):
        from routers.projects.serializers import serialize_annotation
        ann = self._mock_ann()
        qr = SimpleNamespace(result={"q1": "A"}, created_at=_mock_dt())
        d = serialize_annotation(ann, mode="data", questionnaire_response=qr)
        assert d["questionnaire_response"]["result"] == {"q1": "A"}

    def test_full_mode(self):
        from routers.projects.serializers import serialize_annotation
        ann = self._mock_ann()
        d = serialize_annotation(ann, mode="full")
        assert d["task_id"] == "t1"
        assert d["project_id"] == "p1"
        assert "questionnaire_response" not in d


class TestSerializeGeneration:
    def _mock_gen(self, **overrides):
        defaults = {
            "id": "g1", "model_id": "gpt-4", "response_content": "answer",
            "case_data": {"q": "question"}, "created_at": _mock_dt(),
            "response_metadata": {}, "generation_id": "gen-1",
            "task_id": "t1", "usage_stats": {}, "status": "completed",
            "error_message": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_data_mode(self):
        from routers.projects.serializers import serialize_generation
        gen = self._mock_gen()
        d = serialize_generation(gen, mode="data")
        assert d["evaluations"] == []
        assert "generation_id" not in d

    def test_data_mode_with_evaluations(self):
        from routers.projects.serializers import serialize_generation
        gen = self._mock_gen()
        evals = [{"metric": "bleu", "score": 0.8}]
        d = serialize_generation(gen, mode="data", evaluations=evals)
        assert d["evaluations"] == evals

    def test_full_mode(self):
        from routers.projects.serializers import serialize_generation
        gen = self._mock_gen()
        d = serialize_generation(gen, mode="full")
        assert d["generation_id"] == "gen-1"
        assert d["task_id"] == "t1"
        assert "evaluations" not in d


class TestSerializeTaskEvaluation:
    def _mock_te(self, **overrides):
        defaults = {
            "id": "te1", "annotation_id": "a1", "field_name": "answer",
            "answer_type": "text", "ground_truth": "ref",
            "prediction": "pred", "metrics": {"accuracy": 0.9},
            "passed": True, "confidence_score": 0.95,
            "error_message": None, "processing_time_ms": 100,
            "created_at": _mock_dt(), "evaluation_id": "ev1",
            "task_id": "t1", "generation_id": "g1",
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_data_mode_basic(self):
        from routers.projects.serializers import serialize_task_evaluation
        te = self._mock_te()
        d = serialize_task_evaluation(te, mode="data")
        assert d["evaluation_run_id"] == "ev1"
        assert d["evaluated_model"] is None  # No eval_run provided

    def test_data_mode_with_eval_run(self):
        from routers.projects.serializers import serialize_task_evaluation
        te = self._mock_te()
        eval_run = SimpleNamespace(model_id="gpt-4")
        d = serialize_task_evaluation(te, mode="data", eval_run=eval_run)
        assert d["evaluated_model"] == "gpt-4"

    def test_data_mode_with_judge_model_lookup(self):
        from routers.projects.serializers import serialize_task_evaluation
        te = self._mock_te(field_name="cfg1:answer")
        lookup = {("ev1", "cfg1"): "claude-3"}
        d = serialize_task_evaluation(te, mode="data", judge_model_lookup=lookup)
        assert d["judge_model"] == "claude-3"

    def test_data_mode_field_without_colon(self):
        from routers.projects.serializers import serialize_task_evaluation
        te = self._mock_te(field_name="answer")
        d = serialize_task_evaluation(te, mode="data")
        assert d["judge_model"] is None

    def test_full_mode(self):
        from routers.projects.serializers import serialize_task_evaluation
        te = self._mock_te()
        d = serialize_task_evaluation(te, mode="full")
        assert d["evaluation_id"] == "ev1"
        assert d["task_id"] == "t1"
        assert d["generation_id"] == "g1"
        assert "evaluation_run_id" not in d


class TestSerializeEvaluationRun:
    def _mock_er(self, **overrides):
        defaults = {
            "id": "er1", "model_id": "gpt-4",
            "evaluation_type_ids": ["bleu"], "metrics": {"bleu": 0.8},
            "status": "completed", "samples_evaluated": 100,
            "created_at": _mock_dt(), "completed_at": _mock_dt(),
            "project_id": "p1", "task_id": "t1",
            "eval_metadata": {}, "error_message": None,
            "has_sample_results": True, "created_by": "u1",
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_data_mode(self):
        from routers.projects.serializers import serialize_evaluation_run
        er = self._mock_er()
        d = serialize_evaluation_run(er, mode="data")
        assert d["has_sample_results"] is True
        assert d["created_by"] == "u1"
        assert "project_id" not in d

    def test_full_mode(self):
        from routers.projects.serializers import serialize_evaluation_run
        er = self._mock_er()
        d = serialize_evaluation_run(er, mode="full")
        assert d["project_id"] == "p1"
        assert d["task_id"] == "t1"
        assert "has_sample_results" not in d


class TestBuildJudgeModelLookup:
    def test_empty_runs(self):
        from routers.projects.serializers import build_judge_model_lookup
        assert build_judge_model_lookup([]) == {}

    def test_new_format_judge_models(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = SimpleNamespace(
            id="er1",
            eval_metadata={"judge_models": {"cfg1": "claude-3", "cfg2": "gpt-4"}},
        )
        lookup = build_judge_model_lookup([er])
        assert lookup[("er1", "cfg1")] == "claude-3"
        assert lookup[("er1", "cfg2")] == "gpt-4"

    def test_old_format_evaluation_configs(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = SimpleNamespace(
            id="er1",
            eval_metadata={
                "evaluation_configs": [
                    {"id": "cfg1", "metric_parameters": {"judge_model": "gpt-4"}},
                ]
            },
        )
        lookup = build_judge_model_lookup([er])
        assert lookup[("er1", "cfg1")] == "gpt-4"

    def test_new_format_takes_priority(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = SimpleNamespace(
            id="er1",
            eval_metadata={
                "judge_models": {"cfg1": "claude-3"},
                "evaluation_configs": [
                    {"id": "cfg1", "metric_parameters": {"judge_model": "gpt-4"}},
                ],
            },
        )
        lookup = build_judge_model_lookup([er])
        assert lookup[("er1", "cfg1")] == "claude-3"

    def test_none_eval_metadata(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = SimpleNamespace(id="er1", eval_metadata=None)
        assert build_judge_model_lookup([er]) == {}

    def test_config_without_judge_model(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = SimpleNamespace(
            id="er1",
            eval_metadata={
                "evaluation_configs": [
                    {"id": "cfg1", "metric_parameters": {}},
                ]
            },
        )
        assert build_judge_model_lookup([er]) == {}

    def test_config_without_metric_parameters(self):
        from routers.projects.serializers import build_judge_model_lookup
        er = SimpleNamespace(
            id="er1",
            eval_metadata={
                "evaluation_configs": [{"id": "cfg1"}],
            },
        )
        assert build_judge_model_lookup([er]) == {}


class TestBuildEvaluationIndexes:
    def test_empty(self):
        from routers.projects.serializers import build_evaluation_indexes
        te_by_task, te_by_gen = build_evaluation_indexes([])
        assert te_by_task == {}
        assert te_by_gen == {}

    def test_single_evaluation_with_generation(self):
        from routers.projects.serializers import build_evaluation_indexes
        te = SimpleNamespace(task_id="t1", generation_id="g1")
        te_by_task, te_by_gen = build_evaluation_indexes([te])
        assert "t1" in te_by_task
        assert "g1" in te_by_gen

    def test_evaluation_without_generation(self):
        from routers.projects.serializers import build_evaluation_indexes
        te = SimpleNamespace(task_id="t1", generation_id=None)
        te_by_task, te_by_gen = build_evaluation_indexes([te])
        assert "t1" in te_by_task
        assert te_by_gen == {}

    def test_multiple_evaluations_same_task(self):
        from routers.projects.serializers import build_evaluation_indexes
        te1 = SimpleNamespace(task_id="t1", generation_id="g1")
        te2 = SimpleNamespace(task_id="t1", generation_id="g2")
        te_by_task, te_by_gen = build_evaluation_indexes([te1, te2])
        assert len(te_by_task["t1"]) == 2
        assert len(te_by_gen["g1"]) == 1
        assert len(te_by_gen["g2"]) == 1

    def test_multiple_tasks(self):
        from routers.projects.serializers import build_evaluation_indexes
        te1 = SimpleNamespace(task_id="t1", generation_id="g1")
        te2 = SimpleNamespace(task_id="t2", generation_id="g2")
        te_by_task, te_by_gen = build_evaluation_indexes([te1, te2])
        assert "t1" in te_by_task
        assert "t2" in te_by_task
