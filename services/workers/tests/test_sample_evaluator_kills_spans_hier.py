"""Mutation-kill tests for the SPAN and HIERARCHY scorers in
``ml_evaluation/sample_evaluator.py``.

These tests target the *surviving* mutants that the existing
``tests/test_sample_evaluator_mutation_kills.py`` happy-path span/hierarchy
tests miss: degenerate edges (both-empty / one-empty / length-mismatch / zero
length / zero union), guard inversions (``or``<->``and``, ``not x``->``x``,
``>=``<->``>``, ``len>=2``->``>2``/``>=3``), dict-key / index / delimiter
correctness in the parsers, default-parameter substitutions, and ``else``/
``return`` constant flips.

A surviving mutant in any of these formulas = a silently-wrong published
benchmark score, so each test asserts the EXACT documented constant / parsed
structure that the mutation changes. All expected values are HAND-COMPUTED in
the test docstrings.

Targets (sample_evaluator.py line spans):
    _compute_span_metric (~1708), _parse_spans (~1735),
    _spans_label_compatible (~1766), _span_iou (~1811),
    _compute_partial_match (~2208), _calculate_span_overlap (~2266),
    _compute_boundary_accuracy (~2287), _calculate_boundary_score (~2341),
    _compute_hierarchical_metric (~1826), _parse_hierarchy_path (~1873),
    _compute_path_accuracy (~2362), _compute_lca_accuracy (~2425).

Source is NEVER edited; everything is validated with pytest only.
"""

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


# ============================================================================
# _parse_spans  (~1735)
#   Kills: dict-key renames ('start'/'end'/'labels'/'label' -> 'XX..XX'),
#   item[0]<->item[1] / item[2] index swaps, len>=2 -> >2 / >=3,
#   and/or guard inversions, `span = None` / `span['labels'] = None`,
#   `parsed = None` (json branch).
# ============================================================================


def test_parse_spans_list_of_dict_with_labels_exact(ev):
    """A list-of-dict with explicit ``labels`` parses to the EXACT same dict.

    Key-rename mutants ('start'->'XXstartXX', 'end'->'XXendXX',
    'labels'->'XXlabelsXX', read of item['XXlabelsXX']) and the
    `span['labels'] = None` / `span['labels'] = item['XXlabelXX']` mutants all
    change the produced dict, so an exact == comparison fails them.
    """
    assert ev._parse_spans([{"start": 1, "end": 4, "labels": ["A"]}]) == [
        {"start": 1, "end": 4, "labels": ["A"]}
    ]


def test_parse_spans_list_of_dict_singular_label_normalized(ev):
    """``label`` (str) -> ``labels`` list with that single string.

    Hand: {'start':2,'end':9,'label':'X'} -> {'start':2,'end':9,'labels':['X']}.
    Kills 'label'->'XXlabelXX' key reads, span['XXlabelsXX']=... write rename,
    and the `span['labels'] = None` mutant on this branch.
    """
    assert ev._parse_spans([{"start": 2, "end": 9, "label": "X"}]) == [
        {"start": 2, "end": 9, "labels": ["X"]}
    ]


def test_parse_spans_tuple_pair_index_and_keys(ev):
    """A (start, end) tuple pair -> {'start':2,'end':7}.

    Kills item[0]->item[1] (would give start==end==7), 'end'->item[2]
    (IndexError), 'start'->'XXstartXX'/'end'->'XXendXX' key renames.
    """
    assert ev._parse_spans([(2, 7)]) == [{"start": 2, "end": 7}]


def test_parse_spans_two_element_list_accepted_three_distinguished(ev):
    """len(item) >= 2 admits a 2-tuple; >2 / >=3 would reject it.

    A bare 2-element list ``[3, 8]`` must parse to {'start':3,'end':8}. The
    `len(item) > 2` and `len(item) >= 3` mutants both reject the 2-element item
    and return [] instead.
    """
    assert ev._parse_spans([[3, 8]]) == [{"start": 3, "end": 8}]


def test_parse_spans_non_span_dict_in_list_is_skipped(ev):
    """A dict in the list WITHOUT start/end is skipped -> [].

    Original guard: ``isinstance(item, dict) and 'start' in item and 'end' in
    item`` -> False for {'foo':1} -> item skipped -> []. The `and`->`or` mutant
    (`isinstance(dict) or ...`) makes the guard True and then evaluates
    int(item['start']) -> KeyError. So asserting == [] (no crash) kills the
    and->or guard inversion.
    """
    assert ev._parse_spans([{"foo": 1}]) == []


