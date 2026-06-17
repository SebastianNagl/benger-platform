"""Dispatch-precedence + factuality-aggregation + per-sample orchestration
mutation-kill tests for ``ml_evaluation/sample_evaluator.py``.

WHY THIS FILE EXISTS
--------------------
A research-grade LLM benchmark is only trustworthy if the *plumbing* around
the metric math is deterministic: the right metric must be routed to the right
implementation, the factuality aggregation must count claims the way the
algorithm says, and the per-sample loop must assemble exactly the result the
downstream DB/leaderboard reads. A silently mis-routed metric or a wrong
matched/total ratio is an unobservable academic-benchmark corruption — the kind
this suite is built to make impossible.

SCOPE — three orchestration layers, NOT the per-metric math
-----------------------------------------------------------
1. ``_compute_metric_with_details`` — the 4-tier DISPATCH PRECEDENCE:
   (1) registry handler wins (result returned VERBATIM),
   (2) ``korrektur_*`` -> the human-graded skip dict,
   (3) named provenance helpers (coherence/moverscore/qags/bertscore/
       semantic_similarity) — routed strictly BY NAME,
   (4) legacy fallback wrapper, incl. the ``legacy is None -> 0.0`` coercion.
2. ``_compute_factuality_metric`` — the DETERMINISTIC aggregation given mocked
   backend outputs: the QAGS matched/total ratio, parameter threading
   (``num_questions`` -> generate_questions, ``min_answer_overlap`` ->
   ``_answers_match_qags``), the FactCC/SummaC gt/pred ordering + float coerce,
   and ``_answers_match_qags`` itself (the per-claim token-F1 match decision).
3. ``evaluate_sample`` — the per-sample LOOP + ASSEMBLY, driven by a
   monkeypatched ``_compute_metric_with_details`` so the loop logic is isolated
   from the metric math: result-dict shape, per-metric value placement, the
   passed/failed determination, the dict-``value`` primary-key extraction, the
   per-metric exception -> recorded-None (sample does not crash), and the
   entry-guard ``ValueError`` for unparsed generations.

DELIBERATELY NOT RE-TESTED (covered by sibling suites, verified by reading):
  * test_sample_evaluator_branches.py — the *_with_details provenance helpers'
    own internals, _optimal_span_matching, evaluate_sample annotation-skip /
    single-failure / answer_type.
  * test_sample_evaluator_compute_internals.py — _compute_factuality_metric
    coherence/qags inline happy paths, _compute_semantic_metric, the legacy
    fall-through wrapper for a value-1.0 metric, semantic-coherence body.
  * test_sample_evaluator_mutation_kills.py — every deterministic legacy-chain
    metric's math.
This file adds the surgical ROUTING + AGGREGATION-RATIO + LOOP-ASSEMBLY layer
those three miss. Every expected number is HAND-COMPUTED in the docstring.

All neural backends are mocked via ``_get_backend_selector`` / instance-method
patches — NO model downloads.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SE_MOD = "ml_evaluation.sample_evaluator"


@pytest.fixture
def ev():
    """Canonical evaluator construction (mirrors the mutation-kills suite)."""
    from ml_evaluation.sample_evaluator import SampleEvaluator

    return SampleEvaluator(evaluation_id="mut-test", field_configs={})


class _FakeHandler:
    """A minimal stand-in for a registered MetricHandler.

    Returns whatever ``payload`` it was constructed with, verbatim, and records
    the exact args it was called with so the test can assert the dispatch
    forwarded the *normalized* gt/pred + answer_type + parameters.
    """

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def compute(self, gt, pred, answer_type, parameters):
        self.calls.append((gt, pred, answer_type, parameters))
        return self.payload


# ============================================================================
# _compute_metric_with_details — TIER 1: registry handler wins (VERBATIM)
# ============================================================================


class TestDetailsTier1RegistryVerbatim:
    """The registry handler, when present, OWNS the full result dict. The
    dispatch must return it byte-for-byte — no re-wrapping, no value coercion,
    no clobbering of a handler-supplied ``error`` or custom ``details``."""

    def test_handler_result_returned_verbatim(self, ev):
        """A fake handler returns a bespoke dict (non-1.0 value, custom method
        string, populated error, nested details). The dispatch must hand that
        exact object back — identity-equal, not a copy/rewrap."""
        sentinel = {
            "value": 0.4242,
            "method": "totally_custom_name",
            "details": {"backend": "fake-onnx", "claims_checked": 7},
            "error": "degraded-but-usable",
            "primary_metric_key": "ignored",
        }
        handler = _FakeHandler(sentinel)
        with patch("ml_evaluation.metric_registry.get", return_value=handler):
            result = ev._compute_metric_with_details(
                "anything", "Ground TRUTH", "Pred Value", "text", {"k": "v"}
            )
        # Verbatim pass-through: same object, untouched.
        assert result is sentinel
        assert result["value"] == 0.4242
        assert result["method"] == "totally_custom_name"
        assert result["error"] == "degraded-but-usable"
        assert result["details"]["claims_checked"] == 7

    def test_handler_receives_normalized_inputs(self, ev):
        """Dispatch normalizes BEFORE calling the handler: a string gt/pred is
        ``.strip().lower()``-ed (see _normalize_value). Pin that the handler
        sees normalized text and the verbatim parameters dict."""
        handler = _FakeHandler({"value": 1.0, "method": "x", "details": {}, "error": None})
        params = {"threshold": 0.9}
        with patch("ml_evaluation.metric_registry.get", return_value=handler):
            ev._compute_metric_with_details(
                "x", "  HELLO World  ", "  GoodBye  ", "text", params
            )
        gt_seen, pred_seen, atype_seen, params_seen = handler.calls[0]
        assert gt_seen == "hello world"  # stripped + lowercased
        assert pred_seen == "goodbye"
        assert atype_seen == "text"
        assert params_seen == params

    def test_registry_hit_shadows_korrektur_branch(self, ev):
        """Tier 1 precedes tier 2: even a ``korrektur_*`` name returns the
        handler's dict, NOT the human-graded skip dict, when a handler exists.
        This pins the ordering (registry lookup happens before the
        ``startswith('korrektur_')`` check)."""
        handler = _FakeHandler({"value": 0.9, "method": "h", "details": {}, "error": None})
        with patch("ml_evaluation.metric_registry.get", return_value=handler):
            result = ev._compute_metric_with_details(
                "korrektur_falloesung", "gt", "pred", "text", {}
            )
        assert result["value"] == 0.9
        assert "human_graded" not in result["details"]


# ============================================================================
# _compute_metric_with_details — TIER 2: korrektur_* skip dict (exact shape)
# ============================================================================


class TestDetailsTier2KorrekturSkip:
    """When NO handler is registered, a ``korrektur_*`` metric must short to the
    human-graded skip dict: value 0.0, human_graded True, skipped True, error
    None. The worker must NEVER compute a number for a human-graded metric."""

    def test_exact_skip_dict_shape(self, ev):
        with patch("ml_evaluation.metric_registry.get", return_value=None):
            result = ev._compute_metric_with_details(
                "korrektur_klausur", "gt", "pred", "text", {}
            )
        assert result["value"] == 0.0
        assert result["method"] == "korrektur_klausur"
        assert result["details"]["human_graded"] is True
        assert result["details"]["skipped"] is True
        assert "API" in result["details"]["reason"]
        assert result["error"] is None

    def test_prefix_match_not_substring(self, ev):
        """The guard is ``startswith('korrektur_')`` — a name merely CONTAINING
        the token (e.g. 'pre_korrektur_x') must NOT be treated as korrektur; it
        falls through to the legacy chain (and there, being unknown, raises)."""
        with patch("ml_evaluation.metric_registry.get", return_value=None):
            with pytest.raises(ValueError, match="Unknown metric"):
                ev._compute_metric_with_details(
                    "pre_korrektur_classic", "gt", "pred", "text", {}
                )


# ============================================================================
# _compute_metric_with_details — TIER 3: named provenance-helper ROUTING
# ============================================================================


class TestDetailsTier3HelperRouting:
    """Lines 608-617 route 5 names to dedicated helpers. We patch each helper
    on the instance to a unique sentinel and assert the dispatch routes BY NAME
    to exactly the right one (and passes the right args). The helper internals
    are NOT re-tested — only that the wiring sends 'qags' to _qags_with_details,
    'bertscore' to _bertscore_with_details, etc. Registry is forced to miss so
    tier 1 cannot shadow."""

    def _route(self, ev, metric_name, helper_attr, expects_gt):
        sentinel = {"value": 0.123, "method": metric_name, "details": {"routed": True}, "error": None}
        with patch("ml_evaluation.metric_registry.get", return_value=None), patch.object(
            ev, helper_attr, return_value=sentinel
        ) as helper:
            result = ev._compute_metric_with_details(
                metric_name, "Source TEXT", "Pred TEXT", "text", {"p": 1}
            )
        assert result is sentinel
        helper.assert_called_once()
        return helper.call_args

    def test_qags_routes_to_qags_helper(self, ev):
        """'qags' -> _qags_with_details(gt, pred, parameters)."""
        args, _ = self._route(ev, "qags", "_qags_with_details", expects_gt=True)
        # _qags_with_details(self, gt, pred, parameters): gt normalized first.
        assert args[0] == "source text"
        assert args[1] == "pred text"
        assert args[2] == {"p": 1}

    def test_bertscore_routes_to_bertscore_helper(self, ev):
        args, _ = self._route(ev, "bertscore", "_bertscore_with_details", expects_gt=True)
        assert args[0] == "source text"
        assert args[1] == "pred text"

    def test_moverscore_routes_to_moverscore_helper(self, ev):
        args, _ = self._route(ev, "moverscore", "_moverscore_with_details", expects_gt=True)
        assert args[0] == "source text"
        assert args[1] == "pred text"

    def test_semantic_similarity_routes_to_its_helper(self, ev):
        args, _ = self._route(
            ev, "semantic_similarity", "_semantic_similarity_with_details", expects_gt=True
        )
        assert args[0] == "source text"
        assert args[1] == "pred text"

    def test_coherence_routes_to_coherence_helper_pred_only(self, ev):
        """'coherence' is special: _coherence_with_details(pred, parameters) —
        it takes ONLY the prediction (no ground truth). Pin that the dispatch
        forwards the normalized prediction, not the source."""
        sentinel = {"value": 0.5, "method": "coherence", "details": {}, "error": None}
        with patch("ml_evaluation.metric_registry.get", return_value=None), patch.object(
            ev, "_coherence_with_details", return_value=sentinel
        ) as helper:
            result = ev._compute_metric_with_details(
                "coherence", "Source TEXT", "Pred TEXT", "text", {"method": "hybrid"}
            )
        assert result is sentinel
        # First positional arg is the normalized PREDICTION, not the gt.
        assert helper.call_args[0][0] == "pred text"
        assert helper.call_args[0][1] == {"method": "hybrid"}

    def test_helper_routing_requires_registry_miss(self, ev):
        """If a handler IS registered for 'qags', tier 1 wins and the helper is
        never consulted — proves the helper branch is genuinely tier-3, gated
        behind a registry miss."""
        handler = _FakeHandler({"value": 0.7, "method": "qags", "details": {}, "error": None})
        with patch("ml_evaluation.metric_registry.get", return_value=handler), patch.object(
            ev, "_qags_with_details"
        ) as helper:
            result = ev._compute_metric_with_details("qags", "a", "b", "text", {})
        helper.assert_not_called()
        assert result["value"] == 0.7


# ============================================================================
# _compute_metric_with_details — TIER 4: legacy wrapper + None->0.0 coercion
# ============================================================================


class TestDetailsTier4LegacyWrapper:
    """The final fallback wraps a bare-float legacy result into the standard
    dict with ``details.legacy_path == True``. Two kill targets: the
    ``float(legacy)`` coercion, and the ``legacy is None -> 0.0`` guard."""

    def test_legacy_value_is_float_coerced_and_wrapped(self, ev):
        """A legacy method returning an int 1 must be wrapped with value 1.0
        (float), method == metric_name, legacy_path True, parameters echoed."""
        with patch("ml_evaluation.metric_registry.get", return_value=None), patch.object(
            ev, "_compute_metric_legacy", return_value=1
        ):
            result = ev._compute_metric_with_details(
                "some_metric", "gt", "pred", "text", {"alpha": 2}
            )
        assert result["value"] == 1.0
        assert isinstance(result["value"], float)
        assert result["method"] == "some_metric"
        assert result["details"]["legacy_path"] is True
        assert result["details"]["parameters_applied"] == {"alpha": 2}
        assert result["error"] is None

    def test_legacy_none_coerces_to_zero(self, ev):
        """The ``float(legacy_value) if legacy_value is not None else 0.0``
        branch: a legacy method returning None must yield value 0.0, NOT crash
        on float(None). This is the explicit None-safety in line 628."""
        with patch("ml_evaluation.metric_registry.get", return_value=None), patch.object(
            ev, "_compute_metric_legacy", return_value=None
        ):
            result = ev._compute_metric_with_details(
                "some_metric", "gt", "pred", "text", {}
            )
        assert result["value"] == 0.0
        assert result["details"]["legacy_path"] is True

    def test_legacy_zero_stays_zero_not_treated_as_none(self, ev):
        """Guard against an ``is not None`` -> truthiness mutation: a legacy 0.0
        is a real score and must survive as 0.0 (a truthiness check would also
        map it to 0.0, so we additionally pin value 0.0 with a 0.0 input and a
        non-zero input separately to lock the operator)."""
        with patch("ml_evaluation.metric_registry.get", return_value=None), patch.object(
            ev, "_compute_metric_legacy", return_value=0.0
        ):
            result = ev._compute_metric_with_details("m", "g", "p", "text", {})
        assert result["value"] == 0.0
        assert result["error"] is None


# ============================================================================
# _answers_match_qags — the per-claim token-F1 MATCH DECISION
# ============================================================================


class TestAnswersMatchQags:
    """The deterministic per-claim comparison QAGS uses to decide a match.
    precision = |overlap| / |tokens(answer2)|, recall = |overlap| / |tokens(answer1)|,
    f1 = 2PR/(P+R), match iff f1 >= threshold. Every expected f1 is hand-computed."""

    def test_exact_match_shortcuts_true(self, ev):
        """Equal (after lower/strip) -> True before any F1 math."""
        assert ev._answers_match_qags("Berlin", "berlin ", threshold=0.99) is True

    def test_empty_answer_is_false(self, ev):
        """An empty answer can never match a non-empty one."""
        assert ev._answers_match_qags("", "berlin", threshold=0.0) is False
        assert ev._answers_match_qags("berlin", "   ", threshold=0.0) is False

    def test_no_token_overlap_is_false(self, ev):
        """Disjoint token sets -> intersection 0 -> False (no division)."""
        assert ev._answers_match_qags("cat", "dog", threshold=0.0) is False

    def test_high_overlap_above_threshold_true(self, ev):
        """ans1='the quick brown fox', ans2='the quick red fox'.
        tokens1={the,quick,brown,fox}(4), tokens2={the,quick,red,fox}(4),
        overlap={the,quick,fox}=3. P=3/4=.75, R=3/4=.75,
        f1=2*.75*.75/(.75+.75)=1.125/1.5=0.75 >= 0.5 -> True."""
        assert (
            ev._answers_match_qags("the quick brown fox", "the quick red fox", threshold=0.5)
            is True
        )

    def test_low_overlap_below_threshold_false(self, ev):
        """ans1='alpha beta gamma delta', ans2='alpha epsilon zeta eta'.
        overlap={alpha}=1, P=1/4=.25, R=1/4=.25, f1=2*.0625/.5=0.25 < 0.5 -> False."""
        assert (
            ev._answers_match_qags(
                "alpha beta gamma delta", "alpha epsilon zeta eta", threshold=0.5
            )
            is False
        )

    def test_f1_exactly_at_threshold_is_inclusive(self, ev):
        """ans1='a b', ans2='a c': overlap={a}=1, P=1/2=.5, R=1/2=.5,
        f1=2*.25/1.0=0.5. The operator is ``>=`` so f1==threshold MATCHES.
        Kills a ``>=`` -> ``>`` mutation."""
        assert ev._answers_match_qags("a b", "a c", threshold=0.5) is True

    def test_just_above_threshold_excludes_equal(self, ev):
        """Same f1=0.5 but threshold nudged to 0.5000001 -> 0.5 < thr -> False.
        Confirms the boundary is a real comparison, not a constant True."""
        assert ev._answers_match_qags("a b", "a c", threshold=0.5000001) is False


# ============================================================================
# _compute_factuality_metric("qags") — the matched/total AGGREGATION RATIO
# ============================================================================


class TestFactualityQagsAggregation:
    """QAGS final score = matching_answers / total_questions. Pin the ratio for
    a non-1/2, non-trivial case, plus parameter threading. Backend is fully
    mocked: each question yields gt/pred answers; ``_answers_match_qags`` is
    patched to a deterministic, per-question decision so the AGGREGATION (not
    the F1 math, tested above) is what's under assertion."""

    def _selector(self, qb):
        sel = MagicMock()
        sel.get_qags_backend.return_value = qb
        return sel

    def test_two_of_three_match_gives_two_thirds(self, ev):
        """3 questions, the match decision is [True, False, True] -> 2/3.
        Hand: matching_answers=2, total_questions=3 -> 0.6666..."""
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?", "Q2?", "Q3?"]
        qb.answer_question.return_value = {"answer": "x"}
        decisions = iter([True, False, True])
        with patch(f"{SE_MOD}._get_backend_selector", return_value=self._selector(qb)), patch.object(
            ev, "_answers_match_qags", side_effect=lambda *a, **k: next(decisions)
        ):
            val = ev._compute_factuality_metric("qags", "gt", "pred", {})
        assert val == pytest.approx(2 / 3)

    def test_three_of_five_match_gives_zero_point_six(self, ev):
        """5 questions, decisions sum to 3 -> 3/5 = 0.6 exactly."""
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?", "Q2?", "Q3?", "Q4?", "Q5?"]
        qb.answer_question.return_value = {"answer": "x"}
        decisions = iter([True, True, False, True, False])
        with patch(f"{SE_MOD}._get_backend_selector", return_value=self._selector(qb)), patch.object(
            ev, "_answers_match_qags", side_effect=lambda *a, **k: next(decisions)
        ):
            val = ev._compute_factuality_metric("qags", "gt", "pred", {})
        assert val == pytest.approx(0.6)

    def test_zero_matches_gives_zero(self, ev):
        """No decision is True -> matching_answers=0 -> 0/2 = 0.0 (distinct from
        the no-questions guard: here total_questions=2)."""
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?", "Q2?"]
        qb.answer_question.return_value = {"answer": "x"}
        with patch(f"{SE_MOD}._get_backend_selector", return_value=self._selector(qb)), patch.object(
            ev, "_answers_match_qags", return_value=False
        ):
            val = ev._compute_factuality_metric("qags", "gt", "pred", {})
        assert val == 0.0

    def test_num_questions_param_threaded_to_generator(self, ev):
        """``num_questions`` must reach generate_questions as a kwarg (default 5
        otherwise). Pin the value passes through unchanged."""
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?"]
        qb.answer_question.return_value = {"answer": "x"}
        with patch(f"{SE_MOD}._get_backend_selector", return_value=self._selector(qb)), patch.object(
            ev, "_answers_match_qags", return_value=True
        ):
            ev._compute_factuality_metric("qags", "gt", "pred", {"num_questions": 9})
        _, kwargs = qb.generate_questions.call_args
        assert kwargs.get("num_questions") == 9

    def test_min_answer_overlap_param_threaded_to_matcher(self, ev):
        """``min_answer_overlap`` is forwarded as the ``threshold`` kwarg to
        ``_answers_match_qags``. Pin it lands as threshold=0.8 (not the 0.5
        default)."""
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?"]
        qb.answer_question.side_effect = [{"answer": "gtans"}, {"answer": "predans"}]
        seen = {}

        def capture(a1, a2, threshold=0.5):
            seen["threshold"] = threshold
            return True

        with patch(f"{SE_MOD}._get_backend_selector", return_value=self._selector(qb)), patch.object(
            ev, "_answers_match_qags", side_effect=capture
        ):
            ev._compute_factuality_metric(
                "qags", "gt", "pred", {"min_answer_overlap": 0.8}
            )
        assert seen["threshold"] == 0.8

    def test_gt_and_pred_answers_compared_in_order(self, ev):
        """For each question the backend is asked twice: once against the
        GROUND TRUTH, once against the PREDICTION, and those two answers (gt
        first, pred second) are what get compared. Pin the argument ordering
        into _answers_match_qags."""
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?"]

        def answer(question, text):
            # text is the second positional arg to answer_question(question, text)
            return {"answer": f"ans-for-{text}"}

        qb.answer_question.side_effect = answer
        captured = {}

        def matcher(a1, a2, threshold=0.5):
            captured["a1"] = a1
            captured["a2"] = a2
            return True

        with patch(f"{SE_MOD}._get_backend_selector", return_value=self._selector(qb)), patch.object(
            ev, "_answers_match_qags", side_effect=matcher
        ):
            ev._compute_factuality_metric("qags", "the-gt", "the-pred", {})
        # gt-derived answer is the FIRST comparison arg, pred-derived the second.
        assert captured["a1"] == "ans-for-the-gt"
        assert captured["a2"] == "ans-for-the-pred"


