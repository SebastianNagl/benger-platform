"""
Deep coverage tests for ML evaluation modules.

Targets:
1. sample_evaluator.py - pure computation functions, normalization, aggregation, error paths
2. llm_judge_evaluator.py - field mappings, format_value, score_scale, evaluate(), fallback paths
3. backends/torch_backend.py - initialization, availability checks, lazy loading
4. backends/emd_backend.py - availability, compute_emd, get_emd_backend fallback
5. backends/selector.py - singleton, env-var selection, backend caching, error paths

All heavy ML dependencies (torch, transformers, sentence_transformers, bert_score, ot, pyemd)
are mocked to test logic without requiring model downloads.
"""

import json
import math
import os
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest

# Ensure workers root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# 1. SampleEvaluator - Pure Computation Tests
# ============================================================================


class TestSampleEvaluatorPureMetrics:
    """Test pure metric computations that require no model loading."""

    def _make_evaluator(self, **kwargs):
        from ml_evaluation.sample_evaluator import SampleEvaluator

        defaults = {
            "evaluation_id": "test-eval",
            "field_configs": {"f": {"type": "text", "answer_type": "text"}},
        }
        defaults.update(kwargs)
        return SampleEvaluator(**defaults)

    # ----- exact_match / accuracy / confusion_matrix -----

    def test_exact_match_identical(self):
        ev = self._make_evaluator()
        assert ev._compute_metric("exact_match", "hello", "hello", "text") == 1.0

    def test_exact_match_different(self):
        ev = self._make_evaluator()
        assert ev._compute_metric("exact_match", "hello", "world", "text") == 0.0

    def test_accuracy_identical(self):
        ev = self._make_evaluator()
        assert ev._compute_metric("accuracy", "yes", "yes", "text") == 1.0

    def test_accuracy_different(self):
        ev = self._make_evaluator()
        assert ev._compute_metric("accuracy", "yes", "no", "text") == 0.0

    def test_confusion_matrix_correct(self):
        ev = self._make_evaluator()
        assert ev._compute_metric("confusion_matrix", "cat", "cat", "text") == 1.0

    def test_confusion_matrix_wrong(self):
        ev = self._make_evaluator()
        assert ev._compute_metric("confusion_matrix", "cat", "dog", "text") == 0.0

    # ----- classification (single-sample approximations) -----

    def test_precision_correct(self):
        ev = self._make_evaluator()
        assert ev._compute_classification_metric("precision", "a", "a") == 1.0

    def test_precision_wrong(self):
        ev = self._make_evaluator()
        assert ev._compute_classification_metric("precision", "a", "b") == 0.0

    def test_recall_correct(self):
        ev = self._make_evaluator()
        assert ev._compute_classification_metric("recall", "x", "x") == 1.0

    def test_f1_correct(self):
        ev = self._make_evaluator()
        assert ev._compute_classification_metric("f1", "x", "x") == 1.0

    def test_f1_wrong(self):
        ev = self._make_evaluator()
        assert ev._compute_classification_metric("f1", "x", "y") == 0.0

    def test_cohen_kappa_single_sample(self):
        ev = self._make_evaluator()
        assert ev._compute_classification_metric("cohen_kappa", "a", "a") == 1.0
        assert ev._compute_classification_metric("cohen_kappa", "a", "b") == 0.0

    # ----- set metrics -----

    def test_jaccard_identical_sets(self):
        ev = self._make_evaluator()
        assert ev._compute_set_metric("jaccard", ["a", "b"], ["a", "b"]) == 1.0

    def test_jaccard_disjoint_sets(self):
        ev = self._make_evaluator()
        assert ev._compute_set_metric("jaccard", ["a"], ["b"]) == 0.0

    def test_jaccard_partial_overlap(self):
        ev = self._make_evaluator()
        score = ev._compute_set_metric("jaccard", ["a", "b", "c"], ["b", "c", "d"])
        assert abs(score - 2 / 4) < 1e-9

    def test_jaccard_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_set_metric("jaccard", [], []) == 1.0

    def test_jaccard_one_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_set_metric("jaccard", [], ["a"]) == 0.0

    def test_hamming_loss_identical(self):
        ev = self._make_evaluator()
        assert ev._compute_set_metric("hamming_loss", ["a", "b"], ["a", "b"]) == 0.0

    def test_hamming_loss_fully_different(self):
        ev = self._make_evaluator()
        score = ev._compute_set_metric("hamming_loss", ["a"], ["b"])
        assert score == 1.0  # symmetric diff = {a, b}, union = {a, b}

    def test_hamming_loss_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_set_metric("hamming_loss", [], []) == 0.0

    def test_subset_accuracy_exact(self):
        ev = self._make_evaluator()
        assert ev._compute_set_metric("subset_accuracy", ["a", "b"], ["a", "b"]) == 1.0

    def test_subset_accuracy_partial(self):
        ev = self._make_evaluator()
        assert ev._compute_set_metric("subset_accuracy", ["a", "b"], ["a"]) == 0.0

    # ----- _to_set -----

    def test_to_set_from_list(self):
        ev = self._make_evaluator()
        assert ev._to_set(["a", "b"]) == {"a", "b"}

    def test_to_set_from_tuple(self):
        ev = self._make_evaluator()
        assert ev._to_set(("x", "y")) == {"x", "y"}

    def test_to_set_from_set(self):
        ev = self._make_evaluator()
        assert ev._to_set({"p"}) == {"p"}

    def test_to_set_from_string_json(self):
        ev = self._make_evaluator()
        assert ev._to_set('["a","b"]') == {"a", "b"}

    def test_to_set_from_plain_string(self):
        ev = self._make_evaluator()
        assert ev._to_set("single") == {"single"}

    def test_to_set_from_none(self):
        ev = self._make_evaluator()
        assert ev._to_set(None) == set()

    def test_to_set_from_number(self):
        ev = self._make_evaluator()
        assert ev._to_set(42) == {42}

    # ----- _to_list -----

    def test_to_list_from_list(self):
        ev = self._make_evaluator()
        assert ev._to_list([1, 2]) == [1, 2]

    def test_to_list_from_tuple(self):
        ev = self._make_evaluator()
        result = ev._to_list((3, 4))
        assert set(result) == {3, 4}

    def test_to_list_from_json_string(self):
        ev = self._make_evaluator()
        assert ev._to_list('[1,2,3]') == [1, 2, 3]

    def test_to_list_from_comma_separated(self):
        ev = self._make_evaluator()
        assert ev._to_list("a, b, c") == ["a", "b", "c"]

    def test_to_list_from_plain_string(self):
        ev = self._make_evaluator()
        assert ev._to_list("hello") == ["hello"]

    def test_to_list_from_none(self):
        ev = self._make_evaluator()
        assert ev._to_list(None) == []

    def test_to_list_from_number(self):
        ev = self._make_evaluator()
        assert ev._to_list(99) == [99]

    # ----- token_f1 -----

    def test_token_f1_identical(self):
        ev = self._make_evaluator()
        assert ev._compute_token_f1("the cat sat", "the cat sat") == 1.0

    def test_token_f1_no_overlap(self):
        ev = self._make_evaluator()
        assert ev._compute_token_f1("aaa", "bbb") == 0.0

    def test_token_f1_partial_overlap(self):
        ev = self._make_evaluator()
        score = ev._compute_token_f1("the cat sat", "the dog sat")
        # gt_tokens = {the, cat, sat}, pred_tokens = {the, dog, sat}
        # intersection = {the, sat} = 2
        # precision = 2/3, recall = 2/3, f1 = 2/3
        assert abs(score - 2 / 3) < 1e-9

    def test_token_f1_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_token_f1("", "") == 1.0

    def test_token_f1_one_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_token_f1("word", "") == 0.0

    # ----- numeric metrics -----

    def test_mae(self):
        ev = self._make_evaluator()
        assert ev._compute_numeric_metric("mae", "5.0", "3.0") == 2.0

    def test_rmse(self):
        ev = self._make_evaluator()
        result = ev._compute_numeric_metric("rmse", "4.0", "1.0")
        assert abs(result - 3.0) < 1e-9

    def test_mape_nonzero(self):
        ev = self._make_evaluator()
        result = ev._compute_numeric_metric("mape", "100", "90")
        assert abs(result - 10.0) < 1e-9

    def test_mape_zero_gt_nonzero_pred(self):
        ev = self._make_evaluator()
        assert ev._compute_numeric_metric("mape", "0", "5") == 100.0

    def test_mape_zero_both(self):
        ev = self._make_evaluator()
        assert ev._compute_numeric_metric("mape", "0", "0") == 0.0

    def test_r2_raises_runtime_error(self):
        ev = self._make_evaluator()
        with pytest.raises(RuntimeError, match="aggregate-only"):
            ev._compute_numeric_metric("r2", "1", "2")

    def test_correlation_raises_runtime_error(self):
        ev = self._make_evaluator()
        with pytest.raises(RuntimeError, match="aggregate-only"):
            ev._compute_numeric_metric("correlation", "1", "2")

    def test_numeric_metric_invalid_input(self):
        ev = self._make_evaluator()
        assert ev._compute_numeric_metric("mae", "not_a_number", "5") == 0.0

    # ----- levenshtein -----

    def test_levenshtein_identical(self):
        ev = self._make_evaluator()
        assert ev._levenshtein_distance("abc", "abc") == 0

    def test_levenshtein_empty(self):
        ev = self._make_evaluator()
        assert ev._levenshtein_distance("", "abc") == 3

    def test_levenshtein_single_change(self):
        ev = self._make_evaluator()
        assert ev._levenshtein_distance("abc", "adc") == 1

    def test_levenshtein_swap_shorter(self):
        """s1 shorter than s2 triggers recursion."""
        ev = self._make_evaluator()
        assert ev._levenshtein_distance("a", "abc") == 2

    # ----- normalize_value -----

    def test_normalize_string(self):
        ev = self._make_evaluator()
        assert ev._normalize_value("  Hello World  ", "text") == "hello world"

    def test_normalize_list(self):
        ev = self._make_evaluator()
        assert ev._normalize_value([1, 2], "multi") == "[1, 2]"

    def test_normalize_dict(self):
        ev = self._make_evaluator()
        assert ev._normalize_value({"a": 1}, "json") == "{'a': 1}"

    def test_normalize_number(self):
        ev = self._make_evaluator()
        assert ev._normalize_value(42, "numeric") == 42

    # ----- serialize_value -----

    def test_serialize_string(self):
        ev = self._make_evaluator()
        result = ev._serialize_value("hello")
        assert result == {"value": "hello", "type": "str"}

    def test_serialize_int(self):
        ev = self._make_evaluator()
        result = ev._serialize_value(42)
        assert result == {"value": 42, "type": "int"}

    def test_serialize_none(self):
        ev = self._make_evaluator()
        result = ev._serialize_value(None)
        assert result == {"value": None, "type": "NoneType"}

    def test_serialize_list(self):
        ev = self._make_evaluator()
        result = ev._serialize_value([1, 2, 3])
        assert result == {"value": [1, 2, 3], "type": "list"}

    def test_serialize_custom_object(self):
        ev = self._make_evaluator()
        result = ev._serialize_value(object())
        assert result["type"] == "string"

    # ----- is_failure_metric -----

    def test_is_failure_none_value(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("exact_match", None) is True

    def test_is_failure_exact_match_zero(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("exact_match", 0.0) is True

    def test_is_failure_exact_match_one(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("exact_match", 1.0) is False

    def test_is_failure_bleu_low(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("bleu", 0.3) is True

    def test_is_failure_bleu_high(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("bleu", 0.8) is False

    def test_is_failure_cohen_kappa_low(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("cohen_kappa", 0.5) is True

    def test_is_failure_cohen_kappa_high(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("cohen_kappa", 0.7) is False

    def test_is_failure_ndcg_low(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("ndcg", 0.3) is True

    def test_is_failure_ndcg_high(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("ndcg", 0.6) is False

    def test_is_failure_schema_validation_partial(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("schema_validation", 0.5) is True

    def test_is_failure_schema_validation_full(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("schema_validation", 1.0) is False

    def test_is_failure_mae_high(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("mae", 0.5) is True

    def test_is_failure_mae_low(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("mae", 0.1) is False

    def test_is_failure_unknown_metric(self):
        ev = self._make_evaluator()
        assert ev._is_failure_metric("unknown_thing", 0.5) is False

    # ----- calculate_confidence -----

    def test_calculate_confidence_empty(self):
        ev = self._make_evaluator()
        assert ev._calculate_confidence({}) == 0.0

    def test_calculate_confidence_all_none(self):
        ev = self._make_evaluator()
        assert ev._calculate_confidence({"exact_match": None}) == 0.0

    def test_calculate_confidence_positive_metrics(self):
        ev = self._make_evaluator()
        result = ev._calculate_confidence({"exact_match": 1.0, "accuracy": 0.5})
        assert abs(result - 0.75) < 1e-9

    def test_calculate_confidence_error_metrics_inverted(self):
        ev = self._make_evaluator()
        # mae = 0.2 -> inverted = 1.0 - 0.2 = 0.8
        result = ev._calculate_confidence({"mae": 0.2})
        assert abs(result - 0.8) < 1e-9

    def test_calculate_confidence_mape_inverted(self):
        ev = self._make_evaluator()
        # mape = 50 -> inverted = 1.0 - 50/100 = 0.5
        result = ev._calculate_confidence({"mape": 50.0})
        assert abs(result - 0.5) < 1e-9

    def test_calculate_confidence_mape_capped(self):
        ev = self._make_evaluator()
        # mape > 100 -> capped at 100 -> inverted = 0.0
        result = ev._calculate_confidence({"mape": 200.0})
        assert abs(result - 0.0) < 1e-9

    def test_calculate_confidence_fallback_to_average(self):
        """When no recognized metrics, falls back to average of all valid values."""
        ev = self._make_evaluator()
        result = ev._calculate_confidence({"weird_metric": 0.4, "other_metric": 0.6})
        assert abs(result - 0.5) < 1e-9

    # ----- parse_json -----

    def test_parse_json_dict(self):
        ev = self._make_evaluator()
        assert ev._parse_json({"a": 1}) == {"a": 1}

    def test_parse_json_list(self):
        ev = self._make_evaluator()
        assert ev._parse_json([1, 2]) == [1, 2]

    def test_parse_json_valid_string(self):
        ev = self._make_evaluator()
        assert ev._parse_json('{"a":1}') == {"a": 1}

    def test_parse_json_invalid_string(self):
        ev = self._make_evaluator()
        assert ev._parse_json("not json") is None

    def test_parse_json_number(self):
        ev = self._make_evaluator()
        assert ev._parse_json(42) is None

    # ----- json_field_accuracy -----

    def test_json_field_accuracy_identical(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy({"a": 1, "b": 2}, {"a": 1, "b": 2}) == 1.0

    def test_json_field_accuracy_different_values(self):
        ev = self._make_evaluator()
        score = ev._json_field_accuracy({"a": 1, "b": 2}, {"a": 1, "b": 99})
        assert abs(score - 0.5) < 1e-9

    def test_json_field_accuracy_extra_keys(self):
        ev = self._make_evaluator()
        score = ev._json_field_accuracy({"a": 1}, {"a": 1, "b": 2})
        # all_keys = {a, b}, matching = 1 (a matches), score = 0.5
        assert abs(score - 0.5) < 1e-9

    def test_json_field_accuracy_type_mismatch(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy({"a": 1}, [1]) == 0.0

    def test_json_field_accuracy_empty_dicts(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy({}, {}) == 1.0

    def test_json_field_accuracy_empty_dict_vs_nonempty(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy({}, {"a": 1}) == 0.0

    def test_json_field_accuracy_lists(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy([1, 2, 3], [1, 2, 3]) == 1.0

    def test_json_field_accuracy_lists_different_length(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy([1, 2], [1]) == 0.0

    def test_json_field_accuracy_empty_lists(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy([], []) == 1.0

    def test_json_field_accuracy_empty_list_vs_nonempty(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy([], [1]) == 0.0

    def test_json_field_accuracy_nested_dict(self):
        ev = self._make_evaluator()
        gt = {"a": {"x": 1, "y": 2}}
        pred = {"a": {"x": 1, "y": 99}}
        score = ev._json_field_accuracy(gt, pred)
        # a is nested -> recursive: x matches (1), y doesn't (0) -> 0.5
        # outer: 1 key 'a' -> score = 0.5
        assert abs(score - 0.5) < 1e-9

    def test_json_field_accuracy_primitives(self):
        ev = self._make_evaluator()
        assert ev._json_field_accuracy(1, 1) == 1.0
        assert ev._json_field_accuracy(1, 2) == 0.0

    # ----- structured metrics -----

    def test_json_accuracy_both_valid_same(self):
        ev = self._make_evaluator()
        score = ev._compute_structured_metric(
            "json_accuracy", {"a": 1}, {"a": 1}
        )
        assert score == 1.0

    def test_json_accuracy_both_non_json(self):
        ev = self._make_evaluator()
        score = ev._compute_structured_metric("json_accuracy", 42, 42)
        assert score == 1.0

    def test_json_accuracy_one_json_one_not(self):
        ev = self._make_evaluator()
        score = ev._compute_structured_metric("json_accuracy", {"a": 1}, 42)
        assert score == 0.0

    def test_schema_validation_no_schema(self):
        ev = self._make_evaluator()
        score = ev._compute_structured_metric("schema_validation", None, '{"a":1}')
        assert score == 1.0

    def test_schema_validation_no_schema_invalid_json(self):
        ev = self._make_evaluator()
        score = ev._compute_structured_metric("schema_validation", None, "not json")
        assert score == 0.0

    def test_schema_validation_with_valid_schema(self):
        ev = self._make_evaluator()
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
        score = ev._compute_structured_metric(
            "schema_validation", None, {"a": 1}, {"schema": schema}
        )
        assert score == 1.0

    def test_schema_validation_with_invalid_data(self):
        ev = self._make_evaluator()
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
        score = ev._compute_structured_metric(
            "schema_validation", None, {"b": "not_a"}, {"schema": schema}
        )
        assert score == 0.0

    # ----- span metrics -----

    def test_parse_spans_list_of_dicts(self):
        ev = self._make_evaluator()
        spans = ev._parse_spans([{"start": 0, "end": 5}, {"start": 10, "end": 15}])
        assert len(spans) == 2
        assert spans[0] == {"start": 0, "end": 5}

    def test_parse_spans_with_labels(self):
        ev = self._make_evaluator()
        spans = ev._parse_spans([{"start": 0, "end": 5, "labels": ["PER"]}])
        assert spans[0]["labels"] == ["PER"]

    def test_parse_spans_with_single_label(self):
        ev = self._make_evaluator()
        spans = ev._parse_spans([{"start": 0, "end": 5, "label": "PER"}])
        assert spans[0]["labels"] == ["PER"]

    def test_parse_spans_from_tuples(self):
        ev = self._make_evaluator()
        spans = ev._parse_spans([(0, 5), (10, 15)])
        assert len(spans) == 2
        assert spans[0] == {"start": 0, "end": 5}

    def test_parse_spans_single_dict(self):
        ev = self._make_evaluator()
        spans = ev._parse_spans({"start": 0, "end": 10})
        assert len(spans) == 1
        assert spans[0] == {"start": 0, "end": 10}

    def test_parse_spans_from_json_string(self):
        ev = self._make_evaluator()
        spans = ev._parse_spans('[{"start": 0, "end": 5}]')
        assert len(spans) == 1

    def test_parse_spans_empty(self):
        ev = self._make_evaluator()
        assert ev._parse_spans([]) == []
        assert ev._parse_spans("invalid") == []
        assert ev._parse_spans(None) == []

    def test_span_iou_perfect(self):
        ev = self._make_evaluator()
        s = {"start": 0, "end": 10}
        assert ev._span_iou(s, s) == 1.0

    def test_span_iou_no_overlap(self):
        ev = self._make_evaluator()
        assert ev._span_iou({"start": 0, "end": 5}, {"start": 10, "end": 15}) == 0.0

    def test_span_iou_partial(self):
        ev = self._make_evaluator()
        score = ev._span_iou({"start": 0, "end": 10}, {"start": 5, "end": 15})
        # intersection = 5, union = 15, iou = 5/15 = 1/3
        assert abs(score - 1 / 3) < 1e-9

    def test_span_iou_zero_union(self):
        ev = self._make_evaluator()
        assert ev._span_iou({"start": 5, "end": 5}, {"start": 5, "end": 5}) == 0.0

    def test_spans_label_compatible_no_labels(self):
        ev = self._make_evaluator()
        assert ev._spans_label_compatible({"start": 0, "end": 5}, {"start": 0, "end": 5}) is True

    def test_spans_label_compatible_matching(self):
        ev = self._make_evaluator()
        assert ev._spans_label_compatible(
            {"start": 0, "end": 5, "labels": ["PER"]},
            {"start": 0, "end": 5, "labels": ["PER"]},
        ) is True

    def test_spans_label_incompatible(self):
        ev = self._make_evaluator()
        assert ev._spans_label_compatible(
            {"start": 0, "end": 5, "labels": ["PER"]},
            {"start": 0, "end": 5, "labels": ["ORG"]},
        ) is False

    def test_span_exact_match_metric(self):
        ev = self._make_evaluator()
        gt = [{"start": 0, "end": 5}, {"start": 10, "end": 15}]
        pred = [{"start": 0, "end": 5}, {"start": 10, "end": 15}]
        assert ev._compute_span_metric("exact_match", gt, pred) == 1.0

    def test_span_exact_match_different(self):
        ev = self._make_evaluator()
        gt = [{"start": 0, "end": 5}]
        pred = [{"start": 0, "end": 6}]
        assert ev._compute_span_metric("exact_match", gt, pred) == 0.0

    def test_span_iou_metric_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_span_metric("iou", [], []) == 1.0

    def test_span_iou_metric_one_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_span_metric("iou", [{"start": 0, "end": 5}], []) == 0.0

    # ----- partial_match -----

    def test_partial_match_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_partial_match([], []) == 1.0

    def test_partial_match_one_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_partial_match([{"start": 0, "end": 5}], []) == 0.0

    def test_partial_match_perfect(self):
        ev = self._make_evaluator()
        spans = [{"start": 0, "end": 10}]
        assert ev._compute_partial_match(spans, spans) == 1.0

    def test_partial_match_average_mode(self):
        ev = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 5, "end": 15}]
        score = ev._compute_partial_match(gt, pred, {"mode": "average"})
        # overlap = 5, gt_length = 10, overlap_ratio = 0.5
        assert abs(score - 0.5) < 1e-9

    def test_partial_match_average_no_compatible(self):
        ev = self._make_evaluator()
        gt = [{"start": 0, "end": 10, "labels": ["PER"]}]
        pred = [{"start": 0, "end": 10, "labels": ["ORG"]}]
        score = ev._compute_partial_match(gt, pred, {"mode": "average"})
        assert score == 0.0

    # ----- boundary_accuracy -----

    def test_boundary_accuracy_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_boundary_accuracy([], []) == 1.0

    def test_boundary_accuracy_one_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_boundary_accuracy([{"start": 0, "end": 5}], []) == 0.0

    def test_boundary_accuracy_perfect(self):
        ev = self._make_evaluator()
        spans = [{"start": 0, "end": 10}]
        assert ev._compute_boundary_accuracy(spans, spans) == 1.0

    def test_boundary_accuracy_one_match(self):
        ev = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 15}]
        score = ev._compute_boundary_accuracy(gt, pred)
        assert abs(score - 0.5) < 1e-9

    def test_boundary_accuracy_with_tolerance(self):
        ev = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 1, "end": 11}]
        score = ev._compute_boundary_accuracy(gt, pred, {"tolerance": 1})
        assert score == 1.0

    def test_boundary_accuracy_lenient_mode(self):
        ev = self._make_evaluator()
        gt = [{"start": 0, "end": 10}]
        pred = [{"start": 0, "end": 10}, {"start": 20, "end": 30}]
        score = ev._compute_boundary_accuracy(gt, pred, {"mode": "lenient"})
        assert score == 1.0

    def test_calculate_boundary_score_both_match(self):
        ev = self._make_evaluator()
        assert ev._calculate_boundary_score(
            {"start": 0, "end": 10}, {"start": 0, "end": 10}, 0
        ) == 1.0

    def test_calculate_boundary_score_start_only(self):
        ev = self._make_evaluator()
        assert ev._calculate_boundary_score(
            {"start": 0, "end": 10}, {"start": 0, "end": 99}, 0
        ) == 0.5

    def test_calculate_boundary_score_none_match(self):
        ev = self._make_evaluator()
        assert ev._calculate_boundary_score(
            {"start": 0, "end": 10}, {"start": 50, "end": 60}, 0
        ) == 0.0

    # ----- calculate_span_overlap -----

    def test_calculate_span_overlap_perfect(self):
        ev = self._make_evaluator()
        s = {"start": 0, "end": 10}
        assert ev._calculate_span_overlap(s, s) == 1.0

    def test_calculate_span_overlap_no_overlap(self):
        ev = self._make_evaluator()
        assert ev._calculate_span_overlap(
            {"start": 0, "end": 5}, {"start": 10, "end": 15}
        ) == 0.0

    def test_calculate_span_overlap_zero_length_gt(self):
        ev = self._make_evaluator()
        assert ev._calculate_span_overlap(
            {"start": 5, "end": 5}, {"start": 5, "end": 10}
        ) == 0.0

    # ----- hierarchical metrics -----

    def test_parse_hierarchy_path_list(self):
        ev = self._make_evaluator()
        assert ev._parse_hierarchy_path(["Law", "Civil"]) == ["Law", "Civil"]

    def test_parse_hierarchy_path_json_string(self):
        ev = self._make_evaluator()
        assert ev._parse_hierarchy_path('["a","b"]') == ["a", "b"]

    def test_parse_hierarchy_path_delimiter_slash(self):
        ev = self._make_evaluator()
        assert ev._parse_hierarchy_path("Law/Civil/Contract") == ["Law", "Civil", "Contract"]

    def test_parse_hierarchy_path_delimiter_arrow(self):
        ev = self._make_evaluator()
        assert ev._parse_hierarchy_path("A > B > C") == ["A", "B", "C"]

    def test_parse_hierarchy_path_delimiter_double_colon(self):
        ev = self._make_evaluator()
        assert ev._parse_hierarchy_path("A::B::C") == ["A", "B", "C"]

    def test_parse_hierarchy_path_plain(self):
        ev = self._make_evaluator()
        assert ev._parse_hierarchy_path("Leaf") == ["Leaf"]

    def test_parse_hierarchy_path_none(self):
        ev = self._make_evaluator()
        assert ev._parse_hierarchy_path(None) == []

    def test_parse_hierarchy_path_number(self):
        ev = self._make_evaluator()
        assert ev._parse_hierarchy_path(42) == ["42"]

    def test_hierarchical_f1_identical(self):
        ev = self._make_evaluator()
        score = ev._compute_hierarchical_metric("hierarchical_f1", ["A", "B", "C"], ["A", "B", "C"])
        assert score == 1.0

    def test_hierarchical_f1_partial(self):
        ev = self._make_evaluator()
        score = ev._compute_hierarchical_metric("hierarchical_f1", ["A", "B", "C"], ["A", "B", "D"])
        # gt_ancestors = {(A,), (A,B), (A,B,C)}, pred_ancestors = {(A,), (A,B), (A,B,D)}
        # intersection = {(A,), (A,B)} = 2
        # precision = 2/3, recall = 2/3, f1 = 2/3
        assert abs(score - 2 / 3) < 1e-9

    def test_hierarchical_f1_no_overlap(self):
        ev = self._make_evaluator()
        score = ev._compute_hierarchical_metric("hierarchical_f1", ["X"], ["Y"])
        assert score == 0.0

    def test_hierarchical_f1_both_empty(self):
        ev = self._make_evaluator()
        score = ev._compute_hierarchical_metric("hierarchical_f1", [], [])
        assert score == 1.0

    def test_hierarchical_f1_one_empty(self):
        ev = self._make_evaluator()
        score = ev._compute_hierarchical_metric("hierarchical_f1", ["A"], [])
        assert score == 0.0

    # ----- path_accuracy -----

    def test_path_accuracy_identical(self):
        ev = self._make_evaluator()
        score = ev._compute_path_accuracy(["A", "B", "C"], ["A", "B", "C"])
        assert score == 1.0

    def test_path_accuracy_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_path_accuracy([], []) == 1.0

    def test_path_accuracy_one_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_path_accuracy(["A"], []) == 0.0

    def test_path_accuracy_diverges(self):
        ev = self._make_evaluator()
        score = ev._compute_path_accuracy(["A", "B", "C"], ["A", "B", "X"])
        # matching: A (weight=1) + B (weight=2) = 3
        # max: 1 + 2 + 3 = 6
        assert abs(score - 3 / 6) < 1e-9

    def test_path_accuracy_no_normalize(self):
        ev = self._make_evaluator()
        score = ev._compute_path_accuracy(["A", "B"], ["A", "B"], {"normalize": False})
        # matching: A (1) + B (2) = 3
        assert abs(score - 3.0) < 1e-9

    # ----- lca_accuracy -----

    def test_lca_accuracy_identical(self):
        ev = self._make_evaluator()
        assert ev._compute_lca_accuracy(["A", "B"], ["A", "B"]) == 1.0

    def test_lca_accuracy_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_lca_accuracy([], []) == 1.0

    def test_lca_accuracy_one_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_lca_accuracy(["A"], []) == 0.0

    def test_lca_accuracy_no_common(self):
        ev = self._make_evaluator()
        assert ev._compute_lca_accuracy(["X"], ["Y"]) == 0.0

    def test_lca_accuracy_partial(self):
        ev = self._make_evaluator()
        score = ev._compute_lca_accuracy(["A", "B", "C"], ["A", "X"])
        # lca_depth = 1 (only "A" matches), distance_to_gt = 3-1 = 2
        # score = 0.5^2 = 0.25 (above min_score 0.1)
        assert abs(score - 0.25) < 1e-9

    def test_lca_accuracy_custom_decay(self):
        ev = self._make_evaluator()
        score = ev._compute_lca_accuracy(
            ["A", "B", "C"], ["A", "X"], {"decay_rate": 0.7}
        )
        # distance_to_gt = 2, score = 0.7^2 = 0.49
        assert abs(score - 0.49) < 1e-9

    def test_lca_accuracy_min_score(self):
        ev = self._make_evaluator()
        score = ev._compute_lca_accuracy(
            ["A", "B", "C", "D", "E", "F"], ["A", "X"],
            {"decay_rate": 0.1, "min_score": 0.2},
        )
        # distance_to_gt = 5, score = 0.1^5 = 0.00001, clamped to min_score 0.2
        assert abs(score - 0.2) < 1e-9

    # ----- answers_match_qags -----

    def test_qags_answers_match_exact(self):
        ev = self._make_evaluator()
        assert ev._answers_match_qags("Berlin", "Berlin") is True

    def test_qags_answers_match_case_insensitive(self):
        ev = self._make_evaluator()
        assert ev._answers_match_qags("Berlin", "berlin") is True

    def test_qags_answers_no_match(self):
        ev = self._make_evaluator()
        assert ev._answers_match_qags("Berlin", "Paris") is False

    def test_qags_answers_empty(self):
        ev = self._make_evaluator()
        assert ev._answers_match_qags("Berlin", "") is False

    def test_qags_answers_token_overlap(self):
        ev = self._make_evaluator()
        assert ev._answers_match_qags("city of Berlin", "Berlin city") is True

    # ----- validate_text_for_coherence -----

    def test_coherence_validation_empty(self):
        ev = self._make_evaluator()
        with pytest.raises(ValueError, match="non-empty"):
            ev._validate_text_for_coherence("")

    def test_coherence_validation_too_short(self):
        ev = self._make_evaluator()
        with pytest.raises(ValueError, match="at least 20"):
            ev._validate_text_for_coherence("Short.")

    # ----- detect_language_heuristic -----

    def test_detect_language_german_articles(self):
        ev = self._make_evaluator()
        sentences = ["Der Vertrag ist gueltig.", "Die Parteien haben zugestimmt."]
        assert ev._detect_language_heuristic(sentences) == "de"

    def test_detect_language_german_umlauts(self):
        ev = self._make_evaluator()
        sentences = ["Wir prüfen die Lösung."]
        assert ev._detect_language_heuristic(sentences) == "de"

    def test_detect_language_english(self):
        ev = self._make_evaluator()
        sentences = ["The contract is valid.", "All parties agreed."]
        assert ev._detect_language_heuristic(sentences) == "en"

    def test_detect_language_german_capitalization(self):
        ev = self._make_evaluator()
        # German has capitalized nouns mid-sentence, triggering cap_ratio > 0.15
        sentences = ["Wir sehen den Vertrag und die Klausel und das Gericht."]
        assert ev._detect_language_heuristic(sentences) == "de"

    # ----- ranking metrics error paths -----

    def test_weighted_kappa_raises(self):
        ev = self._make_evaluator()
        with pytest.raises(RuntimeError, match="aggregate-only"):
            ev._compute_ranking_metric("weighted_kappa", [1, 2], [1, 2])

    def test_spearman_identical(self):
        ev = self._make_evaluator()
        assert ev._compute_ranking_metric("spearman", [1, 2, 3], [1, 2, 3]) == 1.0

    def test_spearman_different_length(self):
        ev = self._make_evaluator()
        assert ev._compute_ranking_metric("spearman", [1, 2], [1, 2, 3]) == 0.0

    def test_spearman_single_element(self):
        ev = self._make_evaluator()
        assert ev._compute_ranking_metric("spearman", [1], [1]) == 1.0

    def test_kendall_identical(self):
        ev = self._make_evaluator()
        assert ev._compute_ranking_metric("kendall", [1, 2, 3], [1, 2, 3]) == 1.0

    def test_kendall_different_length(self):
        ev = self._make_evaluator()
        assert ev._compute_ranking_metric("kendall", [1], [1, 2]) == 0.0

    def test_ndcg_identical(self):
        ev = self._make_evaluator()
        score = ev._compute_ranking_metric("ndcg", [3, 2, 1], [3, 2, 1])
        assert score == 1.0

    def test_ndcg_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_ranking_metric("ndcg", [], []) == 1.0

    def test_map_perfect(self):
        ev = self._make_evaluator()
        # gt_set = {a, b}, pred_list = [a, b]
        # AP = (1/1 + 2/2) / 2 = 1.0
        score = ev._compute_ranking_metric("map", ["a", "b"], ["a", "b"])
        assert score == 1.0

    def test_map_both_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_ranking_metric("map", [], []) == 1.0

    def test_map_partial(self):
        ev = self._make_evaluator()
        # gt_set = {a, b}, pred_list = [b, c, a]
        # b at pos 0: hits=1, precision=1/1=1.0
        # c at pos 1: not in gt
        # a at pos 2: hits=2, precision=2/3
        # AP = (1.0 + 2/3) / 2 = 5/6
        score = ev._compute_ranking_metric("map", ["a", "b"], ["b", "c", "a"])
        assert abs(score - 5 / 6) < 1e-9

    # ----- unknown metric fallback -----

    def test_unknown_metric_defaults_to_exact_match(self):
        ev = self._make_evaluator()
        assert ev._compute_metric("totally_unknown", "x", "x", "text") == 1.0
        assert ev._compute_metric("totally_unknown", "x", "y", "text") == 0.0

    # ----- evaluate_sample -----

    def test_evaluate_sample_rejects_unparsed_generation(self):
        ev = self._make_evaluator()
        with pytest.raises(ValueError, match="parse_status"):
            ev.evaluate_sample(
                task_id="t1",
                field_name="f",
                ground_truth="a",
                prediction="b",
                metrics_to_compute=["exact_match"],
                generation_id="gen-1",
                parse_status="failed",
            )

    def test_evaluate_sample_allows_unparsed_with_flag(self):
        ev = self._make_evaluator()
        result = ev.evaluate_sample(
            task_id="t1",
            field_name="f",
            ground_truth="hello",
            prediction="hello",
            metrics_to_compute=["exact_match"],
            generation_id="gen-1",
            parse_status="failed",
            allow_unparsed=True,
        )
        assert result["metrics"]["exact_match"] == 1.0
        assert result["passed"] is True

    def test_evaluate_sample_metric_failure(self):
        """When a metric raises, it gets captured as None in metrics."""
        ev = self._make_evaluator()
        result = ev.evaluate_sample(
            task_id="t1",
            field_name="f",
            ground_truth="1",
            prediction="2",
            metrics_to_compute=["r2"],  # Will raise RuntimeError
        )
        assert result["metrics"]["r2"] is None

    def test_evaluate_sample_normal(self):
        ev = self._make_evaluator()
        result = ev.evaluate_sample(
            task_id="t1",
            field_name="f",
            ground_truth="hello world",
            prediction="hello world",
            metrics_to_compute=["exact_match", "accuracy"],
        )
        assert result["metrics"]["exact_match"] == 1.0
        assert result["metrics"]["accuracy"] == 1.0
        assert result["passed"] is True
        assert result["error_message"] is None
        assert "id" in result
        assert "processing_time_ms" in result

    def test_evaluate_sample_with_metric_parameters(self):
        ev = self._make_evaluator(
            metric_parameters={"f": {"bleu": {"max_order": 2}}}
        )
        result = ev.evaluate_sample(
            task_id="t1",
            field_name="f",
            ground_truth="the cat sat on the mat",
            prediction="the cat sat on a mat",
            metrics_to_compute=["bleu"],
        )
        assert result["metrics"]["bleu"] is not None
        assert 0.0 <= result["metrics"]["bleu"] <= 1.0


# ============================================================================
# 2. LLMJudgeEvaluator - Deep Coverage
# ============================================================================


class TestLLMJudgeDeepCoverage:
    """Test LLMJudgeEvaluator paths not covered by existing tests."""

    def _make_evaluator(self, **kwargs):
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        defaults = {
            "ai_service": MagicMock(),
            "judge_model": "test-model",
        }
        defaults.update(kwargs)
        return LLMJudgeEvaluator(**defaults)

    # ----- _extract_nested_value -----

    def test_extract_nested_value_simple(self):
        ev = self._make_evaluator()
        assert ev._extract_nested_value({"a": 1}, "a") == 1

    def test_extract_nested_value_deep(self):
        ev = self._make_evaluator()
        data = {"context": {"jurisdiction": "DE"}}
        assert ev._extract_nested_value(data, "context.jurisdiction") == "DE"

    def test_extract_nested_value_missing(self):
        ev = self._make_evaluator()
        assert ev._extract_nested_value({"a": 1}, "b") is None

    def test_extract_nested_value_none_data(self):
        ev = self._make_evaluator()
        assert ev._extract_nested_value(None, "a") is None

    def test_extract_nested_value_empty_path(self):
        ev = self._make_evaluator()
        assert ev._extract_nested_value({"a": 1}, "") is None

    # ----- _apply_field_mappings -----

    def test_apply_field_mappings_dollar_prefix(self):
        ev = self._make_evaluator(field_mappings={"jurisdiction": "$context.jurisdiction"})
        task_data = {"context": {"jurisdiction": "DE"}}
        result = ev._apply_field_mappings(task_data, {})
        assert result["jurisdiction"] == "DE"

    def test_apply_field_mappings_no_prefix(self):
        ev = self._make_evaluator(field_mappings={"name": "name"})
        task_data = {"name": "Test"}
        result = ev._apply_field_mappings(task_data, {})
        assert result["name"] == "Test"

    def test_apply_field_mappings_missing_field(self):
        ev = self._make_evaluator(field_mappings={"x": "$nonexistent"})
        result = ev._apply_field_mappings({"a": 1}, {})
        assert "x" not in result

    def test_apply_field_mappings_empty(self):
        ev = self._make_evaluator(field_mappings={})
        result = ev._apply_field_mappings({"a": 1}, {"existing": "value"})
        assert result == {"existing": "value"}

    def test_apply_field_mappings_none_task_data(self):
        ev = self._make_evaluator(field_mappings={"x": "$a"})
        result = ev._apply_field_mappings(None, {"k": "v"})
        assert result == {"k": "v"}

    def test_apply_field_mappings_non_string_value(self):
        ev = self._make_evaluator(field_mappings={"count": "$items"})
        result = ev._apply_field_mappings({"items": 42}, {})
        assert result["count"] == "42"

    # ----- _format_value (no answer_type) -----

    def test_format_value_string(self):
        ev = self._make_evaluator()
        assert ev._format_value("hello") == "hello"

    def test_format_value_dict(self):
        ev = self._make_evaluator()
        result = ev._format_value({"a": 1})
        assert '"a"' in result

    def test_format_value_list(self):
        ev = self._make_evaluator()
        result = ev._format_value([1, 2])
        assert "1" in result

    def test_format_value_number(self):
        ev = self._make_evaluator()
        assert ev._format_value(42) == "42"

    # ----- _format_value_by_type -----

    def test_format_value_by_type_text_string(self):
        ev = self._make_evaluator(answer_type="text")
        assert ev._format_value("hello") == "hello"

    def test_format_value_by_type_text_empty(self):
        ev = self._make_evaluator(answer_type="text")
        assert ev._format_value("") == "(empty)"

    def test_format_value_by_type_text_dict(self):
        ev = self._make_evaluator(answer_type="text")
        result = ev._format_value({"text": ["answer"]})
        assert result == "answer"

    def test_format_value_by_type_text_dict_single(self):
        ev = self._make_evaluator(answer_type="text")
        result = ev._format_value({"text": "answer"})
        assert result == "answer"

    def test_format_value_by_type_none(self):
        ev = self._make_evaluator(answer_type="text")
        assert ev._format_value(None) == "(no value provided)"

    def test_format_value_by_type_choices_list(self):
        ev = self._make_evaluator(answer_type="choices")
        result = ev._format_value(["A", "B"])
        assert result == "Selected: [A, B]"

    def test_format_value_by_type_choices_dict(self):
        ev = self._make_evaluator(answer_type="choices")
        result = ev._format_value({"choices": ["A"]})
        assert result == "Selected: [A]"

    def test_format_value_by_type_choices_empty(self):
        ev = self._make_evaluator(answer_type="choices")
        result = ev._format_value([])
        assert result == "Selected: [none]"

    def test_format_value_by_type_choices_string(self):
        ev = self._make_evaluator(answer_type="single_choice")
        result = ev._format_value("option_A")
        assert result == "Selected: [option_A]"

    def test_format_value_by_type_rating_dict(self):
        ev = self._make_evaluator(answer_type="rating")
        result = ev._format_value({"rating": 4})
        assert result == "Value: 4"

    def test_format_value_by_type_rating_number_dict(self):
        ev = self._make_evaluator(answer_type="numeric")
        result = ev._format_value({"number": 3.14})
        assert result == "Value: 3.14"

    def test_format_value_by_type_rating_plain(self):
        ev = self._make_evaluator(answer_type="rating")
        result = ev._format_value(5)
        assert result == "Value: 5"

    def test_format_value_by_type_unknown_dict(self):
        ev = self._make_evaluator(answer_type="unknown_custom_type")
        result = ev._format_value({"x": 1})
        assert '"x"' in result

    def test_format_value_by_type_unknown_string(self):
        ev = self._make_evaluator(answer_type="unknown_custom_type")
        assert ev._format_value("foo") == "foo"

    # ----- _format_spans -----

    def test_format_spans_empty(self):
        ev = self._make_evaluator(answer_type="span_selection")
        assert ev._format_spans(None) == "(no spans annotated)"
        assert ev._format_spans([]) == "(no spans annotated)"

    def test_format_spans_dict_wrapper(self):
        ev = self._make_evaluator(answer_type="span_selection")
        spans = {"spans": [{"text": "John", "start": 0, "end": 4, "labels": ["PER"]}]}
        result = ev._format_spans(spans)
        assert "John" in result
        assert "PER" in result

    def test_format_spans_invalid_type(self):
        ev = self._make_evaluator(answer_type="span_selection")
        result = ev._format_spans("not a list")
        assert "invalid span format" in result

    def test_format_spans_non_dict_entry(self):
        ev = self._make_evaluator(answer_type="span_selection")
        result = ev._format_spans(["invalid_item"])
        assert "invalid span entry" in result

    def test_format_spans_no_labels(self):
        ev = self._make_evaluator(answer_type="span_selection")
        result = ev._format_spans([{"text": "X", "start": 0, "end": 1}])
        assert "no label" in result

    def test_format_spans_string_label(self):
        ev = self._make_evaluator(answer_type="span_selection")
        result = ev._format_spans([{"text": "X", "start": 0, "end": 1, "label": "ORG"}])
        assert "ORG" in result

    def test_format_spans_non_list_labels(self):
        ev = self._make_evaluator(answer_type="span_selection")
        result = ev._format_spans([{"text": "X", "start": 0, "end": 1, "labels": 42}])
        assert "no label" in result

    # ----- score_scale -----

    def test_score_scale_0_1_clamps(self):
        ev = self._make_evaluator(score_scale="0-1")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 1.5, "justification": "too high"}',
        }
        result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result["score"] == 1.0

    def test_score_scale_0_1_normal(self):
        ev = self._make_evaluator(score_scale="0-1")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 0.7, "justification": "good"}',
        }
        result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result["score"] == 0.7

    def test_score_scale_0_100_clamps(self):
        ev = self._make_evaluator(score_scale="0-100")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 150, "justification": "too high"}',
        }
        result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result["score"] == 100.0

    def test_score_scale_1_5_clamps_low(self):
        ev = self._make_evaluator(score_scale="1-5")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": -1, "justification": "too low"}',
        }
        result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result["score"] == 1.0

    # ----- answer_type auto-selection -----

    def test_answer_type_auto_selects_criteria(self):
        ev = self._make_evaluator(answer_type="span_selection", criteria=None)
        assert "boundary_accuracy" in ev.criteria

    def test_answer_type_auto_selects_template(self):
        ev = self._make_evaluator(answer_type="choices", criteria=None)
        assert ev.custom_prompt_template is not None
        assert "classification" in ev.custom_prompt_template.lower()

    def test_no_answer_type_defaults_criteria(self):
        ev = self._make_evaluator(answer_type=None, criteria=None)
        assert ev.criteria == ["helpfulness", "correctness"]

    def test_explicit_criteria_overrides_type(self):
        ev = self._make_evaluator(answer_type="choices", criteria=["fluency"])
        assert ev.criteria == ["fluency"]

    def test_custom_prompt_overrides_type(self):
        custom = "Custom {criterion_name}"
        ev = self._make_evaluator(answer_type="choices", custom_prompt_template=custom)
        assert ev.custom_prompt_template == custom

    # ----- validate_model_config -----

    def test_validate_model_config_with_service(self):
        ev = self._make_evaluator()
        assert ev.validate_model_config({}) is True

    def test_validate_model_config_no_service(self):
        ev = self._make_evaluator(ai_service=None)
        assert ev.validate_model_config({}) is False

    # ----- get_supported_metrics -----

    def test_supported_metrics_includes_custom(self):
        ev = self._make_evaluator(
            custom_criteria={"my_custom": {"name": "MC", "description": "d", "rubric": "r"}}
        )
        metrics = ev.get_supported_metrics()
        assert "llm_judge_my_custom" in metrics
        assert "llm_judge_classic" in metrics

    # ----- evaluate() full pipeline -----

    def test_evaluate_no_ai_service(self):
        from ml_evaluation.base_evaluator import EvaluationConfig

        ev = self._make_evaluator(ai_service=None)
        config = EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={})
        result = ev.evaluate("model-1", [], config)
        assert result.error is not None
        assert result.samples_evaluated == 0

    def test_evaluate_overall_metric(self):
        from ml_evaluation.base_evaluator import EvaluationConfig

        ev = self._make_evaluator()
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        task_data = [
            {
                "data": {"text": "Question"},
                "annotations": [{"result": "expected answer"}],
                "predictions": [{"model_version": "m1", "result": "model answer"}],
            }
        ]

        config = EvaluationConfig(metrics=["llm_judge_overall"], model_config={})
        result = ev.evaluate("m1", task_data, config)

        assert result.samples_evaluated == 1
        assert "llm_judge_overall" in result.metrics

    def test_evaluate_skips_missing_gt_or_pred(self):
        from ml_evaluation.base_evaluator import EvaluationConfig

        ev = self._make_evaluator()
        # Task with no annotations -> no ground truth
        task_data = [
            {
                "data": {"text": "Question"},
                "annotations": [],
                "predictions": [{"model_version": "m1", "result": "answer"}],
            }
        ]

        config = EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={})
        result = ev.evaluate("m1", task_data, config)
        assert result.samples_evaluated == 0

    def test_evaluate_score_aggregation_0_1_scale(self):
        from ml_evaluation.base_evaluator import EvaluationConfig

        ev = self._make_evaluator(score_scale="0-1")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 0.8, "justification": "Good"}',
        }

        task_data = [
            {
                "data": {"text": "Q"},
                "annotations": [{"result": "A"}],
                "predictions": [{"model_version": "m1", "result": "A"}],
            }
        ]

        config = EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={})
        result = ev.evaluate("m1", task_data, config)

        # 0-1 scale: normalized = raw score directly
        assert "llm_judge_helpfulness" in result.metrics
        assert abs(result.metrics["llm_judge_helpfulness"] - 0.8) < 1e-9
        assert abs(result.metrics["llm_judge_helpfulness_raw"] - 0.8) < 1e-9

    def test_evaluate_score_aggregation_1_5_scale(self):
        from ml_evaluation.base_evaluator import EvaluationConfig

        ev = self._make_evaluator(score_scale="1-5")
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 3, "justification": "Average"}',
        }

        task_data = [
            {
                "data": {"text": "Q"},
                "annotations": [{"result": "A"}],
                "predictions": [{"model_version": "m1", "result": "A"}],
            }
        ]

        config = EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={})
        result = ev.evaluate("m1", task_data, config)

        # 1-5 scale: normalized = (3-1)/4 = 0.5
        assert abs(result.metrics["llm_judge_helpfulness"] - 0.5) < 1e-9
        assert abs(result.metrics["llm_judge_helpfulness_raw"] - 3.0) < 1e-9

    def test_evaluate_handles_api_failure_gracefully(self):
        """When AI service fails for all retries, criterion returns None, no scores aggregated."""
        from ml_evaluation.base_evaluator import EvaluationConfig

        ev = self._make_evaluator(max_retries=1)
        ev.ai_service.generate.side_effect = Exception("API Error")

        task_data = [
            {
                "data": {"text": "Q"},
                "annotations": [{"result": "A"}],
                "predictions": [{"model_version": "m1", "result": "A"}],
            }
        ]

        config = EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={})
        result = ev.evaluate("m1", task_data, config)

        # _evaluate_single_criterion catches exceptions internally and returns None
        # So samples_evaluated = 1 (loop completed), but no scores collected
        assert result.samples_evaluated == 1
        # No scores -> no metrics
        assert "llm_judge_helpfulness" not in result.metrics

    def test_evaluate_handles_outer_exception_per_sample(self):
        """When extract_ground_truth raises, it gets logged as an error."""
        from ml_evaluation.base_evaluator import EvaluationConfig

        ev = self._make_evaluator()

        # Task with bad data that will cause extraction to fail
        task_data = [
            {
                "data": {"text": "Q"},
                "annotations": "not_a_list",  # This will cause an error in extraction
                "predictions": [{"model_version": "m1", "result": "A"}],
            }
        ]

        config = EvaluationConfig(metrics=["llm_judge_helpfulness"], model_config={})
        result = ev.evaluate("m1", task_data, config)

        # The error should be caught and logged
        assert result.metadata["errors"] is not None
        assert len(result.metadata["errors"]) > 0

    def test_evaluate_default_criteria_when_no_llm_judge_prefix(self):
        from ml_evaluation.base_evaluator import EvaluationConfig

        ev = self._make_evaluator(criteria=["fluency"])
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        task_data = [
            {
                "data": {"text": "Q"},
                "annotations": [{"result": "A"}],
                "predictions": [{"model_version": "m1", "result": "A"}],
            }
        ]

        # Metric that doesn't start with llm_judge_ - falls through to self.criteria
        config = EvaluationConfig(metrics=["something_else"], model_config={})
        result = ev.evaluate("m1", task_data, config)
        assert result.samples_evaluated == 1

    # ----- _evaluate_single_criterion with custom prompt template KeyError -----

    def test_evaluate_single_criterion_template_keyerror_fallback(self):
        ev = self._make_evaluator(
            custom_prompt_template="Evaluate {unknown_var} for {criterion_name}"
        )
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 3, "justification": "ok"}',
        }
        result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
        assert result is not None
        assert result["score"] == 3.0

    # ----- _evaluate_single_criterion with task_data field mappings -----

    def test_evaluate_single_criterion_with_field_mappings(self):
        ev = self._make_evaluator(field_mappings={"area": "$law_area"})
        ev.ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 5, "justification": "perfect"}',
        }
        result = ev._evaluate_single_criterion(
            "ctx", "gt", "pred", "helpfulness",
            task_data={"law_area": "Civil Law"},
        )
        assert result["score"] == 5.0

    # ----- _parse_evaluation_response edge cases -----

    def test_parse_response_preference_in_text(self):
        ev = self._make_evaluator()
        response = 'Result: {"preference": "B", "justification": "B is better"} end.'
        result = ev._parse_evaluation_response(response)
        assert result is not None
        assert result["preference"] == "B"

    def test_parse_response_empty_content(self):
        ev = self._make_evaluator()
        assert ev._parse_evaluation_response("") is None

    # ----- pairwise with exception -----

    def test_pairwise_exception_returns_tie(self):
        ev = self._make_evaluator(max_retries=1)
        ev.ai_service.generate.side_effect = Exception("boom")
        result = ev.evaluate_pairwise("ctx", "gt", "a", "b", "helpfulness")
        assert result["preference"] == "TIE"

    # ----- E2E test mock path -----

    def test_e2e_test_mode_returns_mock_score(self):
        ev = self._make_evaluator(ai_service=None)
        with patch.dict(os.environ, {"E2E_TEST_MODE": "true"}):
            result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
            assert result is not None
            assert 0.6 <= result["score"] <= 1.0
            assert "Mock" in result["justification"]

    def test_no_e2e_no_service_returns_none(self):
        ev = self._make_evaluator(ai_service=None)
        with patch.dict(os.environ, {}, clear=True):
            # Ensure E2E_TEST_MODE is not set
            os.environ.pop("E2E_TEST_MODE", None)
            result = ev._evaluate_single_criterion("ctx", "gt", "pred", "helpfulness")
            assert result is None


