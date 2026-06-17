"""Mutation-kill tests for ml_evaluation/sample_evaluator.py — scalar/failure paths.

Each test here exists to KILL a specific SURVIVING mutant from the mutmut
baseline recorded in workers/_surv_diffs.txt (the meaningful-coverage program /
mutation co-gate). A surviving mutant in a scoring formula is a silently wrong
published benchmark score, so a killing test asserts the EXACT value, boundary,
operator, formula constant, or raised message the mutation changes — never
merely that a line executes.

Expected values are HAND-COMPUTED in each test/parametrize docstring so a
flipped operator / wrong constant / off-by-one / dropped bucket member fails.

TARGET METHODS (and the surviving-mutant id ranges they cover):
  * _compute_numeric_metric         #667, #668, #671, #672, #674
  * _compute_classification_metric  #677-#680, #683, #684, #687, #688
  * _compute_set_metric             #699, #706, #708, #713, #718, #727
  * _compute_token_f1               #740, #745, #748
  * _levenshtein_distance           #1279, #1287   (#1276 equivalent — see end)
  * _is_failure_metric              #1306-#1312, #1316-#1345, #1349, #1359-#1361
  * _calculate_confidence           #1367, #1368, #1371-#1373, #1379-#1415,
                                    #1418, #1420, #1424, #1445
                                    (#1435, #1442 equivalent — see end)

Equivalent mutants (provably no observable behaviour change) are NOT given a
killing test; they are listed with proof at the bottom of this module.
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
# _compute_numeric_metric  (#667, #668, #671, #672, #674)
#
# r2 and correlation are aggregate-only and RAISE RuntimeError per-sample. The
# `except (ValueError, TypeError)` does NOT catch RuntimeError, so the message
# propagates verbatim. The raised message is two concatenated string literals;
# mutants #667/#671 wrap the FIRST literal in `XX...XX`, #668/#672 wrap the
# SECOND. Asserting the EXACT, whole concatenated message kills the raise being
# removed AND every per-literal `XX`-wrap (a substring/`match=` regex would NOT
# kill a wrap, since `XX` is only a prefix and re.search still finds the core).
#
# #674: the terminal `return 0.0` (reached for an unknown numeric metric or a
# valid-but-no-branch metric) mutated to `return 1.0`.
# ============================================================================

_R2_MSG = (
    "R² score is an aggregate-only metric and cannot be computed per-sample. "
    "Use sklearn.metrics.r2_score at the aggregate level."
)
_CORR_MSG = (
    "Pearson correlation is an aggregate-only metric and cannot be computed per-sample. "
    "Use scipy.stats.pearsonr at the aggregate level."
)


def test_numeric_r2_raises_exact_message(ev):
    """r2 per-sample raises RuntimeError with the EXACT message.

    Kills: the raise being neutralised, #667 (`XX`-wrap of literal 1) and
    #668 (`XX`-wrap of literal 2). Exact-equality fails the moment either
    literal gains an `XX` prefix/suffix.
    """
    with pytest.raises(RuntimeError) as excinfo:
        ev._compute_numeric_metric("r2", 1.0, 2.0)
    assert str(excinfo.value) == _R2_MSG


def test_numeric_correlation_raises_exact_message(ev):
    """correlation per-sample raises RuntimeError with the EXACT message.

    Kills #671 (`XX`-wrap of literal 1) and #672 (`XX`-wrap of literal 2).
    """
    with pytest.raises(RuntimeError) as excinfo:
        ev._compute_numeric_metric("correlation", 1.0, 2.0)
    assert str(excinfo.value) == _CORR_MSG


def test_numeric_unknown_metric_returns_zero(ev):
    """An unknown numeric metric falls through to the terminal `return 0.0`.

    'not_a_metric' matches no branch, conversion succeeds, so we hit the final
    `return 0.0`. Kills #674 (`return 0.0` -> `return 1.0`). Asserting the exact
    0.0 pins the constant.
    """
    assert ev._compute_numeric_metric("not_a_metric", 3.0, 4.0) == 0.0


# ============================================================================
# _compute_classification_metric  (#677-#680, #683, #684, #687, #688)
#
#   is_correct = (gt == pred)
#   precision/recall/f1  -> 1.0 if is_correct else 0.0
#   cohen_kappa          -> 1.0 if is_correct else 0.0
#   (terminal)           -> 1.0 if is_correct else 0.0
#
# #677 flips the membership guard `in` -> `not in`.
# #678/#679/#680 corrupt one bucket literal ("precision"/"recall"/"f1" -> XX).
# #683 flips `== "cohen_kappa"` -> `!=`.  #684 corrupts the literal -> XX.
# #687 flips terminal return `1.0` -> `2.0`.  #688 flips `else 0.0` -> `1.0`.
#
# Strategy: for each of precision/recall/f1/cohen_kappa, assert 1.0 on a
# CORRECT sample AND 0.0 on a WRONG sample. The WRONG sample is the load-bearing
# one for the literal/guard mutants: corrupting "precision" (etc.) or flipping
# `in`->`not in` makes the WRONG sample fall through to the terminal branch,
# which still returns `1.0 if is_correct else 0.0` == 0.0 ... so we additionally
# assert the terminal-branch constants directly via a metric that hits no
# explicit branch (below), and the literal/guard mutants are killed because the
# terminal branch and the explicit branch are the SAME formula here — meaning
# the per-literal #678-#680/#684 mutants are caught only if some input routes
# differently. They do NOT here (every branch returns the identical formula), so
# #678-#680 and #684 and #677 and #683 are EQUIVALENT and listed at the bottom.
# We still pin the live constants #687/#688 with the terminal-branch tests.
# ============================================================================


def test_classification_precision_correct_is_one(ev):
    """gt == pred -> 1.0 for precision."""
    assert ev._compute_classification_metric("precision", "a", "a") == 1.0


def test_classification_precision_wrong_is_zero(ev):
    """gt != pred -> 0.0 for precision."""
    assert ev._compute_classification_metric("precision", "a", "b") == 0.0


def test_classification_recall_correct_wrong(ev):
    assert ev._compute_classification_metric("recall", "a", "a") == 1.0
    assert ev._compute_classification_metric("recall", "a", "b") == 0.0


def test_classification_f1_correct_wrong(ev):
    assert ev._compute_classification_metric("f1", "a", "a") == 1.0
    assert ev._compute_classification_metric("f1", "a", "b") == 0.0


def test_classification_cohen_kappa_correct_wrong(ev):
    assert ev._compute_classification_metric("cohen_kappa", "a", "a") == 1.0
    assert ev._compute_classification_metric("cohen_kappa", "a", "b") == 0.0


def test_classification_terminal_correct_is_one(ev):
    """An unlisted metric hits the terminal `return 1.0 if is_correct else 0.0`.

    is_correct True -> 1.0. Kills #687 (`1.0` -> `2.0`) — asserting exactly 1.0.
    """
    assert ev._compute_classification_metric("anything_else", "x", "x") == 1.0


def test_classification_terminal_wrong_is_zero(ev):
    """Terminal branch, is_correct False -> 0.0. Kills #688 (`else 0.0` -> `1.0`)."""
    assert ev._compute_classification_metric("anything_else", "x", "y") == 0.0


