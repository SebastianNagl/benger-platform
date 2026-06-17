"""Branch-coverage tests for ml_evaluation/inter_annotator_agreement.py.

The existing test_iaa_coverage.py / test_inter_annotator_agreement.py suites
exercise the happy paths and the extreme interpretation bands (perfect / zero
agreement). This file fills in the *intermediate* interpretation bands and a
few edge guards they skip:

  * cronbachs_alpha:   the 'poor' / 'questionable' / 'acceptable' / 'good' bands.
  * krippendorff_alpha: the 'tentative conclusions only' and 'acceptable for
                        tentative conclusions' bands, plus the ratio-distance
                        s == 0 guard.
  * intraclass_correlation: the 'poor' / 'fair' / 'good' bands.
  * compute_all_iaa_metrics: the ValueError/TypeError conversion-skip branch.
  * span_agreement:    the 'Moderate' and 'Fair' interpretation bands.
  * span_boundary_agreement: the 'Good' and 'Moderate' interpretation bands.

Each matrix was run through the real function and its resulting coefficient
band confirmed before being pinned here, so the assertions check BOTH the
numeric band and the human-readable interpretation string (behavioral, not
structural). No model is loaded. Mirrors test_iaa_coverage.py idioms.
"""

import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.inter_annotator_agreement import (  # noqa: E402
    cronbachs_alpha,
    krippendorff_alpha,
    intraclass_correlation,
    compute_all_iaa_metrics,
    span_agreement,
    span_boundary_agreement,
)


# ============================================================================
# cronbachs_alpha — intermediate interpretation bands
# ============================================================================


class TestCronbachsAlphaBands:
    def test_poor_band(self):
        """alpha in [0.5, 0.6) -> 'poor'. Verified ~0.547."""
        matrix = [[7, 7], [1, 6], [4, 3], [6, 7], [2, 5]]
        result = cronbachs_alpha(matrix)
        assert 0.5 <= result["alpha"] < 0.6
        assert result["interpretation"] == "poor"

    def test_questionable_band(self):
        """alpha in [0.6, 0.7) -> 'questionable'. Verified ~0.667."""
        matrix = [[1, 4], [1, 7], [4, 4]]
        result = cronbachs_alpha(matrix)
        assert 0.6 <= result["alpha"] < 0.7
        assert result["interpretation"] == "questionable"

    def test_acceptable_band(self):
        """alpha in [0.7, 0.8) -> 'acceptable'. Verified ~0.75."""
        matrix = [[5, 7], [7, 7], [1, 3]]
        result = cronbachs_alpha(matrix)
        assert 0.7 <= result["alpha"] < 0.8
        assert result["interpretation"] == "acceptable"

    def test_good_band(self):
        """alpha in [0.8, 0.9) -> 'good'. Verified ~0.884."""
        matrix = [[5, 1], [7, 2], [6, 2], [5, 5]]
        result = cronbachs_alpha(matrix)
        assert 0.8 <= result["alpha"] < 0.9
        assert result["interpretation"] == "good"


# ============================================================================
# krippendorff_alpha — intermediate bands + ratio s==0 guard
# ============================================================================


class TestKrippendorffAlphaBands:
    def test_tentative_band(self):
        """interval alpha in [0.0, 0.667) -> 'tentative conclusions only'.
        Verified ~0.5."""
        matrix = [[4, 4], [4, 5], [4, 2], [3, 1], [1, 2]]
        result = krippendorff_alpha(matrix, "interval")
        assert 0.0 <= result["alpha"] < 0.667
        assert result["interpretation"] == "tentative conclusions only"

    def test_acceptable_band(self):
        """interval alpha in [0.667, 0.8) -> 'acceptable for tentative
        conclusions'. Verified ~0.792."""
        matrix = [[5, 5], [2, 3], [5, 4]]
        result = krippendorff_alpha(matrix, "interval")
        assert 0.667 <= result["alpha"] < 0.8
        assert result["interpretation"] == "acceptable for tentative conclusions"

    def test_ratio_zero_sum_distance(self):
        """In ratio mode, a value pair summing to 0 must not divide-by-zero;
        the distance function returns 0 for that pair. A matrix with 0/0 pairs
        plus a 2/2 disagreement row stays computable."""
        matrix = [[0, 0], [0, 0], [2, 2]]
        result = krippendorff_alpha(matrix, "ratio")
        # All rows agree internally -> observed disagreement 0 -> alpha 1.0
        assert result["alpha"] == pytest.approx(1.0)
        assert result["level_of_measurement"] == "ratio"


# ============================================================================
# intraclass_correlation — intermediate bands
# ============================================================================


