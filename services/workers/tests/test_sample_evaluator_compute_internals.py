"""Compute-internals branch coverage for ml_evaluation/sample_evaluator.py.

The existing test_sample_evaluator_branches.py and
test_sample_evaluator_legacy_dispatch.py cover the ``*_with_details``
provenance helpers and the ``_compute_metric_legacy`` dispatch chain. They do
NOT reach the *direct* compute methods that production code touches through a
different path:

  * ``_compute_semantic_coherence`` — its real body is patched out everywhere
    else; here we drive it with a mocked sentence-transformer (multi-sentence
    happy path, single-sentence early-return, model-None RuntimeError, and the
    outer-except RuntimeError).
  * ``_compute_factuality_metric("coherence", ...)`` inline path — the hybrid
    weighted average, the entity-failure-in-hybrid fallback, the entity-only
    re-raise, the total_weight==0 short-circuit, the invalid-method ValueError,
    and the unknown-metric ValueError (distinct from ``_coherence_with_details``).
  * ``_compute_factuality_metric("qags", ...)`` inline path — happy match loop,
    per-question failure counted into the denominator, no-questions guard, and
    the outer RuntimeError.
  * ``_compute_semantic_metric`` compute branches (bertscore pytorch/onnx,
    moverscore, semantic_similarity pytorch/onnx, model-None RuntimeError,
    unknown-metric ValueError) — distinct from the ``_with_details`` wrappers.
  * ``_compute_ranking_metric`` computed-correlation branches (spearman/kendall
    multi-element, ndcg non-empty) — the legacy_dispatch suite only hits the
    identical / mismatch / single-element guards.
  * ``_compute_structured_metric`` schema SchemaError arm, ``_compute_span_metric``
    unknown-metric return, ``_validate_text_for_coherence`` single-sentence
    ValueError, ``_compute_metric_with_details`` legacy fall-through wrapper.

All neural backends are mocked through ``_get_backend_selector`` /
``_get_sentence_transformer`` / ``bert_score_compute`` / ``st_util.cos_sim`` so
NO model downloads. Mirrors the patch idioms in
test_sample_evaluator_branches.py (SE_MOD module-global targets).
"""

import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SE_MOD = "ml_evaluation.sample_evaluator"


def _make_evaluator(**kwargs):
    from ml_evaluation.sample_evaluator import SampleEvaluator

    defaults = {
        "evaluation_id": "test-eval",
        "field_configs": {"f": {"type": "text"}},
    }
    defaults.update(kwargs)
    return SampleEvaluator(**defaults)


# ============================================================================
# _compute_semantic_coherence — real body (mocked sentence-transformer)
# ============================================================================


class TestComputeSemanticCoherence:
    def test_multi_sentence_averages_adjacent_cosines(self):
        """3 embeddings -> 2 adjacent cosine pairs. Each cos_sim().item()==1.0,
        so avg=1.0, coherence=(1+1)/2=1.0 (clamped)."""
        ev = _make_evaluator()
        model = MagicMock()
        # encode returns a 3-element sequence; len()-1 == 2 loop iterations.
        model.encode.return_value = [object(), object(), object()]
        cos = MagicMock()
        cos.item.return_value = 1.0
        with patch(f"{SE_MOD}._get_sentence_transformer", return_value=model), patch(
            f"{SE_MOD}.st_util.cos_sim", return_value=cos
        ):
            score = ev._compute_semantic_coherence(["a.", "b.", "c."])
        assert score == pytest.approx(1.0)

    def test_negative_cosine_maps_into_unit_range(self):
        """cos=-1.0 -> coherence=(-1+1)/2=0.0 (clamp lower bound)."""
        ev = _make_evaluator()
        model = MagicMock()
        model.encode.return_value = [object(), object()]
        cos = MagicMock()
        cos.item.return_value = -1.0
        with patch(f"{SE_MOD}._get_sentence_transformer", return_value=model), patch(
            f"{SE_MOD}.st_util.cos_sim", return_value=cos
        ):
            score = ev._compute_semantic_coherence(["a.", "b."])
        assert score == pytest.approx(0.0)

    def test_single_sentence_returns_one(self):
        """One embedding -> no adjacent pairs -> similarities empty -> 1.0."""
        ev = _make_evaluator()
        model = MagicMock()
        model.encode.return_value = [object()]
        with patch(f"{SE_MOD}._get_sentence_transformer", return_value=model), patch(
            f"{SE_MOD}.st_util.cos_sim"
        ) as cos_sim:
            score = ev._compute_semantic_coherence(["only one."])
        assert score == 1.0
        cos_sim.assert_not_called()

    def test_model_none_raises_runtime_error(self):
        """A None model is re-raised through the outer except as the generic
        'Semantic coherence computation failed' RuntimeError."""
        ev = _make_evaluator()
        with patch(f"{SE_MOD}._get_sentence_transformer", return_value=None):
            with pytest.raises(RuntimeError, match="Semantic coherence computation failed"):
                ev._compute_semantic_coherence(["a.", "b."])

    def test_encode_failure_raises_runtime_error(self):
        ev = _make_evaluator()
        model = MagicMock()
        model.encode.side_effect = RuntimeError("cuda oom")
        with patch(f"{SE_MOD}._get_sentence_transformer", return_value=model):
            with pytest.raises(RuntimeError, match="Semantic coherence computation failed"):
                ev._compute_semantic_coherence(["a.", "b."])


