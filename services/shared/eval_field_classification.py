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

Alongside the classifier this module owns the other half of the same rule:
what a field selector is CALLED once the role is stripped
(``bare_field_name``). ``human:``/``model:`` says where an answer came from,
not what the field is named, so a row stored as ``human:loesung`` and one
stored as ``loesung`` are the same field and must pair, group and match as
one. That rule had been re-implemented at nearly a dozen call sites; new
code should import it from here.

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


#: Role prefixes a prediction-field selector may carry. The prefix records
#: WHERE an answer came from (a human annotation or a model generation); the
#: field name is what follows it.
ROLE_PREFIXES: Tuple[str, ...] = ("human:", "model:")

#: Selectors that stand for "every field of that role", not one nameable
#: field. They have no bare form.
BULK_SELECTORS: Tuple[str, ...] = ("__all_human__", "__all_model__")


def bare_field_name(selector: Optional[str]) -> Optional[str]:
    """The field a selector names, with the role prefix removed.

    ``"human:loesung"`` and ``"loesung"`` both yield ``"loesung"``: which form
    a config or a stored row carries depends only on how it was authored (the
    field picker offers the prefixed form; a config written in code usually
    does not), never on which field is meant.

    Returns ``None`` for anything that names no single field — empty input, a
    bare prefix, or one of :data:`BULK_SELECTORS` — so callers can fall
    through to another source instead of storing a meaningless label.
    """
    value = (selector or "").strip()
    if not value or value in BULK_SELECTORS:
        return None
    for prefix in ROLE_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value or None


def same_field(a: Optional[str], b: Optional[str]) -> bool:
    """True when two selectors name the same field, ignoring the role prefix."""
    if a == b:
        return True
    bare_a, bare_b = bare_field_name(a), bare_field_name(b)
    return bare_a is not None and bare_a == bare_b


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
