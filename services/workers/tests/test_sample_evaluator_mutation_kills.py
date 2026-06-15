"""Mutation-kill tests for ml_evaluation/sample_evaluator.py.

Each test here exists to KILL a specific surviving mutant from the mutmut
baseline (the meaningful-coverage program / mutation co-gate). A killing test
asserts the EXACT value, boundary, operator, or formula constant the mutation
changes — not merely that a line executes. Expected values are HAND-COMPUTED in
each test docstring so a flipped operator / wrong constant / off-by-one fails.

SCOPE — only the cheap, DETERMINISTIC, no-model-download metrics are tested,
dispatched through ``_compute_metric_legacy`` (the legacy if/elif chain that
``_compute_metric`` resolves to for platform built-ins) and their pure helper
methods:

    exact_match, accuracy, confusion_matrix, precision, recall, f1, cohen_kappa,
    token_f1, jaccard, hamming_loss, subset_accuracy, mae, rmse, mape,
    edit_distance (Levenshtein), json_accuracy, schema_validation,
    field_accuracy, span_exact_match, iou, partial_match, boundary_accuracy,
    hierarchical_f1, path_accuracy, lca_accuracy, map (ranking), korrektur_* no-op.

EXCLUDED by design (model/corpus download): bertscore, moverscore,
semantic_similarity, factcc, qags, coherence, bleu, rouge, meteor, chrf,
spearman/kendall/ndcg (scipy/sklearn aggregate-only paths are not asserted to a
fixed value here — covered by the property suite where bounded).
"""

import math
import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.sample_evaluator import SampleEvaluator  # noqa: E402


@pytest.fixture
def ev():
    return SampleEvaluator(evaluation_id="mut-test", field_configs={})


def legacy(ev, metric, gt, pred, answer_type="text", params=None):
    """Dispatch through the legacy chain exactly like _compute_metric does.

    NOTE: _compute_metric_legacy does NOT re-normalize — callers pass already
    normalized gt/pred. We pre-normalize here to mirror _compute_metric so the
    branch under test sees what production sees.
    """
    gt_n = ev._normalize_value(gt, answer_type)
    pred_n = ev._normalize_value(pred, answer_type)
    return ev._compute_metric_legacy(metric, gt_n, pred_n, answer_type, params or {})


# ============================================================================
# exact_match / accuracy / confusion_matrix / classification binary (0/1)
#   Mutants: `1.0 if gt == pred else 0.0` -> flip ==/!=, swap return constants.
# ============================================================================


def test_exact_match_equal_is_one(ev):
    """gt == pred -> 1.0. Kills `== -> !=` and `1.0 -> 0.0` return swap."""
    assert legacy(ev, "exact_match", "abc", "abc") == 1.0


def test_exact_match_unequal_is_zero(ev):
    """gt != pred -> 0.0. Kills the else-branch constant `0.0 -> 1.0`."""
    assert legacy(ev, "exact_match", "abc", "xyz") == 0.0


def test_exact_match_is_case_insensitive_after_normalize(ev):
    """Normalize lowercases+strips, so 'ABC ' == 'abc' -> 1.0."""
    assert legacy(ev, "exact_match", "ABC ", "abc") == 1.0


def test_accuracy_equal_unequal(ev):
    assert legacy(ev, "accuracy", "yes", "yes") == 1.0
    assert legacy(ev, "accuracy", "yes", "no") == 0.0


def test_confusion_matrix_single_sample_binary(ev):
    assert legacy(ev, "confusion_matrix", "x", "x") == 1.0
    assert legacy(ev, "confusion_matrix", "x", "y") == 0.0


@pytest.mark.parametrize("metric", ["precision", "recall", "f1", "cohen_kappa"])
def test_classification_binary_correct(ev, metric):
    """Single-sample classification metrics are 1.0 iff gt == pred."""
    assert legacy(ev, metric, "a", "a") == 1.0
    assert legacy(ev, metric, "a", "b") == 0.0


# ============================================================================
# jaccard  =  |gt ∩ pred| / |gt ∪ pred|
#   Hand: gt={a,b,c}, pred={b,c,d} -> ∩={b,c}=2, ∪={a,b,c,d}=4 -> 0.5
# ============================================================================


def test_jaccard_known_value(ev):
    """{a,b,c} vs {b,c,d}: 2/4 = 0.5. Kills intersection/union swap, & -> |."""
    val = ev._compute_set_metric("jaccard", ["a", "b", "c"], ["b", "c", "d"])
    assert val == pytest.approx(0.5)


def test_jaccard_disjoint_is_zero(ev):
    """{a,b} vs {c,d}: 0/4 = 0.0."""
    assert ev._compute_set_metric("jaccard", ["a", "b"], ["c", "d"]) == 0.0


def test_jaccard_identical_is_one(ev):
    assert ev._compute_set_metric("jaccard", ["a", "b"], ["a", "b"]) == 1.0


