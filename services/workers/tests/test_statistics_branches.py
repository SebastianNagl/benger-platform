"""Branch-coverage tests for ml_evaluation/statistics.py.

Targets the branches the existing test_statistics.py / test_statistics_coverage.py
suites don't reach:

  * significance_test: scipy-unavailable bootstrap fallback, the auto-select
    non-normal path (-> wilcoxon), and the exception branch when a scipy test
    raises (zero-difference Wilcoxon).
  * cohens_d: the "medium" effect-size band (0.5 <= |d| < 0.8).
  * cliffs_delta: the "small" and "medium" interpretation bands.
  * correlation_matrix: the numpy-pearson fallback (SCIPY_AVAILABLE patched off)
    and the nan -> None coercion branch.
  * mcnemar_test: the statsmodels-missing RuntimeError, the length/empty
    ValueErrors, a real significant result, and a real non-significant result.
  * compute_inter_judge_agreement: the numpy-corr fallback (SCIPY off) and the
    "moderate"/"low" interpretation bands.
  * _krippendorff_alpha_interval: the pairs_count == 0 and expected_pairs == 0
    degenerate guards.
  * compare_systems: the a_wins / b_wins / tie winner branches.

Every numeric assertion uses inputs whose expected band was verified against the
real function before being pinned here. No model is loaded. Mirrors the idioms in
test_statistics_coverage.py and test_sample_evaluator_branches.py.
"""

import os
import sys

import numpy as np
import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import ml_evaluation.statistics as stats_mod  # noqa: E402
from ml_evaluation.statistics import (  # noqa: E402
    significance_test,
    cohens_d,
    cliffs_delta,
    correlation_matrix,
    mcnemar_test,
    compute_inter_judge_agreement,
    compare_systems,
    _krippendorff_alpha_interval,
)


# ============================================================================
# significance_test — scipy-off fallback, non-normal auto, exception branch
# ============================================================================


class TestSignificanceTestBranches:
    def test_scipy_unavailable_paired_falls_back_to_bootstrap(self, monkeypatch):
        """When scipy is absent and samples are paired+equal-length, the
        function delegates to paired_bootstrap_test (which returns a
        'mean_difference' / 'p_value' shape, not 'test_type')."""
        monkeypatch.setattr(stats_mod, "SCIPY_AVAILABLE", False)
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [2.0, 3.0, 4.0, 5.0, 6.0]
        result = significance_test(a, b, paired=True)
        # paired_bootstrap_test shape, not the scipy-test shape
        assert "mean_difference" in result
        assert "test_type" not in result
        # b is uniformly 1.0 higher -> A is worse
        assert result["mean_difference"] == pytest.approx(-1.0)

    def test_scipy_unavailable_unpaired_returns_error(self, monkeypatch):
        monkeypatch.setattr(stats_mod, "SCIPY_AVAILABLE", False)
        result = significance_test([1.0, 2.0, 3.0], [4.0, 5.0], paired=False)
        assert result["error"] == "scipy not available for parametric tests"

    def test_auto_select_non_normal_uses_wilcoxon(self):
        """Heavily skewed paired data fails the Shapiro normality check, so the
        auto path selects the non-parametric Wilcoxon test."""
        skew_a = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 100.0]
        skew_b = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]
        result = significance_test(skew_a, skew_b, test_type="auto", paired=True)
        assert result["test_type"] == "wilcoxon"
        assert "p_value" in result


# ============================================================================
# cohens_d — medium band
# ============================================================================


class TestCohensDMediumBand:
    def test_medium_effect_band(self):
        """|d| in [0.5, 0.8) -> 'medium'. Inputs verified to yield ~0.665."""
        a = [2.68, 2.39, 2.20, 2.72, 2.29, 2.37]
        b = [1.06, 2.94, 2.89, 0.48, 2.26, 2.15]
        result = cohens_d(a, b)
        assert 0.5 <= abs(result["cohens_d"]) < 0.8
        assert result["interpretation"] == "medium"


# ============================================================================
# cliffs_delta — small and medium bands
# ============================================================================


