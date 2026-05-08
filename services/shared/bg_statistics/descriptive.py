"""Descriptive statistics: mean, stddev, variance, confidence interval."""

from typing import List, Optional, Tuple

try:
    import numpy as np
    from scipy import stats as scipy_stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(sum(values) / len(values))


def variance(values: List[float], ddof: int = 1) -> Optional[float]:
    n = len(values)
    if n <= ddof:
        return None
    if SCIPY_AVAILABLE:
        return float(np.var(values, ddof=ddof))
    m = sum(values) / n
    return sum((v - m) ** 2 for v in values) / (n - ddof)


def stddev(values: List[float], ddof: int = 1) -> Optional[float]:
    v = variance(values, ddof=ddof)
    if v is None:
        return None
    return float(v ** 0.5)


def confidence_interval(
    values: List[float], confidence: float = 0.95
) -> Tuple[Optional[float], Optional[float], int]:
    """
    Confidence interval of the mean using t-distribution.

    Returns (lower_bound, upper_bound, sample_count). Bounds are None when n<2
    or scipy is unavailable.
    """
    n = len(values)
    if not SCIPY_AVAILABLE or n < 2:
        return (None, None, n)

    m = float(np.mean(values))
    se = float(scipy_stats.sem(values))
    alpha = 1 - confidence
    t_critical = float(scipy_stats.t.ppf(1 - alpha / 2, n - 1))
    margin = t_critical * se
    return (round(m - margin, 4), round(m + margin, 4), n)
