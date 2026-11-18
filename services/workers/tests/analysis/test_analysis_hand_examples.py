"""Hand-computed examples for every estimator, variance and adjustment.

The numbers in the comments are derived on paper. The core example has two
units (u1, u2), two systems (s1, s2) and two conditions (c0, c1), one answer
per cell, with these differences c1 - c0 per unit x system cell:

    (u1, s1): 14 - 10 = 4      (u1, s2): 26 - 20 = 6
    (u2, s1): 31 - 30 = 1      (u2, s2): 49 - 40 = 9

With unit x system fixed effects the within-transformed condition dummy is
+-0.5 and the outcome +-diff/2, so the estimate is the mean difference, 5,
and the residuals are +-(diff - 5)/2 = -+0.5, +-0.5, -+2, +-2. Scores
x*e per cell (both rows together): -0.5, 0.5, -2, 2; X'X = 8 * 0.25 = 2.
"""

from __future__ import annotations

import math

import pytest

from analysis.frame import build_frame
from analysis.inference import mde, tost
from analysis.multiplicity import adjust
from analysis.observations import observation_from_record
from analysis.runner import run_spec
from analysis.spec import normalize_spec

CELLS = {("u1", "s1"): (10, 14), ("u1", "s2"): (20, 26), ("u2", "s1"): (30, 31), ("u2", "s2"): (40, 49)}


def _records():
    out = []
    for (unit, system), (y0, y1) in CELLS.items():
        for cond, y in (("c0", y0), ("c1", y1)):
            out.append(
                {
                    "generation_id": f"{unit}-{system}-{cond}",
                    "task_id": f"{unit}-{cond}",
                    "model_id": system,
                    "variant": {"design": "d", "unit": unit, "factors": {"cond": cond}},
                    "fields": {"y": y},
                }
            )
    return [observation_from_record(r) for r in out]


def _run(estimand, conventions=None, families=None):
    spec = {
        "spec_version": 1,
        "name": "hand",
        "inputs": {"designs": ["d"]},
        "measures": {"y": {"kind": "field", "field": "y"}, "d1": {"kind": "expression", "expr": "1 * (cond == 'c1')"}},
        "estimands": [estimand],
    }
    if conventions:
        spec["conventions"] = conventions
    if families:
        spec["families"] = families
    spec = normalize_spec(spec)
    frame = build_frame(_records(), spec).frame
    return run_spec(frame, spec)


def _fe(vcov, **extra):
    est = {
        "id": "effect",
        "estimator": "fe_ols",
        "outcome": "y",
        "terms": ["d1"],
        "fixed_effects": [["unit", "system"]],
        "vcov": vcov,
        "contrasts": [{"id": "c1-c0", "weights": {"d1": 1}}],
    }
    est.update(extra)
    return est


def test_within_estimate_is_the_mean_difference():
    row = _run(_fe({"type": "iid"})).estimates[0]
    assert row["estimate"] == pytest.approx(5.0, abs=1e-12)
    assert row["n_obs"] == 8 and row["k_params"] == 1


def test_iid_variance_uses_rss_over_n_minus_k():
    # RSS = 2 * (0.25 + 0.25 + 4 + 4) = 17; s2 = 17 / 7; V = s2 / 2
    row = _run(_fe({"type": "iid"})).estimates[0]
    assert row["std_error"] == pytest.approx(math.sqrt(17 / 14), rel=1e-12)


def test_hc1_variance():
    # meat = sum (0.5 e)^2 = 0.25 * 17; V0 = 4.25 / 4; HC1 x 8/7
    row = _run(_fe({"type": "hc1"})).estimates[0]
    assert row["std_error"] == pytest.approx(math.sqrt(4.25 / 4 * 8 / 7), rel=1e-12)


def test_one_way_cluster_statsmodels_factor():
    # by system: s1 scores -0.5 - 2 = -2.5, s2 2.5; meat 12.5; V0 = 12.5 / 4
    # factor G/(G-1) * (N-1)/(N-K) = 2 * 7/7 = 2 -> V = 6.25, SE 2.5
    row = _run(_fe({"type": "cluster", "by": ["system"]})).estimates[0]
    assert row["std_error"] == pytest.approx(2.5, rel=1e-12)
    assert row["n_clusters"] == [2]