def test_jaccard_both_empty_is_one(ev):
    """Both empty = perfect match = 1.0 (kills `return 1.0 -> 0.0` on the guard)."""
    assert ev._compute_set_metric("jaccard", [], []) == 1.0


def test_jaccard_one_empty_is_zero(ev):
    """One empty, one non-empty -> 0.0 (kills the `not gt or not pred` guard)."""
    assert ev._compute_set_metric("jaccard", [], ["a"]) == 0.0
    assert ev._compute_set_metric("jaccard", ["a"], []) == 0.0


def test_jaccard_subset_value(ev):
    """{a,b,c,d} vs {a,b}: ∩=2, ∪=4 -> 0.5."""
    assert ev._compute_set_metric("jaccard", ["a", "b", "c", "d"], ["a", "b"]) == pytest.approx(0.5)


# ============================================================================
# hamming_loss = |gt △ pred| / |gt ∪ pred|   (symmetric diff over union)
#   Hand: gt={a,b,c}, pred={b,c,d} -> △={a,d}=2, all={a,b,c,d}=4 -> 0.5
# ============================================================================


def test_hamming_loss_known_value(ev):
    """{a,b,c} vs {b,c,d}: |△|=2 / |∪|=4 = 0.5. Kills ^ -> & and num/den swap."""
    val = ev._compute_set_metric("hamming_loss", ["a", "b", "c"], ["b", "c", "d"])
    assert val == pytest.approx(0.5)


def test_hamming_loss_identical_is_zero(ev):
    """No symmetric diff -> 0.0 loss."""
    assert ev._compute_set_metric("hamming_loss", ["a", "b"], ["a", "b"]) == 0.0


def test_hamming_loss_disjoint_is_one(ev):
    """{a,b} vs {c,d}: △={a,b,c,d}=4, ∪=4 -> 1.0 (total loss)."""
    assert ev._compute_set_metric("hamming_loss", ["a", "b"], ["c", "d"]) == 1.0


def test_hamming_loss_both_empty_is_zero(ev):
    """Both empty -> no loss -> 0.0 (kills the guard `return 0.0 -> 1.0`)."""
    assert ev._compute_set_metric("hamming_loss", [], []) == 0.0


def test_hamming_loss_one_extra_label(ev):
    """{a} vs {a,b}: △={b}=1, ∪={a,b}=2 -> 0.5."""
    assert ev._compute_set_metric("hamming_loss", ["a"], ["a", "b"]) == pytest.approx(0.5)


# ============================================================================
# subset_accuracy = exact set match
# ============================================================================


def test_subset_accuracy_exact(ev):
    assert ev._compute_set_metric("subset_accuracy", ["a", "b"], ["b", "a"]) == 1.0


def test_subset_accuracy_mismatch(ev):
    assert ev._compute_set_metric("subset_accuracy", ["a", "b"], ["a"]) == 0.0


# ============================================================================
# token_f1 = 2PR/(P+R) over token SETS (lowercased, whitespace split)
#   Hand: gt="the cat sat", pred="the dog sat"
#     gt_tok={the,cat,sat}=3, pred_tok={the,dog,sat}=3, ∩={the,sat}=2
#     P = 2/3, R = 2/3, F1 = 2*(4/9)/(4/3) = (8/9)/(4/3) = 2/3
# ============================================================================


def test_token_f1_known_value(ev):
    """2/3 exactly. Kills the 2* constant, P/R denominators, and P+R==0 guard."""
    val = ev._compute_token_f1("the cat sat", "the dog sat")
    assert val == pytest.approx(2.0 / 3.0)


def test_token_f1_asymmetric_lengths(ev):
    """gt="a b" (2), pred="a b c d" (4), ∩={a,b}=2.
    P=2/4=0.5, R=2/2=1.0, F1=2*(0.5)/(1.5)=2/3."""
    val = ev._compute_token_f1("a b", "a b c d")
    assert val == pytest.approx(2.0 / 3.0)


def test_token_f1_no_overlap_is_zero(ev):
    """Disjoint tokens -> P+R==0 -> 0.0 (kills the `precision + recall == 0` guard)."""
    assert ev._compute_token_f1("a b", "c d") == 0.0


def test_token_f1_identical_is_one(ev):
    assert ev._compute_token_f1("same words here", "same words here") == 1.0


def test_token_f1_both_empty_is_one(ev):
    assert ev._compute_token_f1("", "") == 1.0


def test_token_f1_one_empty_is_zero(ev):
    assert ev._compute_token_f1("a b", "") == 0.0


def test_token_f1_case_insensitive(ev):
    """Lowercased internally -> 'The CAT' matches 'the cat' fully = 1.0."""
    assert ev._compute_token_f1("The CAT", "the cat") == 1.0


