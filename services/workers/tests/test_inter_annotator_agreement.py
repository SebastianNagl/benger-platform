"""Tests for ml_evaluation/inter_annotator_agreement.py - IAA metrics.

Covers:
- cohens_kappa (unweighted, linear, quadratic)
- fleiss_kappa
- cronbachs_alpha
- krippendorff_alpha (nominal, ordinal, interval, ratio)
- percent_agreement
- intraclass_correlation (ICC types)
- _span_iou
- _match_spans
- span_agreement
- span_boundary_agreement
- compute_all_iaa_metrics
"""

import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.inter_annotator_agreement import (
    _match_spans,
    _span_iou,
    cohens_kappa,
    compute_all_iaa_metrics,
    cronbachs_alpha,
    fleiss_kappa,
    intraclass_correlation,
    krippendorff_alpha,
    percent_agreement,
    span_agreement,
    span_boundary_agreement,
)


# ---------------------------------------------------------------------------
# cohens_kappa
# ---------------------------------------------------------------------------

class TestCohensKappa:

    def test_perfect_agreement(self):
        r1 = ["A", "B", "C", "A", "B"]
        r2 = ["A", "B", "C", "A", "B"]
        result = cohens_kappa(r1, r2)
        assert result["kappa"] == 1.0
        assert result["interpretation"] == "almost perfect"

    def test_no_agreement(self):
        # With only 2 categories and complete disagreement,
        # kappa = (po - pe) / (1 - pe) where po=0 and pe=0.5 -> kappa = -1
        r1 = ["A", "B", "A", "B"]
        r2 = ["B", "A", "B", "A"]
        result = cohens_kappa(r1, r2)
        assert result["kappa"] < 0

    def test_unequal_length_error(self):
        result = cohens_kappa(["A"], ["A", "B"])
        assert "error" in result

    def test_empty_ratings_error(self):
        result = cohens_kappa([], [])
        assert "error" in result

    def test_linear_weights(self):
        r1 = [1, 2, 3, 4, 5]
        r2 = [1, 2, 3, 4, 5]
        result = cohens_kappa(r1, r2, weights="linear")
        assert result["kappa"] == 1.0

    def test_quadratic_weights(self):
        r1 = [1, 2, 3, 4, 5]
        r2 = [1, 2, 3, 4, 5]
        result = cohens_kappa(r1, r2, weights="quadratic")
        assert result["kappa"] == 1.0

    def test_unknown_weights_error(self):
        result = cohens_kappa([1, 2], [1, 2], weights="cubic")
        assert "error" in result

    def test_interpretation_moderate(self):
        # Create data with moderate agreement
        r1 = ["A", "A", "B", "B", "A", "B", "A", "B", "A", "B"]
        r2 = ["A", "B", "B", "A", "A", "B", "B", "B", "A", "A"]
        result = cohens_kappa(r1, r2)
        assert "kappa" in result
        assert result["n_samples"] == 10


# ---------------------------------------------------------------------------
# fleiss_kappa
# ---------------------------------------------------------------------------

class TestFleissKappa:

    def test_perfect_agreement(self):
        # All raters agree on each item
        ratings = [
            [1, 1, 1],
            [2, 2, 2],
            [3, 3, 3],
        ]
        result = fleiss_kappa(ratings)
        assert result["kappa"] == 1.0
        assert result["interpretation"] == "almost perfect"

    def test_empty_matrix_error(self):
        result = fleiss_kappa([])
        assert "error" in result

    def test_empty_rows_error(self):
        result = fleiss_kappa([[]])
        assert "error" in result

    def test_result_keys(self):
        ratings = [[1, 2, 1], [2, 2, 1], [1, 1, 1]]
        result = fleiss_kappa(ratings)
        assert "kappa" in result
        assert "observed_agreement" in result
        assert "expected_agreement" in result
        assert "n_items" in result

    def test_custom_categories(self):
        ratings = [[1, 2], [2, 1]]
        result = fleiss_kappa(ratings, categories=[1, 2, 3])
        assert result["n_categories"] == 3