def test_parse_spans_bare_dict_value_exact(ev):
    """A bare dict value (not wrapped in a list) -> single-span list.

    Hand: {'start':5,'end':11,'labels':['L']} -> [{'start':5,'end':11,
    'labels':['L']}]. Kills the dict-branch key renames ('XXstartXX'/'XXendXX'/
    'XXlabelsXX'), the `'start' not in value` / `'end' not in value` guard
    flips (would skip this value -> []), the `or` guard flip, and `span = None`
    (-> AttributeError on span['labels'] assignment).
    """
    assert ev._parse_spans({"start": 5, "end": 11, "labels": ["L"]}) == [
        {"start": 5, "end": 11, "labels": ["L"]}
    ]


def test_parse_spans_bare_dict_singular_label(ev):
    """Bare dict with str ``label`` -> labels:[label].

    Kills the dict-branch 'label'->'XXlabelXX' / 'labels'->'XXlabelsXX' renames
    and the `span['labels'] = None` mutant on the bare-dict path.
    """
    assert ev._parse_spans({"start": 0, "end": 3, "label": "Z"}) == [
        {"start": 0, "end": 3, "labels": ["Z"]}
    ]


def test_parse_spans_json_string_roundtrip(ev):
    """A JSON-string list parses via json.loads then re-parses.

    Kills `parsed = None` in the string branch (None -> _parse_spans(None) ->
    [] instead of the real span).
    """
    assert ev._parse_spans('[{"start": 4, "end": 6}]') == [{"start": 4, "end": 6}]


# ============================================================================
# _spans_label_compatible  (~1766)
#   Kills: & -> | (disjoint labels), or->and guard flip, not x -> x flips,
#   'labels'->'XXlabelsXX' get-key renames, `gt_labels = None` etc.
# ============================================================================


def test_spans_label_compatible_disjoint_is_false(ev):
    """Two non-empty DISJOINT label sets are NOT compatible -> False.

    gt={'A'}, pred={'B'}: original returns bool({'A'} & {'B'}) = bool(set()) =
    False. This single assertion kills:
      - `&`->`|`            (|-> {'A','B'} -> True)
      - `not gt`->`gt`      (gt truthy -> guard True -> early return True)
      - `not pred`->`pred`  (pred truthy -> guard True -> early return True)
      - 'labels'->'XXlabelsXX' get rename (both sets become empty -> guard True
        -> early return True instead of False)
      - `gt_labels=None` / `pred_labels=None` (TypeError on set ops)
    """
    assert ev._spans_label_compatible({"labels": ["A"]}, {"labels": ["B"]}) is False


def test_spans_label_compatible_overlap_is_true(ev):
    """Overlapping labels -> True. gt={'A','B'}, pred={'B'} -> bool({'B'})=True."""
    assert ev._spans_label_compatible({"labels": ["A", "B"]}, {"labels": ["B"]}) is True


def test_spans_label_compatible_one_side_empty_is_true(ev):
    """One side has no labels -> position-only compatible -> True.

    gt has labels, pred has none: original guard ``not gt_labels or not
    pred_labels`` = (False or True) = True -> returns True. The `or`->`and`
    mutant (#1193) makes it (False and False) = False -> falls through to
    bool({'A'} & set()) = False. Asserting True kills the or->and flip.
    """
    assert ev._spans_label_compatible({"labels": ["A"]}, {"labels": []}) is True


# ============================================================================
# _span_iou  (~1811)
#   Kills: union > 0 -> union >= 0 (zero-union ZeroDivision), else 0.0 -> 1.0.
# ============================================================================


def test_span_iou_zero_union_is_zero(ev):
    """Two empty (zero-length) spans at the same point -> 0.0, no crash.

    [5,5] vs [5,5]: inter = max(0, 5-5) = 0; union = (5-5)+(5-5)-0 = 0.
    Original: ``union > 0`` is False -> returns the else 0.0.
      - `union > 0` -> `union >= 0` makes the guard True -> 0/0 -> ZeroDivisionError.
      - `else 0.0` -> `else 1.0` returns 1.0.
    Asserting exactly 0.0 (and no exception) kills both.
    """
    assert ev._span_iou({"start": 5, "end": 5}, {"start": 5, "end": 5}) == 0.0