# ============================================================================
# edit_distance metric = 1 - lev(gt,pred)/max_len   (via _compute_text_similarity)
#   Hand: gt="kitten", pred="sitting" -> lev=3, max_len=7 -> 1 - 3/7 = 4/7
# ============================================================================


def test_edit_distance_known_value(ev):
    """kitten/sitting: lev=3, maxlen=7 -> 4/7. Kills `1.0 -` and the / max_len."""
    val = ev._compute_text_similarity("edit_distance", "kitten", "sitting")
    assert val == pytest.approx(4.0 / 7.0)


def test_edit_distance_identical_is_one(ev):
    assert ev._compute_text_similarity("edit_distance", "abcd", "abcd") == 1.0


def test_edit_distance_both_empty_is_one(ev):
    """max_len==0 short-circuit -> 1.0 (kills `return 1.0 -> 0.0`)."""
    assert ev._compute_text_similarity("edit_distance", "", "") == 1.0


def test_edit_distance_total_mismatch(ev):
    """gt="ab", pred="cd": lev=2, maxlen=2 -> 1 - 2/2 = 0.0."""
    assert ev._compute_text_similarity("edit_distance", "ab", "cd") == 0.0


def test_edit_distance_one_char_diff(ev):
    """"cat"/"car": lev=1, maxlen=3 -> 1 - 1/3 = 2/3."""
    val = ev._compute_text_similarity("edit_distance", "cat", "car")
    assert val == pytest.approx(2.0 / 3.0)


def test_edit_distance_insertion(ev):
    """"abc"/"abcd": lev=1 (one insertion), maxlen=4 -> 1 - 1/4 = 0.75."""
    val = ev._compute_text_similarity("edit_distance", "abc", "abcd")
    assert val == pytest.approx(0.75)


# ============================================================================
# _levenshtein_distance — direct integer edit distance
# ============================================================================


def test_levenshtein_kitten_sitting(ev):
    """Classic textbook value: 3."""
    assert ev._levenshtein_distance("kitten", "sitting") == 3


def test_levenshtein_empty_to_string(ev):
    """len(s2)==0 -> len(s1). 'hello' -> 5."""
    assert ev._levenshtein_distance("hello", "") == 5
    assert ev._levenshtein_distance("", "hello") == 5


def test_levenshtein_identical_is_zero(ev):
    assert ev._levenshtein_distance("abc", "abc") == 0


def test_levenshtein_single_substitution(ev):
    """'flaw' -> 'lawn' is 2 (sub f->l... actually): use a clean case.
    'cat' -> 'cut' = 1 substitution."""
    assert ev._levenshtein_distance("cat", "cut") == 1


def test_levenshtein_off_by_one_guard(ev):
    """'a' vs 'ab' = 1 (single insertion). Kills the +1 insertion/deletion drops."""
    assert ev._levenshtein_distance("a", "ab") == 1
    assert ev._levenshtein_distance("ab", "abc") == 1


# ============================================================================
# numeric metrics: mae, rmse, mape
# ============================================================================


def test_mae_absolute_error(ev):
    """|10 - 7| = 3.0. Kills abs() removal / sign flips."""
    assert ev._compute_numeric_metric("mae", "10", "7") == pytest.approx(3.0)
    assert ev._compute_numeric_metric("mae", "7", "10") == pytest.approx(3.0)


def test_rmse_equals_abs_error_per_sample(ev):
    """sqrt((10-7)^2) = 3.0."""
    assert ev._compute_numeric_metric("rmse", "10", "7") == pytest.approx(3.0)


def test_mape_known_value(ev):
    """|((100-90)/100)|*100 = 10.0 percent. Kills the *100 and the /gt."""
    assert ev._compute_numeric_metric("mape", "100", "90") == pytest.approx(10.0)


def test_mape_gt_zero_pred_nonzero(ev):
    """gt==0, pred!=0 -> 100.0 (kills the `100.0 -> 0.0` boundary constant)."""
    assert ev._compute_numeric_metric("mape", "0", "5") == 100.0


def test_mape_gt_zero_pred_zero(ev):
    """gt==0, pred==0 -> 0.0."""
    assert ev._compute_numeric_metric("mape", "0", "0") == 0.0


def test_numeric_invalid_input_returns_zero(ev):
    """Non-numeric -> 0.0 via the except branch."""
    assert ev._compute_numeric_metric("mae", "notanumber", "5") == 0.0


# ============================================================================
# json_accuracy / _json_field_accuracy
#   Hand: {"a":1,"b":2} vs {"a":1,"b":3} -> all_keys={a,b}=2, match a only -> 1/2
# ============================================================================


def test_json_accuracy_half_match(ev):
    """One of two top-level fields matches -> 0.5."""
    val = ev._compute_structured_metric(
        "json_accuracy", '{"a": 1, "b": 2}', '{"a": 1, "b": 3}'
    )
    assert val == pytest.approx(0.5)


