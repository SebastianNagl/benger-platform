"""Estimators over an analysis frame.

``fe_ols``
    OLS of ``outcome`` on ``terms`` with optional fixed effects. ``method:
    within`` absorbs each fixed-effect set (a column or a combination of
    columns, e.g. unit x system) by subtracting group means; ``dummies``
    adds an intercept and one dummy per non-first level of every set. Terms
    are numeric columns, dummy codings ``{"dummies": F, "reference": R}``
    (columns ``F[level]``; with ``"by": G`` one column per ``F[level]:G[g]``,
    the levels absent from the sample left out), or products ``{"interact":
    [t1, t2]}`` (columns ``a:b``).
``mean_rate``
    The mean of ``outcome`` (an intercept-only OLS, parameter ``(mean)``):
    with the default iid variance its SE is ``sd(ddof=1) / sqrt(n)``.
``paired_within``
    Within-pair differences: for every pair group (``pair_by``, e.g. unit x
    system) the treated rows' outcome minus the mean outcome of the group's
    reference rows, averaged by an intercept-only OLS (parameter
    ``(difference)``).

Rows with a missing outcome, regressor, dummy factor, fixed-effect key or
cluster key are dropped before fitting (listwise), and their count is
reported. A within-transformed column whose largest value is below
:data:`ZERO_TOLERANCE` times its largest raw value is set to exactly zero
(the fixed effects absorb it; what is left is rounding). With
``drop_zero_columns`` a regressor that is zero after absorption is dropped
and named in the fit (contrasts on it are then not estimable); an outcome
that is zero gives a degenerate fit with estimate 0 and variance 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np

from analysis.expression import ExpressionError, parse_expression
from analysis.measures import as_text
from analysis.ols import EngineError, Fit, demean, group_codes, ols

#: Relative size below which a within-transformed column counts as absorbed.
ZERO_TOLERANCE = 1e-12


@dataclass
class ScopedFit:
    estimand_id: str
    scope: str
    scope_values: Dict[str, Any]
    fit: Optional[Fit] = None
    error: Optional[str] = None
    implied_zero: Set[str] = field(default_factory=set)
    rows: int = 0
    rows_dropped: int = 0
    iterations: int = 0

    def summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "estimand": self.estimand_id,
            "scope": self.scope,
            "rows": self.rows,
            "rows_dropped_missing": self.rows_dropped,
        }
        if self.error:
            out["error"] = self.error
        if self.fit is not None:
            out.update(
                n=self.fit.n,
                k=self.fit.k,
                k_ssc=self.fit.k_ssc,
                rank=self.fit.rank,
                parameters=list(self.fit.names),
                dropped=list(self.fit.dropped),
                n_clusters=self.fit.n_clusters,
                fe_levels=list(self.fit.fe_levels),
                fe_iterations=self.iterations,
                warnings=list(self.fit.warnings),
            )
            if self.fit.converged is not None:
                out.update(converged=self.fit.converged, iterations=self.fit.iterations)
            if self.fit.separated:
                out["separated"] = list(self.fit.separated)
            if self.fit.extra:
                out.update({k: v for k, v in self.fit.extra.items() if k not in out})
        return out


def frame_columns(frame) -> Dict[str, np.ndarray]:
    """name -> numpy array (object for text, float/int otherwise)."""
    out = {}
    for name in frame.columns:
        values = frame[name].to_numpy()
        if values.dtype != object and str(frame[name].dtype) in ("str", "string"):
            values = np.array([None if v is None or v != v else v for v in values], dtype=object)
        out[name] = values
    return out


def truthy_mask(
    columns: Mapping[str, np.ndarray],
    n: int,
    text: Optional[str],
    where: str,
    warnings: Optional[List[str]] = None,
) -> np.ndarray:
    """Rows where the condition ``text`` is true. Number texts that
    ``number()`` set to missing for an ambiguous separator are reported in
    ``warnings`` (when given)."""
    if not text:
        return np.ones(n, dtype=bool)
    ambiguous: List[str] = []
    try:
        expr = parse_expression(text)
        missing = sorted(name for name in expr.names if name not in columns)
        if missing:
            raise EngineError(f"{where}: unknown column(s) {', '.join(missing)}")
        kind, arr = expr.evaluate(columns, n, ambiguous)
    except ExpressionError as exc:
        raise EngineError(f"{where}: {exc}") from None
    if ambiguous and warnings is not None:
        warnings.append(f"{where}: {len(ambiguous)} number text(s) with an ambiguous separator set to missing")
    if kind != "num":
        raise EngineError(f"{where}: a filter must be a condition, not text")
    return (arr != 0) & ~np.isnan(arr)


def _is_missing(values: np.ndarray) -> np.ndarray:
    if values.dtype == object:
        return np.fromiter(
            (v is None or (isinstance(v, float) and math.isnan(v)) for v in values),
            dtype=bool,
            count=len(values),
        )
    if np.issubdtype(values.dtype, np.integer):
        return np.zeros(len(values), dtype=bool)
    return np.isnan(values.astype(float))


def _column(columns: Mapping[str, np.ndarray], name: str, where: str) -> np.ndarray:
    if name not in columns:
        raise EngineError(f"{where}: unknown column {name!r}")
    return columns[name]


def _numeric(columns, name: str, where: str) -> np.ndarray:
    values = _column(columns, name, where)
    if values.dtype == object:
        raise EngineError(f"{where}: {name!r} is text; use a dummy coding or a measure")
    return values.astype(float)


def _keys(columns, spec: Any, where: str) -> List[np.ndarray]:
    names = [spec] if isinstance(spec, str) else list(spec)
    return [_column(columns, c, where) for c in names]


def _term_inputs(term: Any) -> Tuple[List[str], List[str]]:
    """(numeric columns, factor columns) a term reads."""
    if isinstance(term, str):
        return [term], []
    if "dummies" in term:
        return [], [term["dummies"]] + ([term["by"]] if term.get("by") else [])
    num: List[str] = []
    fac: List[str] = []
    for sub in term["interact"]:
        a, b = _term_inputs(sub)
        num += a
        fac += b
    return num, fac


def _levels(values: np.ndarray, declared: Optional[Sequence[Any]]) -> List[Any]:
    if declared is not None:
        return list(declared)
    present = {v for v in values.tolist() if v is not None and not (isinstance(v, float) and math.isnan(v))}
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in present):
        return sorted(present)
    return sorted(present, key=lambda v: as_text(v) or "")


def _label(v: Any) -> str:
    return as_text(v) if not isinstance(v, str) else v


def _match(values: np.ndarray, level: Any) -> np.ndarray:
    if values.dtype == object:
        lv = level if isinstance(level, str) else as_text(level)
        return np.fromiter((v == lv for v in values), dtype=bool, count=len(values))
    try:
        target = float(level)
    except (TypeError, ValueError):
        return np.zeros(len(values), dtype=bool)
    return values.astype(float) == target


def expand_term(
    columns, term: Any, where: str, keep_absent: bool = False, references: Optional[Dict[str, str]] = None
) -> Tuple[List[str], List[np.ndarray], Set[str], List[str]]:
    """(names, columns, implied-zero names, absent names) of one term on the
    sample. Absent names are dummy combinations with no row in the sample;
    with ``keep_absent`` they are expanded like the others (all-zero
    columns), which the counterfactual designs of marginal effects need.
    ``references``, when given, receives the reference level of every dummy
    coding (factor -> level label)."""
    if isinstance(term, str):
        return [term], [_numeric(columns, term, where)], set(), []
    if "dummies" in term:
        values = _column(columns, term["dummies"], where)
        levels = _levels(values, term.get("levels"))
        if not levels:
            raise EngineError(f"{where}: {term['dummies']!r} has no levels in the sample")
        ref = term.get("reference", levels[0])
        ref_label = _label(ref)
        factor = term["dummies"]
        if references is not None:
            references[factor] = ref_label
        names: List[str] = []
        cols: List[np.ndarray] = []
        implied: Set[str] = set()
        absent: List[str] = []
        if term.get("by"):
            by_values = _column(columns, term["by"], where)
            by_levels = _levels(by_values, term.get("_by_levels"))
            for lv in levels:
                for g in by_levels:
                    name = f"{factor}[{_label(lv)}]:{term['by']}[{_label(g)}]"
                    if _label(lv) == ref_label:
                        implied.add(name)
                        continue
                    col = (_match(values, lv) & _match(by_values, g)).astype(float)
                    if keep_absent or col.sum() > 0:
                        names.append(name)
                        cols.append(col)
                    else:
                        absent.append(name)
        else:
            implied.add(f"{factor}[{ref_label}]")
            for lv in levels:
                if _label(lv) == ref_label:
                    continue
                names.append(f"{factor}[{_label(lv)}]")
                cols.append(_match(values, lv).astype(float))
        return names, cols, implied, absent
    names = [""]
    cols = [None]
    implied: Set[str] = set()
    absent: List[str] = []
    for sub in term["interact"]:
        sub_names, sub_cols, sub_implied, sub_absent = expand_term(columns, sub, where, keep_absent, references)
        new_names, new_cols = [], []
        for n0 in names:
            for n1 in sub_absent:
                absent.append(n1 if not n0 else f"{n0}:{n1}")
        for n0, c0 in zip(names, cols):
            for n1, c1 in zip(sub_names, sub_cols):
                new_names.append(n1 if not n0 else f"{n0}:{n1}")
                new_cols.append(c1 if c0 is None else c0 * c1)
            for n1 in sub_implied:
                implied.add(n1 if not n0 else f"{n0}:{n1}")
        names, cols = new_names, new_cols
    return names, cols, implied, absent


def _scope_slices(columns, n: int, scope: Any, base: np.ndarray, where: str):
    """[(label, values, mask)] for a scope over the rows in ``base``."""
    if scope == "pooled":
        return [("pooled", {}, base)]
    by = list(scope["by"])
    keys = [_column(columns, c, where) for c in by]
    missing = np.zeros(n, dtype=bool)
    for k in keys:
        missing |= _is_missing(k)
    rows = np.flatnonzero(base & ~missing)
    combos: Dict[Tuple, List[int]] = {}
    for i in rows:
        combos.setdefault(tuple(k[i] for k in keys), []).append(i)

    def sort_key(combo):
        return tuple((0, v, "") if isinstance(v, (int, float)) else (1, 0, str(v)) for v in combo)

    out = []
    for combo in sorted(combos, key=sort_key):
        mask = np.zeros(n, dtype=bool)
        mask[combos[combo]] = True
        values = {c: (v.item() if hasattr(v, "item") else v) for c, v in zip(by, combo)}
        label = "|".join(f"{c}={_label(v)}" for c, v in values.items())
        out.append((label, values, mask))
    return out


def _cluster_codes(columns, vcov: Mapping[str, Any], idx: np.ndarray, where: str) -> Optional[List[np.ndarray]]:
    if vcov.get("type") != "cluster":
        return None
    out = []
    for dim in vcov["by"]:
        keys = [k[idx] for k in _keys(columns, dim, where)]
        codes, _ = group_codes(keys)
        out.append(codes)
    return out


def _required_missing(columns, n: int, numeric: Sequence[str], keys: Sequence[str], where: str) -> np.ndarray:
    miss = np.zeros(n, dtype=bool)
    for name in numeric:
        miss |= np.isnan(_numeric(columns, name, where))
    for name in keys:
        miss |= _is_missing(_column(columns, name, where))
    return miss


def _vcov_keys(vcov: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for dim in vcov.get("by") or []:
        out += [dim] if isinstance(dim, str) else list(dim)
    return out


def fit_fe_ols(columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str):
    conv = est["conventions"]
    outcome = est["outcome"]
    numeric = [outcome]
    factors: List[str] = []
    for term in est["terms"]:
        a, b = _term_inputs(term)
        numeric += a
        factors += b
    fes = [list(fe) for fe in est.get("fixed_effects") or []]
    keys = factors + [c for fe in fes for c in fe] + _vcov_keys(est["vcov"])
    miss = _required_missing(columns, n, numeric, keys, where)
    use = mask & ~miss
    dropped_rows = int((mask & miss).sum())
    idx = np.flatnonzero(use)
    sub = {name: arr[idx] for name, arr in columns.items()}
    names: List[str] = []
    cols: List[np.ndarray] = []
    implied: Set[str] = set()
    absent: List[str] = []
    references: Dict[str, str] = {}
    for term in est["terms"]:
        t_names, t_cols, t_implied, t_absent = expand_term(sub, term, where, references=references)
        names += t_names
        cols += t_cols
        implied |= t_implied
        absent += t_absent
    if len(set(names)) != len(names):
        dup = sorted({x for x in names if names.count(x) > 1})
        raise EngineError(f"{where}: terms repeat the regressor(s) {', '.join(dup)}")
    y = sub[outcome].astype(float)
    X = np.column_stack(cols) if cols else np.empty((len(idx), 0))
    fe_codes = []
    fe_levels = []
    for fe in fes:
        codes, g = group_codes([sub[c] for c in fe])
        fe_codes.append(codes)
        fe_levels.append(g)
    iterations = 0
    if fes and est.get("method", "within") == "within":
        data = np.column_stack([y, X]) if X.size else y[:, None]
        scale = np.max(np.abs(data), axis=0) if len(data) else np.zeros(data.shape[1])
        data, iterations = demean(
            data, fe_codes, tolerance=float(conv["fe_tolerance"]), max_iter=int(conv["fe_max_iter"])
        )
        # A column that the fixed effects absorb entirely is zero up to
        # rounding; make it exactly zero so a constant outcome gives a
        # degenerate fit (estimate 0, variance 0) instead of rounding noise,
        # and an absorbed regressor is dropped instead of fitted on noise.
        if len(data):
            residual = np.max(np.abs(data), axis=0)
            absorbed = residual <= ZERO_TOLERANCE * np.maximum(scale, 1.0)
            data[:, absorbed] = 0.0
        y, X = data[:, 0], data[:, 1:]
    elif fes:
        dummy_cols = [np.ones(len(idx))]
        for codes, g in zip(fe_codes, fe_levels):
            for level in range(1, g):
                dummy_cols.append((codes == level).astype(float))
        X = np.column_stack([X] + dummy_cols) if X.size else np.column_stack(dummy_cols)
        names = names + ["(intercept)"] + [f"(fe{i})" for i in range(len(dummy_cols) - 1)]
    elif est.get("intercept", True):
        X = np.column_stack([np.ones(len(idx)), X]) if X.size else np.ones((len(idx), 1))
        names = ["(intercept)"] + names
    dropped: List[str] = list(absent)
    if conv.get("drop_zero_columns", True) and X.size:
        keep = [j for j in range(X.shape[1]) if np.abs(X[:, j]).sum() > 0]
        dropped += [names[j] for j in range(X.shape[1]) if j not in keep]
        X = X[:, keep]
        names = [names[j] for j in keep]
    clusters = _cluster_codes(sub, est["vcov"], np.arange(len(idx)), where)
    fit = ols(
        y,
        X,
        names,
        vcov_type=est["vcov"]["type"],
        clusters=clusters,
        ssc=conv["ssc"],
        fe_codes=fe_codes if est.get("method", "within") == "within" else (),
        fe_levels=fe_levels if est.get("method", "within") == "within" else (),
    )
    fit.dropped = dropped
    fit.extra["references"] = references
    zero = [nm for nm in dropped if nm not in absent]
    if zero:
        fit.warnings.append("dropped identically-zero regressor(s): " + ", ".join(zero))
    if absent:
        fit.warnings.append("dummy combination(s) without rows: " + ", ".join(absent))
    return fit, implied, len(idx), dropped_rows, iterations


def fit_mean(columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str):
    outcome = est["outcome"]
    miss = _required_missing(columns, n, [outcome], _vcov_keys(est["vcov"]), where)
    use = mask & ~miss
    idx = np.flatnonzero(use)
    sub = {name: arr[idx] for name, arr in columns.items()}
    y = sub[outcome].astype(float)
    clusters = _cluster_codes(sub, est["vcov"], np.arange(len(idx)), where)
    fit = ols(
        y,
        np.ones((len(idx), 1)),
        ["(mean)"],
        vcov_type=est["vcov"]["type"],
        clusters=clusters,
        ssc=est["conventions"]["ssc"],
    )
    return fit, set(), len(idx), int((mask & miss).sum()), 0


def fit_paired(
    columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str, *, treated_subset: np.ndarray
):
    outcome = est["outcome"]
    treat = est["treatment"]
    factor = _column(columns, treat["factor"], where)
    pair_by = list(est["pair_by"])
    y_all = _numeric(columns, outcome, where)
    key_miss = np.zeros(n, dtype=bool)
    for c in pair_by + _vcov_keys(est["vcov"]):
        key_miss |= _is_missing(_column(columns, c, where))
    ref_rows = mask & _match(factor, treat["reference"]) & ~np.isnan(y_all) & ~key_miss
    treated = mask & _match(factor, treat["level"]) & ~key_miss & treated_subset
    pair_keys = [_column(columns, c, where) for c in pair_by]
    sums: Dict[Tuple, List[float]] = {}
    for i in np.flatnonzero(ref_rows):
        sums.setdefault(tuple(k[i] for k in pair_keys), []).append(y_all[i])
    base = {}
    import pandas as pd

    for key, vals in sums.items():
        base[key] = float(pd.Series(vals).mean())
    rows = []
    diffs = []
    for i in np.flatnonzero(treated):
        b = base.get(tuple(k[i] for k in pair_keys))
        if b is None or math.isnan(y_all[i]):
            continue
        rows.append(i)
        diffs.append(y_all[i] - b)
    idx = np.array(rows, dtype=np.int64)
    min_n = int(est.get("min_n", 1))
    if len(idx) < min_n:
        raise EngineError(f"{where}: {len(idx)} pairs, fewer than min_n = {min_n}", n_obs=len(idx))
    sub = {name: arr[idx] for name, arr in columns.items()}
    clusters = _cluster_codes(sub, est["vcov"], np.arange(len(idx)), where)
    fit = ols(
        np.array(diffs, dtype=float),
        np.ones((len(idx), 1)),
        ["(difference)"],
        vcov_type=est["vcov"]["type"],
        clusters=clusters,
        ssc=est["conventions"]["ssc"],
    )
    return fit, set(), len(idx), int((treated & mask).sum()) - len(idx), 0


# --------------------------------------------------------------------------
# Shared design building for the likelihood estimators
# --------------------------------------------------------------------------


def _freeze_term(sub, term: Any) -> Any:
    """``term`` with the levels of every dummy coding fixed to the ones of
    the estimation sample, so a counterfactual design (one column set to a
    single value) expands to the same parameter names."""
    if isinstance(term, str):
        return term
    if "dummies" in term:
        out = dict(term)
        out["levels"] = _levels(sub[term["dummies"]], term.get("levels"))
        if term.get("by"):
            out["_by_levels"] = _levels(sub[term["by"]], None)
        return out
    return {"interact": [_freeze_term(sub, t) for t in term["interact"]]}


def _expand_terms(
    sub, terms: Sequence[Any], where: str, keep_absent: bool = False, references: Optional[Dict[str, str]] = None
):
    names: List[str] = []
    cols: List[np.ndarray] = []
    implied: Set[str] = set()
    absent: List[str] = []
    for term in terms:
        t_names, t_cols, t_implied, t_absent = expand_term(sub, term, where, keep_absent, references)
        names += t_names
        cols += t_cols
        implied |= t_implied
        absent += t_absent
    if len(set(names)) != len(names):
        dup = sorted({x for x in names if names.count(x) > 1})
        raise EngineError(f"{where}: terms repeat the regressor(s) {', '.join(dup)}")
    return names, cols, implied, absent


def _fe_dummies(sub, fes, m: int):
    """Intercept and one dummy per non-first level of every fixed-effect set
    (the ``dummies`` method of fe_ols)."""
    cols = [np.ones(m)]
    for fe in fes:
        codes, g = group_codes([sub[c] for c in fe])
        for level in range(1, g):
            cols.append((codes == level).astype(float))
    names = ["(intercept)"] + [f"(fe{i})" for i in range(len(cols) - 1)]
    return names, cols


def _drop_zero(X: np.ndarray, names: List[str], conv) -> Tuple[np.ndarray, List[str], List[str]]:
    if not conv.get("drop_zero_columns", True) or not X.size:
        return X, names, []
    keep = [j for j in range(X.shape[1]) if np.abs(X[:, j]).sum() > 0]
    dropped = [names[j] for j in range(X.shape[1]) if j not in keep]
    return X[:, keep], [names[j] for j in keep], dropped


def _informative(y: np.ndarray, sub, fes, use: np.ndarray) -> np.ndarray:
    """Rows of fixed-effect groups whose outcome varies (repeated over the
    sets until nothing changes): a group with a constant binary outcome has
    an infinite effect and carries no information on the other parameters."""
    keep = use.copy()
    changed = True
    while changed and keep.any():
        changed = False
        for fe in fes:
            idx = np.flatnonzero(keep)
            codes, g = group_codes([sub[c][idx] for c in fe])
            lo = np.full(g, np.inf)
            hi = np.full(g, -np.inf)
            np.minimum.at(lo, codes, y[idx])
            np.maximum.at(hi, codes, y[idx])
            flat = (hi - lo)[codes] <= 0
            if flat.any():
                keep[idx[flat]] = False
                changed = True
    return keep


class LogitDesign:
    """The design of a logit's estimation sample, rebuilt with one column set
    to a value for average marginal effects."""

    def __init__(self, sub, terms, names: List[str], fixed: Mapping[str, np.ndarray], term_inputs, fe_inputs, where):
        self.sub = sub
        self.terms = terms
        self.names = names
        self.fixed = fixed
        self.term_inputs = set(term_inputs)
        self.fe_inputs = set(fe_inputs)
        self.where = where

    def counterfactual(self, column: str, value: Any) -> np.ndarray:
        if column in self.fe_inputs:
            raise EngineError(f"{self.where}: {column!r} is a fixed-effect column; a margin cannot set it")
        if column not in self.term_inputs:
            raise EngineError(f"{self.where}: no term reads {column!r}")
        numeric, _ = _ml_inputs(None, self.terms)
        if column not in numeric and not _match(self.sub[column], value).any():
            raise EngineError(f"{self.where}: {column!r} has no level {value!r} in the estimation sample")
        m = len(next(iter(self.sub.values())))
        cols = dict(self.sub)
        if cols[column].dtype == object:
            cols[column] = np.array([value if isinstance(value, str) else as_text(value)] * m, dtype=object)
        else:
            try:
                cols[column] = np.full(m, float(value))
            except (TypeError, ValueError):
                raise EngineError(f"{self.where}: {column!r} is numeric; {value!r} is not a number") from None
        t_names, t_cols, _, _ = _expand_terms(cols, self.terms, self.where, keep_absent=True)
        by_name = dict(zip(t_names, t_cols))
        out = np.zeros((m, len(self.names)))
        for j, name in enumerate(self.names):
            if name in self.fixed:
                out[:, j] = self.fixed[name]
            elif name in by_name:
                out[:, j] = by_name[name]
        return out


def _ml_inputs(est, terms) -> Tuple[List[str], List[str]]:
    numeric: List[str] = []
    factors: List[str] = []
    for term in terms:
        a, b = _term_inputs(term)
        numeric += a
        factors += b
    return numeric, factors


def _logit_fit(y, X, names, sub, est, conv, where, clusters):
    from analysis.ml import fit_logit, sandwich

    result = fit_logit(y, X, tolerance=float(conv["ml_tolerance"]), max_iter=int(conv["ml_max_iter"]))
    fit = sandwich(
        result, names, vcov_type=est["vcov"]["type"], clusters=clusters, ssc=conv["ssc"], estimator=est["estimator"]
    )
    bound = float(conv["separation_bound"])
    se = np.sqrt(np.clip(np.diag(fit.vcov), 0, None)) if fit.vcov.size else np.zeros(0)
    fit.separated = [
        name
        for j, name in enumerate(names)
        if not name.startswith("(fe")
        and (abs(fit.beta[j]) > bound or not np.isfinite(se[j]) or se[j] < 1e-8)
    ]
    if fit.separated:
        fit.warnings.append("separation (no p-values): " + ", ".join(fit.separated))
    return fit


def _rows_used(columns, n, est, mask, numeric, keys, where):
    miss = _required_missing(columns, n, numeric, keys, where)
    use = mask & ~miss
    return use, int((mask & miss).sum())


def fit_logit_estimand(columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str):
    conv = est["conventions"]
    terms = est["terms"]
    numeric, factors = _ml_inputs(est, terms)
    fes = [list(fe) for fe in est.get("fixed_effects") or []]
    fe_cols = [c for fe in fes for c in fe]
    use, dropped_rows = _rows_used(columns, n, est, mask, [est["outcome"]] + numeric, factors + fe_cols + _vcov_keys(est["vcov"]), where)
    y_all = _numeric(columns, est["outcome"], where)
    uninformative = 0
    if fes and conv.get("informative_only", True):
        keep = _informative(y_all, columns, fes, use)
        uninformative = int((use & ~keep).sum())
        use = keep
    idx = np.flatnonzero(use)
    sub = {name: arr[idx] for name, arr in columns.items()}
    frozen = [_freeze_term(sub, t) for t in terms]
    references: Dict[str, str] = {}
    names, cols, implied, absent = _expand_terms(sub, frozen, where, references=references)
    m = len(idx)
    fixed: Dict[str, np.ndarray] = {}
    if fes or est.get("intercept", True):
        fe_names, fe_cols_arr = _fe_dummies(sub, fes, m) if fes else (["(intercept)"], [np.ones(m)])
        if fes:
            names, cols = names + fe_names, cols + fe_cols_arr
        else:
            names, cols = fe_names + names, fe_cols_arr + cols
        fixed = dict(zip(fe_names, fe_cols_arr))
    X = np.column_stack(cols) if cols else np.empty((m, 0))
    X, names, zero = _drop_zero(X, names, conv)
    clusters = _cluster_codes(sub, est["vcov"], np.arange(m), where)
    fit = _logit_fit(sub[est["outcome"]].astype(float), X, names, sub, est, conv, where, clusters)
    fit.dropped = list(absent) + zero
    if zero:
        fit.warnings.append("dropped identically-zero regressor(s): " + ", ".join(zero))
    if absent:
        fit.warnings.append("dummy combination(s) without rows: " + ", ".join(absent))
    if uninformative:
        fit.warnings.append(f"{uninformative} row(s) of fixed-effect groups without outcome variation left out")
    fit.extra["rows_uninformative"] = uninformative
    fit.extra["references"] = references
    fit.design = LogitDesign(sub, frozen, names, fixed, numeric + factors, fe_cols, where)
    return fit, implied, m, dropped_rows + uninformative, 0


def fit_bradley_terry(columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str):
    conv = est["conventions"]
    first, second = est["players"]
    terms = est.get("terms") or []
    numeric, factors = _ml_inputs(est, terms)
    fes = [list(fe) for fe in est.get("fixed_effects") or []]
    fe_cols = [c for fe in fes for c in fe]
    logit = est.get("link", "logit") == "logit"
    use, dropped_rows = _rows_used(
        columns, n, est, mask, [est["outcome"]] + numeric,
        [first, second] + factors + fe_cols + _vcov_keys(est["vcov"]), where,
    )
    outside = 0
    if est.get("levels") is not None:
        inside = np.ones(n, dtype=bool)
        for player in (first, second):
            values = _column(columns, player, where)
            known = np.zeros(n, dtype=bool)
            for lv in est["levels"]:
                known |= _match(values, lv)
            inside &= known
        outside = int((use & ~inside).sum())
        use = use & inside
    y_all = _numeric(columns, est["outcome"], where)
    uninformative = 0
    if logit and fes and conv.get("informative_only", True):
        keep = _informative(y_all, columns, fes, use)
        uninformative = int((use & ~keep).sum())
        use = keep
    idx = np.flatnonzero(use)
    sub = {name: arr[idx] for name, arr in columns.items()}
    m = len(idx)
    a, b = sub[first], sub[second]
    if est.get("levels") is not None:
        levels = [_label(v) for v in est["levels"]]
    else:
        levels = _levels(np.concatenate([a, b]) if m else np.array([], dtype=object), None)
        levels = [_label(v) for v in levels]
    ref = _label(est["reference"])
    if ref not in levels:
        raise EngineError(f"{where}: the reference player {ref!r} is not among the players", n_obs=m)
    names: List[str] = []
    cols: List[np.ndarray] = []
    for lv in levels:
        if lv == ref:
            continue
        names.append(f"strength[{lv}]")
        cols.append(_match(a, lv).astype(float) - _match(b, lv).astype(float))
    references: Dict[str, str] = {"strength": ref}
    t_names, t_cols, implied, absent = _expand_terms(sub, terms, where, references=references)
    names, cols = names + t_names, cols + t_cols
    implied = set(implied) | {f"strength[{ref}]"}
    if fes:
        fe_names, fe_arr = _fe_dummies(sub, fes, m)
        names, cols = names + fe_names, cols + fe_arr
    else:
        names, cols = ["(intercept)"] + names, [np.ones(m)] + cols
    X = np.column_stack(cols) if cols else np.empty((m, 0))
    X, names, zero = _drop_zero(X, names, conv)
    clusters = _cluster_codes(sub, est["vcov"], np.arange(m), where)
    y = sub[est["outcome"]].astype(float)
    if logit:
        fit = _logit_fit(y, X, names, sub, est, conv, where, clusters)
    else:
        fit = ols(y, X, names, vcov_type=est["vcov"]["type"], clusters=clusters, ssc=conv["ssc"])
    fit.dropped = list(absent) + zero
    if zero:
        fit.warnings.append("dropped identically-zero regressor(s): " + ", ".join(zero))
    if uninformative:
        fit.warnings.append(f"{uninformative} row(s) of fixed-effect groups without outcome variation left out")
        fit.extra["rows_uninformative"] = uninformative
    if outside:
        fit.warnings.append(f"{outside} row(s) with a player outside the declared levels left out")
    fit.extra["players"] = levels
    fit.extra["references"] = references
    fit.extra["players_are_systems"] = _are_systems(columns, levels)
    return fit, implied, m, dropped_rows + outside + uninformative, 0


def _are_systems(columns, levels: Sequence[str]) -> bool:
    """Whether every one of ``levels`` is a value of the frame's ``system``
    (or ``model_id``) column."""
    for column in ("system", "model_id"):
        if column in columns:
            values = {_label(v) for v in columns[column].tolist() if v is not None}
            if levels and set(levels) <= values:
                return True
    return False


def fit_mixedlm_estimand(columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str):
    from analysis.mixed import fit_mixedlm

    terms = est["terms"]
    numeric, factors = _ml_inputs(est, terms)
    groups = list(est["groups"])
    use, dropped_rows = _rows_used(columns, n, est, mask, [est["outcome"]] + numeric, factors + groups, where)
    idx = np.flatnonzero(use)
    sub = {name: arr[idx] for name, arr in columns.items()}
    m = len(idx)
    references: Dict[str, str] = {}
    names, cols, implied, absent = _expand_terms(sub, terms, where, references=references)
    if est.get("intercept", True):
        names, cols = ["(intercept)"] + names, [np.ones(m)] + cols
    X = np.column_stack(cols) if cols else np.empty((m, 0))
    X, names, zero = _drop_zero(X, names, est["conventions"])
    if len(groups) == 1:
        g = sub[groups[0]]
        g = g if g.dtype == object else np.array([_label(v.item() if hasattr(v, "item") else v) for v in g], dtype=object)
    else:
        g = np.array(
            ["|".join(_label(sub[c][i]) for c in groups) for i in range(m)], dtype=object
        )
    fit = fit_mixedlm(sub[est["outcome"]].astype(float), X, names, g, est["conventions"])
    fit.dropped = list(absent) + zero
    fit.extra["references"] = references
    if zero:
        fit.warnings.append("dropped identically-zero regressor(s): " + ", ".join(zero))
    return fit, implied, m, dropped_rows, 0


def _choice_sets(columns, n, est, mask, where):
    """Rows of the valid choice sets, grouped and ordered by choice."""
    keys = list(est["choice_set"])
    numeric, factors = _ml_inputs(est, est["terms"])
    miss_keys = np.zeros(n, dtype=bool)
    for c in keys:
        miss_keys |= _is_missing(_column(columns, c, where))
    cand = mask & ~miss_keys
    reg_miss = _required_missing(columns, n, numeric, factors + _vcov_keys(est["vcov"]), where)
    y = _numeric(columns, est["outcome"], where)
    idx = np.flatnonzero(cand)
    codes, g = group_codes([columns[c][idx] for c in keys]) if len(idx) else (np.zeros(0, dtype=np.int64), 0)
    members: List[List[int]] = [[] for _ in range(g)]
    for pos, code in enumerate(codes):
        members[code].append(int(idx[pos]))
    rank1 = est["estimator"] == "clogit_rank1"
    sets: List[List[int]] = []
    invalid = 0
    for rows in members:
        if len(rows) < 2 or reg_miss[rows].any():
            invalid += 1
            continue
        r = y[rows]
        if rank1:
            chosen = [i for i, v in zip(rows, r) if v == 1]
            if len(chosen) != 1:
                invalid += 1
                continue
            sets.append(chosen + [i for i in rows if i != chosen[0]])
        else:
            if np.isnan(r).any() or sorted(r.tolist()) != [float(i) for i in range(1, len(rows) + 1)]:
                invalid += 1
                continue
            sets.append([rows[j] for j in np.argsort(r, kind="stable")])
    return sets, invalid, int(mask.sum())


def fit_ranked_logit(columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str):
    from analysis.ml import ChoiceSets, fit_plackett_luce, sandwich

    conv = est["conventions"]
    sets, invalid, in_mask = _choice_sets(columns, n, est, mask, where)
    if not sets:
        raise EngineError(f"{where}: no valid choice set ({invalid} invalid)", n_obs=0)
    flat = [i for rows in sets for i in rows]
    idx = np.array(flat, dtype=np.int64)
    sub = {name: arr[idx] for name, arr in columns.items()}
    references: Dict[str, str] = {}
    names, cols, implied, absent = _expand_terms(sub, est["terms"], where, references=references)
    m = len(idx)
    X = np.column_stack(cols) if cols else np.empty((m, 0))
    set_of = np.repeat(np.arange(len(sets)), [len(r) for r in sets])
    # a regressor constant within every choice set cancels out of the likelihood
    if X.size:
        sums = np.zeros((len(sets), X.shape[1]))
        np.add.at(sums, set_of, X)
        sizes = np.bincount(set_of, minlength=len(sets)).astype(float)
        within = X - (sums / sizes[:, None])[set_of]
        scale = np.maximum(np.max(np.abs(X), axis=0), 1.0)
        constant = np.max(np.abs(within), axis=0) <= ZERO_TOLERANCE * scale
    else:
        constant = np.zeros(0, dtype=bool)
    keep = [j for j in range(len(names)) if not constant[j]]
    zero = [names[j] for j in range(len(names)) if constant[j]]
    if zero and not conv.get("drop_zero_columns", True):
        raise EngineError(f"{where}: regressor(s) constant within every choice set: {', '.join(zero)}")
    X = X[:, keep] if X.size else X
    names = [names[j] for j in keep]
    S = len(sets)
    M = max((len(r) for r in sets), default=0)
    k = len(names)
    Xo = np.zeros((S, M, k))
    valid = np.zeros((S, M), dtype=bool)
    stages = np.zeros(S, dtype=np.int64)
    max_stages = 1 if est["estimator"] == "clogit_rank1" else est.get("stages")
    pos = 0
    for s_i, rows in enumerate(sets):
        size = len(rows)
        Xo[s_i, :size, :] = X[pos : pos + size]
        valid[s_i, :size] = True
        stages[s_i] = size - 1 if max_stages is None else min(int(max_stages), size - 1)
        pos += size
    clusters = None
    if est["vcov"]["type"] == "cluster":
        clusters = []
        first_rows = np.array([rows[0] for rows in sets], dtype=np.int64)
        for dim in est["vcov"]["by"]:
            dim_cols = [dim] if isinstance(dim, str) else list(dim)
            for c in dim_cols:
                values = columns[c]
                for rows in sets:
                    if len({_label(values[i]) for i in rows}) > 1:
                        raise EngineError(f"{where}: the cluster column {c!r} varies within a choice set")
            codes, _ = group_codes([columns[c][first_rows] for c in dim_cols])
            clusters.append(codes)
    result = fit_plackett_luce(
        ChoiceSets(X=Xo, valid=valid, stages=stages),
        tolerance=float(conv["ml_tolerance"]),
        max_iter=int(conv["ml_max_iter"]),
    )
    fit = sandwich(
        result, names, vcov_type=est["vcov"]["type"], clusters=clusters, ssc=conv["ssc"], estimator=est["estimator"]
    )
    fit.dropped = list(absent) + zero
    if zero:
        fit.warnings.append("dropped regressor(s) constant within every choice set: " + ", ".join(zero))
    if invalid:
        fit.warnings.append(f"{invalid} choice set(s) without a valid ranking, a usable size or complete regressors left out")
    fit.extra.update(choice_sets=S, alternatives=m, choice_sets_invalid=invalid, references=references)
    return fit, implied, m, in_mask - m, 0


def fit_spearman(columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str):
    from scipy import stats

    y = _numeric(columns, est["outcome"], where)
    x = _numeric(columns, est["x"], where)
    use = mask & ~np.isnan(y) & ~np.isnan(x)
    m = int(use.sum())
    if m < 3:
        raise EngineError(f"{where}: {m} complete pairs, a rank correlation needs at least 3", n_obs=m)
    xs, ys = x[use], y[use]
    fit = Fit(
        names=["(rho)"], beta=np.array([math.nan]), vcov=np.full((1, 1), math.nan), n=m, k=1,
        df_resid=m - 2, rank=1, vcov_type="none", ssc="none", df_t=m - 2,
    )
    if np.all(xs == xs[0]) or np.all(ys == ys[0]):
        fit.extra = {"rho": None, "p_value": None, "constant_input": True}
        return fit, set(), m, int((mask & ~use).sum()), 0
    res = stats.spearmanr(xs, ys)
    rho = float(res.statistic)
    p = float(res.pvalue)
    t = rho * math.sqrt((m - 2) / (1.0 - rho * rho)) if abs(rho) < 1 else None
    fit.beta = np.array([rho])
    fit.extra = {"rho": rho, "p_value": p if math.isfinite(p) else None, "t": t}
    return fit, set(), m, int((mask & ~use).sum()), 0


ESTIMATORS = {
    "fe_ols": fit_fe_ols,
    "mean_rate": fit_mean,
    "paired_within": fit_paired,
    "logit": fit_logit_estimand,
    "bradley_terry": fit_bradley_terry,
    "mixedlm": fit_mixedlm_estimand,
    "plackett_luce": fit_ranked_logit,
    "clogit_rank1": fit_ranked_logit,
    "spearman": fit_spearman,
}


def fit_estimand(
    columns: Mapping[str, np.ndarray],
    n: int,
    est: Mapping[str, Any],
    base_mask: np.ndarray,
    where: str,
    warnings: Optional[List[str]] = None,
) -> List[ScopedFit]:
    """Fit ``est`` (normalized) once per scope; warnings of its subset and
    of a paired treatment's subset go to ``warnings`` (when given)."""
    mask = base_mask & truthy_mask(columns, n, est.get("subset"), f"{where}/subset", warnings)
    extra: Dict[str, Any] = {}
    if est["estimator"] == "paired_within":
        extra["treated_subset"] = truthy_mask(
            columns, n, est["treatment"].get("subset"), f"{where}/treatment/subset", warnings
        )
    out: List[ScopedFit] = []
    for scope in est["scopes"]:
        for label, values, smask in _scope_slices(columns, n, scope, mask, where):
            sf = ScopedFit(estimand_id=est["id"], scope=label, scope_values=values)
            try:
                fit, implied, rows, dropped, iterations = ESTIMATORS[est["estimator"]](
                    columns, n, est, smask, f"{where}[{label}]", **extra
                )
                sf.fit, sf.implied_zero, sf.rows, sf.rows_dropped, sf.iterations = (
                    fit,
                    implied,
                    rows,
                    dropped,
                    iterations,
                )
            except EngineError as exc:
                sf.error = str(exc)
                sf.rows = exc.n_obs if exc.n_obs is not None else int(smask.sum())
            out.append(sf)
    return out
