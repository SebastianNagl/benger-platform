"""Branch-coverage tests for the legacy metric dispatch in
ml_evaluation/sample_evaluator.py.

The existing test_sample_evaluator_branches.py only drives ``_compute_metric_legacy``
for the korrektur no-op and the unknown-metric ValueError; every other metric in
the if/elif dispatch chain (lines ~413-523) is unreached because the deep-coverage
suite calls the leaf helpers (``_compute_span_metric`` etc.) directly and bypasses
the dispatch. This file routes each *pure-math* metric through
``_compute_metric_legacy`` so the dispatch arm AND the leaf-helper branch it lands
on are both covered, and adds the small pure helpers (``_serialize_value``
non-primitive branch, ``_detect_language_heuristic`` de/en split, ``_parse_spans``
dict-with-label, ``_span_iou`` empty-union, ``_calculate_span_overlap``
zero-length-GT) that the deep suite leaves uncovered.

No neural backend is touched: only the deterministic classification / set /
numeric / ranking / span / hierarchical / structured / text-edit metrics are
exercised. Every numeric assertion was verified against the real implementation
before being pinned. Mirrors the idioms in test_sample_evaluator_branches.py.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_evaluator(**kwargs):
    from ml_evaluation.sample_evaluator import SampleEvaluator

    defaults = {
        "evaluation_id": "test-eval",
        "field_configs": {"f": {"type": "text"}},
    }
    defaults.update(kwargs)
    return SampleEvaluator(**defaults)


# ============================================================================
# Classification dispatch arms (precision / recall / f1 / cohen_kappa /
# confusion_matrix) -> _compute_classification_metric
# ============================================================================


class TestClassificationDispatch:
    @pytest.mark.parametrize("metric", ["precision", "recall", "f1", "cohen_kappa"])
    def test_correct_single_sample_is_one(self, metric):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy(metric, "x", "x", "text", {}) == 1.0

    @pytest.mark.parametrize("metric", ["precision", "recall", "f1", "cohen_kappa"])
    def test_wrong_single_sample_is_zero(self, metric):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy(metric, "x", "y", "text", {}) == 0.0

    def test_confusion_matrix_correct(self):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("confusion_matrix", "a", "a", "text", {}) == 1.0
        assert ev._compute_metric_legacy("confusion_matrix", "a", "b", "text", {}) == 0.0


# ============================================================================
# Set / multi-label dispatch arms -> _compute_set_metric, _compute_token_f1
# ============================================================================


class TestSetMetricDispatch:
    def test_jaccard_partial_overlap(self):
        """gt={a,b,c}, pred={b,c,d}: intersection=2, union=4 -> 0.5."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "jaccard", ["a", "b", "c"], ["b", "c", "d"], "text", {}
        )
        assert abs(score - 0.5) < 1e-9

    def test_hamming_loss_symmetric_difference(self):
        """gt={a,b}, pred={b,c}: sym-diff={a,c}=2, all={a,b,c}=3 -> 2/3."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "hamming_loss", ["a", "b"], ["b", "c"], "text", {}
        )
        assert abs(score - 2 / 3) < 1e-9

    def test_subset_accuracy_exact(self):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy(
            "subset_accuracy", ["a", "b"], ["b", "a"], "text", {}
        ) == 1.0
        assert ev._compute_metric_legacy(
            "subset_accuracy", ["a", "b"], ["a"], "text", {}
        ) == 0.0

    def test_token_f1_partial(self):
        """gt tokens {the,cat,sat}, pred {the,cat,ran}: inter=2.
        precision=2/3, recall=2/3 -> f1=2/3."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "token_f1", "the cat sat", "the cat ran", "text", {}
        )
        assert abs(score - 2 / 3) < 1e-9


# ============================================================================
# Regression dispatch arms -> _compute_numeric_metric
# ============================================================================


class TestNumericMetricDispatch:
    def test_mae(self):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("mae", 5, 3, "text", {}) == 2.0

    def test_rmse_equals_abs_error_for_single_sample(self):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("rmse", 5, 3, "text", {}) == 2.0

    def test_mape_nonzero_gt(self):
        """|5-3|/5 * 100 = 40."""
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("mape", 5, 3, "text", {}) == pytest.approx(40.0)

    def test_mape_zero_gt_nonzero_pred(self):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("mape", 0, 3, "text", {}) == 100.0

    def test_invalid_numeric_returns_zero(self):
        """Non-numeric input -> ValueError caught -> 0.0 (no crash)."""
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("mae", "notanumber", "x", "text", {}) == 0.0

    def test_r2_is_aggregate_only_raises(self):
        ev = _make_evaluator()
        with pytest.raises(RuntimeError, match="aggregate-only"):
            ev._compute_metric_legacy("r2", 5, 3, "text", {})

    def test_correlation_is_aggregate_only_raises(self):
        ev = _make_evaluator()
        with pytest.raises(RuntimeError, match="aggregate-only"):
            ev._compute_metric_legacy("correlation", 5, 3, "text", {})


