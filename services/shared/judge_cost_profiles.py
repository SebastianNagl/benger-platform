"""Per-metric judge-call profiles for the evaluation cost estimate.

The cost endpoint (``services/api/routers/cost_estimate.py``) prices an
LLM-judge evaluation from what one judge call sends and writes back. For the
judges the platform ships it can render that itself (template, case context,
reference, answer, Bewertungsbogen). A judge an extension package ships
renders its own prompt (e.g. ``llm_judge_feedback`` loads a long prompt per
exam type from the package and answers with several pages of Markdown), so
the platform cannot size it: without help the estimate counted only the case
and the answer and assumed a short score-plus-rationale answer, about 5x
under the billed cost.

An extension package therefore registers a profiler for its metric at import
time, the same way it registers a classifier rule
(``eval_field_classification.register_classifier_rule``)::

    from judge_cost_profiles import register_judge_cost_profile

    register_judge_cost_profile("llm_judge_feedback", profile)

where ``profile(task_data, prediction, metric_parameters)`` returns a mapping

* ``prompt`` (str, required): the user prompt the judge would send for this
  task and answer, rendered exactly as the judge does.
* ``overhead_tokens`` (number, optional): input the prompt text does not
  contain (system prompt, chat framing, a response schema). Defaults to the
  platform's fixed judge overhead.
* ``output_tokens`` (number, optional): the visible answer the judge is
  expected to write. Defaults to the platform's share of the config's
  ``max_tokens``.

or ``None`` when it cannot size this call (the platform then falls back to
its generic rule). A profiler that raises is logged and treated as ``None``:
a cost preview must never fail because of it.

A profile only answers while its owning package is active for the caller
(``extension_activation.package_active``), like the metric itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

JudgeCostProfiler = Callable[
    [Dict[str, Any], str, Dict[str, Any]], Optional[Mapping[str, Any]]
]


@dataclass(frozen=True)
class JudgeCallProfile:
    """One judge call as the owning package sizes it."""

    prompt: str
    overhead_tokens: Optional[float] = None
    output_tokens: Optional[float] = None


_PROFILERS: Dict[str, JudgeCostProfiler] = {}
# Which extension package registered each profiler (None: the platform).
_OWNERS: Dict[str, Optional[str]] = {}


def _registration_owner() -> Optional[str]:
    try:
        from extension_registry import current_owner
    except ImportError:  # pragma: no cover - /shared without the registry
        return None
    return current_owner()


def _owner_active(owner: Optional[str]) -> bool:
    if not owner:
        return True
    try:
        import extension_activation
    except ImportError:  # pragma: no cover
        return True
    return extension_activation.package_active(owner)


def register_judge_cost_profile(metric: str, profiler: JudgeCostProfiler) -> None:
    """Register the profiler for ``metric``. Re-registering replaces it
    (reload-safe in dev); a replacement by another package is logged."""
    owner = _registration_owner()
    if metric in _PROFILERS and _OWNERS.get(metric) != owner:
        logger.warning(
            "judge cost profile for %r registered by %s replaces %s's",
            metric,
            owner or "the platform",
            _OWNERS.get(metric) or "the platform",
        )
    _PROFILERS[metric] = profiler
    _OWNERS[metric] = owner


def unregister_judge_cost_profile(metric: str) -> None:
    _PROFILERS.pop(metric, None)
    _OWNERS.pop(metric, None)


def has_judge_cost_profile(metric: Optional[str]) -> bool:
    """Whether an active package sizes ``metric`` itself."""
    return bool(metric) and metric in _PROFILERS and _owner_active(_OWNERS.get(metric))


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def judge_cost_profile(
    metric: Optional[str],
    *,
    task_data: Optional[Dict[str, Any]],
    prediction: str,
    metric_parameters: Optional[Dict[str, Any]],
) -> Optional[JudgeCallProfile]:
    """The registered profile of one judge call, or None (generic sizing)."""
    if not has_judge_cost_profile(metric):
        return None
    try:
        raw = _PROFILERS[metric](
            dict(task_data or {}), prediction or "", dict(metric_parameters or {})
        )
    except Exception:
        logger.exception("judge cost profile for %s failed", metric)
        return None
    if not isinstance(raw, Mapping) or not isinstance(raw.get("prompt"), str):
        if raw is not None:
            logger.warning("judge cost profile for %s returned no prompt: %r", metric, type(raw))
        return None
    return JudgeCallProfile(
        prompt=raw["prompt"],
        overhead_tokens=_number(raw.get("overhead_tokens")),
        output_tokens=_number(raw.get("output_tokens")),
    )