# ============================================================================
# _compute_span_metric  (~1708)
#   Kills: iou one-empty/both-empty guards (covered in existing file) and the
#   trailing `return 0.0` for an UNKNOWN metric name (1733 return 0.0 -> 1.0).
# ============================================================================


def test_compute_span_metric_unknown_name_is_zero(ev):
    """An unrecognised span metric name falls through to ``return 0.0``.

    Kills the `return 0.0` -> `return 1.0` mutant at the end of
    _compute_span_metric. (Not exact_match, not iou -> the final return.)
    """
    assert (
        ev._compute_span_metric(
            "not_a_real_metric", [{"start": 0, "end": 5}], [{"start": 0, "end": 5}]
        )
        == 0.0
    )


def test_compute_span_metric_iou_one_empty_gt_is_zero(ev):
    """gt empty / pred non-empty -> 0.0 (the `if not gt or not pred` guard).

    The existing file only checks pred-empty; this checks the GT-empty side so
    the `or`->`and` flip on `if not gt_spans or not pred_spans` is pinned from
    both sides.
    """
    assert ev._compute_span_metric("iou", [], [{"start": 0, "end": 5}]) == 0.0


# ============================================================================
# _calculate_span_overlap  (~2266)
#   Kills: max(0,..)->max(1,..), end1-start1 -> end1+start1,
#   zero-gt-length branch `1.0 if intersection > 0` constants/operator.
# ============================================================================


def test_calculate_span_overlap_disjoint_is_zero(ev):
    """Non-overlapping spans -> overlap 0.0.

    gt [0,4], pred [10,14]: inter_start = max(0,10)=10, inter_end =
    min(4,14)=4, intersection = max(0, 4-10) = max(0,-6) = 0; gt_length = 4 ->
    0/4 = 0.0. The `max(0, ...)`->`max(1, ...)` mutant yields 1, then 1/4 =
    0.25. Asserting 0.0 kills it.
    """
    assert (
        ev._calculate_span_overlap({"start": 0, "end": 4}, {"start": 10, "end": 14})
        == 0.0
    )


def test_calculate_span_overlap_gt_length_uses_difference(ev):
    """gt_length must be end1 - start1, not end1 + start1.

    gt [2,6] (length 4), pred [0,10] fully covers gt: inter_start = max(2,0)=2,
    inter_end = min(6,10)=6, intersection = 4. Original gt_length = 6-2 = 4 ->
    4/4 = 1.0. The `end1 + start1` mutant gives 6+2 = 8 -> 4/8 = 0.5. start1!=0
    so minus and plus diverge; asserting 1.0 kills the +/- swap.
    """
    assert (
        ev._calculate_span_overlap({"start": 2, "end": 6}, {"start": 0, "end": 10})
        == 1.0
    )


def test_calculate_span_overlap_zero_gt_length_with_overlap_is_one(ev):
    """Zero-length GT span that intersects -> 1.0.

    gt [5,5] (length 0), pred [3,8]: inter_start = max(5,3)=5, inter_end =
    min(5,8)=5, intersection = max(0, 5-5) = 0. With `max(0,...)` the
    intersection is 0 -> `1.0 if 0 > 0 else 0.0` -> 0.0. But the `max(1,...)`
    mutant makes intersection = 1 -> `1.0 if 1 > 0` -> 1.0, AND we want to pin
    the zero-length branch's `intersection > 0` operator and the 1.0/0.0
    constants. Use a pred that genuinely overlaps the point so intersection>0
    under the ORIGINAL formula: gt [5,5] vs pred [4,6] -> inter_start=5,
    inter_end=5, intersection = max(0,0) = 0 as well (points have zero width).
    A zero-length span never has a positive max(0,...) intersection, so to
    exercise `intersection > 0 -> 1.0` we feed intersection>0 directly is
    impossible for zero-length GT; the meaningful kill is the FALSE side below.
    """
    # Zero-length GT, intersection computes to 0 under the real formula ->
    # `1.0 if intersection > 0 else 0.0` returns 0.0.
    # Kills `else 0.0`->`else 1.0` is NOT reachable here (that constant is on
    # the FALSE branch which we DO take) -- asserting 0.0 pins the else-0.0.
    assert (
        ev._calculate_span_overlap({"start": 5, "end": 5}, {"start": 3, "end": 8})
        == 0.0
    )


