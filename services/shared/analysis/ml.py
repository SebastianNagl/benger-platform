"""Maximum-likelihood estimators: logit and rank-ordered (Plackett-Luce) logit.

Both are fitted by Newton-Raphson from zero with the analytic Hessian (both
log-likelihoods are concave), halving a step that lowers the likelihood, and
stop when the largest step is below ``tolerance * (1 + max|b|)``. Newton
converges quadratically, so the estimates are the maximum to machine
precision, not to an optimizer's gradient tolerance.

Variances (:func:`sandwich`), with ``H`` the negative Hessian at the maximum
and ``s_i`` the score of independent observation ``i`` (an answer for the
logit, a choice set for Plackett-Luce):

``iid``
    ``H^-1`` (the model-based variance; no small-sample factor).
``hc1``
    ``H^-1 (sum s_i s_i') H^-1``. statsmodels applies no small-sample
    factor to robust variances of maximum-likelihood models, so neither
    convention does here.
``cluster``
    ``H^-1 (sum_g S_g S_g') H^-1`` with ``S_g`` the score sum of cluster
    ``g``, times ``G/(G-1) * (N-1)/(N-K)`` under the ``statsmodels``
    convention (what statsmodels applies to ``Logit(...).fit(cov_type=
    "cluster")``) and 1 under ``none``; two-way as V1 + V2 - V12.

Degrees of freedom for t inference as for OLS: G-1 for cluster variances,
N-K otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from analysis.ols import EngineError, Fit, group_codes

#: Largest condition number of the Hessian accepted as non-singular.
MAX_CONDITION = 1e15
MAX_HALVINGS = 40


@dataclass
class MLResult:
    beta: np.ndarray
    hessian: np.ndarray  # negative Hessian of the log-likelihood (positive definite)
    scores: np.ndarray  # one row per independent observation
    loglik: float
    iterations: int
    converged: bool


def _solve(H: np.ndarray, g: np.ndarray, what: str) -> np.ndarray:
    if not np.all(np.isfinite(H)) or np.linalg.cond(H) > MAX_CONDITION:
        raise EngineError(f"{what}: the information matrix is singular (collinear regressors)")
    return np.linalg.solve(H, g)


def newton(fun, k: int, *, tolerance: float, max_iter: int, what: str) -> MLResult:
    """Maximise a concave log-likelihood. ``fun(beta)`` returns ``(loglik,
    gradient, negative Hessian, scores)``."""
    beta = np.zeros(k)
    ll, grad, H, scores = fun(beta)
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):
        try:
            step = _solve(H, grad, what)
        except EngineError:
            if iterations == 1:
                raise
            # The information vanishes along a direction (separation): keep
            # the last iterate, report non-convergence and let the
            # separation check flag the parameters that ran away.
            iterations -= 1
            break
        trial = beta + step
        ll_t, grad_t, H_t, scores_t = fun(trial)
        halvings = 0
        while not (np.isfinite(ll_t) and ll_t >= ll - 1e-12 * (1.0 + abs(ll))) and halvings < MAX_HALVINGS:
            step = step / 2.0
            trial = beta + step
            ll_t, grad_t, H_t, scores_t = fun(trial)
            halvings += 1
        beta, ll, grad, H, scores = trial, ll_t, grad_t, H_t, scores_t
        if np.max(np.abs(step)) <= tolerance * (1.0 + np.max(np.abs(beta))):
            converged = True
            break
    return MLResult(beta=beta, hessian=H, scores=scores, loglik=float(ll), iterations=iterations, converged=converged)


# --------------------------------------------------------------------------
# Logit
# --------------------------------------------------------------------------


def logit_terms(y: np.ndarray, X: np.ndarray):
    """The ``fun`` of :func:`newton` for a logit of ``y`` (in [0, 1]) on ``X``."""

    def fun(beta: np.ndarray):
        eta = X @ beta
        p = 1.0 / (1.0 + np.exp(-eta))
        ll = float(np.sum(y * eta - np.logaddexp(0.0, eta)))
        resid = y - p
        scores = X * resid[:, None]
        W = p * (1.0 - p)
        H = X.T @ (X * W[:, None])
        return ll, scores.sum(axis=0), H, scores

    return fun


def fit_logit(y: np.ndarray, X: np.ndarray, *, tolerance: float, max_iter: int) -> MLResult:
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    if len(y) == 0:
        raise EngineError("no observations")
    if X.shape[1] == 0:
        raise EngineError("no regressors left to estimate")
    if len(y) <= X.shape[1]:
        raise EngineError(f"{len(y)} observations for {X.shape[1]} parameters")
    if np.any((y < 0) | (y > 1)):
        raise EngineError("a logit outcome must lie between 0 and 1")
    return newton(logit_terms(y, X), X.shape[1], tolerance=tolerance, max_iter=max_iter, what="logit")


def logit_probabilities(X: np.ndarray, beta: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-(X @ beta)))


# --------------------------------------------------------------------------
# Rank-ordered logit (Plackett-Luce)
# --------------------------------------------------------------------------


@dataclass
class ChoiceSets:
    """Choice sets padded to a common width: ``X`` (S x M x k) holds the
    alternatives of each set in the order chosen (first choice first),
    ``valid`` (S x M) marks real alternatives, ``stages`` (S) how many
    choices of each set enter the likelihood."""

    X: np.ndarray
    valid: np.ndarray
    stages: np.ndarray


def pl_terms(sets: ChoiceSets):
    """The ``fun`` of :func:`newton` for a Plackett-Luce likelihood: stage
    ``t`` of a set chooses its ``t``-th alternative from the alternatives not
    chosen before."""
    Xo, valid, stages = sets.X, sets.valid, sets.stages
    S, M, k = Xo.shape
    max_stage = int(stages.max()) if S else 0

    def fun(beta: np.ndarray):
        u = Xo @ beta  # S x M
        ll = np.zeros(S)
        g = np.zeros((S, k))
        H = np.zeros((k, k))
        positions = np.arange(M)
        for t in range(max_stage):
            active = stages > t
            if not active.any():
                break
            risk = valid & (positions[None, :] >= t) & active[:, None]
            us = np.where(risk, u, -np.inf)
            m = np.max(np.where(active[:, None], us, 0.0), axis=1, keepdims=True)
            w = np.where(risk, np.exp(us - m), 0.0)
            den = w.sum(axis=1)
            den_safe = np.where(active, den, 1.0)
            pw = w / den_safe[:, None]
            xbar = np.einsum("sm,smk->sk", pw, Xo)
            ll += np.where(active, u[:, t] - (np.log(den_safe) + m[:, 0]), 0.0)
            g += np.where(active[:, None], Xo[:, t, :] - xbar, 0.0)
            second = np.einsum("sm,smk,sml->kl", pw, Xo, Xo)
            H += second - xbar.T @ xbar
        return float(ll.sum()), g.sum(axis=0), H, g

    return fun


def fit_plackett_luce(sets: ChoiceSets, *, tolerance: float, max_iter: int) -> MLResult:
    S, _, k = sets.X.shape
    if S == 0:
        raise EngineError("no choice sets")
    if k == 0:
        raise EngineError("no regressors left to estimate")
    if S <= k:
        raise EngineError(f"{S} choice sets for {k} parameters")
    return newton(pl_terms(sets), k, tolerance=tolerance, max_iter=max_iter, what="plackett_luce")


# --------------------------------------------------------------------------
# Variances
# --------------------------------------------------------------------------


def _group_sums(scores: np.ndarray, codes: np.ndarray, groups: int) -> np.ndarray:
    out = np.empty((groups, scores.shape[1]))
    for j in range(scores.shape[1]):
        out[:, j] = np.bincount(codes, weights=scores[:, j], minlength=groups)
    return out


def sandwich(
    result: MLResult,
    names: Sequence[str],
    *,
    vcov_type: str,
    clusters: Optional[Sequence[np.ndarray]],
    ssc: str,
    estimator: str,
) -> Fit:
    """The fit of a maximum-likelihood result with the requested variance."""
    H = result.hessian
    n, k = result.scores.shape[0], len(names)
    if n - k <= 0:
        raise EngineError(f"{n} observations for {k} parameters")
    bread = np.linalg.inv(H) if np.linalg.cond(H) <= MAX_CONDITION else np.linalg.pinv(H)
    n_clusters = None
    if vcov_type == "iid":
        vcov = bread
        df_t: Optional[int] = n - k
    elif vcov_type == "hc1":
        s = result.scores
        vcov = bread @ (s.T @ s) @ bread
        df_t = n - k
    elif vcov_type == "cluster":
        if not clusters or len(clusters) > 2:
            raise EngineError("cluster variance needs one or two clustering dimensions")
        counts = [int(c.max()) + 1 for c in clusters]
        n_clusters = counts
        if min(counts) < 2:
            raise EngineError(f"cluster variance needs at least 2 clusters, found {min(counts)}")
        dims: List[Tuple[np.ndarray, int, float]] = [(c, g, 1.0) for c, g in zip(clusters, counts)]
        if len(clusters) == 2:
            inter, g12 = group_codes([clusters[0], clusters[1]])
            dims.append((inter, g12, -1.0))
        vcov = np.zeros((k, k))
        for codes, g, sign in dims:
            S = _group_sums(result.scores, codes, g)
            factor = 1.0 if ssc == "none" else g / (g - 1.0) * ((n - 1.0) / float(n - k))
            vcov = vcov + sign * factor * (bread @ (S.T @ S) @ bread)
        df_t = min(counts) - 1
    else:
        raise EngineError(f"unknown variance estimator {vcov_type!r}")
    warnings: List[str] = []
    if not result.converged:
        warnings.append(f"{estimator} did not converge in {result.iterations} iterations")
    return Fit(
        names=list(names),
        beta=result.beta,
        vcov=vcov,
        n=n,
        k=k,
        df_resid=n - k,
        rank=k,
        vcov_type=vcov_type,
        ssc=ssc,
        n_clusters=n_clusters,
        df_t=df_t,
        warnings=warnings,
        k_ssc=k,
        converged=result.converged,
        iterations=result.iterations,
        extra={"loglik": result.loglik},
    )