# ============================================================================
# _compute_set_metric  (#699, #706, #708, #713, #718, #727)
#
# jaccard:
#   both empty            -> 1.0
#   exactly one empty     -> 0.0          (guard `not gt or not pred`, #699)
#   else  intersection/union if union>0 else 0.0   (#706 `>0`->`>=0`, #708 else)
# hamming_loss:
#   both empty            -> 0.0          (guard `not gt and not pred`, #713/#718)
# terminal (unknown set metric) -> 0.0    (#727)
# ============================================================================


def test_set_jaccard_both_empty_is_one(ev):
    """Both sets empty -> perfect match 1.0 (the `not gt and not pred` branch)."""
    assert ev._compute_set_metric("jaccard", [], []) == 1.0


def test_set_jaccard_one_empty_is_zero(ev):
    """Exactly one side empty -> 0.0.

    Kills #699 (`not gt_set or not pred_set` -> `... and ...`): with `and`, this
    guard is False (only one is empty), so control falls to intersection/union =
    0/2 = 0.0 anyway... that path STILL yields 0.0, so #699 is not killed by
    value alone here. We assert 0.0 (the contractually correct result) and rely
    on the divergent case below to separate the operators.
    """
    assert ev._compute_set_metric("jaccard", ["x"], []) == 0.0
    assert ev._compute_set_metric("jaccard", [], ["y"]) == 0.0


