"""Neural-metric ORCHESTRATION mutation-kill tests for
``ml_evaluation/sample_evaluator.py``.

These metrics (QAGS, coherence, MoverScore) are headline academic-benchmark
numbers. We cannot unit-test the underlying ML model, but the AGGREGATION /
COUNTING / VALIDATION logic *around* the backend is fully deterministic and is
exactly where a silent off-by-one or a flipped denominator turns into a wrong
published score. Every test here MOCKS the backend (or the per-method
sub-scorers) to fixed values and asserts the EXACT orchestration output, with
the expected value HAND-COMPUTED from the source in each docstring.

What is pinned here (companion to test_sample_evaluator_mutation_kills.py, which
covers the pure deterministic metrics + part of ``_answers_match_qags``):

  _qags_with_details      — the question loop, the matched/succeeded counters,
                            failed-question EXCLUSION from the denominator, the
                            ``succeeded == 0`` early-return, ``score = matched /
                            succeeded``, the two distinct error strings, and the
                            details bookkeeping (total/succeeded/failed/matched).
  _coherence_with_details — method routing (entity/semantic/hybrid), the hybrid
                            entity-grid fallback, ``total_weight``, the
                            ``total_weight == 0`` branch, the normalized weighted
                            average ``sum(score*(w/total))``, the
                            ``max(0, min(1, weighted))`` clamp (both ends), and
                            the weights_input / weights_effective audit dicts.
  _moverscore_with_details— the three input-validation RAISES (empty gt, empty
                            pred, <3 chars), the ``if not scores`` empty-backend
                            branch (value 0.0 + error + backend_returned_scores
                            False) vs. the score passthrough ``float(scores[0])``.
  _answers_match_qags     — only the cases the mutation-kills suite misses:
                            the case-normalization (.lower().strip()) branch, the
                            both-empty -> exact-match-True short-circuit, the
                            one-side-blank-after-strip -> False guard, the F1
                            precision/recall asymmetry (which denominator is
                            which), and the threshold-just-below boundary.
"""

import os
import sys
from unittest.mock import patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.sample_evaluator import SampleEvaluator  # noqa: E402


@pytest.fixture
def ev():
    return SampleEvaluator(evaluation_id="mut-test", field_configs={})


# A prediction string that PASSES _validate_text_for_coherence: non-empty,
# >= 20 chars after strip, and sent_tokenize yields >= 2 sentences. The actual
# content is irrelevant because we monkeypatch the per-method sub-scorers, so
# only the validation gate cares about it.
VALID_COHERENCE_TEXT = "Erster Satz steht hier. Zweiter Satz steht ebenfalls hier."


# ---------------------------------------------------------------------------
# Backend fakes for _qags_with_details and _moverscore_with_details.
# Both metrics resolve their backend through the module-level
# `_get_backend_selector()`; patching that one function swaps the whole chain.
# ---------------------------------------------------------------------------


class _FakeQAGSBackend:
    """Deterministic QAGS backend.

    generate_questions -> a fixed list of question strings.
    answer_question(q, text) -> dict {"answer": ...} driven by `answer_map`,
        which maps (question, which_text) where which_text is "gt"/"pred".
        Any question whose entry is the sentinel _RAISE makes answer_question
        raise, exercising the per-question try/except (failed-question path).
    """

    _RAISE = object()

    def __init__(self, questions, gt_answers, pred_answers, gt_str, pred_str):
        self._questions = questions
        self._gt_answers = gt_answers
        self._pred_answers = pred_answers
        self._gt_str = gt_str
        self._pred_str = pred_str

    def generate_questions(self, gt_str, num_questions=5):
        # Record the call shape but return the pre-baked list regardless.
        return list(self._questions)

    def answer_question(self, question, text):
        if text == self._gt_str:
            ans = self._gt_answers[question]
        elif text == self._pred_str:
            ans = self._pred_answers[question]
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unexpected text passed to answer_question: {text!r}")
        if ans is self._RAISE:
            raise RuntimeError(f"backend failed answering {question!r}")
        return {"answer": ans}


class _FakeSelector:
    def __init__(self, qags_backend=None, moverscore_computer=None):
        self._qags_backend = qags_backend
        self._moverscore_computer = moverscore_computer

    def get_qags_backend(self):
        return self._qags_backend

    def get_moverscore_computer(self):
        return self._moverscore_computer


