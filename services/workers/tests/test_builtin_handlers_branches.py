"""Branch-coverage tests for ml_evaluation/builtin_handlers.py.

builtin_handlers wraps every platform metric in a MetricHandler so the registry
can dispatch them. The handler bodies are the uncovered lines: the generic
``_LegacyMetricHandler.compute`` adapter (which routes through
``SampleEvaluator._compute_metric_legacy``) and the five provenance-rich
handlers (coherence / moverscore / qags / bertscore / semantic_similarity)
that delegate to the corresponding ``_..._with_details`` helper.

Strategy (mirrors test_sample_evaluator_branches.py):
  * ``_LegacyMetricHandler`` is driven with ``exact_match`` / ``f1`` — pure
    lexical metrics that need no neural backend — and we assert the wrapped
    ``{value, method, details, error}`` shape and the parameter provenance.
  * Each provenance handler is exercised with its neural backend mocked through
    ``_get_backend_selector`` (or, for coherence, the ``_compute_*_coherence``
    sub-scores patched). We assert the handler forwards the helper's result dict
    unchanged — same ``value`` / ``method`` the helper produced.

No model is downloaded. ``register_builtin_metric_handlers`` is exercised
through a real ``MetricRegistry`` so the registration path (and every handler's
presence) is covered behaviorally, not via a registration-only assertion.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

SE_MOD = "ml_evaluation.sample_evaluator"

from ml_evaluation.builtin_handlers import (  # noqa: E402
    _LegacyMetricHandler,
    _CoherenceHandler,
    _MoverScoreHandler,
    _QAGSHandler,
    _BERTScoreHandler,
    _SemanticSimilarityHandler,
    register_builtin_metric_handlers,
    PLATFORM_METRIC_NAMES,
)


# ============================================================================
# _LegacyMetricHandler — generic adapter over the legacy if/elif chain
# ============================================================================


class TestLegacyMetricHandler:
    def test_exact_match_hit_returns_standard_shape(self):
        h = _LegacyMetricHandler("exact_match")
        result = h.compute("hello world", "hello world", "text", {})
        assert result["value"] == 1.0
        assert result["method"] == "exact_match"
        assert result["details"]["registered_via"] == "_LegacyMetricHandler"
        assert result["details"]["parameters_applied"] == {}
        assert result["error"] is None

    def test_exact_match_miss_returns_zero(self):
        h = _LegacyMetricHandler("exact_match")
        result = h.compute("hello", "world", "text", None)
        assert result["value"] == 0.0
        # parameters=None -> empty provenance dict, not None
        assert result["details"]["parameters_applied"] == {}

    def test_parameters_are_echoed_into_provenance(self):
        h = _LegacyMetricHandler("f1")
        params = {"average": "macro"}
        result = h.compute("a b c", "a b", "text", params)
        assert result["method"] == "f1"
        assert result["details"]["parameters_applied"] == {"average": "macro"}
        # f1 is a real number in [0, 1]
        assert 0.0 <= result["value"] <= 1.0

    def test_default_answer_type_when_none(self):
        """A None answer_type must not crash — the handler substitutes 'text'."""
        h = _LegacyMetricHandler("exact_match")
        result = h.compute("same", "same", None, {})
        assert result["value"] == 1.0


# ============================================================================
# _CoherenceHandler — delegates to _coherence_with_details(prediction, params)
# ============================================================================


class TestCoherenceHandler:
    def test_forwards_semantic_score(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator

        h = _CoherenceHandler()
        text = "Der Vertrag ist gueltig. Die Parteien haben zugestimmt."
        with patch.object(
            SampleEvaluator, "_compute_semantic_coherence", return_value=0.8
        ):
            result = h.compute("ignored-ground-truth", text, "text", {"method": "semantic"})
        assert abs(result["value"] - 0.8) < 1e-9
        assert result["method"] == "coherence"
        assert result["details"]["methods_used"] == ["semantic"]
        assert result["error"] is None

    def test_invalid_method_propagates_value_error(self):
        h = _CoherenceHandler()
        text = "The contract is valid here. All parties agreed clearly to it."
        with pytest.raises(ValueError, match="Invalid coherence method"):
            h.compute("gt", text, "text", {"method": "bogus"})


# ============================================================================
# _MoverScoreHandler — delegates to _moverscore_with_details(gt, pred, params)
# ============================================================================


class TestMoverScoreHandler:
    def test_forwards_backend_score(self):
        h = _MoverScoreHandler()
        sel = MagicMock()
        computer = MagicMock()
        computer.compute_moverscore.return_value = [0.73]
        sel.get_moverscore_computer.return_value = computer
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            result = h.compute("ground truth text", "prediction text", "text", {"n_gram": 2})
        assert abs(result["value"] - 0.73) < 1e-9
        assert result["method"] == "moverscore"
        assert result["details"]["n_gram"] == 2

    def test_empty_inputs_raise(self):
        h = _MoverScoreHandler()
        with pytest.raises(ValueError):
            h.compute("   ", "prediction text", "text", {})


# ============================================================================
# _QAGSHandler — delegates to _qags_with_details(gt, pred, params)
# ============================================================================


class TestQAGSHandler:
    def test_all_questions_match(self):
        h = _QAGSHandler()
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?", "Q2?"]
        qb.answer_question.return_value = {"answer": "Berlin"}
        sel = MagicMock()
        sel.get_qags_backend.return_value = qb
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            result = h.compute("doc text", "pred text", "text", {})
        assert result["value"] == 1.0
        assert result["method"] == "qags"
        assert result["details"]["matched_answers"] == 2


# ============================================================================
# _BERTScoreHandler / _SemanticSimilarityHandler — delegate to with_details
# ============================================================================


class TestBERTScoreHandler:
    def test_forwards_onnx_backend_score(self):
        """Force the ARM64/ONNX branch so no real bert-score model loads; the
        backend's compute() returns (P, R, F1) and the handler must surface F1."""
        h = _BERTScoreHandler()
        backend = MagicMock()
        backend.compute.return_value = (0.5, 0.6, 0.77)
        sel = MagicMock()
        sel.get_bertscore_backend.return_value = backend
        with patch(f"{SE_MOD}.IS_ARM64", True), patch(
            f"{SE_MOD}._get_backend_selector", return_value=sel
        ):
            result = h.compute("ref text", "cand text", "text", {})
        assert abs(result["value"] - 0.77) < 1e-9
        assert result["method"] == "bertscore"
        assert result["details"]["backend"] == "onnx"


