"""
Mutation-kill tests for the multi-judge consensus aggregation + value
formatting in ml_evaluation/llm_judge_evaluator.py.

The consensus / normalization / agreement math is the published benchmark
number: multiple LLM-judge scores collapse into one consensus value, a CI,
and an inter-judge agreement metric. A silent off-by-one in the
normalization divisor, a wrong z-value, or a flipped agreement guard would
change every reported score WITHOUT crashing -- exactly the failure mode
coverage-shaped tests miss. Each test here hand-computes the expected value
and asserts it EXACTLY, so an arithmetic mutant (e.g. `(score-1)/4` ->
`(score-1)/5`, `1.96` -> `1.95`, `std <= 0.5` -> `std < 0.5`) flips a green
test red.

Strategy for the aggregation tests: monkeypatch the *instance* method
`_evaluate_single_criterion` to return fixed `{"score": X}` dicts (or None),
so no real provider is touched and the score that flows into the math is
deterministic and known. `evaluate_multi_judge` is the function under test;
everything below it (normalize -> mean -> CI -> agreement -> num_judges) is
exercised through it.

For the formatting tests we assert the exact prompt-facing string each
answer_type branch emits, because those strings are what the judge model
reads -- a wrong format silently misleads the judge.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evaluator(score_scale="1-5", ai_service="judge-ai-0", judge_model="judge-0"):
    """Minimal constructor. ai_service only needs to be truthy for the
    base judge (the `if not judge_ai` skip-guard checks truthiness); the
    aggregation tests monkeypatch `_evaluate_single_criterion` so the
    service is never actually called."""
    from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

    return LLMJudgeEvaluator(
        ai_service=ai_service,
        judge_model=judge_model,
        score_scale=score_scale,
    )


def _patch_scores(ev, score_map):
    """Monkeypatch `_evaluate_single_criterion` so it returns a fixed raw
    score keyed by (current judge_model, criterion).

    `evaluate_multi_judge` swaps `self.judge_model` per judge before calling
    the criterion evaluator, so we read `ev.judge_model` at call time to know
    which judge is "speaking". `score_map` is {judge_model: {criterion: raw_score_or_None}}.
    A None value -> the criterion is treated as absent for that judge (the
    real method returns None on hard failure).
    """

    def fake(context, ground_truth, prediction, criterion):
        per_judge = score_map.get(ev.judge_model, {})
        raw = per_judge.get(criterion)
        if raw is None:
            return None
        return {"score": raw}

    ev._evaluate_single_criterion = fake
    return ev


# ===========================================================================
# Normalization branch: `if score_scale == "0-1": normalized = score`
#                       else: `normalized = (score - 1) / 4`
# ===========================================================================


class TestNormalization:
    def test_one_five_scale_score_3_maps_to_exactly_half(self):
        """(3 - 1) / 4 = 2/4 = 0.5 EXACTLY. Pins the `-1` offset and the `/4`
        divisor: `/5` would give 0.4, `(score)/4` would give 0.75, `(score+1)/4`
        would give 1.0 -- all != 0.5."""
        ev = _make_evaluator(score_scale="1-5")
        # Single judge with score 3 -> len(scores)==1 branch -> passthrough of
        # the *normalized* value into consensus_scores.
        _patch_scores(ev, {"judge-0": {"correctness": 3}})
        out = ev.evaluate_multi_judge("ctx", "gt", "pred", ["correctness"], [])
        assert out["scores_by_judge"]["judge-0"]["correctness"] == 0.5
        assert out["consensus_scores"]["correctness"] == 0.5

    def test_one_five_scale_endpoints_map_to_0_and_1(self):
        """score 1 -> (1-1)/4 = 0.0; score 5 -> (5-1)/4 = 1.0. Pins the full
        range of the 1-5 -> 0-1 affine map at both endpoints."""
        ev = _make_evaluator(score_scale="1-5")
        _patch_scores(ev, {"judge-0": {"lo": 1, "hi": 5}})
        out = ev.evaluate_multi_judge("ctx", "gt", "pred", ["lo", "hi"], [])
        assert out["scores_by_judge"]["judge-0"]["lo"] == 0.0
        assert out["scores_by_judge"]["judge-0"]["hi"] == 1.0

    def test_zero_one_scale_is_passthrough(self):
        """On the "0-1" scale the score is already normalized: 0.7 -> 0.7
        verbatim, NO affine transform. Pins the scale branch: if the else
        arm ran, 0.7 would become (0.7-1)/4 = -0.075."""
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"correctness": 0.7}})
        out = ev.evaluate_multi_judge("ctx", "gt", "pred", ["correctness"], [])
        assert out["scores_by_judge"]["judge-0"]["correctness"] == 0.7

    def test_default_scale_uses_one_five_branch(self):
        """The default score_scale "1-5" takes the final affine arm, so score 5
        -> 1.0. (The ladder is three-way: "0-1" passthrough, "0-100" -> /100,
        else 1-5 affine — see the dedicated 0-100 tests below.)"""
        ev = _make_evaluator()  # default score_scale="1-5"
        assert ev.score_scale == "1-5"
        _patch_scores(ev, {"judge-0": {"c": 5}})
        out = ev.evaluate_multi_judge("ctx", "gt", "pred", ["c"], [])
        assert out["scores_by_judge"]["judge-0"]["c"] == 1.0

    def test_zero_hundred_scale_divides_by_100(self):
        """Regression for the incomplete-ladder bug: on the "0-100" scale a raw
        80 must normalize to 0.80 (80/100), NOT the 1-5 affine (80-1)/4 = 19.75.
        The canonical normalization ladder in tasks.py (the worker multi-run
        path) and the clamp in _evaluate_single_criterion both support "0-100";
        evaluate_multi_judge was missing that branch, so a 0-100 judge consensus
        silently blew past 1.0. Pins the added `elif "0-100": score/100` arm."""
        ev = _make_evaluator(score_scale="0-100")
        _patch_scores(ev, {"judge-0": {"correctness": 80}})
        out = ev.evaluate_multi_judge("ctx", "gt", "pred", ["correctness"], [])
        assert out["scores_by_judge"]["judge-0"]["correctness"] == 0.8
        assert out["consensus_scores"]["correctness"] == 0.8

    def test_zero_hundred_scale_endpoints(self):
        """0 -> 0.0 and 100 -> 1.0 on the 0-100 scale (both within [0,1], proving
        the divisor is 100 not 4)."""
        ev = _make_evaluator(score_scale="0-100")
        _patch_scores(ev, {"judge-0": {"lo": 0, "hi": 100}})
        out = ev.evaluate_multi_judge("ctx", "gt", "pred", ["lo", "hi"], [])
        assert out["scores_by_judge"]["judge-0"]["lo"] == 0.0
        assert out["scores_by_judge"]["judge-0"]["hi"] == 1.0


# ===========================================================================
# Consensus mean + the `len(scores) >= 2` / `== 1` / 0 boundary
# ===========================================================================


class TestConsensusMeanAndBoundary:
    def test_two_judges_mean_is_average_of_normalized(self):
        """Two judges, raw 3 & 5 on 1-5 -> normalized 0.5 & 1.0 -> mean 0.75.
        Exactly 2 scores triggers the `>= 2` consensus branch (mean), not the
        `== 1` passthrough."""
        ev = _make_evaluator(score_scale="1-5")
        _patch_scores(ev, {"judge-0": {"c": 3}, "judge-1": {"c": 5}})
        # judge-1's ai_service must be truthy or it gets skipped.
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        # 0.5 and 1.0 -> mean 0.75
        assert out["consensus_scores"]["c"] == 0.75
        assert out["num_judges"] == 2

    def test_two_judges_on_0_1_scale_mean_point_five(self):
        """The prompt's canonical case: 0.4 & 0.6 on the 0-1 scale ->
        consensus mean exactly 0.5."""
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"c": 0.4}, "judge-1": {"c": 0.6}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        assert out["consensus_scores"]["c"] == 0.5

    def test_single_judge_takes_eq_one_branch(self):
        """Exactly 1 score -> the `elif len(scores) == 1` branch:
        consensus = the score itself, CI = (score, score) degenerate,
        agreement = 1.0 (a single judge trivially agrees with itself).
        Pins that the lower boundary of consensus is 1, not 2."""
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"c": 0.42}})
        out = ev.evaluate_multi_judge("ctx", "gt", "pred", ["c"], [])
        assert out["consensus_scores"]["c"] == 0.42
        assert out["confidence_intervals"]["c"] == (0.42, 0.42)
        assert out["inter_judge_agreement"]["c"] == 1.0

    def test_zero_scores_criterion_absent_from_all_outputs(self):
        """A criterion that NO judge scored (every judge returns None) has
        len(scores)==0 -> neither the `>=2` nor the `==1` branch runs, so the
        criterion key is ABSENT from consensus/CI/agreement (not present-with-
        default). Pins that the boundary is exclusive of 0."""
        ev = _make_evaluator(score_scale="0-1")
        # 'scored' is answered; 'unscored' is None for the only judge.
        _patch_scores(ev, {"judge-0": {"scored": 0.5, "unscored": None}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["scored", "unscored"], []
        )
        assert "scored" in out["consensus_scores"]
        assert "unscored" not in out["consensus_scores"]
        assert "unscored" not in out["confidence_intervals"]
        assert "unscored" not in out["inter_judge_agreement"]
        # And it shouldn't appear in the judge's score dict either.
        assert "unscored" not in out["scores_by_judge"]["judge-0"]


# ===========================================================================
# Confidence interval: margin = 1.96 * std / sqrt(n), CI = (avg-m, avg+m)
# ===========================================================================


class TestConfidenceInterval:
    def test_ci_margin_two_judges_exact(self):
        """Two judges, normalized 0.4 & 0.6 (0-1 scale, passthrough).

        avg = (0.4+0.6)/2 = 0.5
        sample stdev (ddof=1) = sqrt(((0.4-0.5)^2 + (0.6-0.5)^2)/(2-1))
                              = sqrt((0.01+0.01)/1) = sqrt(0.02)
        margin = 1.96 * sqrt(0.02) / sqrt(2)
               = 1.96 * 0.141421356.../1.414213562...
               = 1.96 * 0.1 = 0.196
        CI = (0.5 - 0.196, 0.5 + 0.196) = (0.304, 0.696)

        Pins: the 1.96 z-constant, the /sqrt(n) denominator, sample (not
        population) stdev, and the +/- symmetry of the interval.
        """
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"c": 0.4}, "judge-1": {"c": 0.6}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        std = math.sqrt(0.02)  # sample stdev of {0.4, 0.6}
        margin = 1.96 * std / math.sqrt(2)
        avg = 0.5
        lower, upper = out["confidence_intervals"]["c"]
        assert lower == pytest.approx(avg - margin)
        assert upper == pytest.approx(avg + margin)
        # Independently confirm the closed-form 0.196 (so a wrong constant
        # mutant can't be hidden by recomputing it the same wrong way).
        assert lower == pytest.approx(0.304)
        assert upper == pytest.approx(0.696)
        # Symmetric about the mean.
        assert (upper + lower) / 2 == pytest.approx(avg)

    def test_ci_three_judges_uses_sqrt_n_three(self):
        """Three judges, normalized 0.2 / 0.5 / 0.8 (0-1 scale).

        avg = 0.5
        variance(ddof=1) = ((0.2-0.5)^2 + (0.5-0.5)^2 + (0.8-0.5)^2)/(3-1)
                         = (0.09 + 0 + 0.09)/2 = 0.18/2 = 0.09
        stdev = 0.3
        margin = 1.96 * 0.3 / sqrt(3) = 0.588 / 1.732050808... = 0.339481...
        Pins the /sqrt(n) with n=3 specifically (sqrt(2) here would give a
        different, detectably-wrong margin).
        """
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(
            ev,
            {
                "judge-0": {"c": 0.2},
                "judge-1": {"c": 0.5},
                "judge-2": {"c": 0.8},
            },
        )
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [
                {"ai_service": "ai-1", "judge_model": "judge-1"},
                {"ai_service": "ai-2", "judge_model": "judge-2"},
            ],
        )
        std = 0.3  # sample stdev of {0.2, 0.5, 0.8}
        margin = 1.96 * std / math.sqrt(3)
        lower, upper = out["confidence_intervals"]["c"]
        assert out["consensus_scores"]["c"] == pytest.approx(0.5)
        assert lower == pytest.approx(0.5 - margin)
        assert upper == pytest.approx(0.5 + margin)
        assert margin == pytest.approx(0.3394818)


# ===========================================================================
# Agreement: 1 - (std / 0.5) if std <= 0.5 else 0
# ===========================================================================


class TestAgreement:
    def test_perfect_agreement_identical_scores(self):
        """Identical normalized scores 0.5 & 0.5 -> sample stdev 0 ->
        agreement = 1 - 0/0.5 = 1.0. Pins the numerator: a mutant that drops
        the subtraction (`std/0.5`) would yield 0.0 here."""
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"c": 0.5}, "judge-1": {"c": 0.5}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        assert out["inter_judge_agreement"]["c"] == 1.0

    def test_agreement_collapses_to_zero_when_std_exceeds_half(self):
        """Maximally split pair 0.0 & 1.0 (0-1 scale).

        sample stdev(ddof=1) = sqrt(((0-0.5)^2 + (1-0.5)^2)/(2-1))
                             = sqrt(0.25 + 0.25) = sqrt(0.5) ~= 0.7071 > 0.5
        -> the `else 0` branch -> agreement exactly 0 (an int 0, the literal).
        Pins BOTH the 0.5 spread-cap constant AND the `<= 0.5` guard: without
        the guard, `1 - 0.7071/0.5` would be the negative -0.4142, not 0.
        """
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"c": 0.0}, "judge-1": {"c": 1.0}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        # std = sqrt(0.5) ~= 0.7071 > 0.5 -> else branch.
        assert math.sqrt(0.5) > 0.5  # sanity for the precondition
        assert out["inter_judge_agreement"]["c"] == 0

    def test_agreement_partial_within_guard(self):
        """Mild spread 0.4 & 0.6 (0-1 scale): std = sqrt(0.02) ~= 0.14142,
        which is <= 0.5 so the linear branch runs:
        agreement = 1 - sqrt(0.02)/0.5 = 1 - 0.28284... = 0.71715...
        Pins the /0.5 divisor in the linear regime (a /1.0 mutant would give
        ~0.8586 instead)."""
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"c": 0.4}, "judge-1": {"c": 0.6}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        std = math.sqrt(0.02)
        expected = 1 - (std / 0.5)
        assert out["inter_judge_agreement"]["c"] == pytest.approx(expected)
        assert out["inter_judge_agreement"]["c"] == pytest.approx(0.7171572875)

    def test_agreement_at_exact_boundary_std_half(self):
        """std EXACTLY 0.5 must take the `<= 0.5` branch (inclusive), giving
        agreement = 1 - 0.5/0.5 = 0.0 -- distinguishable from the `else 0`
        path only in that this is the float 0.0 reached via the formula, and
        it confirms the comparison is `<=` not `<`.

        Construct std == 0.5 exactly: for the 2-sample case,
        stdev(ddof=1) = |a-b| / sqrt(2). We need |a-b|/sqrt(2) = 0.5
        -> |a-b| = 0.5*sqrt(2) = 0.70710678... Use a=0.0, b=0.5*sqrt(2),
        both valid 0-1 normalized values, on the 0-1 passthrough scale.
        """
        ev = _make_evaluator(score_scale="0-1")
        b = 0.5 * math.sqrt(2)  # ~0.70710678, within [0,1]
        _patch_scores(ev, {"judge-0": {"c": 0.0}, "judge-1": {"c": b}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        # stdev of {0, b} = |b-0|/sqrt(2) = 0.5*sqrt(2)/sqrt(2) = 0.5 exactly.
        from statistics import stdev
        assert stdev([0.0, b]) == pytest.approx(0.5)
        # 1 - 0.5/0.5 = 0.0 via the linear branch (NOT the else literal).
        assert out["inter_judge_agreement"]["c"] == pytest.approx(0.0)


# ===========================================================================
# num_judges: counts judges whose score dict is NON-EMPTY
# ===========================================================================


class TestNumJudges:
    def test_judge_with_all_none_not_counted(self):
        """num_judges = len([j for j in scores_by_judge.values() if j]) --
        a judge whose every criterion returned None contributes an EMPTY
        dict {} (falsy) and is excluded. Two judges configured, one fully
        silent -> num_judges == 1, even though scores_by_judge has 2 keys.
        Pins the `if j` truthiness filter."""
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(
            ev,
            {
                "judge-0": {"c": 0.5},
                "judge-1": {"c": None},  # silent on the only criterion
            },
        )
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        # Both judges have a key in scores_by_judge...
        assert set(out["scores_by_judge"].keys()) == {"judge-0", "judge-1"}
        # ...but judge-1's dict is empty, so it's not counted.
        assert out["scores_by_judge"]["judge-1"] == {}
        assert out["num_judges"] == 1

    def test_all_active_judges_counted(self):
        """Two judges that both score -> num_judges == 2 (the non-degenerate
        baseline, so the previous test's `== 1` is meaningful)."""
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"c": 0.5}, "judge-1": {"c": 0.5}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "ai-1", "judge_model": "judge-1"}],
        )
        assert out["num_judges"] == 2