class TestICCBands:
    def test_poor_band(self):
        """ICC < 0.40 -> 'poor'. Verified ~ -0.45."""
        matrix = [[4, 1], [2, 1], [5, 2], [3, 4], [2, 5]]
        result = intraclass_correlation(matrix, "ICC(2,1)")
        assert result["icc"] < 0.40
        assert result["interpretation"] == "poor"

    def test_fair_band(self):
        """ICC in [0.40, 0.60) -> 'fair'. Verified ~0.483."""
        matrix = [[3, 6], [4, 3], [6, 4], [2, 2], [1, 2]]
        result = intraclass_correlation(matrix, "ICC(2,1)")
        assert 0.40 <= result["icc"] < 0.60
        assert result["interpretation"] == "fair"

    def test_good_band(self):
        """ICC in [0.60, 0.75) -> 'good'. Verified ~0.615."""
        matrix = [[6, 4], [1, 2], [1, 2], [4, 2]]
        result = intraclass_correlation(matrix, "ICC(2,1)")
        assert 0.60 <= result["icc"] < 0.75
        assert result["interpretation"] == "good"


# ============================================================================
# compute_all_iaa_metrics — conversion-failure skip branch
# ============================================================================


class TestComputeAllIAAConversionSkip:
    def test_non_numeric_ordinal_skips_cronbach_icc(self):
        """For an ordinal/interval/ratio level the function tries to cast every
        rating to float for Cronbach/ICC. Non-numeric strings raise ValueError,
        which is caught -> those metrics are simply absent (no crash)."""
        matrix = [["high", "low"], ["mid", "mid"], ["low", "high"]]
        result = compute_all_iaa_metrics(matrix, "ordinal")
        # Percent agreement / krippendorff still computed
        assert "percent_agreement" in result["metrics"]
        assert "krippendorff_alpha" in result["metrics"]
        # Cronbach/ICC skipped because float() conversion failed
        assert "cronbachs_alpha" not in result["metrics"]
        assert "icc" not in result["metrics"]


# ============================================================================
# span_agreement — Moderate / Fair interpretation bands
# ============================================================================


class TestSpanAgreementBands:
    def test_moderate_band(self):
        """F1 in [0.6, 0.8) -> 'Moderate span agreement'. 2 matched of 2 a1 /
        4 a2 -> P=0.5 R=1.0 F1=0.667."""
        annotations = [
            [
                [{"start": 0, "end": 5}, {"start": 10, "end": 15}],
                [
                    {"start": 0, "end": 5},
                    {"start": 10, "end": 15},
                    {"start": 20, "end": 25},
                    {"start": 30, "end": 35},
                ],
            ]
        ]
        result = span_agreement(annotations, include_labels=False)
        assert 0.6 <= result["span_agreement"] < 0.8
        assert result["interpretation"] == "Moderate span agreement"

    def test_fair_band(self):
        """F1 in [0.4, 0.6) -> 'Fair span agreement'. 2 matched of 3 a1 / 5 a2
        -> P=0.4 R=0.667 F1=0.5."""
        annotations = [
            [
                [
                    {"start": 0, "end": 5},
                    {"start": 10, "end": 15},
                    {"start": 40, "end": 45},
                ],
                [
                    {"start": 0, "end": 5},
                    {"start": 10, "end": 15},
                    {"start": 20, "end": 25},
                    {"start": 30, "end": 35},
                    {"start": 50, "end": 55},
                ],
            ]
        ]
        result = span_agreement(annotations, include_labels=False)
        assert 0.4 <= result["span_agreement"] < 0.6
        assert result["interpretation"] == "Fair span agreement"


# ============================================================================
# span_boundary_agreement — Good / Moderate interpretation bands
# ============================================================================


class TestSpanBoundaryAgreementBands:
    def test_good_band(self):
        """boundary in [0.7, 0.9) -> 'Good boundary agreement'. One exact pair
        + one start-only pair -> start=1.0 end=0.5 boundary=0.75."""
        annotations = [
            [[{"start": 0, "end": 10}], [{"start": 0, "end": 10}]],
            [[{"start": 20, "end": 30}], [{"start": 20, "end": 36}]],
        ]
        result = span_boundary_agreement(annotations, tolerance=0)
        assert 0.7 <= result["boundary_agreement"] < 0.9
        assert result["interpretation"] == "Good boundary agreement"

    def test_moderate_band(self):
        """boundary in [0.5, 0.7) -> 'Moderate boundary agreement'. start=0.5
        end=0.5 -> 0.5."""
        annotations = [
            [[{"start": 0, "end": 10}], [{"start": 2, "end": 10}]],
            [[{"start": 20, "end": 30}], [{"start": 20, "end": 33}]],
        ]
        result = span_boundary_agreement(annotations, tolerance=0)
        assert 0.5 <= result["boundary_agreement"] < 0.7
        assert result["interpretation"] == "Moderate boundary agreement"
