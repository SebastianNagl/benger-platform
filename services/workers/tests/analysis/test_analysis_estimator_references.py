"""The estimator extensions against recorded reference implementations.

``reference_values_estimators.json`` holds the results of independent
reference implementations of every new estimator (statsmodels formula fits
over patsy designs, a scipy-optimised rank-ordered logit with a numerical
Hessian, scipy's rank correlation) on the synthetic records of
:mod:`estimator_synthetic` and :mod:`analysis_synthetic`. A harness outside
this repository computed them; only the synthetic inputs (the generators
here) and the resulting numbers are kept. The engine must reproduce every
estimate, standard error, statistic and p-value at 1e-9 relative:

* logit with cluster-robust variance and average marginal effects (t with
  G-1 degrees of freedom), with a group x gender interaction;
* MixedLM with a random intercept per name (REML, the optimizer cascade);
* Wald joint tests on a cluster-robust OLS (named contrasts, all group terms,
  interactions) and on Bradley-Terry strengths and two-way clustered OLS;
* Bradley-Terry as a logit with fixed effects on informative cells, and its
  linear probability version;
* Plackett-Luce over five stages and the rank-1 conditional logit on the
  slots of a docket (slot frame, rank validity from a slot aggregate),
  sandwich variance clustered by docket without a small-sample factor; the
  reference's own BFGS stopping point is replaced by its converged maximum
  (the record keeps how far the default stop was off);
* a lookup table joined by system, offence and group, and a frame stacking
  two projects (each project's estimates equal the reference on its data);
* Spearman's rho per system x role x scenario.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from analysis.frame import build_frame
from analysis.observations import observations_from_records
from analysis.runner import run_spec
from analysis.spec import normalize_spec
from analysis_synthetic import MEASURES, role_swap_records
from estimator_synthetic import (
    DOCKET_GROUPS,
    PAIR_GROUPS,
    SECOND_PROJECT_SEED,
    SINGLE_GROUPS,
    congruence_lookup,
    congruence_pooled,
    docket_records,
    pairs_records,
    single_records,
)

HERE = os.path.dirname(os.path.abspath(__file__))
REL = 1e-9

with open(os.path.join(HERE, "reference_values_estimators.json"), encoding="utf-8") as fh:
    REF = json.load(fh)


def _close(mine, ref, what):
    assert mine is not None, what
    assert math.isclose(mine, ref, rel_tol=REL, abs_tol=0.0 if ref else 1e-300), (what, mine, ref)


def _run(records, spec):
    normalized = normalize_spec({"spec_version": 1, "name": "reference", **spec})
    built = build_frame(observations_from_records(records), normalized, home_project="proj_a")
    result = run_spec(built.frame, normalized)
    return {(r["estimand_id"], r["contrast_id"], r["scope"]): r for r in result.estimates}, built


GROUP = {"dummies": "group", "reference": "ref"}
GENDER = {"dummies": "gender", "reference": "f"}
SINGLE_TERMS = [GROUP, GENDER, {"dummies": "system", "reference": "sys_a"}, {"interact": [GROUP, GENDER]}]
NAMED = [g for g in SINGLE_GROUPS if g not in ("ref", "control")]


def _group_weights(g):
    return {f"group[{g}]": 1.0, f"group[{g}]:gender[m]": 0.5}


@pytest.fixture(scope="module")
def single():
    spec = {
        "inputs": {"designs": ["single"]},
        "measures": {"probation": {"kind": "field", "field": "probation"}, "months": {"kind": "field", "field": "months"}},
        "estimands": [
            {
                "id": "logit",
                "estimator": "logit",
                "outcome": "probation",
                "terms": SINGLE_TERMS,
                "vcov": {"type": "cluster", "by": ["name_id"]},
                "conventions": {"inference": "t"},
                "contrasts": [
                    {"id": g, "kind": "ame", "column": "group", "level": g, "reference": "ref", "scale": 100}
                    for g in NAMED + ["control"]
                ],
            },
            {
                "id": "mixed",
                "estimator": "mixedlm",
                "outcome": "months",
                "terms": SINGLE_TERMS,
                "groups": ["name_id"],
                "contrasts": [{"id": g, "weights": _group_weights(g)} for g in NAMED + ["control"]],
            },
            {
                "id": "ols",
                "estimator": "fe_ols",
                "outcome": "months",
                "terms": SINGLE_TERMS,
                "vcov": {"type": "cluster", "by": ["name_id"]},
                "contrasts": [{"id": g, "weights": _group_weights(g)} for g in NAMED + ["control"]],
                "joint_tests": [
                    {"id": "joint_named", "contrasts": NAMED},
                    {"id": "joint_incl_control", "contrasts": NAMED + ["control"]},
                    {"id": "joint_all_group_terms", "parameters": ["group[*]"]},
                    {"id": "group_x_gender", "rows": [{f"group[{g}]:gender[m]": 1.0} for g in NAMED]},
                ],
            },
        ],
    }
    return _run(single_records(), spec)[0]


def test_logit_average_marginal_effects(single):
    for g, ref in REF["single"]["logit_ame"].items():
        row = single[("logit", g, "pooled")]
        assert row["status"] == "ok" and row["kind"] == "ame"
        for key, mine in (("est", "estimate"), ("se", "std_error"), ("p", "p_value"), ("ci_lo", "ci_lower"), ("ci_hi", "ci_upper")):
            _close(row[mine], ref[key], f"ame {g} {key}")
        assert row["df"] == row["n_clusters"][0] - 1


def test_mixedlm_random_intercept(single):
    for g, ref in REF["single"]["mixedlm"].items():
        row = single[("mixed", g, "pooled")]
        assert row["status"] == "ok"
        for key, mine in (("est", "estimate"), ("se", "std_error"), ("p", "p_value")):
            _close(row[mine], ref[key], f"mixedlm {g} {key}")


def test_mixedlm_variance_component():
    spec = {
        "spec_version": 1,
        "name": "re",
        "inputs": {"designs": ["single"]},
        "measures": {"months": {"kind": "field", "field": "months"}},
        "estimands": [{"id": "mixed", "estimator": "mixedlm", "outcome": "months", "terms": SINGLE_TERMS, "groups": ["name_id"]}],
    }
    normalized = normalize_spec(spec)
    built = build_frame(observations_from_records(single_records()), normalized)
    fit = run_spec(built.frame, normalized).fits[0]
    ref = next(iter(REF["single"]["mixedlm"].values()))["re_var"]
    _close(fit["random_intercept_variance"], ref, "random intercept variance")
    assert fit["optimizer"] == "lbfgs" and fit["reml"] is True


def test_wald_joint_tests_on_cluster_ols(single):
    for name, ref in REF["single"]["ols_joint"].items():
        row = single[("ols", name, "pooled")]
        assert row["kind"] == "wald" and row["status"] == "ok"
        _close(row["statistic"], ref["chi2"], f"{name} chi2")
        _close(row["p_value"], ref["p"], f"{name} p")
        assert row["df"] == ref["df"]


@pytest.mark.parametrize("link", ["logit", "linear"])
def test_bradley_terry(link):
    spec = {
        "inputs": {"designs": ["pairs"]},
        "measures": {
            "choice": {"kind": "field", "field": "choice"},
            "first_wins": {"kind": "expression", "expr": "1 * (choice == 1)"},
            "g1": {"kind": "slot_factor", "factor": "group", "slot": 1},
            "g2": {"kind": "slot_factor", "factor": "group", "slot": 2},
        },
        "estimands": [
            {
                "id": "bt",
                "estimator": "bradley_terry",
                "outcome": "first_wins",
                "players": ["g1", "g2"],
                "reference": "ref",
                "link": link,
                "fixed_effects": [["system", "case"]],
                "vcov": {"type": "cluster", "by": ["unit"]},
                "joint_tests": [{"id": "strengths", "parameters": ["strength[*]"]}],
            }
        ],
    }
    rows, _ = _run(pairs_records(), spec)
    ref = REF["pairs"]["logit" if link == "logit" else "linear"]
    for g in PAIR_GROUPS[1:]:
        row = rows[("bt", f"strength[{g}]", "pooled")]
        r = ref["terms"][g]
        _close(row["estimate"], r["est"], f"{link} {g} est")
        _close(row["std_error"], r["se"], f"{link} {g} se")
        if r["separation"]:
            assert row["status"] == "separation" and row["p_value"] is None
        else:
            _close(row["p_value"], r["p"], f"{link} {g} p")
        assert row["n_obs"] == ref["n"]
    wald = rows[("bt", "strengths", "pooled")]
    _close(wald["statistic"], ref["wald"]["chi2"], "strength chi2")
    _close(wald["p_value"], ref["wald"]["p"], "strength p")
    assert wald["df"] == ref["wald"]["df"]


DOCKET_MEASURES = {
    "rank": {"kind": "field", "field": "rank_{idx}"},
    "risk": {"kind": "field", "field": "risk_{idx}"},
    "rank_valid": {"kind": "slot_aggregate", "field": "rank_{idx}", "function": "is_ranking"},
}
DOCKET_TERMS = [GROUP, {"dummies": "fact", "reference": "f0"}, {"dummies": "pos", "reference": 1}]


@pytest.fixture(scope="module")
def docket():
    spec = {
        "inputs": {"designs": ["docket"]},
        "frame": {"unit": "slot"},
        "measures": DOCKET_MEASURES,
        "estimands": [
            {
                "id": est,
                "estimator": est,
                "outcome": "rank",
                "terms": DOCKET_TERMS,
                "subset": "kind == 'docket' and rank_valid == 1",
                "vcov": {"type": "cluster", "by": ["unit"]},
                "conventions": {"ssc": "none"},
            }
            for est in ("plackett_luce", "clogit_rank1")
        ]
        + [
            {
                "id": "ols",
                "estimator": "fe_ols",
                "outcome": "risk",
                "terms": [GROUP, {"dummies": "fact", "reference": "f0"}, {"dummies": "pos", "reference": 1}, GENDER,
                          {"dummies": "system", "reference": "sys_a"}],
                "subset": "kind == 'docket'",
                "vcov": {"type": "cluster", "by": ["unit", "name_id"]},
                "joint_tests": [{"id": "group", "parameters": ["group[*]"]}],
            }
        ],
    }
    return _run(docket_records(), spec)


@pytest.mark.parametrize("estimator", ["plackett_luce", "clogit_rank1"])
def test_ranked_logits(docket, estimator):
    rows, built = docket
    ref = REF["docket"][estimator]
    assert set(ref) == {r[1] for r in rows if r[0] == estimator}
    for term, r in ref.items():
        row = rows[(estimator, term, "pooled")]
        assert row["status"] == "ok"
        _close(row["estimate"], r["est"], f"{estimator} {term} est")
        _close(row["std_error"], r["se"], f"{estimator} {term} se")
        _close(row["p_value"], r["p"], f"{estimator} {term} p")
        assert row["n_obs"] == REF["docket"]["n_dockets"]
    # the reference's default BFGS stop is off by more than the tolerance:
    # the engine computes the maximum, not an optimizer's stopping point
    assert REF["docket"]["plackett_luce_bfgs_default_max_rel_diff"] > REL


def test_two_way_cluster_ols_and_joint_test_on_a_slot_frame(docket):
    rows, _ = docket
    ref = REF["docket"]["ols_risk"]
    for term, r in ref["terms"].items():
        row = rows[("ols", term, "pooled")]
        _close(row["estimate"], r["est"], f"{term} est")
        _close(row["std_error"], r["se"], f"{term} se")
        _close(row["p_value"], r["p"], f"{term} p")
        assert row["n_obs"] == ref["n"]
    wald = rows[("ols", "group", "pooled")]
    _close(wald["statistic"], ref["wald"]["chi2"], "group chi2")
    _close(wald["p_value"], ref["wald"]["p"], "group p")
    assert wald["df"] == ref["wald"]["df"] == len(DOCKET_GROUPS) - 1


def _second_project(records):
    out = []
    for r in records:
        r = dict(r)
        r["generation_id"] = "b_" + r["generation_id"]
        r["task_id"] = "b_" + r["task_id"]
        r["project_id"] = "proj_b"
        out.append(r)
    return out


def test_lookup_tables_on_a_cross_project_frame():
    first = [dict(r, project_id="proj_a") for r in docket_records()]
    second = _second_project(docket_records(seed=SECOND_PROJECT_SEED))
    spec = {
        "inputs": {"designs": ["docket"], "projects": [{"project_id": "proj_b", "designs": ["docket"]}]},
        "frame": {"unit": "slot"},
        "lookups": [
            {"id": "congruence", "rows": congruence_lookup(), "keys": {"system": "model", "fact": "fact", "group": "group"},
             "columns": {"cong": "cong", "assoc": "assoc"}, "fill": {"cong": 0, "assoc": 0}},
            {"id": "pooled", "rows": congruence_pooled(), "keys": {"fact": "fact", "group": "group"},
             "columns": {"cong_pool": "cong_pool"}, "fill": {"cong_pool": 0}},
        ],
        "measures": {
            "risk": {"kind": "field", "field": "risk_{idx}"},
            "ng": {"kind": "expression", "expr": "1 * (group != 'ref')"},
        },
        "estimands": [
            {
                "id": x,
                "estimator": "fe_ols",
                "outcome": "risk",
                "terms": ["ng", x, {"dummies": "system", "reference": "sys_a"},
                          {"dummies": "fact", "reference": "f0", "by": "system"},
                          {"dummies": "pos", "reference": 1}, GENDER],
                "subset": "kind == 'docket'",
                "vcov": {"type": "cluster", "by": ["unit"]},
                "scopes": [{"by": ["project_id"]}],
                "contrasts": [{"id": x, "weights": {x: 1}, "tost": {"margin": 1}}],
            }
            for x in ("cong", "cong_pool")
        ],
    }
    rows, built = _run(first + second, spec)
    assert built.counts["projects"] == 2
    for project, refs in (("proj_a", REF["lookup"]["project_a"]), ("proj_b", REF["lookup"]["project_b"])):
        for x, r in refs.items():
            row = rows[(x, x, f"project_id={project}")]
            _close(row["estimate"], r["est"], f"{project} {x} est")
            _close(row["std_error"], r["se"], f"{project} {x} se")
            _close(row["p_value"], r["p"], f"{project} {x} p")
            _close(row["tost"][0]["p_tost"], r["p_tost"], f"{project} {x} p_tost")
            assert row["n_obs"] == r["n"]


def test_spearman_per_cell():
    spec = {
        "inputs": {"designs": ["role_swap"]},
        "measures": MEASURES,
        "estimands": [
            {"id": "rho", "estimator": "spearman", "outcome": "share_x", "x": "level",
             "scopes": [{"by": ["system", "x_role", "scenario"]}]}
        ],
    }
    rows, _ = _run(role_swap_records(), spec)
    assert len(REF["spearman"]) == len(rows)
    for key, ref in REF["spearman"].items():
        system, role, scenario = key.split("|")
        row = rows[("rho", "(rho)", f"system={system}|x_role={role}|scenario={scenario}")]
        if ref is None:
            assert row["status"] == "not_estimable" and row["estimate"] is None
        else:
            _close(row["estimate"], ref, f"rho {key}")