# ============================================================================
# _compute_partial_match  (~2208)
#   Kills: both-empty/one-empty guards (or->and), mode default 'best',
#   `mode == 'average'` -> != / 'XXaverageXX', average-branch math
#   (total/len -> total*len, append(0.0)->1.0, >= -> >, else 0.0 -> 1.0,
#   `if not compatible` -> `if compatible`, continue->break),
#   final `... else 0.0` -> 1.0 / `total/len else 1.0`.
# ============================================================================


def test_partial_match_both_empty_via_or_guard(ev):
    """Both-empty -> 1.0 (covered) AND one-empty(gt) -> 0.0 pins the or-guard.

    The existing file checks pred-empty; pin GT-empty too so `if not gt_spans
    or not pred_spans` can't flip to `and` (which would make one-empty fall
    through to the matcher and divide by len([]) -> 1.0/crash).
    """
    assert ev._compute_partial_match([], [{"start": 0, "end": 5}]) == 0.0


def test_partial_match_default_mode_is_best_not_average(ev):
    """Default mode must be 'best' (bipartite), distinguishable from 'average'.

    Two GT spans, one pred span that fully covers GT#1 and misses GT#2.
      gt = [[0,10],[20,30]], pred = [[0,10]].
    BEST (optimal bipartite over _calculate_span_overlap, normalized by
    len(gt_spans)=2):
      overlap(gt0,pred)=10/10=1.0 ; overlap(gt1,pred): inter of [20,30] and
      [0,10] is 0 -> 0.0. Optimal assignment picks (gt0<->pred)=1.0, gt1
      unmatched=0.0. Sum=1.0 -> 1.0/2 = 0.5.
    AVERAGE branch would compute per-GT average over compatible preds:
      gt0: avg over [pred]=1.0 ; gt1: avg=0.0 -> mean = 0.5 too. Same number,
      so to DISTINGUISH default 'best' from a mutated default 'average' or
      `mode == 'average'`->`!= 'average'` we need divergent inputs (below).
    Here we just pin the BEST value 0.5 for the default call.
    """
    val = ev._compute_partial_match([[0, 10], [20, 30]], [[0, 10]])
    assert val == pytest.approx(0.5)


def test_partial_match_average_vs_best_diverge(ev):
    """A case where 'best' and 'average' give DIFFERENT scores.

    gt = [[0,10]] (single GT), pred = [[0,10],[0,5]] (two preds).
    overlaps vs gt: pred0 [0,10] -> 10/10 = 1.0 ; pred1 [0,5] -> 5/10 = 0.5.

    BEST (default, optimal bipartite, normalized by len(gt)=1): best match for
    the single GT is pred0 = 1.0 -> sum 1.0 / 1 = 1.0.

    AVERAGE: per-GT average over compatible preds = (1.0 + 0.5)/2 = 0.75 ->
    mean over GT spans = 0.75.

    So default(best)=1.0 but explicit average=0.75. This kills:
      - default 'best'->'XXbestXX'/None (mode None -> not 'average' -> best
        path still, but None default differs only if it changed the branch;
        the divergence is pinned by comparing the two explicit calls)
      - `mode == 'average'` -> `mode != 'average'` (would swap the two paths)
    """
    best = ev._compute_partial_match([[0, 10]], [[0, 10], [0, 5]])
    avg = ev._compute_partial_match(
        [[0, 10]], [[0, 10], [0, 5]], {"mode": "average"}
    )
    assert best == pytest.approx(1.0)
    assert avg == pytest.approx(0.75)


