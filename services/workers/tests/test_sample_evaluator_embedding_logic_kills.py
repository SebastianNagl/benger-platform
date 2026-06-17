"""Mutation-kill tests for the EMBEDDING / SCORE-EXTRACTION logic in
``ml_evaluation/sample_evaluator.py``.

These three methods compute the platform's HEADLINE academic metrics —
BERTScore F1 and semantic (cosine) similarity. A flipped operator in the
cosine formula, a wrong F1 unwrap (``float(F1)`` vs ``float(F1.mean().item())``),
a missing ``max(0.0, …)`` clamp, or a mis-routed metric name would each produce
a *silently wrong published score*. We therefore MOCK the ML backend so the math
is fully deterministic, and assert the EXACT hand-computed value, the backend
provenance string, the language default, and the documented error branches.

The real ONNX / sentence-transformers / bert-score backends download multi-GB
models and are non-deterministic across hardware — none of that is exercised
here. We pin only the pure arithmetic and the if/elif dispatch that the source
performs on top of whatever vectors / tuples the backend hands back, by
substituting fixed vectors and fixed (P, R, F1) triples.

Target methods (line refs are approximate to source at authoring time):
  * ``_semantic_similarity_with_details``  (~889-932)
  * ``_bertscore_with_details``            (~848-887)
  * ``_compute_semantic_metric``           (~1294-1383)

Cosine reminder used throughout::

    cos(a, b) = dot(a, b) / (||a|| * ||b|| + 1e-9)

then the source clamps with ``max(0.0, float(cos))``.

The ``+ 1e-9`` epsilon in the denominator is a divide-by-zero guard. For unit
vectors (||a|| = ||b|| = 1) the denominator is ``1*1 + 1e-9 = 1.000000001`` so
the result is the ideal cosine divided by 1.000000001 — i.e. shifted by < 1e-9,
far below any ``pytest.approx`` tolerance. We assert that shift is immaterial.
"""

import math
import os
import sys

import numpy as np
import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation import sample_evaluator as se  # noqa: E402
from ml_evaluation.sample_evaluator import SampleEvaluator  # noqa: E402


@pytest.fixture
def ev():
    """Same construction as the sibling mutation-kill suite."""
    return SampleEvaluator(evaluation_id="mut-test", field_configs={})


# ---------------------------------------------------------------------------
# Test doubles for the ML backends.
# ---------------------------------------------------------------------------


class FakeEmbeddingBackend:
    """Stand-in for ``selector.get_embedding_backend()``.

    Source calls ``backend.encode([gt_str])[0]`` then ``backend.encode([pred_str])[0]``
    — i.e. ``encode`` receives a *list with one string* and returns a *list of
    vectors*; the source then takes ``[0]``. We map each input string to a fixed
    ``np.array`` so the cosine is fully determined by the test, not by any model.
    """

    def __init__(self, vec_for):
        # vec_for: dict[str, np.ndarray] mapping the raw string -> its embedding
        self.vec_for = vec_for
        self.calls = []

    def encode(self, texts):
        assert isinstance(texts, list) and len(texts) == 1, (
            "source must call encode([single_str]); got %r" % (texts,)
        )
        s = texts[0]
        self.calls.append(s)
        return [self.vec_for[s]]


class FakeBertScoreBackend:
    """Stand-in for ``selector.get_bertscore_backend()`` (ONNX path).

    Source: ``P, R, F1 = backend.compute([pred_str], [gt_str], lang=lang)`` then
    ``f1_value = float(F1)``. We return a fixed (P, R, F1) triple of plain floats
    and record the call so we can assert argument *order* (pred first, gt second)
    and the ``lang`` kwarg.
    """

    def __init__(self, triple):
        self.triple = triple
        self.calls = []

    def compute(self, preds, gts, lang=None):
        self.calls.append({"preds": preds, "gts": gts, "lang": lang})
        return self.triple


class FakeSelector:
    """Stand-in for the module-level ``backend_selector`` returned by
    ``_get_backend_selector()``. Only the two getters the targets use."""

    def __init__(self, embedding_backend=None, bertscore_backend=None):
        self._embedding_backend = embedding_backend
        self._bertscore_backend = bertscore_backend

    def get_embedding_backend(self):
        return self._embedding_backend

    def get_bertscore_backend(self):
        return self._bertscore_backend


