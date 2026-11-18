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


def expand_term(columns, term: Any, where: str) -> Tuple[List[str], List[np.ndarray], Set[str], List[str]]:
    """(names, columns, implied-zero names, absent names) of one term on the
    sample. Absent names are dummy combinations with no row in the sample."""
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
        names: List[str] = []
        cols: List[np.ndarray] = []
        implied: Set[str] = set()
        absent: List[str] = []
        if term.get("by"):
            by_values = _column(columns, term["by"], where)
            by_levels = _levels(by_values, None)
            for lv in levels:
                for g in by_levels:
                    name = f"{factor}[{_label(lv)}]:{term['by']}[{_label(g)}]"
                    if _label(lv) == ref_label:
                        implied.add(name)
                        continue
                    col = (_match(values, lv) & _match(by_values, g)).astype(float)
                    if col.sum() > 0:
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
        sub_names, sub_cols, sub_implied, sub_absent = expand_term(columns, sub, where)
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
    for term in est["terms"]:
        t_names, t_cols, t_implied, t_absent = expand_term(sub, term, where)
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


def fit_paired(columns, n: int, est: Mapping[str, Any], mask: np.ndarray, where: str):
    outcome = est["outcome"]
    treat = est["treatment"]
    factor = _column(columns, treat["factor"], where)
    pair_by = list(est["pair_by"])
    y_all = _numeric(columns, outcome, where)
    key_miss = np.zeros(n, dtype=bool)
    for c in pair_by + _vcov_keys(est["vcov"]):
        key_miss |= _is_missing(_column(columns, c, where))
    ref_rows = mask & _match(factor, treat["reference"]) & ~np.isnan(y_all) & ~key_miss
    treated = mask & _match(factor, treat["level"]) & ~key_miss
    subset_warnings: List[str] = []
    if treat.get("subset"):
        treated &= truthy_mask(columns, n, treat["subset"], f"{where}/treatment/subset", subset_warnings)
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
    fit.warnings.extend(subset_warnings)
    return fit, set(), len(idx), int((treated & mask).sum()) - len(idx), 0


ESTIMATORS = {"fe_ols": fit_fe_ols, "mean_rate": fit_mean, "paired_within": fit_paired}


def fit_estimand(
    columns: Mapping[str, np.ndarray],
    n: int,
    est: Mapping[str, Any],
    base_mask: np.ndarray,
    where: str,
    warnings: Optional[List[str]] = None,
) -> List[ScopedFit]:
    """Fit ``est`` (normalized) once per scope; warnings of its subset go to
    ``warnings`` (when given)."""
    mask = base_mask & truthy_mask(columns, n, est.get("subset"), f"{where}/subset", warnings)
    out: List[ScopedFit] = []
    for scope in est["scopes"]:
        for label, values, smask in _scope_slices(columns, n, scope, mask, where):
            sf = ScopedFit(estimand_id=est["id"], scope=label, scope_values=values)
            try:
                fit, implied, rows, dropped, iterations = ESTIMATORS[est["estimator"]](
                    columns, n, est, smask, f"{where}[{label}]"
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