def test_json_accuracy_full_match(ev):
    val = ev._compute_structured_metric(
        "json_accuracy", '{"a": 1, "b": 2}', '{"a": 1, "b": 2}'
    )
    assert val == 1.0


def test_json_accuracy_extra_key_lowers_score(ev):
    """gt has {a}, pred has {a,b}: all_keys=2, a matches (b only in pred, not counted) -> 1/2."""
    val = ev._compute_structured_metric(
        "json_accuracy", '{"a": 1}', '{"a": 1, "b": 9}'
    )
    assert val == pytest.approx(0.5)


def test_json_accuracy_both_nonjson_is_one(ev):
    """Two non-JSON strings -> both parse None -> 1.0."""
    assert ev._compute_structured_metric("json_accuracy", "plain text", "other text") == 1.0


def test_json_accuracy_one_json_one_not_is_zero(ev):
    assert ev._compute_structured_metric("json_accuracy", '{"a": 1}', "not json") == 0.0


def test_json_field_accuracy_type_mismatch_is_zero(ev):
    """dict vs list -> type mismatch -> 0.0."""
    assert ev._json_field_accuracy({"a": 1}, [1, 2]) == 0.0


def test_json_field_accuracy_list_length_mismatch_is_zero(ev):
    assert ev._json_field_accuracy([1, 2, 3], [1, 2]) == 0.0


def test_json_field_accuracy_list_partial(ev):
    """[1,2,3] vs [1,9,3]: 2 of 3 match -> 2/3."""
    assert ev._json_field_accuracy([1, 2, 3], [1, 9, 3]) == pytest.approx(2.0 / 3.0)


def test_json_field_accuracy_nested(ev):
    """{"x":{"a":1,"b":2}} vs {"x":{"a":1,"b":9}}: x recurses -> 1/2; top all_keys=1 -> 0.5."""
    val = ev._json_field_accuracy({"x": {"a": 1, "b": 2}}, {"x": {"a": 1, "b": 9}})
    assert val == pytest.approx(0.5)


def test_json_field_accuracy_empty_dicts_is_one(ev):
    assert ev._json_field_accuracy({}, {}) == 1.0


# ============================================================================
# schema_validation
# ============================================================================


def test_schema_validation_no_schema_valid_json(ev):
    """No schema + valid JSON -> 1.0."""
    assert ev._compute_structured_metric("schema_validation", "{}", '{"a": 1}') == 1.0


def test_schema_validation_no_schema_invalid_json(ev):
    """No schema + non-JSON pred -> 0.0."""
    assert ev._compute_structured_metric("schema_validation", "{}", "not json") == 0.0


def test_schema_validation_valid_against_schema(ev):
    schema = {"type": "object", "properties": {"a": {"type": "number"}}, "required": ["a"]}
    val = ev._compute_structured_metric(
        "schema_validation", "{}", '{"a": 1}', {"schema": schema}
    )
    assert val == 1.0


def test_schema_validation_invalid_against_schema(ev):
    """Required key missing -> ValidationError -> 0.0."""
    schema = {"type": "object", "properties": {"a": {"type": "number"}}, "required": ["a"]}
    val = ev._compute_structured_metric(
        "schema_validation", "{}", '{"b": 1}', {"schema": schema}
    )
    assert val == 0.0


# ============================================================================
# span metrics: span_exact_match, iou (_span_iou, _calculate_span_overlap)
# ============================================================================


def test_span_exact_match_equal(ev):
    g = [{"start": 0, "end": 5}]
    assert ev._compute_span_metric("exact_match", g, [{"start": 0, "end": 5}]) == 1.0


def test_span_exact_match_unequal(ev):
    assert ev._compute_span_metric(
        "exact_match", [{"start": 0, "end": 5}], [{"start": 1, "end": 5}]
    ) == 0.0


def test_span_iou_known_value(ev):
    """span [0,10] vs [5,15]: inter=5 ([5,10]), union=10+10-5=15 -> 5/15 = 1/3.
    Single span pair -> total_iou/max(1,1) = 1/3."""
    val = ev._compute_span_metric(
        "iou", [{"start": 0, "end": 10}], [{"start": 5, "end": 15}]
    )
    assert val == pytest.approx(1.0 / 3.0)


def test_span_iou_identical_is_one(ev):
    assert ev._compute_span_metric(
        "iou", [{"start": 2, "end": 8}], [{"start": 2, "end": 8}]
    ) == 1.0


def test_span_iou_disjoint_is_zero(ev):
    """[0,5] vs [10,15]: no overlap -> 0.0."""
    assert ev._compute_span_metric(
        "iou", [{"start": 0, "end": 5}], [{"start": 10, "end": 15}]
    ) == 0.0


def test_span_iou_both_empty_is_one(ev):
    assert ev._compute_span_metric("iou", [], []) == 1.0


