"""The judge model's reasoning reaches ``task_evaluations.raw_reasoning``.

``LLMJudgeEvaluator`` copies the provider response's ``reasoning`` into the
judge result under ``_raw_reasoning``; every row builder moves it out of the
result (``tasks._pop_judge_reasoning``, next to the ``_judge_prompts_used``
pop) into the ``raw_reasoning`` column. These tests pin each step and that
the reasoning never stays inside the metrics blob or feeds the score.
"""

import os

os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("BENGER_TEST_MODE", "1")

import json  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

import tasks as tasks_module  # noqa: E402
from evaluation.inline_judges import inline_judge_row  # noqa: E402
from tasks import _evaluate_llm_judge_single, _pop_judge_reasoning  # noqa: E402

JUDGE_REASONING = "Die Antwort nennt § 433 BGB; das reicht für Punkte."


class TestPopJudgeReasoning:
    def test_moves_reasoning_out_of_result(self):
        result = {"score": 4, "_raw_reasoning": JUDGE_REASONING}
        assert _pop_judge_reasoning(result) == JUDGE_REASONING
        assert result == {"score": 4}

    def test_absent_empty_or_non_string_is_none(self):
        assert _pop_judge_reasoning(None) is None
        assert _pop_judge_reasoning({"score": 1}) is None
        assert _pop_judge_reasoning({"_raw_reasoning": ""}) is None
        result = {"_raw_reasoning": MagicMock()}
        assert _pop_judge_reasoning(result) is None
        assert "_raw_reasoning" not in result

    def test_control_characters_stripped(self):
        assert _pop_judge_reasoning({"_raw_reasoning": "a\x00b\x07c\nd"}) == "abc\nd"


class TestEvaluatorCopiesProviderReasoning:
    def _judge(self, response):
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        ai_service = MagicMock()
        ai_service.generate.return_value = response
        return LLMJudgeEvaluator(
            ai_service=ai_service, judge_model="gpt-4o", score_scale="1-5", max_retries=1
        )

    def test_success_result_carries_reasoning_and_score_from_answer(self):
        judge = self._judge({
            "success": True,
            "content": json.dumps({"score": 4, "justification": "gut"}),
            "reasoning": JUDGE_REASONING,
            "usage": {},
            "metadata": {},
        })
        result = judge._evaluate_single_criterion(
            context="", ground_truth="ja", prediction="ja", criterion="correctness"
        )
        assert result["score"] == 4.0
        assert result["_raw_reasoning"] == JUDGE_REASONING
        assert JUDGE_REASONING not in result["_raw_output"]

    def test_provider_failure_keeps_reasoning(self):
        judge = self._judge({
            "success": False,
            "error": "boom",
            "content": "",
            "reasoning": JUDGE_REASONING,
            "usage": {},
            "metadata": {"error_type": "api_error"},
        })
        result = judge._evaluate_single_criterion(
            context="", ground_truth="ja", prediction="ja", criterion="correctness"
        )
        assert result["error"] is True
        assert result["_raw_reasoning"] == JUDGE_REASONING


class TestInlineJudgeRow:
    def test_reasoning_moved_to_column(self):
        judge = MagicMock()
        judge.compute.return_value = {
            "feedback_markdown": "ok",
            "_judge_prompts_used": {"system": "s"},
            "_raw_reasoning": JUDGE_REASONING,
        }
        seen = {}

        def _build_row(*, result, error_message):
            seen["result"] = dict(result)
            return {"metrics": {"m": {"details": result}}, "passed": True}

        judge.build_row.side_effect = _build_row
        row = inline_judge_row(
            judge,
            evaluator=MagicMock(),
            task_data={},
            prediction="p",
            metric_params={},
            row={"id": "r1"},
        )
        assert row["raw_reasoning"] == JUDGE_REASONING
        assert row["judge_prompts_used"] == {"system": "s"}
        assert "_raw_reasoning" not in seen["result"]


class TestImmediateJudgeRows:
    def _call(self, judge, metric_type):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=judge,
        ):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                _evaluate_llm_judge_single(
                    db=db,
                    record_id="r1",
                    immediate_eval_id="i1",
                    project_id="p1",
                    task_id="t1",
                    annotation_id=None,
                    user_id="u1",
                    field_name="loesung",
                    metric_type=metric_type,
                    prediction="pred",
                    reference="ref",
                    metric_params={"judge_model": "gpt-4o"},
                    organization_id=None,
                    judge_run_id="jr1",
                    evaluation_config_id="cfg1",
                )
        return db.add.call_args.args[0]

    def test_multidim_row(self):
        judge = MagicMock()
        judge.is_multidim_mode.return_value = True
        judge._evaluate_multidim_single_call.return_value = {
            "scores": {"clarity": 3},
            "total_score": 3.0,
            "total_max": 5.0,
            "_call_metadata": {},
            "_raw_output": "{}",
            "_raw_reasoning": JUDGE_REASONING,
            "_judge_prompts_used": {"system": "s"},
        }
        row = self._call(judge, "llm_judge_grundprinzipien")
        assert row.raw_reasoning == JUDGE_REASONING
        assert JUDGE_REASONING not in json.dumps(row.metrics, ensure_ascii=False)

    def test_single_criterion_row(self):
        judge = MagicMock()
        judge.is_multidim_mode.return_value = False
        judge.score_scale = "1-5"
        judge.criteria = ["correctness"]
        judge._evaluate_single_criterion.return_value = {
            "score": 5.0,
            "_raw_output": "{}",
            "_raw_reasoning": JUDGE_REASONING,
        }
        row = self._call(judge, "llm_judge_correctness")
        assert row.raw_reasoning == JUDGE_REASONING
        assert row.metrics["llm_judge_correctness"] == pytest.approx(1.0)
        assert "_raw_reasoning" not in row.metrics["llm_judge_correctness_details"]
