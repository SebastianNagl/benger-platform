"""Property-based tests for ml_evaluation.sample_evaluator (hypothesis).

The 44-metric ``SampleEvaluator`` is a crown-jewel pure module: every score-style
metric is a bounded similarity in [0, 1] with well-defined reflexivity / empty /
symmetry behaviour. These properties assert those INVARIANTS over arbitrary text
and structured inputs — the off-by-one / wrong-operator / flipped-branch mutants
that example tests miss (the mutation co-gate, issue: meaningful-coverage program).

Call path: metrics are dispatched through the legacy if/elif chain via
``SampleEvaluator._compute_metric_legacy(metric_name, gt, pred, answer_type, params)``,
which is what ``_compute_metric`` / ``_compute_metric_with_details`` resolve to for
platform built-ins. We normalise inputs the same way the evaluator does
(``_normalize_value``) before reasoning about symmetry.

SCOPE — only the cheap, deterministic, no-model-download metrics are tested:
    exact_match, accuracy, confusion_matrix, precision, recall, f1, cohen_kappa,
    token_f1, jaccard, hamming_loss, subset_accuracy, edit_distance, chrf,
    json_accuracy, field_accuracy, span_exact_match, iou, partial_match,
    boundary_accuracy, hierarchical_f1, path_accuracy, lca_accuracy.

EXCLUDED — transformer/NLI/embedding-backed or corpus-download metrics that
lazy-load torch / sentence-transformers / NLTK corpora and would download models
or hang in a sandbox: bertscore, moverscore, semantic_similarity, factcc, qags,
coherence (model-backed), and bleu, rouge, meteor (need NLTK wordnet/punkt
corpora that may be fetched over the network). Those are NOT score-bounded-pure
and are out of scope by design here.
"""

import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.sample_evaluator import SampleEvaluator

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Short-ish text — wide enough to exercise token overlap / edit distance, small
# enough to keep examples fast. Surrogate codepoints excluded (they break str ops).
_text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=24)
_nonempty_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), min_codepoint=33),
    min_size=1,
    max_size=24,
)

# Label tokens for set-style metrics.
_label = st.sampled_from(["a", "b", "c", "d", "e", "f"])
_label_list = st.lists(_label, max_size=6)

# Bounded non-negative integers for span endpoints.
_pos = st.integers(min_value=0, max_value=50)

# Score-style metrics whose contract is a value in [0, 1] for arbitrary text.
_TEXT_BOUNDED_METRICS = ["exact_match", "accuracy", "token_f1", "edit_distance", "chrf"]

# Set-overlap metrics that should be symmetric over label sets.
_SET_SYMMETRIC_METRICS = ["jaccard", "subset_accuracy", "hamming_loss"]


def _make_evaluator() -> SampleEvaluator:
    return SampleEvaluator(
        evaluation_id="prop-test",
        field_configs={"f": {"type": "text"}},
    )


def _score(ev: SampleEvaluator, metric: str, gt, pred, answer_type="text", params=None):
    """Drive a single metric through the legacy dispatch chain and return float."""
    return ev._compute_metric_legacy(metric, gt, pred, answer_type, params or {})


