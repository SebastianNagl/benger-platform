"""Analysis specs: schema, semantic rules, normalization and hashing."""

from __future__ import annotations

import copy
import json

import pytest

from analysis.spec import (
    DEFAULT_CONVENTIONS,
    SpecError,
    measure_order,
    normalize_spec,
    spec_hash,
    validate_spec,
)
from analysis_synthetic import role_swap_spec


def _minimal(**extra):
    spec = {
        "spec_version": 1,
        "name": "minimal",
        "inputs": {"designs": ["d"]},
        "measures": {"y": {"kind": "field", "field": "y"}},
        "estimands": [{"id": "m", "estimator": "mean_rate", "outcome": "y"}],
    }
    spec.update(extra)
    return spec


def _errors(spec):
    with pytest.raises(SpecError) as exc:
        validate_spec(spec)
    return " | ".join(exc.value.errors)


def test_the_synthetic_spec_is_valid():
    validate_spec(role_swap_spec())


def test_normalization_fills_every_convention():
    spec = normalize_spec(_minimal(conventions={"ssc": "fixest"}))
    est = spec["estimands"][0]
    assert set(est["conventions"]) == set(DEFAULT_CONVENTIONS)
    assert est["conventions"]["ssc"] == "fixest"
    assert est["scopes"] == ["pooled"] and est["vcov"] == {"type": "iid"}
    assert est["contrasts"] == "terms"
    assert spec["measures"]["y"]["type"] == "number"


def test_estimand_conventions_override_spec_conventions():
    spec = _minimal(conventions={"inference": "t"})
    spec["estimands"][0]["conventions"] = {"inference": "normal", "ci_level": 0.9}
    est = normalize_spec(spec)["estimands"][0]
    assert est["conventions"]["inference"] == "normal" and est["conventions"]["ci_level"] == 0.9


def test_tost_margin_and_single_bound_set_become_a_list_of_bounds():
    spec = normalize_spec(role_swap_spec())
    role = spec["estimands"][0]["contrasts"][0]
    assert role["tost"] == [{"bounds": [-3.0, 3.0], "level": 0.9}, {"bounds": [-2.0, 2.0], "level": 0.9}]
    wrong = [e for e in spec["estimands"] if e["id"] == "wrong_side"][0]
    assert wrong["contrasts"][0]["tost"] == [{"bounds": [-5.0, 5.0], "level": 0.9}]


def test_hash_ignores_key_order_and_changes_with_a_convention():
    spec = role_swap_spec()
    shuffled = json.loads(json.dumps(spec), object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    assert spec_hash(normalize_spec(spec)) == spec_hash(normalize_spec(shuffled))
    changed = copy.deepcopy(spec)
    changed["conventions"]["ci_critical"] = "exact"
    assert spec_hash(normalize_spec(changed)) != spec_hash(normalize_spec(spec))


def test_normalize_does_not_mutate_its_input():
    spec = role_swap_spec()
    before = json.dumps(spec, sort_keys=True)
    normalize_spec(spec)
    assert json.dumps(spec, sort_keys=True) == before


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda s: s.pop("inputs"), "'inputs' is a required property"),
        (lambda s: s.update(spec_version=2), "1 was expected"),
        (lambda s: s["inputs"].update(designs=[]), "should be non-empty"),
        (lambda s: s["measures"].update({"bad name": {"kind": "field", "field": "y"}}), "does not match"),
        (lambda s: s["measures"].update(z={"kind": "field", "field": "y", "by": "x", "fields": {}}), "/measures/z"),
        (lambda s: s["estimands"][0].update(estimator="ols"), "is not one of"),
        (lambda s: s["estimands"][0].update(vcov={"type": "cluster"}), "'by' is a required property"),
        (lambda s: s["estimands"][0].update(vcov={"type": "iid", "by": ["unit"]}), "should not be valid"),
        (lambda s: s.update(conventions={"ssc": "stata"}), "is not one of"),
    ],
)
def test_schema_errors(mutate, message):
    spec = _minimal()
    mutate(spec)
    assert message in _errors(spec)


def test_semantic_errors():
    spec = _minimal(
        measures={
            "y": {"kind": "field", "field": "y"},
            "unit": {"kind": "field", "field": "u"},
            "a": {"kind": "expression", "expr": "b + 1"},
            "b": {"kind": "expression", "expr": "a + 1"},
            "c": {"kind": "expression", "expr": "lambda: 1"},
        },
        filter="1 +",
        estimands=[
            {"id": "m", "estimator": "mean_rate", "outcome": "y", "terms": ["x"]},
            {"id": "m", "estimator": "fe_ols", "outcome": "y", "terms": ["x"], "fixed_effects": [["unit"]], "intercept": True},
            {"id": "f", "estimator": "fe_ols", "outcome": "y"},
            {"id": "p", "estimator": "paired_within", "outcome": "y", "pair_by": ["unit"], "treatment": {"factor": "c", "level": "x"}},
            {
                "id": "t",
                "estimator": "fe_ols",
                "outcome": "y",
                "terms": ["x"],
                "contrasts": [
                    {"id": "a", "weights": {"x": 1}, "tost": {"bounds": [3, -3]}},
                    {"id": "a", "weights": {"x": 1}},
                ],
            },
        ],
        families=[
            {"id": "f1", "method": "bh", "members": [{"estimand": "nope"}]},
            {"id": "f1", "method": "holm", "members": [{"estimand": "t", "contrast": "zz", "scope": "weird"}]},
            {"id": "f2", "method": "bh", "exploratory": True, "missing_p": "count", "members": [{"estimand": "t"}]},
        ],
    )
    text = _errors(spec)
    for fragment in (
        "'unit' is a reserved column name",
        "cycle a -> b -> a",
        "/measures/c/expr",
        "/filter: does not parse",
        "terms: only for fe_ols",
        "duplicate estimand id 'm'",
        "an intercept is absorbed",
        "fe_ols needs 'terms'",
        "needs a 'reference' level",
        "lower must be below upper",
        "duplicate contrast id 'a'",
        "for exploratory families only",
        "unknown estimand 'nope'",
        "duplicate family id 'f1'",
        "unknown contrast 'zz'",
        "use 'pooled'",
        "defined for holm and bonferroni only",
    ):
        assert fragment in text, fragment


def test_measure_order_follows_dependencies():
    measures = {
        "c": {"kind": "expression", "expr": "a + b"},
        "a": {"kind": "field", "field": "a"},
        "b": {"kind": "expression", "expr": "a * 2"},
    }
    assert measure_order(measures) == ["a", "b", "c"]
