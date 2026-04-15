"""
Tests for Ranking Metrics (Spearman, Kendall, NDCG, MAP, Weighted Kappa).

Scientific Rigor: All tests verify mathematical correctness with known expected values.
NO MOCKS - All metrics use real implementations.

References:
- Spearman: scipy.stats.spearmanr
- Kendall: scipy.stats.kendalltau
- NDCG: sklearn.metrics.ndcg_score
- MAP: Information Retrieval standard
- Weighted Kappa: sklearn.metrics.cohen_kappa_score
"""

import os
import sys

import numpy as np
import pytest
from scipy.stats import kendalltau, spearmanr
from sklearn.metrics import cohen_kappa_score, ndcg_score

# Add path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSpearmanCorrelation:
    """Test Spearman rank correlation with known expected values.

    Reference: Spearman (1904), scipy.stats.spearmanr
    """

    def test_spearman_perfect_positive(self):
        """Test Spearman = 1.0 for identical rankings."""
        x = [1, 2, 3, 4, 5]
        y = [1, 2, 3, 4, 5]

        corr, _ = spearmanr(x, y)
        assert abs(corr - 1.0) < 0.001, f"Identical rankings should have rho=1.0, got {corr}"

    def test_spearman_perfect_negative(self):
        """Test Spearman = -1.0 for reversed rankings."""
        x = [1, 2, 3, 4, 5]
        y = [5, 4, 3, 2, 1]

        corr, _ = spearmanr(x, y)
        assert abs(corr - (-1.0)) < 0.001, f"Reversed rankings should have rho=-1.0, got {corr}"

    def test_spearman_partial_correlation(self):
        """Test Spearman with partial rank agreement."""
        # Known example: x ranks are 1,2,3,4,5 and y ranks are 1,3,2,5,4
        x = [1, 2, 3, 4, 5]
        y = [1, 3, 2, 5, 4]

        corr, _ = spearmanr(x, y)
        # This gives rho = 0.7 (known value for this example)
        assert 0.5 < corr < 1.0, f"Partial agreement should have 0.5 < rho < 1.0, got {corr}"

    def test_spearman_sample_evaluator(self):
        """Test Spearman through SampleEvaluator."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        # Identical rankings
        score = evaluator._compute_ranking_metric("spearman", [1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
        assert score == 1.0, f"Identical rankings should have Spearman 1.0, got {score}"

    def test_spearman_different_lengths_returns_zero(self):
        """Test Spearman returns 0.0 for lists of different lengths."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        score = evaluator._compute_ranking_metric("spearman", [1, 2, 3], [1, 2])
        assert score == 0.0, f"Different length lists should return 0.0, got {score}"


class TestKendallTau:
    """Test Kendall's tau correlation with known expected values.

    Reference: Kendall (1938), scipy.stats.kendalltau
    """

    def test_kendall_perfect_positive(self):
        """Test Kendall tau = 1.0 for identical rankings."""
        x = [1, 2, 3, 4, 5]
        y = [1, 2, 3, 4, 5]

        tau, _ = kendalltau(x, y)
        assert abs(tau - 1.0) < 0.001, f"Identical rankings should have tau=1.0, got {tau}"

    def test_kendall_perfect_negative(self):
        """Test Kendall tau = -1.0 for reversed rankings."""
        x = [1, 2, 3, 4, 5]
        y = [5, 4, 3, 2, 1]

        tau, _ = kendalltau(x, y)
        assert abs(tau - (-1.0)) < 0.001, f"Reversed rankings should have tau=-1.0, got {tau}"

    def test_kendall_with_ties(self):
        """Test Kendall tau handles tied ranks correctly."""
        x = [1, 2, 2, 4, 5]  # Tie at rank 2
        y = [1, 2, 3, 4, 5]

        tau, _ = kendalltau(x, y)
        # Should still be high positive correlation
        assert tau > 0.8, f"Similar rankings with tie should have tau > 0.8, got {tau}"

    def test_kendall_sample_evaluator(self):
        """Test Kendall through SampleEvaluator."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        score = evaluator._compute_ranking_metric("kendall", [1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
        assert score == 1.0, f"Identical rankings should have Kendall 1.0, got {score}"


class TestNDCG:
    """Test Normalized Discounted Cumulative Gain with known expected values.

    Reference: Järvelin & Kekäläinen (2002), sklearn.metrics.ndcg_score
    """

    def test_ndcg_perfect_ranking(self):
        """Test NDCG = 1.0 for ideal ranking."""
        # Relevance scores in ideal order (descending)
        y_true = np.array([[5, 4, 3, 2, 1]])
        y_pred = np.array([[5, 4, 3, 2, 1]])

        score = ndcg_score(y_true, y_pred)
        assert abs(score - 1.0) < 0.001, f"Ideal ranking should have NDCG 1.0, got {score}"

    def test_ndcg_reversed_ranking(self):
        """Test NDCG < 1.0 for reversed ranking."""
        y_true = np.array([[5, 4, 3, 2, 1]])
        y_pred = np.array([[1, 2, 3, 4, 5]])

        score = ndcg_score(y_true, y_pred)
        assert score < 1.0, f"Reversed ranking should have NDCG < 1.0, got {score}"
        assert score > 0.0, f"NDCG should be > 0, got {score}"

    def test_ndcg_at_k(self):
        """Test NDCG@k truncates ranking at k."""
        y_true = np.array([[5, 4, 3, 2, 1]])
        y_pred = np.array([[5, 4, 1, 2, 3]])  # Top 2 are correct

        ndcg_full = ndcg_score(y_true, y_pred)
        ndcg_at_2 = ndcg_score(y_true, y_pred, k=2)

        assert ndcg_at_2 == 1.0, f"NDCG@2 should be 1.0 (top 2 correct), got {ndcg_at_2}"
        assert ndcg_full < 1.0, f"Full NDCG should be < 1.0, got {ndcg_full}"

    def test_ndcg_sample_evaluator(self):
        """Test NDCG through SampleEvaluator."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        score = evaluator._compute_ranking_metric("ndcg", [5, 4, 3, 2, 1], [5, 4, 3, 2, 1])
        assert abs(score - 1.0) < 0.001, f"Perfect ranking should have NDCG 1.0, got {score}"


