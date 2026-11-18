"""Multiplicity adjustments over declared families of tests.

The arithmetic equals ``statsmodels.stats.multitest.multipletests`` for
``holm``, ``bonferroni`` and ``fdr_bh`` (same operations in the same order,
so the adjusted p-values agree to the last bit for the same inputs).
Benjamini-Hochberg controls the false discovery rate and is accepted only in
families marked exploratory.

Missing p-values (a contrast without a finite variance) are skipped by
default: they are not tests and do not count towards the family size. With
``missing="count"`` they count as tests that cannot reject (Holm and
Bonferroni use the full member count ``m``), which is what
``multipletests`` does when it is handed NaN p-values; their adjusted value
stays missing.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

import numpy as np

METHODS = ("holm", "bonferroni", "bh")


def adjust(
    pvalues: Sequence[Optional[float]], method: str, missing: str = "skip"
) -> List[Optional[float]]:
    """Adjusted p-values, ``None`` where the input is missing."""
    if method not in METHODS:
        raise ValueError(f"unknown adjustment {method!r}")
    if missing not in ("skip", "count"):
        raise ValueError(f"unknown missing-p policy {missing!r}")
    if missing == "count" and method == "bh":
        raise ValueError("missing='count' is defined for holm and bonferroni only")
    idx = [i for i, p in enumerate(pvalues) if p is not None and not math.isnan(p)]
    out: List[Optional[float]] = [None] * len(pvalues)
    if not idx:
        return out
    p = np.array([float(pvalues[i]) for i in idx])
    k = len(p)
    m = len(pvalues) if missing == "count" else k
    if method == "bonferroni":
        adj = np.minimum(p * float(m), 1.0)
    else:
        order = np.argsort(p)
        sorted_p = p[order]
        if method == "holm":
            raw = sorted_p * np.arange(m, m - k, -1)
            corrected = np.maximum.accumulate(raw)
        else:
            ecdf = np.arange(1, k + 1) / float(k)
            raw = sorted_p / ecdf
            corrected = np.minimum.accumulate(raw[::-1])[::-1]
        corrected = np.where(corrected > 1, 1.0, corrected)
        adj = np.empty(k)
        adj[order] = corrected
    for i, value in zip(idx, adj):
        out[i] = float(value)
    return out