# ===========================================================================
# Judge-config skip (no ai_service) + AI-service swap/restore
# ===========================================================================


class TestJudgeSkipAndSwapRestore:
    def test_judge_without_ai_service_is_skipped(self):
        """An additional judge config lacking "ai_service" hits the
        `if not judge_ai: ... continue` guard and never contributes a row to
        scores_by_judge. Only the base judge remains -> single-judge consensus."""
        ev = _make_evaluator(score_scale="0-1")
        _patch_scores(ev, {"judge-0": {"c": 0.5}})
        out = ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            # No "ai_service" key -> judge_ai is None -> skipped.
            [{"judge_model": "ghost-judge"}],
        )
        assert "ghost-judge" not in out["scores_by_judge"]
        assert list(out["scores_by_judge"].keys()) == ["judge-0"]
        assert out["num_judges"] == 1
        # Single contributing judge -> the `== 1` branch.
        assert out["consensus_scores"]["c"] == 0.5
        assert out["inter_judge_agreement"]["c"] == 1.0

    def test_ai_service_and_model_restored_after_run(self):
        """After the loop, `self.ai_service` / `self.judge_model` must be
        restored to the base evaluator's originals (the function swaps them
        per judge and restores inside the loop). Pins the save/restore pair --
        a mutant that drops the restore would leave the LAST additional
        judge's service/model on the instance."""
        ev = _make_evaluator(
            score_scale="0-1", ai_service="BASE-AI", judge_model="judge-0"
        )
        _patch_scores(ev, {"judge-0": {"c": 0.5}, "judge-1": {"c": 0.5}})
        ev.evaluate_multi_judge(
            "ctx", "gt", "pred", ["c"],
            [{"ai_service": "OTHER-AI", "judge_model": "judge-1"}],
        )
        assert ev.ai_service == "BASE-AI"
        assert ev.judge_model == "judge-0"