def test_span_iou_one_empty_is_zero(ev):
    assert ev._compute_span_metric("iou", [{"start": 0, "end": 5}], []) == 0.0


def test_span_iou_direct_half(ev):
    """_span_iou [0,10] vs [0,5]: inter=5, union=10+5-5=10 -> 0.5."""
    assert ev._span_iou({"start": 0, "end": 10}, {"start": 0, "end": 5}) == pytest.approx(0.5)


def test_span_iou_adjacent_no_overlap(ev):
    """[0,5] vs [5,10]: inter = max(0, 5-5)=0 -> 0.0 (kills the max(0,...) clamp)."""
    assert ev._span_iou({"start": 0, "end": 5}, {"start": 5, "end": 10}) == 0.0


# ============================================================================
# partial_match (_calculate_span_overlap relative to GT length)
#   Hand: gt [0,10], pred [5,15]: inter=5, gt_len=10 -> 0.5
# ============================================================================


def test_partial_match_overlap_ratio(ev):
    """One GT span [0,10], pred [5,15]: overlap=5/10=0.5; /len(gt)=1 -> 0.5."""
    val = ev._compute_partial_match([{"start": 0, "end": 10}], [{"start": 5, "end": 15}])
    assert val == pytest.approx(0.5)


def test_partial_match_full_overlap_is_one(ev):
    val = ev._compute_partial_match([{"start": 0, "end": 10}], [{"start": 0, "end": 10}])
    assert val == 1.0


def test_partial_match_both_empty_is_one(ev):
    assert ev._compute_partial_match([], []) == 1.0


def test_partial_match_one_empty_is_zero(ev):
    assert ev._compute_partial_match([{"start": 0, "end": 5}], []) == 0.0


def test_partial_match_min_overlap_threshold_zeroes(ev):
    """overlap 0.5 < min_overlap 0.6 -> 0.0 (kills `>= min_overlap` operator)."""
    val = ev._compute_partial_match(
        [{"start": 0, "end": 10}],
        [{"start": 5, "end": 15}],
        {"min_overlap": 0.6},
    )
    assert val == 0.0


def test_partial_match_min_overlap_boundary_kept(ev):
    """overlap 0.5 >= min_overlap 0.5 -> kept (boundary is inclusive)."""
    val = ev._compute_partial_match(
        [{"start": 0, "end": 10}],
        [{"start": 5, "end": 15}],
        {"min_overlap": 0.5},
    )
    assert val == pytest.approx(0.5)


def test_calculate_span_overlap_relative_to_gt(ev):
    """gt [0,4], pred [2,10]: inter=2, gt_len=4 -> 0.5 (denominator is GT length)."""
    val = ev._calculate_span_overlap({"start": 0, "end": 4}, {"start": 2, "end": 10})
    assert val == pytest.approx(0.5)


# ============================================================================
# boundary_accuracy (_calculate_boundary_score: 0.0 / 0.5 / 1.0)
# ============================================================================


def test_boundary_score_both_match_is_one(ev):
    val = ev._calculate_boundary_score({"start": 0, "end": 5}, {"start": 0, "end": 5}, 0)
    assert val == 1.0


def test_boundary_score_one_match_is_half(ev):
    """start matches, end off -> 0.5 (kills the 0.5 constant + and/or branch swap)."""
    val = ev._calculate_boundary_score({"start": 0, "end": 5}, {"start": 0, "end": 9}, 0)
    assert val == 0.5


def test_boundary_score_no_match_is_zero(ev):
    val = ev._calculate_boundary_score({"start": 0, "end": 5}, {"start": 3, "end": 9}, 0)
    assert val == 0.0


def test_boundary_score_tolerance_inclusive(ev):
    """|0-2|=2 <= tolerance 2 -> start matches; end |5-5|=0 matches -> 1.0.
    Kills `<= -> <` on the tolerance comparison."""
    val = ev._calculate_boundary_score({"start": 0, "end": 5}, {"start": 2, "end": 5}, 2)
    assert val == 1.0


def test_boundary_score_tolerance_exceeded(ev):
    """|0-3|=3 > tolerance 2 -> start no match; end matches -> 0.5."""
    val = ev._calculate_boundary_score({"start": 0, "end": 5}, {"start": 3, "end": 5}, 2)
    assert val == 0.5


def test_boundary_accuracy_strict_known(ev):
    """One GT span, one boundary matches -> 0.5 / 1 GT span -> 0.5."""
    val = ev._compute_boundary_accuracy(
        [{"start": 0, "end": 5}], [{"start": 0, "end": 9}]
    )
    assert val == pytest.approx(0.5)


def test_boundary_accuracy_both_empty_is_one(ev):
    assert ev._compute_boundary_accuracy([], []) == 1.0


def test_boundary_accuracy_one_empty_is_zero(ev):
    assert ev._compute_boundary_accuracy([{"start": 0, "end": 5}], []) == 0.0