class FakeMeanItem:
    """Mimics a torch tensor far enough for the pytorch BERTScore path.

    Source: ``f1_value = float(F1.mean().item())``. So ``F1`` must expose
    ``.mean()`` returning an object with ``.item()`` returning a float.
    """

    def __init__(self, value):
        self._value = value

    def mean(self):
        return self

    def item(self):
        return self._value


# ===========================================================================
# _semantic_similarity_with_details — COSINE MATH (ARM64 / ONNX path)
# ===========================================================================


def _force_arm_with_embeddings(monkeypatch, vec_for):
    """Force IS_ARM64 True and wire a fake embedding backend returning vec_for."""
    monkeypatch.setattr(se, "IS_ARM64", True)
    backend = FakeEmbeddingBackend(vec_for)
    monkeypatch.setattr(se, "_get_backend_selector", lambda: FakeSelector(embedding_backend=backend))
    return backend


def test_semantic_similarity_identical_unit_vectors_is_one(ev, monkeypatch):
    """gt=[1,0], pred=[1,0] -> dot=1, ||a||=||b||=1 -> cos = 1/(1+1e-9) ≈ 1.0.

    Pins: the dot product numerator, both norms in the denominator, and that the
    +1e-9 epsilon does NOT materially move a unit-vector result (approx 1.0).
    Kills a numerator/denominator swap or a dropped norm (which would give != 1).
    """
    _force_arm_with_embeddings(
        monkeypatch,
        {"truth": np.array([1.0, 0.0]), "guess": np.array([1.0, 0.0])},
    )
    out = ev._semantic_similarity_with_details("truth", "guess", {})
    assert out["value"] == pytest.approx(1.0, abs=1e-7)
    # epsilon really is below tolerance, but strictly < 1.0:
    assert out["value"] < 1.0
    assert out["method"] == "semantic_similarity"
    assert out["details"]["backend"] == "onnx"
    assert out["details"]["model"] == "MiniLM-onnx"
    assert out["error"] is None


def test_semantic_similarity_orthogonal_is_zero(ev, monkeypatch):
    """gt=[1,0], pred=[0,1] -> dot=0 -> cos=0 -> max(0.0,0.0)=0.0.

    Kills a mutated numerator that uses something other than the true dot
    product (any non-zero dot here would break the 0.0 assertion).
    """
    _force_arm_with_embeddings(
        monkeypatch,
        {"a": np.array([1.0, 0.0]), "b": np.array([0.0, 1.0])},
    )
    out = ev._semantic_similarity_with_details("a", "b", {})
    assert out["value"] == pytest.approx(0.0, abs=1e-7)


def test_semantic_similarity_45deg_is_inv_sqrt2(ev, monkeypatch):
    """gt=[1,1], pred=[1,0]:
        dot = 1*1 + 1*0 = 1
        ||gt|| = sqrt(2), ||pred|| = 1
        cos = 1 / (sqrt(2)*1 + 1e-9) ≈ 1/sqrt(2) ≈ 0.70710678.

    This is the load-bearing geometry test: it pins BOTH norms simultaneously
    (dropping either norm changes the value), the dot, and the division.
    """
    _force_arm_with_embeddings(
        monkeypatch,
        {"gt": np.array([1.0, 1.0]), "pr": np.array([1.0, 0.0])},
    )
    out = ev._semantic_similarity_with_details("gt", "pr", {})
    assert out["value"] == pytest.approx(1.0 / math.sqrt(2.0), abs=1e-6)


def test_semantic_similarity_antiparallel_is_clamped_to_zero(ev, monkeypatch):
    """gt=[1,0], pred=[-1,0] -> dot=-1, norms=1 -> cos=-1 -> max(0.0,-1)=0.0.

    Pins the ``max(0.0, …)`` clamp. Without the clamp the raw cosine is ~-1.0;
    a published similarity of -1.0 would be nonsensical, so the clamp is
    scientifically load-bearing. Kills removal of ``max(0.0, …)``.
    """
    _force_arm_with_embeddings(
        monkeypatch,
        {"x": np.array([1.0, 0.0]), "y": np.array([-1.0, 0.0])},
    )
    out = ev._semantic_similarity_with_details("x", "y", {})
    assert out["value"] == 0.0


