"""Correlation: Pearson, Spearman."""

from typing import List, Optional

try:
    import numpy as np
    from scipy import stats as scipy_stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def pearson(values_a: List[float], values_b: List[float]) -> Optional[float]:
    """Pearson correlation coefficient. Returns None if insufficient data or NaN."""
    if not SCIPY_AVAILABLE or len(values_a) < 3 or len(values_b) < 3:
        return None
    if len(values_a) != len(values_b):
        return None
    try:
        r, _ = scipy_stats.pearsonr(values_a, values_b)
        if np.isnan(r):
            return None
        return round(float(r), 4)
    except Exception:
        return None


def spearman(values_a: List[float], values_b: List[float]) -> Optional[float]:
    """Spearman rank correlation. Returns None if insufficient data or NaN."""
    if not SCIPY_AVAILABLE or len(values_a) < 3 or len(values_b) < 3:
        return None
    if len(values_a) != len(values_b):
        return None
    try:
        r, _ = scipy_stats.spearmanr(values_a, values_b)
        if np.isnan(r):
            return None
        return round(float(r), 4)
    except Exception:
        return None