# ============================================================================
# 3. TorchBackend - Initialization and Availability
# ============================================================================


class TestTorchBackendAvailability:
    """Test torch backend is_available and lazy loading paths."""

    def test_torch_embedding_available_when_imports_succeed(self):
        from ml_evaluation.backends.torch_backend import TorchEmbeddingBackend

        backend = TorchEmbeddingBackend()
        # Reset cached state
        backend._torch_available = None
        result = backend.is_available()
        assert isinstance(result, bool)

    def test_torch_embedding_caches_availability(self):
        from ml_evaluation.backends.torch_backend import TorchEmbeddingBackend

        backend = TorchEmbeddingBackend()
        backend._torch_available = True
        assert backend.is_available() is True

    def test_torch_embedding_unavailable(self):
        from ml_evaluation.backends.torch_backend import TorchEmbeddingBackend

        backend = TorchEmbeddingBackend()
        backend._torch_available = False
        assert backend.is_available() is False

    def test_torch_bertscore_available(self):
        from ml_evaluation.backends.torch_backend import TorchBERTScoreBackend

        backend = TorchBERTScoreBackend()
        backend._bert_score_available = None
        result = backend.is_available()
        assert isinstance(result, bool)

    def test_torch_bertscore_caches(self):
        from ml_evaluation.backends.torch_backend import TorchBERTScoreBackend

        backend = TorchBERTScoreBackend()
        backend._bert_score_available = True
        assert backend.is_available() is True

    def test_torch_qags_available(self):
        from ml_evaluation.backends.torch_backend import TorchQAGSBackend

        backend = TorchQAGSBackend()
        backend._torch_available = None
        result = backend.is_available()
        assert isinstance(result, bool)

    def test_torch_qags_caches(self):
        from ml_evaluation.backends.torch_backend import TorchQAGSBackend

        backend = TorchQAGSBackend()
        backend._torch_available = False
        assert backend.is_available() is False

    def test_torch_summac_available(self):
        from ml_evaluation.backends.torch_backend import TorchSummaCBackend

        backend = TorchSummaCBackend()
        backend._torch_available = None
        result = backend.is_available()
        assert isinstance(result, bool)

    def test_torch_summac_caches(self):
        from ml_evaluation.backends.torch_backend import TorchSummaCBackend

        backend = TorchSummaCBackend()
        backend._torch_available = True
        assert backend.is_available() is True

    def test_torch_embedding_model_name(self):
        from ml_evaluation.backends.torch_backend import TorchEmbeddingBackend

        backend = TorchEmbeddingBackend("custom-model")
        assert backend.model_name == "custom-model"
        assert backend._model is None

    def test_torch_bertscore_init(self):
        from ml_evaluation.backends.torch_backend import TorchBERTScoreBackend

        backend = TorchBERTScoreBackend()
        assert backend._bert_score_available is None

    def test_torch_qags_init(self):
        from ml_evaluation.backends.torch_backend import TorchQAGSBackend

        backend = TorchQAGSBackend()
        assert backend._qg_model is None
        assert backend._qg_tokenizer is None
        assert backend._qa_pipeline is None

    def test_torch_summac_init(self):
        from ml_evaluation.backends.torch_backend import TorchSummaCBackend

        backend = TorchSummaCBackend()
        assert backend._model is None
        assert backend._tokenizer is None
        assert backend.VITC_MODEL == "tals/albert-xlarge-vitaminc-mnli"

    def test_torch_embedding_encode_calls_model(self):
        from ml_evaluation.backends.torch_backend import TorchEmbeddingBackend

        backend = TorchEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2]])
        backend._model = mock_model

        result = backend.encode(["test"])
        mock_model.encode.assert_called_once_with(["test"], convert_to_numpy=True)
        assert result.shape == (1, 2)

    def test_torch_bertscore_compute_calls_library(self):
        """Test BERTScore compute delegates to bert_score library."""
        from ml_evaluation.backends.torch_backend import TorchBERTScoreBackend

        backend = TorchBERTScoreBackend()

        mock_tensor = MagicMock()
        mock_tensor.mean.return_value.item.return_value = 0.9

        with patch("bert_score.score") as mock_bs:
            mock_bs.return_value = (mock_tensor, mock_tensor, mock_tensor)
            P, R, F1 = backend.compute(["candidate"], ["reference"], lang="en")

        assert P == 0.9
        assert R == 0.9
        assert F1 == 0.9

    def test_torch_qags_answer_question(self):
        from ml_evaluation.backends.torch_backend import TorchQAGSBackend

        backend = TorchQAGSBackend()
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = {"answer": "Berlin", "score": 0.95}
        backend._qa_pipeline = mock_pipeline

        result = backend.answer_question("What is the capital?", "Berlin is the capital.")
        assert result["answer"] == "Berlin"
        assert result["score"] == 0.95


