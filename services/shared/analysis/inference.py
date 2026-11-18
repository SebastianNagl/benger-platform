"""Contrasts, intervals, equivalence tests (TOST) and minimum detectable effects.

A linear contrast is ``L'b`` with variance ``L'VL``; a ratio contrast is
``scale * (a'b + a0) / (c'b + c0)`` with a delta-method standard error. Both
report a two-sided p-value against ``null`` and a confidence interval
``est +- crit * se``, where ``crit`` is the ``ci_level`` quantile of the
inference distribution (normal, or t with the fit's degrees of freedom), or
the fixed number given as ``ci_critical``.

TOST (two one-sided tests): with bounds ``(lower, upper)`` and level
``tost_level`` (0.90 by default, one-sided alpha 0.05), the contrast is
equivalent when the ``tost_level`` interval lies strictly inside the bounds;
``p_tost`` is the larger of the two one-sided p-values. The TOST interval
always uses the exact quantile, whatever ``ci_critical`` says.

MDE: ``(q(1 - alpha / (2 m)) + q(power)) * se`` for ``m`` tests (a Holm or
Bonferroni worst case), with normal quantiles.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np

from analysis.ols import Fit

NULL_MATCH_TOLERANCE = 1e-9


class ContrastError(ValueError):
    """A contrast that names parameters the fit does not have."""


def _quantile(p: float, inference: str, df: Optional[int]) -> float:
    from scipy import stats

    if inference == "t":
        if not df or df <= 0:
            return math.nan
        return float(stats.t.ppf(p, df))
    return float(stats.norm.ppf(p))


def _two_sided_p(stat: float, inference: str, df: Optional[int]) -> float:
    from scipy import stats

    if inference == "t":
        if not df or df <= 0:
            return math.nan
        return float(2 * stats.t.sf(abs(stat), df))
    return float(2 * stats.norm.sf(abs(stat)))


def _sf(x: float, inference: str, df: Optional[int]) -> float:
    from scipy import stats

    if inference == "t":
        return float(stats.t.sf(x, df)) if df and df > 0 else math.nan
    return float(stats.norm.sf(x))


def _cdf(x: float, inference: str, df: Optional[int]) -> float:
    from scipy import stats

    if inference == "t":
        return float(stats.t.cdf(x, df)) if df and df > 0 else math.nan
    return float(stats.norm.cdf(x))


def weight_vector(
    fit: Fit,
    weights: Mapping[str, float],
    *,
    implied_zero: Mapping[str, str] = (),
) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """``L`` for ``weights`` over ``fit.names``.

    Returns ``(None, reason)`` when the contrast cannot be estimated from
    this fit: a weight on a regressor that was dropped as identically zero.
    ``implied_zero`` names parameters that are zero by construction (the
    reference level of a dummy coding) and may carry a weight. Any other
    unknown name raises :class:`ContrastError`."""
    L = np.zeros(len(fit.names))
    for name, w in weights.items():
        if name in fit.names:
            L[fit.names.index(name)] += float(w)
        elif name in fit.dropped:
            if float(w) != 0.0:
                return None, f"{name!r} was dropped as identically zero after absorbing fixed effects"
        elif name in implied_zero:
            continue
        else:
            raise ContrastError(
                f"unknown parameter {name!r}; the fit has {', '.join(fit.names) or 'none'}"
            )
    return L, None


def _critical(conventions: Mapping[str, Any], df: Optional[int]) -> float:
    fixed = conventions.get("ci_critical", "exact")
    if fixed != "exact":
        return float(fixed)
    level = float(conventions["ci_level"])
    return _quantile(1 - (1 - level) / 2, conventions["inference"], df)


def _p_value(est: float, se: float, null: float, conventions, df) -> Tuple[float, Optional[float]]:
    if not math.isfinite(se):
        return math.nan, None
    if se > 0:
        stat = (est - null) / se
        return _two_sided_p(stat, conventions["inference"], df), stat
    if conventions.get("degenerate_p") == "null_match":
        return (1.0 if abs(est - null) < NULL_MATCH_TOLERANCE else 0.0), None
    return math.nan, None


def tost(
    est: float,
    se: float,
    bounds: Tuple[float, float],
    level: float,
    inference: str,
    df: Optional[int],
) -> Dict[str, Any]:
    lower, upper = float(bounds[0]), float(bounds[1])
    out: Dict[str, Any] = {"lower": lower, "upper": upper, "level": float(level)}
    if not (math.isfinite(est) and math.isfinite(se)):
        out.update({"ci_lower": None, "ci_upper": None, "p_lower": None, "p_upper": None,
                    "p_tost": None, "equivalent": None})
        return out
    crit = _quantile(1 - (1 - level) / 2, inference, df)
    lo, hi = est - crit * se, est + crit * se
    if se > 0:
        p_lower = _sf((est - lower) / se, inference, df)
        p_upper = _cdf((est - upper) / se, inference, df)
        equivalent = bool(lo > lower and hi < upper)
    else:
        equivalent = bool(lower < est < upper)
        p_lower = 0.0 if est > lower else 1.0
        p_upper = 0.0 if est < upper else 1.0
    out.update(
        {
            "ci_lower": lo,
            "ci_upper": hi,
            "p_lower": p_lower,
            "p_upper": p_upper,
            "p_tost": max(p_lower, p_upper),
            "equivalent": equivalent,
        }
    )
    return out


def mde(se: float, power: float, alpha: float, tests: int) -> Optional[float]:
    from scipy import stats

    if not math.isfinite(se):
        return None
    z_alpha = float(stats.norm.ppf(1 - alpha / (2 * tests)))
    z_power = float(stats.norm.ppf(power))
    return (z_alpha + z_power) * se


def _base_row(fit: Fit, conventions: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "n_obs": fit.n,
        "n_clusters": fit.n_clusters,
        "k_params": fit.k,
        "df": fit.df_t if conventions["inference"] == "t" else None,
    }


def linear_contrast(
    fit: Fit,
    contrast: Mapping[str, Any],
    conventions: Mapping[str, Any],
    *,
    implied_zero=(),
) -> Dict[str, Any]:
    """Estimate one linear contrast; returns the inference fields of an
    estimate row."""
    row = _base_row(fit, conventions)
    row["null_value"] = float(contrast.get("null", 0.0))
    L, reason = weight_vector(fit, contrast["weights"], implied_zero=implied_zero)
    if L is None:
        row.update(status="not_estimable", message=reason)
        return row
    est = float(L @ fit.beta)
    var = float(L @ fit.vcov @ L)
    se = math.sqrt(var) if var >= 0 else math.nan
    df = fit.df_t if conventions["inference"] == "t" else None
    p, stat = _p_value(est, se, row["null_value"], conventions, df)
    crit = _critical(conventions, df)
    row.update(
        estimate=est,
        std_error=se,
        statistic=stat,
        p_value=p,
        ci_level=float(conventions["ci_level"]),
        ci_lower=est - crit * se if math.isfinite(se) else None,
        ci_upper=est + crit * se if math.isfinite(se) else None,
        status="ok" if math.isfinite(se) and se > 0 else ("degenerate" if se == 0 else "negative_variance"),
    )
    if row["status"] == "negative_variance":
        row["message"] = "the variance of this contrast is negative (two-way cluster variance)"
    elif row["status"] == "degenerate":
        row["message"] = "the contrast has no sampling variance"
    if contrast.get("tost"):
        row["tost"] = [
            tost(est, se, tuple(t["bounds"]), float(t["level"]), conventions["inference"], df)
            for t in contrast["tost"]
        ]
    if contrast.get("mde"):
        m = contrast["mde"]
        row["mde"] = {
            "power": float(m.get("power", 0.8)),
            "alpha": float(m.get("alpha", 0.05)),
            "tests": int(m.get("tests", 1)),
            "value": mde(se, float(m.get("power", 0.8)), float(m.get("alpha", 0.05)), int(m.get("tests", 1))),
        }
    return row


def ratio_contrast(
    fit: Fit,
    contrast: Mapping[str, Any],
    conventions: Mapping[str, Any],
    *,
    implied_zero=(),
) -> Dict[str, Any]:
    """``scale * (a'b + a0) / (c'b + c0)`` with a delta-method SE."""
    row = _base_row(fit, conventions)
    num, den = contrast["numerator"], contrast["denominator"]
    a, reason_a = weight_vector(fit, num["weights"], implied_zero=implied_zero)
    c, reason_c = weight_vector(fit, den["weights"], implied_zero=implied_zero)
    if a is None or c is None:
        row.update(status="not_estimable", message=reason_a or reason_c)
        return row
    A = float(a @ fit.beta) + float(num.get("constant", 0.0))
    B = float(c @ fit.beta) + float(den.get("constant", 0.0))
    scale = float(contrast.get("scale", 1.0))
    row["ratio"] = {"numerator": A, "denominator": B, "scale": scale}
    gate = float(contrast.get("min_abs_denominator", 0.0))
    if abs(B) < max(gate, 1e-12):
        row.update(
            status="not_estimable",
            message=f"denominator {B:.6g} is below the minimum {max(gate, 1e-12):.6g} in absolute value",
        )
        return row
    est = scale * A / B
    grad = scale * (a / B - c * A / B**2)
    var = float(grad @ fit.vcov @ grad)
    se = math.sqrt(max(var, 0.0))
    df = fit.df_t if conventions["inference"] == "t" else None
    crit = _critical(conventions, df)
    null = contrast.get("null")
    p, stat = (None, None)
    if null is not None:
        p, stat = _p_value(est, se, float(null), conventions, df)
    row.update(
        estimate=est,
        std_error=se,
        statistic=stat,
        p_value=p,
        null_value=float(null) if null is not None else None,
        ci_level=float(conventions["ci_level"]),
        ci_lower=est - crit * se,
        ci_upper=est + crit * se,
        status="ok" if se > 0 else "degenerate",
    )
    return row