class TestSemanticSimilarityHandler:
    def test_forwards_onnx_cosine(self):
        """ARM64/ONNX branch: identical encoded vectors -> cosine 1.0."""
        import numpy as np

        h = _SemanticSimilarityHandler()
        backend = MagicMock()
        vec = np.array([1.0, 0.0, 0.0])
        backend.encode.side_effect = [[vec], [vec]]
        sel = MagicMock()
        sel.get_embedding_backend.return_value = backend
        with patch(f"{SE_MOD}.IS_ARM64", True), patch(
            f"{SE_MOD}._get_backend_selector", return_value=sel
        ):
            result = h.compute("a contract clause", "a contract clause", "text", {})
        assert result["value"] == pytest.approx(1.0)
        assert result["method"] == "semantic_similarity"
        assert result["details"]["backend"] == "onnx"


# ============================================================================
# register_builtin_metric_handlers — behavioral registration check
# ============================================================================


class TestRegisterBuiltinHandlers:
    def test_registers_provenance_and_generic_handlers(self):
        from ml_evaluation.handlers import MetricRegistry

        registry = MetricRegistry()
        register_builtin_metric_handlers(registry)

        # The five provenance-rich metrics resolve to a handler.
        for name in ("coherence", "moverscore", "qags", "bertscore", "semantic_similarity"):
            assert registry.get(name) is not None, f"{name} not registered"

        # Every generic platform metric resolves to a handler that computes a
        # standard dict for a pure-lexical metric.
        for name in PLATFORM_METRIC_NAMES:
            assert registry.get(name) is not None, f"{name} not registered"

        # Behavioral spot-check: the registered exact_match handler scores a hit.
        em = registry.get("exact_match")
        out = em.compute("x", "x", "text", {})
        assert out["value"] == 1.0
