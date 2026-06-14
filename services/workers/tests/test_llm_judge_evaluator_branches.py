"""
Branch-coverage tests for ml_evaluation/llm_judge_evaluator.py.

Targets the module-level helpers and multi-dimension single-call path the
existing suite (test_ml_evaluation_deep_coverage.py / test_llm_judge_evaluator.py)
doesn't reach:

  * ``_extract_call_metadata`` — flattening usage + metadata,
  * ``_preprocess_jinja_placeholders`` — {{var}} -> {var},
  * ``_half_point_enum`` — half-point score enums,
  * ``_build_rubric_json_schema`` — strict OpenAI schema construction,
  * ``_parse_multidim_response`` — direct / fenced / brace-matched JSON,
  * ``is_multidim_mode`` — max_score detection,
  * ``_evaluate_multidim_single_call`` — config error, success, clamping,
    parse-failure dict, provider-failure dict,
  * ``_evaluate_single_criterion`` failure-dict provenance (provider exhausted,
    parse failure, falloesung guard),
  * ``evaluate_pairwise`` success path.

The AI service is a MagicMock; no real provider call is ever made. Mirrors the
mocking idioms in test_ml_evaluation_deep_coverage.py (TestLLMJudgeDeepCoverage).
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_evaluator(**kwargs):
    from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

    defaults = {"ai_service": MagicMock(), "judge_model": "test-model"}
    defaults.update(kwargs)
    return LLMJudgeEvaluator(**defaults)


# ============================================================================
# Module-level helpers
# ============================================================================


class TestModuleHelpers:
    def test_extract_call_metadata_flattens_usage_and_metadata(self):
        from ml_evaluation.llm_judge_evaluator import _extract_call_metadata

        response = {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "total_tokens": 125,
            },
            "metadata": {
                "seed": 42,
                "finish_reason": "stop",
                "temperature": 0.0,
                "provider_name": "openai",
                # not in the allow-list -> dropped
                "internal_debug": "should not appear",
            },
        }
        out = _extract_call_metadata(response)
        assert out["input_tokens"] == 100
        assert out["output_tokens"] == 25
        assert out["total_tokens"] == 125
        assert out["seed"] == 42
        assert out["finish_reason"] == "stop"
        assert out["provider_name"] == "openai"
        assert "internal_debug" not in out

    def test_extract_call_metadata_missing_blocks(self):
        from ml_evaluation.llm_judge_evaluator import _extract_call_metadata

        out = _extract_call_metadata({})
        assert out["input_tokens"] is None
        assert out["output_tokens"] is None
        assert out["total_tokens"] is None

    def test_preprocess_jinja_placeholders(self):
        from ml_evaluation.llm_judge_evaluator import _preprocess_jinja_placeholders

        assert _preprocess_jinja_placeholders("Score {{fall}} now") == "Score {fall} now"
        # single-brace passes through unchanged
        assert _preprocess_jinja_placeholders("keep {var}") == "keep {var}"
        # multiple
        assert (
            _preprocess_jinja_placeholders("{{a}} and {{b}}") == "{a} and {b}"
        )

    def test_half_point_enum(self):
        from ml_evaluation.llm_judge_evaluator import _half_point_enum

        assert _half_point_enum(2.0) == [0.0, 0.5, 1.0, 1.5, 2.0]
        assert _half_point_enum(1.0) == [0.0, 0.5, 1.0]
        assert _half_point_enum(0.0) == [0.0]

    def test_build_rubric_json_schema_strict_shape(self):
        from ml_evaluation.llm_judge_evaluator import _build_rubric_json_schema

        criteria = {
            "subsumtion": {"max_score": 2.0},
            "ergebnis": {"max_score": 1.0},
            # no max_score -> skipped from the schema
            "freitext": {"description": "notes"},
        }
        schema = _build_rubric_json_schema(criteria)
        scores_props = schema["properties"]["scores"]["properties"]
        assert "subsumtion" in scores_props
        assert "ergebnis" in scores_props
        assert "freitext" not in scores_props
        # strict mode requires closed objects + all keys required
        assert schema["properties"]["scores"]["additionalProperties"] is False
        assert set(schema["properties"]["scores"]["required"]) == {
            "subsumtion",
            "ergebnis",
        }
        # per-dimension score is enum-constrained, max is const-locked
        sub = scores_props["subsumtion"]
        assert sub["properties"]["score"]["enum"] == [0.0, 0.5, 1.0, 1.5, 2.0]
        assert sub["properties"]["max"]["const"] == 2.0
        assert sub["additionalProperties"] is False
        assert schema["required"] == ["scores", "total_score", "overall_assessment"]


# ============================================================================
# _parse_multidim_response
# ============================================================================


class TestParseMultidimResponse:
    def test_direct_json(self):
        from ml_evaluation.llm_judge_evaluator import _parse_multidim_response

        out = _parse_multidim_response('{"scores": {"a": {"score": 1}}, "total_score": 1}')
        assert out["scores"]["a"]["score"] == 1

    def test_fenced_json_block(self):
        from ml_evaluation.llm_judge_evaluator import _parse_multidim_response

        content = 'Here is my evaluation:\n```json\n{"scores": {"x": {"score": 2}}}\n```\nDone.'
        out = _parse_multidim_response(content)
        assert out["scores"]["x"]["score"] == 2

    def test_brace_matched_largest_with_scores(self):
        from ml_evaluation.llm_judge_evaluator import _parse_multidim_response

        # A small leading object without "scores" then the real one.
        content = 'prefix {"note": 1} then {"scores": {"y": {"score": 3}}, "total_score": 3} suffix'
        out = _parse_multidim_response(content)
        assert out["scores"]["y"]["score"] == 3

    def test_unparseable_returns_none(self):
        from ml_evaluation.llm_judge_evaluator import _parse_multidim_response

        assert _parse_multidim_response("no json here at all") is None

    def test_none_content_returns_none(self):
        from ml_evaluation.llm_judge_evaluator import _parse_multidim_response

        assert _parse_multidim_response(None) is None


# ============================================================================
# is_multidim_mode
# ============================================================================


class TestIsMultidimMode:
    def test_true_when_any_criterion_has_max_score(self):
        ev = _make_evaluator(custom_criteria={"a": {"max_score": 2.0}})
        assert ev.is_multidim_mode() is True

    def test_false_when_no_max_score(self):
        ev = _make_evaluator(custom_criteria={"a": {"description": "no max"}})
        assert ev.is_multidim_mode() is False

    def test_false_when_no_custom_criteria(self):
        ev = _make_evaluator()
        assert ev.is_multidim_mode() is False


# ============================================================================
# _evaluate_multidim_single_call
# ============================================================================


class TestEvaluateMultidimSingleCall:
    def _multidim_evaluator(self, **kwargs):
        defaults = {
            "custom_criteria": {
                "subsumtion": {"max_score": 2.0},
                "ergebnis": {"max_score": 1.0},
            },
            "custom_prompt_template": "Bewerte {{fall}}: {prediction}",
        }
        defaults.update(kwargs)
        return _make_evaluator(**defaults)

    def test_missing_template_is_config_error(self):
        ev = self._multidim_evaluator(custom_prompt_template=None)
        result = ev._evaluate_multidim_single_call("ctx", "gt", "pred")
        assert result["error"] is True
        assert result["_call_metadata"]["error_type"] == "config_error"

    def test_success_clamps_and_sums(self):
        ev = self._multidim_evaluator()
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": (
                '{"scores": {"subsumtion": {"score": 5.0, "reason": "over max"}, '
                '"ergebnis": {"score": 0.5, "reason": "ok"}}, '
                '"total_score": 2.5, "overall_assessment": "solid"}'
            ),
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "metadata": {"finish_reason": "stop"},
        }
        result = ev._evaluate_multidim_single_call(
            "ctx", "gt", "pred", task_data={"fall": "Sachverhalt"}
        )
        # subsumtion 5.0 clamps to max 2.0; ergebnis stays 0.5
        assert result["scores"]["subsumtion"]["score"] == 2.0
        assert result["scores"]["ergebnis"]["score"] == 0.5
        assert result["total_max"] == 3.0
        # model total_score 2.5 differs from summed 2.5 by 0 -> trusted
        assert result["total_score"] == 2.5
        assert result["overall_assessment"] == "solid"
        assert result["_call_metadata"]["total_tokens"] == 15

    def test_summed_total_used_when_model_total_far_off(self):
        ev = self._multidim_evaluator()
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": (
                '{"scores": {"subsumtion": {"score": 1.0}, "ergebnis": {"score": 1.0}}, '
                '"total_score": 99.0, "overall_assessment": ""}'
            ),
            "usage": {},
            "metadata": {},
        }
        result = ev._evaluate_multidim_single_call("ctx", "gt", "pred")
        # model total 99 is > 0.5 off the summed 2.0 -> summed value used
        assert result["total_score"] == 2.0

    def test_bare_numeric_score_normalized(self):
        """A dimension returned as a bare number (not a dict) is coerced."""
        ev = self._multidim_evaluator()
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": '{"scores": {"subsumtion": 1.5, "ergebnis": 1.0}, "overall_assessment": ""}',
            "usage": {},
            "metadata": {},
        }
        result = ev._evaluate_multidim_single_call("ctx", "gt", "pred")
        assert result["scores"]["subsumtion"]["score"] == 1.5
        assert result["scores"]["subsumtion"]["reason"] == ""

    def test_provider_failure_returns_error_dict(self):
        ev = self._multidim_evaluator(max_retries=1)
        ev.ai_service.generate_structured.return_value = {
            "success": False,
            "error": "rate limited",
            "content": "",
            "metadata": {"error_type": "rate_limit"},
            "usage": {},
        }
        result = ev._evaluate_multidim_single_call("ctx", "gt", "pred")
        assert result["error"] is True
        assert result["error_message"] == "rate limited"

    def test_parse_failure_returns_error_dict(self):
        ev = self._multidim_evaluator(max_retries=1)
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": "this is not json",
            "usage": {},
            "metadata": {},
        }
        result = ev._evaluate_multidim_single_call("ctx", "gt", "pred")
        assert result["error"] is True
        assert result["_call_metadata"]["error_type"] == "parse_error"

    def test_field_outputs_bind_into_template(self):
        """field_outputs keys auto-bind so {{kurzantwort}} resolves; non-string
        values are JSON-encoded."""
        ev = self._multidim_evaluator(
            custom_prompt_template="Frage {{fall}} Antwort {{kurzantwort}}: {prediction}"
        )
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": '{"scores": {"subsumtion": {"score": 1.0}, "ergebnis": {"score": 1.0}}, "overall_assessment": ""}',
            "usage": {},
            "metadata": {},
        }
        result = ev._evaluate_multidim_single_call(
            "ctx",
            "gt",
            "pred",
            task_data={"fall": "S"},
            field_outputs={"kurzantwort": ["a", "b"]},
        )
        prompt = result["_judge_prompts_used"]["evaluation_prompt"]
        assert "S" in prompt
        # list field JSON-encoded
        assert '["a", "b"]' in prompt


# ============================================================================
# _evaluate_single_criterion failure & guard branches
# ============================================================================


class TestSingleCriterionBranches:
    def test_falloesung_guard_raises(self):
        ev = _make_evaluator()
        with pytest.raises(RuntimeError, match="benger_extended"):
            ev._evaluate_single_criterion("ctx", "gt", "pred", "falloesung_xyz")

    def test_provider_exhausted_returns_failure_dict(self):
        ev = _make_evaluator(max_retries=2)
        ev.ai_service.generate.return_value = {
            "success": False,
            "error": "provider exhausted retries",
            "content": "",
            "metadata": {"error_type": "rate_limit"},
            "usage": {},
        }
        result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result is not None
        assert result["error"] is True
        assert result["error_message"] == "provider exhausted retries"
        # broke out of the retry loop without retrying provider-side failures
        assert ev.ai_service.generate.call_count == 1

    def test_parse_failure_returns_failure_dict_after_retries(self):
        ev = _make_evaluator(max_retries=2)
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": "not parseable json with no score",
            "metadata": {},
            "usage": {},
        }
        result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result is not None
        assert result["error"] is True
        assert result["_call_metadata"]["error_type"] == "parse_error"
        # parse failures ARE retried -> called max_retries times
        assert ev.ai_service.generate.call_count == 2

    def test_success_attaches_provenance_and_metadata(self):
        ev = _make_evaluator(score_scale="1-5")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "good"}',
            "metadata": {"seed": 7, "finish_reason": "stop"},
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
        result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result["score"] == 4.0
        assert result["_judge_prompts_used"]["criterion"] == "helpfulness"
        assert result["_call_metadata"]["seed"] == 7
        assert result["_call_metadata"]["total_tokens"] == 5
        assert result["_raw_output"] == result["_raw_output"]  # present


# ============================================================================
# evaluate_pairwise
# ============================================================================


class TestEvaluatePairwise:
    def test_pairwise_returns_preference_uppercased(self):
        ev = _make_evaluator()
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"preference": "a", "justification": "A is clearer"}',
        }
        result = ev.evaluate_pairwise("ctx", "gt", "resp A", "resp B", "helpfulness")
        assert result["preference"] == "A"
        assert result["justification"] == "A is clearer"
        assert result["criterion"] == "helpfulness"

    def test_pairwise_provider_failure_loops_to_tie(self):
        ev = _make_evaluator(max_retries=1)
        ev.ai_service.generate.return_value = {"success": False, "error": "down"}
        result = ev.evaluate_pairwise("ctx", "gt", "a", "b", "helpfulness")
        assert result["preference"] == "TIE"
