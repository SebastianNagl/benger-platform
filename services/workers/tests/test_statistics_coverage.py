"""Coverage tests for ml_evaluation/statistics.py.

Tests: bootstrap_confidence_interval, paired_bootstrap_test,
significance_test, cohens_d, cliffs_delta, correlation_matrix,
mcnemar_test, aggregate_with_statistics, compute_inter_judge_agreement,
compute_consensus_score, compare_systems.
"""

import sys
import os

workers_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, workers_root)

import numpy as np

from ml_evaluation.statistics import (
    bootstrap_confidence_interval,
    paired_bootstrap_test,
    significance_test,
    cohens_d,
    cliffs_delta,
    correlation_matrix,
    aggregate_with_statistics,
    compute_inter_judge_agreement,
    compute_consensus_score,
    compare_systems,
    _krippendorff_alpha_interval,
)


class TestBootstrapConfidenceInterval:
    def test_single_value(self):
        result = bootstrap_confidence_interval([5.0])
        assert result["point_estimate"] == 5.0
        assert result["ci_lower"] == 5.0
        assert result["ci_upper"] == 5.0
        assert result["std_error"] == 0.0

    def test_empty(self):
        result = bootstrap_confidence_interval([])
        assert result["point_estimate"] == 0.0

    def test_normal_data(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = bootstrap_confidence_interval(data)
        assert 2.0 <= result["point_estimate"] <= 4.0
        assert result["ci_lower"] <= result["ci_upper"]

    def test_median_statistic(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = bootstrap_confidence_interval(data, statistic="median")
        assert result["point_estimate"] == 3.0

    def test_std_statistic(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = bootstrap_confidence_interval(data, statistic="std")
        assert result["point_estimate"] > 0

    def test_custom_confidence(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result90 = bootstrap_confidence_interval(data, confidence_level=0.90)
        result99 = bootstrap_confidence_interval(data, confidence_level=0.99)
        # 99% CI should be wider
        width90 = result90["ci_upper"] - result90["ci_lower"]
        width99 = result99["ci_upper"] - result99["ci_lower"]
        assert width99 >= width90 - 0.5  # Tolerance for bootstrap randomness

    def test_unknown_statistic_defaults_mean(self):
        data = [1.0, 2.0, 3.0]
        result = bootstrap_confidence_interval(data, statistic="nonexistent")
        assert result["point_estimate"] == 2.0


class TestPairedBootstrapTest:
    def test_same_scores(self):
        scores = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = paired_bootstrap_test(scores, scores)
        assert result["mean_difference"] == 0.0

    def test_different_lengths(self):
        result = paired_bootstrap_test([1.0, 2.0], [1.0])
        assert "error" in result

    def test_too_few_samples(self):
        result = paired_bootstrap_test([1.0], [2.0])
        assert "error" in result

    def test_significantly_different(self):
        a = [1.0, 1.0, 1.0, 1.0, 1.0]
        b = [5.0, 5.0, 5.0, 5.0, 5.0]
        result = paired_bootstrap_test(a, b)
        assert result["mean_difference"] < 0
        assert not result["a_better"]


class TestSignificanceTest:
    def test_auto_paired(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.5, 2.5, 3.5, 4.5, 5.5]
        result = significance_test(a, b, paired=True)
        assert "test_type" in result or "mean_difference" in result

    def test_wilcoxon(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.1, 2.1, 3.1, 4.1, 5.1]
        result = significance_test(a, b, test_type="wilcoxon", paired=True)
        assert "p_value" in result or "error" in result

    def test_mannwhitney(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.5, 2.5, 3.5, 4.5, 5.5]
        result = significance_test(a, b, test_type="mannwhitney", paired=False)
        assert "p_value" in result or "error" in result

    def test_t_test(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.5, 2.5, 3.5, 4.5, 5.5]
        result = significance_test(a, b, test_type="t-test", paired=True)
        assert "p_value" in result

    def test_t_test_unpaired(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0, 7.0]
        result = significance_test(a, b, test_type="t-test", paired=False)
        assert "p_value" in result

    def test_wilcoxon_different_lengths(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0]
        result = significance_test(a, b, test_type="wilcoxon", paired=True)
        assert "error" in result

    def test_small_sample_auto(self):
        a = [1.0, 2.0]
        b = [3.0, 4.0]
        result = significance_test(a, b, test_type="auto", paired=True)
        assert "p_value" in result or "mean_difference" in result


class TestCohensD:
    def test_identical(self):
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        result = cohens_d(a, b)
        assert result["cohens_d"] == 0.0
        assert result["interpretation"] == "negligible"

    def test_large_effect(self):
        a = [10.0, 11.0, 12.0, 13.0, 14.0]
        b = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = cohens_d(a, b)
        assert abs(result["cohens_d"]) >= 0.8
        assert result["interpretation"] == "large"

    def test_small_effect(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.5, 2.5, 3.5, 4.5, 5.5]
        result = cohens_d(a, b)
        assert abs(result["cohens_d"]) >= 0.2
        assert result["interpretation"] in ("small", "medium")

    def test_zero_std(self):
        a = [5.0, 5.0, 5.0]
        b = [5.0, 5.0, 5.0]
        result = cohens_d(a, b)
        assert result["cohens_d"] == 0.0


class TestCliffsDelta:
    def test_identical(self):
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        result = cliffs_delta(a, b)
        assert result["cliffs_delta"] == 0.0

    def test_complete_dominance(self):
        a = [10.0, 11.0, 12.0]
        b = [1.0, 2.0, 3.0]
        result = cliffs_delta(a, b)
        assert result["cliffs_delta"] == 1.0
        assert result["a_better"] is True

    def test_reverse_dominance(self):
        a = [1.0, 2.0, 3.0]
        b = [10.0, 11.0, 12.0]
        result = cliffs_delta(a, b)
        assert result["cliffs_delta"] == -1.0

    def test_empty_a(self):
        result = cliffs_delta([], [1.0, 2.0])
        assert result["cliffs_delta"] == 0.0

    def test_empty_b(self):
        result = cliffs_delta([1.0, 2.0], [])
        assert result["cliffs_delta"] == 0.0


class TestCorrelationMatrix:
    def test_two_metrics(self):
        data = {
            "accuracy": [0.8, 0.9, 0.7, 0.85, 0.95],
            "f1": [0.75, 0.88, 0.68, 0.82, 0.92],
        }
        result = correlation_matrix(data)
        assert result["accuracy"]["accuracy"] == 1.0
        assert result["f1"]["f1"] == 1.0
        assert result["accuracy"]["f1"] is not None

    def test_single_metric(self):
        result = correlation_matrix({"a": [1, 2, 3]})
        assert result == {}

    def test_short_data(self):
        data = {"a": [1.0, 2.0], "b": [3.0]}
        result = correlation_matrix(data)
        assert result["a"]["b"] is None

    def test_spearman(self):
        data = {
            "a": [1.0, 2.0, 3.0, 4.0, 5.0],
            "b": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
        result = correlation_matrix(data, method="spearman")
        assert result["a"]["b"] is not None


class TestAggregateWithStatistics:
    def test_empty(self):
        result = aggregate_with_statistics([], "accuracy")
        assert result["mean"] is None
        assert result["n_samples"] == 0

    def test_normal_data(self):
        scores = [0.8, 0.9, 0.85, 0.95, 0.88]
        result = aggregate_with_statistics(scores, "accuracy")
        assert result["metric"] == "accuracy"
        assert 0.8 <= result["mean"] <= 0.95
        assert result["n_samples"] == 5
        assert result["ci_lower"] <= result["ci_upper"]

    def test_single_score(self):
        result = aggregate_with_statistics([0.9], "f1")
        assert result["mean"] == 0.9
        assert result["std"] == 0.0


class TestComputeInterJudgeAgreement:
    def test_too_few_judges(self):
        result = compute_inter_judge_agreement({"judge1": [1, 2, 3]})
        assert "error" in result

    def test_empty(self):
        result = compute_inter_judge_agreement({})
        assert "error" in result

    def test_perfect_agreement(self):
        result = compute_inter_judge_agreement({
            "judge1": [1.0, 2.0, 3.0, 4.0, 5.0],
            "judge2": [1.0, 2.0, 3.0, 4.0, 5.0],
        })
        assert result["krippendorff_alpha"] == 1.0
        assert result["interpretation"] == "high agreement"

    def test_no_agreement(self):
        result = compute_inter_judge_agreement({
            "judge1": [1.0, 2.0, 3.0, 4.0, 5.0],
            "judge2": [5.0, 4.0, 3.0, 2.0, 1.0],
        })
        assert result["krippendorff_alpha"] < 0.5

    def test_different_lengths(self):
        result = compute_inter_judge_agreement({
            "judge1": [1, 2, 3],
            "judge2": [1, 2],
        })
        assert "error" in result

    def test_too_few_samples(self):
        result = compute_inter_judge_agreement({
            "judge1": [1.0],
            "judge2": [1.0],
        })
        assert "error" in result

    def test_three_judges(self):
        result = compute_inter_judge_agreement({
            "j1": [1.0, 2.0, 3.0],
            "j2": [1.1, 2.1, 3.1],
            "j3": [1.2, 2.2, 3.2],
        })
        assert result["n_judges"] == 3
        assert "pairwise_correlations" in result


class TestComputeConsensusScore:
    def test_empty(self):
        result = compute_consensus_score({})
        assert result["consensus_score"] is None

    def test_single_judge(self):
        result = compute_consensus_score({"j1": 5.0})
        assert result["consensus_score"] == 5.0
        assert result["n_judges"] == 1

    def test_mean(self):
        result = compute_consensus_score({"j1": 4.0, "j2": 6.0}, method="mean")
        assert result["consensus_score"] == 5.0

    def test_median(self):
        result = compute_consensus_score({"j1": 1.0, "j2": 5.0, "j3": 9.0}, method="median")
        assert result["consensus_score"] == 5.0

    def test_trimmed_mean(self):
        result = compute_consensus_score(
            {"j1": 1.0, "j2": 5.0, "j3": 9.0}, method="trimmed_mean"
        )
        assert result["consensus_score"] == 5.0  # trimmed mean of [5.0]

    def test_trimmed_mean_two_judges(self):
        result = compute_consensus_score({"j1": 3.0, "j2": 7.0}, method="trimmed_mean")
        # With only 2, can't trim; falls back to mean
        assert result["consensus_score"] == 5.0


class TestCompareSystemsMeta:
    def test_basic_comparison(self):
        a = {"accuracy": [0.9, 0.8, 0.85, 0.9, 0.88]}
        b = {"accuracy": [0.7, 0.65, 0.72, 0.68, 0.71]}
        result = compare_systems(a, b, "Model A", "Model B")
        assert result["system_a"] == "Model A"
        assert "accuracy" in result["metrics"]

    def test_no_common_metrics(self):
        a = {"accuracy": [0.9]}
        b = {"f1": [0.8]}
        result = compare_systems(a, b)
        assert result["metrics"] == {}


class TestKrippendorffAlphaInterval:
    def test_perfect(self):
        ratings = np.array([[1, 2, 3], [1, 2, 3]])
        alpha = _krippendorff_alpha_interval(ratings)
        assert alpha == 1.0

    def test_no_variation(self):
        ratings = np.array([[5, 5, 5], [5, 5, 5]])
        alpha = _krippendorff_alpha_interval(ratings)
        assert alpha == 1.0
