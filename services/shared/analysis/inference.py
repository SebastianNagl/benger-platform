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

An average marginal effect (kind ``ame``, logit only) is the mean over the
estimation sample of the predicted probability with one column set to a
level minus the same with it set to a reference, with a delta-method SE.
A joint test (:func:`wald_test`) asks whether several contrasts equal their
nulls at once (chi2 on the rank of their covariance).

A contrast of a maximum-likelihood fit that depends on a separated parameter
(:func:`separated_in`) keeps its estimate and interval but has no p-value
(status ``separation``).
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

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


def _standard_error(var: float) -> Tuple[float, str, Optional[str]]:
    """``(se, status, message)`` of a contrast with variance ``var``."""
    if not math.isfinite(var):
        return math.nan, "not_estimable", "the variance of this contrast is not finite"
    if var < 0:
        return math.nan, "negative_variance", "the variance of this contrast is negative"
    if var == 0:
        return 0.0, "degenerate", "the contrast has no sampling variance"
    return math.sqrt(var), "ok", None


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
    se, status, message = _standard_error(float(L @ fit.vcov @ L))
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
        status=status,
    )
    if message:
        row["message"] = message
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
    se, status, message = _standard_error(float(grad @ fit.vcov @ grad))
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
        ci_lower=est - crit * se if math.isfinite(se) else None,
        ci_upper=est + crit * se if math.isfinite(se) else None,
        status=status,
    )
    if message:
        row["message"] = message
    return row


# --------------------------------------------------------------------------
# Average marginal effects, separation and joint (Wald) tests
# --------------------------------------------------------------------------

#: Relative tolerance of the rank of a joint test's covariance (pinv cut-off).
WALD_RANK_TOLERANCE = 1e-10


def ame_value(fit: Fit, contrast: Mapping[str, Any]) -> Tuple[float, np.ndarray]:
    """``(value, gradient)`` of an average marginal effect: the mean over the
    estimation sample of ``p(x | column = level) - p(x | column = reference)``
    times ``scale``, with its gradient in the fit's parameters (delta
    method)."""
    from analysis.ml import logit_probabilities

    design = fit.design
    if design is None:
        raise ContrastError("average marginal effects need a logit fit")
    X1 = design.counterfactual(contrast["column"], contrast["level"])
    X0 = design.counterfactual(contrast["column"], contrast["reference"])
    p1 = logit_probabilities(X1, fit.beta)
    p0 = logit_probabilities(X0, fit.beta)
    m = len(p1)
    scale = float(contrast.get("scale", 1.0))
    value = float(np.mean(p1 - p0))
    grad = (p1 * (1 - p1)) @ X1 / m - (p0 * (1 - p0)) @ X0 / m
    return scale * value, scale * grad


def ame_contrast(fit: Fit, contrast: Mapping[str, Any], conventions: Mapping[str, Any], **_) -> Dict[str, Any]:
    """Estimate one average marginal effect of a logit."""
    from analysis.ols import EngineError

    row = _base_row(fit, conventions)
    row["null_value"] = float(contrast.get("null", 0.0))
    try:
        est, grad = ame_value(fit, contrast)
    except EngineError as exc:
        row.update(status="not_estimable", message=str(exc))
        return row
    se, status, message = _standard_error(float(grad @ fit.vcov @ grad))
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
        status=status,
    )
    if message:
        row["message"] = message
    if contrast.get("tost"):
        row["tost"] = [
            tost(est, se, tuple(t["bounds"]), float(t["level"]), conventions["inference"], df)
            for t in contrast["tost"]
        ]
    if contrast.get("mde"):
        mm = contrast["mde"]
        row["mde"] = {
            "power": float(mm.get("power", 0.8)),
            "alpha": float(mm.get("alpha", 0.05)),
            "tests": int(mm.get("tests", 1)),
            "value": mde(se, float(mm.get("power", 0.8)), float(mm.get("alpha", 0.05)), int(mm.get("tests", 1))),
        }
    return row


def separated_in(fit: Fit, contrast: Mapping[str, Any]) -> list:
    """The separated parameters a contrast depends on: those with a nonzero
    weight (linear, ratio), any separated parameter for a marginal effect."""
    if not fit.separated:
        return []
    kind = contrast.get("kind", "linear")
    if kind == "ame":
        return list(fit.separated)
    weights: Dict[str, float] = {}
    if kind == "ratio":
        for part in ("numerator", "denominator"):
            weights.update(contrast[part]["weights"])
    else:
        weights = dict(contrast.get("weights") or {})
    return [name for name in fit.separated if float(weights.get(name, 0.0)) != 0.0]