def test_semantic_similarity_scale_invariant(ev, monkeypatch):
    """Cosine ignores magnitude: gt=[3,4] (||=5), pred=[3,4] -> cos≈1.0.
    Also gt=[3,4], pred=[6,8] (parallel, scaled) -> still cos≈1.0.

    Confirms the *normalization* divides by the product of norms (not, say, by a
    single norm or by nothing) — a magnitude leak would push this away from 1.0.
    """
    _force_arm_with_embeddings(
        monkeypatch,
        {"p": np.array([3.0, 4.0]), "q": np.array([6.0, 8.0])},
    )
    out = ev._semantic_similarity_with_details("p", "q", {})
    assert out["value"] == pytest.approx(1.0, abs=1e-7)


def test_semantic_similarity_encodes_gt_then_pred_separately(ev, monkeypatch):
    """The source encodes gt and pred as two separate one-element batches.
    Assert both raw strings reached encode() so a swapped/duplicated arg
    (encoding pred twice) is caught.
    """
    backend = _force_arm_with_embeddings(
        monkeypatch,
        {"the truth": np.array([1.0, 0.0]), "the guess": np.array([0.0, 1.0])},
    )
    ev._semantic_similarity_with_details("the truth", "the guess", {})
    assert backend.calls == ["the truth", "the guess"]


# ---- non-ARM branch: documented RuntimeError when model fails to load --------


def test_semantic_similarity_non_arm_none_model_raises_runtimeerror(ev, monkeypatch):
    """IS_ARM64 False + ``_get_sentence_transformer()`` returns None ->
    the documented RuntimeError('… could not be loaded …').

    Kills a mutant that drops the ``if model is None: raise`` guard (which would
    instead NPE on ``model.encode`` with a less actionable error).
    """
    monkeypatch.setattr(se, "IS_ARM64", False)
    monkeypatch.setattr(se, "_get_sentence_transformer", lambda: None)
    with pytest.raises(RuntimeError, match="could not be loaded"):
        ev._semantic_similarity_with_details("a", "b", {})


def test_semantic_similarity_non_arm_uses_cos_sim_and_clamps(ev, monkeypatch):
    """IS_ARM64 False, a fake sentence-transformer model + a fake ``st_util``
    whose ``cos_sim(...).item()`` returns a NEGATIVE number -> clamped to 0.0,
    backend tagged 'pytorch'.

    Pins the non-ARM clamp ``max(0.0, float(st_util.cos_sim(...).item()))`` and
    the backend_id branch. ``model.encode`` is a no-op stub; the value comes from
    the stubbed cos_sim, so the test is fully deterministic and model-free.
    """

    class _FakeModel:
        def encode(self, text, convert_to_tensor=False):
            return text  # opaque token; cos_sim is stubbed below

        # _get_sentence_transformer's model_id line calls getattr(model,
        # "_first_module", lambda: None)(); returning falsy keeps model_id falsy.

    class _Sim:
        def item(self):
            return -0.42  # negative -> must clamp to 0.0

    class _FakeUtil:
        @staticmethod
        def cos_sim(a, b):
            return _Sim()

    monkeypatch.setattr(se, "IS_ARM64", False)
    monkeypatch.setattr(se, "_get_sentence_transformer", lambda: _FakeModel())
    monkeypatch.setattr(se, "st_util", _FakeUtil())

    out = ev._semantic_similarity_with_details("g", "p", {})
    assert out["value"] == 0.0
    assert out["details"]["backend"] == "pytorch"
    assert out["method"] == "semantic_similarity"