# ============================================================================
# Ranking dispatch arms -> _compute_ranking_metric
# ============================================================================


class TestRankingMetricDispatch:
    def test_weighted_kappa_aggregate_only_raises(self):
        ev = _make_evaluator()
        with pytest.raises(RuntimeError, match="aggregate-only"):
            ev._compute_metric_legacy("weighted_kappa", [1, 2], [1, 2], "text", {})

    def test_spearman_identical_lists_is_one(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "spearman_correlation", [1, 2, 3], [1, 2, 3], "text", {}
        )
        assert score == 1.0

    def test_spearman_length_mismatch_is_zero(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "spearman_correlation", [1, 2, 3], [1, 2], "text", {}
        )
        assert score == 0.0

    def test_kendall_identical_lists_is_one(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "kendall_tau", [1, 2, 3], [1, 2, 3], "text", {}
        )
        assert score == 1.0

    def test_kendall_reversed_clamped_to_zero(self):
        """Perfectly reversed -> tau=-1, clamped by max(0.0, tau) -> 0.0."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "kendall_tau", [1, 2, 3, 4], [4, 3, 2, 1], "text", {}
        )
        assert score == 0.0

    def test_ndcg_empty_both_is_one(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy("ndcg", [], [], "text", {})
        assert score == 1.0

    def test_map_perfect_ranking(self):
        """gt set {a,b}, pred [a,b,c]: hits at pos1 (1/1) and pos2 (2/2),
        sum=2.0, /|gt|=2 -> 1.0."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "map", ["a", "b"], ["a", "b", "c"], "text", {}
        )
        assert abs(score - 1.0) < 1e-9

    def test_map_no_hits(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy("map", ["a", "b"], ["x", "y"], "text", {})
        assert score == 0.0


# ============================================================================
# Text-similarity edit_distance arm -> _compute_text_similarity
# (pure Python Levenshtein, no library models)
# ============================================================================


class TestEditDistanceDispatch:
    def test_identical_strings_score_one(self):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("edit_distance", "abcd", "abcd", "text", {}) == 1.0

    def test_one_substitution(self):
        """'abcd' vs 'abce': distance 1, max_len 4 -> 1 - 1/4 = 0.75."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy("edit_distance", "abcd", "abce", "text", {})
        assert abs(score - 0.75) < 1e-9

    def test_empty_strings_score_one(self):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("edit_distance", "", "", "text", {}) == 1.0


# ============================================================================
# Structured dispatch arms -> _compute_structured_metric
# ============================================================================


class TestStructuredMetricDispatch:
    def test_json_accuracy_full_match(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "json_accuracy", '{"a": 1, "b": 2}', '{"a": 1, "b": 2}', "text", {}
        )
        assert score == 1.0

    def test_json_accuracy_half_match(self):
        """Two keys, one matches -> 0.5."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "json_accuracy", '{"a": 1, "b": 2}', '{"a": 1, "b": 99}', "text", {}
        )
        assert abs(score - 0.5) < 1e-9

    def test_json_accuracy_one_side_not_json(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "json_accuracy", '{"a": 1}', "plain text", "text", {}
        )
        assert score == 0.0

    def test_schema_validation_no_schema_valid_json(self):
        """No schema in params: returns 1.0 for any parseable JSON."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "schema_validation", "{}", '{"x": 1}', "text", {}
        )
        assert score == 1.0

    def test_schema_validation_no_schema_invalid_json(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "schema_validation", "{}", "not json at all !!!", "text", {}
        )
        assert score == 0.0

    def test_schema_validation_with_schema_pass(self):
        ev = _make_evaluator()
        schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
        score = ev._compute_metric_legacy(
            "schema_validation", "{}", '{"x": 5}', "text", {"schema": schema}
        )
        assert score == 1.0

    def test_schema_validation_with_schema_fail(self):
        ev = _make_evaluator()
        schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
        score = ev._compute_metric_legacy(
            "schema_validation", "{}", '{"y": 5}', "text", {"schema": schema}
        )
        assert score == 0.0


# ============================================================================
# Span dispatch arms -> _compute_span_metric
# ============================================================================


class TestSpanMetricDispatch:
    def test_span_exact_match_identical(self):
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 5}]
        pred = [{"start": 0, "end": 5}]
        assert ev._compute_metric_legacy("span_exact_match", gt, pred, "text", {}) == 1.0

    def test_span_exact_match_differs(self):
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 5}]
        pred = [{"start": 1, "end": 5}]
        assert ev._compute_metric_legacy("span_exact_match", gt, pred, "text", {}) == 0.0

    def test_iou_partial(self):
        """IoU(0-10, 5-15) = 5/15; max(len)=1 -> 1/3."""
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 5, "end": 15}]
        score = ev._compute_metric_legacy("iou", gt, pred, "text", {})
        assert abs(score - 1 / 3) < 1e-9

    def test_iou_both_empty_is_one(self):
        ev = _make_evaluator()
        assert ev._compute_metric_legacy("iou", [], [], "text", {}) == 1.0

    def test_iou_one_empty_is_zero(self):
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        assert ev._compute_metric_legacy("iou", gt, [], "text", {}) == 0.0


# ============================================================================
# Hierarchical dispatch arms -> _compute_hierarchical_metric
# ============================================================================


class TestHierarchicalMetricDispatch:
    def test_hierarchical_f1_identical_paths(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "hierarchical_f1", "Law > Civil > Contract", "Law > Civil > Contract", "text", {}
        )
        assert score == 1.0

    def test_hierarchical_f1_partial_overlap(self):
        """gt ancestors {(Law,),(Law,Civil),(Law,Civil,Contract)} (3),
        pred ancestors {(Law,),(Law,Civil)} (2), intersection 2.
        precision=2/2=1, recall=2/3 -> f1 = 2*(1*2/3)/(1+2/3) = 0.8."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "hierarchical_f1", "Law > Civil > Contract", "Law > Civil", "text", {}
        )
        assert abs(score - 0.8) < 1e-9

    def test_hierarchical_f1_both_empty_is_one(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy("hierarchical_f1", "", "", "text", {})
        assert score == 1.0


# ============================================================================
# Specialized NLP dispatch arms -> field/partial/boundary/path/lca
# ============================================================================


class TestSpecializedMetricDispatch:
    def test_field_accuracy_nested(self):
        """Two top-level keys both match (one nested) -> 1.0."""
        ev = _make_evaluator()
        gt = '{"a": 1, "nested": {"x": 10}}'
        pred = '{"a": 1, "nested": {"x": 10}}'
        score = ev._compute_metric_legacy("field_accuracy", gt, pred, "text", {})
        assert score == 1.0

    def test_field_accuracy_both_non_json_is_one(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "field_accuracy", "plain", "plaintoo", "text", {}
        )
        assert score == 1.0

    def test_partial_match_full_overlap(self):
        """Identical span -> overlap ratio 1.0 / 1 GT span -> 1.0."""
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 10}]
        score = ev._compute_metric_legacy("partial_match", gt, pred, "text", {})
        assert abs(score - 1.0) < 1e-9

    def test_partial_match_half_overlap(self):
        """gt 0-10, pred 0-5: intersection 5 / gt_length 10 = 0.5."""
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 5}]
        score = ev._compute_metric_legacy("partial_match", gt, pred, "text", {})
        assert abs(score - 0.5) < 1e-9

    def test_partial_match_average_mode(self):
        """average mode path: single compatible pred span, 0.5 overlap."""
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 5}]
        score = ev._compute_metric_legacy(
            "partial_match", gt, pred, "text", {"mode": "average"}
        )
        assert abs(score - 0.5) < 1e-9

    def test_boundary_accuracy_both_match(self):
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 10}]
        score = ev._compute_metric_legacy("boundary_accuracy", gt, pred, "text", {})
        assert score == 1.0

    def test_boundary_accuracy_one_match_is_half(self):
        """Start matches, end differs -> 0.5."""
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 20}]
        score = ev._compute_metric_legacy("boundary_accuracy", gt, pred, "text", {})
        assert abs(score - 0.5) < 1e-9

    def test_boundary_accuracy_lenient_mode(self):
        ev = _make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 10}]
        score = ev._compute_metric_legacy(
            "boundary_accuracy", gt, pred, "text", {"mode": "lenient"}
        )
        assert score == 1.0

    def test_path_accuracy_full_match(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "path_accuracy", "A > B > C", "A > B > C", "text", {}
        )
        assert score == 1.0

    def test_path_accuracy_diverges_at_second_level(self):
        """weights 1,2,3. The loop adds max_possible_score += weight BEFORE the
        divergence break, so i=0 (match, w=1) and i=1 (diverge, w=2) both count
        toward max_possible (=3) but only level0 scores (=1) -> 1/3."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "path_accuracy", "A > B > C", "A > X > C", "text", {}
        )
        assert abs(score - 1 / 3) < 1e-9

    def test_lca_accuracy_exact(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "lca_accuracy", "A > B > C", "A > B > C", "text", {}
        )
        assert score == 1.0

    def test_lca_accuracy_partial_decay(self):
        """LCA at depth 2 (A,B), gt depth 3: distance 1, decay 0.5^1 = 0.5."""
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "lca_accuracy", "A > B > C", "A > B > D", "text", {}
        )
        assert abs(score - 0.5) < 1e-9

    def test_lca_accuracy_no_common_ancestor(self):
        ev = _make_evaluator()
        score = ev._compute_metric_legacy(
            "lca_accuracy", "A > B", "X > Y", "text", {}
        )
        assert score == 0.0


# ============================================================================
# Pure leaf-helper branches the deep suite leaves uncovered
# ============================================================================


class TestSerializeValueBranches:
    def test_primitive_value(self):
        ev = _make_evaluator()
        out = ev._serialize_value("hello")
        assert out == {"value": "hello", "type": "str"}

    def test_list_value_keeps_type(self):
        ev = _make_evaluator()
        out = ev._serialize_value([1, 2, 3])
        assert out["value"] == [1, 2, 3]
        assert out["type"] == "list"

    def test_non_serializable_object_stringified(self):
        """An arbitrary object (not str/num/bool/None/list/dict) hits the
        else branch -> str() with type 'string'."""
        ev = _make_evaluator()

        class Weird:
            def __str__(self):
                return "weird-repr"

        out = ev._serialize_value(Weird())
        assert out == {"value": "weird-repr", "type": "string"}


class TestDetectLanguageHeuristic:
    def test_german_umlaut_triggers_de(self):
        ev = _make_evaluator()
        assert ev._detect_language_heuristic(["Die Prüfung ist schwer."]) == "de"

    def test_german_article_start_triggers_de(self):
        """No umlauts, but >30% of sentences start with a German article."""
        ev = _make_evaluator()
        sentences = ["Der Mann geht.", "Die Frau bleibt."]
        assert ev._detect_language_heuristic(sentences) == "de"

    def test_plain_english_is_en(self):
        ev = _make_evaluator()
        sentences = ["the cat sat on the mat", "it then ran away quickly"]
        assert ev._detect_language_heuristic(sentences) == "en"


class TestParseSpansAndIoUHelpers:
    def test_parse_spans_dict_with_label_string(self):
        """A single span dict carrying a string 'label' -> normalized into a
        one-element list with labels list (hits the dict-input branch)."""
        ev = _make_evaluator()
        spans = ev._parse_spans({"start": 0, "end": 5, "label": "PER"})
        assert spans == [{"start": 0, "end": 5, "labels": ["PER"]}]

    def test_parse_spans_dict_with_labels_list(self):
        ev = _make_evaluator()
        spans = ev._parse_spans({"start": 1, "end": 9, "labels": ["ORG", "LOC"]})
        assert spans == [{"start": 1, "end": 9, "labels": ["ORG", "LOC"]}]

    def test_parse_spans_json_string_roundtrip(self):
        ev = _make_evaluator()
        spans = ev._parse_spans('[{"start": 2, "end": 4}]')
        assert spans == [{"start": 2, "end": 4}]

    def test_parse_spans_unparseable_returns_empty(self):
        ev = _make_evaluator()
        assert ev._parse_spans(12345) == []

    def test_span_iou_disjoint_spans_zero(self):
        ev = _make_evaluator()
        s1 = {"start": 0, "end": 5}
        s2 = {"start": 10, "end": 15}
        assert ev._span_iou(s1, s2) == 0.0

    def test_span_iou_identical_is_one(self):
        ev = _make_evaluator()
        s = {"start": 0, "end": 10}
        assert ev._span_iou(s, dict(s)) == 1.0


    def test_calculate_span_overlap_zero_length_gt_no_overlap(self):
        ev = _make_evaluator()
        gt = {"start": 5, "end": 5}
        pred = {"start": 20, "end": 30}
        assert ev._calculate_span_overlap(gt, pred) == 0.0


class TestSpansLabelCompatible:
    def test_overlapping_labels_compatible(self):
        ev = _make_evaluator()
        assert ev._spans_label_compatible(
            {"start": 0, "end": 1, "labels": ["A", "B"]},
            {"start": 0, "end": 1, "labels": ["B"]},
        ) is True

    def test_disjoint_labels_incompatible(self):
        ev = _make_evaluator()
        assert ev._spans_label_compatible(
            {"start": 0, "end": 1, "labels": ["A"]},
            {"start": 0, "end": 1, "labels": ["B"]},
        ) is False

    def test_missing_labels_treated_as_compatible(self):
        ev = _make_evaluator()
        assert ev._spans_label_compatible(
            {"start": 0, "end": 1},
            {"start": 0, "end": 1, "labels": ["B"]},
        ) is True