def test_one_way_cluster_without_correction():
    row = _run(_fe({"type": "cluster", "by": ["system"]}), {"ssc": "none"}).estimates[0]
    assert row["std_error"] == pytest.approx(math.sqrt(12.5 / 4), rel=1e-12)


def test_one_way_cluster_fixest_factor_counts_a_nested_fixed_effect_once():
    # unit x system cells are nested in system: K = 1 + 4 - 4 + 1 = 2,
    # factor (N-1)/(N-K) * G/(G-1) = 7/6 * 2 -> V = 12.5/4 * 7/3
    row = _run(_fe({"type": "cluster", "by": ["system"]}), {"ssc": "fixest"}).estimates[0]
    assert row["std_error"] == pytest.approx(math.sqrt(12.5 / 4 * 7 / 3), rel=1e-12)


def test_two_way_cluster_is_v1_plus_v2_minus_v12():
    # unit scores: u1 -0.5 + 0.5 = 0, u2 -2 + 2 = 0 -> V_unit = 0
    # system: V = 6.25 (above); intersection (4 cells): meat 8.5, V0 = 8.5/4,
    # factor 4/3 -> 17/6; V = 0 + 6.25 - 17/6 = 41/12
    row = _run(_fe({"type": "cluster", "by": ["unit", "system"]})).estimates[0]
    assert row["std_error"] == pytest.approx(math.sqrt(41 / 12), rel=1e-12)
    assert row["n_clusters"] == [2, 2]


def test_t_inference_uses_g_minus_one_degrees_of_freedom():
    from scipy import stats

    row = _run(_fe({"type": "cluster", "by": ["system"]}), {"inference": "t"}).estimates[0]
    assert row["df"] == 1
    crit = stats.t.ppf(0.975, 1)
    assert row["ci_lower"] == pytest.approx(5 - crit * 2.5, rel=1e-12)
    assert row["p_value"] == pytest.approx(2 * stats.t.sf(2.0, 1), rel=1e-12)


def test_fixed_critical_value_and_normal_p():
    from scipy import stats

    row = _run(_fe({"type": "cluster", "by": ["system"]}), {"ci_critical": 1.96}).estimates[0]
    assert row["ci_lower"] == row["estimate"] - 1.96 * row["std_error"]
    assert row["ci_upper"] == row["estimate"] + 1.96 * row["std_error"]
    assert row["ci_upper"] == pytest.approx(9.9, rel=1e-12)
    assert row["p_value"] == pytest.approx(2 * stats.norm.sf(2.0), rel=1e-12)
    assert row["statistic"] == pytest.approx(2.0, rel=1e-12)


def test_dummies_method_equals_within():
    within = _run(_fe({"type": "iid"})).estimates[0]
    dummies = _run(_fe({"type": "iid"}, method="dummies")).estimates[0]
    assert dummies["estimate"] == pytest.approx(within["estimate"], rel=1e-12)
    # K counts intercept and the three fixed-effect dummies: RSS / (8 - 5)
    assert dummies["k_params"] == 5
    assert dummies["std_error"] == pytest.approx(math.sqrt(17 / 3 / 2), rel=1e-12)


def test_mean_rate_has_the_iid_standard_error_of_the_mean():
    # y = 10, 14, 20, 26, 30, 31, 40, 49: mean 27.5
    values = [10, 14, 20, 26, 30, 31, 40, 49]
    mean = sum(values) / 8
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / 7)
    row = _run({"id": "m", "estimator": "mean_rate", "outcome": "y"}).estimates[0]
    assert row["contrast_id"] == "(mean)"
    assert row["estimate"] == pytest.approx(mean, rel=1e-12)
    assert row["std_error"] == pytest.approx(sd / math.sqrt(8), rel=1e-12)