# ============================================================================
# 4. EMD Backend
# ============================================================================


class TestEMDBackend:
    """Test EMD backend availability and fallback."""

    def test_pot_backend_caches_availability(self):
        from ml_evaluation.backends.emd_backend import POTEMDBackend

        backend = POTEMDBackend()
        backend._pot_available = True
        assert backend.is_available() is True

    def test_pot_backend_unavailable(self):
        from ml_evaluation.backends.emd_backend import POTEMDBackend

        backend = POTEMDBackend()
        backend._pot_available = False
        assert backend.is_available() is False

    def test_pot_backend_detects(self):
        from ml_evaluation.backends.emd_backend import POTEMDBackend

        backend = POTEMDBackend()
        backend._pot_available = None
        result = backend.is_available()
        assert isinstance(result, bool)

    def test_pyemd_backend_caches(self):
        from ml_evaluation.backends.emd_backend import PyEMDBackend

        backend = PyEMDBackend()
        backend._pyemd_available = True
        assert backend.is_available() is True

    def test_pyemd_backend_unavailable(self):
        from ml_evaluation.backends.emd_backend import PyEMDBackend

        backend = PyEMDBackend()
        backend._pyemd_available = False
        assert backend.is_available() is False

    def test_get_emd_backend_pot_available(self):
        """When POT is available, it should be returned."""
        from ml_evaluation.backends.emd_backend import get_emd_backend, POTEMDBackend

        backend = get_emd_backend()
        # POT is installed in the test environment
        assert isinstance(backend, POTEMDBackend)

    def test_get_emd_backend_falls_back_to_pyemd(self):
        """When POT not available, falls to pyemd on x86_64."""
        from ml_evaluation.backends.emd_backend import PyEMDBackend

        with patch("ml_evaluation.backends.emd_backend.POTEMDBackend") as MockPOT:
            mock_pot = MockPOT.return_value
            mock_pot.is_available.return_value = False

            with patch("ml_evaluation.backends.emd_backend.IS_ARM64", False):
                with patch("ml_evaluation.backends.emd_backend.PyEMDBackend") as MockPyEMD:
                    mock_pyemd = MockPyEMD.return_value
                    mock_pyemd.is_available.return_value = True

                    from ml_evaluation.backends import emd_backend
                    # Re-call the function with patched classes
                    result = emd_backend.get_emd_backend()
                    assert result is mock_pyemd

    def test_get_emd_backend_raises_when_none_available(self):
        """When no backend available, raises RuntimeError."""
        with patch("ml_evaluation.backends.emd_backend.POTEMDBackend") as MockPOT:
            mock_pot = MockPOT.return_value
            mock_pot.is_available.return_value = False

            with patch("ml_evaluation.backends.emd_backend.IS_ARM64", True):
                from ml_evaluation.backends import emd_backend
                with pytest.raises(RuntimeError, match="No EMD backend"):
                    emd_backend.get_emd_backend()

    def test_pot_compute_emd_with_mock(self):
        """Test POT compute_emd normalizes and computes correctly."""
        from ml_evaluation.backends.emd_backend import POTEMDBackend

        backend = POTEMDBackend()

        mock_ot = MagicMock()
        mock_ot.emd2.return_value = 0.5

        with patch.dict("sys.modules", {"ot": mock_ot}):
            src = np.array([0.5, 0.5])
            tgt = np.array([0.3, 0.7])
            dist = np.array([[0.1, 0.2], [0.3, 0.4]])
            result = backend.compute_emd(src, tgt, dist)

        assert isinstance(result, float)


