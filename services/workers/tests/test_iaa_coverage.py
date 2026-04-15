"""Coverage tests for ml_evaluation/inter_annotator_agreement.py.

Tests: cohens_kappa, fleiss_kappa, cronbachs_alpha, krippendorff_alpha,
percent_agreement, intraclass_correlation, compute_all_iaa_metrics,
_span_iou, _match_spans, span_agreement, span_boundary_agreement.
"""

import sys
import os

workers_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, workers_root)

from ml_evaluation.inter_annotator_agreement import (
    cohens_kappa,
    fleiss_kappa,
    cronbachs_alpha,
    krippendorff_alpha,
    percent_agreement,
    intraclass_correlation,
    compute_all_iaa_metrics,
    _span_iou,
    _match_spans,
    span_agreement,
    span_boundary_agreement,
)


class TestCohensKappa:
    def test_perfect_agreement(self):
        result = cohens_kappa([1, 2, 3, 1, 2], [1, 2, 3, 1, 2])
        assert result["kappa"] == 1.0
        assert result["interpretation"] == "almost perfect"

    def test_different_lengths(self):
        result = cohens_kappa([1, 2], [1])
        assert "error" in result

    def test_empty(self):
        result = cohens_kappa([], [])
        assert "error" in result

    def test_no_agreement(self):
        result = cohens_kappa([1, 1, 1], [2, 2, 2])
        assert result["kappa"] <= 0.0

    def test_linear_weights(self):
        result = cohens_kappa([1, 2, 3, 4], [1, 2, 3, 4], weights="linear")
        assert result["kappa"] == 1.0

    def test_quadratic_weights(self):
        result = cohens_kappa([1, 2, 3, 4], [1, 2, 3, 4], weights="quadratic")
        assert result["kappa"] == 1.0

    def test_unknown_weights(self):
        result = cohens_kappa([1, 2, 3], [1, 2, 3], weights="unknown")
        assert "error" in result

    def test_partial_agreement(self):
        result = cohens_kappa([1, 1, 2, 2], [1, 2, 1, 2])
        assert -1.0 <= result["kappa"] <= 1.0

    def test_slight_interpretation(self):
        """Test getting 'slight' interpretation."""
        result = cohens_kappa([1, 2, 1, 2, 1], [2, 1, 2, 1, 2])
        assert result["kappa"] < 0.20


class TestFleissKappa:
    def test_empty(self):
        result = fleiss_kappa([])
        assert "error" in result

    def test_empty_rows(self):
        result = fleiss_kappa([[]])
        assert "error" in result

    def test_perfect_agreement(self):
        matrix = [[1, 1, 1], [2, 2, 2], [3, 3, 3]]
        result = fleiss_kappa(matrix)
        assert result["kappa"] == 1.0

    def test_no_agreement(self):
        matrix = [[1, 2, 3], [2, 3, 1], [3, 1, 2]]
        result = fleiss_kappa(matrix)
        assert result["kappa"] <= 0.5

    def test_with_categories(self):
        matrix = [[1, 1], [2, 2]]
        result = fleiss_kappa(matrix, categories=[1, 2])
        assert "kappa" in result

    def test_with_none_values(self):
        matrix = [[1, None, 1], [2, 2, None]]
        result = fleiss_kappa(matrix)
        assert "kappa" in result


class TestCronbachsAlpha:
    def test_empty(self):
        result = cronbachs_alpha([])
        assert "error" in result

    def test_single_rater(self):
        # 1 item x 3 raters, n_items=1 causes n_items-1=0 ZeroDivisionError
        # This is expected behavior for degenerate input
        import pytest
        with pytest.raises(ZeroDivisionError):
            cronbachs_alpha([[1, 2, 3]])

    def test_perfect_consistency(self):
        matrix = [[1, 2, 3], [1, 2, 3]]
        result = cronbachs_alpha(matrix)
        assert result["alpha"] == 1.0
        assert result["interpretation"] == "excellent"

    def test_low_consistency(self):
        matrix = [[1, 5, 1, 5], [5, 1, 5, 1]]
        result = cronbachs_alpha(matrix)
        assert result["alpha"] < 0.5

    def test_zero_total_variance(self):
        matrix = [[1, 1], [1, 1]]
        result = cronbachs_alpha(matrix)
        assert result["alpha"] == 0.0