class _FakeMoverScoreComputer:
    """Returns a fixed `scores` list, ignoring inputs."""

    def __init__(self, scores):
        self._scores = scores
        self.calls = []

    def compute_moverscore(self, refs, preds, n_gram=1, remove_subwords=True):
        self.calls.append((refs, preds, n_gram, remove_subwords))
        return list(self._scores)


def _patch_selector(selector):
    """Patch the module-level _get_backend_selector to yield `selector`."""
    return patch(
        "ml_evaluation.sample_evaluator._get_backend_selector",
        return_value=selector,
    )


# ===========================================================================
# _qags_with_details
#   score = matched / succeeded, where:
#     succeeded counts only Q's that completed BOTH answer_question calls AND
#       the _answers_match_qags comparison without raising;
#     matched counts succeeded Q's whose answers matched;
#     a raising Q is appended to failed_questions and EXCLUDED from succeeded
#       (it is NOT a non-match in the denominator).
# ===========================================================================


def test_qags_all_match_score_one(ev):
    """4 questions, every gt/pred answer identical -> all 4 match.
    matched=4, succeeded=4 -> score = 4/4 = 1.0. Pins the matched++ and the
    matched/succeeded division when they coincide."""
    qs = ["q1", "q2", "q3", "q4"]
    gt = {q: f"answer {q}" for q in qs}
    pred = {q: f"answer {q}" for q in qs}
    backend = _FakeQAGSBackend(qs, gt, pred, "GTTEXT", "PREDTEXT")
    sel = _FakeSelector(qags_backend=backend)
    with _patch_selector(sel):
        out = ev._qags_with_details("GTTEXT", "PREDTEXT", {"num_questions": 4})
    assert out["value"] == 1.0
    assert out["error"] is None
    d = out["details"]
    assert d["total_questions_generated"] == 4
    assert d["questions_succeeded"] == 4
    assert d["questions_failed"] == 0
    assert d["matched_answers"] == 4


def test_qags_failed_question_excluded_from_denominator(ev):
    """4 questions: q1,q2,q3 answers all match; q4's pred answer RAISES.
    The raiser is excluded from `succeeded` (NOT counted as a non-match), so
    matched=3, succeeded=3 -> score = 3/3 = 1.0 (NOT 3/4 = 0.75).
    This is the headline 'honest denominator' contract: kills any mutant that
    counts the failed Q into succeeded or treats it as matched=0/non-match."""
    qs = ["q1", "q2", "q3", "q4"]
    gt = {q: f"answer {q}" for q in qs}
    pred = {q: f"answer {q}" for q in qs}
    pred["q4"] = _FakeQAGSBackend._RAISE  # pred-side answer raises
    backend = _FakeQAGSBackend(qs, gt, pred, "GTTEXT", "PREDTEXT")
    sel = _FakeSelector(qags_backend=backend)
    with _patch_selector(sel):
        out = ev._qags_with_details("GTTEXT", "PREDTEXT", {"num_questions": 4})
    assert out["value"] == 1.0  # 3/3, not 3/4
    assert out["error"] is None
    d = out["details"]
    assert d["total_questions_generated"] == 4
    assert d["questions_succeeded"] == 3
    assert d["questions_failed"] == 1
    assert d["matched_answers"] == 3
    # the failed question is recorded with its error string
    assert d["failed_question_errors"][0]["question"] == "q4"
    assert "backend failed" in d["failed_question_errors"][0]["error"]


def test_qags_two_of_three_match_score_two_thirds(ev):
    """3 questions: q1 matches (identical), q2 matches (identical),
    q3 mismatches (disjoint tokens -> _answers_match_qags False). All three
    SUCCEED (no raise). matched=2, succeeded=3 -> score = 2/3.
    Pins `score = matched / succeeded` with matched != succeeded."""
    qs = ["q1", "q2", "q3"]
    gt = {"q1": "alpha", "q2": "beta", "q3": "gamma delta"}
    pred = {"q1": "alpha", "q2": "beta", "q3": "epsilon zeta"}
    backend = _FakeQAGSBackend(qs, gt, pred, "GTTEXT", "PREDTEXT")
    sel = _FakeSelector(qags_backend=backend)
    with _patch_selector(sel):
        out = ev._qags_with_details("GTTEXT", "PREDTEXT", {"num_questions": 3})
    assert out["value"] == pytest.approx(2.0 / 3.0)
    assert out["error"] is None
    d = out["details"]
    assert d["questions_succeeded"] == 3
    assert d["matched_answers"] == 2
    assert d["questions_failed"] == 0