# ---------------------------------------------------------------------------
# cronbachs_alpha
# ---------------------------------------------------------------------------

class TestCronbachsAlpha:

    def test_perfect_consistency(self):
        # Cronbach's alpha measures internal consistency across raters.
        # Each rater should have different scores but consistent patterns.
        # Raters are columns, items are rows.
        ratings = [[1, 2], [2, 3], [3, 4], [4, 5], [5, 6]]
        result = cronbachs_alpha(ratings)
        assert result["alpha"] > 0.99
        assert result["interpretation"] == "excellent"

    def test_empty_matrix_error(self):
        result = cronbachs_alpha([])
        assert "error" in result

    def test_single_rater_error(self):
        result = cronbachs_alpha([[1], [2], [3]])
        assert "error" in result

    def test_zero_total_variance(self):
        # All same values
        ratings = [[3, 3], [3, 3], [3, 3]]
        result = cronbachs_alpha(ratings)
        assert result["alpha"] == 0.0

    def test_result_keys(self):
        ratings = [[1, 2], [3, 4], [5, 5]]
        result = cronbachs_alpha(ratings)
        assert "alpha" in result
        assert "interpretation" in result
        assert "n_items" in result
        assert "n_raters" in result


# ---------------------------------------------------------------------------
# krippendorff_alpha
# ---------------------------------------------------------------------------

class TestKrippendorffAlpha:

    def test_perfect_nominal_agreement(self):
        ratings = [["A", "A"], ["B", "B"], ["C", "C"]]
        result = krippendorff_alpha(ratings, level_of_measurement="nominal")
        assert result["alpha"] == 1.0
        assert result["interpretation"] == "good reliability"

    def test_empty_matrix_error(self):
        result = krippendorff_alpha([])
        assert "error" in result

    def test_too_few_ratings_error(self):
        result = krippendorff_alpha([[None, None], [None, None]])
        assert "error" in result

    def test_interval_measurement(self):
        ratings = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
        result = krippendorff_alpha(ratings, level_of_measurement="interval")
        assert result["alpha"] > 0.99

    def test_with_missing_data(self):
        ratings = [["A", "A"], ["B", None], ["C", "C"]]
        result = krippendorff_alpha(ratings, level_of_measurement="nominal")
        assert "alpha" in result

    def test_ordinal_measurement(self):
        ratings = [[1, 1], [2, 2], [3, 3]]
        result = krippendorff_alpha(ratings, level_of_measurement="ordinal")
        assert result["alpha"] > 0.99

    def test_ratio_measurement(self):
        ratings = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
        result = krippendorff_alpha(ratings, level_of_measurement="ratio")
        assert result["alpha"] > 0.99

    def test_result_keys(self):
        ratings = [[1, 2], [2, 1], [1, 1]]
        result = krippendorff_alpha(ratings)
        assert "alpha" in result
        assert "observed_disagreement" in result
        assert "expected_disagreement" in result
        assert "level_of_measurement" in result


# ---------------------------------------------------------------------------
# percent_agreement
# ---------------------------------------------------------------------------

class TestPercentAgreement:

    def test_full_agreement(self):
        ratings = [["A", "A"], ["B", "B"], ["C", "C"]]
        result = percent_agreement(ratings)
        assert result["percent_agreement"] == 1.0
        assert result["interpretation"] == "excellent"

    def test_no_agreement(self):
        ratings = [["A", "B"], ["B", "A"], ["A", "B"]]
        result = percent_agreement(ratings)
        assert result["percent_agreement"] == 0.0

    def test_partial_agreement(self):
        ratings = [["A", "A"], ["B", "A"], ["C", "C"], ["D", "C"]]
        result = percent_agreement(ratings)
        assert result["percent_agreement"] == 0.5

    def test_empty_ratings_error(self):
        result = percent_agreement([])
        assert "error" in result

    def test_single_rater_items_skipped(self):
        ratings = [["A"], ["B", "B"]]
        result = percent_agreement(ratings)
        assert result["total_items"] == 1

    def test_interpretation_levels(self):
        # 80% agreement => good
        ratings = [["A", "A"], ["B", "B"], ["C", "C"], ["D", "D"], ["E", "F"]]
        result = percent_agreement(ratings)
        assert result["percent_agreement"] == 0.8
        assert result["interpretation"] == "good"