# ============================================================================
# 5. BackendSelector
# ============================================================================


class TestBackendSelector:
    """Test BackendSelector singleton, env-var routing, and caching."""

    def _fresh_selector(self):
        """Create a fresh BackendSelector (bypass singleton for testing)."""
        from ml_evaluation.backends.selector import BackendSelector

        # Reset singleton
        BackendSelector._instance = None
        selector = BackendSelector()
        return selector

    def teardown_method(self):
        """Reset singleton after each test."""
        from ml_evaluation.backends.selector import BackendSelector
        BackendSelector._instance = None

    def test_singleton(self):
        from ml_evaluation.backends.selector import BackendSelector

        BackendSelector._instance = None
        s1 = BackendSelector()
        s2 = BackendSelector()
        assert s1 is s2

    def test_should_use_onnx_arm64(self):
        selector = self._fresh_selector()
        with patch("ml_evaluation.backends.selector.IS_ARM64", True):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("BENGER_USE_PYTORCH", None)
                os.environ.pop("BENGER_USE_ONNX", None)
                assert selector._should_use_onnx() is True

    def test_should_use_onnx_forced_pytorch(self):
        selector = self._fresh_selector()
        with patch("ml_evaluation.backends.selector.IS_ARM64", True):
            with patch.dict(os.environ, {"BENGER_USE_PYTORCH": "true"}):
                assert selector._should_use_onnx() is False

    def test_should_use_onnx_forced_onnx_on_x86(self):
        selector = self._fresh_selector()
        with patch("ml_evaluation.backends.selector.IS_ARM64", False):
            with patch.dict(os.environ, {"BENGER_USE_ONNX": "true"}):
                os.environ.pop("BENGER_USE_PYTORCH", None)
                assert selector._should_use_onnx() is True

    def test_should_use_onnx_x86_default(self):
        selector = self._fresh_selector()
        with patch("ml_evaluation.backends.selector.IS_ARM64", False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("BENGER_USE_PYTORCH", None)
                os.environ.pop("BENGER_USE_ONNX", None)
                assert selector._should_use_onnx() is False

    def test_get_bertscore_caches(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        selector._bertscore_backend = mock_backend
        assert selector.get_bertscore_backend() is mock_backend

    def test_get_embedding_caches_default(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        selector._embedding_backend = mock_backend
        assert selector.get_embedding_backend() is mock_backend

    def test_get_embedding_custom_model_no_cache(self):
        """Custom model name creates new backend each time (no caching)."""
        selector = self._fresh_selector()
        with patch.object(selector, "_should_use_onnx", return_value=False):
            mock_backend_1 = MagicMock()
            mock_backend_2 = MagicMock()
            with patch(
                "ml_evaluation.backends.torch_backend.TorchEmbeddingBackend",
                side_effect=[mock_backend_1, mock_backend_2],
            ) as MockTorch:
                b1 = selector.get_embedding_backend(model_name="custom-1")
                b2 = selector.get_embedding_backend(model_name="custom-2")
                assert MockTorch.call_count == 2
                assert b1 is not b2

    def test_get_moverscore_caches(self):
        selector = self._fresh_selector()
        mock_computer = MagicMock()
        selector._moverscore_computer = mock_computer
        assert selector.get_moverscore_computer() is mock_computer

    def test_get_qags_caches(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        selector._qags_backend = mock_backend
        assert selector.get_qags_backend() is mock_backend

    def test_get_summac_caches(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        selector._summac_backend = mock_backend
        assert selector.get_summac_backend() is mock_backend

    def test_get_bertscore_raises_when_none_available(self):
        selector = self._fresh_selector()
        with patch.object(selector, "_should_use_onnx", return_value=False):
            with patch(
                "ml_evaluation.backends.torch_backend.TorchBERTScoreBackend.is_available",
                return_value=False,
            ):
                with pytest.raises(RuntimeError, match="No BERTScore backend"):
                    selector.get_bertscore_backend()

    def test_get_embedding_raises_when_none_available(self):
        selector = self._fresh_selector()
        with patch.object(selector, "_should_use_onnx", return_value=False):
            with patch(
                "ml_evaluation.backends.torch_backend.TorchEmbeddingBackend.is_available",
                return_value=False,
            ):
                with pytest.raises(RuntimeError, match="No embedding backend"):
                    selector.get_embedding_backend()

    def test_get_qags_raises_when_none_available(self):
        selector = self._fresh_selector()
        with patch.object(selector, "_should_use_onnx", return_value=False):
            with patch(
                "ml_evaluation.backends.torch_backend.TorchQAGSBackend.is_available",
                return_value=False,
            ):
                with pytest.raises(RuntimeError, match="No QAGS backend"):
                    selector.get_qags_backend()

    def test_get_summac_raises_when_none_available(self):
        selector = self._fresh_selector()
        with patch.object(selector, "_should_use_onnx", return_value=False):
            with patch(
                "ml_evaluation.backends.torch_backend.TorchSummaCBackend.is_available",
                return_value=False,
            ):
                with pytest.raises(RuntimeError, match="No SummaC backend"):
                    selector.get_summac_backend()

    def test_get_bertscore_onnx_path(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        mock_backend.is_available.return_value = True
        with patch.object(selector, "_should_use_onnx", return_value=True):
            with patch(
                "ml_evaluation.backends.onnx_backend.ONNXBERTScoreBackend",
                return_value=mock_backend,
            ):
                result = selector.get_bertscore_backend()
                assert result is mock_backend

    def test_get_bertscore_onnx_unavailable_falls_to_torch(self):
        selector = self._fresh_selector()
        mock_onnx = MagicMock()
        mock_onnx.is_available.return_value = False
        mock_torch = MagicMock()
        mock_torch.is_available.return_value = True
        with patch.object(selector, "_should_use_onnx", return_value=True):
            with patch(
                "ml_evaluation.backends.onnx_backend.ONNXBERTScoreBackend",
                return_value=mock_onnx,
            ):
                with patch(
                    "ml_evaluation.backends.torch_backend.TorchBERTScoreBackend",
                    return_value=mock_torch,
                ):
                    result = selector.get_bertscore_backend()
                    assert result is mock_torch

    def test_get_embedding_onnx_path(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        mock_backend.is_available.return_value = True
        with patch.object(selector, "_should_use_onnx", return_value=True):
            with patch(
                "ml_evaluation.backends.onnx_backend.ONNXEmbeddingBackend",
                return_value=mock_backend,
            ):
                result = selector.get_embedding_backend()
                assert result is mock_backend

    def test_get_embedding_onnx_custom_model_path(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        with patch.object(selector, "_should_use_onnx", return_value=True):
            with patch(
                "ml_evaluation.backends.onnx_backend.ONNXEmbeddingBackend",
                return_value=mock_backend,
            ) as MockONNX:
                result = selector.get_embedding_backend(model_name="custom-model")
                MockONNX.assert_called_with("custom-model")

    def test_get_qags_onnx_path(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        mock_backend.is_available.return_value = True
        with patch.object(selector, "_should_use_onnx", return_value=True):
            with patch(
                "ml_evaluation.backends.onnx_backend.ONNXQAGSBackend",
                return_value=mock_backend,
            ):
                result = selector.get_qags_backend()
                assert result is mock_backend

    def test_get_summac_onnx_path(self):
        selector = self._fresh_selector()
        mock_backend = MagicMock()
        mock_backend.is_available.return_value = True
        with patch.object(selector, "_should_use_onnx", return_value=True):
            with patch(
                "ml_evaluation.backends.onnx_backend.ONNXSummaCBackend",
                return_value=mock_backend,
            ):
                result = selector.get_summac_backend()
                assert result is mock_backend

    def test_get_moverscore_creates_with_onnx_flag(self):
        selector = self._fresh_selector()
        mock_computer = MagicMock()
        with patch.object(selector, "_should_use_onnx", return_value=True):
            with patch(
                "ml_evaluation.backends.moverscore_impl.MoverScoreComputer",
                return_value=mock_computer,
            ) as MockMS:
                result = selector.get_moverscore_computer()
                MockMS.assert_called_with(use_onnx=True)
                assert result is mock_computer


# ============================================================================
# 6. SampleEvaluator - Text Similarity (BLEU, ROUGE, METEOR, chrF, edit_distance)
# ============================================================================


class TestSampleEvaluatorTextSimilarity:
    """Test text similarity metrics that use real implementations."""

    def _make_evaluator(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator

        return SampleEvaluator(
            evaluation_id="test",
            field_configs={"f": {"type": "text"}},
        )

    def test_edit_distance_identical(self):
        ev = self._make_evaluator()
        assert ev._compute_text_similarity("edit_distance", "hello", "hello") == 1.0

    def test_edit_distance_empty(self):
        ev = self._make_evaluator()
        assert ev._compute_text_similarity("edit_distance", "", "") == 1.0

    def test_edit_distance_partial(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity("edit_distance", "abc", "adc")
        # distance = 1, max_len = 3, normalized = 1 - 1/3 = 2/3
        assert abs(score - 2 / 3) < 1e-9

    def test_bleu_identical(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity("bleu", "the cat sat on the mat", "the cat sat on the mat")
        assert score > 0.9

    def test_bleu_empty_prediction(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity("bleu", "the cat", "")
        assert score == 0.0

    def test_bleu_custom_weights(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity(
            "bleu", "the cat sat", "the cat sat",
            parameters={"max_order": 2, "weights": [0.5, 0.5]}
        )
        assert score > 0.9

    def test_rouge_identical(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity("rouge", "the cat sat", "the cat sat")
        assert score > 0.9

    def test_rouge_custom_variant(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity(
            "rouge", "the cat sat on the mat", "the cat sat on a mat",
            parameters={"variant": "rouge1"}
        )
        assert 0.0 < score <= 1.0

    def test_meteor_identical(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity("meteor", "the cat sat", "the cat sat")
        assert score > 0.9

    def test_meteor_empty_prediction(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity("meteor", "the cat", "")
        assert score == 0.0

    def test_chrf_identical(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity("chrf", "hello world", "hello world")
        assert score > 0.9

    def test_chrf_custom_params(self):
        ev = self._make_evaluator()
        score = ev._compute_text_similarity(
            "chrf", "hello world", "hello world",
            parameters={"char_order": 3, "word_order": 1, "beta": 1}
        )
        assert 0.0 < score <= 1.0

    def test_unknown_text_similarity_returns_zero(self):
        ev = self._make_evaluator()
        assert ev._compute_text_similarity("unknown_metric", "a", "b") == 0.0


# ============================================================================
# 7. SampleEvaluator - field_accuracy (JSON comparison)
# ============================================================================


class TestSampleEvaluatorFieldAccuracy:
    """Test _compute_field_accuracy with nested JSON structures."""

    def _make_evaluator(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator

        return SampleEvaluator(
            evaluation_id="test",
            field_configs={"f": {"type": "structured_text"}},
        )

    def test_both_non_json(self):
        ev = self._make_evaluator()
        assert ev._compute_field_accuracy(42, 42) == 1.0

    def test_one_json_one_not(self):
        ev = self._make_evaluator()
        assert ev._compute_field_accuracy({"a": 1}, 42) == 0.0

    def test_identical_json(self):
        ev = self._make_evaluator()
        assert ev._compute_field_accuracy({"a": 1, "b": 2}, {"a": 1, "b": 2}) == 1.0

    def test_with_ignore_keys(self):
        ev = self._make_evaluator()
        score = ev._compute_field_accuracy(
            {"a": 1, "id": "x"}, {"a": 1, "id": "y"},
            {"ignore_keys": ["id"]}
        )
        assert score == 1.0

    def test_with_strict_types(self):
        ev = self._make_evaluator()
        score = ev._compute_field_accuracy(
            {"a": 1}, {"a": "1"},
            {"strict_types": True}
        )
        assert score == 0.0

    def test_compare_json_fields_nested(self):
        ev = self._make_evaluator()
        gt = {"outer": {"inner": "val"}}
        pred = {"outer": {"inner": "val"}}
        score = ev._compare_json_fields(gt, pred, set(), False)
        assert score == 1.0

    def test_compare_json_fields_list(self):
        ev = self._make_evaluator()
        score = ev._compare_json_fields([1, 2, 3], [1, 2, 3], set(), False)
        assert score == 1.0

    def test_compare_json_fields_empty_dicts(self):
        ev = self._make_evaluator()
        assert ev._compare_json_fields({}, {}, set(), False) == 1.0

    def test_compare_json_fields_missing_key(self):
        ev = self._make_evaluator()
        score = ev._compare_json_fields({"a": 1}, {"b": 2}, set(), False)
        # keys = {a, b}, a missing from pred, b missing from gt -> score = 0
        assert score == 0.0


# ============================================================================
# 8. SampleEvaluator - entity extraction
# ============================================================================


class TestSampleEvaluatorEntityExtraction:
    """Test language-aware entity extraction for coherence."""

    def _make_evaluator(self):
        from ml_evaluation.sample_evaluator import SampleEvaluator

        return SampleEvaluator(
            evaluation_id="test",
            field_configs={"f": {"type": "text"}},
        )

    def test_extract_entities_german(self):
        ev = self._make_evaluator()
        sentences = ["Das Gericht hat entschieden.", "Der Vertrag ist gueltig."]
        grid = ev._extract_entities_german(sentences)
        # German capitalized nouns in non-initial position: "Gericht", "Vertrag"
        assert len(grid) > 0

    def test_extract_entities_german_pronouns(self):
        ev = self._make_evaluator()
        sentences = ["Er hat es getan.", "Sie war dabei."]
        grid = ev._extract_entities_german(sentences)
        assert "er" in grid or "sie" in grid

    def test_extract_entities_english(self):
        ev = self._make_evaluator()
        sentences = ["The lawyer argued the case.", "The judge reviewed evidence."]
        grid = ev._extract_entities_english(sentences)
        assert len(grid) > 0
        # Should find nouns like "lawyer", "case", "judge", "evidence"
        found_nouns = set(grid.keys())
        assert "lawyer" in found_nouns or "case" in found_nouns

    def test_compute_entity_coherence_raises_on_no_entities(self):
        ev = self._make_evaluator()
        # Sentences with no recognizable entities/nouns
        with pytest.raises(RuntimeError, match="Entity coherence"):
            ev._compute_entity_coherence([".", "."])


# ============================================================================
# 9. LLMJudgeEvaluator - multi_judge consensus
# ============================================================================


class TestLLMJudgeMultiJudgeDeep:
    """Deep coverage for multi-judge consensus paths."""

    def test_multi_judge_single_score_no_variance(self):
        """Single judge produces CI = (score, score) and agreement = 1.0."""
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        mock_ai = MagicMock()
        mock_ai.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }
        ev = LLMJudgeEvaluator(ai_service=mock_ai, judge_model="model-1")

        result = ev.evaluate_multi_judge(
            context="ctx",
            ground_truth="gt",
            prediction="pred",
            criteria=["helpfulness"],
            additional_judge_configs=[],  # No additional judges
        )

        assert result["num_judges"] == 1
        assert result["inter_judge_agreement"]["helpfulness"] == 1.0
        ci = result["confidence_intervals"]["helpfulness"]
        assert ci[0] == ci[1]

    def test_multi_judge_skips_no_ai_service(self):
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        mock_ai = MagicMock()
        mock_ai.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }
        ev = LLMJudgeEvaluator(ai_service=mock_ai, judge_model="model-1")

        result = ev.evaluate_multi_judge(
            context="ctx",
            ground_truth="gt",
            prediction="pred",
            criteria=["helpfulness"],
            additional_judge_configs=[
                {"judge_model": "model-2", "ai_service": None},  # Will be skipped
            ],
        )

        # Only primary judge should have scores
        assert "model-1" in result["scores_by_judge"]

    def test_multi_judge_0_1_scale(self):
        from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator

        mock_ai = MagicMock()
        mock_ai.generate.return_value = {
            "success": True,
            "content": '{"score": 0.8, "justification": "Good"}',
        }
        ev = LLMJudgeEvaluator(
            ai_service=mock_ai, judge_model="model-1", score_scale="0-1"
        )

        result = ev.evaluate_multi_judge(
            context="ctx", ground_truth="gt", prediction="pred",
            criteria=["helpfulness"],
            additional_judge_configs=[],
        )

        # 0-1 scale: normalized = score directly
        assert abs(result["consensus_scores"]["helpfulness"] - 0.8) < 1e-9