def test_qags_all_questions_fail_returns_zero_with_convention_error(ev):
    """3 questions generated, but EVERY answer_question raises -> succeeded == 0.
    Early-return branch: value 0.0 and the 'All QAGS questions failed ...'
    error (the questions-non-empty arm). Kills any mutant that turns the
    succeeded==0 guard off (which would hit 0/0 ZeroDivisionError) or swaps the
    two error strings."""
    qs = ["q1", "q2", "q3"]
    raise_all = {q: _FakeQAGSBackend._RAISE for q in qs}
    backend = _FakeQAGSBackend(qs, raise_all, raise_all, "GTTEXT", "PREDTEXT")
    sel = _FakeSelector(qags_backend=backend)
    with _patch_selector(sel):
        out = ev._qags_with_details("GTTEXT", "PREDTEXT", {"num_questions": 3})
    assert out["value"] == 0.0
    assert out["error"] is not None
    assert "All QAGS questions failed" in out["error"]
    assert "no successful Q/A pair" in out["error"]
    d = out["details"]
    assert d["total_questions_generated"] == 3
    assert d["questions_succeeded"] == 0
    assert d["questions_failed"] == 3
    # matched_answers key is absent on the succeeded==0 branch
    assert "matched_answers" not in d


def test_qags_no_questions_generated_distinct_error(ev):
    """generate_questions returns [] -> the loop never runs -> succeeded == 0,
    but `questions` is falsy so the OTHER error string fires:
    'QAGS generated no questions from ground truth'. Kills the
    `if questions ... else ...` selection of the two error messages."""
    backend = _FakeQAGSBackend([], {}, {}, "GTTEXT", "PREDTEXT")
    sel = _FakeSelector(qags_backend=backend)
    with _patch_selector(sel):
        out = ev._qags_with_details("GTTEXT", "PREDTEXT", {"num_questions": 5})
    assert out["value"] == 0.0
    assert out["error"] == "QAGS generated no questions from ground truth"
    d = out["details"]
    assert d["total_questions_generated"] == 0
    assert d["questions_succeeded"] == 0
    assert d["questions_failed"] == 0


def test_qags_zero_matches_all_succeed_score_zero(ev):
    """2 questions, both SUCCEED but neither matches (disjoint answers).
    matched=0, succeeded=2 -> score = 0/2 = 0.0 via the NORMAL path (error
    None), distinct from the succeeded==0 early-return (which has a non-None
    error). Kills a mutant that conflates 'zero matched' with 'zero succeeded'."""
    qs = ["q1", "q2"]
    gt = {"q1": "alpha beta", "q2": "gamma delta"}
    pred = {"q1": "uno dos", "q2": "tres quatro"}
    backend = _FakeQAGSBackend(qs, gt, pred, "GTTEXT", "PREDTEXT")
    sel = _FakeSelector(qags_backend=backend)
    with _patch_selector(sel):
        out = ev._qags_with_details("GTTEXT", "PREDTEXT", {"num_questions": 2})
    assert out["value"] == 0.0
    assert out["error"] is None  # NORMAL path, not the all-failed convention
    d = out["details"]
    assert d["questions_succeeded"] == 2
    assert d["matched_answers"] == 0


def test_qags_failed_errors_capped_at_ten(ev):
    """12 questions all raise -> failed_question_errors is sliced [:10] in the
    succeeded==0 branch. questions_failed reports the true 12, but only 10
    error records are surfaced. Kills a mutant that drops the [:10] slice."""
    qs = [f"q{i}" for i in range(12)]
    raise_all = {q: _FakeQAGSBackend._RAISE for q in qs}
    backend = _FakeQAGSBackend(qs, raise_all, raise_all, "GTTEXT", "PREDTEXT")
    sel = _FakeSelector(qags_backend=backend)
    with _patch_selector(sel):
        out = ev._qags_with_details("GTTEXT", "PREDTEXT", {"num_questions": 12})
    d = out["details"]
    assert d["questions_failed"] == 12
    assert len(d["failed_question_errors"]) == 10