# ============================================================================
# hierarchical_f1 (ancestor-set F1)
#   Hand: gt=[A,B,C], pred=[A,B,D]
#     gt_anc={(A),(A,B),(A,B,C)}=3, pred_anc={(A),(A,B),(A,B,D)}=3, ∩=2
#     P=2/3, R=2/3, F1=2/3
# ============================================================================


def test_hierarchical_f1_known_value(ev):
    """Shared prefix A>B then diverge: F1 = 2/3."""
    val = ev._compute_hierarchical_metric("hierarchical_f1", "A>B>C", "A>B>D")
    assert val == pytest.approx(2.0 / 3.0)


def test_hierarchical_f1_identical_is_one(ev):
    assert ev._compute_hierarchical_metric("hierarchical_f1", "A>B>C", "A>B>C") == 1.0


def test_hierarchical_f1_no_common_root_is_zero(ev):
    """gt=[X], pred=[Y]: ancestors {(X)} vs {(Y)}, ∩=0 -> P+R=0 -> 0.0."""
    assert ev._compute_hierarchical_metric("hierarchical_f1", "X", "Y") == 0.0


def test_hierarchical_f1_both_empty_is_one(ev):
    """Empty paths -> 1.0 (kills the empty guard return)."""
    assert ev._compute_hierarchical_metric("hierarchical_f1", "", "") == 1.0


def test_hierarchical_f1_one_empty_is_zero(ev):
    assert ev._compute_hierarchical_metric("hierarchical_f1", "A>B", "") == 0.0


def test_hierarchical_f1_partial_prefix(ev):
    """gt=[A,B], pred=[A]: gt_anc={(A),(A,B)}=2, pred_anc={(A)}=1, ∩=1.
    P=1/1=1, R=1/2=0.5, F1=2*(0.5)/(1.5)=2/3."""
    val = ev._compute_hierarchical_metric("hierarchical_f1", "A>B", "A")
    assert val == pytest.approx(2.0 / 3.0)


# ============================================================================
# path_accuracy (weighted prefix match, normalized)
#   Default weights for depth 3 = [1,2,3], total = 6.
#   Hand gt=[A,B,C] pred=[A,B,D]: levels 0,1 match (w=1,2)=3; level 2 diverge break.
#     normalized = 3/6 = 0.5
# ============================================================================


def test_path_accuracy_known_weighted_value(ev):
    """First two of three levels match with weights 1,2 -> 3/6 = 0.5."""
    val = ev._compute_path_accuracy("A>B>C", "A>B>D")
    assert val == pytest.approx(0.5)


def test_path_accuracy_full_match_is_one(ev):
    assert ev._compute_path_accuracy("A>B>C", "A>B>C") == 1.0


def test_path_accuracy_first_level_diverges_is_zero(ev):
    """gt=[A,B] pred=[X,B]: level 0 diverges immediately -> 0/(1+2)=0.0."""
    assert ev._compute_path_accuracy("A>B", "X>B") == 0.0


def test_path_accuracy_one_of_two_matches(ev):
    """gt=[A,B] pred=[A,X]: level0 matches w=1, level1 diverge break.
    matched=1, max=1+2=3 -> 1/3."""
    val = ev._compute_path_accuracy("A>B", "A>X")
    assert val == pytest.approx(1.0 / 3.0)


def test_path_accuracy_both_empty_is_one(ev):
    assert ev._compute_path_accuracy("", "") == 1.0


def test_path_accuracy_one_empty_is_zero(ev):
    assert ev._compute_path_accuracy("A>B", "") == 0.0


def test_path_accuracy_unnormalized_raw_score(ev):
    """normalize=False returns raw weighted sum: A>B>C vs A>B>D -> 1+2 = 3.0."""
    val = ev._compute_path_accuracy("A>B>C", "A>B>D", {"normalize": False})
    assert val == pytest.approx(3.0)


def test_path_accuracy_custom_weights(ev):
    """Custom level_weights=[10,20,30] for A>B>C vs A>B>X: levels 0,1 match
    (10+20=30), level 2 diverges. normalized = 30/(10+20+30) = 30/60 = 0.5.
    Kills the `level_weights[i]` indexing and the weight accumulation."""
    val = ev._compute_path_accuracy(
        "A>B>C", "A>B>X", {"level_weights": [10, 20, 30]}
    )
    assert val == pytest.approx(0.5)


def test_path_accuracy_short_weights_extended(ev):
    """level_weights=[5] shorter than depth 3 -> extended to [5,6,7].
    A>B>C vs A>B>C all match -> 18/18 = 1.0. The extension loop
    (`level_weights[-1] + 1`) must fire or this raises IndexError."""
    val = ev._compute_path_accuracy("A>B>C", "A>B>C", {"level_weights": [5]})
    assert val == pytest.approx(1.0)


