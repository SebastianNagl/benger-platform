"""Linear mixed model with a random intercept (statsmodels MixedLM).

``mixedlm`` fits ``outcome ~ terms`` with a random intercept per level of
``groups`` by statsmodels' ``MixedLM`` (REML by default). Unlike the other
estimators it is not computed by the engine itself: the variance component
comes from a numerical optimizer whose stopping point depends on the
optimizer, so the convention is statsmodels' own fit, and the workers' lock
pins its version (recorded with every run).

Acceptance (the conventions ``mixedlm_optimizers`` and
``mixedlm_max_se_ratio``): the optimizers are tried in order and the first
fit is kept that converged, has a finite log-likelihood, and whose
fixed-effect variances are all positive and finite with standard errors at
most ``mixedlm_max_se_ratio`` times the outcome's standard deviation.
``lbfgs`` can stop at the boundary of the variance component (variance 0,
an infinite log-likelihood, a singular Hessian, zero or absurd standard
errors) and still report convergence; such a fit is refused and the next
optimizer tried. When no optimizer gives an accepted fit, the estimand fails
with the last reason.

The optimizers stop at their own tolerances, so two optimizers agree on the
variance component only to about 1e-4 relative; the estimates are those of
the first accepted optimizer, reproducible for a given statsmodels version.

The variance of the fixed effects is the model-based one (``vcov`` iid);
t inference uses N-K degrees of freedom.
"""

from __future__ import annotations

import math
import warnings as _warnings
from typing import Any, List, Mapping, Sequence

import numpy as np

from analysis.ols import EngineError, Fit


def fit_mixedlm(
    y: np.ndarray,
    X: np.ndarray,
    names: Sequence[str],
    groups: np.ndarray,
    conventions: Mapping[str, Any],
) -> Fit:
    import statsmodels.api as sm

    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    n, k = X.shape
    if n == 0:
        raise EngineError("no observations")
    if k == 0:
        raise EngineError("no regressors left to estimate")
    if n <= k:
        raise EngineError(f"{n} observations for {k} parameters")
    if len(set(groups.tolist())) < 2:
        raise EngineError("a random intercept needs at least 2 groups")
    sd_y = float(np.std(y, ddof=1)) if n > 1 else 0.0
    sd_y = sd_y or 1.0
    ratio = float(conventions["mixedlm_max_se_ratio"])
    reml = bool(conventions["reml"])
    model = sm.MixedLM(y, X, groups=groups)
    last = "failed"
    for method in conventions["mixedlm_optimizers"]:
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            try:
                res = model.fit(reml=reml, method=method)
            except Exception as exc:  # noqa: BLE001 - try the next optimizer
                last = f"{method}: failed ({type(exc).__name__})"
                continue
        beta = np.asarray(res.fe_params, dtype=float)
        vcov = np.asarray(res.cov_params(), dtype=float)[:k, :k]
        diag = np.diag(vcov)
        llf = float(res.llf)
        if not res.converged:
            last = f"{method}: did not converge"
            continue
        if not math.isfinite(llf) or not np.all(np.isfinite(diag)) or not np.all(diag > 0):
            last = f"{method}: stopped at a singular fit (log-likelihood {llf}, variance component on the boundary)"
            continue
        se = np.sqrt(diag)
        if se.max() > ratio * sd_y:
            last = f"{method}: a standard error exceeds {ratio:g} times the outcome's standard deviation"
            continue
        notes: List[str] = sorted({str(w.message).splitlines()[0][:200] for w in caught})
        re_var = float(np.asarray(res.cov_re)[0, 0])
        fit = Fit(
            names=list(names),
            beta=beta,
            vcov=vcov,
            n=n,
            k=k,
            df_resid=n - k,
            rank=k,
            vcov_type="iid",
            ssc="model",
            df_t=n - k,
            warnings=[f"mixedlm ({method}): {note}" for note in notes],
            k_ssc=k,
            converged=True,
            extra={
                "optimizer": method,
                "reml": reml,
                "random_intercept_variance": re_var,
                "residual_variance": float(res.scale),
                "loglik": llf,
                "groups": int(len(set(groups.tolist()))),
            },
        )
        return fit
    raise EngineError(f"mixedlm: no optimizer gave an accepted fit (last: {last})")