def test_semantic_similarity_non_arm_positive_passes_through(ev, monkeypatch):
    """Same non-ARM path but cos_sim().item() = 0.61 (>0) -> passes through
    unclamped as 0.61. Distinguishes "always returns 0" mutants from the real
    pass-through, and pairs with the negative-clamp test above.
    """

    class _FakeModel:
        def encode(self, text, convert_to_tensor=False):
            return text

    class _Sim:
        def item(self):
            return 0.61

    class _FakeUtil:
        @staticmethod
        def cos_sim(a, b):
            return _Sim()

    monkeypatch.setattr(se, "IS_ARM64", False)
    monkeypatch.setattr(se, "_get_sentence_transformer", lambda: _FakeModel())
    monkeypatch.setattr(se, "st_util", _FakeUtil())

    out = ev._semantic_similarity_with_details("g", "p", {})
    assert out["value"] == pytest.approx(0.61)
    assert out["details"]["backend"] == "pytorch"


# ===========================================================================
# _bertscore_with_details — F1 EXTRACTION + backend provenance
# ===========================================================================


def test_bertscore_arm_extracts_f1_float_and_onnx_backend(ev, monkeypatch):
    """ARM64 path: backend.compute returns (P=0.10, R=0.20, F1=0.83) ->
    f1_value = float(F1) = 0.83, backend 'onnx'.

    Kills mutants that unwrap P or R instead of F1 (would give 0.10 / 0.20), or
    that tag the wrong backend. Also asserts lang defaults to 'de' and that the
    backend received (pred, gt) in that exact order.
    """
    backend = FakeBertScoreBackend((0.10, 0.20, 0.83))
    monkeypatch.setattr(se, "IS_ARM64", True)
    monkeypatch.setattr(
        se, "_get_backend_selector", lambda: FakeSelector(bertscore_backend=backend)
    )

    out = ev._bertscore_with_details("ground truth", "prediction", {})
    assert out["value"] == pytest.approx(0.83)
    assert out["method"] == "bertscore"
    assert out["details"]["backend"] == "onnx"
    assert out["details"]["lang"] == "de"  # default
    # ONNX path never rescales:
    assert out["details"]["rescale_with_baseline"] is False
    assert out["error"] is None
    # arg order: compute([pred_str], [gt_str], lang=...)
    assert backend.calls[0]["preds"] == ["prediction"]
    assert backend.calls[0]["gts"] == ["ground truth"]
    assert backend.calls[0]["lang"] == "de"


def test_bertscore_arm_explicit_lang_overrides_default(ev, monkeypatch):
    """parameters={'lang':'en'} flows through to the backend and into details.
    Kills a mutant that hardcodes 'de' / drops the parameters.get lookup.
    """
    backend = FakeBertScoreBackend((0.0, 0.0, 0.5))
    monkeypatch.setattr(se, "IS_ARM64", True)
    monkeypatch.setattr(
        se, "_get_backend_selector", lambda: FakeSelector(bertscore_backend=backend)
    )
    out = ev._bertscore_with_details("gt", "pred", {"lang": "en"})
    assert out["details"]["lang"] == "en"
    assert backend.calls[0]["lang"] == "en"


def test_bertscore_pytorch_extracts_f1_mean_item_and_rescales(ev, monkeypatch):
    """Non-ARM path: bert_score_compute returns (P, R, F1) where F1.mean().item()
    = 0.91 -> f1_value = 0.91, backend 'pytorch', rescale_with_baseline True.

    Pins the *different* unwrap on this branch (``float(F1.mean().item())`` vs
    the ARM ``float(F1)``) and the rescale flag. We also capture the kwargs
    bert_score_compute is called with to assert rescale_with_baseline=True and
    verbose=False are actually passed to the library.
    """
    captured = {}

    def fake_compute(preds, gts, lang=None, rescale_with_baseline=None, verbose=None):
        captured.update(
            preds=preds,
            gts=gts,
            lang=lang,
            rescale_with_baseline=rescale_with_baseline,
            verbose=verbose,
        )
        # P, R are unused on this path; F1 needs .mean().item():
        return (FakeMeanItem(0.0), FakeMeanItem(0.0), FakeMeanItem(0.91))

    monkeypatch.setattr(se, "IS_ARM64", False)
    monkeypatch.setattr(se, "bert_score_compute", fake_compute)

    out = ev._bertscore_with_details("the gt", "the pred", {})
    assert out["value"] == pytest.approx(0.91)
    assert out["details"]["backend"] == "pytorch"
    assert out["details"]["rescale_with_baseline"] is True
    assert out["details"]["lang"] == "de"
    # library actually invoked with rescale + quiet, pred-first/gt-second:
    assert captured["preds"] == ["the pred"]
    assert captured["gts"] == ["the gt"]
    assert captured["rescale_with_baseline"] is True
    assert captured["verbose"] is False
    assert captured["lang"] == "de"