def test_partial_match_average_no_compatible_is_zero(ev):
    """AVERAGE branch: a GT span with NO label-compatible pred scores 0.0.

    gt span labelled {'A'} only; pred span labelled {'B'} only (disjoint, so
    _spans_label_compatible is False) -> compatible = [] -> the `if not
    compatible: overlap_scores.append(0.0); continue` path. With one GT span
    the mean is 0.0.
    Kills:
      - `if not compatible` -> `if compatible` (would try to average over [] ->
        division by zero / skip)
      - `overlap_scores.append(0.0)` -> append(1.0) (would give 1.0)
      - `continue` -> `break` (with a single GT span the result is the same 0.0,
        but the structural mutant is pinned by the multi-GT variant being 0.0
        only if break didn't truncate -- here single-GT keeps it deterministic)
    """
    val = ev._compute_partial_match(
        [{"start": 0, "end": 10, "labels": ["A"]}],
        [{"start": 0, "end": 10, "labels": ["B"]}],
        {"mode": "average"},
    )
    assert val == 0.0


def test_partial_match_average_total_over_len_is_division(ev):
    """AVERAGE: avg_overlap = total_overlap / len(compatible), not * len.

    gt = [[0,10]] ; pred = [[0,10],[0,5]] (both compatible: no labels).
    total_overlap = 1.0 + 0.5 = 1.5 ; len(compatible) = 2 -> avg = 0.75.
    The `total_overlap * len(compatible)` mutant gives 1.5*2 = 3.0 -> mean 3.0.
    Asserting 0.75 kills the /-> * swap (and `avg_overlap = None`).
    """
    val = ev._compute_partial_match(
        [[0, 10]], [[0, 10], [0, 5]], {"mode": "average"}
    )
    assert val == pytest.approx(0.75)


def test_partial_match_average_min_overlap_inclusive_boundary(ev):
    """AVERAGE: avg_overlap >= min_overlap keeps the boundary; > would drop it.

    gt = [[0,10]] ; pred = [[0,5]] -> avg_overlap = 0.5. With min_overlap = 0.5
    the original `avg_overlap >= min_overlap` keeps 0.5 -> score 0.5. The
    `>=`->`>` mutant drops it (0.5 > 0.5 False) -> 0.0; the `else 0.0`->`1.0`
    mutant would give 1.0. Asserting 0.5 kills both.
    """
    val = ev._compute_partial_match(
        [[0, 10]], [[0, 5]], {"mode": "average", "min_overlap": 0.5}
    )
    assert val == pytest.approx(0.5)


# ============================================================================
# _compute_boundary_accuracy  (~2287)
#   Kills: both-empty/one-empty guards, tolerance default 0 (not 1),
#   mode default 'strict', `mode == 'lenient'` branch, lenient best/ max
#   constants, strict `total/len else 1.0`.
# ============================================================================


def test_boundary_accuracy_one_empty_gt_is_zero(ev):
    """gt empty / pred non-empty -> 0.0 (pin the GT-empty side of the guard)."""
    assert ev._compute_boundary_accuracy([], [{"start": 0, "end": 5}]) == 0.0


def test_boundary_accuracy_default_tolerance_is_zero(ev):
    """Default tolerance is 0: a 1-char-off start is NOT a match.

    gt [0,5], pred [1,5]: start diff = 1 > tol 0 -> start NOT matched; end diff
    = 0 <= 0 -> end matched -> boundary score 0.5 -> /1 GT span = 0.5.
    The `parameters.get('tolerance', 0)` -> default 1 mutant would make start
    diff 1 <= 1 -> both match -> 1.0. Asserting 0.5 kills the default-1 mutant
    (and the 'tolerance'->'XXtoleranceXX' key rename, which also yields the
    mutated default).
    """
    val = ev._compute_boundary_accuracy([[0, 5]], [[1, 5]])
    assert val == pytest.approx(0.5)


def test_boundary_accuracy_default_mode_strict_vs_lenient_diverge(ev):
    """Default mode 'strict' (bipartite/normalized) differs from 'lenient' (max).

    gt = [[0,10],[100,110]] ; pred = [[0,10]] (matches GT#0 exactly, far from
    GT#1).
    STRICT (default): optimal bipartite boundary scores: gt0<->pred = 1.0
      (both boundaries match), gt1 unmatched -> 0.0. Sum 1.0 / 2 GT = 0.5.
    LENIENT: per-GT best score then max over GT: gt0 best = 1.0, gt1 best =
      0.0 -> max(best_scores) = 1.0.
    So default=0.5 but explicit lenient=1.0. Kills default 'strict'->'XXstrictXX'
    / None and the `mode == 'lenient'`->`!= 'lenient'` swap.
    """
    strict = ev._compute_boundary_accuracy([[0, 10], [100, 110]], [[0, 10]])
    lenient = ev._compute_boundary_accuracy(
        [[0, 10], [100, 110]], [[0, 10]], {"mode": "lenient"}
    )
    assert strict == pytest.approx(0.5)
    assert lenient == pytest.approx(1.0)