class TestTextMetricsBounded:
    @settings(max_examples=60, deadline=None)
    @given(metric=st.sampled_from(_TEXT_BOUNDED_METRICS), gt=_text, pred=_text)
    def test_score_in_unit_interval(self, metric, gt, pred):
        ev = _make_evaluator()
        # Mirror the evaluator's own normalisation step.
        g = ev._normalize_value(gt, "text")
        p = ev._normalize_value(pred, "text")
        v = _score(ev, metric, g, p)
        assert isinstance(v, float)
        assert 0.0 <= v <= 1.0, f"{metric}({gt!r},{pred!r}) = {v} out of [0,1]"

    @settings(max_examples=60, deadline=None)
    @given(metric=st.sampled_from(_TEXT_BOUNDED_METRICS), x=_nonempty_text)
    def test_reflexivity_perfect_score(self, metric, x):
        ev = _make_evaluator()
        nx = ev._normalize_value(x, "text")
        v = _score(ev, metric, nx, nx)
        # Identical inputs => perfect similarity for these metrics.
        assert v == pytest.approx(1.0, abs=1e-9), f"{metric}(x,x) = {v} (x={x!r})"

    @settings(max_examples=40, deadline=None)
    @given(metric=st.sampled_from(_TEXT_BOUNDED_METRICS), other=_text)
    def test_empty_handling_stays_in_range(self, metric, other):
        ev = _make_evaluator()
        no = ev._normalize_value(other, "text")
        for gt, pred in (("", ""), ("", no), (no, "")):
            v = _score(ev, metric, gt, pred)
            assert 0.0 <= v <= 1.0, f"{metric}({gt!r},{pred!r}) = {v} out of range"

    @settings(max_examples=40, deadline=None)
    @given(metric=st.sampled_from(_TEXT_BOUNDED_METRICS), gt=_text, pred=_text)
    def test_deterministic(self, metric, gt, pred):
        ev = _make_evaluator()
        g = ev._normalize_value(gt, "text")
        p = ev._normalize_value(pred, "text")
        assert _score(ev, metric, g, p) == _score(ev, metric, g, p)


class TestExactMatchSemantics:
    @settings(max_examples=60, deadline=None)
    @given(gt=_text, pred=_text)
    def test_exact_match_is_indicator_of_equality(self, gt, pred):
        ev = _make_evaluator()
        g = ev._normalize_value(gt, "text")
        p = ev._normalize_value(pred, "text")
        v = _score(ev, "exact_match", g, p)
        assert v == (1.0 if g == p else 0.0)


class TestClassificationSingleSample:
    # For a single sample precision/recall/f1/cohen_kappa collapse to a binary
    # correct/incorrect indicator — must be exactly 0.0 or 1.0, never anything
    # in between, and 1.0 iff equal.
    @settings(max_examples=60, deadline=None)
    @given(
        metric=st.sampled_from(["precision", "recall", "f1", "cohen_kappa", "confusion_matrix"]),
        gt=_text,
        pred=_text,
    )
    def test_binary_indicator(self, metric, gt, pred):
        ev = _make_evaluator()
        g = ev._normalize_value(gt, "text")
        p = ev._normalize_value(pred, "text")
        v = _score(ev, metric, g, p)
        assert v in (0.0, 1.0)
        assert (v == 1.0) == (g == p)


class TestTokenF1:
    @settings(max_examples=60, deadline=None)
    @given(gt=_text, pred=_text)
    def test_bounded(self, gt, pred):
        ev = _make_evaluator()
        v = ev._compute_token_f1(gt, pred)
        assert 0.0 <= v <= 1.0

    @settings(max_examples=60, deadline=None)
    @given(x=_nonempty_text)
    def test_reflexivity_nonempty(self, x):
        ev = _make_evaluator()
        # token_f1 lowercases internally; a string with at least one
        # whitespace-delimited token scores 1.0 against itself.
        if x.split():  # has at least one token
            assert ev._compute_token_f1(x, x) == pytest.approx(1.0, abs=1e-9)

    @settings(max_examples=60, deadline=None)
    @given(gt=_text, pred=_text)
    def test_symmetry(self, gt, pred):
        ev = _make_evaluator()
        # F1 over bag-of-tokens is symmetric (precision/recall swap).
        assert ev._compute_token_f1(gt, pred) == pytest.approx(
            ev._compute_token_f1(pred, gt), abs=1e-9
        )


