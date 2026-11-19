"""Run a normalized spec over a frame: fits, contrasts, families.

:func:`run_spec` is deterministic: the estimates come out in spec order
(estimand, then scope, then contrast) with a ``position``, and the same frame,
spec and engine version give bit-identical numbers.

Every estimate row is a plain dict with JSON-safe values (``None`` for
missing numbers) and the keys of :data:`ESTIMATE_KEYS`; analysis runs store
one row per estimate.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np

from analysis.estimators import ScopedFit, fit_estimand, frame_columns, truthy_mask
import re

from analysis.inference import (
    ContrastError,
    ame_contrast,
    contrast_vector,
    linear_contrast,
    mark_separation,
    mde,
    ratio_contrast,
    separated_in,
    wald_test,
)
from analysis.multiplicity import adjust
from analysis.ols import EngineError
from analysis.spec import ESTIMATOR_PARAMETER

ESTIMATE_KEYS = (
    "position",
    "estimand_id",
    "contrast_id",
    "estimator",
    "kind",
    "outcome",
    "scope",
    "scope_values",
    "status",
    "message",
    "estimate",
    "std_error",
    "statistic",
    "df",
    "p_value",
    "null_value",
    "ci_level",
    "ci_lower",
    "ci_upper",
    "tost",
    "equivalent",
    "mde",
    "ratio",
    "family",
    "p_adjusted",
    "adjustments",
    "n_obs",
    "n_clusters",
    "k_params",
    "conventions",
)


@dataclass
class AnalysisResult:
    estimates: List[Dict[str, Any]]
    fits: List[Dict[str, Any]]
    warnings: List[str] = field(default_factory=list)
    timings: Dict[str, float] = field(default_factory=dict)
    rows_in_filter: int = 0


def _clean(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (np.floating,)):
        v = float(value)
        return v if math.isfinite(v) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _conventions_record(est: Mapping[str, Any]) -> Dict[str, Any]:
    conv = dict(est["conventions"])
    kind = est["estimator"]
    conv["vcov"] = est.get("vcov")
    if kind in ("fe_ols", "logit", "bradley_terry"):
        conv["fixed_effects"] = est.get("fixed_effects") or []
        conv["method"] = est.get("method") if est.get("fixed_effects") else None
    if kind == "bradley_terry":
        conv["link"] = est.get("link", "logit")
    if kind == "mixedlm":
        conv["groups"] = list(est["groups"])
    if kind in ("plackett_luce", "clogit_rank1"):
        conv["choice_set"] = list(est["choice_set"])
        conv["stages"] = 1 if kind == "clogit_rank1" else est.get("stages")
    return conv


def _spearman_row(sf: ScopedFit) -> Dict[str, Any]:
    fit = sf.fit
    extra = fit.extra
    row: Dict[str, Any] = {"n_obs": fit.n, "n_clusters": None, "k_params": 1, "df": fit.df_t}
    if extra.get("constant_input"):
        row.update(status="not_estimable", message="an input is constant, so its ranks carry no order")
        return row
    row.update(
        estimate=extra["rho"],
        statistic=extra.get("t"),
        p_value=extra.get("p_value"),
        null_value=0.0,
        status="ok",
    )
    return row


def _resolve_joint_rows(est: Mapping[str, Any], sf: ScopedFit, test: Mapping[str, Any]):
    """``(rows, reason)``: the (value, gradient, null) rows of a joint test,
    or None and why it cannot be computed on this fit."""
    fit = sf.fit
    if "rows" in test:
        contrasts = [{"id": f"row{i}", "kind": "linear", "weights": w} for i, w in enumerate(test["rows"])]
    elif "parameters" in test:
        patterns = [re.compile(".*".join(re.escape(part) for part in pat.split("*")) + r"\Z") for pat in test["parameters"]]
        names = [n for n in fit.names if any(p.match(n) for p in patterns)]
        if not names:
            return None, "no parameter matches " + ", ".join(test["parameters"])
        contrasts = [{"id": n, "kind": "linear", "weights": {n: 1.0}} for n in names]
    else:
        listed = est["contrasts"] if isinstance(est["contrasts"], list) else []
        by_id = {c["id"]: c for c in listed}
        contrasts = []
        for cid in test["contrasts"]:
            if cid in by_id:
                contrasts.append(by_id[cid])
            elif not listed and cid in fit.names:
                contrasts.append({"id": cid, "kind": "linear", "weights": {cid: 1.0}})
            else:
                return None, f"unknown contrast {cid!r}"
    rows = []
    separated: List[str] = []
    for c in contrasts:
        value, grad, null, reason = contrast_vector(fit, c, implied_zero=sf.implied_zero)
        if value is None:
            return None, reason
        rows.append((value, grad, null))
        separated += [n for n in separated_in(fit, c) if n not in separated]
    return (rows, separated), None


def _contrasts_for(est: Mapping[str, Any], fit) -> List[Dict[str, Any]]:
    contrasts = est["contrasts"]
    if contrasts != "terms":
        return list(contrasts)
    if fit is None:
        # The fit failed: one error row, so the failure shows among the estimates.
        name = ESTIMATOR_PARAMETER.get(est["estimator"])
        return [{"id": name, "kind": "linear", "weights": {name: 1.0} if name else {}, "null": 0.0}]
    return [
        {"id": name, "kind": "linear", "weights": {name: 1.0}, "null": 0.0}
        for name in fit.names
        if not name.startswith("(fe") and name != "(intercept)"
    ] or [
        {"id": name, "kind": "linear", "weights": {name: 1.0}, "null": 0.0} for name in fit.names[:1]
    ]


def _estimate_rows(est: Mapping[str, Any], sf: ScopedFit) -> List[Dict[str, Any]]:
    rows = []
    conventions = _conventions_record(est)
    for c in _contrasts_for(est, sf.fit):
        row: Dict[str, Any] = {
            "estimand_id": est["id"],
            "contrast_id": c["id"],
            "estimator": est["estimator"],
            "kind": c.get("kind", "linear"),
            "outcome": est["outcome"],
            "scope": sf.scope,
            "scope_values": dict(sf.scope_values),
            "conventions": conventions,
        }
        if sf.fit is None:
            row.update(status="error", message=sf.error, n_obs=sf.rows)
        elif est["estimator"] == "spearman":
            row.update(_spearman_row(sf))
        else:
            try:
                if row["kind"] == "ratio":
                    row.update(ratio_contrast(sf.fit, c, est["conventions"], implied_zero=sf.implied_zero))
                elif row["kind"] == "ame":
                    row.update(ame_contrast(sf.fit, c, est["conventions"]))
                else:
                    row.update(linear_contrast(sf.fit, c, est["conventions"], implied_zero=sf.implied_zero))
                mark_separation(row, separated_in(sf.fit, c))
            except ContrastError as exc:
                row.update(status="error", message=str(exc), n_obs=sf.fit.n)
        tosts = row.get("tost")
        row["equivalent"] = tosts[0].get("equivalent") if tosts else None
        rows.append(row)
    for test in est.get("joint_tests") or []:
        row = {
            "estimand_id": est["id"],
            "contrast_id": test["id"],
            "estimator": est["estimator"],
            "kind": "wald",
            "outcome": est["outcome"],
            "scope": sf.scope,
            "scope_values": dict(sf.scope_values),
            "conventions": conventions,
        }
        if sf.fit is None:
            row.update(status="error", message=sf.error, n_obs=sf.rows)
        else:
            resolved, reason = _resolve_joint_rows(est, sf, test)
            if resolved is None:
                row.update(status="not_estimable", message=reason, n_obs=sf.fit.n)
            else:
                test_rows, separated = resolved
                row.update(wald_test(sf.fit, test_rows, est["conventions"]))
                mark_separation(row, separated, joint=True)
        row["equivalent"] = None
        rows.append(row)
    return rows


def _scope_kind(row: Mapping[str, Any]) -> str:
    if row["scope"] == "pooled":
        return "pooled"
    return "by:" + ",".join(row["scope_values"].keys())


def _member_matches(member: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    if member["estimand"] != row["estimand_id"]:
        return False
    if member.get("contrast", "*") not in ("*", row["contrast_id"]):
        return False
    scope = member.get("scope", "*")
    if scope == "*":
        return True
    if scope == "pooled":
        return row["scope"] == "pooled"
    if scope.startswith("by:"):
        return _scope_kind(row) == "by:" + ",".join(c.strip() for c in scope[3:].split(","))
    return row["scope"] == scope


def apply_families(rows: List[Dict[str, Any]], families: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        row.setdefault("adjustments", [])
        row.setdefault("family", None)
        row.setdefault("p_adjusted", None)
    for fam in families:
        members = [
            i for i, row in enumerate(rows) if any(_member_matches(m, row) for m in fam["members"])
        ]
        groups: Dict[Tuple, List[int]] = {}
        for i in members:
            row = rows[i]
            key = []
            for part in fam.get("split_by") or []:
                if part == "estimand":
                    key.append(row["estimand_id"])
                elif part == "contrast":
                    key.append(row["contrast_id"])
                elif part == "scope_kind":
                    key.append(_scope_kind(row))
                else:
                    key.append(row["scope"])
            groups.setdefault(tuple(key), []).append(i)
        for key, idx in groups.items():
            ps = [rows[i].get("p_value") for i in idx]
            missing = fam.get("missing_p", "skip")
            adjusted = adjust(ps, fam["method"], missing)
            size = len(idx) if missing == "count" else sum(1 for p in adjusted if p is not None)
            for i, p_adj in zip(idx, adjusted):
                entry: Dict[str, Any] = {
                    "family": fam["id"],
                    "method": fam["method"],
                    "group": list(key),
                    "size": size,
                    "p_adjusted": p_adj,
                }
                if fam.get("mde") and size:
                    m = fam["mde"]
                    se = rows[i].get("std_error")
                    entry["mde"] = {
                        "power": float(m.get("power", 0.8)),
                        "alpha": float(m.get("alpha", 0.05)),
                        "tests": int(m.get("tests", size)),
                        "value": mde(se, float(m.get("power", 0.8)), float(m.get("alpha", 0.05)), int(m.get("tests", size)))
                        if isinstance(se, float) and math.isfinite(se)
                        else None,
                    }
                rows[i]["adjustments"].append(entry)
                if rows[i]["family"] is None:
                    rows[i]["family"] = fam["id"]
                    rows[i]["p_adjusted"] = p_adj


def run_spec(frame, spec: Mapping[str, Any]) -> AnalysisResult:
    """Every estimand of ``spec`` (normalized) on ``frame``."""
    t0 = time.perf_counter()
    columns = frame_columns(frame)
    n = len(frame)
    warnings: List[str] = []
    base = truthy_mask(columns, n, spec.get("filter"), "/filter", warnings)
    rows: List[Dict[str, Any]] = []
    fits: List[Dict[str, Any]] = []
    for i, est in enumerate(spec["estimands"]):
        for sf in fit_estimand(columns, n, est, base, f"/estimands/{i}", warnings):
            fits.append(sf.summary())
            if sf.error:
                warnings.append(f"{est['id']} [{sf.scope}]: {sf.error}")
            elif sf.fit is not None:
                for w in sf.fit.warnings:
                    warnings.append(f"{est['id']} [{sf.scope}]: {w}")
            rows.extend(_estimate_rows(est, sf))
    t1 = time.perf_counter()
    apply_families(rows, spec.get("families") or [])
    out = []
    for pos, row in enumerate(rows):
        full = {k: row.get(k) for k in ESTIMATE_KEYS}
        full["position"] = pos
        out.append(_clean(full))
    return AnalysisResult(
        estimates=out,
        fits=[_clean(f) for f in fits],
        warnings=warnings,
        timings={"estimation_s": t1 - t0, "total_s": time.perf_counter() - t0},
        rows_in_filter=int(base.sum()),
    )


__all__ = ["AnalysisResult", "ESTIMATE_KEYS", "EngineError", "apply_families", "run_spec"]