def test_bertscore_pytorch_explicit_lang(ev, monkeypatch):
    """Non-ARM path honours an explicit lang too."""

    def fake_compute(preds, gts, lang=None, rescale_with_baseline=None, verbose=None):
        return (FakeMeanItem(0.0), FakeMeanItem(0.0), FakeMeanItem(0.4))

    monkeypatch.setattr(se, "IS_ARM64", False)
    monkeypatch.setattr(se, "bert_score_compute", fake_compute)
    out = ev._bertscore_with_details("gt", "pred", {"lang": "fr"})
    assert out["details"]["lang"] == "fr"
    assert out["value"] == pytest.approx(0.4)


def test_bertscore_details_host_arch_present(ev, monkeypatch):
    """details['host_arch'] is platform.machine() — a non-empty provenance
    string. Kills a mutant that drops the key (researchers filter on it).
    """
    backend = FakeBertScoreBackend((0.0, 0.0, 0.7))
    monkeypatch.setattr(se, "IS_ARM64", True)
    monkeypatch.setattr(
        se, "_get_backend_selector", lambda: FakeSelector(bertscore_backend=backend)
    )
    out = ev._bertscore_with_details("gt", "pred", {})
    assert "host_arch" in out["details"]
    assert isinstance(out["details"]["host_arch"], str)
    assert out["details"]["host_arch"] != ""


# ===========================================================================
# _compute_semantic_metric — metric-name routing + extraction (scalar return)
# ===========================================================================


def test_compute_semantic_metric_bertscore_arm_returns_f1_float(ev, monkeypatch):
    """metric='bertscore', ARM64: returns float(F1) of the (P,R,F1) triple.
    F1=0.77 -> 0.77. Kills routing to the wrong branch or unwrapping P/R.
    """
    backend = FakeBertScoreBackend((0.1, 0.2, 0.77))
    monkeypatch.setattr(se, "IS_ARM64", True)
    monkeypatch.setattr(
        se, "_get_backend_selector", lambda: FakeSelector(bertscore_backend=backend)
    )
    val = ev._compute_semantic_metric("bertscore", "gt", "pred")
    assert val == pytest.approx(0.77)
    # default lang 'de', pred-first/gt-second:
    assert backend.calls[0]["lang"] == "de"
    assert backend.calls[0]["preds"] == ["pred"]
    assert backend.calls[0]["gts"] == ["gt"]


def test_compute_semantic_metric_bertscore_pytorch_returns_mean_item(ev, monkeypatch):
    """metric='bertscore', non-ARM: returns float(F1.mean().item()) = 0.66."""
    monkeypatch.setattr(se, "IS_ARM64", False)
    monkeypatch.setattr(
        se,
        "bert_score_compute",
        lambda preds, gts, lang=None, rescale_with_baseline=None, verbose=None: (
            FakeMeanItem(0.0),
            FakeMeanItem(0.0),
            FakeMeanItem(0.66),
        ),
    )
    val = ev._compute_semantic_metric("bertscore", "gt", "pred")
    assert val == pytest.approx(0.66)


def test_compute_semantic_metric_semantic_similarity_arm_cosine(ev, monkeypatch):
    """metric='semantic_similarity', ARM64, gt=[1,1]/pred=[1,0] -> 1/sqrt(2).
    Same cosine geometry as the details method, but via the scalar dispatch.
    """
    _force_arm_with_embeddings(
        monkeypatch,
        {"gt": np.array([1.0, 1.0]), "pr": np.array([1.0, 0.0])},
    )
    val = ev._compute_semantic_metric("semantic_similarity", "gt", "pr")
    assert val == pytest.approx(1.0 / math.sqrt(2.0), abs=1e-6)