def test_paired_within_averages_the_differences():
    est = {
        "id": "pairs",
        "estimator": "paired_within",
        "outcome": "y",
        "pair_by": ["unit", "system"],
        "treatment": {"factor": "cond", "level": "c1", "reference": "c0"},
        "vcov": {"type": "iid"},
    }
    row = _run(est).estimates[0]
    diffs = [4, 6, 1, 9]
    assert row["estimate"] == pytest.approx(5.0, rel=1e-12)
    sd = math.sqrt(sum((d - 5) ** 2 for d in diffs) / 3)
    assert row["std_error"] == pytest.approx(sd / 2, rel=1e-12)
    assert row["n_obs"] == 4


def test_paired_within_reports_the_pair_count_below_min_n():
    est = {
        "id": "pairs",
        "estimator": "paired_within",
        "outcome": "y",
        "pair_by": ["unit", "system"],
        "treatment": {"factor": "cond", "level": "c1", "reference": "c0"},
        "min_n": 10,
    }
    row = _run(est).estimates[0]
    assert row["status"] == "error" and row["n_obs"] == 4
    assert "fewer than min_n" in row["message"]


def test_ambiguous_number_texts_in_filters_and_subsets_are_reported():
    amounts = {"u1-s1-c1": "1,000"}
    records = []
    for obs in _records():
        rec = {"generation_id": obs.generation_id, "task_id": obs.task_id, "model_id": obs.model_id,
               "variant": {"design": "d", "unit": obs.unit, "factors": dict(obs.factors)},
               "fields": {**obs.fields, "amt": amounts.get(obs.generation_id, "2,5")}}
        records.append(observation_from_record(rec))
    condition = "number(amt) >= 0"
    spec = normalize_spec({
        "spec_version": 1, "name": "hand", "inputs": {"designs": ["d"]},
        "measures": {"y": {"kind": "field", "field": "y"}, "amt": {"kind": "field", "field": "amt", "type": "text"}},
        "filter": f"{condition} or cond == 'c0'",
        "estimands": [
            {"id": "rate", "estimator": "mean_rate", "outcome": "y", "subset": condition},
            {"id": "pairs", "estimator": "paired_within", "outcome": "y", "pair_by": ["unit", "system"],
             "treatment": {"factor": "cond", "level": "c1", "reference": "c0", "subset": condition},
             "vcov": {"type": "iid"}},
        ],
    })
    result = run_spec(build_frame(records, spec).frame, spec)
    message = "1 number text(s) with an ambiguous separator set to missing"
    assert f"/filter: {message}" in result.warnings
    assert f"/estimands/0/subset: {message}" in result.warnings
    assert any(w.startswith("pairs [") and w.endswith(f"/treatment/subset: {message}") for w in result.warnings)
    # "1,000" is missing, not 1.0 or 1000: its row is left out, so the pairs
    # are those of CELLS without (u1, s1): differences 6, 1 and 9
    assert result.rows_in_filter == 7
    pairs = next(e for e in result.estimates if e["estimand_id"] == "pairs")
    assert pairs["n_obs"] == 3 and pairs["estimate"] == pytest.approx(16 / 3, rel=1e-12)


def test_tost_decision_and_p_value():
    from scipy import stats

    out = tost(1.0, 1.0, (-3.0, 3.0), 0.90, "normal", None)
    z = stats.norm.ppf(0.95)
    assert out["ci_lower"] == pytest.approx(1 - z) and out["ci_upper"] == pytest.approx(1 + z)
    assert out["equivalent"] is True
    assert out["p_lower"] == pytest.approx(stats.norm.sf(4.0))
    assert out["p_upper"] == pytest.approx(stats.norm.cdf(-2.0))
    assert out["p_tost"] == pytest.approx(stats.norm.cdf(-2.0))
    wide = tost(1.0, 2.0, (-3.0, 3.0), 0.90, "normal", None)
    assert wide["equivalent"] is False and wide["p_tost"] > 0.05


def test_tost_asymmetric_bounds_and_zero_se():
    out = tost(0.5, 0.0, (-1.0, 2.0), 0.90, "normal", None)
    assert out["equivalent"] is True and out["p_tost"] == 0.0
    out = tost(2.5, 0.0, (-1.0, 2.0), 0.90, "normal", None)
    assert out["equivalent"] is False and out["p_tost"] == 1.0


