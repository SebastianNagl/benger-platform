"""
Tests for Span/Sequence Metrics (IoU, Partial Match, Boundary Accuracy).

Scientific Rigor: All tests verify mathematical correctness with known expected values.
NO MOCKS - All metrics use real implementations.

Used for Named Entity Recognition, text highlighting, and sequence labeling.
"""

import os
import sys

# Add path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSpanExactMatch:
    """Test exact span matching accuracy."""

    def test_span_exact_match_perfect(self):
        """Test span exact match = 1.0 for identical spans."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 0, "end": 10}
        pred = {"start": 0, "end": 10}

        score = evaluator._compute_span_metric("exact_match", gt, pred)
        assert score == 1.0, f"Identical spans should match exactly, got {score}"

    def test_span_exact_match_off_by_one(self):
        """Test span exact match = 0.0 for off-by-one spans."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 0, "end": 10}
        pred = {"start": 0, "end": 11}  # Off by one

        score = evaluator._compute_span_metric("exact_match", gt, pred)
        assert score == 0.0, f"Off-by-one should not match exactly, got {score}"

    def test_span_exact_match_no_overlap(self):
        """Test span exact match = 0.0 for non-overlapping spans."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 0, "end": 10}
        pred = {"start": 20, "end": 30}

        score = evaluator._compute_span_metric("exact_match", gt, pred)
        assert score == 0.0, f"Non-overlapping spans should have score 0, got {score}"


class TestIoU:
    """Test Intersection over Union (IoU) for spans.

    IoU = |intersection| / |union|

    Used in Named Entity Recognition and object detection.
    """

    def test_iou_perfect_overlap(self):
        """Test IoU = 1.0 for identical spans."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 0, "end": 10}
        pred = {"start": 0, "end": 10}

        score = evaluator._compute_span_metric("iou", gt, pred)
        assert score == 1.0, f"Identical spans should have IoU 1.0, got {score}"

    def test_iou_half_overlap(self):
        """Test IoU calculation for 50% overlap."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        # gt: [0, 10), pred: [5, 15)
        # intersection: [5, 10) = 5
        # union: [0, 15) = 15
        # IoU = 5/15 = 0.333
        gt = {"start": 0, "end": 10}
        pred = {"start": 5, "end": 15}

        score = evaluator._compute_span_metric("iou", gt, pred)
        assert abs(score - 0.333) < 0.01, f"50% overlap should have IoU ~0.333, got {score}"

    def test_iou_no_overlap(self):
        """Test IoU = 0.0 for non-overlapping spans."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 0, "end": 10}
        pred = {"start": 20, "end": 30}

        score = evaluator._compute_span_metric("iou", gt, pred)
        assert score == 0.0, f"No overlap should have IoU 0.0, got {score}"

    def test_iou_contained_span(self):
        """Test IoU for contained span (prediction inside ground truth)."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        # gt: [0, 20), pred: [5, 15)
        # intersection: [5, 15) = 10
        # union: [0, 20) = 20
        # IoU = 10/20 = 0.5
        gt = {"start": 0, "end": 20}
        pred = {"start": 5, "end": 15}

        score = evaluator._compute_span_metric("iou", gt, pred)
        assert abs(score - 0.5) < 0.01, f"Contained span should have IoU 0.5, got {score}"


class TestPartialMatch:
    """Test partial span matching with threshold.

    A match is considered successful if overlap exceeds a threshold.
    """

    def test_partial_match_above_threshold(self):
        """Test partial match returns high score for significant overlap."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        # gt: [0, 10), pred: [0, 8)
        # overlap = 8, gt_length = 10
        # overlap_ratio = 8/10 = 0.8
        gt = {"start": 0, "end": 10}
        pred = {"start": 0, "end": 8}

        score = evaluator._compute_partial_match(gt, pred)
        # With 80% overlap, score should be high
        assert score >= 0.7, f"High overlap should have score >= 0.7, got {score}"

    def test_partial_match_below_threshold(self):
        """Test partial match returns low score for minimal overlap."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        # gt: [0, 10), pred: [7, 12)
        # overlap = 3, gt_length = 10
        # overlap_ratio = 3/10 = 0.3
        gt = {"start": 0, "end": 10}
        pred = {"start": 7, "end": 12}

        score = evaluator._compute_partial_match(gt, pred)
        # With only 30% overlap, score should be low
        assert score <= 0.5, f"Low overlap should have score <= 0.5, got {score}"

    def test_partial_match_perfect_overlap(self):
        """Test partial match returns 1.0 for perfect overlap."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 0, "end": 10}
        pred = {"start": 0, "end": 10}

        score = evaluator._compute_partial_match(gt, pred)
        assert score == 1.0, f"Perfect overlap should have score 1.0, got {score}"


