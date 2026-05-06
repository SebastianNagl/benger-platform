"""Effect-size measures: Cohen's d, Cliff's delta."""

from typing import Dict, List, Optional

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def _cohens_d_interpretation(abs_d: float) -> str:
    if abs_d >= 0.8:
        return "large"
    if abs_d >= 0.5:
        return "medium"
    if abs_d >= 0.2:
        return "small"
    return "negligible"


def cohens_d(values_a: List[float], values_b: List[float]) -> Dict[str, Optional[float]]:
    """
    Cohen's d effect size between two samples.

    Returns {"cohens_d": float|None, "interpretation": "negligible"|"small"|"medium"|"large"|None}.
    """
    if not NUMPY_AVAILABLE or len(values_a) < 2 or len(values_b) < 2:
        return {"cohens_d": None, "interpretation": None}

    mean_diff = float(np.mean(values_a) - np.mean(values_b))
    pooled_std = float(
        np.sqrt(
            (
                (len(values_a) - 1) * np.var(values_a, ddof=1)
                + (len(values_b) - 1) * np.var(values_b, ddof=1)
            )
            / (len(values_a) + len(values_b) - 2)
        )
    )

    if pooled_std == 0:
        return {"cohens_d": 0.0, "interpretation": "negligible"}

    d = mean_diff / pooled_std
    return {"cohens_d": round(d, 4), "interpretation": _cohens_d_interpretation(abs(d))}


def _cliffs_delta_interpretation(abs_delta: float) -> str:
    if abs_delta >= 0.474:
        return "large"
    if abs_delta >= 0.33:
        return "medium"
    if abs_delta >= 0.147:
        return "small"
    return "negligible"


def cliffs_delta(values_a: List[float], values_b: List[float]) -> Dict[str, Optional[float]]:
    """
    Cliff's delta — non-parametric effect size.

    Returns {"cliffs_delta": float|None, "interpretation": "negligible"|"small"|"medium"|"large"|None}.
    """
    if not values_a or not values_b:
        return {"cliffs_delta": None, "interpretation": None}

    greater = sum(1 for a in values_a for b in values_b if a > b)
    less = sum(1 for a in values_a for b in values_b if a < b)
    n = len(values_a) * len(values_b)

    if n == 0:
        return {"cliffs_delta": None, "interpretation": None}

    delta = (greater - less) / n
    return {"cliffs_delta": round(delta, 4), "interpretation": _cliffs_delta_interpretation(abs(delta))}