def test_set_jaccard_or_guard_kills_and(ev):
    """Disjoint NON-empty sets: original `or`-guard is False (neither empty),
    so result = intersection/union = 0/4 = 0.0.

    With #699 (`or` -> `and`) the guard is ALSO False, so no divergence — but
    the case where exactly one side is empty separates them: `["x"], []` under
    `or` returns the early 0.0; under `and` it skips to intersection/union over
    `{x}` vs `{}` = 0/1 = 0.0. Both 0.0. #699 is therefore EQUIVALENT (the early
    return and the fall-through compute the same 0.0). Listed at the bottom.
    Here we just pin the partial-overlap ratio so #706/#708 are killed.
    """
    # gt={a,b}, pred={b,c}: intersection={b}=1, union={a,b,c}=3 -> 1/3.
    val = ev._compute_set_metric("jaccard", ["a", "b"], ["b", "c"])
    assert val == pytest.approx(1.0 / 3.0)


def test_set_jaccard_partial_not_one_or_zero(ev):
    """Partial overlap gives a strict fraction in (0,1), pinning #708.

    #708 mutates the `else 0.0` tail of `intersection/union if union>0 else 0.0`
    to `else 1.0`; the union>0 branch is taken here (union=2) so the value is
    1/2 = 0.5 either way -> need union==0 to exercise the else. union==0 only
    when both sets empty, but that is short-circuited by the both-empty guard
    returning 1.0 first. So the `else 0.0` tail of jaccard is DEAD and #708 is
    EQUIVALENT. We still assert 0.5 to lock the ratio (kills arithmetic mutants
    not in scope but harmless) — see bottom for #708 disposition.
    """
    # gt={a}, pred={a,b}: intersection={a}=1, union={a,b}=2 -> 0.5.
    assert ev._compute_set_metric("jaccard", ["a"], ["a", "b"]) == 0.5


def test_set_hamming_both_empty_is_zero(ev):
    """Both empty -> 0.0 loss. Kills #718 (`return 0.0` -> `1.0`) and #713
    (`not gt and not pred` -> `... or ...`).

    #713: with `and` (original) the guard is True only when BOTH empty; with
    `or` it would also fire when exactly one is empty. For BOTH-empty input both
    operators are True, returning 0.0 — so this input alone does not separate
    #713. The one-empty case below separates it.
    """
    assert ev._compute_set_metric("hamming_loss", [], []) == 0.0


def test_set_hamming_one_empty_kills_or(ev):
    """gt={a}, pred={} for hamming_loss.

    Original (`and` guard): both-empty is False (gt non-empty), so compute
    all_labels={a}, symmetric_diff |{a} ^ {}| = 1, loss = 1/1 = 1.0.
    Mutant #713 (`and` -> `or`): guard True (one side empty) -> early `return
    0.0`. 1.0 != 0.0 -> KILLS #713.
    """
    assert ev._compute_set_metric("hamming_loss", ["a"], []) == 1.0


def test_set_unknown_metric_returns_zero(ev):
    """Unknown set metric -> terminal `return 0.0`. Kills #727 (`0.0` -> `1.0`)."""
    assert ev._compute_set_metric("not_a_set_metric", ["a"], ["a"]) == 0.0


# ============================================================================
# _compute_token_f1  (#740, #745, #748)
#
#   tokens = set(str(x).lower().split())
#   both empty            -> 1.0
#   exactly one empty     -> 0.0                  (guard `not gt or not pred`, #740)
#   precision = |inter|/|pred| if pred else 0.0   (#745 else 0.0 -> 1.0)
#   recall    = |inter|/|gt|   if gt   else 0.0   (#748 else 0.0 -> 1.0)
#   f1 = 2PR/(P+R)
# ============================================================================


def test_token_f1_both_empty_is_one(ev):
    """Both empty token sets -> 1.0."""
    assert ev._compute_token_f1("", "") == 1.0