def test_holm_bonferroni_and_bh_by_hand():
    p = [0.01, 0.04, 0.03]
    assert adjust(p, "holm") == pytest.approx([0.03, 0.06, 0.06])
    assert adjust(p, "bonferroni") == pytest.approx([0.03, 0.12, 0.09])
    assert adjust(p, "bh") == pytest.approx([0.03, 0.04, 0.04])


def test_missing_p_values_are_skipped_or_counted():
    p = [0.01, None, 0.03, float("nan")]
    skipped = adjust(p, "holm")
    assert skipped[0] == pytest.approx(0.02) and skipped[2] == pytest.approx(0.03)
    assert skipped[1] is None and skipped[3] is None
    counted = adjust(p, "holm", "count")
    assert counted[0] == pytest.approx(0.04) and counted[2] == pytest.approx(0.09)
    assert adjust(p, "bonferroni", "count")[2] == pytest.approx(0.12)
    with pytest.raises(ValueError):
        adjust(p, "bh", "count")


def test_mde_is_the_holm_worst_case_formula():
    # z(1 - 0.05/6) + z(0.8) for three tests, times se
    assert mde(1.0, 0.8, 0.05, 3) == pytest.approx(2.3939797998185104 + 0.8416212335729143, rel=1e-12)


def test_ratio_contrast_delta_method():
    est = _fe(
        {"type": "iid"},
        terms=["d1"],
        contrasts=[
            {
                "id": "ratio",
                "kind": "ratio",
                "numerator": {"weights": {"d1": 1}, "constant": 5},
                "denominator": {"weights": {"d1": 2}},
                "scale": -1,
            }
        ],
    )
    row = _run(est).estimates[0]
    # -(5 + 5) / 10 = -1; gradient -(1/10 - 2 * 10 / 100) = 0.1; se = 0.1 * sqrt(17/14)
    assert row["estimate"] == pytest.approx(-1.0, rel=1e-12)
    assert row["std_error"] == pytest.approx(0.1 * math.sqrt(17 / 14), rel=1e-12)
    gated = _fe(
        {"type": "iid"},
        contrasts=[
            {
                "id": "gated",
                "kind": "ratio",
                "numerator": {"weights": {"d1": 1}},
                "denominator": {"weights": {"d1": 1}},
                "min_abs_denominator": 6,
            }
        ],
    )
    assert _run(gated).estimates[0]["status"] == "not_estimable"


def test_scopes_and_families():
    est = _fe({"type": "iid"}, scopes=["pooled", {"by": ["system"]}])
    fam = [
        {"id": "pooled", "method": "bonferroni", "members": [{"estimand": "effect", "scope": "pooled"}]},
        {"id": "per_system", "method": "bonferroni", "members": [{"estimand": "effect", "scope": "by:system"}]},
    ]
    rows = _run(est, families=fam).estimates
    assert [r["scope"] for r in rows] == ["pooled", "system=s1", "system=s2"]
    pooled, s1, s2 = rows
    assert pooled["family"] == "pooled" and pooled["p_adjusted"] == pooled["p_value"]
    # s1: differences 4 and 1 -> 2.5; s2: 6 and 9 -> 7.5
    assert s1["estimate"] == pytest.approx(2.5) and s2["estimate"] == pytest.approx(7.5)
    assert s1["scope_values"] == {"system": "s1"}
    assert s1["p_adjusted"] == pytest.approx(min(1.0, 2 * s1["p_value"]))
    assert s1["adjustments"][0]["size"] == 2


def test_cluster_variance_needs_two_clusters():
    est = _fe({"type": "cluster", "by": ["system"]}, scopes=[{"by": ["system"]}])
    rows = _run(est).estimates
    assert all(r["status"] == "error" and "at least 2 clusters" in r["message"] for r in rows)


def test_a_failed_fit_shows_as_an_error_row():
    est = _fe({"type": "iid"}, terms=["nope"], contrasts="terms")
    rows = _run(est).estimates
    assert len(rows) == 1 and rows[0]["status"] == "error"
    assert rows[0]["contrast_id"] is None and "unknown column 'nope'" in rows[0]["message"]