# ============================================================================
# lca_accuracy (exponential decay from LCA to GT node)
#   decay_rate default 0.5, min_score default 0.1
#   Hand gt=[A,B,C] pred=[A,B]: LCA depth=2, distance_to_gt = 3-2 = 1
#     score = 0.5^1 = 0.5, max(0.5, 0.1) = 0.5
# ============================================================================


def test_lca_accuracy_distance_one(ev):
    """LCA at A>B, GT one deeper -> 0.5^1 = 0.5."""
    val = ev._compute_lca_accuracy("A>B>C", "A>B")
    assert val == pytest.approx(0.5)


def test_lca_accuracy_distance_two(ev):
    """gt=[A,B,C,D] pred=[A,B]: LCA depth=2, dist=4-2=2 -> 0.5^2 = 0.25."""
    val = ev._compute_lca_accuracy("A>B>C>D", "A>B")
    assert val == pytest.approx(0.25)


def test_lca_accuracy_exact_is_one(ev):
    assert ev._compute_lca_accuracy("A>B>C", "A>B>C") == 1.0


def test_lca_accuracy_no_common_ancestor_is_zero(ev):
    """gt=[A] pred=[X]: lca_depth==0 -> 0.0 (kills the `lca_depth == 0` guard)."""
    assert ev._compute_lca_accuracy("A>Y>Z", "X>Y>Z") == 0.0


def test_lca_accuracy_min_score_floor(ev):
    """Far distance with min_score floor: gt depth 5, LCA depth 1 -> 0.5^4=0.0625
    < min_score 0.1 -> floored to 0.1 (kills `max(score, min_score)` -> min)."""
    val = ev._compute_lca_accuracy(
        "A>B>C>D>E", "A>Z", {"decay_rate": 0.5, "min_score": 0.1}
    )
    assert val == pytest.approx(0.1)


def test_lca_accuracy_both_empty_is_one(ev):
    assert ev._compute_lca_accuracy("", "") == 1.0


def test_lca_accuracy_custom_decay(ev):
    """decay_rate=0.25, dist=1 -> 0.25 (kills the decay_rate**dist exponent base)."""
    val = ev._compute_lca_accuracy("A>B>C", "A>B", {"decay_rate": 0.25})
    assert val == pytest.approx(0.25)


# ============================================================================
# map (Mean Average Precision, ranking)
#   Hand: gt_set={a,b,c}, pred=[a,x,b]
#     i=0 a hit -> hits=1, prec=1/1=1
#     i=1 x miss
#     i=2 b hit -> hits=2, prec=2/3
#     sum=1 + 2/3 = 5/3 ; / |gt|=3 -> 5/9
# ============================================================================


def test_map_known_value(ev):
    """gt={a,b,c}, pred=[a,x,b] -> (1 + 2/3)/3 = 5/9."""
    val = ev._compute_ranking_metric("map", ["a", "b", "c"], ["a", "x", "b"])
    assert val == pytest.approx(5.0 / 9.0)


def test_map_perfect_ranking(ev):
    """gt={a,b}, pred=[a,b]: (1/1 + 2/2)/2 = (1+1)/2 = 1.0."""
    val = ev._compute_ranking_metric("map", ["a", "b"], ["a", "b"])
    assert val == pytest.approx(1.0)


def test_map_no_hits_is_zero(ev):
    """gt={a,b}, pred=[x,y]: no hits -> 0/2 = 0.0."""
    val = ev._compute_ranking_metric("map", ["a", "b"], ["x", "y"])
    assert val == 0.0


def test_map_rank_position_matters(ev):
    """gt={a}, pred=[x,a]: hit at index 1 -> prec=1/2; /|gt|=1 -> 0.5.
    Kills the `hits/(i+1)` off-by-one (would give 1/1=1.0 if i not +1)."""
    val = ev._compute_ranking_metric("map", ["a"], ["x", "a"])
    assert val == pytest.approx(0.5)


# ============================================================================
# korrektur_* dispatch -> human-graded no-op returns 0.0
# ============================================================================


def test_korrektur_metric_is_noop_zero(ev):
    assert legacy(ev, "korrektur_falloesung", "anything", "else") == 0.0


# ============================================================================
# unknown metric must raise (fail-loud contract, not silent 0/1)
# ============================================================================


def test_unknown_metric_raises(ev):
    with pytest.raises(ValueError, match="Unknown metric"):
        legacy(ev, "definitely_not_a_metric", "a", "b")


# ============================================================================
# _is_failure_metric — per-family failure thresholds (deterministic logic)
#   binary < 0.5 ; similarity < 0.7 ; correlation < 0.6 ; ranking < 0.5 ;
#   schema_validation < 1.0 ; error metrics > 0.3 ; None -> True ; default False
# ============================================================================


def test_failure_none_value_is_failure(ev):
    assert ev._is_failure_metric("f1", None) is True