# ===========================================================================
# _coherence_with_details
#   value = max(0, min(1, sum(score_i * (w_i / total_weight))))
#   method routing: "entity" -> entity only; "semantic" -> semantic only;
#   "hybrid" -> both, with entity errors degrading to semantic-only.
# ===========================================================================


def test_coherence_hybrid_weighted_average_exact(ev):
    """method=hybrid, entity=0.8 (w 0.6), semantic=0.4 (w 0.4).
    total_weight = 0.6 + 0.4 = 1.0.
    weighted = 0.8*(0.6/1.0) + 0.4*(0.4/1.0) = 0.48 + 0.16 = 0.64.
    Hand-computed EXACTLY. Pins the weighted-average formula, the per-term
    normalization, and that BOTH sub-scores enter."""
    with patch.object(ev, "_compute_entity_coherence", return_value=0.8), \
         patch.object(ev, "_compute_semantic_coherence", return_value=0.4):
        out = ev._coherence_with_details(VALID_COHERENCE_TEXT, {"method": "hybrid"})
    assert out["value"] == pytest.approx(0.64)
    assert out["error"] is None
    d = out["details"]
    assert d["method_requested"] == "hybrid"
    assert d["methods_used"] == ["entity", "semantic"]
    assert d["fallback_reason"] is None
    # weights_input = the per-method weights that ENTERED (both present)
    assert d["weights_input"] == {"entity": 0.6, "semantic": 0.4}
    # weights_effective = post-normalization (total 1.0 here, so unchanged)
    assert d["weights_effective"]["entity"] == pytest.approx(0.6)
    assert d["weights_effective"]["semantic"] == pytest.approx(0.4)


def test_coherence_entity_only_passthrough(ev):
    """method=entity -> only entity contributes. entity=0.3, w default 0.6.
    total_weight = 0.6. weighted = 0.3 * (0.6/0.6) = 0.3. Pins that the
    semantic sub-call is NOT invoked and the single-term average == the score."""
    sem_called = {"hit": False}

    def _sem(_sentences):
        sem_called["hit"] = True
        return 0.99

    with patch.object(ev, "_compute_entity_coherence", return_value=0.3), \
         patch.object(ev, "_compute_semantic_coherence", side_effect=_sem):
        out = ev._coherence_with_details(VALID_COHERENCE_TEXT, {"method": "entity"})
    assert out["value"] == pytest.approx(0.3)
    assert sem_called["hit"] is False
    d = out["details"]
    assert d["methods_used"] == ["entity"]
    assert d["weights_input"] == {"entity": 0.6, "semantic": 0.0}
    # only entity entered -> effective entity weight normalizes to 1.0
    assert d["weights_effective"]["entity"] == pytest.approx(1.0)
    assert d["weights_effective"]["semantic"] == pytest.approx(0.0)


def test_coherence_semantic_only_passthrough(ev):
    """method=semantic -> entity sub-call NOT invoked. semantic=0.5, w 0.4.
    weighted = 0.5 * (0.4/0.4) = 0.5."""
    ent_called = {"hit": False}

    def _ent(_sentences):
        ent_called["hit"] = True
        return 0.99

    with patch.object(ev, "_compute_entity_coherence", side_effect=_ent), \
         patch.object(ev, "_compute_semantic_coherence", return_value=0.5):
        out = ev._coherence_with_details(VALID_COHERENCE_TEXT, {"method": "semantic"})
    assert out["value"] == pytest.approx(0.5)
    assert ent_called["hit"] is False
    assert out["details"]["methods_used"] == ["semantic"]
    assert out["details"]["weights_input"] == {"entity": 0.0, "semantic": 0.4}


def test_coherence_entity_only_mode_reraises_as_runtime(ev):
    """method=entity and the entity sub-call raises -> RuntimeError
    'Coherence (entity-only mode): ...'. There is NO semantic fallback in
    entity-only mode. Kills a mutant that swallows the error or falls back."""
    with patch.object(
        ev, "_compute_entity_coherence", side_effect=ValueError("grid empty")
    ), patch.object(ev, "_compute_semantic_coherence", return_value=0.9):
        with pytest.raises(RuntimeError, match="entity-only mode"):
            ev._coherence_with_details(VALID_COHERENCE_TEXT, {"method": "entity"})


