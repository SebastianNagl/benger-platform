"""
Branch-coverage tests for ml_evaluation/sample_evaluator.py.

Targets the uncovered branches the deep-coverage suite doesn't reach:

  * the Phase-2 provenance helpers (``_coherence_with_details``,
    ``_moverscore_with_details``, ``_qags_with_details``,
    ``_bertscore_with_details``, ``_semantic_similarity_with_details``) —
    including their empty-input guards and audit-trail dict shapes,
  * ``_compute_metric_with_details`` dispatch (registry hit, korrektur no-op,
    legacy fall-through wrapper),
  * ``_optimal_span_matching`` Hungarian assignment with label compatibility,
  * the semantic / factuality dispatch error and validation branches,
  * ``_compute_metric`` registry-first dispatch + korrektur no-op.

All neural backends are mocked through ``_get_backend_selector`` / the
sentence-transformer loader so NO model is downloaded. Pure-math helpers are
driven with crafted inputs and asserted to known values within epsilon.
Mirrors the idioms in test_ml_evaluation_deep_coverage.py.
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
# _compute_metric_with_details dispatch
# ============================================================================


class TestComputeMetricWithDetails:
    def test_registry_handler_returns_standard_shape(self):
        """exact_match is registered via _LegacyMetricHandler; the details
        path should return the standard {value, method, details, error} dict."""
        ev = _make_evaluator()
        result = ev._compute_metric_with_details(
            "exact_match", "hello", "hello", "text", {}
        )
        assert result["value"] == 1.0
        assert result["method"] == "exact_match"
        assert isinstance(result["details"], dict)
        assert result["error"] is None

    def test_registry_handler_mismatch_zero(self):
        ev = _make_evaluator()
        result = ev._compute_metric_with_details(
            "exact_match", "hello", "world", "text", {}
        )
        assert result["value"] == 0.0

    def test_korrektur_metric_is_human_graded_noop(self):
        """korrektur_* metrics are human-graded: worker returns a skipped
        no-op dict, never computes anything."""
        ev = _make_evaluator()
        result = ev._compute_metric_with_details(
            "korrektur_falloesung", "gt", "pred", "text", {}
        )
        assert result["value"] == 0.0
        assert result["details"]["human_graded"] is True
        assert result["details"]["skipped"] is True
        assert "API" in result["details"]["reason"]

    def test_none_parameters_default_to_empty(self):
        ev = _make_evaluator()
        result = ev._compute_metric_with_details(
            "accuracy", "x", "x", "text", None
        )
        assert result["value"] == 1.0


# ============================================================================
# _compute_metric registry-first dispatch + korrektur no-op
# ============================================================================


class TestComputeMetricDispatch:
    def test_registry_first_returns_float(self):
        ev = _make_evaluator()
        assert ev._compute_metric("exact_match", "a", "a", "text") == 1.0
        assert ev._compute_metric("exact_match", "a", "b", "text") == 0.0

    def test_korrektur_metric_returns_zero_noop(self):
        """korrektur_* dispatched through the legacy chain is a NaN-safe 0."""
        ev = _make_evaluator()
        # Direct legacy path (registry has no korrektur_ handler on platform side)
        assert ev._compute_metric_legacy(
            "korrektur_classic", "gt", "pred", "text", {}
        ) == 0.0

    def test_unknown_metric_raises_value_error(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="Unknown metric"):
            ev._compute_metric_legacy("nonexistent_xyz", "a", "a", "text", {})


# ============================================================================
# _coherence_with_details — audit trail of method weights
# ============================================================================


class TestCoherenceWithDetails:
    def test_semantic_only_weights_and_provenance(self):
        """method='semantic' skips the entity grid entirely; the result records
        weights_input (entity=0) and a normalized effective weight of 1.0 for
        semantic."""
        ev = _make_evaluator()
        text = "Der Vertrag ist gueltig. Die Parteien haben zugestimmt."
        with patch.object(
            ev, "_compute_semantic_coherence", return_value=0.8
        ):
            result = ev._coherence_with_details(text, {"method": "semantic"})
        assert abs(result["value"] - 0.8) < 1e-9
        assert result["method"] == "coherence"
        assert result["details"]["methods_used"] == ["semantic"]
        assert result["details"]["weights_input"]["entity"] == 0.0
        assert abs(result["details"]["weights_effective"]["semantic"] - 1.0) < 1e-9
        assert result["error"] is None

    def test_hybrid_entity_failure_falls_back_to_semantic(self):
        """In hybrid mode, an entity-grid failure must NOT abort the metric:
        it falls back to semantic-only and records the fallback_reason."""
        ev = _make_evaluator()
        text = "The contract is valid here. All parties agreed clearly to it."
        with patch.object(
            ev,
            "_compute_entity_coherence",
            side_effect=RuntimeError("no entities found"),
        ), patch.object(ev, "_compute_semantic_coherence", return_value=0.6):
            result = ev._coherence_with_details(text, {"method": "hybrid"})
        assert abs(result["value"] - 0.6) < 1e-9
        assert "semantic" in result["details"]["methods_used"]
        assert "entity" not in result["details"]["methods_used"]
        assert result["details"]["fallback_reason"] is not None

    def test_entity_only_failure_raises(self):
        """Pure 'entity' mode propagates the failure as RuntimeError."""
        ev = _make_evaluator()
        text = "The contract is valid here. All parties agreed clearly to it."
        with patch.object(
            ev,
            "_compute_entity_coherence",
            side_effect=RuntimeError("no entities found"),
        ):
            with pytest.raises(RuntimeError, match="entity-only mode"):
                ev._coherence_with_details(text, {"method": "entity"})

    def test_hybrid_weighted_average(self):
        """Both sub-scores present: weighted by entity_weight/semantic_weight,
        then normalized. entity=1.0 w=0.6, semantic=0.0 w=0.4 -> 0.6."""
        ev = _make_evaluator()
        text = "The lawyer argued the case here. The judge then reviewed all evidence."
        with patch.object(
            ev, "_compute_entity_coherence", return_value=1.0
        ), patch.object(ev, "_compute_semantic_coherence", return_value=0.0):
            result = ev._coherence_with_details(
                text, {"method": "hybrid", "entity_weight": 0.6, "semantic_weight": 0.4}
            )
        assert abs(result["value"] - 0.6) < 1e-9
        assert set(result["details"]["methods_used"]) == {"entity", "semantic"}

    def test_invalid_method_raises(self):
        ev = _make_evaluator()
        text = "The contract is valid here. All parties agreed clearly to it."
        with pytest.raises(ValueError, match="Invalid coherence method"):
            ev._coherence_with_details(text, {"method": "bogus"})

    def test_empty_text_validation_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="non-empty"):
            ev._coherence_with_details("", {"method": "semantic"})


# ============================================================================
# _moverscore_with_details — empty guards + backend provenance
# ============================================================================


class TestMoverScoreWithDetails:
    def test_empty_ground_truth_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="non-empty ground truth"):
            ev._moverscore_with_details("   ", "prediction text", {})

    def test_empty_prediction_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="non-empty prediction"):
            ev._moverscore_with_details("ground truth text", "  ", {})

    def test_too_short_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="longer than 3 characters"):
            ev._moverscore_with_details("ab", "cd", {})

    def test_backend_returns_score_provenance(self):
        ev = _make_evaluator()
        mock_selector = MagicMock()
        mock_computer = MagicMock()
        mock_computer.compute_moverscore.return_value = [0.73]
        mock_selector.get_moverscore_computer.return_value = mock_computer
        with patch(f"{SE_MOD}._get_backend_selector", return_value=mock_selector):
            result = ev._moverscore_with_details(
                "ground truth text", "prediction text", {"n_gram": 2}
            )
        assert abs(result["value"] - 0.73) < 1e-9
        assert result["method"] == "moverscore"
        assert result["details"]["backend_returned_scores"] is True
        assert result["details"]["n_gram"] == 2
        assert result["error"] is None

    def test_backend_empty_scores_surfaces_error(self):
        ev = _make_evaluator()
        mock_selector = MagicMock()
        mock_computer = MagicMock()
        mock_computer.compute_moverscore.return_value = []
        mock_selector.get_moverscore_computer.return_value = mock_computer
        with patch(f"{SE_MOD}._get_backend_selector", return_value=mock_selector):
            result = ev._moverscore_with_details(
                "ground truth text", "prediction text", {}
            )
        assert result["value"] == 0.0
        assert result["details"]["backend_returned_scores"] is False
        assert "no scores" in result["error"]


# ============================================================================
# _qags_with_details — per-question failure tracking
# ============================================================================


class TestQAGSWithDetails:
    def _selector_with_backend(self, qags_backend):
        sel = MagicMock()
        sel.get_qags_backend.return_value = qags_backend
        return sel

    def test_all_questions_match(self):
        ev = _make_evaluator()
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?", "Q2?"]
        qb.answer_question.return_value = {"answer": "Berlin"}
        sel = self._selector_with_backend(qb)
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            result = ev._qags_with_details("doc text", "pred text", {})
        assert result["value"] == 1.0
        assert result["details"]["questions_succeeded"] == 2
        assert result["details"]["matched_answers"] == 2
        assert result["error"] is None

    def test_partial_match_excludes_failed_from_denominator(self):
        """A question whose answering raises is excluded from the denominator,
        not counted as a non-match (honest measurement)."""
        ev = _make_evaluator()
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?", "Q2?", "Q3?"]

        # Q1 matches, Q2 mismatches, Q3 raises (excluded).
        def answer(question, text):
            if question == "Q3?":
                raise RuntimeError("QA model failed")
            if question == "Q1?":
                return {"answer": "match"}
            # Q2: gt vs pred differ
            return {"answer": "gt" if text == "doc text" else "pred"}

        qb.answer_question.side_effect = answer
        sel = self._selector_with_backend(qb)
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            result = ev._qags_with_details("doc text", "pred text", {})
        # 2 succeeded (Q1,Q2), 1 matched -> 0.5; Q3 in failed list
        assert abs(result["value"] - 0.5) < 1e-9
        assert result["details"]["questions_succeeded"] == 2
        assert result["details"]["questions_failed"] == 1
        assert result["details"]["matched_answers"] == 1

    def test_all_questions_fail_returns_zero_with_error(self):
        ev = _make_evaluator()
        qb = MagicMock()
        qb.generate_questions.return_value = ["Q1?"]
        qb.answer_question.side_effect = RuntimeError("boom")
        sel = self._selector_with_backend(qb)
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            result = ev._qags_with_details("doc text", "pred text", {})
        assert result["value"] == 0.0
        assert result["details"]["questions_succeeded"] == 0
        assert "All QAGS questions failed" in result["error"]

    def test_no_questions_generated_returns_zero(self):
        ev = _make_evaluator()
        qb = MagicMock()
        qb.generate_questions.return_value = []
        sel = self._selector_with_backend(qb)
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            result = ev._qags_with_details("doc text", "pred text", {})
        assert result["value"] == 0.0
        assert "no questions" in result["error"]


# ============================================================================
# _bertscore_with_details / _semantic_similarity_with_details — backend branch
# ============================================================================


class TestSemanticProvenanceHelpers:
    def test_bertscore_pytorch_branch(self):
        """On non-ARM64 the helper uses bert_score_compute and tags backend
        'pytorch'. We mock the library so no model loads."""
        ev = _make_evaluator()
        mock_f1 = MagicMock()
        mock_f1.mean.return_value.item.return_value = 0.91
        with patch(f"{SE_MOD}.IS_ARM64", False), patch(
            f"{SE_MOD}.bert_score_compute",
            return_value=(MagicMock(), MagicMock(), mock_f1),
        ):
            result = ev._bertscore_with_details("ref text", "cand text", {"lang": "en"})
        assert abs(result["value"] - 0.91) < 1e-9
        assert result["details"]["backend"] == "pytorch"
        assert result["details"]["lang"] == "en"
        assert result["details"]["rescale_with_baseline"] is True

    def test_bertscore_onnx_branch(self):
        """On ARM64 the helper routes through the ONNX backend selector."""
        ev = _make_evaluator()
        backend = MagicMock()
        backend.compute.return_value = (0.5, 0.6, 0.77)
        sel = MagicMock()
        sel.get_bertscore_backend.return_value = backend
        with patch(f"{SE_MOD}.IS_ARM64", True), patch(
            f"{SE_MOD}._get_backend_selector", return_value=sel
        ):
            result = ev._bertscore_with_details("ref text", "cand text", {})
        assert abs(result["value"] - 0.77) < 1e-9
        assert result["details"]["backend"] == "onnx"
        assert result["details"]["rescale_with_baseline"] is False

    def test_semantic_similarity_onnx_cosine(self):
        """ARM64 path computes cosine of two encoded vectors. Identical vectors
        -> similarity 1.0."""
        ev = _make_evaluator()
        backend = MagicMock()
        vec = np.array([1.0, 0.0, 0.0])
        backend.encode.side_effect = [[vec], [vec]]
        sel = MagicMock()
        sel.get_embedding_backend.return_value = backend
        with patch(f"{SE_MOD}.IS_ARM64", True), patch(
            f"{SE_MOD}._get_backend_selector", return_value=sel
        ):
            result = ev._semantic_similarity_with_details("ref", "cand", {})
        assert abs(result["value"] - 1.0) < 1e-6
        assert result["details"]["backend"] == "onnx"
        assert result["details"]["model"] == "MiniLM-onnx"

    def test_semantic_similarity_pytorch_branch(self):
        """Non-ARM64 path uses the sentence-transformer + cos_sim utility."""
        ev = _make_evaluator()
        model = MagicMock()
        model.encode.side_effect = ["emb_gt", "emb_pred"]
        cos = MagicMock()
        cos.item.return_value = 0.42
        with patch(f"{SE_MOD}.IS_ARM64", False), patch(
            f"{SE_MOD}._get_sentence_transformer", return_value=model
        ), patch(f"{SE_MOD}.st_util.cos_sim", return_value=cos):
            result = ev._semantic_similarity_with_details("ref", "cand", {})
        assert abs(result["value"] - 0.42) < 1e-9
        assert result["details"]["backend"] == "pytorch"


# ============================================================================
# _compute_semantic_metric / _compute_factuality_metric dispatch errors
# ============================================================================


class TestSemanticFactualityDispatch:
    def test_moverscore_metric_empty_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="non-empty ground truth"):
            ev._compute_semantic_metric("moverscore", "", "pred", {})

    def test_unknown_semantic_metric_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="Unknown semantic metric"):
            ev._compute_semantic_metric("not_a_metric", "a", "b", {})

    def test_unknown_factcc_method_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="Unknown FactCC method"):
            ev._compute_factuality_metric("factcc", "gt", "pred", {"method": "bogus"})

    def test_factcc_summac_backend_failure_raises_runtime(self):
        ev = _make_evaluator()
        sel = MagicMock()
        backend = MagicMock()
        backend.score_consistency.side_effect = RuntimeError("model gone")
        sel.get_summac_backend.return_value = backend
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            with pytest.raises(RuntimeError, match="SummaC scoring failed"):
                ev._compute_factuality_metric("factcc", "doc", "claim", {"method": "summac"})

    def test_factcc_summac_success(self):
        ev = _make_evaluator()
        sel = MagicMock()
        backend = MagicMock()
        backend.score_consistency.return_value = 0.88
        sel.get_summac_backend.return_value = backend
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            score = ev._compute_factuality_metric(
                "factcc", "doc", "claim", {"method": "summac"}
            )
        assert abs(score - 0.88) < 1e-9

    def test_qags_metric_no_questions_returns_zero(self):
        ev = _make_evaluator()
        sel = MagicMock()
        qb = MagicMock()
        qb.generate_questions.return_value = []
        sel.get_qags_backend.return_value = qb
        with patch(f"{SE_MOD}._get_backend_selector", return_value=sel):
            score = ev._compute_factuality_metric("qags", "doc", "pred", {})
        assert score == 0.0

    def test_unknown_factuality_metric_raises(self):
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="Unknown factuality metric"):
            ev._compute_factuality_metric("not_real", "a", "b", {})


# ============================================================================
# _optimal_span_matching — Hungarian assignment + label compatibility
# ============================================================================


class TestOptimalSpanMatching:
    def test_perfect_one_to_one_iou(self):
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}, {"start": 20, "end": 30}]
        pred = [{"start": 20, "end": 30}, {"start": 0, "end": 10}]  # shuffled
        total = ev._optimal_span_matching(gt, pred, ev._span_iou)
        # Optimal assignment matches each pair exactly -> total IoU == 2.0
        assert abs(total - 2.0) < 1e-9

    def test_label_incompatible_pairs_score_zero(self):
        """Spans with disjoint labels are excluded from the score matrix, so a
        perfect-position-overlap but wrong-label pair scores 0."""
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10, "labels": ["PER"]}]
        pred = [{"start": 0, "end": 10, "labels": ["ORG"]}]
        total = ev._optimal_span_matching(gt, pred, ev._span_iou)
        assert total == 0.0

    def test_iou_metric_uses_optimal_matching(self):
        """End-to-end: _compute_span_metric('iou') divides total by max(len)."""
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 5, "end": 15}]
        # IoU(0-10, 5-15) = 5/15 = 1/3; max(len)=1 -> 1/3
        score = ev._compute_span_metric("iou", gt, pred)
        assert abs(score - 1 / 3) < 1e-9


# ============================================================================
# evaluate_sample — primary_value dict extraction + error envelope
# ============================================================================


class TestEvaluateSampleBranches:
    def test_annotation_id_skips_parse_status_check(self):
        """For annotation-based evaluation the parse_status gate is skipped."""
        ev = _make_evaluator()
        result = ev.evaluate_sample(
            task_id="t1",
            field_name="f",
            ground_truth="hello",
            prediction="hello",
            metrics_to_compute=["exact_match"],
            generation_id="gen-1",
            annotation_id="ann-1",
            parse_status="failed",  # would normally raise, but annotation_id present
        )
        assert result["metrics"]["exact_match"]["value"] == 1.0
        assert result["passed"] is True

    def test_failure_metric_marks_sample_not_passed(self):
        ev = _make_evaluator()
        result = ev.evaluate_sample(
            task_id="t1",
            field_name="f",
            ground_truth="hello",
            prediction="world",
            metrics_to_compute=["exact_match"],
        )
        assert result["metrics"]["exact_match"]["value"] == 0.0
        assert result["passed"] is False

    def test_answer_type_from_field_config(self):
        ev = _make_evaluator(field_configs={"f": {"type": "span_selection"}})
        result = ev.evaluate_sample(
            task_id="t1",
            field_name="f",
            ground_truth="hello",
            prediction="hello",
            metrics_to_compute=["exact_match"],
        )
        assert result["answer_type"] == "span_selection"
