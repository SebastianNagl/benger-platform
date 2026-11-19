"""The engine against two independent implementations, on the synthetic design.

* statsmodels (installed in the workers image), live: the ``statsmodels``
  convention must reproduce ``sm.OLS(...).fit(cov_type=...)`` on the same
  within-transformed data, one- and two-way clustering, HC1, iid, explicit
  fixed-effect dummies, and ``multipletests``.
* pyfixest, recorded in ``reference_values.json`` by
  ``make_reference_values.py``: the ``fixest`` convention and the
  ``statsmodels`` convention with pyfixest's matching options, with t
  inference on G-1 degrees of freedom.

Everything at 1e-9 relative.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from analysis.frame import build_frame
from analysis.multiplicity import adjust
from analysis.observations import observations_from_records
from analysis.runner import run_spec
from analysis.spec import normalize_spec
from analysis_synthetic import MEASURES, role_swap_records

HERE = os.path.dirname(os.path.abspath(__file__))
REL = 1e-9


@pytest.fixture(scope="module")
def frame():
    spec = normalize_spec(
        {
            "spec_version": 1,
            "name": "x",
            "inputs": {"designs": ["role_swap"]},
            "measures": MEASURES,
            "estimands": [{"id": "m", "estimator": "mean_rate", "outcome": "share_x"}],
        }
    )
    return build_frame(observations_from_records(role_swap_records()), spec).frame


def _engine(frame, estimand, conventions=None):
    spec = normalize_spec(
        {
            "spec_version": 1,
            "name": "x",
            "inputs": {"designs": ["role_swap"]},
            "measures": MEASURES,
            "conventions": conventions or {},
            "estimands": [dict(estimand, id="e", contrasts="terms")],
        }
    )
    return {r["contrast_id"]: r for r in run_spec(frame, spec).estimates}


def _within(frame, y, xs, fe):
    x = frame[[y] + xs + fe + ["name_id"]].dropna(subset=[y] + xs).copy()
    g = x.groupby(fe)
    for c in [y] + xs:
        x[c] = x[c] - g[c].transform("mean")
    return x


def _close(a, b, rel=REL):
    assert a == pytest.approx(b, rel=rel), (a, b)


@pytest.mark.parametrize("by", [["unit"], ["unit", "name_id"]])
def test_cluster_matches_statsmodels(frame, by):
    x = _within(frame, "share_x", ["x_p", "first_x"], ["unit", "system"])
    groups = (
        pd.factorize(x[by[0]])[0]
        if len(by) == 1
        else np.column_stack([pd.factorize(x[c])[0] for c in by])
    )
    ref = sm.OLS(x["share_x"], x[["x_p", "first_x"]]).fit(cov_type="cluster", cov_kwds={"groups": groups})
    mine = _engine(
        frame,
        {"estimator": "fe_ols", "outcome": "share_x", "terms": ["x_p", "first_x"],
         "fixed_effects": [["unit", "system"]], "vcov": {"type": "cluster", "by": by}},
    )
    for name in ("x_p", "first_x"):
        _close(mine[name]["estimate"], ref.params[name])
        _close(mine[name]["std_error"], ref.bse[name])
        _close(mine[name]["p_value"], ref.pvalues[name])


@pytest.mark.parametrize("vcov, cov_type", [({"type": "hc1"}, "HC1"), ({"type": "iid"}, "nonrobust")])
def test_robust_and_iid_match_statsmodels(frame, vcov, cov_type):
    x = frame.dropna(subset=["share_x"])
    X = sm.add_constant(x[["level", "x_p", "first_x"]])
    ref = sm.OLS(x["share_x"], X).fit(cov_type=cov_type)
    mine = _engine(frame, {"estimator": "fe_ols", "outcome": "share_x", "terms": ["level", "x_p", "first_x"], "vcov": vcov})
    for name in ("level", "x_p", "first_x"):
        _close(mine[name]["estimate"], ref.params[name])
        _close(mine[name]["std_error"], ref.bse[name])


def test_fixed_effect_dummies_match_statsmodels(frame):
    x = frame.dropna(subset=["share_x"]).reset_index(drop=True)
    dummies = pd.get_dummies(x[["system", "scenario"]], drop_first=True, dtype=float)
    X = sm.add_constant(pd.concat([x[["x_p", "first_x"]], dummies], axis=1))
    ref = sm.OLS(x["share_x"], X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(x["unit"])[0]})
    mine = _engine(
        frame,
        {"estimator": "fe_ols", "outcome": "share_x", "terms": ["x_p", "first_x"],
         "fixed_effects": [["system"], ["scenario"]], "method": "dummies",
         "vcov": {"type": "cluster", "by": ["unit"]}},
    )
    for name in ("x_p", "first_x"):
        _close(mine[name]["estimate"], ref.params[name])
        _close(mine[name]["std_error"], ref.bse[name])
    assert mine["x_p"]["k_params"] == X.shape[1]


def test_alternating_projections_match_dummies(frame):
    est = {"estimator": "fe_ols", "outcome": "share_x", "terms": ["x_p", "first_x"],
           "fixed_effects": [["system"], ["scenario"]], "vcov": {"type": "iid"}}
    within = _engine(frame, est)
    dummies = _engine(frame, dict(est, method="dummies"))
    for name in ("x_p", "first_x"):
        _close(within[name]["estimate"], dummies[name]["estimate"])


def test_adjustments_match_multipletests():
    rng = np.random.default_rng(3)
    p = list(rng.uniform(0, 0.2, size=17)) + [0.0, 1.0, 0.05, 0.05]
    for method, sm_name in (("holm", "holm"), ("bonferroni", "bonferroni"), ("bh", "fdr_bh")):
        assert adjust(p, method) == list(multipletests(p, method=sm_name)[1])


def test_counted_missing_p_matches_multipletests_with_nan():
    p = [0.01, float("nan"), 0.04, 0.02, float("nan")]
    ref = multipletests(p, method="holm")[1]
    mine = adjust(p, "holm", "count")
    for a, b in zip(mine, ref):
        assert (a is None and np.isnan(b)) or a == b


REFERENCE = json.load(open(os.path.join(HERE, "reference_values.json"), encoding="utf-8"))

PYFIXEST = {
    "within_crv_unit_matched": ({"terms": ["x_p", "first_x"], "fixed_effects": [["unit", "system"]], "vcov": {"type": "cluster", "by": ["unit"]}}, "statsmodels"),
    "within_crv_two_way_matched": ({"terms": ["x_p", "first_x"], "fixed_effects": [["unit", "system"]], "vcov": {"type": "cluster", "by": ["unit", "name_id"]}}, "statsmodels"),
    "within_crv_unit_fixest": ({"terms": ["x_p", "first_x"], "fixed_effects": [["unit", "system"]], "vcov": {"type": "cluster", "by": ["unit"]}}, "fixest"),
    "within_crv_two_way_fixest": ({"terms": ["x_p", "first_x"], "fixed_effects": [["unit", "system"]], "vcov": {"type": "cluster", "by": ["unit", "name_id"]}}, "fixest"),
    "within_iid_fixest": ({"terms": ["x_p", "first_x"], "fixed_effects": [["unit", "system"]], "vcov": {"type": "iid"}}, "fixest"),
    "within_hetero_fixest": ({"terms": ["x_p", "first_x"], "fixed_effects": [["unit", "system"]], "vcov": {"type": "hc1"}}, "fixest"),
    "two_sets_crv_unit_fixest": ({"terms": ["level", "x_p", "first_x"], "fixed_effects": [["system"], ["name_id"]], "vcov": {"type": "cluster", "by": ["unit"]}}, "fixest"),
}


@pytest.mark.parametrize("case_id", sorted(PYFIXEST))
def test_matches_recorded_pyfixest(frame, case_id):
    estimand, ssc = PYFIXEST[case_id]
    ref = REFERENCE["cases"][case_id]
    mine = _engine(
        frame,
        dict(estimand, estimator="fe_ols", outcome="share_x"),
        {"ssc": ssc, "inference": "t"},
    )
    for name, values in ref["coefficients"].items():
        row = mine[name]
        assert row["n_obs"] == ref["n"]
        _close(row["estimate"], values["estimate"])
        _close(row["std_error"], values["std_error"])
        # interval bounds near zero: relative to the larger of bound and SE
        scale = max(abs(values["ci_lower_t"]), abs(values["ci_upper_t"]), values["std_error"])
        assert abs(row["ci_lower"] - values["ci_lower_t"]) <= REL * scale
        assert abs(row["ci_upper"] - values["ci_upper_t"]) <= REL * scale
        if values["p_value_t"] > 1e-300:
            _close(row["p_value"], values["p_value_t"], rel=1e-7)