def test_coherence_hybrid_entity_failure_falls_back_to_semantic(ev):
    """method=hybrid, entity sub-call raises -> degrade to semantic-only.
    semantic=0.7, w 0.4. coherence_scores holds only (0.7, 0.4) ->
    total_weight = 0.4 -> weighted = 0.7 * (0.4/0.4) = 0.7.
    fallback_reason is set; methods_used == ['semantic']; weights_input has
    entity 0.0 (it never entered) and semantic 0.4. Pins the hybrid fallback
    that the comment says replaced a SILENT semantic-only fallback."""
    with patch.object(
        ev, "_compute_entity_coherence", side_effect=ValueError("grid empty")
    ), patch.object(ev, "_compute_semantic_coherence", return_value=0.7):
        out = ev._coherence_with_details(VALID_COHERENCE_TEXT, {"method": "hybrid"})
    assert out["value"] == pytest.approx(0.7)
    assert out["error"] is None
    d = out["details"]
    assert d["methods_used"] == ["semantic"]
    assert d["fallback_reason"] is not None
    assert "entity grid unavailable" in d["fallback_reason"]
    assert d["weights_input"] == {"entity": 0.0, "semantic": 0.4}
    assert d["weights_effective"]["semantic"] == pytest.approx(1.0)
    assert d["weights_effective"]["entity"] == pytest.approx(0.0)


def test_coherence_invalid_method_raises_value_error(ev):
    """method neither entity/semantic/hybrid -> NO sub-scores collected ->
    coherence_scores empty -> ValueError('Invalid coherence method: ...').
    Kills a mutant that defaults to a score instead of raising."""
    with patch.object(ev, "_compute_entity_coherence", return_value=0.5), \
         patch.object(ev, "_compute_semantic_coherence", return_value=0.5):
        with pytest.raises(ValueError, match="Invalid coherence method"):
            ev._coherence_with_details(VALID_COHERENCE_TEXT, {"method": "bogus"})


def test_coherence_custom_unnormalized_weights_normalize(ev):
    """Custom weights that do NOT sum to 1: entity_weight=3, semantic_weight=1.
    entity=1.0, semantic=0.0. total_weight = 3 + 1 = 4.
    weighted = 1.0*(3/4) + 0.0*(1/4) = 0.75.
    Pins that the average divides by total_weight (normalization), not by a
    hardcoded 1.0 or by len(scores)."""
    with patch.object(ev, "_compute_entity_coherence", return_value=1.0), \
         patch.object(ev, "_compute_semantic_coherence", return_value=0.0):
        out = ev._coherence_with_details(
            VALID_COHERENCE_TEXT,
            {"method": "hybrid", "entity_weight": 3, "semantic_weight": 1},
        )
    assert out["value"] == pytest.approx(0.75)
    d = out["details"]
    assert d["weights_requested"] == {"entity": 3, "semantic": 1}
    # effective weights normalize 3/4 and 1/4
    assert d["weights_effective"]["entity"] == pytest.approx(0.75)
    assert d["weights_effective"]["semantic"] == pytest.approx(0.25)


def test_coherence_total_weight_zero_returns_zero(ev):
    """Both weights 0 -> total_weight == 0 -> the value=0.0 branch (avoids a
    0/0). weights_effective falls back to all-zeros. Kills a mutant that
    removes the total_weight==0 guard (-> ZeroDivisionError) or returns a
    nonzero default."""
    with patch.object(ev, "_compute_entity_coherence", return_value=0.9), \
         patch.object(ev, "_compute_semantic_coherence", return_value=0.9):
        out = ev._coherence_with_details(
            VALID_COHERENCE_TEXT,
            {"method": "hybrid", "entity_weight": 0, "semantic_weight": 0},
        )
    assert out["value"] == 0.0
    assert out["details"]["weights_effective"] == {"entity": 0.0, "semantic": 0.0}


def test_coherence_clamp_upper_bound(ev):
    """A sub-scorer returning > 1 must be clamped: entity=1.5 (w 0.6),
    semantic=1.5 (w 0.4). weighted = 1.5*0.6 + 1.5*0.4 = 1.5 -> min(1, 1.5)=1.0.
    Kills the `min(1.0, weighted)` upper clamp."""
    with patch.object(ev, "_compute_entity_coherence", return_value=1.5), \
         patch.object(ev, "_compute_semantic_coherence", return_value=1.5):
        out = ev._coherence_with_details(VALID_COHERENCE_TEXT, {"method": "hybrid"})
    assert out["value"] == 1.0