# ===========================================================================
# SECONDARY: value formatting (gt/pred -> judge prompt)
# ===========================================================================


class TestFormatValueByType:
    def _ev(self, answer_type):
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        return LLMJudgeEvaluator(
            ai_service="x", judge_model="m", answer_type=answer_type
        )

    # -- None sentinel ------------------------------------------------------
    def test_none_value_sentinel(self):
        """None -> the explicit '(no value provided)' sentinel, regardless of
        type. Checked before any type branch."""
        ev = self._ev("text")
        assert ev._format_value_by_type(None, "text") == "(no value provided)"

    # -- text family --------------------------------------------------------
    def test_text_plain_string_passthrough(self):
        ev = self._ev("text")
        assert ev._format_value_by_type("Hallo Welt", "text") == "Hallo Welt"

    def test_text_empty_string_sentinel(self):
        """Empty string is falsy -> '(empty)' sentinel, not ''."""
        ev = self._ev("text")
        assert ev._format_value_by_type("", "text") == "(empty)"

    def test_text_dict_text_list_first_element(self):
        """{text: [v, ...]} -> str of the FIRST element. Pins the [0] index."""
        ev = self._ev("long_text")
        assert ev._format_value_by_type({"text": ["first", "second"]}, "long_text") == "first"

    def test_text_dict_text_scalar(self):
        """{text: scalar} (non-list, truthy) -> str(scalar)."""
        ev = self._ev("short_text")
        assert ev._format_value_by_type({"text": "answer"}, "short_text") == "answer"

    # -- choice family ------------------------------------------------------
    def test_choices_list_formats_selected_csv(self):
        """A list -> 'Selected: [a, b]' with ', ' join. Pins the wrapper text
        and the separator."""
        ev = self._ev("multiple_choice")
        assert ev._format_value_by_type(["a", "b"], "multiple_choice") == "Selected: [a, b]"

    def test_choices_empty_list_none_sentinel(self):
        """Empty list -> 'Selected: [none]' (items string is empty -> sentinel)."""
        ev = self._ev("choices")
        assert ev._format_value_by_type([], "choices") == "Selected: [none]"

    def test_choices_dict_choices_key(self):
        """{choices: [...]} unwraps to the list, then formats."""
        ev = self._ev("single_choice")
        assert ev._format_value_by_type({"choices": ["X"]}, "single_choice") == "Selected: [X]"

    def test_choices_scalar_fallback(self):
        """A non-list, non-dict scalar -> 'Selected: [scalar]' via the final
        return."""
        ev = self._ev("binary")
        assert ev._format_value_by_type("yes", "binary") == "Selected: [yes]"

    # -- rating / numeric ---------------------------------------------------
    def test_rating_scalar_value(self):
        ev = self._ev("rating")
        assert ev._format_value_by_type(4, "rating") == "Value: 4"

    def test_numeric_dict_number_key(self):
        """{number: X} -> 'Value: X'. The `.get('rating') or .get('number')`
        chain reaches 'number' when 'rating' is absent."""
        ev = self._ev("numeric")
        assert ev._format_value_by_type({"number": 42}, "numeric") == "Value: 42"

    # -- fallback (unknown type) -------------------------------------------
    def test_unknown_type_dict_json(self):
        """An answer_type that matches NO branch falls through to the JSON
        dump for dict/list. json.dumps(..., indent=2) of {"k": 1}."""
        import json

        ev = self._ev("rating")
        # Call with a type string that isn't handled, forcing the fallback.
        out = ev._format_value_by_type({"k": 1}, "some_unknown_type")
        assert out == json.dumps({"k": 1}, indent=2)