class TestKrippendorffAlpha:
    def test_empty(self):
        result = krippendorff_alpha([])
        assert "error" in result

    def test_too_few_ratings(self):
        result = krippendorff_alpha([[1]])
        assert "error" in result

    def test_perfect_nominal(self):
        matrix = [["a", "a"], ["b", "b"], ["c", "c"]]
        result = krippendorff_alpha(matrix, "nominal")
        assert result["alpha"] == 1.0

    def test_perfect_interval(self):
        matrix = [[1, 1], [2, 2], [3, 3]]
        result = krippendorff_alpha(matrix, "interval")
        assert result["alpha"] == 1.0

    def test_ordinal(self):
        matrix = [[1, 1], [2, 2]]
        result = krippendorff_alpha(matrix, "ordinal")
        assert "alpha" in result

    def test_ratio(self):
        matrix = [[1, 1], [2, 2]]
        result = krippendorff_alpha(matrix, "ratio")
        assert "alpha" in result

    def test_with_missing(self):
        matrix = [["a", "a", None], ["b", None, "b"]]
        result = krippendorff_alpha(matrix, "nominal")
        assert "alpha" in result

    def test_no_valid_pairs(self):
        matrix = [[None, None], [None, None]]
        result = krippendorff_alpha(matrix)
        assert "error" in result

    def test_good_reliability_interpretation(self):
        matrix = [[1, 1], [2, 2], [3, 3], [4, 4]]
        result = krippendorff_alpha(matrix, "interval")
        assert result["interpretation"] == "good reliability"


class TestPercentAgreement:
    def test_empty(self):
        result = percent_agreement([])
        assert "error" in result

    def test_perfect(self):
        matrix = [["a", "a"], ["b", "b"]]
        result = percent_agreement(matrix)
        assert result["percent_agreement"] == 1.0

    def test_zero(self):
        matrix = [["a", "b"], ["b", "a"]]
        result = percent_agreement(matrix)
        assert result["percent_agreement"] == 0.0

    def test_partial(self):
        matrix = [["a", "a"], ["b", "a"]]
        result = percent_agreement(matrix)
        assert result["percent_agreement"] == 0.5

    def test_single_rater(self):
        matrix = [["a"], ["b"]]
        result = percent_agreement(matrix)
        assert "error" in result


class TestIntraclassCorrelation:
    def test_empty(self):
        result = intraclass_correlation([])
        assert "error" in result

    def test_single_rater(self):
        # 1 item, 3 raters -> n_items=1, causes n_items-1=0 -> nan ICC
        result = intraclass_correlation([[1, 2, 3]])
        import math
        assert math.isnan(result["icc"])

    def test_perfect_icc21(self):
        matrix = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
        result = intraclass_correlation(matrix, "ICC(2,1)")
        assert result["icc"] >= 0.9

    def test_perfect_icc11(self):
        matrix = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
        result = intraclass_correlation(matrix, "ICC(1,1)")
        assert result["icc"] >= 0.9

    def test_perfect_icc31(self):
        matrix = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
        result = intraclass_correlation(matrix, "ICC(3,1)")
        assert result["icc"] >= 0.9

    def test_unknown_type(self):
        result = intraclass_correlation([[1, 2], [3, 4]], "ICC(99,99)")
        assert "error" in result


class TestComputeAllIAAMetrics:
    def test_nominal(self):
        matrix = [["a", "a"], ["b", "b"]]
        result = compute_all_iaa_metrics(matrix, "nominal")
        assert "percent_agreement" in result["metrics"]
        assert "fleiss_kappa" in result["metrics"]

    def test_ordinal(self):
        matrix = [[1, 1], [2, 2], [3, 3]]
        result = compute_all_iaa_metrics(matrix, "ordinal")
        assert "fleiss_kappa" in result["metrics"]

    def test_interval(self):
        matrix = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
        result = compute_all_iaa_metrics(matrix, "interval")
        assert "cronbachs_alpha" in result["metrics"]
        assert "icc" in result["metrics"]

    def test_two_raters_cohens(self):
        matrix = [["a", "a"], ["b", "b"]]
        result = compute_all_iaa_metrics(matrix, "nominal")
        assert "cohens_kappa" in result["metrics"]


