"""
Metric handler protocol + registry for fine-grained metric dispatch.

Background
----------
The worker's `SampleEvaluator._compute_metric` is a 60+ branch if/elif chain
over hardcoded metric names, with extended-only metrics (e.g.
`llm_judge_falloesung`) bolted into platform `tasks.py` as ad-hoc `if
metric_type == "..."` branches. This module introduces the registry that
lets each metric live in its own handler — and lets the extended package
register handlers via the existing `register_metric_handlers` hook in
`benger_extended.workers`.

Result shape
------------
Every handler's `compute(...)` returns a uniform dict::

    {
        "value": float | Dict[str, float],   # required
        "method": str,                       # required (canonical metric name)
        "details": Optional[dict],           # provenance — JSON-serializable
        "error": Optional[str],              # set if degraded but usable; else None
    }

When `value` is a dict (e.g. precision/recall/f1 from one compute call),
the handler exposes `primary_metric_key` so callers that want a single
representative number can extract it without knowing the metric's shape.

Migration policy (Phase 1 of the academic-rigor plan)
-----------------------------------------------------
This module is **additive**. Phase 1 introduces it; Phase 4 walks the
if/elif chain into handlers; Phase 5 lets extended register Falllösung as
a handler. Until then, `_compute_metric` consults the registry first and
falls through to the legacy chain on miss. No metric behaviour changes in
Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class MetricHandler(ABC):
    """Pluggable handler for a single metric.

    Subclasses set ``name`` (required) and ``primary_metric_key`` (only when
    ``compute`` returns a dict-valued ``value``), and implement ``compute``.
    """

    #: Canonical metric name as referenced in `evaluation_config.evaluation_configs[i].metric`.
    name: str = ""

    #: When :meth:`compute` returns ``{"value": {...}}``, names the float key
    #: callers should surface as the primary score for leaderboards/exports.
    primary_metric_key: Optional[str] = None

    @abstractmethod
    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute the metric for a single (ground_truth, prediction) pair.

        Implementations MUST return the standard result dict described in the
        module docstring. Implementations MUST NOT silently substitute a
        different sub-method or backend without recording it in
        ``details`` — the whole point of the registry is to eliminate
        unobservable metric semantics.
        """


class MetricRegistry:
    """Maps canonical metric names to their handler instances."""

    def __init__(self) -> None:
        self._handlers: Dict[str, MetricHandler] = {}

    def register(self, handler: MetricHandler) -> None:
        if not handler.name:
            raise ValueError(
                f"MetricHandler {type(handler).__name__} must set a non-empty `name`"
            )
        if handler.name in self._handlers:
            # Last-registered wins; helpful for tests but warn so accidental
            # double-registration in production startup is visible.
            import logging

            logging.getLogger(__name__).warning(
                "Metric handler %r already registered (replacing %s with %s)",
                handler.name,
                type(self._handlers[handler.name]).__name__,
                type(handler).__name__,
            )
        self._handlers[handler.name] = handler

    def get(self, metric_name: str) -> Optional[MetricHandler]:
        return self._handlers.get(metric_name)

    def names(self) -> list[str]:
        return sorted(self._handlers.keys())


def extract_value(result: Any) -> Optional[float]:
    """Backward-compat helper for callers that expected a bare float.

    Accepts:
      * a bare ``float`` / ``int`` (legacy metric path)
      * the new dict shape ``{"value": float, "details": {...}}``
      * a dict shape with multi-output ``{"value": {"precision": .., "f1": ..}}``
        — uses ``primary_metric_key`` (stored under that name in the outer
        dict) or the first key of the inner dict.

    Returns ``None`` if no numeric value can be extracted.
    """
    if result is None:
        return None
    if isinstance(result, (int, float)):
        return float(result)
    if isinstance(result, dict):
        v = result.get("value")
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            primary = result.get("primary_metric_key") or next(iter(v), None)
            if primary is not None and isinstance(v.get(primary), (int, float)):
                return float(v[primary])
    return None


__all__ = [
    "MetricHandler",
    "MetricRegistry",
    "extract_value",
]
