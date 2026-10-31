"""Metric value coercion shared by the API and the workers.

TaskEvaluation.metrics and EvaluationRun.metrics carry either the legacy
bare-float shape or the ``{"value": float|dict, "details": {...}}`` shape.
``coerce_metric_value`` turns one stored value into a float for display and
aggregation. It lives in /shared so code that runs in the worker image
(report_service, export_stream) can use it; the worker image has no
``routers`` package.

``routers.evaluations.results._coerce_metric_value`` re-exports this
function under its historical name.

Note: ``aggregate_summaries._coerce_metric_value`` is a separate, more lenient
variant (it also parses numeric strings and recurses into nested dicts) that
backs the leaderboard SQL twin. The two are intentionally not merged here.
"""

from typing import Any


def coerce_metric_value(val: Any) -> float | None:
    """Accept either the legacy bare-float persistence shape OR the
    ``{"value": float|dict, "details": {...}}`` shape produced by
    ``SampleEvaluator._compute_metric_with_details``.

    For multi-output metrics (precision/recall/f1 from one compute call),
    the inner value is a dict: surface ``primary_metric_key`` if set,
    otherwise the first numeric value in insertion order.

    Also accepts the pre-unified-shape Korrektur Falllösung blob
    (``{"score": 51.5, "total_score": 51.5, "dimensions": {...}, ...}``)
    that earlier submit_falloesung_grade calls wrote: surface
    ``total_score`` (or ``score``) as the primary number so legacy rows
    don't render as n/a in the eval results table.
    """
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        inner = val.get("value")
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return float(inner)
        if isinstance(inner, dict):
            primary = val.get("primary_metric_key") or next(iter(inner), None)
            inner_v = inner.get(primary) if primary else None
            if isinstance(inner_v, (int, float)) and not isinstance(inner_v, bool):
                return float(inner_v)
        # Legacy Korrektur Falllösung shape fallback.
        for legacy_key in ("total_score", "score"):
            legacy_v = val.get(legacy_key)
            if isinstance(legacy_v, (int, float)) and not isinstance(legacy_v, bool):
                return float(legacy_v)
    return None