# ============================================================================
# _compute_factuality_metric("coherence", ...) — inline path
# ============================================================================


_LONG = "Die Klage ist begruendet. Der Beklagte hat den Vertrag verletzt."


class TestFactualityCoherenceInline:
    def test_hybrid_weighted_average(self):
        """entity 1.0 (w .6) + semantic 0.0 (w .4) -> 1*.6 + 0*.4 = 0.6."""
        ev = _make_evaluator()
        with patch.object(ev, "_compute_entity_coherence", return_value=1.0), patch.object(
            ev, "_compute_semantic_coherence", return_value=0.0
        ):
            val = ev._compute_factuality_metric("coherence", "", _LONG, {"method": "hybrid"})
        assert val == pytest.approx(0.6)

    def test_hybrid_entity_failure_falls_back_to_semantic(self):
        """Entity grid raises in hybrid mode -> swallowed, semantic-only used."""
        ev = _make_evaluator()
        with patch.object(
            ev, "_compute_entity_coherence", side_effect=RuntimeError("no entities")
        ), patch.object(ev, "_compute_semantic_coherence", return_value=0.7):
            val = ev._compute_factuality_metric("coherence", "", _LONG, {"method": "hybrid"})
        # Only semantic score present (weight 0.4), total_weight 0.4 -> 0.7.
        assert val == pytest.approx(0.7)

    def test_entity_only_failure_reraised_as_runtime_error(self):
        ev = _make_evaluator()
        with patch.object(
            ev, "_compute_entity_coherence", side_effect=RuntimeError("no entities")
        ):
            with pytest.raises(RuntimeError, match="Coherence computation failed"):
                ev._compute_factuality_metric("coherence", "", _LONG, {"method": "entity"})

    def test_total_weight_zero_short_circuits_to_zero(self):
        """Both weights 0 in hybrid -> total_weight 0 -> 0.0 (lines 1601-1602)."""
        ev = _make_evaluator()
        with patch.object(ev, "_compute_entity_coherence", return_value=1.0), patch.object(
            ev, "_compute_semantic_coherence", return_value=1.0
        ):
            val = ev._compute_factuality_metric(
                "coherence",
                "",
                _LONG,
                {"method": "hybrid", "entity_weight": 0, "semantic_weight": 0},
            )
        assert val == 0.0

    def test_invalid_method_raises_runtime_error(self):
        """A method that is neither entity/semantic/hybrid -> coherence_scores
        empty -> ValueError -> wrapped RuntimeError."""
        ev = _make_evaluator()
        with pytest.raises(RuntimeError, match="Coherence computation failed"):
            ev._compute_factuality_metric("coherence", "", _LONG, {"method": "bogus"})

    def test_unknown_factuality_metric_raises_value_error(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="Unknown factuality metric"):
            ev._compute_factuality_metric("not_a_metric", "a", "b", {})


# ============================================================================
# _compute_factuality_metric("qags", ...) — inline path
# ============================================================================


class TestFactualityQagsInline:
    def _selector_with_qags(self, qb):
        sel = MagicMock()
        sel.get_qags_backend.return_value = qb
        return sel

    def test_all_questions_match(self):
        ev = _make_evaluator()
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?", "Q2?"]
        qb.answer_question.return_value = {"answer": "same"}
        sel = self._selector_with_qags(qb)
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel), patch.object(
            ev, "_answers_match_qags", return_value=True
        ):
            val = ev._compute_factuality_metric("qags", "gt text", "pred text", {})
        assert val == pytest.approx(1.0)

    def test_per_question_failure_counts_in_denominator(self):
        """One answer_question pair raises -> that question still increments
        total_questions (line 1519) but not matching -> 1/2 = 0.5."""
        ev = _make_evaluator()
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?", "Q2?"]
        # First question: both answers ok. Second: gt answer ok, pred raises.
        qb.answer_question.side_effect = [
            {"answer": "a"},
            {"answer": "a"},
            {"answer": "a"},
            RuntimeError("model fail"),
        ]
        sel = self._selector_with_qags(qb)
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel), patch.object(
            ev, "_answers_match_qags", return_value=True
        ):
            val = ev._compute_factuality_metric("qags", "gt", "pred", {})
        assert val == pytest.approx(0.5)

    def test_no_questions_returns_zero(self):
        ev = _make_evaluator()
        qb = MagicMock()
        qb.generate_questions.return_value = []
        sel = self._selector_with_qags(qb)
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            val = ev._compute_factuality_metric("qags", "gt", "pred", {})
        assert val == 0.0

    def test_backend_failure_raises_runtime_error(self):
        ev = _make_evaluator()
        sel = MagicMock()
        sel.get_qags_backend.side_effect = RuntimeError("backend down")
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            with pytest.raises(RuntimeError, match="QAGS computation failed"):
                ev._compute_factuality_metric("qags", "gt", "pred", {})


