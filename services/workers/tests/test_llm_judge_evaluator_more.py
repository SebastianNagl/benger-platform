"""Additional branch coverage for ml_evaluation/llm_judge_evaluator.py.

Targets branches NOT reached by test_llm_judge_evaluator_branches.py,
test_llm_judge_evaluator.py, or test_ml_evaluation_deep_coverage.py:

- ``create_llm_judge_for_user`` factory — success (AI service resolved) and
  the exception-fallback path (returns a no-AI evaluator when resolution
  raises). This is the only module-level symbol with zero existing coverage.
- ``_parse_evaluation_response`` — the bare-object ``"score"`` / ``"preference"``
  regex fallbacks (when the response is neither raw JSON nor fenced JSON) and
  the JSONDecodeError-inside-each-branch paths.
- ``_evaluate_multidim_single_call`` — the auto-bind skip branches for
  non-identifier / None task_data + field_outputs keys, and the exception
  (provider raises) failure-dict path with backoff sleep stubbed.
- ``evaluate_pairwise`` — thinking_budget / reasoning_effort kwarg forwarding
  and the exception-retry path.
- ``_evaluate_single_criterion`` — the exception-retry path with the
  classify_error_type import-fallback to "unknown", and backoff sleep.

The AI service is a MagicMock; no real provider call is ever made. ``time.sleep``
is patched so backoff branches don't actually wait. Mirrors the idioms in
test_llm_judge_evaluator_branches.py.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.llm_judge_evaluator import (  # noqa: E402
    LLMJudgeEvaluator,
    create_llm_judge_for_user,
)


def _make_evaluator(**kwargs):
    defaults = {"ai_service": MagicMock(), "judge_model": "test-model"}
    defaults.update(kwargs)
    return LLMJudgeEvaluator(**defaults)


# ===========================================================================
# create_llm_judge_for_user  (factory — success + exception fallback)
# ===========================================================================


class TestCreateLLMJudgeByomRouting:
    """A custom (is_official=False) judge model must be resolved through
    get_ai_service_for_model_row (row + evaluating user's per-model
    credential), NOT the provider-keyed get_ai_service_for_user which the
    string heuristic would misroute to 'openai'. Official rows keep the old
    path."""

    def _db_returning(self, row):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        return db

    def _fake_row(self, is_official):
        r = MagicMock()
        r.id = "custom-abc" if not is_official else "gpt-4o"
        r.is_official = is_official
        return r

    def test_custom_judge_routes_through_model_row_factory(self):
        import ai_services.user_aware_ai_service  # noqa: F401

        uaas_mod = sys.modules["ai_services.user_aware_ai_service"]

        row = self._fake_row(is_official=False)
        fake_singleton = MagicMock()
        fake_singleton.get_ai_service_for_model_row.return_value = MagicMock()
        with patch.object(uaas_mod, "user_aware_ai_service", fake_singleton):
            create_llm_judge_for_user(
                db=self._db_returning(row),
                user_id="user-9",
                provider="openai",  # what the heuristic WOULD have said
                judge_model="custom-abc",
            )
        fake_singleton.get_ai_service_for_model_row.assert_called_once()
        _, kwargs = fake_singleton.get_ai_service_for_model_row.call_args
        assert kwargs["model"] is row
        assert kwargs["user_id"] == "user-9"
        fake_singleton.get_ai_service_for_user.assert_not_called()

    def test_official_judge_uses_provider_path(self):
        import ai_services.user_aware_ai_service  # noqa: F401

        uaas_mod = sys.modules["ai_services.user_aware_ai_service"]

        row = self._fake_row(is_official=True)
        fake_singleton = MagicMock()
        fake_singleton.get_ai_service_for_user.return_value = MagicMock()
        with patch.object(uaas_mod, "user_aware_ai_service", fake_singleton):
            create_llm_judge_for_user(
                db=self._db_returning(row),
                user_id="user-9",
                provider="openai",
                judge_model="gpt-4o",
            )
        fake_singleton.get_ai_service_for_user.assert_called_once()
        fake_singleton.get_ai_service_for_model_row.assert_not_called()


# ===========================================================================
# _parse_evaluation_response  (regex fallbacks for bare score/preference)
# ===========================================================================


class TestParseEvaluationResponseFallbacks:
    def test_bare_score_object_extracted_from_prose(self):
        ev = _make_evaluator()
        # Not raw JSON, no fenced block — but contains a bare {"score": ...}
        # object the score-regex recovers.
        content = 'My assessment is as follows: {"score": 4, "justification": "ok"} done.'
        out = ev._parse_evaluation_response(content)
        assert out["score"] == 4
        assert out["justification"] == "ok"

    def test_bare_preference_object_extracted_from_prose(self):
        ev = _make_evaluator()
        content = 'After review: {"preference": "A", "justification": "clearer"} end.'
        out = ev._parse_evaluation_response(content)
        assert out["preference"] == "A"

    def test_fenced_block_takes_precedence(self):
        ev = _make_evaluator()
        content = 'text\n```json\n{"score": 5}\n```\nmore'
        out = ev._parse_evaluation_response(content)
        assert out["score"] == 5

    def test_unparseable_returns_none(self):
        ev = _make_evaluator()
        assert ev._parse_evaluation_response("no json, no score, nothing") is None

    def test_malformed_score_object_returns_none(self):
        ev = _make_evaluator()
        # Has the word "score" but the brace content is invalid JSON →
        # the regex matches but json.loads raises → falls through to None.
        out = ev._parse_evaluation_response('{"score": not-valid-json}')
        assert out is None


# ===========================================================================
# _evaluate_single_criterion  (exception-retry + classify fallback + backoff)
# ===========================================================================


class TestSingleCriterionExceptionPath:
    def test_exception_retries_then_returns_failure_dict(self):
        ev = _make_evaluator(max_retries=2)
        ev.ai_service.generate.side_effect = RuntimeError("network blip")
        with patch("time.sleep") as sleep:
            result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result is not None
        assert result["error"] is True
        assert result["error_message"] == "network blip"
        # error_type comes from classify_error_type, falling back to "unknown"
        # when ai_services.base_service isn't importable in this env. Either a
        # real classification or "unknown" — both are non-None strings.
        assert isinstance(result["_call_metadata"]["error_type"], str)
        # Retried twice (generate called each attempt), backoff slept between.
        assert ev.ai_service.generate.call_count == 2
        assert sleep.call_count == 1  # only between attempt 1 and 2

    def test_thinking_budget_and_reasoning_effort_forwarded(self):
        ev = _make_evaluator(thinking_budget=2048, reasoning_effort="high")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 3, "justification": "ok"}',
            "metadata": {},
            "usage": {},
        }
        ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        _, kwargs = ev.ai_service.generate.call_args
        assert kwargs["seed"] == ev.seed
        assert kwargs["thinking_budget"] == 2048
        assert kwargs["reasoning_effort"] == "high"


# ===========================================================================
# evaluate_pairwise  (thinking/reasoning forwarding + exception retry)
# ===========================================================================


class TestEvaluatePairwiseExtra:
    def test_thinking_and_reasoning_forwarded(self):
        ev = _make_evaluator(thinking_budget=1000, reasoning_effort="low")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"preference": "b", "justification": "B better"}',
        }
        result = ev.evaluate_pairwise("ctx", "gt", "a", "b", "helpfulness")
        assert result["preference"] == "B"
        _, kwargs = ev.ai_service.generate.call_args
        assert kwargs["thinking_budget"] == 1000
        assert kwargs["reasoning_effort"] == "low"

    def test_exception_retries_then_returns_tie(self):
        ev = _make_evaluator(max_retries=2)
        ev.ai_service.generate.side_effect = RuntimeError("boom")
        with patch("time.sleep") as sleep:
            result = ev.evaluate_pairwise("ctx", "gt", "a", "b", "helpfulness")
        assert result == {
            "preference": "TIE",
            "justification": "Evaluation failed",
            "criterion": "helpfulness",
        }
        assert ev.ai_service.generate.call_count == 2
        assert sleep.call_count == 1


# ===========================================================================
# _evaluate_multidim_single_call  (auto-bind skip branches + exception path)
# ===========================================================================


class TestMultidimAutoBindSkips:
    def _multidim_evaluator(self, **kwargs):
        defaults = {
            "custom_criteria": {"subsumtion": {"max_score": 2.0}},
            "custom_prompt_template": "Bewerte: {prediction}",
        }
        defaults.update(kwargs)
        return _make_evaluator(**defaults)

    def test_non_identifier_and_none_keys_are_skipped(self):
        ev = self._multidim_evaluator()
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": '{"scores": {"subsumtion": {"score": 1.0}}, "overall_assessment": ""}',
            "usage": {},
            "metadata": {},
        }
        # task_data carries a non-identifier key ("not an id"), a non-str key
        # (123), and a None value — all must be skipped without raising. The
        # valid "fall" key binds.
        result = ev._evaluate_multidim_single_call(
            "ctx",
            "gt",
            "pred",
            task_data={"not an id": "x", 123: "y", "skipme": None, "fall": "S"},
            field_outputs={"bad key": "z", "good": "G"},
        )
        assert result["scores"]["subsumtion"]["score"] == 1.0
        # No KeyError / crash from the skipped keys — success dict returned.
        assert "error" not in result

    def test_exception_path_returns_failure_dict(self):
        ev = self._multidim_evaluator(max_retries=2)
        ev.ai_service.generate_structured.side_effect = RuntimeError("provider exploded")
        with patch("time.sleep") as sleep:
            result = ev._evaluate_multidim_single_call("ctx", "gt", "pred")
        assert result["error"] is True
        assert result["error_message"] == "provider exploded"
        assert isinstance(result["_call_metadata"]["error_type"], str)
        assert ev.ai_service.generate_structured.call_count == 2
        assert sleep.call_count == 1

    def test_thinking_budget_forwarded_on_structured_call(self):
        ev = self._multidim_evaluator(thinking_budget=4096, reasoning_effort="medium")
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": '{"scores": {"subsumtion": {"score": 2.0}}, "overall_assessment": "ok"}',
            "usage": {},
            "metadata": {},
        }
        ev._evaluate_multidim_single_call("ctx", "gt", "pred")
        _, kwargs = ev.ai_service.generate_structured.call_args
        assert kwargs["thinking_budget"] == 4096
        assert kwargs["reasoning_effort"] == "medium"
        assert kwargs["seed"] == ev.seed