def test_compute_semantic_metric_semantic_similarity_arm_clamp(ev, monkeypatch):
    """Anti-parallel vectors -> raw cosine -1 -> clamped to 0.0 on the scalar
    dispatch path too (mirrors the details-method clamp test)."""
    _force_arm_with_embeddings(
        monkeypatch,
        {"x": np.array([1.0, 0.0]), "y": np.array([-1.0, 0.0])},
    )
    val = ev._compute_semantic_metric("semantic_similarity", "x", "y")
    assert val == 0.0


def test_compute_semantic_metric_unknown_raises_valueerror(ev):
    """An unrouted metric name hits the final ``raise ValueError``.
    Kills a mutant that silently returns instead of raising — which would let an
    unsupported metric publish a bogus 0.0/None.
    """
    with pytest.raises(ValueError, match="Unknown semantic metric"):
        ev._compute_semantic_metric("not_a_real_metric", "gt", "pred")


def test_compute_semantic_metric_moverscore_empty_gt_raises(ev):
    """metric='moverscore' with empty/blank gt -> ValueError BEFORE any backend
    is touched. Pins the input-guard branch (non-empty gt required). No model
    download occurs because the guard short-circuits.
    """
    with pytest.raises(ValueError, match="non-empty ground truth"):
        ev._compute_semantic_metric("moverscore", "   ", "some prediction")


def test_compute_semantic_metric_moverscore_empty_pred_raises(ev):
    """Blank pred -> the prediction-side guard fires."""
    with pytest.raises(ValueError, match="non-empty prediction"):
        ev._compute_semantic_metric("moverscore", "some ground truth", "   ")


def test_compute_semantic_metric_moverscore_too_short_raises(ev):
    """gt/pred shorter than 3 chars -> the length guard fires (still no backend).
    'ab' is non-empty but len 2 < 3.
    """
    with pytest.raises(ValueError, match="longer than 3 characters"):
        ev._compute_semantic_metric("moverscore", "ab", "cd")


def test_compute_semantic_metric_moverscore_extracts_first_score(ev, monkeypatch):
    """metric='moverscore', valid inputs: ``computer.compute_moverscore`` returns
    [0.55, 0.99] -> the source returns ``float(scores[0])`` = 0.55.

    Kills a mutant that indexes the wrong element or averages. Also asserts the
    n_gram / remove_subwords defaults (1 / True) are forwarded.
    """

    captured = {}

    class _Computer:
        def compute_moverscore(self, gts, preds, n_gram=None, remove_subwords=None):
            captured.update(
                gts=gts, preds=preds, n_gram=n_gram, remove_subwords=remove_subwords
            )
            return [0.55, 0.99]

    class _Sel:
        def get_moverscore_computer(self):
            return _Computer()

    monkeypatch.setattr(se, "_get_backend_selector", lambda: _Sel())

    val = ev._compute_semantic_metric("moverscore", "ground truth text", "prediction text")
    assert val == pytest.approx(0.55)  # scores[0], not scores[1]/mean
    assert captured["n_gram"] == 1  # default
    assert captured["remove_subwords"] is True  # default
    # source passes ([gt], [pred]) in that order to compute_moverscore:
    assert captured["gts"] == ["ground truth text"]
    assert captured["preds"] == ["prediction text"]


def test_compute_semantic_metric_moverscore_empty_scores_returns_zero(ev, monkeypatch):
    """If the computer returns an empty list, the source's
    ``float(scores[0]) if scores else 0.0`` falls to 0.0.
    Kills a mutant that drops the ``if scores`` guard (which would IndexError).
    """

    class _Computer:
        def compute_moverscore(self, gts, preds, n_gram=None, remove_subwords=None):
            return []

    class _Sel:
        def get_moverscore_computer(self):
            return _Computer()

    monkeypatch.setattr(se, "_get_backend_selector", lambda: _Sel())
    val = ev._compute_semantic_metric("moverscore", "ground truth", "prediction")
    assert val == 0.0