# ============================================================================
# _compute_factuality_metric("factcc", method="factcc") — model-None guard
# ============================================================================


class TestFactualityFactccModelGuard:
    def test_factcc_model_none_raises(self):
        """With method='factcc' and the loader returning (None, None), the guard
        raises before any tensor work (lines 1431-1435). No model downloads."""
        ev = _make_evaluator()
        with patch(f"{SE_MOD}._get_factcc_model", return_value=(None, None)):
            with pytest.raises(RuntimeError, match="FactCC model could not be loaded"):
                ev._compute_factuality_metric("factcc", "src", "claim", {"method": "factcc"})

    def test_factcc_unknown_method_raises_value_error(self):
        """An unrecognised FactCC method -> ValueError (lines 1466-1469)."""
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="Unknown FactCC method"):
            ev._compute_factuality_metric("factcc", "src", "claim", {"method": "nope"})


# ============================================================================
# _compute_semantic_metric — direct compute branches
# ============================================================================


class TestComputeSemanticMetric:
    def test_bertscore_pytorch(self):
        ev = _make_evaluator()
        mock_f1 = MagicMock()
        mock_f1.mean.return_value.item.return_value = 0.88
        with patch(f"{SE_MOD}.IS_ARM64", False), patch(
            f"{SE_MOD}.bert_score_compute",
            return_value=(MagicMock(), MagicMock(), mock_f1),
        ):
            val = ev._compute_semantic_metric("bertscore", "ref", "cand", {"lang": "en"})
        assert val == pytest.approx(0.88)

    def test_bertscore_onnx(self):
        ev = _make_evaluator()
        backend = MagicMock()
        backend.compute.return_value = (0.5, 0.6, 0.73)
        sel = MagicMock()
        sel.get_bertscore_backend.return_value = backend
        with patch(f"{SE_MOD}.IS_ARM64", True), patch(
            f"{SE_MOD}._get_backend_selector", return_value=sel
        ):
            val = ev._compute_semantic_metric("bertscore", "ref", "cand", {})
        assert val == pytest.approx(0.73)

    def test_moverscore_returns_first_score(self):
        ev = _make_evaluator()
        computer = MagicMock()
        computer.compute_moverscore.return_value = [0.42]
        sel = MagicMock()
        sel.get_moverscore_computer.return_value = computer
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            val = ev._compute_semantic_metric("moverscore", "ground truth", "prediction", {})
        assert val == pytest.approx(0.42)

    def test_moverscore_empty_scores_returns_zero(self):
        ev = _make_evaluator()
        computer = MagicMock()
        computer.compute_moverscore.return_value = []
        sel = MagicMock()
        sel.get_moverscore_computer.return_value = computer
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            val = ev._compute_semantic_metric("moverscore", "ground truth", "prediction", {})
        assert val == 0.0

    def test_moverscore_empty_text_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="non-empty ground truth"):
            ev._compute_semantic_metric("moverscore", "", "prediction", {})

    def test_semantic_similarity_onnx_identical_vectors(self):
        ev = _make_evaluator()
        backend = MagicMock()
        vec = np.array([1.0, 0.0, 0.0])
        backend.encode.side_effect = [[vec], [vec]]
        sel = MagicMock()
        sel.get_embedding_backend.return_value = backend
        with patch(f"{SE_MOD}.IS_ARM64", True), patch(
            f"{SE_MOD}._get_backend_selector", return_value=sel
        ):
            val = ev._compute_semantic_metric("semantic_similarity", "ref", "cand", {})
        assert val == pytest.approx(1.0, abs=1e-6)

    def test_semantic_similarity_pytorch(self):
        ev = _make_evaluator()
        model = MagicMock()
        model.encode.side_effect = ["emb_gt", "emb_pred"]
        cos = MagicMock()
        cos.item.return_value = 0.33
        with patch(f"{SE_MOD}.IS_ARM64", False), patch(
            f"{SE_MOD}._get_sentence_transformer", return_value=model
        ), patch(f"{SE_MOD}.st_util.cos_sim", return_value=cos):
            val = ev._compute_semantic_metric("semantic_similarity", "ref", "cand", {})
        assert val == pytest.approx(0.33)

    def test_semantic_similarity_pytorch_model_none_raises(self):
        ev = _make_evaluator()
        with patch(f"{SE_MOD}.IS_ARM64", False), patch(
            f"{SE_MOD}._get_sentence_transformer", return_value=None
        ):
            with pytest.raises(RuntimeError, match="Sentence transformer model could not be loaded"):
                ev._compute_semantic_metric("semantic_similarity", "ref", "cand", {})

    def test_unknown_semantic_metric_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="Unknown semantic metric"):
            ev._compute_semantic_metric("not_real", "a", "b", {})


