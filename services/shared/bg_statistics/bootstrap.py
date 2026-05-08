"""Bootstrap confidence intervals."""

from typing import Callable, List, Optional, Tuple

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def bootstrap_ci(
    values: List[float],
    statistic: Callable[[List[float]], float] = None,
    n_iterations: int = 1000,
    confidence: float = 0.95,
    seed: Optional[int] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Bootstrap confidence interval for a sample statistic (default: mean).

    Returns (lower_bound, upper_bound) at the given confidence level. Returns
    (None, None) when there's insufficient data or numpy is missing.
    """
    if not NUMPY_AVAILABLE or len(values) < 2:
        return (None, None)

    if statistic is None:
        statistic = lambda x: float(np.mean(x))  # noqa: E731

    rng = np.random.default_rng(seed)
    n = len(values)
    arr = np.asarray(values)
    samples = []
    for _ in range(n_iterations):
        idx = rng.integers(0, n, size=n)
        samples.append(statistic(arr[idx].tolist()))

    alpha = (1 - confidence) / 2
    lower = float(np.quantile(samples, alpha))
    upper = float(np.quantile(samples, 1 - alpha))
    return (round(lower, 4), round(upper, 4))