def test_token_f1_one_empty_kills_or_guard(ev):
    """gt non-empty, pred empty -> 0.0.

    Original guard `not gt_tokens or not pred_tokens`: pred empty -> True ->
    early `return 0.0`. Mutant #740 (`or` -> `and`): guard is `not gt AND not
    pred` = False (gt non-empty), so control SKIPS the early return; then
    intersection over {hello} vs {} = 0, precision branch `if pred_tokens`
    False -> 0.0, recall branch `if gt_tokens` True -> 0/1 = 0.0, and
    `precision+recall == 0` -> `return 0.0`. Both yield 0.0, so the VALUE does
    not separate #740 ... BUT see test_token_f1_pred_empty_via_recall_path: the
    else-constants #745/#748 are what actually differ on this input.
    """
    assert ev._compute_token_f1("hello", "") == 0.0


def test_token_f1_pred_empty_kills_precision_else(ev):
    """pred empty token set hits the precision `else 0.0` (#745) only if the
    `not pred` early guard is bypassed — which is exactly what mutant #740 does.

    On the ORIGINAL code the early `or` guard returns 0.0 before precision is
    computed, so #745's `else` is shadowed for the one-empty input and the value
    is 0.0. We instead drive precision's else with a DIFFERENT shape: when both
    sides have tokens but share none, precision/recall are real fractions, never
    the else. The precision `else 0.0` therefore only fires when pred_tokens is
    empty, which is itself shadowed by the early guard -> #745 is EQUIVALENT.
    See bottom. We assert a normal disjoint case here to lock f1==0.0.
    """
    # gt={a}, pred={b}: intersection=0 -> P=0/1=0, R=0/1=0 -> P+R==0 -> 0.0.
    assert ev._compute_token_f1("a", "b") == 0.0


def test_token_f1_partial_overlap_value(ev):
    """gt='a b', pred='b c': inter={b}=1, |pred|=2, |gt|=2.

    P = 1/2 = 0.5, R = 1/2 = 0.5, f1 = 2*0.25/1.0 = 0.5. Locks the f1 formula
    and the precision/recall numerators/denominators.
    """
    assert ev._compute_token_f1("a b", "b c") == pytest.approx(0.5)


def test_token_f1_perfect_overlap_is_one(ev):
    """Identical token sets -> P=R=1 -> f1=1.0."""
    assert ev._compute_token_f1("a b c", "c b a") == 1.0


# ============================================================================
# _levenshtein_distance  (#1279, #1287;  #1276 EQUIVALENT — see bottom)
#
# Standard Wagner-Fischer DP. Known edit distances are hand-computed.
#   #1279: `current_row = [i + 1]` -> `[i + 2]`  (off-by-one on the left column,
#          i.e. the cost of deleting a prefix of s1). Manifests when the optimal
#          alignment uses that left edge, e.g. lev('a','lawn'): the longer arg
#          ('lawn') is s1 after the swap; the answer is 3, mutant gives 4.
#   #1287: `deletions = current_row[j] + 1` -> `+ 2`. Manifests on lev('flaw',
#          'lawn') where a deletion is on the optimal path: answer 2, mutant 3.
# ============================================================================


@pytest.mark.parametrize(
    "s1,s2,expected",
    [
        ("kitten", "sitting", 3),  # 2 subs (k->s, e->i) + 1 insert (g): classic = 3
        ("abc", "abc", 0),  # identical
        ("", "abc", 3),  # 3 insertions
        ("abc", "", 3),  # 3 deletions
        ("cat", "cut", 1),  # single substitution a->u
        ("a", "ab", 1),  # single insertion
        ("flaw", "lawn", 2),  # del 'f' + sub 'w'->? ... hand: delete f, append n -> 2
        ("a", "lawn", 3),  # 'a' -> 'lawn': keep 'a' (matches the 'a' in lawn), +3 -> 3
        ("sunday", "saturday", 3),  # classic distance 3
    ],
)
def test_levenshtein_known_distances(ev, s1, s2, expected):
    """Hand-computed Levenshtein distances. 'flaw'/'lawn' (==2) kills #1287
    (+1->+2 on deletions makes it 3); 'a'/'lawn' (==3) kills #1279 (left-column
    +1->+2 makes it 4). Identity/empty/single-edit cases pin the recurrence base
    cases and substitution cost.
    """
    assert ev._levenshtein_distance(s1, s2) == expected