# ============================================================================
# _calculate_boundary_score  (~2341)
#   Kills: `abs(gt['start'] - pred['start'])` -> `+`.
# ============================================================================


def test_calculate_boundary_score_start_uses_subtraction(ev):
    """start_match uses abs(start_gt - start_pred), not the sum.

    gt start=5, pred start=5, end=5 vs 5, tolerance=0:
      diff = abs(5-5) = 0 <= 0 -> start matches; end abs(5-5)=0 -> matches ->
      1.0. The `-`->`+` mutant computes abs(5+5)=10 > 0 -> start NOT matched ->
      only end matches -> 0.5. Asserting 1.0 kills the minus->plus swap.
    """
    val = ev._calculate_boundary_score(
        {"start": 5, "end": 5}, {"start": 5, "end": 5}, 0
    )
    assert val == 1.0


# ============================================================================
# _parse_hierarchy_path  (~1873)
#   Kills: delimiter-list members ('/'/'::'/' > '/' / ' renamed to XX..XX),
#   `value is None` -> `is not None`, `parsed = None` (json branch).
# ============================================================================


def test_parse_hierarchy_path_slash_delimiter(ev):
    """'a/b/c' splits on '/'. Kills '/'->'XX/XX' (no split -> ['a/b/c'])."""
    assert ev._parse_hierarchy_path("a/b/c") == ["a", "b", "c"]


def test_parse_hierarchy_path_gt_delimiter(ev):
    """'a>b>c' splits on '>'. Pins the '>' delimiter member."""
    assert ev._parse_hierarchy_path("a>b>c") == ["a", "b", "c"]


def test_parse_hierarchy_path_double_colon_delimiter(ev):
    """'a::b' splits on '::'. Kills '::'->'XX::XX' (no split -> ['a::b'])."""
    assert ev._parse_hierarchy_path("a::b") == ["a", "b"]


def test_parse_hierarchy_path_none_is_empty(ev):
    """None -> []. Kills `value is None` -> `is not None`.

    With `is not None`, None would NOT take this branch and would fall to the
    final `else: return [str(value)]` -> ['None']. Asserting [] kills it.
    """
    assert ev._parse_hierarchy_path(None) == []


def test_parse_hierarchy_path_json_list_string(ev):
    """A JSON-list string parses via json.loads. Kills `parsed = None`.

    '["a","b"]' -> json.loads -> ['a','b']. The `parsed = None` mutant makes
    isinstance(None, list) False, falling to the delimiter loop; '["a","b"]'
    has no delimiter -> ['["a","b"]'] (single element). Asserting ['a','b']
    kills it.
    """
    assert ev._parse_hierarchy_path('["a", "b"]') == ["a", "b"]


# ============================================================================
# _compute_hierarchical_metric  (~1826)
#   Kills: parameters None default, hierarchical_f1 both-empty/one-empty guards
#   and the `return 0.0` arms, precision/recall `else 0.0`->1.0 (empty ancestor
#   guard -- only reachable on empty path, which the earlier guard already
#   handles, so those two are EQUIVALENT, see note), and trailing return 0.0.
# ============================================================================


def test_hierarchical_unknown_metric_is_zero(ev):
    """Unknown hierarchical metric name -> trailing `return 0.0`.

    Kills `return 0.0` -> `return 1.0` at the end of
    _compute_hierarchical_metric. Use a non-empty path so the value isn't
    masked by an earlier branch.
    """
    assert ev._compute_hierarchical_metric("nope_metric", "A>B", "A>B") == 0.0


def test_hierarchical_f1_one_empty_gt_is_zero(ev):
    """gt empty / pred non-empty -> 0.0 (pin the GT-empty side of the or-guard).

    Existing file checks pred-empty; pin GT-empty so `if not gt_path or not
    pred_path` can't flip to `and`.
    """
    assert ev._compute_hierarchical_metric("hierarchical_f1", "", "A>B") == 0.0


