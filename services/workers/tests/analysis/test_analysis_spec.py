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


def _est(**kw):
    return dict({"id": "e", "outcome": "y"}, **kw)


def test_estimator_extension_rules():
    spec = _minimal(
        measures={
            "y": {"kind": "field", "field": "y"},
            "t": {"kind": "field", "field": "risk_{idx}"},
            "o": {"kind": "field", "field": "risk_{idx}", "slot": "other"},
            "p": {"kind": "slot_factor", "factor": "group", "slot": "own"},
            "q": {"kind": "field", "field": "plain", "slot": 1},
            "twice": {"kind": "field", "field": "a_{idx}_{idx}", "slot": 1},
            "slot": {"kind": "field", "field": "y"},
        },
        estimands=[
            _est(id="a", estimator="logit", terms=["x"], method="within", fixed_effects=[["unit"]],
                 conventions={"ssc": "fixest", "reml": False}),
            _est(id="b", estimator="mean_rate", players=["p", "p"]),
            _est(id="c", estimator="mixedlm", terms=["x"], vcov={"type": "cluster", "by": ["unit"]}),
            _est(id="d", estimator="spearman", x="x", vcov={"type": "iid"}, joint_tests=[{"id": "j", "parameters": ["*"]}]),
            _est(id="e", estimator="plackett_luce", terms=["x"], vcov={"type": "hc1"}),
            _est(id="f", estimator="fe_ols", terms=["x"],
                 contrasts=[{"id": "m", "kind": "ame", "column": "g", "level": "a", "reference": "b"}],
                 joint_tests=[{"id": "m", "contrasts": ["zz"]}]),
            _est(id="g", estimator="bradley_terry", players=["p", "p"], reference="z", levels=["a", "b"]),
            _est(id="h", estimator="mixedlm", terms=["x"]),
        ],
        lookups=[
            {"id": "l", "rows": [{"k": 1}], "keys": {"g": "k"}, "columns": {"y": "v", "slot": "v"}, "fill": {"zz": 0}},
            {"id": "l", "rows": [{"k": 1, "v": 1}], "keys": {"g": "k"}, "columns": {"slot": "v"}},
        ],
    )
    text = _errors(spec)
    for fragment in (
        "/measures/t: a field with {idx} needs a slot frame",
        "/measures/o/slot: 'other' needs a slot frame",
        "/measures/p/slot: 'own' is the row's slot",
        "/measures/q/slot: 'slot' needs {idx} in the field name",
        "/measures/twice: 'a_{idx}_{idx}' must contain {idx} once",
        "/measures/slot: 'slot' is a reserved column name",
        "/estimands/0/method: logit takes its fixed effects as dummies only",
        "/estimands/0/conventions/reml: not a convention of logit",
        "/estimands/0/conventions/ssc: logit takes 'statsmodels' or 'none'",
        "/estimands/1/players: only for bradley_terry",
        "/estimands/2/vcov: mixedlm reports the model-based (iid) variance only",
        "/estimands/2: mixedlm needs 'groups'",
        "/estimands/3/vcov: spearman has no variance estimator",
        "/estimands/3/joint_tests: spearman has no parameters to test jointly",
        "/estimands/4/vcov: plackett_luce takes iid or cluster",
        "/estimands/4/choice_set: plackett_luce ranks the slots of a generation by default",
        "/estimands/5/contrasts/0: average marginal effects are for logit only",
        "/estimands/5/joint_tests/0/id: 'm' is already a contrast or joint test",
        "/estimands/5/joint_tests/0/contrasts: unknown contrast 'zz'",
        "/estimands/6/players: the two player columns must differ",
        "/estimands/6/reference: not one of the levels",
        "/lookups/0/columns/y: 'y' is already a frame column or measure",
        "/lookups/0/fill/zz: not one of the lookup's columns",
        "/lookups/0/rows/0: missing v",
        "/lookups/1/id: duplicate lookup id 'l'",
        "/lookups/1/columns/slot: another lookup adds 'slot'",
        "/estimands/7: mixedlm needs 'groups'",
    ):
        assert fragment in text, fragment


def test_schema_refuses_a_lookup_with_both_or_neither_source():
    both = _minimal(lookups=[{"id": "l", "rows": [{"k": 1}], "table": {"name": "t", "version": 1},
                              "keys": {"g": "k"}, "columns": {"c": "k"}}])
    assert "/lookups/0" in _errors(both)
    neither = _minimal(lookups=[{"id": "l", "keys": {"g": "k"}, "columns": {"c": "k"}}])
    assert "/lookups/0" in _errors(neither)


def test_normalization_of_the_extensions():
    spec = normalize_spec(_minimal(
        frame={"unit": "slot"},
        conventions={"reml": False, "ml_max_iter": 50},
        measures={"y": {"kind": "field", "field": "risk_{idx}"}, "g": {"kind": "slot_factor", "factor": "group", "slot": "other"}},
        lookups=[{"id": "l", "rows": [{"k": 1, "v": 2}], "keys": {"g": "k"}, "columns": {"c": "v"}}],
        estimands=[
            _est(id="ols", estimator="fe_ols", terms=["c"]),
            _est(id="lg", estimator="logit", terms=["c"], fixed_effects=[["unit"]],
                 contrasts=[{"id": "m", "kind": "ame", "column": "c", "level": 1, "reference": 0}]),
            _est(id="mx", estimator="mixedlm", terms=["c"], groups=["unit"]),
            _est(id="pl", estimator="plackett_luce", terms=["c"]),
            _est(id="bt", estimator="bradley_terry", players=["g", "g2"], reference="a"),
            _est(id="sp", estimator="spearman", x="c"),
        ],
    ))
    assert spec["measures"]["y"]["slot"] == "own"
    assert spec["lookups"][0]["fill"] == {}
    ols, lg, mx, pl, bt, sp = spec["estimands"]
    assert set(ols["conventions"]) == set(DEFAULT_CONVENTIONS)
    assert lg["conventions"]["ml_max_iter"] == 50 and lg["conventions"]["informative_only"] is True
    assert "reml" not in lg["conventions"] and lg["method"] == "dummies" and lg["intercept"] is False
    assert lg["contrasts"][0] == {"id": "m", "kind": "ame", "column": "c", "level": 1, "reference": 0, "scale": 1.0, "null": 0.0}
    assert mx["conventions"]["reml"] is False and mx["intercept"] is True
    assert mx["conventions"]["mixedlm_optimizers"] == ["lbfgs", "powell", "bfgs"]
    assert pl["choice_set"] == ["generation_id"] and "stages" not in pl
    assert bt["link"] == "logit" and bt["fixed_effects"] == [] and bt["terms"] == []
    assert "vcov" not in sp and sp["contrasts"] == "terms"


def test_specs_without_the_extensions_hash_as_before():
    # the engine's new keys are only added where a spec uses them
    spec = normalize_spec(role_swap_spec())
    assert "frame" not in spec and "lookups" not in spec
    assert all(set(e["conventions"]) == set(DEFAULT_CONVENTIONS) for e in spec["estimands"])