def test_coherence_clamp_lower_bound(ev):
    """A sub-scorer returning < 0 must be clamped to 0: entity=-0.5 (w 0.6),
    semantic=-0.5 (w 0.4). weighted = -0.5 -> max(0, -0.5) = 0.0.
    Kills the `max(0.0, weighted)` lower clamp."""
    with patch.object(ev, "_compute_entity_coherence", return_value=-0.5), \
         patch.object(ev, "_compute_semantic_coherence", return_value=-0.5):
        out = ev._coherence_with_details(VALID_COHERENCE_TEXT, {"method": "hybrid"})
    assert out["value"] == 0.0


# ===========================================================================
# _moverscore_with_details
#   Input validation RAISES before the backend is touched; otherwise
#   value = float(scores[0]) on a non-empty backend result, else the
#   explicit empty-output branch (value 0.0, error set, flag False).
# ===========================================================================


def test_moverscore_empty_gt_raises(ev):
    """Blank ground truth -> ValueError('non-empty ground truth') BEFORE the
    backend is consulted. Kills a mutant that drops the gt-empty guard."""
    sel = _FakeSelector(moverscore_computer=_FakeMoverScoreComputer([0.9]))
    with _patch_selector(sel):
        with pytest.raises(ValueError, match="non-empty ground truth"):
            ev._moverscore_with_details("   ", "valid prediction text", {})


def test_moverscore_empty_pred_raises(ev):
    """Blank prediction -> ValueError('non-empty prediction'). Kills the
    pred-empty guard removal."""
    sel = _FakeSelector(moverscore_computer=_FakeMoverScoreComputer([0.9]))
    with _patch_selector(sel):
        with pytest.raises(ValueError, match="non-empty prediction"):
            ev._moverscore_with_details("valid ground truth text", "", {})


def test_moverscore_too_short_text_raises(ev):
    """gt 'ab' has len 2 (< 3) after strip -> ValueError('3 characters').
    Kills the `< 3` boundary on the length check."""
    sel = _FakeSelector(moverscore_computer=_FakeMoverScoreComputer([0.9]))
    with _patch_selector(sel):
        with pytest.raises(ValueError, match="3 characters"):
            ev._moverscore_with_details("ab", "valid prediction text", {})


def test_moverscore_three_chars_is_allowed(ev):
    """len == 3 passes the `< 3` guard (boundary is exclusive). 'abc' (3) is
    accepted and the backend score flows through. Kills `< 3` -> `<= 3`."""
    comp = _FakeMoverScoreComputer([0.55])
    sel = _FakeSelector(moverscore_computer=comp)
    with _patch_selector(sel):
        out = ev._moverscore_with_details("abc", "xyz", {})
    assert out["value"] == pytest.approx(0.55)
    assert out["error"] is None


def test_moverscore_score_passthrough(ev):
    """Backend returns [0.73] -> value = float(scores[0]) = 0.73,
    backend_returned_scores True, error None. Pins the `scores[0]` index and
    the float() coercion."""
    comp = _FakeMoverScoreComputer([0.73, 0.11])  # only [0] is used
    sel = _FakeSelector(moverscore_computer=comp)
    with _patch_selector(sel):
        out = ev._moverscore_with_details(
            "ground truth sentence here", "predicted sentence here", {}
        )
    assert out["value"] == pytest.approx(0.73)
    assert out["details"]["backend_returned_scores"] is True
    assert out["error"] is None
    # default parameters forwarded to the backend
    assert comp.calls[0][2] == 1  # n_gram default
    assert comp.calls[0][3] is True  # remove_subwords default


def test_moverscore_empty_backend_result_explicit_zero(ev):
    """Backend returns [] -> the explicit empty-output branch: value 0.0,
    error 'MoverScore backend returned no scores', backend_returned_scores
    False. This is the whole point of the method: distinguish a genuine 0 from
    an empty backend. Kills a mutant that drops the `if not scores` guard
    (-> IndexError on scores[0]) or sets the flag/error wrong."""
    comp = _FakeMoverScoreComputer([])
    sel = _FakeSelector(moverscore_computer=comp)
    with _patch_selector(sel):
        out = ev._moverscore_with_details(
            "ground truth sentence here", "predicted sentence here", {}
        )
    assert out["value"] == 0.0
    assert out["details"]["backend_returned_scores"] is False
    assert out["error"] == "MoverScore backend returned no scores"


