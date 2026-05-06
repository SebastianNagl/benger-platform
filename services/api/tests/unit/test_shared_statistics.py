"""
Tests for the shared statistics package.

Sanity checks the math primitives and verifies the composite `compute_agreement`
works for both categorical and numeric raters.
"""

from bg_statistics import (
    bootstrap_ci,
    cliffs_delta,
    cohens_d,
    cohens_kappa,
    compute_agreement,
    confidence_interval,
    fleiss_kappa,
    mean,
    pearson,
    percent_agreement,
    spearman,
    stddev,
    variance,
)


class TestDescriptive:
    def test_mean(self):
        assert mean([1, 2, 3, 4, 5]) == 3.0
        assert mean([]) is None

    def test_variance(self):
        # Sample variance (ddof=1, the academic default for unbiased
        # estimation): for the textbook series the *population* variance is
        # 4.0 but the sample variance is 32/7 ≈ 4.5714. We default to ddof=1.
        assert abs(variance([2, 4, 4, 4, 5, 5, 7, 9]) - 32 / 7) < 1e-9
        assert variance([2, 4, 4, 4, 5, 5, 7, 9], ddof=0) == 4.0
        assert variance([1]) is None

    def test_stddev(self):
        import math

        assert abs(stddev([2, 4, 4, 4, 5, 5, 7, 9]) - math.sqrt(32 / 7)) < 1e-9
        assert stddev([2, 4, 4, 4, 5, 5, 7, 9], ddof=0) == 2.0

    def test_confidence_interval_returns_bounds(self):
        lo, hi, n = confidence_interval([1.0, 2.0, 3.0, 4.0, 5.0])
        assert n == 5
        assert lo is not None and hi is not None
        assert lo < 3.0 < hi

    def test_confidence_interval_too_small(self):
        lo, hi, n = confidence_interval([1.0])
        assert (lo, hi, n) == (None, None, 1)


class TestEffectSize:
    def test_cohens_d_zero_when_equal(self):
        result = cohens_d([1, 2, 3], [1, 2, 3])
        assert result["cohens_d"] == 0.0
        assert result["interpretation"] == "negligible"

    def test_cohens_d_large_when_separated(self):
        result = cohens_d([1, 2, 3, 4], [10, 11, 12, 13])
        assert result["cohens_d"] is not None
        assert abs(result["cohens_d"]) > 0.8
        assert result["interpretation"] == "large"

    def test_cliffs_delta_zero_when_overlapping(self):
        result = cliffs_delta([1, 2, 3], [1, 2, 3])
        assert result["cliffs_delta"] == 0.0

    def test_cliffs_delta_one_when_separated(self):
        result = cliffs_delta([1, 2, 3], [10, 11, 12])
        assert result["cliffs_delta"] == -1.0


class TestCorrelation:
    def test_pearson_perfect_positive(self):
        assert pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == 1.0

    def test_pearson_perfect_negative(self):
        assert pearson([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]) == -1.0

    def test_pearson_too_few_returns_none(self):
        assert pearson([1, 2], [2, 4]) is None

    def test_spearman_handles_ties(self):
        r = spearman([1, 2, 3, 4], [4, 3, 2, 1])
        assert r == -1.0


class TestBootstrap:
    def test_bootstrap_ci_brackets_mean(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        lo, hi = bootstrap_ci(values, n_iterations=200, seed=42)
        assert lo is not None and hi is not None
        assert lo < 5.5 < hi


class TestAgreement:
    def test_cohens_kappa_perfect(self):
        result = cohens_kappa(["a", "b", "c", "a"], ["a", "b", "c", "a"])
        assert result["kappa"] == 1.0

    def test_cohens_kappa_disagree(self):
        result = cohens_kappa(["a", "a", "a", "a"], ["b", "b", "b", "b"])
        # Both raters always pick one (different) category — observed and expected
        # agreement are both 0, so kappa is undefined and falls back to 0.
        assert result["kappa"] == 0.0

    def test_fleiss_kappa_perfect(self):
        # Each item rated identically by all raters
        matrix = [["a", "a", "a"], ["b", "b", "b"], ["c", "c", "c"]]
        result = fleiss_kappa(matrix)
        assert result["kappa"] == 1.0

    def test_percent_agreement(self):
        matrix = [["a", "a", "a"], ["b", "b", "c"], ["c", "c", "c"]]
        # 2/3 items unanimous
        assert percent_agreement(matrix) == round(2 / 3, 4)

    def test_compute_agreement_categorical(self):
        triples = [
            ("rater1", "task1", "yes"),
            ("rater2", "task1", "yes"),
            ("rater1", "task2", "no"),
            ("rater2", "task2", "no"),
            ("rater1", "task3", "yes"),
            ("rater2", "task3", "no"),
        ]
        report = compute_agreement(triples, score_type="categorical")
        assert report.n_raters == 2
        assert report.n_items == 3
        assert report.percent_agreement is not None
        # 2 of 3 items agreed
        assert report.percent_agreement == round(2 / 3, 4)
        assert report.fleiss_kappa is not None
        assert ("rater1", "rater2") in report.cohens_kappa_pairwise

    def test_compute_agreement_numeric(self):
        triples = [
            ("judge_a", "task1", 0.8),
            ("judge_b", "task1", 0.7),
            ("judge_a", "task2", 0.5),
            ("judge_b", "task2", 0.6),
            ("judge_a", "task3", 0.9),
            ("judge_b", "task3", 0.95),
        ]
        report = compute_agreement(triples, score_type="numeric")
        assert report.n_raters == 2
        assert report.n_items == 3
        assert ("judge_a", "judge_b") in report.pearson_r_pairwise
        assert report.mean_absolute_deviation is not None
        # Per-item MAD averages roughly (0.05 + 0.05 + 0.025) / 3 ≈ 0.0417
        assert 0.0 < report.mean_absolute_deviation < 0.1

    def test_compute_agreement_empty(self):
        report = compute_agreement([], score_type="categorical")
        assert report.n_raters == 0
        assert report.n_items == 0