class TestBoundaryAccuracy:
    """Test boundary accuracy (start/end precision).

    Measures how close the predicted boundaries are to ground truth.
    """

    def test_boundary_accuracy_perfect(self):
        """Test boundary accuracy = 1.0 for exact boundaries."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 10, "end": 20}
        pred = {"start": 10, "end": 20}

        score = evaluator._compute_boundary_accuracy(gt, pred)
        assert score == 1.0, f"Exact boundaries should have accuracy 1.0, got {score}"

    def test_boundary_accuracy_off_by_one_start(self):
        """Test boundary accuracy for off-by-one start."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 10, "end": 20}
        pred = {"start": 11, "end": 20}  # Start off by 1

        score = evaluator._compute_boundary_accuracy(gt, pred)
        # Half correct (end is correct, start is off)
        assert 0.4 < score < 0.6, f"One boundary off should have ~0.5 accuracy, got {score}"

    def test_boundary_accuracy_both_off(self):
        """Test boundary accuracy for both boundaries off."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 10, "end": 20}
        pred = {"start": 11, "end": 21}  # Both off by 1

        score = evaluator._compute_boundary_accuracy(gt, pred)
        assert score < 1.0, f"Both boundaries off should reduce accuracy, got {score}"

    def test_boundary_accuracy_with_tolerance(self):
        """Test boundary accuracy with tolerance parameter."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = {"start": 10, "end": 20}
        pred = {"start": 11, "end": 20}  # Start off by 1

        # With tolerance of 1, should be considered exact match
        score = evaluator._compute_boundary_accuracy(gt, pred, {"tolerance": 1})
        assert score == 1.0, f"Within tolerance should be 1.0, got {score}"


class TestSpanMetricLists:
    """Test span metrics with list inputs (multiple spans)."""

    def test_span_list_exact_match(self):
        """Test span exact match for lists of spans."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = [{"start": 0, "end": 5}, {"start": 10, "end": 15}]
        pred = [{"start": 0, "end": 5}, {"start": 10, "end": 15}]

        score = evaluator._compute_span_metric("exact_match", gt, pred)
        assert score == 1.0, f"Identical span lists should match exactly, got {score}"

    def test_span_list_partial_overlap(self):
        """Test span metrics for partially matching span lists."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

        gt = [{"start": 0, "end": 5}, {"start": 10, "end": 15}]
        pred = [{"start": 0, "end": 5}]  # Missing second span

        score = evaluator._compute_span_metric("exact_match", gt, pred)
        # Only 1 out of 2 spans matched
        assert score < 1.0, f"Missing span should reduce score, got {score}"


