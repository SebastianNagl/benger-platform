"""OLS with absorbed fixed effects and named variance conventions.

The numeric core of the engine. Point estimates follow statsmodels' OLS
exactly (Moore-Penrose pseudo-inverse of the design, bread
``pinv(X) pinv(X)'``), so the default ``statsmodels`` convention reproduces
``sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": ...})`` on the
same within-transformed data to machine precision. Every small-sample choice
is explicit:

``ssc="statsmodels"``
    K = the columns of the fitted design (after absorption and after
    dropping identically-zero columns). iid: RSS/(N-K); HC1: N/(N-K) times
    HC0; cluster (CRV1): G/(G-1) * (N-1)/(N-K) for each clustering
    dimension with its own G; two-way as V1 + V2 - V12 (Cameron, Gelbach
    and Miller) with V12 over the intersection, without an eigenvalue fix.

``ssc="fixest"``
    The defaults of R fixest as implemented by pyfixest
    (``k_fixef="nonnested"``, ``G_df="min"``): K also counts the absorbed
    fixed-effect levels (one less per additional fixed-effect set), except
    that a set fully nested in a cluster dimension counts as one; iid
    RSS/(N-K); HC1 N/(N-K); cluster (N-1)/(N-K) * G/(G-1) with G the
    smallest cluster count for every component.

``ssc="none"``
    No factor: iid RSS/N, HC0, CRV0.

Degrees of freedom for t inference: G-1 for cluster variances (G the
smallest cluster count), N-K otherwise, with K as above.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np


class EngineError(ValueError):
    """A fit that cannot be computed (no rows, too few clusters, ...).

    ``n_obs`` is the number of usable observations when the estimator knows
    it (for example the pairs found before a minimum-count gate)."""

    def __init__(self, message: str, n_obs: Optional[int] = None):
        super().__init__(message)
        self.n_obs = n_obs


@dataclass
class Fit:
    names: List[str]
    beta: np.ndarray
    vcov: np.ndarray
    n: int
    k: int
    df_resid: int
    rank: int
    vcov_type: str
    ssc: str
    n_clusters: Optional[List[int]] = None
    df_t: Optional[int] = None
    dropped: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    fe_levels: List[int] = field(default_factory=list)
    k_ssc: Optional[int] = None
    # Iterative estimators: convergence, iterations and estimator-specific
    # results (log-likelihood, variance components, optimizer) for the fit
    # summary; parameters a separation check flagged.
    converged: Optional[bool] = None
    iterations: Optional[int] = None
    extra: dict = field(default_factory=dict)
    separated: List[str] = field(default_factory=list)
    # The design of the estimation sample, for average marginal effects
    # (estimators.LogitDesign); None for the other estimators.
    design: Optional[object] = None

    def index(self, name: str) -> int:
        return self.names.index(name)


def group_codes(keys: Sequence[np.ndarray]) -> Tuple[np.ndarray, int]:
    """Integer codes 0..G-1 of the row-wise combination of ``keys``
    (each an array of hashable values without missing entries)."""
    if len(keys) == 1:
        codes, uniques = _factorize(keys[0])
        return codes, len(uniques)
    combined = np.zeros(len(keys[0]), dtype=np.int64)
    for key in keys:
        codes, uniques = _factorize(key)
        combined = combined * (len(uniques) + 1) + codes
    codes, uniques = _factorize(combined)
    return codes, len(uniques)


def _factorize(values: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    import pandas as pd

    codes, uniques = pd.factorize(np.asarray(values, dtype=object), sort=True)
    if (codes < 0).any():
        raise EngineError("missing value in a grouping key")
    return codes.astype(np.int64), np.asarray(uniques, dtype=object)


def demean(
    data: np.ndarray,
    fe_codes: Sequence[np.ndarray],
    *,
    tolerance: float = 1e-12,
    max_iter: int = 10000,
) -> Tuple[np.ndarray, int]:
    """Absorb fixed effects from every column of ``data`` (n x c).

    One set: subtract the group mean, computed by pandas' groupby mean so the
    numbers equal ``x - x.groupby(g).transform("mean")``. Several sets:
    alternating projections until the largest change is below
    ``tolerance * (1 + max|x|)``; returns the iteration count (1 for one
    set)."""
    import pandas as pd

    def one(x: np.ndarray, codes: np.ndarray) -> np.ndarray:
        frame = pd.DataFrame(x)
        means = frame.groupby(codes, sort=False).transform("mean").to_numpy()
        return x - means

    x = np.array(data, dtype=float, copy=True)
    if not fe_codes:
        return x, 0
    if len(fe_codes) == 1:
        return one(x, fe_codes[0]), 1
    for it in range(1, max_iter + 1):
        before = x
        for codes in fe_codes:
            x = one(x, codes)
        change = np.max(np.abs(x - before)) if x.size else 0.0
        scale = 1.0 + (np.max(np.abs(x)) if x.size else 0.0)
        if change <= tolerance * scale:
            return x, it
    raise EngineError(
        f"absorbing {len(fe_codes)} fixed-effect sets did not converge in {max_iter} iterations"
    )


def _group_sums(xu: np.ndarray, codes: np.ndarray, groups: int) -> np.ndarray:
    out = np.empty((groups, xu.shape[1]))
    for j in range(xu.shape[1]):
        out[:, j] = np.bincount(codes, weights=xu[:, j], minlength=groups)
    return out


def _nested(fe: np.ndarray, cluster: np.ndarray) -> bool:
    """Every level of ``fe`` lies inside one cluster."""
    import pandas as pd

    pairs = pd.DataFrame({"fe": fe, "cl": cluster}).drop_duplicates()
    return bool(pairs["fe"].is_unique)


def ols(
    y: np.ndarray,
    X: np.ndarray,
    names: Sequence[str],
    *,
    vcov_type: str = "iid",
    clusters: Optional[Sequence[np.ndarray]] = None,
    ssc: str = "statsmodels",
    fe_codes: Sequence[np.ndarray] = (),
    fe_levels: Sequence[int] = (),
) -> Fit:
    """Fit ``y`` on ``X`` (already within-transformed when fixed effects are
    absorbed; ``fe_codes``/``fe_levels`` then describe what was absorbed, for
    the ``fixest`` parameter count)."""
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    n, k = X.shape
    if n == 0:
        raise EngineError("no observations")
    if k == 0:
        raise EngineError("no regressors left to estimate")
    if n <= k:
        raise EngineError(f"{n} observations for {k} parameters")
    pinv = np.linalg.pinv(X, rcond=1e-15)
    beta = pinv @ y
    bread = pinv @ pinv.T
    resid = y - X @ beta
    rank = int(np.linalg.matrix_rank(X))
    warnings: List[str] = []
    if rank < k:
        warnings.append(f"collinear regressors: rank {rank} < {k} parameters")

    # parameter count of the small-sample factor
    if ssc == "fixest" and fe_levels:
        n_fe = len(fe_levels)
        k_fe = int(sum(fe_levels))
        k_fe_adj = k_fe - (n_fe - 1) if n_fe > 1 else k_fe
        k_ssc = k + k_fe_adj
        if vcov_type == "cluster" and clusters:
            nested = [
                i
                for i, codes in enumerate(fe_codes)
                if any(_nested(codes, c) for c in clusters)
            ]
            if nested:
                k_ssc = k_ssc - sum(fe_levels[i] for i in nested) + len(nested)
    else:
        k_ssc = k
    if n - k_ssc <= 0:
        raise EngineError(f"{n} observations for {k_ssc} parameters including fixed effects")

    n_clusters = None
    df_t: Optional[int]
    if vcov_type == "iid":
        rss = float(resid @ resid)
        denom = n if ssc == "none" else n - k_ssc
        vcov = bread * (rss / denom)
        df_t = n - k_ssc
    elif vcov_type == "hc1":
        xu = X * resid[:, None]
        meat = xu.T @ xu
        vcov = bread @ meat @ bread
        if ssc != "none":
            vcov = vcov * (n / (n - k_ssc))
        df_t = n - k_ssc
    elif vcov_type == "cluster":
        if not clusters or len(clusters) > 2:
            raise EngineError("cluster variance needs one or two clustering dimensions")
        xu = X * resid[:, None]
        dims: List[Tuple[np.ndarray, int, float]] = []
        counts = [int(c.max()) + 1 for c in clusters]
        n_clusters = counts
        if min(counts) < 2:
            raise EngineError(f"cluster variance needs at least 2 clusters, found {min(counts)}")
        g_min = min(counts)

        def factor(g: int) -> float:
            if ssc == "none":
                return 1.0
            if ssc == "fixest":
                return (g_min / (g_min - 1.0)) * ((n - 1.0) / float(n - k_ssc))
            return g / (g - 1.0) * ((n - 1.0) / float(n - k_ssc))

        for c, g in zip(clusters, counts):
            dims.append((c, g, 1.0))
        if len(clusters) == 2:
            inter, g12 = group_codes([clusters[0], clusters[1]])
            dims.append((inter, g12, -1.0))
        vcov = np.zeros((k, k))
        for codes, g, sign in dims:
            S = _group_sums(xu, codes, g)
            v = bread @ (S.T @ S) @ bread
            vcov = vcov + sign * factor(g) * v
        df_t = g_min - 1
    else:
        raise EngineError(f"unknown variance estimator {vcov_type!r}")
    return Fit(
        names=list(names),
        beta=beta,
        vcov=vcov,
        n=n,
        k=k,
        df_resid=n - k,
        rank=rank,
        vcov_type=vcov_type,
        ssc=ssc,
        n_clusters=n_clusters,
        df_t=df_t,
        warnings=warnings,
        fe_levels=list(fe_levels),
        k_ssc=k_ssc,
    )
