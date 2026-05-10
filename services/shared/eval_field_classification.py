"""Shared prediction-field classification for evaluation runs.

The worker (`services/workers/tasks.py`) and the cost endpoint
(`services/api/routers/cost_estimate.py`) both need to decide whether each
prediction-field on an evaluation config refers to the **annotation** side
(human-graded subjects, joined from `Annotation.completed_by`) or the
**generation** side (LLM-produced subjects, filtered by model). They used
to encode that decision twice — once inline in the worker, once in the
cost endpoint — which made the two diverge silently and made the cost
preview lie about the falloesung judge in particular.

This module is the single source of truth. Both call sites import
``classify_pred_fields`` from here.

The classifier knows two things:

1. The **default** rule: a field is human if it carries the ``human:``
   prefix or is the ``__all_human__`` wildcard; everything else is LLM.

2. **Per-metric overrides**: a metric can register a custom rule that
   re-classifies fields when the default produces zero human fields. This
   is what the existing ``llm_judge_falloesung`` backward-compat path
   does (unprefixed fields evaluate annotations) and what future metrics
   landing in extended will do too — extended registers its rules from
   ``benger_extended/__init__.py`` at import time, so the platform never
   needs to know what the rule is, only that the registration API exists.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

ClassifierRule = Callable[[List[str]], Tuple[List[str], List[str]]]
"""A classifier rule takes the raw `prediction_fields` list and returns
`(human_fields, llm_fields)`. The two returned lists must partition the
input — every original field appears in exactly one of them."""


_RULES: Dict[str, ClassifierRule] = {}


def register_classifier_rule(metric: str, rule: ClassifierRule) -> None:
    """Register a metric-specific override that runs when the default
    classifier finds zero explicit human fields. Idempotent — re-registering
    the same metric replaces the rule, so reload-safe in dev."""
    _RULES[metric] = rule


def classify_pred_fields(
    metric: Optional[str],
    prediction_fields: List[str],
) -> Tuple[List[str], List[str]]:
    """Split `prediction_fields` into (human_fields, llm_fields).

    Rules:
    - Fields starting with ``human:`` or equal to ``__all_human__`` are always
      human-side.
    - Remaining fields are LLM-side BY DEFAULT.
    - If a per-metric rule is registered AND the default split produced zero
      explicit human fields, the metric's rule is consulted to re-classify
      the unprefixed fields. This mirrors the worker's existing falloesung
      backward-compat condition — only a config with NO ``human:`` prefixes
      gets re-classified by metric.
    """
    if not prediction_fields:
        return [], []

    explicit_human = [
        f for f in prediction_fields if f.startswith("human:") or f == "__all_human__"
    ]
    explicit_llm = [f for f in prediction_fields if f not in explicit_human]

    if explicit_human or metric is None or metric not in _RULES:
        return explicit_human, explicit_llm

    return _RULES[metric](prediction_fields)


# ---------------------------------------------------------------------------
# Built-in rules registered at module import time.
# ---------------------------------------------------------------------------


def _falloesung_compat(fields: List[str]) -> Tuple[List[str], List[str]]:
    """`llm_judge_falloesung` historically allowed unprefixed prediction
    fields and treated them as annotation-side. New configs should use the
    ``human:`` prefix explicitly, but configs created before that
    convention existed still need to resolve correctly."""
    human = [
        f for f in fields
        if not f.startswith("model:") and f not in ("__all_model__", "__all_human__")
    ]
    llm = [f for f in fields if f not in human]
    return human, llm


register_classifier_rule("llm_judge_falloesung", _falloesung_compat)