class TestIoUCalculation:
    """Direct tests for IoU calculation with various edge cases."""

    def test_iou_calculation_basic(self):
        """Test basic IoU calculation formula."""

        def calculate_iou(span1, span2):
            """Calculate IoU for two spans."""
            start1, end1 = span1["start"], span1["end"]
            start2, end2 = span2["start"], span2["end"]

            # Intersection
            inter_start = max(start1, start2)
            inter_end = min(end1, end2)
            intersection = max(0, inter_end - inter_start)

            # Union
            union = (end1 - start1) + (end2 - start2) - intersection

            if union == 0:
                return 0.0

            return intersection / union

        # Test case 1: Perfect overlap
        assert calculate_iou({"start": 0, "end": 10}, {"start": 0, "end": 10}) == 1.0

        # Test case 2: No overlap
        assert calculate_iou({"start": 0, "end": 10}, {"start": 20, "end": 30}) == 0.0

        # Test case 3: Partial overlap
        # [0, 10) and [5, 15): intersection = [5, 10) = 5, union = 10 + 10 - 5 = 15
        iou = calculate_iou({"start": 0, "end": 10}, {"start": 5, "end": 15})
        assert abs(iou - 5 / 15) < 0.001


class TestSpanEmptyInputs:
    """Test span metrics with empty inputs."""

    def _make_evaluator(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator
        return SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

    def test_iou_both_empty(self):
        """Both empty -> 1.0 (perfect agreement on nothing)."""
        evaluator = self._make_evaluator()
        assert evaluator._compute_span_metric("iou", [], []) == 1.0

    def test_iou_gt_empty(self):
        """GT empty, pred non-empty -> 0.0."""
        evaluator = self._make_evaluator()
        assert evaluator._compute_span_metric("iou", [], [{"start": 0, "end": 5}]) == 0.0

    def test_iou_pred_empty(self):
        """GT non-empty, pred empty -> 0.0."""
        evaluator = self._make_evaluator()
        assert evaluator._compute_span_metric("iou", [{"start": 0, "end": 5}], []) == 0.0

    def test_exact_match_both_empty(self):
        """Both empty -> 1.0."""
        evaluator = self._make_evaluator()
        assert evaluator._compute_span_metric("exact_match", [], []) == 1.0

    def test_partial_match_both_empty(self):
        """Both empty -> 1.0."""
        evaluator = self._make_evaluator()
        assert evaluator._compute_partial_match([], []) == 1.0

    def test_partial_match_gt_empty(self):
        """GT empty, pred non-empty -> 0.0."""
        evaluator = self._make_evaluator()
        assert evaluator._compute_partial_match([], [{"start": 0, "end": 5}]) == 0.0

    def test_boundary_accuracy_both_empty(self):
        """Both empty -> 1.0."""
        evaluator = self._make_evaluator()
        assert evaluator._compute_boundary_accuracy([], []) == 1.0


class TestSpanLabelAware:
    """Test that span metrics respect entity labels."""

    def _make_evaluator(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator
        return SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

    def test_iou_same_position_different_labels(self):
        """Same position but different labels should score 0.0 for IoU."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10, "labels": ["PERSON"]}]
        pred = [{"start": 0, "end": 10, "labels": ["ORGANIZATION"]}]
        score = evaluator._compute_span_metric("iou", gt, pred)
        assert score == 0.0, f"Different labels at same position should score 0, got {score}"

    def test_iou_same_position_same_labels(self):
        """Same position and same labels should score 1.0."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10, "labels": ["PERSON"]}]
        pred = [{"start": 0, "end": 10, "labels": ["PERSON"]}]
        score = evaluator._compute_span_metric("iou", gt, pred)
        assert score == 1.0, f"Same labels at same position should score 1.0, got {score}"

    def test_iou_no_labels_position_only(self):
        """No labels -> fall back to position-only matching (backwards compatible)."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 10}]
        score = evaluator._compute_span_metric("iou", gt, pred)
        assert score == 1.0, f"Position-only matching should work, got {score}"

    def test_exact_match_different_labels(self):
        """Exact match should fail if labels differ."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10, "labels": ["PERSON"]}]
        pred = [{"start": 0, "end": 10, "labels": ["ORG"]}]
        score = evaluator._compute_span_metric("exact_match", gt, pred)
        assert score == 0.0, f"Different labels should not match exactly, got {score}"

    def test_partial_match_different_labels(self):
        """Partial match should return 0 if labels are incompatible."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10, "labels": ["PERSON"]}]
        pred = [{"start": 0, "end": 10, "labels": ["ORGANIZATION"]}]
        score = evaluator._compute_partial_match(gt, pred)
        assert score == 0.0, f"Incompatible labels should score 0, got {score}"

    def test_boundary_accuracy_different_labels(self):
        """Boundary accuracy should return 0 if labels are incompatible."""
        evaluator = self._make_evaluator()
        gt = [{"start": 10, "end": 20, "labels": ["DATE"]}]
        pred = [{"start": 10, "end": 20, "labels": ["LOC"]}]
        score = evaluator._compute_boundary_accuracy(gt, pred)
        assert score == 0.0, f"Incompatible labels should score 0, got {score}"

    def test_multi_span_label_matching(self):
        """Multiple spans with mixed labels should only match compatible ones."""
        evaluator = self._make_evaluator()
        gt = [
            {"start": 0, "end": 10, "labels": ["PERSON"]},
            {"start": 20, "end": 30, "labels": ["ORG"]},
        ]
        pred = [
            {"start": 0, "end": 10, "labels": ["PERSON"]},  # Matches GT[0]
            {"start": 20, "end": 30, "labels": ["DATE"]},   # Does NOT match GT[1]
        ]
        score = evaluator._compute_span_metric("iou", gt, pred)
        # Only 1 of 2 GT spans matched (IoU 1.0 for match, 0.0 for mismatch)
        # total_iou = 1.0, max(len(gt), len(pred)) = 2
        assert abs(score - 0.5) < 0.01, f"Half matching should score ~0.5, got {score}"

    def test_parse_spans_preserves_labels(self):
        """_parse_spans should preserve labels when present."""
        evaluator = self._make_evaluator()
        spans = evaluator._parse_spans([
            {"start": 0, "end": 10, "labels": ["PERSON"]},
            {"start": 20, "end": 30, "label": "ORG"},
        ])
        assert len(spans) == 2
        assert spans[0]["labels"] == ["PERSON"]
        assert spans[1]["labels"] == ["ORG"]

    def test_parse_spans_without_labels(self):
        """_parse_spans should work without labels (backwards compatible)."""
        evaluator = self._make_evaluator()
        spans = evaluator._parse_spans([{"start": 0, "end": 10}])
        assert len(spans) == 1
        assert "labels" not in spans[0]


class TestSpanHungarianMatching:
    """Test that optimal bipartite matching gives correct results.

    The Hungarian algorithm should produce better results than greedy
    when span counts differ or when greedy assignment is suboptimal.
    """

    def _make_evaluator(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator
        return SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

    def test_hungarian_vs_greedy_scenario(self):
        """Scenario where greedy matching gives suboptimal result.

        GT:   [0,10) [10,20)
        Pred: [0,20) [10,20)

        Greedy (GT[0] first): GT[0] best-matches Pred[0] (IoU=10/20=0.5),
                               GT[1] best-matches Pred[1] (IoU=1.0)
                               Total = 1.5/2 = 0.75

        But also greedy could match GT[0]->Pred[0] and GT[1]->Pred[1], same result.

        With Hungarian: GT[0]->Pred[0] (0.5), GT[1]->Pred[1] (1.0) = 1.5/2 = 0.75
        OR: GT[0]->Pred[1] (0.0 - no overlap), GT[1]->Pred[0] (0.5) = 0.5/2 = 0.25

        Hungarian should pick the optimal: 0.75
        """
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10}, {"start": 10, "end": 20}]
        pred = [{"start": 0, "end": 20}, {"start": 10, "end": 20}]
        score = evaluator._compute_span_metric("iou", gt, pred)
        assert abs(score - 0.75) < 0.01, f"Expected 0.75, got {score}"

    def test_more_predictions_than_gt(self):
        """Extra predictions should reduce score via denominator."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 10}, {"start": 20, "end": 30}]  # Extra unmatched pred
        score = evaluator._compute_span_metric("iou", gt, pred)
        # IoU for matched pair = 1.0, max(1, 2) = 2, so score = 0.5
        assert abs(score - 0.5) < 0.01, f"Extra pred should reduce score, got {score}"

    def test_more_gt_than_predictions(self):
        """Missing predictions should reduce score via denominator."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10}, {"start": 20, "end": 30}]
        pred = [{"start": 0, "end": 10}]  # Missing one prediction
        score = evaluator._compute_span_metric("iou", gt, pred)
        # IoU for matched pair = 1.0, max(2, 1) = 2, so score = 0.5
        assert abs(score - 0.5) < 0.01, f"Missing pred should reduce score, got {score}"

    def test_no_valid_matches(self):
        """No overlapping spans should score 0."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 50, "end": 60}]
        score = evaluator._compute_span_metric("iou", gt, pred)
        assert score == 0.0, f"No overlap should score 0, got {score}"


class TestSpanOverlapping:
    """Test span metrics with overlapping and nested spans."""

    def _make_evaluator(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator
        return SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

    def test_nested_spans_in_gt(self):
        """Nested spans (one inside another) should each match independently."""
        evaluator = self._make_evaluator()
        # GT has outer span [0,20) and inner span [5,15)
        gt = [{"start": 0, "end": 20}, {"start": 5, "end": 15}]
        pred = [{"start": 0, "end": 20}, {"start": 5, "end": 15}]
        score = evaluator._compute_span_metric("iou", gt, pred)
        assert score == 1.0, f"Matching nested spans should score 1.0, got {score}"

    def test_overlapping_spans_partial(self):
        """Overlapping GT spans matched against non-overlapping predictions."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 15}, {"start": 10, "end": 25}]
        pred = [{"start": 0, "end": 12}, {"start": 13, "end": 25}]
        score = evaluator._compute_span_metric("iou", gt, pred)
        # Should be > 0 (partial matches) but < 1 (not perfect)
        assert 0.0 < score < 1.0, f"Partial overlapping match expected between 0 and 1, got {score}"


class TestSpanConfigDefaults:
    """Contract tests: verify which metrics MUST be available for span evaluation.

    These validate the evaluator dispatches the expected span metrics correctly,
    independent of the API config module (which lives in a different service).
    """

    def _make_evaluator(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator
        return SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "span"}}
        )

    def test_iou_metric_is_dispatched(self):
        """IoU metric should be computable for span data."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 10}]
        # Should not fall through to default (which returns 0.0 for matching data)
        score = evaluator._compute_span_metric("iou", gt, pred)
        assert score == 1.0, f"IoU should be dispatched and return 1.0, got {score}"

    def test_span_exact_match_is_dispatched(self):
        """span_exact_match should be computable for span data."""
        evaluator = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 10}]
        score = evaluator._compute_span_metric("exact_match", gt, pred)
        assert score == 1.0, f"exact_match should be dispatched and return 1.0, got {score}"

    def test_token_f1_does_not_handle_span_data(self):
        """token_f1 stringifies JSON spans - it should NOT be used for span evaluation.

        This test documents the bug: token_f1 treats span dicts as text tokens,
        producing meaningless scores. It was removed from SPAN_SELECTION defaults.
        """
        evaluator = self._make_evaluator()
        # Identical span data
        gt = [{"start": 0, "end": 10, "labels": ["PERSON"]}]
        pred = [{"start": 0, "end": 10, "labels": ["PERSON"]}]
        # token_f1 stringifies and tokenizes: "{'start': 0, 'end': 10, ...}"
        # The string representations should match, but the score is fragile
        # and semantically meaningless for span evaluation
        score = evaluator._compute_token_f1(gt, pred)
        # We just verify it doesn't crash and document this is NOT a span metric
        assert isinstance(score, float)
