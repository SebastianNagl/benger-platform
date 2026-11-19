"""List measures against gold: item extraction and every statistic,
checked on hand-computed sets."""

from __future__ import annotations

import math
import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from analysis.list_measures import check_list_measure, item_set, list_measure_value, statistic  # noqa: E402

A = frozenset({"a", "b", "c"})
G = frozenset({"b", "c", "d", "e"})

# A ∩ G = {b, c}; A \ G = {a}; G \ A = {d, e}; A ∪ G has 5 items.
HAND = {
    "n_answer": 3.0,
    "n_gold": 4.0,
    "hits": 2.0,
    "misses": 2.0,
    "extras": 1.0,
    "precision": 2 / 3,
    "recall": 2 / 4,
    "f1": 2 * (2 / 3) * (1 / 2) / ((2 / 3) + (1 / 2)),  # 4/7
    "jaccard": 2 / 5,
    "exact": 0.0,
    "any": 1.0,
    "all": 0.0,
}


@pytest.mark.parametrize("name", sorted(HAND))
def test_statistics_by_hand(name):
    assert statistic(A, G, name) == pytest.approx(HAND[name], rel=0, abs=1e-15)


def test_f1_hand_value_is_four_sevenths():
    assert statistic(A, G, "f1") == pytest.approx(4 / 7, abs=1e-15)


def test_empty_sets_and_missing_values():
    empty = frozenset()
    assert math.isnan(statistic(empty, G, "precision"))
    assert statistic(empty, G, "recall") == 0.0
    assert math.isnan(statistic(A, empty, "recall"))
    assert math.isnan(statistic(empty, G, "f1"))
    assert statistic(frozenset({"x"}), frozenset({"y"}), "f1") == 0.0
    assert math.isnan(statistic(empty, empty, "jaccard"))
    assert statistic(empty, empty, "exact") == 1.0
    assert statistic(A, empty, "all") == 1.0
    assert math.isnan(statistic(None, G, "hits"))
    assert math.isnan(statistic(A, None, "hits"))
    assert statistic(A, None, "n_answer") == 3.0


def test_items_from_lists_texts_patterns_and_normalization():
    m = {"items": {"pattern": r"\bB\s*([1-5])\b", "template": "B{1}", "flags": ["IGNORECASE"]}}
    assert item_set(["b 5", "B2 and B 3", None, {"x": 1}], m) == frozenset({"B5", "B2", "B3"})
    assert item_set("relied on B1, b 4 and B9", m) == frozenset({"B1", "B4"})
    assert item_set(None, m) is None
    assert item_set([], m) == frozenset()
    split = {"split": r"[;,]", "normalize": ["strip", "casefold"]}
    assert item_set(" Foo; bar ,FOO,, ", split) == frozenset({"foo", "bar"})
    assert item_set([1, 2.0, True], {}) == frozenset({"1", "2", "true"})
    assert item_set("a  b", {"normalize": ["collapse_whitespace"]}) == frozenset({"a b"})


def test_measure_value_against_task_gold_and_fixed_values():
    m = {"statistic": "recall", "gold": {"path": "gold.items"}, "normalize": ["casefold"]}
    assert list_measure_value(m, ["A", "x"], {"gold": {"items": ["a", "b"]}}) == 0.5
    assert math.isnan(list_measure_value(m, ["A"], {"gold": {}}))
    fixed = {"statistic": "any", "gold": {"values": ["B5"]}}
    assert list_measure_value(fixed, ["B5", "B1"], {}) == 1.0
    assert list_measure_value(fixed, ["B1"], {}) == 0.0


def test_checks():
    assert check_list_measure({"statistic": "recall"}, "/m") == ["/m: statistic 'recall' needs 'gold'"]
    assert check_list_measure({"statistic": "n_answer"}, "/m") == []
    bad = check_list_measure({"statistic": "hits", "gold": {"values": []}, "items": {"pattern": "(", "template": "x"}}, "/m")
    assert "does not compile" in bad[0]
    group = check_list_measure(
        {"statistic": "hits", "gold": {"values": []}, "items": {"pattern": "(a)", "template": "{2}"}}, "/m"
    )
    assert "group {2} does not exist" in group[0]


def test_list_measure_in_a_frame():
    from analysis.frame import build_frame
    from analysis.observations import observations_from_records
    from analysis.spec import normalize_spec

    records = [
        {"generation_id": "g1", "task_id": "t1", "model_id": "m", "design": "d", "unit": "u1",
         "fields": {"cited": ["B1", "B5"]}, "task_data": {"gold": {"unusable": ["B5"]}}},
        {"generation_id": "g2", "task_id": "t2", "model_id": "m", "design": "d", "unit": "u2",
         "fields": {"cited": []}, "task_data": {"gold": {"unusable": ["B5"]}}},
        {"generation_id": "g3", "task_id": "t3", "model_id": "m", "design": "d", "unit": "u3",
         "fields": {}, "task_data": {"gold": {"unusable": ["B5"]}}},
    ]
    spec = normalize_spec({
        "spec_version": 1, "name": "lists", "inputs": {"designs": ["d"]},
        "measures": {
            "flags_key": {"kind": "list", "field": "cited", "statistic": "any", "gold": {"path": "gold.unusable"}},
            "n_cited": {"kind": "list", "field": "cited", "statistic": "n_answer"},
        },
        "estimands": [{"id": "e", "estimator": "mean_rate", "outcome": "flags_key"}],
    })
    frame = build_frame(observations_from_records(records), spec).frame
    assert frame["flags_key"].tolist()[:2] == [1.0, 0.0] and math.isnan(frame["flags_key"].tolist()[2])
    assert frame["n_cited"].tolist()[:2] == [2.0, 0.0]