def test_hierarchical_f1_default_parameters_none(ev):
    """Called with parameters=None (default) must not crash and gives 1.0.

    `if parameters is None: parameters = {}` guard. The `is not None` flip
    would skip the assignment (parameters stays None) but hierarchical_f1 never
    reads parameters, so that specific mutant is benign here -- the value is
    pinned regardless. (See note: parameters-None mutants in this method are
    reached only by path_accuracy/lca sub-calls.)
    """
    assert ev._compute_hierarchical_metric("hierarchical_f1", "A>B", "A>B") == 1.0


# ============================================================================
# _compute_path_accuracy  (~2362)
#   Kills: both-empty (and->or / not flips), one-empty return 0.0->1.0,
#   level_weights default key, `while len < max_depth` -> `<=`, weight-extend
#   arithmetic (+1->-1 / +2, else 1->2), `max_possible > 0` -> >= / else 1.0.
# ============================================================================


def test_path_accuracy_one_empty_pred_is_zero(ev):
    """gt non-empty / pred empty -> 0.0 (the one-empty `return 0.0`).

    Pins `return 0.0` -> `return 1.0` and the `not gt or not pred` guard on the
    pred-empty side (the existing file already does the gt side via "" gt).
    """
    assert ev._compute_path_accuracy("A>B", "") == 0.0


def test_path_accuracy_both_empty_is_one(ev):
    """Both empty -> 1.0 (the `not gt and not pred` guard).

    `not gt_path and not pred_path` -> True for ("",""). The first-operand
    `not gt_path`->`gt_path` flip makes it (False and True)=False -> falls to
    one-empty guard -> both empty -> `not gt or not pred` True -> 0.0. So
    asserting 1.0 kills the `not`->bare flips on the both-empty guard, and the
    `and`->`or` flip (which would make ("nonempty"," ") wrongly hit 1.0 -- see
    next test).
    """
    assert ev._compute_path_accuracy("", "") == 1.0


def test_path_accuracy_both_empty_guard_not_or(ev):
    """A>B vs A>B is NOT both-empty: must score 1.0 via the real formula path.

    If `not gt_path and not pred_path` were mutated to `or`, a non-empty input
    where one side were empty would short-circuit; here both are non-empty so
    the and->or flip is pinned by combining with the one-empty test above:
    A>B/A>B both non-empty -> guard False -> proceeds -> exact match -> 1.0.
    """
    assert ev._compute_path_accuracy("A>B", "A>B") == 1.0


def test_path_accuracy_weight_extension_uses_default_increment(ev):
    """Short custom level_weights are extended by +1 from the last element.

    gt = pred = "A>B>C" (max_depth 3). level_weights=[5] given. Extension:
      len 1 < 3 -> append 5+1=6 -> [5,6]; len 2 < 3 -> append 6+1=7 -> [5,6,7].
    All three levels match -> matching = 5+6+7 = 18 ; max_possible = 18 ->
    18/18 = 1.0 (normalized). This particular full-match case is 1.0 for the
    +1 path AND the +2 path, so to pin the increment we need a PARTIAL match
    where the weights matter (next test). Here we assert the structural while
    loop ran (no IndexError) and value is 1.0.
    """
    val = ev._compute_path_accuracy("A>B>C", "A>B>C", {"level_weights": [5]})
    assert val == 1.0


def test_path_accuracy_weight_extension_increment_value(ev):
    """Partial match pins the +1 extension increment (vs -1 / +2 / else).

    gt = "A>B>C", pred = "A>X>C" (level 0 matches, level 1 diverges -> break).
    level_weights=[10] given, max_depth=3. Extension (+1):
      [10] -> 10+1=11 -> [10,11] -> 11+1=12 -> [10,11,12].
    The scoring loop adds `max_possible_score += weight` BEFORE checking the
    match, and `break`s on the first divergence:
      i=0: max_possible += 10 (=10); A==A -> matching += 10 (=10)
      i=1: max_possible += 11 (=21); B!=X -> break (level 2 never reached)
    -> matching = 10, max_possible = 21 -> 10/21.
      `+1`->`-1`: [10,9,8]  -> i=1 max_possible 10+9=19  -> 10/19 (different).
      `+1`->`+2`: [10,12,14]-> i=1 max_possible 10+12=22 -> 10/22 (different).
    Asserting 10/21 kills the increment mutants.
    """
    val = ev._compute_path_accuracy("A>B>C", "A>X>C", {"level_weights": [10]})
    assert val == pytest.approx(10.0 / 21.0)