def mark_separation(row: Dict[str, Any], names, *, joint: bool = False) -> None:
    """Withhold the p-value (and the equivalence verdicts) of a contrast on
    separated parameters; the estimate and interval stay as computed. A
    joint test on separated parameters is marked even when its variance is
    not usable, since the separation is the reason."""
    allowed = ("ok", "degenerate", "not_estimable") if joint else ("ok", "degenerate")
    if not names or row.get("status") not in allowed:
        return
    row["status"] = "separation"
    row["p_value"] = None
    row["message"] = "separation: " + ", ".join(names) + " (no p-value)"
    for t in row.get("tost") or []:
        t.update(p_lower=None, p_upper=None, p_tost=None, equivalent=None)


def contrast_vector(
    fit: Fit, contrast: Mapping[str, Any], *, implied_zero=()
) -> Tuple[Optional[float], Optional[np.ndarray], float, Optional[str]]:
    """``(value, gradient, null, reason)`` of a contrast for a joint test;
    value and gradient are None with the reason when it is not estimable."""
    kind = contrast.get("kind", "linear")
    if kind == "ame":
        from analysis.ols import EngineError

        try:
            value, grad = ame_value(fit, contrast)
        except EngineError as exc:
            return None, None, 0.0, str(exc)
        return value, grad, float(contrast.get("null", 0.0)), None
    if kind == "ratio":
        num, den = contrast["numerator"], contrast["denominator"]
        a, reason_a = weight_vector(fit, num["weights"], implied_zero=implied_zero)
        c, reason_c = weight_vector(fit, den["weights"], implied_zero=implied_zero)
        if a is None or c is None:
            return None, None, 0.0, reason_a or reason_c
        A = float(a @ fit.beta) + float(num.get("constant", 0.0))
        B = float(c @ fit.beta) + float(den.get("constant", 0.0))
        if abs(B) < max(float(contrast.get("min_abs_denominator", 0.0)), 1e-12):
            return None, None, 0.0, f"the denominator of {contrast['id']!r} is too close to zero"
        scale = float(contrast.get("scale", 1.0))
        null = contrast.get("null")
        return scale * A / B, scale * (a / B - c * A / B**2), float(null) if null is not None else 0.0, None
    L, reason = weight_vector(fit, contrast["weights"], implied_zero=implied_zero)
    if L is None:
        return None, None, 0.0, reason
    return float(L @ fit.beta), L, float(contrast.get("null", 0.0)), None


def wald_test(
    fit: Fit, rows: Sequence[Tuple[float, np.ndarray, float]], conventions: Mapping[str, Any]
) -> Dict[str, Any]:
    """Joint Wald test that every row's value equals its null:
    ``chi2 = r' pinv(G V G') r`` with ``r`` the values minus the nulls and
    ``G`` the stacked gradients, on as many degrees of freedom as the rank of
    ``G V G'`` (singular values below 1e-10 of the largest count as zero, so
    redundant restrictions do not add degrees of freedom)."""
    from scipy import stats

    out = _base_row(fit, conventions)
    out.update(estimate=None, std_error=None, null_value=None, ci_level=None, ci_lower=None, ci_upper=None)
    r = np.array([v - null for v, _, null in rows], dtype=float)
    G = np.vstack([g for _, g, _ in rows])
    V = G @ fit.vcov @ G.T
    if not np.all(np.isfinite(V)) or not np.all(np.isfinite(r)):
        out.update(status="not_estimable", message="the restrictions or their variance are not finite",
                   statistic=None, df=None, p_value=None)
        return out
    rank = int(np.linalg.matrix_rank(V, tol=WALD_RANK_TOLERANCE * max(1.0, float(np.abs(V).max()))))
    if rank == 0:
        out.update(status="not_estimable", message="the restrictions have no sampling variance",
                   statistic=None, df=0, p_value=None)
        return out
    chi2 = float(r @ np.linalg.pinv(V, rcond=WALD_RANK_TOLERANCE) @ r)
    out.update(statistic=chi2, df=rank, p_value=float(stats.chi2.sf(chi2, rank)), status="ok")
    if rank < len(rows):
        out["message"] = f"rank {rank} of {len(rows)} restrictions"
    return out