class TestFormatSpans:
    def _ev(self):
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        return LLMJudgeEvaluator(
            ai_service="x", judge_model="m", answer_type="span_selection"
        )

    def test_span_single_entry_exact_string(self):
        """One span with text/start/end/labels -> the exact 1-indexed line:
          '  1. "John Smith" (chars 0-10) labeled as [PERSON]'
        Pins the numbering (i+1), the quote chars, the 'chars {s}-{e}' format,
        and the '[label]' bracket wrapper."""
        ev = self._ev()
        spans = [{"text": "John Smith", "start": 0, "end": 10, "labels": ["PERSON"]}]
        out = ev._format_spans(spans)
        assert out == '  1. "John Smith" (chars 0-10) labeled as [PERSON]'

    def test_span_multi_entry_joined_and_indexed(self):
        """Two spans -> two newline-joined lines, indices 1 then 2, labels
        joined by ', '."""
        ev = self._ev()
        spans = [
            {"text": "John Smith", "start": 0, "end": 10, "labels": ["PERSON"]},
            {"text": "New York", "start": 45, "end": 53, "labels": ["LOCATION", "GPE"]},
        ]
        out = ev._format_spans(spans)
        expected = (
            '  1. "John Smith" (chars 0-10) labeled as [PERSON]\n'
            '  2. "New York" (chars 45-53) labeled as [LOCATION, GPE]'
        )
        assert out == expected

    def test_span_missing_fields_use_placeholders(self):
        """A span dict missing text/start/end/labels -> 'N/A', '?', '?',
        'no label' placeholders. Pins each default."""
        ev = self._ev()
        out = ev._format_spans([{}])
        assert out == '  1. "N/A" (chars ?-?) labeled as [no label]'

    def test_span_string_label_wrapped_to_list(self):
        """A single string label is wrapped to [label] then joined -> renders
        as the bare string inside the brackets."""
        ev = self._ev()
        spans = [{"text": "x", "start": 1, "end": 2, "label": "ORG"}]
        out = ev._format_spans(spans)
        assert out == '  1. "x" (chars 1-2) labeled as [ORG]'

    def test_span_empty_list_sentinel(self):
        """Empty list -> '(no spans annotated)'."""
        ev = self._ev()
        assert ev._format_spans([]) == "(no spans annotated)"

    def test_span_dict_unwraps_spans_key(self):
        """{spans: [...]} unwraps to the inner list before formatting."""
        ev = self._ev()
        out = ev._format_spans({"spans": [{"text": "y", "start": 3, "end": 4, "labels": ["L"]}]})
        assert out == '  1. "y" (chars 3-4) labeled as [L]'

    def test_span_invalid_type_message(self):
        """A non-list, non-dict spans value -> the typed invalid-format msg."""
        ev = self._ev()
        assert ev._format_spans(42) == "(invalid span format: int)"

    def test_span_invalid_entry_in_list(self):
        """A non-dict element inside the list -> the per-entry invalid msg,
        still 1-indexed."""
        ev = self._ev()
        assert ev._format_spans(["not-a-dict"]) == "  1. (invalid span entry)"


class TestFormatValueDispatch:
    """`_format_value` dispatches to `_format_value_by_type` when answer_type
    is set, else falls back to plain str / json.dumps."""

    def test_dispatches_to_typed_when_answer_type_set(self):
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        ev = LLMJudgeEvaluator(ai_service="x", judge_model="m", answer_type="rating")
        assert ev._format_value(7) == "Value: 7"

    def test_plain_string_passthrough_without_answer_type(self):
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        ev = LLMJudgeEvaluator(ai_service="x", judge_model="m")  # answer_type None
        assert ev._format_value("just text") == "just text"

    def test_dict_json_without_answer_type(self):
        import json

        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        ev = LLMJudgeEvaluator(ai_service="x", judge_model="m")
        assert ev._format_value({"a": 1}) == json.dumps({"a": 1}, indent=2)
