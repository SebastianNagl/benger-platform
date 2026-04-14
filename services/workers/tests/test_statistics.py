"""Tests for ml_evaluation/statistics.py - statistical analysis utilities.

Covers:
- bootstrap_confidence_interval
- paired_bootstrap_test
- cohens_d
- cliffs_delta
- correlation_matrix
- aggregate_with_statistics
- compute_consensus_score
- compute_inter_judge_agreement
- _krippendorff_alpha_interval
- compare_systems
"""

import os
import sys

import numpy as np
import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.statistics import (
    _krippendorff_alpha_interval,
    aggregate_with_statistics,
    bootstrap_confidence_interval,
    cliffs_delta,
    cohens_d,
    compare_systems,
    compute_consensus_score,
    compute_inter_judge_agreement,
    correlation_matrix,
    paired_bootstrap_test,
)


# ---------------------------------------------------------------------------
# bootstrap_confidence_interval
# ---------------------------------------------------------------------------

class TestBootstrapConfidenceInterval:

    def test_basic_mean(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = bootstrap_confidence_interval(data, statistic="mean")
        assert abs(result["point_estimate"] - 3.0) < 1e-6
        assert result["ci_lower"] <= result["point_estimate"]
        assert result["ci_upper"] >= result["point_estimate"]
        assert result["confidence_level"] == 0.95
        assert result["n_samples"] == 5

    def test_median(self):
        data = [1.0, 2.0, 3.0, 4.0, 100.0]
        result = bootstrap_confidence_interval(data, statistic="median")
        assert abs(result["point_estimate"] - 3.0) < 1e-6

    def test_std(self):
        data = [1.0, 1.0, 1.0, 1.0]
        result = bootstrap_confidence_interval(data, statistic="std")
        assert abs(result["point_estimate"]) < 1e-6

    def test_single_element(self):
        result = bootstrap_confidence_interval([5.0])
        assert result["point_estimate"] == 5.0
        assert result["ci_lower"] == 5.0
        assert result["ci_upper"] == 5.0
        assert result["std_error"] == 0.0

    def test_empty_list(self):
        result = bootstrap_confidence_interval([])
        assert result["point_estimate"] == 0.0

    def test_custom_confidence_level(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = bootstrap_confidence_interval(data, confidence_level=0.99)
        assert result["confidence_level"] == 0.99

    def test_reproducibility_with_seed(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        r1 = bootstrap_confidence_interval(data, random_state=42)
        r2 = bootstrap_confidence_interval(data, random_state=42)
        assert r1["ci_lower"] == r2["ci_lower"]
        assert r1["ci_upper"] == r2["ci_upper"]


# ---------------------------------------------------------------------------
# paired_bootstrap_test
# ---------------------------------------------------------------------------

class TestPairedBootstrapTest:

    def test_identical_scores(self):
        scores = [0.8, 0.9, 0.7, 0.85, 0.75]
        result = paired_bootstrap_test(scores, scores)
        assert abs(result["mean_difference"]) < 1e-6
        assert result["p_value"] >= 0.0

    def test_clearly_different_scores(self):
        a = [0.9, 0.95, 0.92, 0.88, 0.91]
        b = [0.3, 0.35, 0.32, 0.28, 0.31]
        result = paired_bootstrap_test(a, b)
        assert result["mean_difference"] > 0
        assert result["a_better"] == True

    def test_unequal_length_error(self):
        result = paired_bootstrap_test([1.0, 2.0], [1.0])
        assert "error" in result

    def test_too_few_samples_error(self):
        result = paired_bootstrap_test([1.0], [2.0])
        assert "error" in result

    def test_result_keys(self):
        a = [0.8, 0.9, 0.7]
        b = [0.7, 0.8, 0.6]
        result = paired_bootstrap_test(a, b)
        assert "mean_difference" in result
        assert "p_value" in result
        assert "ci_lower" in result
        assert "ci_upper" in result
        assert "significant_at_05" in result
        assert "significant_at_01" in result
        assert "n_samples" in result


# ---------------------------------------------------------------------------
# cohens_d
# ---------------------------------------------------------------------------

class TestCohensD:

    def test_identical_distributions(self):
        scores = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = cohens_d(scores, scores)
        assert abs(result["cohens_d"]) < 1e-6
        assert result["interpretation"] == "negligible"

    def test_large_effect(self):
        a = [5.0, 6.0, 7.0, 8.0, 9.0]
        b = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = cohens_d(a, b)
        assert abs(result["cohens_d"]) > 0.8
        assert result["interpretation"] == "large"
        assert result["a_better"] == True

    def test_small_effect(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [0.8, 1.8, 2.8, 3.8, 4.8]
        result = cohens_d(a, b)
        assert result["interpretation"] == "small" or result["interpretation"] == "negligible"

    def test_zero_variance(self):
        a = [5.0, 5.0, 5.0]
        b = [5.0, 5.0, 5.0]
        result = cohens_d(a, b)
        assert result["cohens_d"] == 0.0

    def test_medium_effect(self):
        a = [3.0, 4.0, 5.0, 6.0, 7.0]
        b = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = cohens_d(a, b)
        # d ~= 1.26 which is "large"
        assert result["interpretation"] in ("medium", "large")


# ---------------------------------------------------------------------------
# cliffs_delta
# ---------------------------------------------------------------------------

class TestCliffsDelta:

    def test_identical_distributions(self):
        scores = [1.0, 2.0, 3.0]
        result = cliffs_delta(scores, scores)
        assert abs(result["cliffs_delta"]) < 1e-6
        assert result["interpretation"] == "negligible"

    def test_complete_dominance(self):
        a = [10.0, 11.0, 12.0]
        b = [1.0, 2.0, 3.0]
        result = cliffs_delta(a, b)
        assert result["cliffs_delta"] == 1.0
        assert result["interpretation"] == "large"
        assert result["a_better"] is True

    def test_b_dominates(self):
        a = [1.0, 2.0, 3.0]
        b = [10.0, 11.0, 12.0]
        result = cliffs_delta(a, b)
        assert result["cliffs_delta"] == -1.0
        assert result["a_better"] is False

    def test_empty_scores(self):
        result = cliffs_delta([], [1.0, 2.0])
        assert result["cliffs_delta"] == 0.0

    def test_total_pairs(self):
        a = [1.0, 2.0]
        b = [3.0, 4.0, 5.0]
        result = cliffs_delta(a, b)
        assert result["total_pairs"] == 6


# ---------------------------------------------------------------------------
# correlation_matrix
# ---------------------------------------------------------------------------

class TestCorrelationMatrix:

    def test_perfect_correlation(self):
        data = {
            "metric_a": [1.0, 2.0, 3.0, 4.0, 5.0],
            "metric_b": [2.0, 4.0, 6.0, 8.0, 10.0],
        }
        result = correlation_matrix(data)
        assert result["metric_a"]["metric_a"] == 1.0
        assert result["metric_b"]["metric_b"] == 1.0
        assert abs(result["metric_a"]["metric_b"] - 1.0) < 1e-6

    def test_single_metric(self):
        result = correlation_matrix({"a": [1.0, 2.0, 3.0]})
        assert result == {}

    def test_negative_correlation(self):
        data = {
            "a": [1.0, 2.0, 3.0, 4.0, 5.0],
            "b": [5.0, 4.0, 3.0, 2.0, 1.0],
        }
        result = correlation_matrix(data)
        assert result["a"]["b"] is not None
        assert result["a"]["b"] < -0.9

    def test_too_few_samples_returns_none(self):
        data = {
            "a": [1.0, 2.0],
            "b": [3.0, 4.0],
        }
        result = correlation_matrix(data)
        assert result["a"]["b"] is None


# ---------------------------------------------------------------------------
# aggregate_with_statistics
# ---------------------------------------------------------------------------

class TestAggregateWithStatistics:

    def test_basic_aggregation(self):
        scores = [0.8, 0.9, 0.85, 0.87, 0.92]
        result = aggregate_with_statistics(scores, "accuracy")
        assert result["metric"] == "accuracy"
        assert abs(result["mean"] - np.mean(scores)) < 1e-6
        assert abs(result["median"] - np.median(scores)) < 1e-6
        assert result["n_samples"] == 5
        assert result["ci_lower"] <= result["mean"]
        assert result["ci_upper"] >= result["mean"]

    def test_empty_scores(self):
        result = aggregate_with_statistics([], "f1")
        assert result["mean"] is None
        assert result["n_samples"] == 0

    def test_single_score(self):
        result = aggregate_with_statistics([0.9], "accuracy")
        assert result["mean"] == 0.9
        assert result["n_samples"] == 1


# ---------------------------------------------------------------------------
# compute_consensus_score
# ---------------------------------------------------------------------------

class TestComputeConsensusScore:

    def test_mean_method(self):
        scores = {"judge_a": 4.0, "judge_b": 5.0, "judge_c": 3.0}
        result = compute_consensus_score(scores, method="mean")
        assert abs(result["consensus_score"] - 4.0) < 1e-6
        assert result["n_judges"] == 3

    def test_median_method(self):
        scores = {"a": 1.0, "b": 5.0, "c": 3.0}
        result = compute_consensus_score(scores, method="median")
        assert result["consensus_score"] == 3.0

    def test_trimmed_mean(self):
        scores = {"a": 1.0, "b": 3.0, "c": 5.0}
        result = compute_consensus_score(scores, method="trimmed_mean")
        assert result["consensus_score"] == 3.0  # Trims 1.0 and 5.0

    def test_single_judge(self):
        result = compute_consensus_score({"judge_a": 4.0})
        assert result["consensus_score"] == 4.0
        assert result["variance"] == 0.0

    def test_no_judges(self):
        result = compute_consensus_score({})
        assert result["consensus_score"] is None

    def test_result_keys(self):
        scores = {"a": 4.0, "b": 5.0}
        result = compute_consensus_score(scores)
        assert "variance" in result
        assert "std" in result
        assert "min_score" in result
        assert "max_score" in result
        assert "range" in result


# ---------------------------------------------------------------------------
# compute_inter_judge_agreement
# ---------------------------------------------------------------------------

class TestComputeInterJudgeAgreement:

    def test_perfect_agreement(self):
        scores = {"judge_a": [1.0, 2.0, 3.0, 4.0, 5.0],
                  "judge_b": [1.0, 2.0, 3.0, 4.0, 5.0]}
        result = compute_inter_judge_agreement(scores)
        assert result["krippendorff_alpha"] is not None
        assert result["krippendorff_alpha"] > 0.99
        assert result["interpretation"] == "high agreement"

    def test_no_agreement(self):
        scores = {"judge_a": [1.0, 5.0, 1.0, 5.0],
                  "judge_b": [5.0, 1.0, 5.0, 1.0]}
        result = compute_inter_judge_agreement(scores)
        assert result["krippendorff_alpha"] is not None
        assert result["krippendorff_alpha"] < 0

    def test_too_few_judges(self):
        result = compute_inter_judge_agreement({"judge_a": [1.0, 2.0]})
        assert "error" in result

    def test_too_few_samples(self):
        scores = {"a": [1.0], "b": [1.0]}
        result = compute_inter_judge_agreement(scores)
        assert "error" in result

    def test_unequal_sample_counts(self):
        scores = {"a": [1.0, 2.0], "b": [1.0]}
        result = compute_inter_judge_agreement(scores)
        assert "error" in result

    def test_three_judges(self):
        scores = {"a": [1.0, 2.0, 3.0, 4.0],
                  "b": [1.1, 2.1, 3.1, 4.1],
                  "c": [0.9, 1.9, 2.9, 3.9]}
        result = compute_inter_judge_agreement(scores)
        assert result["n_judges"] == 3
        assert result["n_samples"] == 4
        assert result["mean_pairwise_correlation"] is not None
        assert result["mean_pairwise_correlation"] > 0.9


# ---------------------------------------------------------------------------
# _krippendorff_alpha_interval
# ---------------------------------------------------------------------------

class TestKrippendorffAlphaInterval:

    def test_perfect_agreement(self):
        ratings = np.array([[1.0, 2.0, 3.0],
                           [1.0, 2.0, 3.0]])
        alpha = _krippendorff_alpha_interval(ratings)
        assert alpha > 0.99

    def test_no_agreement(self):
        ratings = np.array([[1.0, 5.0, 1.0, 5.0],
                           [5.0, 1.0, 5.0, 1.0]])
        alpha = _krippendorff_alpha_interval(ratings)
        assert alpha < 0

    def test_all_same_ratings(self):
        ratings = np.array([[3.0, 3.0, 3.0],
                           [3.0, 3.0, 3.0]])
        alpha = _krippendorff_alpha_interval(ratings)
        assert alpha == 1.0


# ---------------------------------------------------------------------------
# compare_systems
# ---------------------------------------------------------------------------

class TestCompareSystems:

    def test_basic_comparison(self):
        a_scores = {"accuracy": [0.9, 0.85, 0.88, 0.92, 0.87]}
        b_scores = {"accuracy": [0.7, 0.72, 0.68, 0.75, 0.71]}
        result = compare_systems(a_scores, b_scores, "GPT-4", "Llama")
        assert result["system_a"] == "GPT-4"
        assert result["system_b"] == "Llama"
        assert "accuracy" in result["metrics"]
        assert result["metrics"]["accuracy"]["mean_a"] > result["metrics"]["accuracy"]["mean_b"]

    def test_no_common_metrics(self):
        a = {"accuracy": [0.9]}
        b = {"f1": [0.8]}
        result = compare_systems(a, b)
        assert result["metrics"] == {}

    def test_summary_counts(self):
        a = {"m1": [0.9, 0.85, 0.88], "m2": [0.9, 0.85, 0.88]}
        b = {"m1": [0.3, 0.35, 0.32], "m2": [0.3, 0.35, 0.32]}
        result = compare_systems(a, b)
        total = result["summary"]["a_wins"] + result["summary"]["b_wins"] + result["summary"]["ties"]
        assert total == 2
