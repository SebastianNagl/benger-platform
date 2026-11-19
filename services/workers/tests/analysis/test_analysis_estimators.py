"""The estimator extensions: hand-computed examples, identities and live
cross-checks against statsmodels (installed in the workers image).

* logit: a saturated two-group logit has the log odds ratio as its slope and
  the difference of the two shares as its average marginal effect, exactly;
  iid, HC1 and one- and two-way cluster variances equal statsmodels'
  ``Logit(...).fit(cov_type=...)``; separation withholds p-values;
  uninformative fixed-effect groups are left out and counted.
* Bradley-Terry equals a logit on the +1/-1 difference coding.
* A rank-1 conditional logit (and Plackett-Luce) over pairs equals a logit
  without intercept on the regressors' difference.
* A joint test of one contrast is its squared z statistic; redundant
  restrictions do not add degrees of freedom.
* Spearman's rho of a monotone relation is 1; a constant input is not
  estimable.
* MixedLM refuses statsmodels' lbfgs fit when it stops on the boundary of the
  variance component and takes the next optimizer, equal to statsmodels'
  own fit with that optimizer.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

from analysis.frame import build_frame
from analysis.observations import observations_from_records
from analysis.runner import run_spec
from analysis.spec import normalize_spec
from estimator_synthetic import pairs_records, single_records

REL = 1e-9


def _close(a, b, rel=REL):
    assert a is not None and math.isclose(a, b, rel_tol=rel, abs_tol=0.0 if b else 1e-300), (a, b)


def _records(rows, design="d"):
    out = []
    for i, row in enumerate(rows):
        row = dict(row)
        fields = {k: row.pop(k) for k in list(row) if k.startswith("y") or k.startswith("r_")}
        slots = row.pop("slots", [])
        out.append({
            "generation_id": f"g{i:05d}", "task_id": f"t{i:05d}", "model_id": row.pop("system", "m"),
            "variant": {"design": design, "unit": row.pop("unit", f"u{i}"), "factors": row, "slots": slots},
            "fields": fields,
        })
    return out


def _estimates(records, estimands, measures=None, frame=None, **spec_extra):
    spec = {"spec_version": 1, "name": "t", "inputs": {"designs": ["d"]}, "estimands": estimands,
            "measures": measures if measures is not None else {"y": {"kind": "field", "field": "y"}}, **spec_extra}
    if frame:
        spec["frame"] = {"unit": frame}
    normalized = normalize_spec(spec)
    built = build_frame(observations_from_records(records), normalized)
    result = run_spec(built.frame, normalized)
    return {(r["estimand_id"], r["contrast_id"], r["scope"]): r for r in result.estimates}, result, built


def _two_groups():
    # group a: 3 of 10 succeed; group b: 7 of 10
    rows = [{"g": "a", "y": int(i < 3)} for i in range(10)] + [{"g": "b", "y": int(i < 7)} for i in range(10)]
    return _records(rows)


def test_saturated_logit_slope_and_marginal_effect():
    rows, _, _ = _estimates(_two_groups(), [{
        "id": "l", "estimator": "logit", "outcome": "y", "terms": [{"dummies": "g", "reference": "a"}],
        "contrasts": [{"id": "b", "weights": {"g[b]": 1}},
                      {"id": "ame", "kind": "ame", "column": "g", "level": "b", "reference": "a", "scale": 100}],
    }])
    slope = rows[("l", "b", "pooled")]
    _close(slope["estimate"], math.log((0.7 / 0.3) / (0.3 / 0.7)))
    # iid variance of a log odds ratio: sum of 1/count over the four cells
    _close(slope["std_error"], math.sqrt(1 / 3 + 1 / 7 + 1 / 7 + 1 / 3))
    ame = rows[("l", "ame", "pooled")]
    _close(ame["estimate"], 100 * (0.7 - 0.3))
    # delta method on the saturated model: the binomial SE of the difference
    _close(ame["std_error"], 100 * math.sqrt(0.7 * 0.3 / 10 + 0.3 * 0.7 / 10))


def _statsmodels_frame():
    records = single_records(names_per_group=4, reps=3)
    spec = normalize_spec({"spec_version": 1, "name": "t", "inputs": {"designs": ["single"]},
                           "measures": {"y": {"kind": "field", "field": "probation"}},
                           "estimands": [{"id": "m", "estimator": "mean_rate", "outcome": "y"}]})
    return records, build_frame(observations_from_records(records), spec).frame


@pytest.mark.parametrize(
    "vcov",
    [{"type": "iid"}, {"type": "hc1"}, {"type": "cluster", "by": ["name_id"]}, {"type": "cluster", "by": ["name_id", "system"]}],
)
def test_logit_variances_match_statsmodels(vcov):
    records, frame = _statsmodels_frame()
    rows, result, _ = _estimates(records, [{
        "id": "l", "estimator": "logit", "outcome": "y", "vcov": vcov,
        "terms": [{"dummies": "group", "reference": "ref"}, {"dummies": "gender", "reference": "f"}],
    }], measures={"y": {"kind": "field", "field": "probation"}}, inputs={"designs": ["single"]})
    model = smf.logit("y ~ C(group, Treatment('ref')) + C(gender)", frame)
    if vcov["type"] == "iid":
        ref = model.fit(disp=0)
    elif vcov["type"] == "hc1":
        ref = model.fit(disp=0, cov_type="HC1")
    else:
        groups = np.column_stack([pd.factorize(frame[c])[0] for c in vcov["by"]])
        ref = model.fit(disp=0, cov_type="cluster", cov_kwds={"groups": groups if groups.shape[1] > 1 else groups[:, 0]})
    for name, value in ref.params.items():
        if name == "Intercept":
            continue
        level = name.split("[T.")[1][:-1]
        mine = rows[("l", f"{'gender' if 'gender' in name else 'group'}[{level}]", "pooled")]
        _close(mine["estimate"], value)
        _close(mine["std_error"], ref.bse[name])
        _close(mine["p_value"], ref.pvalues[name])
    assert result.fits[0]["converged"] is True


def test_logit_separation_withholds_p_values():
    rows = [{"g": "a", "y": int(i < 4)} for i in range(10)] + [{"g": "b", "y": 1} for _ in range(10)]
    est, result, _ = _estimates(_records(rows), [{
        "id": "l", "estimator": "logit", "outcome": "y", "terms": [{"dummies": "g", "reference": "a"}],
        "joint_tests": [{"id": "all", "parameters": ["g[*]"]}],
    }])
    row = est[("l", "g[b]", "pooled")]
    assert row["status"] == "separation" and row["p_value"] is None and row["estimate"] > 8
    assert "separation" in row["message"]
    assert est[("l", "all", "pooled")]["status"] == "separation"
    assert result.fits[0]["separated"] == ["g[b]"] and result.fits[0]["converged"] is False


def test_logit_leaves_out_uninformative_fixed_effect_groups():
    rows = []
    for cell in range(6):
        for i in range(12):
            constant = cell == 5
            rows.append({"cell": f"c{cell}", "x": float(i % 2), "y": 1 if constant else int((i * 7 + cell) % 5 < 2 + (i % 2))})
    records = _records(rows)
    est, result, _ = _estimates(records, [
        {"id": "l", "estimator": "logit", "outcome": "y", "terms": ["x"], "fixed_effects": [["cell"]]},
        {"id": "all", "estimator": "logit", "outcome": "y", "terms": ["x"], "fixed_effects": [["cell"]],
         "conventions": {"informative_only": False}},
    ])
    fit = result.fits[0]
    assert fit["rows_uninformative"] == 12 and fit["n"] == 60
    # statsmodels on the informative cells with full dummies gives the same slope
    frame = pd.DataFrame(rows)
    informative = frame[frame.cell != "c5"]
    ref = smf.logit("y ~ 0 + C(cell) + x", informative).fit(disp=0)
    _close(est[("l", "x", "pooled")]["estimate"], ref.params["x"])
    _close(est[("l", "x", "pooled")]["std_error"], ref.bse["x"])
    # without the filter the constant cell's effect runs away
    assert result.fits[1]["converged"] is False


def test_bradley_terry_is_a_logit_on_the_difference_coding():
    records = pairs_records(units=60)
    measures = {
        "choice": {"kind": "field", "field": "choice"},
        "first_wins": {"kind": "expression", "expr": "1 * (choice == 1)"},
        "g1": {"kind": "slot_factor", "factor": "group", "slot": 1},
        "g2": {"kind": "slot_factor", "factor": "group", "slot": 2},
    }
    levels = ["a", "b", "c", "d", "e", "f"]
    for lv in levels:
        measures[f"x_{lv}"] = {"kind": "expression", "expr": f"1 * (g1 == '{lv}') - 1 * (g2 == '{lv}')"}
    spec = dict(measures=measures, inputs={"designs": ["pairs"]})
    est, _, _ = _estimates(records, [
        {"id": "bt", "estimator": "bradley_terry", "outcome": "first_wins", "players": ["g1", "g2"], "reference": "ref",
         "vcov": {"type": "cluster", "by": ["unit"]}},
        {"id": "lg", "estimator": "logit", "outcome": "first_wins", "terms": [f"x_{lv}" for lv in levels],
         "vcov": {"type": "cluster", "by": ["unit"]}},
    ], **spec)
    for lv in levels:
        a, b = est[("bt", f"strength[{lv}]", "pooled")], est[("lg", f"x_{lv}", "pooled")]
        _close(a["estimate"], b["estimate"], 1e-12)
        _close(a["std_error"], b["std_error"], 1e-12)


def _choice_pairs(n=80, seed=4):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n):
        x = rng.normal(size=(2, 2))
        u = x @ np.array([0.8, -0.5]) + rng.gumbel(size=2)
        first = int(np.argmax(u))
        slots = [{"index": i, "factors": {"x1": float(x[i, 0]), "x2": float(x[i, 1])}} for i in range(2)]
        rows.append({"slots": slots, "unit": f"u{s % 20}", "r_0": 1 if first == 0 else 2, "r_1": 1 if first == 1 else 2,
                     "y": float(first == 0)})
    return _records(rows)


@pytest.mark.parametrize("estimator", ["plackett_luce", "clogit_rank1"])
def test_ranked_logit_on_pairs_is_a_logit_on_differences(estimator):
    records = _choice_pairs()
    measures = {"rank": {"kind": "field", "field": "r_{idx}"}}
    ranked, result, _ = _estimates(records, [{
        "id": "pl", "estimator": estimator, "outcome": "rank", "terms": ["x1", "x2"],
        "vcov": {"type": "cluster", "by": ["unit"]}, "conventions": {"ssc": "none"},
    }], measures=measures, frame="slot")
    frame_rows = []
    for r in records:
        s = r["variant"]["slots"]
        frame_rows.append({"y": r["fields"]["y"], "d1": s[0]["factors"]["x1"] - s[1]["factors"]["x1"],
                           "d2": s[0]["factors"]["x2"] - s[1]["factors"]["x2"], "unit": r["variant"]["unit"]})
    frame = pd.DataFrame(frame_rows)
    ref = sm.Logit(frame["y"], frame[["d1", "d2"]]).fit(disp=0)
    groups = pd.factorize(frame["unit"])[0]
    # sandwich without a small-sample factor: H^-1 (sum_g S_g S_g') H^-1
    X = frame[["d1", "d2"]].to_numpy()
    p = 1 / (1 + np.exp(-X @ ref.params.to_numpy()))
    scores = X * (frame["y"].to_numpy() - p)[:, None]
    S = np.vstack([scores[groups == g].sum(axis=0) for g in range(groups.max() + 1)])
    bread = np.linalg.inv(X.T @ (X * (p * (1 - p))[:, None]))
    V = bread @ S.T @ S @ bread
    for j, (name, d) in enumerate((("x1", "d1"), ("x2", "d2"))):
        row = ranked[("pl", name, "pooled")]
        _close(row["estimate"], ref.params[d])
        _close(row["std_error"], math.sqrt(V[j, j]))
    assert result.fits[0]["choice_sets"] == len(records)


def test_ranked_logit_drops_invalid_sets_and_constant_regressors():
    records = _choice_pairs(40)
    records[0]["fields"].update(r_0=1, r_1=1)  # a tie
    for r in records:
        for s in r["variant"]["slots"]:
            s["factors"]["const"] = 1.0
    _, result, _ = _estimates(records, [{
        "id": "pl", "estimator": "plackett_luce", "outcome": "rank", "terms": ["x1", "x2", "const"],
    }], measures={"rank": {"kind": "field", "field": "r_{idx}"}}, frame="slot")
    fit = result.fits[0]
    assert fit["choice_sets"] == 39 and fit["choice_sets_invalid"] == 1
    assert fit["dropped"] == ["const"]
    assert any("constant within every choice set" in w for w in result.warnings)


@pytest.mark.parametrize("estimator", ["plackett_luce", "clogit_rank1"])
def test_a_scope_without_a_valid_choice_set_is_an_error_row(estimator):
    good = _choice_pairs(40)
    tied = _choice_pairs(10, seed=5)
    for r in tied:
        r["model_id"] = "tied"
        r["generation_id"] = "t" + r["generation_id"]
        r["task_id"] = "t" + r["task_id"]
        r["fields"].update(r_0=1, r_1=1)
    measures = {"rank": {"kind": "field", "field": "r_{idx}"}}
    spec = {"id": "pl", "estimator": estimator, "outcome": "rank", "terms": ["x1", "x2"]}
    scoped, _, _ = _estimates(good + tied, [{**spec, "scopes": [{"by": ["system"]}]}], measures=measures, frame="slot")
    alone, _, _ = _estimates(good, [spec], measures=measures, frame="slot")
    [error] = [r for (_, _, scope), r in scoped.items() if scope == "system=tied"]
    assert error["status"] == "error" and "no valid choice set (10 invalid)" in error["message"]
    for name in ("x1", "x2"):
        _close(scoped[("pl", name, "system=m")]["estimate"], alone[("pl", name, "pooled")]["estimate"])
        _close(scoped[("pl", name, "system=m")]["std_error"], alone[("pl", name, "pooled")]["std_error"])


def test_joint_test_of_one_contrast_is_its_squared_z():
    rows = [{"g": ["a", "b", "c"][i % 3], "y": float((i * 37) % 11)} for i in range(60)]
    est, _, _ = _estimates(_records(rows), [{
        "id": "o", "estimator": "fe_ols", "outcome": "y", "terms": [{"dummies": "g", "reference": "a"}],
        "vcov": {"type": "hc1"},
        "contrasts": [{"id": "b", "weights": {"g[b]": 1}}, {"id": "c", "weights": {"g[c]": 1}},
                      {"id": "b_again", "weights": {"g[b]": 2}}],
        "joint_tests": [{"id": "one", "contrasts": ["b"]}, {"id": "redundant", "contrasts": ["b", "b_again"]},
                        {"id": "none", "parameters": ["zz*"]}],
    }])
    b = est[("o", "b", "pooled")]
    one = est[("o", "one", "pooled")]
    _close(one["statistic"], (b["estimate"] / b["std_error"]) ** 2)
    _close(one["p_value"], b["p_value"])
    redundant = est[("o", "redundant", "pooled")]
    assert redundant["df"] == 1 and "rank 1 of 2" in redundant["message"]
    assert est[("o", "none", "pooled")]["status"] == "not_estimable"


def test_a_joint_test_of_a_ratio_needs_its_null():
    rows = [{"g": ["a", "b", "c"][i % 3], "y": float((i * 37) % 11) + 3} for i in range(60)]
    ratio = {"kind": "ratio", "numerator": {"weights": {"g[b]": 1}}, "denominator": {"weights": {"g[c]": 1}}}
    est, _, _ = _estimates(_records(rows), [{
        "id": "o", "estimator": "fe_ols", "outcome": "y", "terms": [{"dummies": "g", "reference": "a"}],
        "vcov": {"type": "hc1"},
        "contrasts": [{"id": "rel", **ratio}, {"id": "rel1", **ratio, "null": 1.0}],
        "joint_tests": [{"id": "no_null", "contrasts": ["rel"]}, {"id": "with_null", "contrasts": ["rel1"]}],
    }])
    no_null = est[("o", "no_null", "pooled")]
    assert no_null["status"] == "not_estimable" and no_null["p_value"] is None
    assert "ratio contrast 'rel' has no null" in no_null["message"]
    # one restriction: the Wald statistic is the squared z of the ratio against its null
    single, joint = est[("o", "rel1", "pooled")], est[("o", "with_null", "pooled")]
    _close(joint["statistic"], ((single["estimate"] - 1.0) / single["std_error"]) ** 2)
    _close(joint["p_value"], single["p_value"])


def test_spearman_hand_examples():
    rows = [{"x": float(i), "y": float(i ** 3)} for i in range(10)] + [{"x": 1.0, "y": 5.0, "grp": "flat"} for _ in range(5)]
    for r in rows[:10]:
        r["grp"] = "monotone"
    est, _, _ = _estimates(
        _records(rows), [{"id": "s", "estimator": "spearman", "outcome": "y", "x": "x", "scopes": [{"by": ["grp"]}]}]
    )
    mono = est[("s", "(rho)", "grp=monotone")]
    assert mono["estimate"] == pytest.approx(1.0, rel=1e-12) and mono["df"] == 8
    flat = est[("s", "(rho)", "grp=flat")]
    assert flat["status"] == "not_estimable" and flat["estimate"] is None
    rng = np.random.default_rng(2)
    x, y = rng.normal(size=30), rng.normal(size=30)
    est, _, _ = _estimates(_records([{"x": float(a), "y": float(b)} for a, b in zip(x, y)]),
                           [{"id": "s", "estimator": "spearman", "outcome": "y", "x": "x"}])
    ref = stats.spearmanr(x, y)
    _close(est[("s", "(rho)", "pooled")]["estimate"], ref.statistic)
    _close(est[("s", "(rho)", "pooled")]["p_value"], ref.pvalue)


def test_marginal_effects_need_a_term_column():
    est, _, _ = _estimates(_two_groups(), [{
        "id": "l", "estimator": "logit", "outcome": "y", "terms": [{"dummies": "g", "reference": "a"}],
        "contrasts": [{"id": "bad", "kind": "ame", "column": "unit", "level": "x", "reference": "y"}],
    }])
    row = est[("l", "bad", "pooled")]
    assert row["status"] == "not_estimable" and "no term reads 'unit'" in row["message"]


def test_marginal_effects_need_both_levels_in_the_sample():
    # setting g to a level without rows changes no dummy column, so without
    # the check the effect would come out as exactly 0
    est, _, _ = _estimates(_two_groups(), [{
        "id": "l", "estimator": "logit", "outcome": "y",
        "terms": [{"dummies": "g", "levels": ["a", "b", "c"], "reference": "a"}],
        "contrasts": [{"id": "typo", "kind": "ame", "column": "g", "level": "bb", "reference": "a"},
                      {"id": "declared", "kind": "ame", "column": "g", "level": "c", "reference": "a"},
                      {"id": "no_ref", "kind": "ame", "column": "g", "level": "b", "reference": "c"},
                      {"id": "ok", "kind": "ame", "column": "g", "level": "b", "reference": "a"}],
        "joint_tests": [{"id": "both", "contrasts": ["ok", "declared"]}],
    }])
    for cid, level in (("typo", "bb"), ("declared", "c"), ("no_ref", "c")):
        row = est[("l", cid, "pooled")]
        assert row["status"] == "not_estimable" and row["estimate"] is None, row
        assert f"no level {level!r}" in row["message"]
    _close(est[("l", "ok", "pooled")]["estimate"], 0.7 - 0.3)
    assert est[("l", "both", "pooled")]["status"] == "not_estimable"


def test_bradley_terry_leaves_out_players_outside_the_declared_levels():
    records = pairs_records(units=60)
    measures = {
        "choice": {"kind": "field", "field": "choice"},
        "first_wins": {"kind": "expression", "expr": "1 * (choice == 1)"},
        "g1": {"kind": "slot_factor", "factor": "group", "slot": 1},
        "g2": {"kind": "slot_factor", "factor": "group", "slot": 2},
    }
    spec = dict(measures=measures, inputs={"designs": ["pairs"]})
    bt = {"estimator": "bradley_terry", "outcome": "first_wins", "players": ["g1", "g2"], "reference": "ref"}
    declared, result, _ = _estimates(records, [{"id": "bt", **bt, "levels": ["ref", "a", "b", "c", "d", "e"]}], **spec)
    without_f = [r for r in records if all(s["factors"]["group"] != "f" for s in r["variant"]["slots"])]
    assert 0 < len(without_f) < len(records)
    reference, _, _ = _estimates(without_f, [{"id": "bt", **bt}], **spec)
    for lv in ("a", "b", "c", "d", "e"):
        mine, ref = declared[("bt", f"strength[{lv}]", "pooled")], reference[("bt", f"strength[{lv}]", "pooled")]
        _close(mine["estimate"], ref["estimate"], 1e-12)
        _close(mine["std_error"], ref["std_error"], 1e-12)
    fit = result.fits[0]
    assert fit["n"] == len(without_f) and fit["rows_dropped_missing"] == len(records) - len(without_f)
    assert any("outside the declared levels" in w for w in result.warnings)


def test_mixedlm_skips_a_boundary_lbfgs_fit():
    # On these records statsmodels' lbfgs reports convergence at a variance
    # component of 0 with an infinite log-likelihood; powell finds the maximum.
    records = single_records(seed=20261131)
    spec = {"inputs": {"designs": ["single"]}, "measures": {"months": {"kind": "field", "field": "months"}}}
    terms = [{"dummies": "group", "reference": "ref"}, {"dummies": "gender", "reference": "f"}, {"dummies": "system", "reference": "sys_a"}]
    est, result, built = _estimates(records, [{"id": "mx", "estimator": "mixedlm", "outcome": "months", "terms": terms,
                                               "groups": ["name_id"]}], **spec)
    fit = result.fits[0]
    assert fit["optimizer"] == "powell"
    frame = built.frame
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.mixedlm("months ~ C(group, Treatment('ref')) + C(gender) + C(system)", frame, groups=frame["name_id"])
        broken = model.fit(reml=True, method="lbfgs")
        ref = model.fit(reml=True, method="powell")
    assert broken.converged and not math.isfinite(broken.llf)
    _close(fit["random_intercept_variance"], float(ref.cov_re.iloc[0, 0]), 1e-8)
    for name, value in ref.fe_params.items():
        if not name.startswith("C(group"):
            continue
        level = name.split("[T.")[1][:-1]
        _close(est[("mx", f"group[{level}]", "pooled")]["estimate"], value, 1e-8)
        _close(est[("mx", f"group[{level}]", "pooled")]["std_error"], ref.bse_fe[name], 1e-8)