class TestSetMetrics:
    @settings(max_examples=60, deadline=None)
    @given(metric=st.sampled_from(_SET_SYMMETRIC_METRICS), a=_label_list, b=_label_list)
    def test_bounded(self, metric, a, b):
        ev = _make_evaluator()
        v = ev._compute_set_metric(metric, a, b)
        assert 0.0 <= v <= 1.0

    @settings(max_examples=60, deadline=None)
    @given(metric=st.sampled_from(_SET_SYMMETRIC_METRICS), a=_label_list, b=_label_list)
    def test_symmetry(self, metric, a, b):
        ev = _make_evaluator()
        # jaccard / subset_accuracy / hamming_loss are all symmetric in their
        # two set arguments (intersection / union / symmetric-difference).
        assert ev._compute_set_metric(metric, a, b) == pytest.approx(
            ev._compute_set_metric(metric, b, a), abs=1e-9
        )

    @settings(max_examples=40, deadline=None)
    @given(a=_label_list)
    def test_jaccard_reflexive_and_subset_reflexive(self, a):
        ev = _make_evaluator()
        # Identical sets: jaccard == 1, subset_accuracy == 1, hamming_loss == 0.
        assert ev._compute_set_metric("jaccard", a, a) == pytest.approx(1.0, abs=1e-9)
        assert ev._compute_set_metric("subset_accuracy", a, a) == 1.0
        assert ev._compute_set_metric("hamming_loss", a, a) == pytest.approx(0.0, abs=1e-9)

    def test_both_empty_edge_cases(self):
        ev = _make_evaluator()
        assert ev._compute_set_metric("jaccard", [], []) == 1.0
        assert ev._compute_set_metric("subset_accuracy", [], []) == 1.0
        assert ev._compute_set_metric("hamming_loss", [], []) == 0.0


class TestEditDistanceRatio:
    @settings(max_examples=60, deadline=None)
    @given(gt=_text, pred=_text)
    def test_bounded_and_symmetric(self, gt, pred):
        ev = _make_evaluator()
        v_ab = ev._compute_text_similarity("edit_distance", gt, pred)
        v_ba = ev._compute_text_similarity("edit_distance", pred, gt)
        assert 0.0 <= v_ab <= 1.0
        # Levenshtein distance is a metric (symmetric), and the normaliser
        # (max length) is symmetric too.
        assert v_ab == pytest.approx(v_ba, abs=1e-9)

    @settings(max_examples=40, deadline=None)
    @given(x=_text)
    def test_reflexive_one(self, x):
        ev = _make_evaluator()
        assert ev._compute_text_similarity("edit_distance", x, x) == pytest.approx(1.0, abs=1e-9)


class TestLevenshteinDistance:
    @settings(max_examples=60, deadline=None)
    @given(a=_text, b=_text)
    def test_metric_axioms(self, a, b):
        ev = _make_evaluator()
        d_ab = ev._levenshtein_distance(a, b)
        d_ba = ev._levenshtein_distance(b, a)
        # Non-negativity, symmetry, identity-of-indiscernibles, and the bound
        # d <= max(len) that the edit_distance ratio relies on for [0,1].
        assert d_ab >= 0
        assert d_ab == d_ba
        assert (d_ab == 0) == (a == b)
        assert d_ab <= max(len(a), len(b))