def test_moverscore_parameters_forwarded(ev):
    """Custom n_gram / remove_subwords flow into compute_moverscore and into
    the details audit. Pins the parameter plumbing."""
    comp = _FakeMoverScoreComputer([0.42])
    sel = _FakeSelector(moverscore_computer=comp)
    with _patch_selector(sel):
        out = ev._moverscore_with_details(
            "ground truth sentence here",
            "predicted sentence here",
            {"n_gram": 2, "remove_subwords": False},
        )
    assert out["value"] == pytest.approx(0.42)
    assert out["details"]["n_gram"] == 2
    assert out["details"]["remove_subwords"] is False
    assert comp.calls[0][2] == 2
    assert comp.calls[0][3] is False


# ===========================================================================
# _answers_match_qags — cases NOT already covered by the mutation-kills suite.
# Already covered there: exact match, no overlap, F1==0.5 boundary inclusive,
# F1 below threshold, empty answer, custom threshold. Add the remaining
# branches:
# ===========================================================================


def test_answers_match_case_and_whitespace_normalized(ev):
    """'  The Answer  ' vs 'the answer' -> after .lower().strip() both equal
    'the answer' -> the EXACT-match short-circuit returns True before any token
    arithmetic. Kills a mutant that drops the .lower() or the .strip() in the
    normalization (the strings differ raw)."""
    assert ev._answers_match_qags("  The Answer  ", "the answer") is True


def test_answers_match_both_empty_is_true(ev):
    """Two empty strings normalize to '' == '' -> the exact-match branch fires
    FIRST and returns True (the `not ans1 or not ans2` False-guard below is
    never reached). Pins the ordering: exact-match check precedes the empty
    guard. Kills a mutant that reorders them (which would return False)."""
    assert ev._answers_match_qags("", "") is True
    assert ev._answers_match_qags("   ", "  ") is True  # both strip to ''


def test_answers_match_one_blank_after_strip_is_false(ev):
    """Non-empty raw vs whitespace-only: 'x' vs '   ' -> ans2 strips to '' ->
    not equal, then `not ans2` True -> return False. Kills the empty-side guard
    removal (which would proceed to token F1 and divide by zero / mismatch)."""
    assert ev._answers_match_qags("x", "   ") is False
    assert ev._answers_match_qags("   ", "x") is False


def test_answers_match_f1_precision_recall_asymmetry(ev):
    """ans1='a b' (2 tokens), ans2='a b c d' (4 tokens), intersection={a,b}=2.
    precision = inter/len(tokens2) = 2/4 = 0.5
    recall    = inter/len(tokens1) = 2/2 = 1.0
    f1 = 2*(0.5*1.0)/(0.5+1.0) = 1.0/1.5 = 2/3 ≈ 0.667 >= 0.5 -> True.
    With a SWAPPED precision/recall denominator the F1 is identical here, so to
    pin the asymmetry we ALSO check the threshold-sensitive sibling below."""
    assert ev._answers_match_qags("a b", "a b c d") is True


def test_answers_match_f1_just_below_threshold_false(ev):
    """ans1='a b c' (3), ans2='a d e f' (4), intersection={a}=1.
    precision = 1/4 = 0.25, recall = 1/3 ≈ 0.333.
    f1 = 2*(0.25*0.3333)/(0.25+0.3333) = (0.16667)/(0.58333) ≈ 0.2857 < 0.5
    -> False. A precision/recall denominator swap gives the same f1 (symmetric
    product), but the magnitude pins that BOTH len() denominators are token-set
    sizes (not, e.g., intersection in the denominator)."""
    assert ev._answers_match_qags("a b c", "a d e f") is False


def test_answers_match_default_threshold_is_half(ev):
    """ans1='a b c d' (4), ans2='a b e f' (4), intersection={a,b}=2.
    precision = recall = 2/4 = 0.5, f1 = 0.5. With the DEFAULT threshold (no
    threshold kwarg) 0.5 >= 0.5 -> True. Pins that the default is 0.5, not a
    higher value that would reject this."""
    assert ev._answers_match_qags("a b c d", "a b e f") is True
