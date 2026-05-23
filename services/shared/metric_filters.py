"""Single source of truth for the "real metric key" noise filter.

Used to be a private helper in `routers/projects/helpers.py`, but the
projects-list, dashboard, leaderboard and worker recompute paths all need
the same predicate to agree on what counts as a "real" metric. Hosting it
here lets both the API (which has /shared on sys.path) and the worker
(ditto) import the same definition without one reaching into the other's
package surface.
"""

from typing import Optional, Tuple

# Metric-key noise stripped out of the "scored (subject, metric) pairs" tally.
# Mirrors the dropdown filter in routers/evaluations/metadata.py so the tile
# and the metric list agree on what counts as a "real" metric.
_METRIC_NOISE_SUFFIXES: Tuple[str, ...] = (
    "_details",
    "_raw",
    "_passed",
    "_grade_points",
    "_response",
)
_METRIC_EXCLUDED_KEYS = frozenset({"raw_score", "error"})

# Sub-metric names that look like noise (end in a suffix above) but are
# registered as displayable standalone metrics in the frontend metric
# registry. Without this override the aggregator + tile counters would drop
# them on the floor and the leaderboard column shows n/a for everyone even
# though the per-row value exists (see aggregate_summaries.py — the
# UNION ALL that lifts grade_points out of `details`).
_METRIC_REGISTERED_OVERRIDES = frozenset({"llm_judge_falloesung_grade_points"})


def metric_key_is_real(key: Optional[str]) -> bool:
    """True for keys that should count toward the scored-pairs tally."""
    if not key or key in _METRIC_EXCLUDED_KEYS:
        return False
    if key in _METRIC_REGISTERED_OVERRIDES:
        return True
    return not key.endswith(_METRIC_NOISE_SUFFIXES)


# Legacy underscore alias — many call sites already use this name.
_metric_key_is_real = metric_key_is_real