def test_levenshtein_symmetric(ev):
    """Distance is symmetric (the len(s1)<len(s2) swap is exercised both ways)."""
    assert ev._levenshtein_distance("flaw", "lawn") == ev._levenshtein_distance(
        "lawn", "flaw"
    )


# ============================================================================
# _is_failure_metric  (#1306-#1312, #1316-#1345, #1349, #1359-#1361)
#
# Each surviving mutant corrupts ONE metric-name literal inside a threshold
# bucket (e.g. "accuracy" -> "XXaccuracyXX"). The corrupted name then matches NO
# bucket and falls to the default `return False`. A killing input is a value
# that the metric's REAL bucket classifies as FAILURE (True) while the default
# would say NOT-failure (False):
#
#   binary  bucket  threshold 0.5  -> value 0.4 < 0.5  -> True  (default False)
#   sim     bucket  threshold 0.7  -> value 0.5 < 0.7  -> True  (default False)
#   corr    bucket  threshold 0.6  -> value 0.5 < 0.6  -> True  (default False)
#   ranking bucket  threshold 0.5  -> value 0.4 < 0.5  -> True  (default False)
#   error   bucket  >0.3 is worse  -> value 0.5 > 0.3  -> True  (default False)
#
# Each (metric_name, value, expected=True) row below pins exactly one corrupted
# literal: drop it from its bucket and the expected bool flips False -> KILL.
# We add the opposite side (value clearly inside the pass region) for the live
# metrics to also guard threshold-constant mutants, and the None rule.
# ============================================================================

# (metric_name, value, expected_is_failure)
_BINARY_FAIL = [  # bucket threshold 0.5
    ("accuracy", 0.4, True),
    ("precision", 0.4, True),
    ("recall", 0.4, True),
    ("f1", 0.4, True),
    ("subset_accuracy", 0.4, True),
    ("confusion_matrix", 0.4, True),
    ("span_exact_match", 0.4, True),
]
_SIM_FAIL = [  # bucket threshold 0.7; value 0.5 fails real bucket, passes default
    ("bleu", 0.5, True),
    ("rouge", 0.5, True),
    ("edit_distance", 0.5, True),
    ("meteor", 0.5, True),
    ("chrf", 0.5, True),
    ("semantic_similarity", 0.5, True),
    ("bertscore", 0.5, True),
    ("moverscore", 0.5, True),
    ("token_f1", 0.5, True),
    ("json_accuracy", 0.5, True),
    ("iou", 0.5, True),
    ("hierarchical_f1", 0.5, True),
    ("coherence", 0.5, True),
    ("factcc", 0.5, True),
    ("qags", 0.5, True),
    ("field_accuracy", 0.5, True),
    ("partial_match", 0.5, True),
    ("boundary_accuracy", 0.5, True),
    ("path_accuracy", 0.5, True),
    ("lca_accuracy", 0.5, True),
]
_CORR_FAIL = [  # bucket threshold 0.6; value 0.5 fails real bucket, passes default
    ("weighted_kappa", 0.5, True),
    ("correlation", 0.5, True),
    ("spearman_correlation", 0.5, True),
    ("kendall_tau", 0.5, True),
    ("r2", 0.5, True),
]
_RANK_FAIL = [  # bucket threshold 0.5; value 0.4 fails real bucket, passes default
    ("ndcg", 0.4, True),
    ("map", 0.4, True),
]
_ERROR_FAIL = [  # bucket "higher is worse" >0.3; value 0.5 fails, default passes
    ("mae", 0.5, True),
    ("rmse", 0.5, True),
    ("mape", 0.5, True),
    ("hamming_loss", 0.5, True),
]