def test_failure_binary_threshold_half(ev):
    """exact_match: < 0.5 fails. 0.49 fail, 0.5 pass (kills `< 0.5` operator+const)."""
    assert ev._is_failure_metric("exact_match", 0.49) is True
    assert ev._is_failure_metric("exact_match", 0.5) is False


def test_failure_similarity_threshold_point_seven(ev):
    """jaccard: < 0.7 fails. 0.69 fail, 0.7 pass."""
    assert ev._is_failure_metric("jaccard", 0.69) is True
    assert ev._is_failure_metric("jaccard", 0.7) is False


def test_failure_correlation_threshold_point_six(ev):
    """cohen_kappa: < 0.6 fails. 0.59 fail, 0.6 pass."""
    assert ev._is_failure_metric("cohen_kappa", 0.59) is True
    assert ev._is_failure_metric("cohen_kappa", 0.6) is False


def test_failure_ranking_threshold_half(ev):
    assert ev._is_failure_metric("map", 0.49) is True
    assert ev._is_failure_metric("map", 0.5) is False


def test_failure_schema_validation_threshold_one(ev):
    """schema_validation: < 1.0 fails (anything but a perfect 1.0)."""
    assert ev._is_failure_metric("schema_validation", 0.99) is True
    assert ev._is_failure_metric("schema_validation", 1.0) is False


def test_failure_error_metric_threshold_point_three(ev):
    """mae: > 0.3 fails (higher is worse). 0.31 fail, 0.3 pass (kills `> 0.3`)."""
    assert ev._is_failure_metric("mae", 0.31) is True
    assert ev._is_failure_metric("mae", 0.3) is False


def test_failure_unknown_metric_default_not_failure(ev):
    """Unknown metric name -> default branch returns False (not a failure)."""
    assert ev._is_failure_metric("some_unlisted_metric", 0.0) is False


# ============================================================================
# _calculate_confidence — mean of positive metrics, error metrics inverted
# ============================================================================


def test_confidence_empty_is_zero(ev):
    assert ev._calculate_confidence({}) == 0.0


def test_confidence_mean_of_positives(ev):
    """{f1:1.0, accuracy:0.0} -> mean = 0.5."""
    assert ev._calculate_confidence({"f1": 1.0, "accuracy": 0.0}) == pytest.approx(0.5)


def test_confidence_error_metric_inverted(ev):
    """mae=0.25 -> normalized = 1 - min(0.25,1) = 0.75; only metric -> 0.75."""
    assert ev._calculate_confidence({"mae": 0.25}) == pytest.approx(0.75)


def test_confidence_mape_capped_and_inverted(ev):
    """mape=50 -> 1 - min(50,100)/100 = 1 - 0.5 = 0.5."""
    assert ev._calculate_confidence({"mape": 50.0}) == pytest.approx(0.5)


def test_confidence_error_metric_clamped_at_zero(ev):
    """mae=2.0 -> 1 - min(2,1) = 0.0 (kills the max(0.0, ...) clamp / the min cap)."""
    assert ev._calculate_confidence({"mae": 2.0}) == 0.0


# ============================================================================
# _answers_match_qags — deterministic token-overlap F1 >= threshold (default 0.5)
#   No model download; pure set arithmetic.
# ============================================================================


def test_qags_match_exact(ev):
    assert ev._answers_match_qags("the answer", "the answer") is True


def test_qags_no_overlap_no_match(ev):
    assert ev._answers_match_qags("alpha beta", "gamma delta") is False


def test_qags_threshold_boundary_inclusive(ev):
    """ans1="a b" ans2="a c": ∩={a}=1, P=1/2 R=1/2 F1=0.5 >= 0.5 -> True.
    Kills `>= threshold` -> `> threshold` (which would make 0.5 fail)."""
    assert ev._answers_match_qags("a b", "a c") is True


def test_qags_below_threshold_no_match(ev):
    """ans1="a b c" ans2="a x y": ∩={a}=1, P=1/3 R=1/3 F1=1/3 < 0.5 -> False."""
    assert ev._answers_match_qags("a b c", "a x y") is False


def test_qags_empty_answer_no_match(ev):
    assert ev._answers_match_qags("something", "") is False


def test_qags_custom_threshold(ev):
    """F1=1/3 with threshold 0.3 -> 1/3 >= 0.3 -> True (kills hardcoded 0.5 default)."""
    assert ev._answers_match_qags("a b c", "a x y", threshold=0.3) is True


# ============================================================================
# _normalize_value — strip+lower for str, str() for containers
# ============================================================================


def test_normalize_strips_and_lowers(ev):
    assert ev._normalize_value("  Hello WORLD  ", "text") == "hello world"


def test_normalize_list_to_str(ev):
    assert ev._normalize_value([1, 2], "text") == "[1, 2]"


def test_normalize_passthrough_number(ev):
    assert ev._normalize_value(42, "number") == 42
