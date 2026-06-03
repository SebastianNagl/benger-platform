"""Shared statistical helpers for the ARR paper scripts.

Thin scipy wrappers around the rank/MAE helpers that were previously copied
across compute_agreement.py, derive_inter_judge_agreement.py,
derive_grundprinzipien_summary.py and derive_zjs_summary.py. They preserve the
`None`-on-too-few-pairs contract the manuscript prose relies on, so callers can
swap `from _stats import pearson, spearman, mae` for the local copy without
changing downstream serialisation.

`welford_update` is also shared: a single-pass online (mean, variance)
accumulator used by the ZJS / Grundprinzipien streams where the input is too
large to buffer.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats


def _clean(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None, None
    a = np.asarray([p[0] for p in pairs], dtype=float)
    b = np.asarray([p[1] for p in pairs], dtype=float)
    return a, b


def pearson(xs, ys):
    a, b = _clean(xs, ys)
    if a is None:
        return None
    r = stats.pearsonr(a, b).statistic
    return None if not math.isfinite(r) else float(r)


def spearman(xs, ys):
    a, b = _clean(xs, ys)
    if a is None:
        return None
    r = stats.spearmanr(a, b).statistic
    return None if not math.isfinite(r) else float(r)


def kendall_tau(xs, ys):
    a, b = _clean(xs, ys)
    if a is None:
        return None
    r = stats.kendalltau(a, b).statistic
    return None if not math.isfinite(r) else float(r)


def mae(xs, ys):
    a, b = _clean(xs, ys)
    return None if a is None else float(np.mean(np.abs(a - b)))


def welford_update(state, value):
    """In-place online (n, mean, M2) update; sample variance is M2/(n-1).

    `state` is a mutable [n, mean, M2] list. `None` is silently skipped so
    streaming callers don't need to filter upstream.
    """
    if value is None:
        return
    v = float(value)
    state[0] += 1
    delta = v - state[1]
    state[1] += delta / state[0]
    state[2] += delta * (v - state[1])
