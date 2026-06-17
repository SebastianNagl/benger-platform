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


# ---------------------------------------------------------------------------
# Immediate-evaluation eligibility
# ---------------------------------------------------------------------------
# Metrics that load transformer models (sentence-transformers, BERT, NLI,
# QA/QG pipelines) at compute time. They are fully supported in BATCH
# evaluation — one model load amortizes over many samples on a warm worker —
# but are deliberately excluded from IMMEDIATE (per-submit) evaluation:
#   * a per-submit model load is far too slow for "instant" feedback, and
#   * stacking those loads on the small interactive worker fleet risks OOM.
# The immediate-eval dispatcher filters these out and the modal surfaces them
# as "batch only". Mirrored on the frontend in evaluation-types.ts
# (`immediate_eligible: false`). Lives here because both the API (dispatch
# router) and the worker (defense-in-depth) need the same predicate and both
# have /shared on sys.path.
HEAVY_METRICS = frozenset(
    {
        "bertscore",
        "moverscore",
        "semantic_similarity",
        "factcc",
        "qags",
        "coherence",
    }
)


def is_heavy_metric(metric_name: Optional[str]) -> bool:
    """True for transformer-model-loading metrics excluded from immediate
    (per-submit) evaluation. See :data:`HEAVY_METRICS`."""
    return bool(metric_name) and metric_name in HEAVY_METRICS


def is_immediate_eligible(metric_name: Optional[str]) -> bool:
    """Whether a metric may run in immediate (post-submit) evaluation.

    Excludes human-graded Korrektur metrics (``korrektur_*`` — scored by a
    person, never computed by the worker) and heavy/semantic metrics; every
    other metric (deterministic + LLM judges) is eligible.
    """
    if not metric_name or metric_name.startswith("korrektur_"):
        return False
    return not is_heavy_metric(metric_name)