# ---------------------------------------------------------------------------
# intraclass_correlation
# ---------------------------------------------------------------------------

class TestIntraclassCorrelation:

    def test_perfect_icc(self):
        ratings = [[1, 1], [2, 2], [3, 3], [4, 4], [5, 5]]
        result = intraclass_correlation(ratings)
        assert result["icc"] > 0.99
        assert result["interpretation"] == "excellent"

    def test_empty_matrix_error(self):
        result = intraclass_correlation([])
        assert "error" in result

    def test_single_rater_error(self):
        result = intraclass_correlation([[1], [2], [3]])
        assert "error" in result

    def test_icc_types(self):
        ratings = [[1, 2], [3, 4], [5, 5], [2, 3]]
        for icc_type in ["ICC(1,1)", "ICC(2,1)", "ICC(3,1)"]:
            result = intraclass_correlation(ratings, icc_type=icc_type)
            assert "icc" in result
            assert result["icc_type"] == icc_type

    def test_unknown_icc_type_error(self):
        result = intraclass_correlation([[1, 2]], icc_type="ICC(99,99)")
        assert "error" in result


# ---------------------------------------------------------------------------
# _span_iou
# ---------------------------------------------------------------------------

class TestSpanIoU:

    def test_exact_overlap(self):
        assert _span_iou({"start": 0, "end": 10}, {"start": 0, "end": 10}) == 1.0

    def test_no_overlap(self):
        assert _span_iou({"start": 0, "end": 5}, {"start": 10, "end": 15}) == 0.0

    def test_partial_overlap(self):
        iou = _span_iou({"start": 0, "end": 10}, {"start": 5, "end": 15})
        # Intersection: 5-10 = 5, Union: 0-15 = 15, IoU = 5/15 = 0.333
        assert abs(iou - 1/3) < 1e-6

    def test_contained_span(self):
        iou = _span_iou({"start": 2, "end": 8}, {"start": 0, "end": 10})
        # Intersection: 2-8 = 6, Union: 0-10 = 10, IoU = 6/10 = 0.6
        assert abs(iou - 0.6) < 1e-6

    def test_zero_length_spans(self):
        result = _span_iou({"start": 0, "end": 0}, {"start": 0, "end": 0})
        assert result == 1.0  # Both empty at same position


# ---------------------------------------------------------------------------
# _match_spans
# ---------------------------------------------------------------------------

class TestMatchSpans:

    def test_exact_match(self):
        spans1 = [{"start": 0, "end": 10}]
        spans2 = [{"start": 0, "end": 10}]
        matches = _match_spans(spans1, spans2)
        assert len(matches) == 1
        assert matches[0][2] == 1.0  # Perfect IoU

    def test_no_match_below_threshold(self):
        spans1 = [{"start": 0, "end": 5}]
        spans2 = [{"start": 100, "end": 105}]
        matches = _match_spans(spans1, spans2)
        assert len(matches) == 0

    def test_custom_threshold(self):
        spans1 = [{"start": 0, "end": 10}]
        spans2 = [{"start": 5, "end": 15}]
        # IoU = 5/15 = 0.333
        matches = _match_spans(spans1, spans2, iou_threshold=0.3)
        assert len(matches) == 1

    def test_one_to_one_matching(self):
        """Each span in spans2 can only be matched once."""
        spans1 = [{"start": 0, "end": 10}, {"start": 0, "end": 10}]
        spans2 = [{"start": 0, "end": 10}]
        matches = _match_spans(spans1, spans2)
        assert len(matches) == 1

    def test_empty_spans(self):
        assert _match_spans([], [{"start": 0, "end": 10}]) == []
        assert _match_spans([{"start": 0, "end": 10}], []) == []