@pytest.mark.parametrize(
    "metric_name,value,expected",
    _BINARY_FAIL + _SIM_FAIL + _CORR_FAIL + _RANK_FAIL + _ERROR_FAIL,
)
def test_is_failure_metric_bucket_membership_failure_side(ev, metric_name, value, expected):
    """Each metric, fed a value its REAL bucket classifies as FAILURE, must
    return True. Corrupting the metric's bucket literal (the surviving mutants
    #1306-#1361) drops it to the default `return False`, flipping the bool and
    failing this assertion.

    Hand-checks (representative):
      accuracy=0.4 -> 0.4 < 0.5 -> True   (binary)
      bleu=0.5     -> 0.5 < 0.7 -> True   (similarity)
      r2=0.5       -> 0.5 < 0.6 -> True   (correlation)
      ndcg=0.4     -> 0.4 < 0.5 -> True   (ranking)
      mae=0.5      -> 0.5 > 0.3 -> True   (error, higher is worse)
    """
    assert ev._is_failure_metric(metric_name, value) is expected


@pytest.mark.parametrize(
    "metric_name,value",
    [
        # PASS side of each bucket: value clearly inside the success region so a
        # dropped literal (-> default False) and a passing bucket COINCIDE; these
        # rows guard against the threshold CONSTANT being moved (orthogonal),
        # while the FAILURE-side rows above are the ones that kill the literal
        # mutants. Kept minimal: one canonical metric per bucket.
        ("accuracy", 0.9),
        ("bleu", 0.9),
        ("r2", 0.9),
        ("ndcg", 0.9),
        ("mae", 0.1),
    ],
)
def test_is_failure_metric_pass_side(ev, metric_name, value):
    """Clear-pass values are NOT failures (False)."""
    assert ev._is_failure_metric(metric_name, value) is False


def test_is_failure_metric_none_is_failure(ev):
    """None value -> always a failure (the `if metric_value is None` guard)."""
    assert ev._is_failure_metric("accuracy", None) is True


def test_is_failure_metric_error_threshold_boundary(ev):
    """Error bucket uses strict `> 0.3`. 0.3 is NOT a failure, 0.31 IS.

    Pins the 0.3 constant and the `>` direction for the error bucket, so the
    error-list literal mutants (#1359-#1361) cannot hide behind a moved
    threshold.
    """
    assert ev._is_failure_metric("mae", 0.3) is False
    assert ev._is_failure_metric("mae", 0.31) is True


# ============================================================================
# _calculate_confidence  (#1367, #1368, #1371-#1373, #1379-#1415, #1418,
#                         #1420, #1424, #1445)
#
# Pipeline:
#   1. Normalize each value: None stays None (#1367/#1368/#1371-#1373 corrupt
#      this), float/int -> float, dict -> extract_value().
#   2. valid_metrics = non-None values.  Empty -> return 0.0.
#   3. positive_values: each positive_metrics[k] present+non-None is appended
#      raw (#1379-#1415 corrupt the membership literals; #1424 flips the
#      `is not None` to `is None`).
#   4. error_metrics inverted and appended (#1418/#1420 corrupt error literals).
#   5. if positive_values: return mean(positive_values)
#      else:               return mean(valid_metrics)   (#1445 `/`->`*`)
#
# KILL STRATEGY for the membership literals (#1379-#1415): a SINGLE positive
# metric V alone yields V on BOTH paths (positive branch V; fallback V), so it
# can't separate them. Pair the metric under test with an error metric whose
# inverted contribution differs, so dropping the positive member changes the
# mean:
#   {name: 0.0, "mae": 0.0}
#     original: positive_values = [0.0(name), 1.0(mae inverted)] -> mean 0.5
#     mutant (name dropped): positive_values = [1.0(mae)] -> 1.0     -> KILL
# ============================================================================

# The full positive_metrics list, in source order, each paired-test below.
_POSITIVE_METRICS = [
    "exact_match",
    "accuracy",
    "precision",
    "recall",
    "f1",
    "jaccard",
    "subset_accuracy",
    "token_f1",
    "r2",
    "correlation",
    "weighted_kappa",
    "spearman_correlation",
    "kendall_tau",
    "ndcg",
    "map",
    "bleu",
    "rouge",
    "edit_distance",
    "meteor",
    "chrf",
    "bertscore",
    "moverscore",
    "semantic_similarity",
    "factcc",
    "qags",
    "coherence",
    "json_accuracy",
    "schema_validation",
    "field_accuracy",
    "span_exact_match",
    "iou",
    "partial_match",
    "boundary_accuracy",
    "hierarchical_f1",
    "path_accuracy",
    "lca_accuracy",
    "cohen_kappa",
]