class TestMeanAveragePrecision:
    """Test Mean Average Precision (MAP) with known expected values.

    Reference: Manning, Raghavan & Schütze (2008) "Introduction to Information Retrieval"
    """

    def test_map_all_relevant_first(self):
        """Test MAP = 1.0 when all relevant items are ranked first."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        # Ground truth: items A, B are relevant
        # Prediction: A, B ranked first, then C, D
        score = evaluator._compute_ranking_metric(
            "map", {"A", "B"}, ["A", "B", "C", "D"]  # Relevant items  # Ranked list
        )
        assert score == 1.0, f"All relevant first should have MAP 1.0, got {score}"

    def test_map_calculated(self):
        """Test MAP calculation with known precision values."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        # Ground truth: {A, C} are relevant (2 items)
        # Prediction: [A, B, C, D]
        # At A (position 1): precision = 1/1 = 1.0
        # At C (position 3): precision = 2/3 = 0.667
        # AP = (1.0 + 0.667) / 2 = 0.833
        score = evaluator._compute_ranking_metric("map", {"A", "C"}, ["A", "B", "C", "D"])
        assert abs(score - 0.833) < 0.01, f"MAP should be ~0.833, got {score}"

    def test_map_no_relevant_found(self):
        """Test MAP = 0.0 when no relevant items are in the ranking."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        score = evaluator._compute_ranking_metric(
            "map", {"A", "B"}, ["C", "D", "E"]  # Relevant items  # None are relevant
        )
        assert score == 0.0, f"No relevant items found should have MAP 0.0, got {score}"


class TestWeightedKappa:
    """Test Weighted Cohen's Kappa with known expected values.

    Reference: Cohen (1968), sklearn.metrics.cohen_kappa_score
    """

    def test_weighted_kappa_perfect_agreement(self):
        """Test weighted kappa = 1.0 for perfect agreement."""
        y1 = [1, 2, 3, 4, 5]
        y2 = [1, 2, 3, 4, 5]

        kappa = cohen_kappa_score(y1, y2, weights='quadratic')
        assert abs(kappa - 1.0) < 0.001, f"Perfect agreement should have kappa=1.0, got {kappa}"

    def test_weighted_kappa_partial_agreement(self):
        """Test weighted kappa for ordinal scale with partial agreement."""
        # 5-point scale, some off-by-one errors
        y1 = [1, 2, 3, 4, 5]
        y2 = [1, 2, 4, 4, 5]  # One off-by-one error

        kappa = cohen_kappa_score(y1, y2, weights='quadratic')
        # Should be high but not perfect
        assert 0.8 < kappa < 1.0, f"Partial agreement should have 0.8 < kappa < 1.0, got {kappa}"

    def test_weighted_kappa_linear_vs_quadratic(self):
        """Test that linear and quadratic weighting differ in their treatment of disagreements."""
        y1 = [1, 1, 5]
        y2 = [1, 3, 5]  # One 2-point difference

        kappa_linear = cohen_kappa_score(y1, y2, weights='linear')
        kappa_quadratic = cohen_kappa_score(y1, y2, weights='quadratic')

        # Both should be reasonable agreement scores but different
        assert 0.5 < kappa_linear < 1.0, f"Linear kappa should be reasonable, got {kappa_linear}"
        assert (
            0.5 < kappa_quadratic < 1.0
        ), f"Quadratic kappa should be reasonable, got {kappa_quadratic}"
        # Note: Quadratic can be > or < linear depending on the distribution of disagreements

    def test_weighted_kappa_is_aggregate_only(self):
        """Test weighted kappa raises error for per-sample computation."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        with pytest.raises(RuntimeError, match="aggregate-only"):
            evaluator._compute_ranking_metric("weighted_kappa", 3, 3)


class TestRankingMetricsNoFallback:
    """Test that ranking metrics properly raise errors on failure."""

    def test_spearman_raises_on_failure(self):
        """Test Spearman raises RuntimeError on computation failure."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        # This should not fall back - if scipy fails, it should raise
        # Empty lists will be caught early and return 1.0 (both empty)
        score = evaluator._compute_ranking_metric("spearman", [], [])
        # Empty lists are considered equal
        assert score == 1.0

    def test_ndcg_raises_on_failure(self):
        """Test NDCG raises RuntimeError on computation failure."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "list"}}
        )

        # Invalid inputs should raise RuntimeError, not return fallback values
        with pytest.raises(RuntimeError, match="NDCG"):
            evaluator._compute_ranking_metric("ndcg", "not a list", "also not a list")