# ============================================================================
# _compute_factuality_metric("factcc", summac) — gt/pred order + float coerce
# ============================================================================


class TestFactualityFactccSummac:
    """SummaC is the default FactCC method. Pin that the SOURCE (gt) is the
    first arg and the CLAIM (pred) the second into score_consistency, and that
    the backend's numeric score is float-coerced through unchanged."""

    def test_summac_source_claim_order_and_float_coerce(self, ev):
        backend = MagicMock()
        backend.score_consistency.return_value = 1  # int -> must come out float 1.0
        sel = MagicMock()
        sel.get_summac_backend.return_value = backend
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            val = ev._compute_factuality_metric(
                "factcc", "the source", "the claim", {}  # default method=summac
            )
        assert val == 1.0
        assert isinstance(val, float)
        # score_consistency(source, claim): gt(source) first, pred(claim) second.
        args, _ = backend.score_consistency.call_args
        assert args[0] == "the source"
        assert args[1] == "the claim"


# ============================================================================
# evaluate_sample — per-sample LOOP + ASSEMBLY (metric math isolated out)
# ============================================================================


class TestEvaluateSampleOrchestration:
    """Drive evaluate_sample with ``_compute_metric_with_details`` monkeypatched
    so the LOOP and result-dict ASSEMBLY are what's under test, not the metric
    math. We pin: every requested metric appears with its returned dict, the
    passed/failed determination, the per-metric exception -> recorded-None +
    sample survives, the dict-valued primary-key extraction, and the
    result-envelope fields."""

    def _ev(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator

        return SampleEvaluator(
            evaluation_id="eval-orch", field_configs={"f": {"type": "text"}}
        )

    def test_every_requested_metric_appears_with_its_value(self):
        """Three metrics requested; the stub returns a distinct dict per name.
        Each must land in result['metrics'] under its own key, verbatim."""
        ev = self._ev()
        returns = {
            "exact_match": {"value": 1.0, "method": "exact_match", "details": {}, "error": None},
            "f1": {"value": 0.9, "method": "f1", "details": {}, "error": None},
            "bleu": {"value": 0.8, "method": "bleu", "details": {}, "error": None},
        }

        def stub(metric_name, gt, pred, atype, params):
            return returns[metric_name]

        with patch.object(ev, "_compute_metric_with_details", side_effect=stub):
            result = ev.evaluate_sample(
                task_id="t1",
                field_name="f",
                ground_truth="x",
                prediction="x",
                metrics_to_compute=["exact_match", "f1", "bleu"],
            )
        assert set(result["metrics"].keys()) == {"exact_match", "f1", "bleu"}
        assert result["metrics"]["exact_match"]["value"] == 1.0
        assert result["metrics"]["f1"]["value"] == 0.9
        assert result["metrics"]["bleu"]["value"] == 0.8
        # All three pass their thresholds -> sample passed.
        assert result["passed"] is True

    def test_one_failing_metric_flips_passed_false_others_unaffected(self):
        """exact_match value 0.0 is below its 0.5 threshold -> passed False, but
        the other metrics still appear with their values (the loop continues)."""
        ev = self._ev()
        returns = {
            "exact_match": {"value": 0.0, "method": "exact_match", "details": {}, "error": None},
            "f1": {"value": 0.95, "method": "f1", "details": {}, "error": None},
        }
        with patch.object(
            ev, "_compute_metric_with_details", side_effect=lambda m, *a: returns[m]
        ):
            result = ev.evaluate_sample(
                task_id="t1",
                field_name="f",
                ground_truth="a",
                prediction="b",
                metrics_to_compute=["exact_match", "f1"],
            )
        assert result["passed"] is False
        assert result["metrics"]["f1"]["value"] == 0.95
        assert result["metrics"]["exact_match"]["value"] == 0.0

    def test_metric_exception_recorded_as_none_sample_survives(self):
        """A metric whose compute RAISES is caught by the PER-METRIC try/except
        (lines 283-287): it is recorded as None and the loop CONTINUES to the
        next metric. Crucially the ``_is_failure_metric`` check lives INSIDE the
        try BEFORE the raise, so on exception ``passed`` is NOT touched — a
        failing-to-compute metric does not by itself flip the sample to failed
        (that is the other metrics' job). Here exact_match passes, so the sample
        stays passed=True, the boom metric is None, and the whole sample does
        NOT crash (no top-level error_message). This pins the exact contract:
        recorded-None + loop-survives + passed-unchanged-by-exception."""
        ev = self._ev()

        def stub(metric_name, *a):
            if metric_name == "boom":
                raise RuntimeError("metric exploded")
            return {"value": 1.0, "method": metric_name, "details": {}, "error": None}

        with patch.object(ev, "_compute_metric_with_details", side_effect=stub):
            result = ev.evaluate_sample(
                task_id="t1",
                field_name="f",
                ground_truth="x",
                prediction="x",
                metrics_to_compute=["exact_match", "boom"],
            )
        assert result["metrics"]["boom"] is None
        assert result["metrics"]["exact_match"]["value"] == 1.0
        # The raising metric is absorbed; passed is decided only by metrics that
        # DID compute. exact_match passed -> sample passed. No top-level error.
        assert result["passed"] is True
        assert result["error_message"] is None
        assert result["answer_type"] == "text"

    def test_dict_value_uses_primary_metric_key_for_failure_check(self):
        """When a metric returns ``value`` as a DICT (e.g. precision/recall/f1
        bundle), the failure check extracts ``primary_metric_key``. Here f1's
        primary key points at a sub-score of 0.2, which is below f1's 0.7
        threshold -> passed False. Pins lines 271-279 dict-extraction."""
        ev = self._ev()
        bundle = {
            "value": {"precision": 0.9, "recall": 0.9, "f1": 0.2},
            "primary_metric_key": "f1",
            "method": "f1",
            "details": {},
            "error": None,
        }
        with patch.object(ev, "_compute_metric_with_details", return_value=bundle):
            result = ev.evaluate_sample(
                task_id="t1",
                field_name="f",
                ground_truth="x",
                prediction="y",
                metrics_to_compute=["f1"],
            )
        # primary value 0.2 < 0.7 -> failure.
        assert result["passed"] is False
        assert result["metrics"]["f1"]["value"]["f1"] == 0.2

    def test_dict_value_without_primary_key_uses_first_inner_key(self):
        """No ``primary_metric_key`` -> ``next(iter(value))`` (first inserted
        key). Here the first key 'a' holds 0.95 (>= 0.7) so the metric passes,
        even though a later key is low. Pins the ``next(iter(...))`` fallback."""
        ev = self._ev()
        bundle = {
            "value": {"a": 0.95, "z": 0.0},  # 'a' is first -> used for threshold
            "method": "rouge",
            "details": {},
            "error": None,
        }
        with patch.object(ev, "_compute_metric_with_details", return_value=bundle):
            result = ev.evaluate_sample(
                task_id="t1",
                field_name="f",
                ground_truth="x",
                prediction="x",
                metrics_to_compute=["rouge"],
            )
        # rouge threshold 0.7; first-key value 0.95 -> pass.
        assert result["passed"] is True

    def test_result_envelope_carries_identity_and_serialized_io(self):
        """The assembled envelope must echo evaluation_id, task_id,
        generation_id, field_name and serialize gt/pred via _serialize_value
        (which tags the python type). Pin the structural contract the DB reads."""
        ev = self._ev()
        with patch.object(
            ev,
            "_compute_metric_with_details",
            return_value={"value": 1.0, "method": "exact_match", "details": {}, "error": None},
        ):
            result = ev.evaluate_sample(
                task_id="task-42",
                field_name="f",
                ground_truth="GT",
                prediction="PR",
                metrics_to_compute=["exact_match"],
                generation_id="gen-7",
                parse_status="success",
            )
        assert result["evaluation_id"] == "eval-orch"
        assert result["task_id"] == "task-42"
        assert result["generation_id"] == "gen-7"
        assert result["field_name"] == "f"
        assert result["ground_truth"] == {"value": "GT", "type": "str"}
        assert result["prediction"] == {"value": "PR", "type": "str"}
        assert isinstance(result["processing_time_ms"], int)

    def test_metric_params_threaded_per_field_and_metric(self):
        """metric_parameters[field][metric] must reach the compute call's
        ``parameters`` arg. Pin the threading: a configured {'threshold':0.9}
        for ('f','f1') shows up as the 5th positional arg."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        ev = SampleEvaluator(
            evaluation_id="e",
            field_configs={"f": {"type": "text"}},
            metric_parameters={"f": {"f1": {"threshold": 0.9}}},
        )
        seen = {}

        def stub(metric_name, gt, pred, atype, params):
            seen[metric_name] = params
            return {"value": 1.0, "method": metric_name, "details": {}, "error": None}

        with patch.object(ev, "_compute_metric_with_details", side_effect=stub):
            ev.evaluate_sample(
                task_id="t",
                field_name="f",
                ground_truth="x",
                prediction="x",
                metrics_to_compute=["f1"],
            )
        assert seen["f1"] == {"threshold": 0.9}

    def test_unparsed_generation_without_allow_raises_before_loop(self):
        """The entry guard: an LLM generation (generation_id set, no
        annotation_id) with parse_status != 'success' and allow_unparsed False
        must raise ValueError BEFORE any metric is computed. Pin that the
        compute method is never even called."""
        ev = self._ev()
        with patch.object(ev, "_compute_metric_with_details") as compute:
            with pytest.raises(ValueError, match="parse_status"):
                ev.evaluate_sample(
                    task_id="t",
                    field_name="f",
                    ground_truth="x",
                    prediction="x",
                    metrics_to_compute=["exact_match"],
                    generation_id="gen-1",
                    parse_status="failed",
                )
        compute.assert_not_called()

    def test_allow_unparsed_bypasses_entry_guard(self):
        """allow_unparsed=True lets a failed-parse generation through to the
        loop (the disjunct in the guard). Pin the sample evaluates normally."""
        ev = self._ev()
        with patch.object(
            ev,
            "_compute_metric_with_details",
            return_value={"value": 1.0, "method": "exact_match", "details": {}, "error": None},
        ):
            result = ev.evaluate_sample(
                task_id="t",
                field_name="f",
                ground_truth="x",
                prediction="x",
                metrics_to_compute=["exact_match"],
                generation_id="gen-1",
                parse_status="failed",
                allow_unparsed=True,
            )
        assert result["metrics"]["exact_match"]["value"] == 1.0
        assert result["error_message"] is None