class TestStructuredAndHierarchicalBounded:
    @settings(max_examples=50, deadline=None)
    @given(
        gt=st.dictionaries(_label, st.integers(-5, 5), max_size=4),
        pred=st.dictionaries(_label, st.integers(-5, 5), max_size=4),
    )
    def test_json_and_field_accuracy_bounded(self, gt, pred):
        ev = _make_evaluator()
        for metric in ("json_accuracy",):
            v = ev._compute_structured_metric(metric, gt, pred)
            assert 0.0 <= v <= 1.0
        v_field = ev._compute_field_accuracy(gt, pred)
        assert 0.0 <= v_field <= 1.0

    @settings(max_examples=40, deadline=None)
    @given(d=st.dictionaries(_label, st.integers(-5, 5), min_size=1, max_size=4))
    def test_json_accuracy_reflexive(self, d):
        ev = _make_evaluator()
        assert ev._compute_structured_metric("json_accuracy", d, d) == pytest.approx(1.0, abs=1e-9)
        assert ev._compute_field_accuracy(d, d) == pytest.approx(1.0, abs=1e-9)

    @settings(max_examples=50, deadline=None)
    @given(gt=_label_list, pred=_label_list)
    def test_hierarchical_metrics_bounded(self, gt, pred):
        ev = _make_evaluator()
        for metric in ("hierarchical_f1", "path_accuracy", "lca_accuracy"):
            v = ev._compute_hierarchical_metric(metric, gt, pred)
            assert 0.0 <= v <= 1.0, f"{metric}({gt},{pred}) = {v}"

    @settings(max_examples=40, deadline=None)
    @given(path=st.lists(_label, min_size=1, max_size=5))
    def test_hierarchical_reflexive(self, path):
        ev = _make_evaluator()
        for metric in ("hierarchical_f1", "path_accuracy", "lca_accuracy"):
            assert ev._compute_hierarchical_metric(metric, path, path) == pytest.approx(
                1.0, abs=1e-9
            ), metric


class TestSpanMetricsBounded:
    @st.composite
    def _span_list(draw):
        n = draw(st.integers(min_value=0, max_value=4))
        spans = []
        for _ in range(n):
            start = draw(_pos)
            length = draw(st.integers(min_value=0, max_value=20))
            spans.append({"start": start, "end": start + length})
        return spans

    @settings(max_examples=50, deadline=None)
    @given(gt=_span_list(), pred=_span_list())
    def test_span_exact_match_and_iou_bounded(self, gt, pred):
        ev = _make_evaluator()
        v_em = ev._compute_span_metric("exact_match", gt, pred)
        v_iou = ev._compute_span_metric("iou", gt, pred)
        assert v_em in (0.0, 1.0)
        assert 0.0 <= v_iou <= 1.0

    @settings(max_examples=50, deadline=None)
    @given(gt=_span_list(), pred=_span_list())
    def test_partial_and_boundary_bounded(self, gt, pred):
        ev = _make_evaluator()
        v_partial = ev._compute_partial_match(gt, pred)
        v_boundary = ev._compute_boundary_accuracy(gt, pred)
        assert 0.0 <= v_partial <= 1.0
        assert 0.0 <= v_boundary <= 1.0

    @settings(max_examples=40, deadline=None)
    @given(
        spans=st.lists(
            st.builds(
                lambda s, ln: {"start": s, "end": s + ln},
                _pos,
                st.integers(min_value=1, max_value=20),  # positive length only
            ),
            min_size=1,
            max_size=4,
        )
    )
    def test_iou_reflexive_when_nonempty(self, spans):
        ev = _make_evaluator()
        # A set of POSITIVE-LENGTH spans matched against itself is a perfect IoU
        # (each span's IoU with itself is 1.0; the optimal assignment picks the
        # diagonal). NOTE: zero-length spans correctly score 0.0 — _span_iou
        # returns 0.0 when union==0, since an empty span has no area to overlap.
        v = ev._compute_span_metric("iou", spans, spans)
        assert v == pytest.approx(1.0, abs=1e-9)
        assert ev._compute_span_metric("exact_match", spans, spans) == 1.0


class TestComputeMetricDispatchNoCrash:
    @settings(max_examples=40, deadline=None)
    @given(
        metric=st.sampled_from(
            _TEXT_BOUNDED_METRICS
            + ["precision", "recall", "f1", "cohen_kappa", "token_f1"]
        ),
        gt=_text,
        pred=_text,
    )
    def test_public_compute_metric_returns_bounded_float(self, metric, gt, pred):
        # Exercise the registry-aware public entry point (the one the worker
        # pipeline actually calls). Result must be a float in [0, 1] for these
        # deterministic metrics, never raise.
        ev = _make_evaluator()
        v = ev._compute_metric(metric, gt, pred, "text", {})
        assert isinstance(v, float)
        assert 0.0 <= v <= 1.0