# ---------------------------------------------------------------------------
# span_agreement
# ---------------------------------------------------------------------------

class TestSpanAgreement:

    def test_perfect_span_agreement(self):
        annotations = [
            [
                [{"start": 0, "end": 5, "labels": ["PER"]}],
                [{"start": 0, "end": 5, "labels": ["PER"]}],
            ]
        ]
        result = span_agreement(annotations)
        assert result["span_agreement"] > 0.9
        assert result["avg_iou"] > 0.9

    def test_no_annotations_error(self):
        result = span_agreement([])
        assert "error" in result

    def test_single_annotator_error(self):
        result = span_agreement([[[{"start": 0, "end": 5}]]])
        assert "error" in result

    def test_label_agreement(self):
        annotations = [
            [
                [{"start": 0, "end": 10, "labels": ["PER"]}],
                [{"start": 0, "end": 10, "labels": ["PER"]}],
            ]
        ]
        result = span_agreement(annotations, include_labels=True)
        assert "label_agreement" in result
        assert result["label_agreement"] == 1.0

    def test_label_disagreement(self):
        annotations = [
            [
                [{"start": 0, "end": 10, "labels": ["PER"]}],
                [{"start": 0, "end": 10, "labels": ["ORG"]}],
            ]
        ]
        result = span_agreement(annotations, include_labels=True)
        assert result["label_agreement"] == 0.0


# ---------------------------------------------------------------------------
# span_boundary_agreement
# ---------------------------------------------------------------------------

class TestSpanBoundaryAgreement:

    def test_perfect_boundary(self):
        annotations = [
            [
                [{"start": 0, "end": 10}],
                [{"start": 0, "end": 10}],
            ]
        ]
        result = span_boundary_agreement(annotations)
        assert result["boundary_agreement"] == 1.0

    def test_no_annotations_error(self):
        result = span_boundary_agreement([])
        assert "error" in result

    def test_with_tolerance(self):
        annotations = [
            [
                [{"start": 0, "end": 10}],
                [{"start": 1, "end": 11}],
            ]
        ]
        result_strict = span_boundary_agreement(annotations, tolerance=0)
        result_tolerant = span_boundary_agreement(annotations, tolerance=1)
        # With tolerance=1, boundaries are within tolerance
        if "boundary_agreement" in result_tolerant:
            assert result_tolerant["boundary_agreement"] >= result_strict.get("boundary_agreement", 0)


# ---------------------------------------------------------------------------
# compute_all_iaa_metrics
# ---------------------------------------------------------------------------

class TestComputeAllIAAMetrics:

    def test_nominal_level(self):
        ratings = [["A", "A"], ["B", "B"], ["A", "B"]]
        result = compute_all_iaa_metrics(ratings, level_of_measurement="nominal")
        assert "percent_agreement" in result["metrics"]
        assert "fleiss_kappa" in result["metrics"]
        assert "krippendorff_alpha" in result["metrics"]
        assert "cohens_kappa" in result["metrics"]  # 2 raters

    def test_ordinal_level(self):
        ratings = [[1, 1], [2, 2], [3, 3], [4, 3]]
        result = compute_all_iaa_metrics(ratings, level_of_measurement="ordinal")
        assert "percent_agreement" in result["metrics"]
        assert "cronbachs_alpha" in result["metrics"]
        assert "icc" in result["metrics"]

    def test_interval_level(self):
        ratings = [[1.0, 1.1], [2.0, 2.1], [3.0, 3.1]]
        result = compute_all_iaa_metrics(ratings, level_of_measurement="interval")
        assert "cronbachs_alpha" in result["metrics"]