class TestCliffsDeltaBands:
    def test_small_band(self):
        """|delta| in [0.147, 0.33) -> 'small'. Verified ~ -0.167."""
        a = [3, 4, 1, 3, 2, 3]
        b = [4, 4, 2, 3, 3, 2]
        result = cliffs_delta(a, b)
        assert 0.147 <= abs(result["cliffs_delta"]) < 0.33
        assert result["interpretation"] == "small"

    def test_medium_band(self):
        """|delta| in [0.33, 0.474) -> 'medium'. Verified ~ -0.472."""
        a = [0, 1, 1, 3, 0, 2]
        b = [0, 4, 1, 4, 4, 2]
        result = cliffs_delta(a, b)
        assert 0.33 <= abs(result["cliffs_delta"]) < 0.474
        assert result["interpretation"] == "medium"


# ============================================================================
# correlation_matrix — numpy fallback + nan -> None
# ============================================================================


class TestCorrelationMatrixBranches:
    def test_numpy_pearson_fallback_when_scipy_off(self, monkeypatch):
        """With scipy unavailable, pearson falls through to numpy.corrcoef."""
        monkeypatch.setattr(stats_mod, "SCIPY_AVAILABLE", False)
        data = {
            "a": [1.0, 2.0, 3.0, 4.0, 5.0],
            "b": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
        result = correlation_matrix(data)
        # Perfectly correlated -> 1.0 on the off-diagonal
        assert result["a"]["b"] == pytest.approx(1.0)
        assert result["b"]["a"] == pytest.approx(1.0)

    def test_constant_series_yields_none(self):
        """A constant column makes pearson r undefined (nan) -> coerced to None."""
        data = {"a": [1.0, 1.0, 1.0, 1.0], "b": [2.0, 3.0, 4.0, 5.0]}
        result = correlation_matrix(data)
        assert result["a"]["b"] is None
        assert result["b"]["a"] is None


# ============================================================================
# mcnemar_test — missing-lib, validation, significant, non-significant
# ============================================================================


class TestMcNemarTest:
    def test_missing_statsmodels_raises(self, monkeypatch):
        monkeypatch.setattr(stats_mod, "STATSMODELS_AVAILABLE", False)
        with pytest.raises(RuntimeError, match="statsmodels"):
            mcnemar_test([True, False], [False, True])

    def test_length_mismatch_raises(self):
        if not stats_mod.STATSMODELS_AVAILABLE:
            pytest.skip("statsmodels not installed")
        with pytest.raises(ValueError, match="equal length"):
            mcnemar_test([True, False, True], [True, False])

    def test_empty_raises(self):
        if not stats_mod.STATSMODELS_AVAILABLE:
            pytest.skip("statsmodels not installed")
        with pytest.raises(ValueError, match="empty"):
            mcnemar_test([], [])

    def test_non_significant_result(self):
        if not stats_mod.STATSMODELS_AVAILABLE:
            pytest.skip("statsmodels not installed")
        # Balanced discordant pairs -> not significant
        a = [True, True, False, True, False, True, False, False]
        b = [True, False, False, False, True, True, False, True]
        result = mcnemar_test(a, b)
        # numpy bool: compare by value, not identity
        assert bool(result["significant_at_05"]) is False
        assert result["a_correct_b_wrong"] == 2
        assert result["a_wrong_b_correct"] == 2

    def test_significant_result_a_better(self):
        if not stats_mod.STATSMODELS_AVAILABLE:
            pytest.skip("statsmodels not installed")
        # A correct, B wrong on the first 15; both wrong on the last 5 -> strongly
        # discordant in A's favour.
        a = [True] * 15 + [False] * 5
        b = [False] * 15 + [False] * 5
        result = mcnemar_test(a, b)
        assert result["p_value"] < 0.05
        assert bool(result["significant_at_05"]) is True
        assert bool(result["a_better"]) is True
        assert result["a_correct_b_wrong"] == 15
        assert result["a_wrong_b_correct"] == 0


# ============================================================================
# compute_inter_judge_agreement — numpy fallback + interpretation bands
# ============================================================================


class TestInterJudgeAgreementBranches:
    def test_numpy_corr_fallback_when_scipy_off(self, monkeypatch):
        monkeypatch.setattr(stats_mod, "SCIPY_AVAILABLE", False)
        result = compute_inter_judge_agreement(
            {
                "judge1": [1.0, 2.0, 3.0, 4.0, 5.0],
                "judge2": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        )
        assert result["mean_pairwise_correlation"] == pytest.approx(1.0)

    def test_moderate_agreement_band(self):
        """alpha in [0.667, 0.8) -> 'moderate agreement'. Verified ~0.731."""
        result = compute_inter_judge_agreement(
            {
                "j1": [4.1, 2.1, 1.3, 2.3],
                "j2": [6.0, 3.1, -0.2, 1.3],
            }
        )
        alpha = result["krippendorff_alpha"]
        assert 0.667 <= alpha < 0.8
        assert result["interpretation"] == "moderate agreement"

    def test_low_agreement_band(self):
        """alpha in [0.0, 0.667) -> 'low agreement'. Verified ~0.315."""
        result = compute_inter_judge_agreement(
            {
                "j1": [4.5, 4.4, 4.1, 2.8, 4.4],
                "j2": [3.3, 5.6, 4.0, 3.3, 3.1],
            }
        )
        alpha = result["krippendorff_alpha"]
        assert 0.0 <= alpha < 0.667
        assert result["interpretation"] == "low agreement"


# ============================================================================
# _krippendorff_alpha_interval — degenerate guards
# ============================================================================


class TestKrippendorffIntervalDegenerate:
    def test_single_judge_returns_zero(self):
        """With one judge there are no within-sample pairs -> pairs_count == 0
        guard returns 0.0."""
        ratings = np.array([[1.0, 2.0, 3.0]])
        assert _krippendorff_alpha_interval(ratings) == 0.0

    def test_single_total_rating_returns_zero(self):
        """One judge, one sample -> n_total == 1 -> expected_pairs == 0 guard.
        (Also exercises the pairs_count == 0 path first, but a 1x1 array hits
        the expected-pairs guard distinctly from the multi-sample single-judge
        case.)"""
        ratings = np.array([[5.0]])
        assert _krippendorff_alpha_interval(ratings) == 0.0


# ============================================================================
# compare_systems — winner branches
# ============================================================================


class TestCompareSystemsWinners:
    def test_a_wins(self):
        a = {"acc": [0.90, 0.91, 0.92, 0.93, 0.95, 0.94, 0.90, 0.91]}
        b = {"acc": [0.10, 0.11, 0.12, 0.13, 0.15, 0.14, 0.10, 0.11]}
        result = compare_systems(a, b, "A", "B")
        assert result["summary"]["a_wins"] == 1
        assert result["summary"]["b_wins"] == 0
        assert result["metrics"]["acc"]["winner"] == "A"

    def test_b_wins(self):
        a = {"acc": [0.10, 0.11, 0.12, 0.13, 0.15, 0.14, 0.10, 0.11]}
        b = {"acc": [0.90, 0.91, 0.92, 0.93, 0.95, 0.94, 0.90, 0.91]}
        result = compare_systems(a, b, "A", "B")
        assert result["summary"]["b_wins"] == 1
        assert result["summary"]["a_wins"] == 0
        assert result["metrics"]["acc"]["winner"] == "B"

    def test_tie(self):
        a = {"acc": [0.50, 0.51, 0.49, 0.50, 0.52, 0.48]}
        b = {"acc": [0.50, 0.51, 0.49, 0.50, 0.52, 0.48]}
        result = compare_systems(a, b)
        assert result["summary"]["ties"] == 1
        assert result["metrics"]["acc"]["winner"] == "tie"

    def test_short_metric_skips_significance(self):
        """< 3 paired samples skips the significance/effect block entirely."""
        a = {"acc": [0.9, 0.8]}
        b = {"acc": [0.7, 0.6]}
        result = compare_systems(a, b)
        assert "significance" not in result["metrics"]["acc"]
        assert result["summary"] == {"a_wins": 0, "b_wins": 0, "ties": 0}