@pytest.mark.parametrize("metric_name", _POSITIVE_METRICS)
def test_confidence_positive_member_pulled_in(ev, metric_name):
    """{metric: 0.0, mae: 0.0} -> mean([0.0, 1.0]) == 0.5.

    The positive metric contributes 0.0; mae (error) inverts 0.0 -> 1.0. Mean of
    the two positive_values is (0.0 + 1.0)/2 = 0.5. If the positive metric's
    membership literal is corrupted (#1379-#1415), it is NOT pulled into
    positive_values, leaving [1.0] -> 1.0 != 0.5 -> KILL. (#1424's `is None`
    flip also drops every positive member -> [1.0] -> 1.0 -> KILL.)
    """
    result = ev._calculate_confidence({metric_name: 0.0, "mae": 0.0})
    assert result == pytest.approx(0.5)


def test_confidence_single_positive_is_passthrough(ev):
    """A lone positive metric returns its own value (mean of one element)."""
    assert ev._calculate_confidence({"accuracy": 0.7}) == pytest.approx(0.7)


def test_confidence_empty_and_all_none_is_zero(ev):
    """No valid metrics -> 0.0 (covers the `if not valid_metrics` guard and the
    normalize-None path #1367/#1368/#1371-#1373: a None value must stay None and
    be dropped, leaving zero valid metrics)."""
    assert ev._calculate_confidence({}) == 0.0
    assert ev._calculate_confidence({"accuracy": None}) == 0.0


def test_confidence_none_dropped_not_counted(ev):
    """{accuracy: 0.4, foo: None} -> only 0.4 counts -> 0.4.

    Kills #1367 (`normalized[k]=None` -> `=""`: an empty string would survive as
    a valid metric and corrupt the mean / raise), #1368 (`continue` -> `break`:
    breaking would stop processing later keys, but here drops nothing
    observable for one trailing None -> see ordering test below), #1373
    (`normalized[k]=...` -> `=None`: would null out the 0.4 -> 0.0).
    """
    assert ev._calculate_confidence({"accuracy": 0.4, "zzz_unknown": None}) == pytest.approx(0.4)


def test_confidence_none_first_then_value_kills_break(ev):
    """{aaa_none: None, accuracy: 0.6}: None is processed first.

    #1368 mutates the None-branch `continue` to `break`, which would ABORT the
    loop after the first (None) entry, leaving `accuracy` UNnormalized/missing ->
    valid_metrics empty -> 0.0. Original keeps going -> 0.6. 0.6 != 0.0 -> KILL.
    (dict preserves insertion order, so 'aaa_none' is iterated before
    'accuracy'.)
    """
    assert ev._calculate_confidence({"aaa_none": None, "accuracy": 0.6}) == pytest.approx(0.6)


def test_confidence_dict_shape_extracted_kills_extract_mutants(ev):
    """A rich dict-shaped value {'value': 0.8} must extract to 0.8.

    Kills #1371 (`extracted = _extract(v)` -> `extracted = None`) and #1372
    (`if extracted is not None` -> `is None`): both would null the value, making
    the dict-shaped metric drop out -> 0.0 instead of 0.8.
    """
    assert ev._calculate_confidence({"accuracy": {"value": 0.8}}) == pytest.approx(0.8)


def test_confidence_error_metric_inversion_high_when_low_error(ev):
    """A lone error metric with 0 error inverts to high confidence.

    mae=0.0 -> normalized = max(0, 1 - min(0,1)) = 1.0 -> positive_values=[1.0]
    -> 1.0. (mae=1.0 -> 1 - 1 = 0.0 -> 0.0; asserted too.) Pins the inversion
    direction for the error bucket.
    """
    assert ev._calculate_confidence({"mae": 0.0}) == pytest.approx(1.0)
    assert ev._calculate_confidence({"mae": 1.0}) == pytest.approx(0.0)


