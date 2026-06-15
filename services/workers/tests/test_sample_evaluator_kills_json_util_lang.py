"""Hand-computed mutation-KILL tests for ml_evaluation/sample_evaluator.py.

These target SURVIVING mutants (from the mutmut baseline captured in the
gitignored ``_surv_diffs.txt``) across the JSON-comparison, value-coercion,
and language-heuristic helpers. A surviving mutant here = a silently wrong
published benchmark score (json/field accuracy) or a broken parse / language
tag. Each test asserts the EXACT constant / boundary / formula the mutation
changes, with the expected value HAND-COMPUTED in the docstring so a flipped
operator, wrong constant, off-by-one, or wiped collection fails.

Methods covered (mutant id ranges in `_surv_diffs.txt`):
  - _compute_metric              #137-146 (registry dispatch)
  - _compute_structured_metric   #1051-1071 (json_accuracy / schema_validation)
  - _json_field_accuracy         #1077-1105
  - _compute_field_accuracy      #1448-1462
  - _compare_json_fields         #1463-1517
  - _to_set                      #728-729
  - _to_list                     #842-846
  - _serialize_value             #1295-1301
  - _detect_language_heuristic   #1741-1799

Validate (PASS-only, NO mutmut), from repo root:
  docker compose -f infra/docker-compose.test.yml --profile test run --rm \
    --entrypoint /bin/sh test-workers-runner -c \
    'pip install -q -r requirements-test.txt; cd /app; python -m pytest -q \
     --no-cov -o addopts= -p no:cacheprovider \
     tests/test_sample_evaluator_kills_json_util_lang.py 2>&1 | tail -20'

EQUIVALENT mutants intentionally NOT asserted (with reasons) are listed at the
bottom of this file and tagged inline where relevant.
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
# _compute_metric  (#137-146) — registry-first dispatch.
#
# The registry path and the legacy chain return the SAME value for built-ins,
# so to PIN the dispatch we register throw-away probe handlers at runtime
# (registering a handler is a legitimate test action; it does not edit source).
# Cleanup removes them so the process-singleton registry is left untouched.
# ============================================================================


@pytest.fixture
def registry_probe():
    """Register probe handlers under names with NO legacy branch.

    - 'mut_probe_metric' -> {"value": 0.7}  (a fixed sentinel != legacy)
    - 'mut_probe_none'   -> {"value": None} (forces extract_value -> None)

    A name with no built-in branch means the legacy chain RAISES ValueError
    ("Unknown metric"); so any mutant that bypasses the registry path is
    caught by the sentinel assertions below.
    """
    from ml_evaluation import metric_registry
    from ml_evaluation.handlers import MetricHandler

    class _ProbeValue(MetricHandler):
        name = "mut_probe_metric"

        def compute(self, ground_truth, prediction, answer_type, parameters=None):
            return {"value": 0.7, "method": self.name, "details": {}, "error": None}

    class _ProbeNone(MetricHandler):
        name = "mut_probe_none"

        def compute(self, ground_truth, prediction, answer_type, parameters=None):
            return {"value": None, "method": self.name, "details": {}, "error": None}

    added = []
    for h in (_ProbeValue(), _ProbeNone()):
        # Direct dict insert avoids the "already registered" warning path and
        # lets us guarantee a clean removal regardless of register() internals.
        metric_registry._handlers[h.name] = h
        added.append(h.name)
    try:
        yield metric_registry
    finally:
        for n in added:
            metric_registry._handlers.pop(n, None)


def test_compute_metric_registry_path_carries_handler_value(ev, registry_probe):
    """#141 (_handler = registry.get(name) -> None) and
    #142 (if _handler is not None -> is None).

    Original: the registered handler returns {"value": 0.7}; extract_value ->
    0.7; _compute_metric returns 0.7. Both mutants bypass the handler block,
    fall to _compute_metric_legacy('mut_probe_metric', ...) which has NO branch
    -> raises ValueError. So asserting == 0.7 fails for either mutant.
    """
    assert ev._compute_metric("mut_probe_metric", "x", "y", "text", {}) == 0.7


def test_compute_metric_none_value_defaults_to_zero(ev, registry_probe):
    """#146 (float(_value if _value is not None else 0.0) -> else 1.0).

    The probe returns {"value": None} -> extract_value -> None -> the
    `_value is None` branch -> original float(0.0) == 0.0. Mutant -> float(1.0)
    == 1.0. Pin to 0.0.
    """
    assert ev._compute_metric("mut_probe_none", "x", "y", "text", {}) == 0.0


def test_compute_metric_preserves_passed_parameters(ev):
    """#137 (if parameters is None -> is not None).

    Route 'field_accuracy' through the registry (its _LegacyMetricHandler calls
    _compute_metric_legacy -> _compute_field_accuracy, which reads strict_types).
    gt/pred are JSON STRINGS (so _normalize_value's str().lower() keeps them
    valid JSON) with a value that is equal-by-==  but type-different: 1 (int)
    vs 1.0 (float).

    With params={"strict_types": True} PRESERVED:
      _compare_json_fields -> key 'a' both present, strict_types True,
      type(1) != type(1.0) -> += 0.0 -> 0.0/1 == 0.0.
    Mutant #137 makes `if parameters is not None` true for the passed dict and
    REWRITES parameters = {} -> strict_types defaults False -> not strict ->
    direct compare 1 == 1.0 (True) -> += 1.0 -> 1.0/1 == 1.0.
    Pin to 0.0.
    """
    score = ev._compute_metric(
        "field_accuracy", '{"a": 1}', '{"a": 1.0}', "text", {"strict_types": True}
    )
    assert score == 0.0


# ============================================================================
# _compute_structured_metric  (#1051-1071)
# ============================================================================


def test_structured_json_accuracy_one_none_returns_zero(ev):
    """#1053 (json_accuracy one-is-JSON branch `return 0.0` -> 1.0).

    gt='not json' -> _parse_json -> None; pred='{"a": 1}' -> dict.
    Both-None? no. One-None? yes -> original returns 0.0. Mutant -> 1.0.
    (#1051, the `or`->`and` on this guard, is equivalent: the downstream
    _json_field_accuracy(None, dict) also returns 0.0 via its type-mismatch
    guard — see EQUIVALENT notes.)
    """
    assert ev._compute_structured_metric("json_accuracy", "not json", '{"a": 1}') == 0.0


def test_structured_schema_pred_not_json_returns_zero(ev):
    """#1063 (schema_validation `if pred_json is None: return 0.0` -> 1.0).

    A non-empty schema is provided (so the `if not schema` shortcut is skipped),
    pred is not valid JSON -> pred_json None -> original 0.0. Mutant -> 1.0.
    """
    score = ev._compute_structured_metric(
        "schema_validation", "{}", "definitely not json",
        {"schema": {"type": "object"}},
    )
    assert score == 0.0


def test_structured_schema_validation_failure_returns_zero(ev):
    """#1066 (schema_validation `except ValidationError: return 0.0` -> 1.0).

    pred='123' parses to int 123; schema requires a string -> jsonschema raises
    ValidationError -> original returns 0.0. Mutant -> 1.0.
    """
    score = ev._compute_structured_metric(
        "schema_validation", '"x"', "123", {"schema": {"type": "string"}}
    )
    assert score == 0.0


def test_structured_invalid_schema_raises_runtime_error(ev):
    """#1069 (raise RuntimeError(f"Invalid JSON schema: {e}") message mutated to
    "XXInvalid JSON schema: {e}XX").

    A schema whose `type` value is itself invalid (123 is not a valid JSON-Schema
    type) makes jsonschema raise SchemaError -> wrapped as RuntimeError whose
    message STARTS WITH 'Invalid JSON schema'. The mutant's message starts with
    'XXInvalid' so the anchored `^Invalid JSON schema` regex fails for it.
    """
    with pytest.raises(RuntimeError, match=r"^Invalid JSON schema"):
        ev._compute_structured_metric(
            "schema_validation", '{"a": 1}', '{"a": 1}', {"schema": {"type": 123}}
        )


def test_structured_unknown_metric_returns_zero(ev):
    """#1071 (final fallthrough `return 0.0` -> 1.0).

    A metric_name that is neither json_accuracy nor schema_validation skips both
    branches -> original returns 0.0. Mutant -> 1.0.
    """
    assert ev._compute_structured_metric("totally_unknown_metric", "a", "b") == 0.0


# ============================================================================
# _json_field_accuracy  (#1077-1105)
# ============================================================================


def test_jfa_empty_gt_nonempty_pred_is_zero(ev):
    """#1077 (`return 1.0 if not pred_json else 0.0` -> else 1.0) for empty dict gt.

    gt={} (empty dict), pred={"a":1}. Both dict (type match); `not gt` True ->
    `return 1.0 if not pred else 0.0`; `not {"a":1}` is False -> original 0.0.
    Mutant -> 1.0.
    """
    assert ev._json_field_accuracy({}, {"a": 1}) == 0.0


def test_jfa_both_empty_dicts_is_one(ev):
    """#1094 (`return 1.0 ...` -> 2.0) and #1095 (`if not pred_json` -> `if pred_json`).

    gt={} pred={}. `not gt` True -> `return 1.0 if not pred else 0.0`;
    `not {}` True -> original 1.0. #1094 -> 2.0. #1095 -> `1.0 if {} else 0.0`
    -> `if {}` False -> 0.0. Pin to 1.0.
    """
    assert ev._json_field_accuracy({}, {}) == 1.0


def test_jfa_nested_recursion_accumulates_not_overwrites(ev):
    """#1089 (`matching_keys += self._json_field_accuracy(...)` -> `=`).

    Three top-level keys a,b,c, each a nested dict {"x":1,"y":9} vs {"x":1,"y":8}.
    For each key the values are NOT == (so the recursion branch is taken):
      inner _jfa({"x":1,"y":9},{"x":1,"y":8}): all_keys={x,y}; x equal -> +1;
      y unequal, non-container -> +0 -> 1/2 = 0.5.
    Original: matching_keys = 0.5+0.5+0.5 = 1.5 -> 1.5/3 = 0.5.
    Mutant `=`: matching_keys is overwritten each iteration to the (order-
    independent) recursion value 0.5 -> final 0.5 -> 0.5/3 = 0.1667.
    Pin to 0.5.
    """
    gt = {"a": {"x": 1, "y": 9}, "b": {"x": 1, "y": 9}, "c": {"x": 1, "y": 9}}
    pred = {"a": {"x": 1, "y": 8}, "b": {"x": 1, "y": 8}, "c": {"x": 1, "y": 8}}
    assert ev._json_field_accuracy(gt, pred) == pytest.approx(0.5)


def test_jfa_empty_gt_nonempty_pred_else_branch(ev):
    """#1096 (`return 1.0 if not pred_json else 0.0` -> else 1.0, empty gt path).

    gt={} pred={"a":1}: `not gt` True -> `1.0 if not {"a":1} else 0.0` -> else
    0.0. Mutant -> 1.0. (Same call as #1077 but kept distinct for clarity of
    the `else` constant; #1077 is the line-1685 occurrence, #1096 likewise.)
    """
    assert ev._json_field_accuracy({}, {"a": 1}) == 0.0


def test_jfa_primitive_equal_is_one(ev):
    """#1103 (`return 1.0 ...` -> 2.0) and #1104 (`gt == pred` -> `!=`).

    gt=5 pred=5 (ints, primitive branch): `1.0 if 5==5 else 0.0` -> 1.0.
    #1103 -> 2.0. #1104 -> `1.0 if 5!=5 else 0.0` -> 0.0. Pin to 1.0.
    """
    assert ev._json_field_accuracy(5, 5) == 1.0


def test_jfa_primitive_unequal_is_zero(ev):
    """#1105 (`... else 0.0` -> else 1.0, primitive branch).

    gt=5 pred=6: `1.0 if 5==6 else 0.0` -> 0.0. Mutant -> 1.0. Pin to 0.0.
    """
    assert ev._json_field_accuracy(5, 6) == 0.0


# ============================================================================
# _compute_field_accuracy  (#1448-1462)
#  NOTE: this method parses gt/pred via _parse_json directly (no normalize),
#  so JSON strings are parsed faithfully.
# ============================================================================


def test_cfa_ignore_keys_param_is_read(ev):
    """#1448 (`parameters.get("ignore_keys", [])` -> typo'd key "XXignore_keysXX").

    gt={"a":1,"b":2}, pred={"a":1,"b":99}, ignore_keys=["b"].
    Original: all_keys = ({a,b}|{a,b}) - {b} = {a}; a matches -> 1.0/1 = 1.0.
    Mutant reads the typo key -> ignore_keys defaults [] -> all_keys={a,b};
    a matches (+1), b: 2 != 99 (+0) -> 1.0/2 = 0.5. Pin to 1.0.
    """
    score = ev._compute_field_accuracy(
        '{"a": 1, "b": 2}', '{"a": 1, "b": 99}', {"ignore_keys": ["b"]}
    )
    assert score == 1.0


def test_cfa_strict_types_true_param_is_read(ev):
    """#1450 (`parameters.get("strict_types", False)` -> typo key) and
    #1452 (`strict_types = None`).

    gt={"a":1}, pred={"a":1.0}, params={"strict_types": True}.
    Original strict: type(1) != type(1.0) -> += 0.0 -> 0.0.
    #1450 reads typo key -> default False -> not strict -> 1 == 1.0 (True) -> 1.0.
    #1452 sets strict_types=None (falsy) -> not strict -> 1.0.
    Pin to 0.0.
    """
    score = ev._compute_field_accuracy(
        '{"a": 1}', '{"a": 1.0}', {"strict_types": True}
    )
    assert score == 0.0


def test_cfa_strict_types_default_is_false(ev):
    """#1451 (`parameters.get("strict_types", False)` default -> True).

    gt={"a":1}, pred={"a":1.0}, NO strict_types param.
    Original default False -> not strict -> 1 == 1.0 -> 1.0.
    Mutant default True -> strict -> type mismatch -> 0.0. Pin to 1.0.
    """
    assert ev._compute_field_accuracy('{"a": 1}', '{"a": 1.0}', {}) == 1.0


def test_cfa_both_non_json_is_one(ev):
    """#1455/#1456 (both-None guard operands flipped) and #1458 (`return 1.0` -> 2.0).

    gt and pred are both unparseable -> gt_json None, pred_json None.
    Original: `gt is None and pred is None` True -> return 1.0.
    #1455 (`gt is not None and ...`) -> False -> next `gt None or pred None`
    True -> 0.0. #1456 (`... and pred is not None`) -> False -> 0.0.
    #1458 -> 2.0. Pin to 1.0.
    """
    assert ev._compute_field_accuracy("not json", "also not json") == 1.0


def test_cfa_both_none_guard_uses_and_not_or(ev):
    """#1457 (`gt is None and pred is None` -> `or`).

    gt='not json' (None), pred='{"a":1}' (dict). Original first guard
    (`None is None and dict is None`) is False -> second guard
    (`None is None or dict is None`) True -> return 0.0.
    Mutant #1457 makes first guard `None is None or dict is None` True ->
    return 1.0 (wrongly declaring a non-JSON vs JSON pair a perfect match).
    Pin to 0.0.
    """
    assert ev._compute_field_accuracy("not json", '{"a": 1}') == 0.0


def test_cfa_one_none_returns_zero(ev):
    """#1462 (`if gt_json is None or pred_json is None: return 0.0` -> return 1.0).

    gt='not json' (None), pred='{"a":1}' (dict) -> one-None -> original 0.0.
    Mutant -> 1.0. Pin to 0.0.
    (#1461, `or`->`and` on this guard, is equivalent: with `and` the one-None
    case falls through to _compare_json_fields(None, dict) whose type-mismatch
    guard also returns 0.0 — see EQUIVALENT notes.)
    """
    assert ev._compute_field_accuracy("not json", '{"a": 1}') == 0.0


# ============================================================================
# _compare_json_fields  (#1463-1517)
#  Signature: (gt_obj, pred_obj, ignore_keys, strict_types, path="")
# ============================================================================

EMPTY: set = set()


def test_cjf_type_mismatch_is_zero(ev):
    """#1465 (type-mismatch `return 0.0` -> 1.0).

    gt={} (dict), pred=[] (list): type(dict) != type(list) -> original 0.0.
    Mutant -> 1.0. Pin to 0.0.
    """
    assert ev._compare_json_fields({}, [], EMPTY, False) == 0.0


def test_cjf_dict_gt_nonempty_pred_empty_is_zero(ev):
    """#1466 (dict guard `not gt_obj` -> `gt_obj`) and #1468 (`and` -> `or`).

    gt={"a":1}, pred={}. Original: `not {"a":1} and not {}` = False -> continue;
    all_keys={a}; a in gt not in pred -> one-missing -> +0.0 -> 0.0/1 = 0.0.
    #1466: `{"a":1} and not {}` = True -> early `return 1.0`.
    #1468: `not gt or not pred` = `False or True` = True -> early `return 1.0`.
    Pin to 0.0.
    """
    assert ev._compare_json_fields({"a": 1}, {}, EMPTY, False) == 0.0


def test_cjf_dict_gt_empty_pred_nonempty_is_zero(ev):
    """#1467 (dict guard `not pred_obj` -> `pred_obj`).

    gt={}, pred={"a":1}. Original: `not {} and not {"a":1}` = `True and False`
    = False -> continue; all_keys={a}; a not in gt, in pred -> one-missing ->
    +0.0 -> 0.0/1 = 0.0.
    #1467: `not {} and {"a":1}` = `True and (truthy)` = True -> early return 1.0.
    Pin to 0.0.
    """
    assert ev._compare_json_fields({}, {"a": 1}, EMPTY, False) == 0.0


def test_cjf_key_union_not_intersection(ev):
    """#1470 (`set|set` -> `&`), #1472 (all_keys = None), #1473 (`if not all_keys`
    -> `if all_keys`).

    gt={"a":1,"b":2}, pred={"a":1,"c":3}. UNION keys = {a,b,c} (3).
      a present-equal -> +1.0; b in gt only -> +0.0; c in pred only -> +0.0.
      -> 1.0/3 = 0.3333.
    #1470 (intersection {a}): a equal -> 1.0/1 = 1.0.
    #1472 (all_keys=None): `if not None` True -> return 1.0.
    #1473 (`if all_keys`): non-empty -> early return 1.0.
    Pin to 1/3.
    """
    score = ev._compare_json_fields(
        {"a": 1, "b": 2}, {"a": 1, "c": 3}, EMPTY, False
    )
    assert score == pytest.approx(1.0 / 3.0)


def test_cjf_all_keys_empty_after_ignore_is_one(ev):
    """#1474 (`if not all_keys: return 1.0` -> 2.0).

    gt={"a":1}, pred={"a":1}, ignore_keys={"a"}. both non-empty so the
    both-empty guard is skipped; all_keys = ({a}|{a}) - {a} = {} -> empty ->
    original `return 1.0`. Mutant -> 2.0. Pin to 1.0.
    """
    assert ev._compare_json_fields({"a": 1}, {"a": 1}, {"a"}, False) == 1.0


def test_cjf_gt_only_key_scores_zero_not_one(ev):
    """#1479 (`key not in gt_obj` -> `key in gt_obj`), #1481 (`and` -> `or`), and
    #1490 (one-missing `+= 0.0` -> `+= 1.0`).

    gt={"a":1,"b":2}, pred={"a":1}. UNION {a,b}.
      a present-equal -> +1.0; b in gt only -> one-missing -> +0.0 -> 1.0/2 = 0.5.
    #1479: for key b, `b in gt and b not in pred` True -> the BOTH-MISSING
      branch `+= 1.0` -> (a also hits it: `a in gt and a not in pred` False ->
      else both-present +1.0) -> 2.0/2 = 1.0.
    #1481: `key not in gt or key not in pred` True for b -> both-missing +1.0
      -> 2.0/2 = 1.0.
    #1490: one-missing increment becomes +1.0 -> b contributes 1.0 -> 2.0/2 = 1.0.
    All three -> 1.0; original 0.5. Pin to 0.5 (order-independent: sum is
    commutative).
    """
    assert ev._compare_json_fields({"a": 1, "b": 2}, {"a": 1}, EMPTY, False) == 0.5


def test_cjf_pred_only_key_scores_zero_not_one(ev):
    """#1480 (`key not in pred_obj` -> `key in pred_obj`).

    gt={"a":1}, pred={"a":1,"b":2}. UNION {a,b}.
      a present-equal -> +1.0; b in pred only -> one-missing -> +0.0 -> 0.5.
    #1480: for b, `b not in gt and b in pred` True -> both-missing +1.0 ->
      2.0/2 = 1.0. Pin to 0.5.
    """
    assert ev._compare_json_fields({"a": 1}, {"a": 1, "b": 2}, EMPTY, False) == 0.5


def test_cjf_strict_types_mismatch_is_zero(ev):
    """#1493 (`strict_types and type != type` -> `==`) and #1497 (strict-mismatch
    `+= 0.0` -> `+= 1.0`).

    gt={"a":1}, pred={"a":1.0}, strict_types=True. Single key a, both present:
      strict True and type(1) != type(1.0) True -> += 0.0 -> 0.0/1 = 0.0.
    #1493 (`==`): strict True and type==type False -> else direct compare
      1 == 1.0 True -> += 1.0 -> 1.0.
    #1497: strict-mismatch increment +1.0 -> 1.0/1 = 1.0.
    Pin to 0.0.
    """
    assert ev._compare_json_fields({"a": 1}, {"a": 1.0}, EMPTY, True) == 0.0


def test_cjf_strict_types_guard_uses_and_not_or(ev):
    """#1494 (`strict_types and ...` -> `strict_types or ...`).

    gt={"a":1}, pred={"a":1.0}, strict_types=False. Single key a both present:
      Original: `False and type != type` -> False -> else direct 1 == 1.0 True
      -> += 1.0 -> 1.0.
      Mutant `or`: `False or type(1) != type(1.0)` -> True -> += 0.0 -> 0.0.
    Pin to 1.0.
    """
    assert ev._compare_json_fields({"a": 1}, {"a": 1.0}, EMPTY, False) == 1.0


def test_cjf_nested_recursion_subtract_mutant(ev):
    """#1499 (nested `matching_score += self._compare_json_fields(...)` -> `-=`).

    gt={"a":{"x":1}}, pred={"a":{"x":1}}. Single key a; values are equal dicts
    BUT the dict-vs-dict `==` short-circuits to True only at the increment...
    actually a==a means equality check, so use unequal-but-recursing values to
    force the recursion path:
      gt={"a":{"x":1}}, pred={"a":{"x":2}} -> a not ==, isinstance dict ->
      recurse _compare({"x":1},{"x":2}) -> x: 1 != 2 -> 0.0/1 = 0.0.
      Original += 0.0 -> 0.0. That does NOT distinguish +=/-= (both 0.0).
    So we need a POSITIVE recursion result: gt={"a":{"x":1,"y":9}},
      pred={"a":{"x":1,"y":8}} -> recurse -> x match (+1), y mismatch (+0) ->
      1/2 = 0.5. Original += 0.5 -> 0.5/1 = 0.5. Mutant -= 0.5 -> -0.5/1 = -0.5.
    Pin to 0.5.
    """
    gt = {"a": {"x": 1, "y": 9}}
    pred = {"a": {"x": 1, "y": 8}}
    assert ev._compare_json_fields(gt, pred, EMPTY, False) == pytest.approx(0.5)


def test_cjf_nested_recursion_overwrite_mutant(ev):
    """#1498 (nested `matching_score += self._compare_json_fields(...)` -> `=`).

    Three top-level keys a,b,c each recursing to 0.5 (as in #1499's positive
    case). Original: 0.5+0.5+0.5 = 1.5 -> 1.5/3 = 0.5.
    Mutant `=` overwrites matching_score to the LAST recursion result (0.5,
    order-independent since every recursion returns 0.5) -> 0.5/3 = 0.1667.
    Pin to 0.5.
    """
    gt = {
        "a": {"x": 1, "y": 9},
        "b": {"x": 1, "y": 9},
        "c": {"x": 1, "y": 9},
    }
    pred = {
        "a": {"x": 1, "y": 8},
        "b": {"x": 1, "y": 8},
        "c": {"x": 1, "y": 8},
    }
    assert ev._compare_json_fields(gt, pred, EMPTY, False) == pytest.approx(0.5)


def test_cjf_direct_value_mismatch_is_zero(ev):
    """#1504 (`1.0 if gt_val == pred_val else 0.0` -> else 1.0, dict member).

    gt={"a":1}, pred={"a":2}: single key a both present, not strict, not
    container -> 1 == 2 False -> += 0.0 -> 0.0/1 = 0.0. Mutant else 1.0 -> 1.0.
    Pin to 0.0.
    """
    assert ev._compare_json_fields({"a": 1}, {"a": 2}, EMPTY, False) == 0.0


def test_cjf_both_empty_lists_is_one(ev):
    """#1506/#1507 (list both-empty guard operands flipped) and #1509 (`return
    1.0` -> 2.0) for two empty lists.

    gt=[], pred=[]. Original: `not [] and not []` True -> return 1.0.
    #1506 (`gt_obj and not pred_obj`): `[] and ...` falsy -> continue -> len
      0==0 -> matching=sum(empty)=0 -> 0/len([]) -> ZeroDivisionError (raises).
    #1507 (`not gt and pred`): `True and []` falsy -> continue -> same
      ZeroDivisionError.
    #1509: return 2.0.
    Pin to 1.0 (any raise or 2.0 fails this).
    """
    assert ev._compare_json_fields([], [], EMPTY, False) == 1.0


def test_cjf_list_length_mismatch_is_zero(ev):
    """#1508 (list both-empty guard `and` -> `or`), #1510 (`len != len` ->
    `len == len`), #1511 (length-mismatch `return 0.0` -> 1.0).

    gt=[1,2], pred=[1]. Original: not both empty; `len 2 != len 1` True ->
    return 0.0.
    #1508 (`or`): `not [1,2] or not [1]` ... actually for THIS input gt non-
      empty; we instead use gt=[],pred=[1] below for #1508. For #1510 the
      `len == len` flip -> False -> matching=sum(zip([1,2],[1]))=cmp(1,1)=1.0
      -> 1.0/len([1,2]) = 1.0/2 = 0.5.
    #1511: length-mismatch returns 1.0.
    Pin to 0.0.
    """
    assert ev._compare_json_fields([1, 2], [1], EMPTY, False) == 0.0


def test_cjf_list_empty_vs_nonempty_is_zero(ev):
    """#1507/#1508 (list both-empty guard) with gt=[], pred=[1].

    Original: `not [] and not [1]` = `True and False` = False -> continue;
    len 0 != len 1 True -> return 0.0.
    #1507 (`not [] and [1]`) = `True and truthy` True -> return 1.0.
    #1508 (`not [] or not [1]`) = `True or False` True -> return 1.0.
    Pin to 0.0.
    """
    assert ev._compare_json_fields([], [1], EMPTY, False) == 0.0


def test_cjf_list_sum_not_none(ev):
    """#1513 (`matching_score = sum(...)` -> `matching_score = None`).

    gt=[1,2], pred=[1,2]: len match; matching = cmp(1,1)+cmp(2,2) = 2.0 ->
    2.0/2 = 1.0. Mutant None -> `None / 2` -> TypeError (raises). Pin to 1.0.
    """
    assert ev._compare_json_fields([1, 2], [1, 2], EMPTY, False) == 1.0


def test_cjf_list_divides_by_length(ev):
    """#1514 (`matching_score / len(gt_obj)` -> `* len(gt_obj)`).

    gt=[1,2], pred=[1,2]: matching=2.0; original 2.0/2 = 1.0; mutant 2.0*2 = 4.0.
    Pin to 1.0.
    """
    assert ev._compare_json_fields([1, 2], [1, 2], EMPTY, False) == 1.0


def test_cjf_primitive_equal_is_one(ev):
    """#1515 (primitive `return 1.0 ...` -> 2.0) and #1516 (`==` -> `!=`).

    gt=5, pred=5 (not dict/list): `1.0 if 5==5 else 0.0` -> 1.0. #1515 -> 2.0;
    #1516 -> `1.0 if 5!=5 else 0.0` -> 0.0. Pin to 1.0.
    """
    assert ev._compare_json_fields(5, 5, EMPTY, False) == 1.0


def test_cjf_primitive_unequal_is_zero(ev):
    """#1517 (primitive `... else 0.0` -> else 1.0).

    gt=5, pred=6: `1.0 if 5==6 else 0.0` -> 0.0. Mutant -> 1.0. Pin to 0.0.
    """
    assert ev._compare_json_fields(5, 6, EMPTY, False) == 0.0


# ============================================================================
# _to_set  (#728-729)
# ============================================================================


def test_to_set_json_list_string(ev):
    """#728 (`parsed = json.loads(value)` -> `parsed = None`).

    '["a","b"]' -> json.loads -> ["a","b"] -> set -> {"a","b"}.
    Mutant parsed=None -> not a list -> falls to `{value}` = {'["a","b"]'}.
    Pin to {"a","b"}.
    """
    assert ev._to_set('["a", "b"]') == {"a", "b"}


def test_to_set_none_is_empty(ev):
    """#729 (`elif value is None` -> `is not None`).

    None -> original `set()`. Mutant `None is not None` False -> else `{None}`.
    Pin to empty set.
    """
    assert ev._to_set(None) == set()


# ============================================================================
# _to_list  (#842-846)
# ============================================================================


def test_to_list_json_list_string(ev):
    """#842 (`parsed = json.loads(value)` -> `parsed = None`).

    '["a","b","c"]' -> json.loads -> list -> returned as-is.
    Mutant parsed=None -> not list -> (the string contains commas) ->
    split(',') -> ['["a"', '"b"', '"c"]'] which != ["a","b","c"]. Pin exactly.
    """
    assert ev._to_list('["a", "b", "c"]') == ["a", "b", "c"]


def test_to_list_comma_split(ev):
    """#843 (`if ',' in value` -> `if 'XX,XX' in value`), #844 (`',' in` ->
    `',' not in`), #845 (`value.split(',')` -> `value.split('XX,XX')`).

    'a,b,c' is not valid JSON -> comma path. Original -> ['a','b','c'].
    #843: 'XX,XX' not in 'a,b,c' -> False -> return ['a,b,c'].
    #844: ',' not in 'a,b,c' -> False -> return ['a,b,c'].
    #845: 'a,b,c'.split('XX,XX') -> ['a,b,c'].
    Pin to ['a','b','c'].
    """
    assert ev._to_list("a,b,c") == ["a", "b", "c"]


def test_to_list_none_is_empty(ev):
    """#846 (`elif value is None` -> `is not None`).

    None -> original []. Mutant -> else `[None]`. Pin to [].
    """
    assert ev._to_list(None) == []


# ============================================================================
# _serialize_value  (#1295-1301)  — exact-dict assertions pin every key/value.
# ============================================================================


def test_serialize_primitive_exact_dict(ev):
    """#1295 (`"value"` -> `"XXvalueXX"`) and #1296 (`"type"` -> `"XXtypeXX"`),
    primitive branch (str).

    'hello' -> {"value": "hello", "type": "str"}. Any key rename breaks the
    exact-dict assertion.
    """
    assert ev._serialize_value("hello") == {"value": "hello", "type": "str"}


def test_serialize_list_exact_dict(ev):
    """#1297 (`"value"` -> `"XXvalueXX"`) and #1298 (`"type"` -> `"XXtypeXX"`),
    list/dict branch.

    [1,2] -> {"value": [1,2], "type": "list"}.
    """
    assert ev._serialize_value([1, 2]) == {"value": [1, 2], "type": "list"}


def test_serialize_other_exact_dict(ev):
    """#1299 (`"value"` -> "XXvalueXX"), #1300 (`"type"` -> "XXtypeXX"), #1301
    (`"string"` -> "XXstringXX"), the else branch.

    A tuple is neither (str,int,float,bool,None) nor (list,dict) -> else branch
    -> {"value": str((1,2)), "type": "string"} = {"value": "(1, 2)",
    "type": "string"}.
    """
    assert ev._serialize_value((1, 2)) == {"value": "(1, 2)", "type": "string"}


# ============================================================================
# _detect_language_heuristic  (#1741-1799)
# ============================================================================

# German article tokens, one per article (#1741-1755). Each sentence:
#   - starts with the article (lowercase -> words[0].lower() matches),
#   - has NO umlaut/eszett (so german_char_pattern stays False),
#   - is all-lowercase after the article (so cap_ratio == 0),
#   - is a single sentence (so german_start_ratio == 1/1 == 1.0 > 0.3).
# Original -> 'de'. Removing THAT article from the set -> start_count 0 -> 'en'.
GERMAN_ARTICLES = [
    "der", "die", "das", "ein", "eine", "dem", "den", "des",
    "einem", "einer", "eines", "im", "am", "zum", "zur",
]


@pytest.mark.parametrize("article", GERMAN_ARTICLES)
def test_detect_each_german_article_yields_de(ev, article):
    """#1741-1755 (each article string mutated to "XX<article>XX"), plus
    #1756 (german_articles = None -> TypeError on membership test),
    #1762 (first-loop `words = None` -> no count),
    #1763 (`words[0]` -> `words[1]`),
    #1764 (`in german_articles` -> `not in`),
    #1767 (`german_start_count += 1` -> `-= 1`),
    #1794 (`german_start_ratio > 0.3` -> `> 1.3` makes the start signal dead).

    Each sentence's ONLY German signal is the leading article -> ratio 1.0 >
    0.3 -> 'de'. Any mutation that drops that article, mis-indexes the first
    word, flips the membership, decrements the count, or raises the threshold
    above the max ratio (1.0) makes it 'en' (or raises). Pin to 'de'.
    """
    sentence = f"{article} katze rennt sehr weit fort"
    assert ev._detect_language_heuristic([sentence]) == "de"


def test_detect_plain_english_is_en(ev):
    """#1757 (`ch in text` -> `ch not in text`), #1760 (`german_start_count = 0`
    -> 1), #1761 (`= None` -> ratio TypeError), #1765 (`if words and ...` ->
    `if words or ...`), #1771 (`german_start_ratio = None` -> `None > 0.3`
    TypeError), #1772 (`capitalized_non_initial = 0` -> 1), #1773 (`= None` ->
    cap_ratio TypeError), #1775 (`total_non_initial = None` -> += TypeError),
    #1776 (second-loop `words = None` -> `None[1:]` TypeError), #1779
    (`cleaned = None` -> .isalpha AttributeError), #1792 (`cap_ratio = None` ->
    `None > 0.15` TypeError), #1799 (`return 'en'` -> "XXenXX").

    'the cat sat on the mat': no umlaut (char_pattern False), words[0]='the'
    not a German article (start_count 0, ratio 0), words[1:] all lowercase
    (cap 0/5 = 0). All three OR-terms False -> 'en'. Pin to 'en'.
    """
    assert ev._detect_language_heuristic(["the cat sat on the mat"]) == "en"


def test_detect_umlaut_only_is_de(ev):
    """#1759 (`german_char_pattern = None` -> falsy, umlaut signal lost),
    #1797 (`char_pattern or start>0.3` -> `char_pattern and start>0.3`),
    #1798 (`return 'de'` -> "XXdeXX").

    'the cät sat on the mat': the ONLY German signal is 'ä'. char_pattern True;
    start_ratio 0; cap_ratio 0. Original -> 'de'.
    #1759: char_pattern None (falsy) -> 'en'.
    #1797: `(True and 0 > 0.3=False) or cap_ratio>0.15=False` -> 'en'.
    Pin to 'de'.
    """
    assert ev._detect_language_heuristic(["the cät sat on the mat"]) == "de"


def test_detect_uppercase_X_char_set_unmutated(ev):
    """#1758 (`'äöüÄÖÜß'` -> `'XXäöüÄÖÜßXX'`).

    'the report is filed under X for now today': no umlaut, 'the' not an
    article, single-letter 'X' is len 1 (skipped in cap count) -> all signals
    False -> 'en'. The mutant adds 'X' to the char set; the uppercase 'X' in
    the text then trips german_char_pattern -> 'de'. Pin to 'en'.
    """
    assert (
        ev._detect_language_heuristic(["the report is filed under X for now today"])
        == "en"
    )


def test_detect_cap_only_german_is_de(ev):
    """#1796 (`cap_ratio > 0.15` -> `> 1.15` makes the cap signal dead),
    #1788 (`capitalized_non_initial += 1` -> `-= 1`).

    'start Hans Maria Klaus Berlin Koeln Bonn': no umlaut (Koeln, not Köln),
    'start' not an article (start_ratio 0). words[1:] = 6 Capitalized words ->
    cap 6, total 6 -> cap_ratio 1.0 > 0.15 -> 'de' via capitalization only.
    #1796: 1.0 > 1.15 False -> 'en'. #1788: cap = -6 -> -6/6 = -1.0 -> 'en'.
    Pin to 'de'.
    """
    s = "start Hans Maria Klaus Berlin Koeln Bonn"
    assert ev._detect_language_heuristic([s]) == "de"


def test_detect_start_count_overwrite_two_articles(ev):
    """#1766 (`german_start_count += 1` -> `= 1`).

    5 sentences: 2 start with a German article, 3 are plain English. No umlaut,
    all lowercase (cap 0). german_start_count: original 2 -> 2/5 = 0.4 > 0.3 ->
    'de'. Mutant `= 1`: each article match SETS count to 1 -> final 1 -> 1/5 =
    0.2 <= 0.3 -> 'en'. Pin to 'de'.
    """
    sentences = [
        "der hund rennt",
        "die katze schlaeft",
        "cats are nice",
        "dogs run fast",
        "birds can fly",
    ]
    assert ev._detect_language_heuristic(sentences) == "de"


def test_detect_start_count_increment_and_ratio_div(ev):
    """#1768 (`german_start_count += 1` -> `+= 2`) and #1769
    (`german_start_count / max(len,1)` -> `* max(len,1)`).

    4 sentences: 1 German article start, 3 plain English. No umlaut, all
    lowercase (cap 0). Original: count 1, ratio 1/4 = 0.25 <= 0.3 -> 'en'.
    #1768: count 2 -> 2/4 = 0.5 > 0.3 -> 'de'. #1769: 1 * 4 = 4 > 0.3 -> 'de'.
    Pin to 'en'.
    """
    sentences = [
        "der hund rennt",
        "cats are nice",
        "dogs run fast",
        "birds can fly",
    ]
    assert ev._detect_language_heuristic(sentences) == "en"


def test_detect_start_ratio_threshold_strict_gt(ev):
    """#1793 (`german_start_ratio > 0.3` -> `>= 0.3`).

    10 sentences: exactly 3 start with German articles, 7 plain English; no
    umlaut, all lowercase (cap 0). german_start_ratio = 3/10 = 0.30 exactly.
    Original `0.30 > 0.3` False -> 'en'. Mutant `0.30 >= 0.3` True -> 'de'.
    Pin to 'en'.
    """
    sentences = [
        "der hund rennt",
        "die katze schlaeft",
        "das auto faehrt",
        "cats are nice",
        "dogs run fast",
        "birds can fly",
        "fish can swim",
        "trees grow tall",
        "rain falls down",
        "wind blows hard",
    ]
    assert ev._detect_language_heuristic(sentences) == "en"


def test_detect_words_two_slice_skips_word_one(ev):
    """#1777 (`for word in words[1:]` -> `words[2:]`), #1774
    (`total_non_initial = 0` -> 1), #1786 (`cleaned[0].isupper()` ->
    `cleaned[1].isupper()`).

    'go Hans and run or jump now': words[0]='go' (not article). words[1:] =
    [Hans, and, run, or, jump, now] -> 6 qualifying, cap = 1 (Hans) ->
    cap_ratio 1/6 = 0.1667 > 0.15 -> 'de'.
    #1777: words[2:] = [and, run, or, jump, now] -> cap 0 -> 0 -> 'en'.
    #1774: total starts 1 -> total 7 -> 1/7 = 0.143 <= 0.15 -> 'en'.
    #1786: cleaned[1] of 'Hans' = 'a' (not upper) -> cap 0 -> 'en'.
    Pin to 'de'.
    """
    assert ev._detect_language_heuristic(["go Hans and run or jump now"]) == "de"


def test_detect_total_reset_and_decrement(ev):
    """#1783 (`total_non_initial += 1` -> `= 1`), #1784 (`-= 1`), #1789
    (`capitalized_non_initial += 1` -> `+= 2`), #1790 (`capitalized_non_initial
    / max(total,1)` -> `* max(total,1)`).

    'go Tom run jump walk swim hike bike skip': words[0]='go'. words[1:] =
    8 qualifying lowercase words + 1 capital (Tom) -> total 8, cap 1 ->
    cap_ratio 1/8 = 0.125 <= 0.15 -> 'en'.
    #1783: total = 1 -> 1/1 = 1.0 -> 'de'. #1784: total = -8 -> max(-8,1)=1 ->
      1/1 = 1.0 -> 'de'. #1789: cap = 2 -> 2/8 = 0.25 -> 'de'. #1790: 1 * 8 =
      8 -> 'de'. Pin to 'en'.
    """
    s = "go Tom run jump walk swim hike bike skip"
    assert ev._detect_language_heuristic([s]) == "en"


def test_detect_total_double_mutant(ev):
    """#1785 (`total_non_initial += 1` -> `+= 2`).

    'go Tom run jump walk': words[1:] = [Tom, run, jump, walk] -> total 4,
    cap 1 (Tom) -> 1/4 = 0.25 > 0.15 -> 'de'. Mutant: total 8 -> 1/8 = 0.125
    <= 0.15 -> 'en'. Pin to 'de'.
    """
    assert ev._detect_language_heuristic(["go Tom run jump walk"]) == "de"


def test_detect_cap_reset_two_capitals(ev):
    """#1787 (`capitalized_non_initial += 1` -> `= 1`).

    'go Tom Ana run jump walk swim hike bike': words[1:] = 8 qualifying, 2
    capitals (Tom, Ana) -> cap 2, total 8 -> 2/8 = 0.25 > 0.15 -> 'de'.
    Mutant `= 1`: cap reset to 1 -> 1/8 = 0.125 <= 0.15 -> 'en'. Pin to 'de'.
    """
    s = "go Tom Ana run jump walk swim hike bike"
    assert ev._detect_language_heuristic([s]) == "de"


def test_detect_len_threshold_ge_two(ev):
    """#1780 (`len(cleaned) >= 2` -> `> 2`) and #1781 (`>= 2` -> `>= 3`).

    'run Ab xy xy xy xy xy': words[1:] = [Ab, xy, xy, xy, xy, xy] -> all len 2.
    Original `>= 2`: all 6 qualify, cap 1 (Ab) -> 1/6 = 0.1667 > 0.15 -> 'de'.
    #1780 (`> 2`): every word is len 2 -> none qualifies -> total 0 ->
      cap_ratio 0/max(0,1) = 0 -> 'en'.
    #1781 (`>= 3`): same -> none qualifies -> 'en'.
    Pin to 'de'.
    """
    assert ev._detect_language_heuristic(["run Ab xy xy xy xy xy"]) == "de"


def test_detect_isalpha_and_len_guard_uses_and(ev):
    """#1782 (`cleaned.isalpha() and len >= 2` -> `or`).

    'go K V K V K done here now': words[1:] = [K, V, K, V, K, done, here, now].
    Original `and`: single letters fail len >= 2 -> skipped; qualifying =
    [done, here, now] all lowercase -> cap 0, total 3 -> 0 -> 'en'.
    Mutant `or`: each single capital letter has isalpha True -> counted ->
    cap += 1 for K,V,K,V,K (5) -> total 8, cap 5 -> 5/8 = 0.625 > 0.15 -> 'de'.
    Pin to 'en'.
    """
    assert ev._detect_language_heuristic(["go K V K V K done here now"]) == "en"


def test_detect_strip_char_set_unmutated(ev):
    """#1778 (`word.strip('.,;:!?()[]"\\'')` -> `'XX...XX'` adds 'X' to stripped
    chars).

    'go Xen Xup Xon Xit Xup go': words[1:] = [Xen, Xup, Xon, Xit, Xup, go].
    Original strip removes only punctuation -> 'Xen' stays 'Xen' (X uppercase,
    counted as capital). 5 capitals, total 6 -> 5/6 = 0.833 > 0.15 -> 'de'.
    Mutant strips leading 'X' -> 'en','up','on','it','up' (lowercase first
    char) -> cap 0 -> 0/6 = 0 -> 'en'. Pin to 'de'.
    """
    assert ev._detect_language_heuristic(["go Xen Xup Xon Xit Xup go"]) == "de"


def test_detect_cap_ratio_threshold_strict_gt(ev):
    """#1795 (`cap_ratio > 0.15` -> `>= 0.15`).

    words[0]='go' then 3 Capitalized len-2 words (Ab, Cd, Ef) + 17 lowercase
    len-2 words ('xy') -> total 20, cap 3 -> cap_ratio 3/20 = 0.15 exactly.
    No umlaut, 'go' not an article (start_ratio 0). Original `0.15 > 0.15`
    False -> 'en'. Mutant `0.15 >= 0.15` True -> 'de'. Pin to 'en'.
    """
    sentence = "go Ab Cd Ef " + " ".join(["xy"] * 17)
    assert ev._detect_language_heuristic([sentence]) == "en"


def test_detect_cap_decrement_multi_capital_english(ev):
    """#1783-family sanity / direct cap-decrement crossover (#1784) on an
    English-baseline sentence with one capital.

    'go Tom run jump walk swim hike bike skip' has cap 1, total 8 -> 0.125 ->
    'en'. (#1784 `total -= 1` -> total -8 -> max 1 -> 1/1 = 1.0 -> 'de'.)
    Covered above; this is an explicit 'en' pin so the decrement mutants are
    double-anchored. Pin to 'en'.
    """
    s = "go Tom run jump walk swim hike bike skip"
    assert ev._detect_language_heuristic([s]) == "en"


# ============================================================================
# EQUIVALENT MUTANTS (intentionally NOT asserted) — confirmed by reading source
# ----------------------------------------------------------------------------
# _compare_json_fields:
#   #1463  path default "" -> "XXXX"               : `path` only feeds key_path,
#   #1477  key_path f"{path}.{key}" -> "XX...XX"   :  which only ever becomes the
#   #1478  key_path = None                          :  `path` arg of a recursive
#   #1512  list f"{path}[{i}]" -> "XX...XX"         :  call. `path`/`key_path`
#          are NEVER read in any numeric branch -> cannot change the score.
#   #1482  both-missing `+= 1.0` -> `= 1.0`         : the both-missing branch
#   #1483  both-missing `+= 1.0` -> `-= 1.0`        :  (key not in gt AND not in
#   #1484  both-missing `+= 1.0` -> `+= 2.0`        :  pred) is UNREACHABLE because
#          all_keys is the UNION minus ignore_keys; every key is in gt or pred.
#   #1488  one-missing `+= 0.0` -> `= 0.0`          : the `= 0.0` reset only
#   #1495  strict-mismatch `+= 0.0` -> `= 0.0`      :  differs from `+= 0.0` when
#          the running matching_score is already > 0 at that key; whether the
#          one-missing / strict-mismatch key is iterated AFTER an accumulating
#          match depends on Python set-iteration order of all_keys, which is not
#          guaranteed across hash seeds. No order-independent kill exists, so
#          these are skipped (conservative).
#   #1489  one-missing `+= 0.0` -> `-= 0.0`         : `-= 0.0` is arithmetically
#   #1496  strict-mismatch `+= 0.0` -> `-= 0.0`     :  identical to `+= 0.0`.
#
# _json_field_accuracy:
#   #1092  `... if all_keys else 1.0` -> `else 2.0` : the `else` is dead — we
#          only reach this line when gt_json is a NON-EMPTY dict (the empty-dict
#          guard returns earlier), so all_keys (>= gt's keys) is always truthy.
#
# _compute_field_accuracy / _compute_structured_metric:
#   #1461  `gt is None or pred is None` -> `and`    : with `and`, the one-None
#   #1051  `gt is None or pred is None` -> `and`    :  case falls through to
#          _compare_json_fields(None, dict) / _json_field_accuracy(None, dict),
#          whose `type(None) != type(dict)` guard ALSO returns 0.0 -> identical
#          result either way.
#
# _detect_language_heuristic:
#   #1770  `german_start_count / max(len(sentences),1)` -> `max(...,2)` : differs
#          only when len(sentences) <= 1; with a single sentence the ratio is
#          1.0 (article) vs 0.5 — both > 0.3 -> same 'de'; with 0 article -> 0
#          vs 0. The language decision never changes.
#   #1791  `cap_ratio = capitalized/max(total,1)` -> `max(total,2)` : differs
#          only when total <= 1; total==1,cap==1 -> 1.0 vs 0.5 (both > 0.15);
#          total<=1,cap==0 -> 0 vs 0. Decision never changes.
#
# _compute_metric:
#   #138   `parameters = {}` -> `parameters = None` : only fires when the caller
#          passed parameters=None; both downstream consumers (the legacy handler
#          `dict(parameters) if parameters else {}` and _compute_metric_legacy's
#          own `if parameters is None: parameters = {}`) fully tolerate None ->
#          identical result.
#
# _compute_structured_metric:
#   #1070  `RuntimeError("Schema validation failed: ...")` message mutated : the
#          generic `except Exception` branch requires jsonschema to raise an
#          exception that is NEITHER ValidationError NOR SchemaError. Reliably
#          provoking that is jsonschema-version-dependent ($ref resolution
#          errors changed class across versions), so no stable, source-edit-free
#          trigger exists; skipped (conservative). The sibling message mutant
#          #1069 (SchemaError -> "Invalid JSON schema") IS killed above.
# ============================================================================