# ============================================================================
# _compute_ranking_metric — computed-correlation branches
# ============================================================================


class TestComputeRankingMetricComputed:
    def test_spearman_multi_element_reversed(self):
        """len>1, unequal lists -> real spearmanr. [1,2,3] vs [3,2,1] = -1 ->
        max(0.0, -1) = 0.0 (line 1213-1215)."""
        ev = _make_evaluator()
        val = ev._compute_ranking_metric("spearman", [1, 2, 3], [3, 2, 1], {})
        assert val == 0.0

    def test_spearman_multi_element_partial_positive(self):
        """A partially-correlated pair yields a positive coefficient."""
        ev = _make_evaluator()
        val = ev._compute_ranking_metric("spearman", [1, 2, 3, 4], [1, 2, 4, 3], {})
        assert val > 0.0

    def test_kendall_multi_element_reversed(self):
        ev = _make_evaluator()
        val = ev._compute_ranking_metric("kendall", [1, 2, 3], [3, 2, 1], {})
        assert val == 0.0

    def test_kendall_multi_element_partial_positive(self):
        ev = _make_evaluator()
        val = ev._compute_ranking_metric("kendall", [1, 2, 3, 4], [1, 2, 4, 3], {})
        assert val > 0.0

    def test_ndcg_non_empty_perfect_order(self):
        """Non-empty relevance lists route through sklearn ndcg_score
        (lines 1246-1248)."""
        ev = _make_evaluator()
        val = ev._compute_ranking_metric("ndcg", [3, 2, 1], [3, 2, 1], {})
        assert val == pytest.approx(1.0)


# ============================================================================
# _compute_structured_metric — schema error arm
# ============================================================================


class TestComputeStructuredSchemaError:
    def test_invalid_schema_raises_runtime_error(self):
        """A malformed JSON schema (type is an int) makes jsonschema raise
        SchemaError -> wrapped RuntimeError (lines 1660-1661)."""
        ev = _make_evaluator()
        with pytest.raises(RuntimeError, match="Invalid JSON schema"):
            ev._compute_structured_metric(
                "schema_validation",
                "{}",
                '{"a": 1}',
                {"schema": {"type": 123}},
            )


# ============================================================================
# _compute_span_metric — unknown metric returns 0.0
# ============================================================================


class TestComputeSpanMetricUnknown:
    def test_unknown_span_metric_returns_zero(self):
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 5}]
        val = ev._compute_span_metric("not_a_span_metric", gt, gt)
        assert val == 0.0


# ============================================================================
# _validate_text_for_coherence — single-sentence ValueError
# ============================================================================


class TestValidateTextForCoherence:
    def test_single_long_sentence_raises(self):
        """A 20+ char string that tokenizes to a single sentence trips the
        '< 2 sentences' guard (line 2544)."""
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="at least 2 sentences"):
            ev._validate_text_for_coherence("this is one single clause without end")


# ============================================================================
# _compute_metric_with_details — legacy fall-through wrapper
# ============================================================================


class TestComputeMetricWithDetailsLegacyFallThrough:
    def test_unregistered_metric_uses_legacy_wrapper(self):
        """With the registry forced to miss, a plain metric falls through to
        the legacy chain and is wrapped in the standard dict with
        details.legacy_path == True (lines 624-635)."""
        ev = _make_evaluator()
        with patch("ml_evaluation.metric_registry.get", return_value=None):
            result = ev._compute_metric_with_details(
                "exact_match", "hello", "hello", "text", {"unused": 1}
            )
        assert result["value"] == 1.0
        assert result["method"] == "exact_match"
        assert result["details"]["legacy_path"] is True
        assert result["details"]["parameters_applied"] == {"unused": 1}
        assert result["error"] is None