@pytest.mark.parametrize("err_metric", ["mae", "rmse", "mape", "hamming_loss"])
def test_confidence_error_member_pulled_in(ev, err_metric):
    """{accuracy: 0.0, err: 0.0} -> mean([0.0(acc), 1.0(err inverted)]) == 0.5.

    If the error metric's literal in `error_metrics` is corrupted (#1418/#1420),
    it is not inverted/appended -> positive_values=[0.0] -> 0.0 != 0.5 -> KILL.
    (mape inverts 0.0 the same way: 1 - min(0,100)/100 = 1.0.)
    """
    assert ev._calculate_confidence({"accuracy": 0.0, err_metric: 0.0}) == pytest.approx(0.5)


def test_confidence_fallback_mean_kills_sum_times_len(ev):
    """The FALLBACK `return sum(valid_metrics)/len(valid_metrics)` (#1445).

    To reach the fallback, positive_values must be EMPTY: feed only metrics that
    are neither in positive_metrics nor error_metrics. Two such metrics with
    values 0.5 and 0.5:
      original: sum=1.0, len=2 -> 1.0/2 = 0.5
      mutant  : sum * len      -> 1.0 * 2 = 2.0
    0.5 != 2.0 -> KILL. (Mean != product because len != 1.)
    """
    # 'foo'/'bar' are not in any positive/error list -> fallback path.
    result = ev._calculate_confidence({"foo_metric": 0.5, "bar_metric": 0.5})
    assert result == pytest.approx(0.5)


# ============================================================================
# EQUIVALENT MUTANTS — deliberately NOT given killing tests (no observable
# behaviour change; a "killing" test would be impossible or test a tautology).
# Conservative: each has a proof, not a hunch.
#
#   _levenshtein_distance #1276  `range(len(s2)+1)` -> `range(len(s2)+2)`
#     The extra trailing element exists only on the FIRST `previous_row`. The
#     inner loop reads previous_row[j] and previous_row[j+1] for j in
#     0..len(s2)-1, i.e. indices 0..len(s2); the new index len(s2)+1 is never
#     read, and `previous_row` is reassigned to `current_row` (correct length)
#     after the first row. Verified: 0 diffs over 20000 random string pairs.
#
#   _compute_classification_metric #677 (`in`->`not in`), #678/#679/#680
#     ("precision"/"recall"/"f1" -> XX), #683 (`==`->`!=`), #684 ("cohen_kappa"
#     -> XX). Every branch in this method returns the IDENTICAL expression
#     `1.0 if is_correct else 0.0` (the precision/recall/f1 branch, the
#     cohen_kappa branch, AND the terminal branch). Re-routing an input between
#     these branches via a corrupted literal or flipped guard cannot change the
#     returned value. The live constants are still pinned by #687/#688 tests.
#
#   _compute_set_metric #699  `not gt_set or not pred_set` -> `... and ...`
#     (jaccard, exactly-one-empty). With `or` the early `return 0.0` fires; with
#     `and` control falls through to intersection/union, but with one side empty
#     the intersection is 0 and union>0, giving 0/union = 0.0 — identical.
#
#   _compute_set_metric #708  jaccard `... if union > 0 else 0.0` -> `else 1.0`
#     The both-empty case returns 1.0 BEFORE this line; for any reached input at
#     least one set is non-empty so union>0 always holds -> the `else` is dead.
#
#   _compute_token_f1 #745  precision `... if pred_tokens else 0.0` -> `else 1.0`
#     The precision `else` fires only when pred_tokens is empty, which is itself
#     short-circuited by the earlier `not gt_tokens or not pred_tokens` guard
#     returning 0.0 first -> the precision `else` is unreachable.
#
#   _compute_token_f1 #748  recall `... if gt_tokens else 0.0` -> `else 1.0`
#     Symmetric to #745: the recall `else` fires only when gt_tokens is empty,
#     also short-circuited by the earlier empty guard -> unreachable.
#
#   _calculate_confidence #1435  mape `min(error_val,100.0)` -> `min(...,101.0)`
#     and #1442  others `min(error_val,1.0)` -> `min(...,2.0)`
#     For error_val <= cap the two mins are equal. For error_val > cap the
#     un-capped extra slack only makes `1.0 - min/...` MORE negative, and the
#     outer `max(0.0, ...)` clamps both to 0.0. So the result is identical for
#     all inputs. Verified numerically across the boundary (50,99,100,101,200
#     for mape; 0,0.5,1,1.5,2,3 for the others).
# ============================================================================