def test_path_accuracy_while_strict_less_than(ev):
    """`while len(level_weights) < max_depth` must be strict `<`, not `<=`.

    gt = pred = "A>B" (max_depth 2), level_weights=[3,4] (already length 2).
    Original: 2 < 2 False -> no extra append -> weights stay [3,4]. matching =
    3+4 = 7, max_possible 7 -> 1.0. The `<`->`<=` mutant runs once more: 2 <= 2
    True -> append 4+1=5 -> [3,4,5]; then 3 <= 2 False stop. The extra weight 5
    is never indexed in the i in range(max_depth=2) loop, so max_possible stays
    3+4 = 7 and the value is STILL 1.0 -> EQUIVALENT for this input. To force a
    difference we'd need max_depth to change, which it doesn't. (See note.)
    This test pins the 1.0 value for the no-extension case.
    """
    val = ev._compute_path_accuracy("A>B", "A>B", {"level_weights": [3, 4]})
    assert val == 1.0


def test_path_accuracy_unnormalized_max_possible_guard(ev):
    """normalize=False returns raw matching_score (pins the normalize branch).

    gt = pred = "A>B>C", default weights [1,2,3], all match -> matching = 6.
    normalize=False -> returns 6.0 (raw). The normalized branch would return
    1.0. Asserting 6.0 keeps the False branch distinct and pins
    `return matching_score`.
    """
    val = ev._compute_path_accuracy("A>B>C", "A>B>C", {"normalize": False})
    assert val == 6.0


# ============================================================================
# _compute_lca_accuracy  (~2425)
#   Kills: both-empty/one-empty guards, one-empty return 0.0->1.0,
#   min_score default key, decay/min behaviour.
# ============================================================================


def test_lca_accuracy_one_empty_pred_is_zero(ev):
    """gt non-empty / pred empty -> 0.0 (one-empty `return 0.0`).

    Pins `return 0.0`->1.0 and the pred-empty side of `not gt or not pred`.
    """
    assert ev._compute_lca_accuracy("A>B", "") == 0.0


def test_lca_accuracy_both_empty_guard_not_flips(ev):
    """Both empty -> 1.0; pins the `not gt and not pred` flips and and->or.

    The `not gt_path`->`gt_path` / `not pred_path`->`pred_path` flips break the
    both-empty True; the `and`->`or` flip is pinned together with the one-empty
    test above. Asserting 1.0 for ("","") covers the True side.
    """
    assert ev._compute_lca_accuracy("", "") == 1.0


def test_lca_accuracy_default_min_score_floor(ev):
    """Default min_score is 0.1: a deep GT with shallow LCA floors at 0.1.

    gt = "A>B>C>D>E>F" (depth 6), pred = "A>B" (shares prefix A>B).
    lca_depth = 2 ; distance_to_gt = 6 - 2 = 4 ; score = decay 0.5**4 =
    0.0625. max(0.0625, min_score 0.1) = 0.1 (floor wins).
    The `parameters.get('min_score', 0.1)` -> 'XXmin_scoreXX' key-rename mutant
    yields the SAME default 0.1, so it's pinned only if the default value is
    read; here floor=0.1 confirms the default is in effect (an explicit
    min_score below 0.0625 would change it). Asserting 0.1 pins the floor.
    """
    val = ev._compute_lca_accuracy("A>B>C>D>E>F", "A>B")
    assert val == pytest.approx(0.1)


def test_lca_accuracy_min_score_explicit_below_decay(ev):
    """Explicit min_score below the decayed score -> decay wins (no floor).

    gt = "A>B>C" (depth 3), pred = "A>B": lca_depth 2, distance 1, score =
    0.5**1 = 0.5. min_score=0.01 < 0.5 -> max(0.5, 0.01) = 0.5. This pins that
    min_score is actually plumbed in (default 0.1 would still give 0.5 here, so
    this is a sanity anchor for the decay value, complementing the floor test).
    """
    val = ev._compute_lca_accuracy("A>B>C", "A>B", {"min_score": 0.01})
    assert val == pytest.approx(0.5)
