"""
Surgical mutation-kill tests for the LLM-as-Judge SCORING ORCHESTRATION.

Target: ``ml_evaluation/llm_judge_evaluator.py`` — the deterministic logic that
sits AROUND the (mocked) judge LLM call: score extraction, the CLAMP to the
valid range, normalization, threshold/aggregate logic, verdict determination,
result-dict assembly, and graceful handling of malformed / None judge output.

These tests do NOT call a real LLM. The AI service is a MagicMock whose
``generate`` / ``generate_structured`` returns a FIXED judge payload, so every
assertion pins the *arithmetic and control flow* the evaluator applies to that
payload, never the mocked content itself.

Scope vs. the existing suites (test_llm_judge_evaluator.py / _branches / _more):
those cover the happy paths plus a few clamp/parse cases. This file adds the
BOUNDARY + OPERATOR layer they miss:

  * ``_evaluate_single_criterion`` — the LOWER clamp + every exact bound, on all
    three score scales (``1-5`` / ``0-1`` / ``0-100``). A judge returning 7 on a
    0-5 scale must clamp to 5, NOT pass through. The existing suite only tested
    the 1-5 high clamp.
  * ``evaluate`` — the TOP-LEVEL entry, which had NO direct test anywhere in the
    judge suites. Pins criteria selection, the ``(avg-1)/4`` normalization vs the
    ``0-1`` passthrough, the ``_raw`` companion metric, the ``llm_judge_overall``
    aggregate, and the failure-dict-skipping guard.
  * ``_evaluate_multidim_single_call`` — the model-total trust TOLERANCE boundary
    (``abs(model_total - total) <= 0.5``: ``0.5`` trusted, ``0.51`` rejected),
    per-dimension clamp at both ends, and missing-dimension default.
  * ``evaluate_pairwise`` — the parse-failure → TIE fallthrough and the empty
    ``justification`` default, beyond the A/B/tie cases already covered.

Every numeric expectation is hand-computed in the test's docstring.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Mirror the path bootstrap the sibling judge suites use.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.base_evaluator import EvaluationConfig  # noqa: E402
from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers — reuse the established mock idiom: a MagicMock ai_service whose
# .generate / .generate_structured returns a fixed dict with success/content.
# ---------------------------------------------------------------------------


def _make_evaluator(**kwargs):
    """Construct an evaluator with a MagicMock ai_service (overridable)."""
    defaults = {"ai_service": MagicMock(), "judge_model": "judge-x"}
    defaults.update(kwargs)
    return LLMJudgeEvaluator(**defaults)


def _score_payload(score):
    """A successful single-criterion judge response carrying ``score``."""
    return {
        "success": True,
        "content": '{"score": %s, "justification": "j"}' % repr(score),
        "usage": {},
        "metadata": {},
    }


# Four-dimension Grundprinzipien-style rubric used for the multi-dim path.
# Sum of max_score = 40 + 25 + 25 + 10 = 100.
_MULTIDIM_CRITERIA = {
    "result_correctness": {"name": "RC", "description": "", "rubric": "", "max_score": 40},
    "legal_knowledge": {"name": "LK", "description": "", "rubric": "", "max_score": 25},
    "subsumption": {"name": "SU", "description": "", "rubric": "", "max_score": 25},
    "clarity": {"name": "CL", "description": "", "rubric": "", "max_score": 10},
}


def _multidim_content(rc, lk, su, cl, total):
    return (
        '{"scores": {'
        '"result_correctness": {"score": %s, "max": 40, "reason": ""},'
        '"legal_knowledge": {"score": %s, "max": 25, "reason": ""},'
        '"subsumption": {"score": %s, "max": 25, "reason": ""},'
        '"clarity": {"score": %s, "max": 10, "reason": ""}'
        '}, "total_score": %s, "overall_assessment": "oa"}'
    ) % (repr(rc), repr(lk), repr(su), repr(cl), repr(total))


# ===========================================================================
# _evaluate_single_criterion — the CLAMP, on all three scales + both bounds.
# This is the heart of "a wrong/missing clamp lets an out-of-range judge score
# through". The existing suite only pinned the 1-5 HIGH clamp (10 -> 5).
# ===========================================================================


class TestSingleCriterionClamp1to5:
    """Default ``1-5`` scale: score = max(1.0, min(5.0, raw))."""

    def _run(self, raw):
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5")
        ev.ai_service.generate.return_value = _score_payload(raw)
        return ev._evaluate_single_criterion(
            context="c", ground_truth="g", prediction="p", criterion="helpfulness"
        )

    def test_below_min_clamps_up_to_1(self):
        """raw 0 -> min(5,0)=0 -> max(1,0)=1.0. Catches a dropped lower clamp
        (which would leak 0) or a flipped max/min."""
        assert self._run(0)["score"] == 1.0

    def test_negative_clamps_up_to_1(self):
        """raw -3 -> 1.0. A missing lower clamp would let -3 through."""
        assert self._run(-3)["score"] == 1.0

    def test_exact_min_bound_passes_through(self):
        """raw 1 sits ON the lower bound -> 1.0 unchanged (clamp must not push
        a valid boundary value off it)."""
        assert self._run(1)["score"] == 1.0

    def test_exact_max_bound_passes_through(self):
        """raw 5 sits ON the upper bound -> 5.0 unchanged."""
        assert self._run(5)["score"] == 5.0

    def test_just_above_max_clamps_to_5(self):
        """raw 5.5 -> 5.0. Tighter than the existing 10->5 test: pins that the
        bound is exactly 5, not 'some large number'."""
        assert self._run(5.5)["score"] == 5.0

    def test_in_range_float_unchanged(self):
        """raw 3.5 is interior -> passes through verbatim (no rounding)."""
        assert self._run(3.5)["score"] == 3.5


class TestSingleCriterionClamp0to1:
    """``0-1`` scale: score = max(0.0, min(1.0, raw))."""

    def _run(self, raw):
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="0-1")
        ev.ai_service.generate.return_value = _score_payload(raw)
        return ev._evaluate_single_criterion(
            context="c", ground_truth="g", prediction="p", criterion="helpfulness"
        )

    def test_above_one_clamps_to_1(self):
        """raw 1.5 -> 1.0. If the 0-1 branch were missing, the 1-5 fallback
        (min 1.0) would also yield 1.0 here — so pair with the below-zero test
        which only the 0-1 branch handles."""
        assert self._run(1.5)["score"] == 1.0

    def test_below_zero_clamps_to_0(self):
        """raw -0.2 -> 0.0. The 1-5 fallback would WRONGLY clamp this to 1.0,
        so this kills 'wrong scale branch selected'."""
        assert self._run(-0.2)["score"] == 0.0

    def test_exact_zero_passes(self):
        """raw 0 -> 0.0 (lower bound stays)."""
        assert self._run(0)["score"] == 0.0

    def test_exact_one_passes(self):
        """raw 1 -> 1.0 (upper bound stays)."""
        assert self._run(1)["score"] == 1.0

    def test_interior_unchanged(self):
        """raw 0.42 interior -> verbatim."""
        assert self._run(0.42)["score"] == 0.42


class TestSingleCriterionClamp0to100:
    """``0-100`` scale: score = max(0.0, min(100.0, raw))."""

    def _run(self, raw):
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="0-100")
        ev.ai_service.generate.return_value = _score_payload(raw)
        return ev._evaluate_single_criterion(
            context="c", ground_truth="g", prediction="p", criterion="helpfulness"
        )

    def test_above_hundred_clamps(self):
        """raw 150 -> 100.0."""
        assert self._run(150)["score"] == 100.0

    def test_below_zero_clamps(self):
        """raw -5 -> 0.0."""
        assert self._run(-5)["score"] == 0.0

    def test_exact_hundred_passes(self):
        """raw 100 -> 100.0 (bound stays)."""
        assert self._run(100)["score"] == 100.0

    def test_interior_unchanged(self):
        """raw 73 interior -> 73.0."""
        assert self._run(73)["score"] == 73.0


class TestSingleCriterionScoreCoercionAndAssembly:
    """Score string->float coercion + the assembled result-dict keys."""

    def test_string_score_is_floated_then_clamped(self):
        """Judge returns ``"score": "9"`` (a STRING). ``float("9")`` = 9.0, then
        the 1-5 clamp -> 5.0. Pins the ``float(result["score"])`` coercion AND
        the clamp together."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": "9", "justification": "j"}',
            "usage": {},
            "metadata": {},
        }
        out = ev._evaluate_single_criterion(
            context="c", ground_truth="g", prediction="p", criterion="helpfulness"
        )
        assert out["score"] == 5.0

    def test_success_result_dict_has_expected_keys(self):
        """The success payload assembles score + the provenance/metadata
        envelope. Pins that ``score`` is present and the failure marker is
        absent (so the outer ``evaluate`` loop treats it as a real score)."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5")
        ev.ai_service.generate.return_value = _score_payload(4)
        out = ev._evaluate_single_criterion(
            context="c", ground_truth="g", prediction="p", criterion="helpfulness"
        )
        assert out["score"] == 4.0
        assert "error" not in out
        assert out["_judge_prompts_used"]["criterion"] == "helpfulness"
        assert out["_judge_prompts_used"]["judge_model"] == "judge-x"

    def test_parse_failure_returns_error_dict_without_score(self):
        """Unparseable content -> after retries, a failure dict with
        ``error: True`` and NO ``score`` key (so ``evaluate`` skips it).
        Distinct from the existing parse test in _branches because it asserts
        the ABSENCE of ``score`` (the guard ``evaluate`` keys on)."""
        ev = _make_evaluator(criteria=["helpfulness"], max_retries=1)
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": "no json whatsoever",
            "usage": {},
            "metadata": {},
        }
        out = ev._evaluate_single_criterion(
            context="c", ground_truth="g", prediction="p", criterion="helpfulness"
        )
        assert out is not None
        assert out.get("error") is True
        assert "score" not in out


# ===========================================================================
# evaluate(...) — TOP-LEVEL ENTRY. Untested anywhere in the judge suites.
# Pins: criteria selection, normalization (1-5 vs 0-1), the _raw companion,
# the overall aggregate, and the failure-dict-skipping guard.
# ===========================================================================


def _task(model_id, gt="reference", pred="prediction"):
    """Minimal task dict the base extractors understand.

    extract_ground_truth -> annotations[0]["result"];
    extract_predictions  -> predictions matching model_id by model_version/id.
    """
    return {
        "data": {"text": "ctx"},
        "annotations": [{"result": gt}],
        "predictions": [{"model_version": model_id, "result": pred}],
    }


class TestEvaluateNormalizationAndAggregate:
    def test_no_ai_service_returns_error_result(self):
        """ai_service None -> early EvaluationResult with the error string and
        0 samples. Pins the guard before any criterion work."""
        ev = LLMJudgeEvaluator(ai_service=None, judge_model="j", criteria=["helpfulness"])
        res = ev.evaluate(
            "m1",
            [_task("m1")],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        assert res.error == "No AI service configured for LLM judge"
        assert res.samples_evaluated == 0

    def test_single_criterion_1to5_normalization_and_raw(self):
        """One sample, judge score 4 on the 1-5 scale.
          raw avg = 4.0
          normalized = (4 - 1) / 4 = 0.75
          overall = mean of normalized scores = 0.75
        Pins the exact (avg-1)/4 transform AND the _raw companion metric."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5")
        ev.ai_service.generate.return_value = _score_payload(4)
        res = ev.evaluate(
            "m1",
            [_task("m1")],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        assert res.samples_evaluated == 1
        assert res.metrics["llm_judge_helpfulness"] == pytest.approx(0.75)
        assert res.metrics["llm_judge_helpfulness_raw"] == pytest.approx(4.0)
        assert res.metrics["llm_judge_overall"] == pytest.approx(0.75)

    def test_min_score_normalizes_to_zero(self):
        """Judge score 1 (the floor) -> (1-1)/4 = 0.0. Kills an off-by-one in
        the '-1' offset (e.g. (avg)/4 would give 0.25)."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5")
        ev.ai_service.generate.return_value = _score_payload(1)
        res = ev.evaluate(
            "m1",
            [_task("m1")],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        assert res.metrics["llm_judge_helpfulness"] == pytest.approx(0.0)

    def test_max_score_normalizes_to_one(self):
        """Judge score 5 (the ceiling) -> (5-1)/4 = 1.0. Kills a wrong divisor
        (e.g. /5 would give 0.8)."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5")
        ev.ai_service.generate.return_value = _score_payload(5)
        res = ev.evaluate(
            "m1",
            [_task("m1")],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        assert res.metrics["llm_judge_helpfulness"] == pytest.approx(1.0)

    def test_0to100_scale_divides_by_100(self):
        """Regression for the incomplete-ladder bug: judge score 80 on the
        0-100 scale -> 80/100 = 0.8 normalized (raw 80.0), NOT (80-1)/4 = 19.75.
        evaluate() was missing the "0-100" branch that the worker's tasks.py
        normalization ladder and the _evaluate_single_criterion clamp both have,
        so a 0-100 judge's normalized metric silently exceeded 1.0."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="0-100")
        ev.ai_service.generate.return_value = _score_payload(80)
        res = ev.evaluate(
            "m1",
            [_task("m1")],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        assert res.metrics["llm_judge_helpfulness"] == pytest.approx(0.8)
        assert res.metrics["llm_judge_helpfulness_raw"] == pytest.approx(80.0)
        assert res.metrics["llm_judge_overall"] == pytest.approx(0.8)

    def test_0to1_scale_passthrough_no_normalization(self):
        """On the 0-1 scale the avg is already 0-1, so normalized == raw.
        Judge score 0.6 -> normalized 0.6, raw 0.6. Kills 'always applies
        (avg-1)/4' which would give (0.6-1)/4 = -0.1."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="0-1")
        ev.ai_service.generate.return_value = _score_payload(0.6)
        res = ev.evaluate(
            "m1",
            [_task("m1")],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        assert res.metrics["llm_judge_helpfulness"] == pytest.approx(0.6)
        assert res.metrics["llm_judge_helpfulness_raw"] == pytest.approx(0.6)

    def test_average_over_multiple_samples(self):
        """Two samples scored 2 and 4 on the 1-5 scale.
          raw avg = (2 + 4) / 2 = 3.0
          normalized = (3 - 1) / 4 = 0.5
        Pins that aggregation averages the RAW scores then normalizes once
        (not normalize-then-average, which would also give 0.5 here, so use
        the _raw to disambiguate: raw must be exactly 3.0)."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5")
        ev.ai_service.generate.side_effect = [_score_payload(2), _score_payload(4)]
        res = ev.evaluate(
            "m1",
            [_task("m1"), _task("m1")],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        assert res.samples_evaluated == 2
        assert res.metrics["llm_judge_helpfulness_raw"] == pytest.approx(3.0)
        assert res.metrics["llm_judge_helpfulness"] == pytest.approx(0.5)

    def test_overall_is_mean_of_normalized_only(self):
        """Two criteria, scores 5 and 3.
          helpfulness: (5-1)/4 = 1.0 ; correctness: (3-1)/4 = 0.5
          overall = mean(1.0, 0.5) = 0.75
        Critically the _raw metrics (5.0, 3.0) must be EXCLUDED from the
        overall mean — including them would give a wildly different number.
        Kills 'overall averages everything including _raw'."""
        ev = _make_evaluator(criteria=["helpfulness", "correctness"], score_scale="1-5")
        ev.ai_service.generate.side_effect = [_score_payload(5), _score_payload(3)]
        res = ev.evaluate(
            "m1",
            [_task("m1")],
            EvaluationConfig(
                metrics=["llm_judge_helpfulness", "llm_judge_correctness"], model_config={}
            ),
        )
        assert res.metrics["llm_judge_helpfulness"] == pytest.approx(1.0)
        assert res.metrics["llm_judge_correctness"] == pytest.approx(0.5)
        assert res.metrics["llm_judge_overall"] == pytest.approx(0.75)

    def test_failure_dict_excluded_from_average(self):
        """First sample is a provider failure (success=False -> failure dict
        with no 'score'); second succeeds with score 4.
          Only the second contributes: raw avg = 4.0, normalized = 0.75.
        Pins the ``not result.get('error') and 'score' in result`` guard — a
        broken guard would either crash on result['score'] or fold the failure
        into the mean."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5", max_retries=1)
        ev.ai_service.generate.side_effect = [
            {"success": False, "error": "rate limit", "metadata": {"error_type": "rate_limit"}, "usage": {}},
            _score_payload(4),
        ]
        res = ev.evaluate(
            "m1",
            [_task("m1"), _task("m1")],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        # Both samples are "evaluated" (the loop increments regardless), but only
        # the scored one feeds the metric.
        assert res.samples_evaluated == 2
        assert res.metrics["llm_judge_helpfulness_raw"] == pytest.approx(4.0)
        assert res.metrics["llm_judge_helpfulness"] == pytest.approx(0.75)

    def test_overall_metric_expands_to_all_default_criteria(self):
        """A metric of ``llm_judge_overall`` selects ALL DEFAULT_CRITERIA
        (helpfulness, correctness, fluency, coherence, relevance, safety,
        accuracy = 7 criteria). With every judge call scoring 5:
          each normalized = (5-1)/4 = 1.0 ; overall = 1.0.
        Pins the 'overall' branch that replaces criteria_to_use wholesale."""
        ev = _make_evaluator(score_scale="1-5")
        ev.ai_service.generate.return_value = _score_payload(5)
        res = ev.evaluate(
            "m1",
            [_task("m1")],
            EvaluationConfig(metrics=["llm_judge_overall"], model_config={}),
        )
        # 7 default criteria each produce a normalized + a _raw metric, plus overall.
        norm_keys = [k for k in res.metrics if k.startswith("llm_judge_") and not k.endswith("_raw")]
        # 7 criteria + the overall aggregate.
        assert len(norm_keys) == 8
        assert res.metrics["llm_judge_overall"] == pytest.approx(1.0)

    def test_no_scores_yields_empty_metrics(self):
        """When ground_truth/prediction are missing the sample is skipped (no
        criterion call), so metrics stays empty and overall is never added.
        Pins the ``if scores:`` and ``if len(metrics) > 0`` guards."""
        ev = _make_evaluator(criteria=["helpfulness"], score_scale="1-5")
        task = {"data": {"text": "ctx"}, "annotations": [], "predictions": []}
        res = ev.evaluate(
            "m1",
            [task],
            EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={}),
        )
        assert res.metrics == {}
        assert "llm_judge_overall" not in res.metrics
        ev.ai_service.generate.assert_not_called()


# ===========================================================================
# _evaluate_multidim_single_call — per-dim clamp at both bounds, the model-total
# trust TOLERANCE boundary, and missing-dimension default.
# ===========================================================================


class TestMultidimClampAndTotal:
    def _ev(self):
        return _make_evaluator(
            custom_criteria=_MULTIDIM_CRITERIA,
            custom_prompt_template="Fall: {{fall}}",
        )

    def _run(self, content):
        ev = self._ev()
        ev.ai_service.generate_structured.return_value = {
            "success": True,
            "content": content,
            "usage": {},
            "metadata": {},
        }
        return ev._evaluate_multidim_single_call(
            context="", ground_truth="g", prediction="p", task_data={"fall": "x"}
        )

    def test_per_dim_clamped_high_and_low(self):
        """rc=999 -> clamp to 40 ; lk=-5 -> clamp to 0 ; su=25 (bound) -> 25 ;
        cl=10 (bound) -> 10. summed total = 40 + 0 + 25 + 10 = 75. The model's
        declared total (75) is within 0.5 of summed -> trusted -> 75."""
        out = self._run(_multidim_content(999, -5, 25, 10, 75))
        assert out["scores"]["result_correctness"]["score"] == 40.0
        assert out["scores"]["legal_knowledge"]["score"] == 0.0
        assert out["scores"]["subsumption"]["score"] == 25.0
        assert out["scores"]["clarity"]["score"] == 10.0
        assert out["total_score"] == pytest.approx(75.0)
        assert out["total_max"] == pytest.approx(100.0)

    def test_model_total_trusted_at_exact_tolerance_boundary(self):
        """Summed = 10 + 10 + 10 + 5 = 35. Model declares total 35.5.
          abs(35.5 - 35) = 0.5  ->  <= 0.5 is TRUE  ->  model total trusted.
        Result total_score = 35.5 (the model's value, not the sum). This pins
        the boundary uses ``<=`` not ``<``."""
        out = self._run(_multidim_content(10, 10, 10, 5, 35.5))
        assert out["total_score"] == pytest.approx(35.5)

    def test_model_total_rejected_just_past_tolerance(self):
        """Summed = 35 again. Model declares 35.6.
          abs(35.6 - 35) = 0.6  ->  <= 0.5 is FALSE  ->  fall back to summed 35.
        Pins that just past the boundary the summed value wins."""
        out = self._run(_multidim_content(10, 10, 10, 5, 35.6))
        assert out["total_score"] == pytest.approx(35.0)

    def test_missing_dimension_defaults_to_zero(self):
        """When a dimension is absent from the judge's ``scores`` object it
        defaults to score 0 (``scores_in.get(key) or {}`` -> ``{}`` ->
        ``float({}.get('score', 0))`` = 0). Here only result_correctness is
        present (38); the other three default to 0.
          summed = 38 + 0 + 0 + 0 = 38 ; model total 38 -> trusted."""
        content = (
            '{"scores": {'
            '"result_correctness": {"score": 38, "max": 40, "reason": ""}'
            '}, "total_score": 38, "overall_assessment": ""}'
        )
        out = self._run(content)
        assert out["scores"]["result_correctness"]["score"] == 38.0
        assert out["scores"]["legal_knowledge"]["score"] == 0.0
        assert out["scores"]["subsumption"]["score"] == 0.0
        assert out["scores"]["clarity"]["score"] == 0.0
        assert out["total_score"] == pytest.approx(38.0)

    def test_bare_numeric_dim_score_coerced_and_clamped(self):
        """A dimension given as a bare number (not an object) is wrapped:
        ``raw = {"score": float(raw), "reason": ""}``. Here clarity=99 (bare) on
        a max of 10 -> clamped to 10. The others are objects scoring 0.
          summed = 0 + 0 + 0 + 10 = 10."""
        content = (
            '{"scores": {'
            '"result_correctness": {"score": 0, "max": 40, "reason": ""},'
            '"legal_knowledge": {"score": 0, "max": 25, "reason": ""},'
            '"subsumption": {"score": 0, "max": 25, "reason": ""},'
            '"clarity": 99'
            '}, "total_score": 10, "overall_assessment": ""}'
        )
        out = self._run(content)
        assert out["scores"]["clarity"]["score"] == 10.0
        assert out["total_score"] == pytest.approx(10.0)

    def test_interior_dim_scores_untouched_and_summed(self):
        """All four interior: rc=20, lk=12, su=8, cl=4. None clamped.
          summed = 20 + 12 + 8 + 4 = 44 ; model total 44 -> trusted -> 44.
        Pins the addition operator in the total accumulation (a '-' or wrong
        accumulator would diverge)."""
        out = self._run(_multidim_content(20, 12, 8, 4, 44))
        assert out["total_score"] == pytest.approx(44.0)
        assert out["total_max"] == pytest.approx(100.0)


# ===========================================================================
# evaluate_pairwise — verdict determination + result assembly. Existing suite
# covers A / b->B / tie->TIE / provider-failure->TIE. These add the PARSE
# failure fallthrough and the missing-justification default.
# ===========================================================================


class TestPairwiseVerdict:
    def test_uppercases_verdict_and_carries_justification(self):
        """Judge says preference 'a' -> uppercased to 'A'; justification carried
        verbatim; criterion echoed back. Pins the .upper() + assembly."""
        ev = _make_evaluator()
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"preference": "a", "justification": "A reads cleaner"}',
        }
        out = ev.evaluate_pairwise(
            context="c", ground_truth="g", response_a="A", response_b="B", criterion="fluency"
        )
        assert out["preference"] == "A"
        assert out["justification"] == "A reads cleaner"
        assert out["criterion"] == "fluency"

    def test_parse_failure_falls_through_to_tie(self):
        """Provider succeeds but the content has NO ``preference`` key, so the
        ``if result and "preference" in result`` guard never returns; after the
        retry loop exhausts we hit the terminal TIE. Pins that an unparseable
        verdict is a TIE, not a crash and not a stale A/B. Uses max_retries=1 so
        we don't sleep through backoff."""
        ev = _make_evaluator(max_retries=1)
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": "the judge waffled and emitted no verdict json",
        }
        out = ev.evaluate_pairwise(
            context="c", ground_truth="g", response_a="A", response_b="B", criterion="helpfulness"
        )
        assert out["preference"] == "TIE"
        assert out["criterion"] == "helpfulness"

    def test_missing_justification_defaults_to_empty_string(self):
        """Judge returns a verdict with no ``justification`` field. The assembly
        uses ``result.get("justification", "")`` -> empty string, not a KeyError.
        Verdict 'B' still surfaces."""
        ev = _make_evaluator()
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"preference": "B"}',
        }
        out = ev.evaluate_pairwise(
            context="c", ground_truth="g", response_a="A", response_b="B", criterion="correctness"
        )
        assert out["preference"] == "B"
        assert out["justification"] == ""

    def test_tie_verdict_normalizes_casing(self):
        """A mixed-case 'TiE' verdict normalizes to 'TIE' via .upper() — pins
        that the literal compare/assembly is case-insensitive on the way out
        (distinct from the existing lowercase 'tie' case)."""
        ev = _make_evaluator()
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"preference": "TiE", "justification": "even"}',
        }
        out = ev.evaluate_pairwise(
            context="c", ground_truth="g", response_a="A", response_b="B", criterion="helpfulness"
        )
        assert out["preference"] == "TIE"