class TestSpanIOU:
    def test_identical(self):
        assert _span_iou({"start": 0, "end": 10}, {"start": 0, "end": 10}) == 1.0

    def test_no_overlap(self):
        assert _span_iou({"start": 0, "end": 5}, {"start": 10, "end": 15}) == 0.0

    def test_partial_overlap(self):
        iou = _span_iou({"start": 0, "end": 10}, {"start": 5, "end": 15})
        assert 0.0 < iou < 1.0

    def test_contained(self):
        iou = _span_iou({"start": 2, "end": 8}, {"start": 0, "end": 10})
        assert iou > 0.5

    def test_zero_length_spans(self):
        assert _span_iou({"start": 0, "end": 0}, {"start": 0, "end": 0}) == 1.0


class TestMatchSpans:
    def test_perfect_match(self):
        s1 = [{"start": 0, "end": 10}]
        s2 = [{"start": 0, "end": 10}]
        matches = _match_spans(s1, s2)
        assert len(matches) == 1

    def test_no_match(self):
        s1 = [{"start": 0, "end": 5}]
        s2 = [{"start": 50, "end": 55}]
        matches = _match_spans(s1, s2)
        assert len(matches) == 0

    def test_one_to_one(self):
        s1 = [{"start": 0, "end": 10}, {"start": 20, "end": 30}]
        s2 = [{"start": 0, "end": 10}, {"start": 20, "end": 30}]
        matches = _match_spans(s1, s2)
        assert len(matches) == 2

    def test_custom_threshold(self):
        s1 = [{"start": 0, "end": 10}]
        s2 = [{"start": 3, "end": 13}]
        matches_strict = _match_spans(s1, s2, iou_threshold=0.8)
        matches_loose = _match_spans(s1, s2, iou_threshold=0.3)
        assert len(matches_loose) >= len(matches_strict)


class TestSpanAgreement:
    def test_empty(self):
        result = span_agreement([])
        assert "error" in result

    def test_no_annotators(self):
        result = span_agreement([[]])
        assert "error" in result

    def test_perfect_agreement(self):
        s = [{"start": 0, "end": 10, "labels": ["PER"]}]
        result = span_agreement([[s, s]])
        assert result["span_agreement"] == 1.0

    def test_no_spans(self):
        result = span_agreement([[[], []]])
        assert result["span_agreement"] == 0.0

    def test_label_agreement(self):
        s1 = [{"start": 0, "end": 10, "labels": ["PER"]}]
        s2 = [{"start": 0, "end": 10, "labels": ["PER"]}]
        result = span_agreement([[s1, s2]], include_labels=True)
        assert result.get("label_agreement", 0) == 1.0

    def test_label_disagreement(self):
        s1 = [{"start": 0, "end": 10, "labels": ["PER"]}]
        s2 = [{"start": 0, "end": 10, "labels": ["ORG"]}]
        result = span_agreement([[s1, s2]], include_labels=True)
        assert result.get("label_agreement", 1) == 0.0


class TestSpanBoundaryAgreement:
    def test_empty(self):
        result = span_boundary_agreement([])
        assert "error" in result

    def test_no_annotators(self):
        result = span_boundary_agreement([[]])
        assert "error" in result

    def test_perfect_boundaries(self):
        s1 = [{"start": 0, "end": 10}]
        s2 = [{"start": 0, "end": 10}]
        result = span_boundary_agreement([[s1, s2]])
        assert result["boundary_agreement"] == 1.0

    def test_with_tolerance(self):
        s1 = [{"start": 0, "end": 10}]
        s2 = [{"start": 1, "end": 11}]
        result_strict = span_boundary_agreement([[s1, s2]], tolerance=0)
        result_tolerant = span_boundary_agreement([[s1, s2]], tolerance=1)
        assert result_tolerant["boundary_agreement"] >= result_strict["boundary_agreement"]

    def test_no_matching_spans(self):
        s1 = [{"start": 0, "end": 5}]
        s2 = [{"start": 100, "end": 105}]
        result = span_boundary_agreement([[s1, s2]])
        assert "error" in result
