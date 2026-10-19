"""Overlay inline judges (core 2.41): ``evaluation/inline_judges.py``.

A judge whose result is not a score (the extended edition's feedback-only
judge) plugs in through ``benger_extended.workers.get_inline_judge``. These
tests pin the lookup (Falllösung keeps its own hooks, a missing or broken
overlay means the generic path), the row the bulk cells build from the
judge's output, the immediate lane's dispatch, and that the evaluation
planner counts a score-less result as evaluated.
"""

import sys
import types
from unittest.mock import MagicMock, patch

from evaluation.inline_judges import inline_judge_row, resolve_inline_judge
from evaluation_planning import _row_has_score


class _Judge:
    def __init__(self, result):
        self.result = result
        self.compute_kwargs = None

    def compute(self, **kwargs):
        self.compute_kwargs = kwargs
        return self.result

    def build_row(self, *, result, error_message):
        if error_message:
            return {"metrics": {"m": {"value": None, "error": error_message}}, "passed": False}
        return {
            "metrics": {"m": {"value": None, "details": {"feedback_only": True}, "error": None}},
            "passed": True,
        }


def _overlay(get_inline_judge):
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    workers.get_inline_judge = get_inline_judge
    pkg.workers = workers
    return patch.dict(sys.modules, {"benger_extended": pkg, "benger_extended.workers": workers})


class TestResolve:
    def test_returns_the_overlay_judge(self):
        judge = object()
        with _overlay(lambda metric: judge if metric == "llm_judge_feedback" else None):
            assert resolve_inline_judge("llm_judge_feedback") is judge
            assert resolve_inline_judge("llm_judge_custom") is None

    def test_falloesung_keeps_its_dedicated_hooks(self):
        lookup = MagicMock(return_value=object())
        with _overlay(lookup):
            assert resolve_inline_judge("llm_judge_falloesung") is None
        lookup.assert_not_called()

    def test_community_edition_has_none(self):
        with patch.dict(sys.modules, {"benger_extended": None, "benger_extended.workers": None}):
            assert resolve_inline_judge("llm_judge_feedback") is None

    def test_an_overlay_without_the_hook_has_none(self):
        pkg = types.ModuleType("benger_extended")
        workers = types.ModuleType("benger_extended.workers")
        with patch.dict(sys.modules, {"benger_extended": pkg, "benger_extended.workers": workers}):
            assert resolve_inline_judge("llm_judge_feedback") is None

    def test_a_raising_overlay_falls_back_to_none(self):
        def boom(metric):
            raise RuntimeError("broken overlay")

        with _overlay(boom):
            assert resolve_inline_judge("llm_judge_feedback") is None


def _evaluator():
    ev = MagicMock()
    ev.ai_service = "svc"
    ev.judge_model = "gpt-5.4-mini"
    ev.temperature = 0.0
    ev.max_tokens = 16000
    ev.thinking_budget = None
    ev.reasoning_effort = "low"
    return ev


class TestInlineJudgeRow:
    def test_success_row_carries_context_judge_output_and_audit_prompt(self):
        judge = _Judge({"feedback_markdown": "## Intro", "_judge_prompts_used": {"user": "p"}})
        row = inline_judge_row(
            judge,
            evaluator=_evaluator(),
            task_data=None,
            prediction="copie",
            metric_params={"exam_type": "fr-dissertation"},
            row={"id": "r1", "task_id": "t1"},
        )
        assert row["id"] == "r1" and row["task_id"] == "t1"
        assert row["passed"] is True
        assert row["error_message"] is None
        assert row["judge_prompts_used"] == {"user": "p"}
        assert judge.compute_kwargs == {
            "ai_service": "svc",
            "judge_model": "gpt-5.4-mini",
            "temperature": 0.0,
            "max_tokens": 16000,
            "thinking_budget": None,
            "reasoning_effort": "low",
            "task_data": {},
            "prediction": "copie",
            "metric_params": {"exam_type": "fr-dissertation"},
        }

    def test_error_wrapper_becomes_an_error_row(self):
        judge = _Judge({"error": True, "error_message": "no key"})
        row = inline_judge_row(
            judge, evaluator=_evaluator(), task_data={}, prediction=None,
            metric_params=None, row={"id": "r2"},
        )
        assert row["passed"] is False
        assert row["error_message"] == "no key"
        assert judge.compute_kwargs["prediction"] == ""
        assert judge.compute_kwargs["metric_params"] == {}

    def test_no_result_is_an_error_row(self):
        row = inline_judge_row(
            _Judge(None), evaluator=_evaluator(), task_data={}, prediction="x",
            metric_params={}, row={},
        )
        assert row["error_message"] == "LLM judge evaluation failed"
        assert row["judge_prompts_used"] is None


class TestPlannerCountsFeedbackAsEvaluated:
    def test_feedback_only_row_is_evaluated(self):
        assert _row_has_score(
            {"llm_judge_feedback": {"value": None, "details": {"feedback_only": True}, "error": None}}
        ) is True

    def test_a_failed_feedback_row_is_not(self):
        assert _row_has_score(
            {"llm_judge_feedback": {"value": None, "details": {"feedback_only": True}, "error": "x"}}
        ) is False

    def test_a_null_value_without_the_marker_is_not(self):
        assert _row_has_score({"m": {"value": None, "details": {}}}) is False


class TestImmediateLane:
    def test_the_inline_judge_persists_its_own_row(self):
        import tasks as tasks_module
        from tasks import _run_immediate_config_job

        judge = MagicMock()
        judge.evaluate_single = MagicMock(
            return_value={"status": "completed", "record_id": "rec-1", "score": None}
        )
        db = MagicMock()
        job = {
            "metric_type": "llm_judge_feedback",
            "metric_params": {"exam_type": "fr-cas-pratique"},
            "field_name": "loesung",
            "prediction_value": "copie",
            "reference_value": "",
            "judge_run_id": "jr-1",
            "evaluation_config_id": "cfg-1",
            "record_id": "rec-1",
        }
        with patch.object(tasks_module, "SessionLocal", return_value=db), patch(
            "evaluation.orchestration.resolve_inline_judge", return_value=judge
        ):
            result = _run_immediate_config_job(
                job=job,
                dispatch_eval_id="eval-1",
                project_id="proj-1",
                task_id="task-1",
                annotation_id="ann-1",
                organization_id=None,
                user_id="user-1",
                task_data={"sachverhalt": "Cas"},
            )
        assert result == {"status": "completed", "record_id": "rec-1", "score": None}
        kwargs = judge.evaluate_single.call_args.kwargs
        assert kwargs["metric"] == "llm_judge_feedback"
        assert kwargs["record_id"] == "rec-1"
        assert kwargs["immediate_eval_id"] == "eval-1"
        assert kwargs["judge_run_id"] == "jr-1"
        assert kwargs["evaluation_config_id"] == "cfg-1"
        assert kwargs["prediction"] == "copie"
        assert kwargs["task_data"] == {"sachverhalt": "Cas"}
        db.close.assert_called_once()

