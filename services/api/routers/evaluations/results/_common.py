"""
Shared imports, router instance, and cross-submodule helpers for the
evaluation results package.

Score-extraction helpers (`_coerce_metric_value`, `_extract_primary_score`)
live here because they are used by handlers across MORE THAN ONE submodule
(`distributions` uses `_coerce_metric_value`; `by_task_model` uses
`_extract_primary_score`, which internally calls `_coerce_metric_value`).
"""

# NOTE: nearly all of these imports are re-exported to the concern submodules
# (via star-import and explicit name lists) and to the package __init__; they
# are "unused" within this file by design, hence the per-line F401 suppression.
import logging
from datetime import datetime, timezone  # noqa: F401
from typing import Any, Dict, List, Optional  # noqa: F401

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status  # noqa: F401
from sqlalchemy import func, literal_column, select  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401
from sqlalchemy.orm import Session  # noqa: F401

from auth_module import User, require_user  # noqa: F401
from database import get_async_db, get_db  # noqa: F401
from models import EvaluationRun as DBEvaluationRun  # noqa: F401
from models import HumanEvaluationSession, LikertScaleEvaluation, PreferenceRanking  # noqa: F401
from project_models import Annotation, Project, Task  # noqa: F401
from routers.evaluations.helpers import EvaluationResultsResponse  # noqa: F401
from routers.projects.helpers import (  # noqa: F401
    check_project_accessible,
    check_project_accessible_async,
    get_org_context_from_request,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============= Score Extraction Helper =============


# Known metadata-suffix keys that should never be treated as primary scores.
# Used by both the explicit llm_judge_* matcher and the generic fallback.
_METRIC_METADATA_SUFFIXES = (
    "_response",      # LLM judge raw text
    "_passed",        # boolean cast to 0/1
    "_details",       # nested explanation dict
    "_raw",           # raw pre-aggregation array
    "_grade_points",  # Falloesung grade-points sub-metric
)


def _coerce_metric_value(val: Any) -> Optional[float]:
    """Phase 2: accept either the legacy bare-float persistence shape OR the
    new ``{"value": float|dict, "details": {...}}`` shape produced by
    ``SampleEvaluator._compute_metric_with_details``.

    For multi-output metrics (precision/recall/f1 from one compute call),
    the inner value is a dict — surface ``primary_metric_key`` if set,
    otherwise the first numeric value in insertion order.

    Also accepts the pre-unified-shape Korrektur Falllösung blob
    (``{"score": 51.5, "total_score": 51.5, "dimensions": {...}, ...}``)
    that earlier submit_falloesung_grade calls wrote — surface
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


def _extract_primary_score(metrics: Optional[Dict[str, Any]]) -> Optional[float]:
    """Extract the primary display score from a TaskEvaluation metrics dict.

    Each TaskEvaluation row corresponds to ONE config x ONE (pred, ref) pair x
    ONE metric, so the primary score is the single non-metadata numeric value
    in the dict.

    Precedence (handles multi-metric edge cases first, then generic fallback):
    1. llm_judge_custom (pinned for backwards-compat)
    2. Any llm_judge_* numeric key (excluding metadata suffixes)
    3. korrektur_falloesung (human-graded total score)
    4. score, overall_score (legacy keys)
    5. Generic: first non-metadata, non-error numeric value (covers
       bleu, rouge, meteor, exact_match, accuracy, f1, etc.)

    Phase 2: every numeric extraction routes through ``_coerce_metric_value``
    so both the legacy bare-float shape AND the new
    ``{value, details}`` shape produce the right number.
    """
    if not metrics:
        return None

    # 1. Custom LLM judge
    if "llm_judge_custom" in metrics:
        coerced = _coerce_metric_value(metrics["llm_judge_custom"])
        if coerced is not None:
            return coerced

    # 2. Any llm_judge_* numeric key
    for key, val in metrics.items():
        if not key.startswith("llm_judge_"):
            continue
        if key.endswith(_METRIC_METADATA_SUFFIXES):
            continue
        coerced = _coerce_metric_value(val)
        if coerced is not None:
            return coerced

    # 3. Domain-specific human-graded metric: takes precedence over generic
    # `score` / `overall_score` so projects using Falllosung-grade headline it.
    if "korrektur_falloesung" in metrics:
        coerced = _coerce_metric_value(metrics["korrektur_falloesung"])
        if coerced is not None:
            return coerced

    # 4. Legacy generic keys
    for key in ("score", "overall_score"):
        if key in metrics:
            coerced = _coerce_metric_value(metrics[key])
            if coerced is not None:
                return coerced

    # 5. Generic fallback: first non-metadata, non-error numeric value.
    # Covers BLEU, ROUGE, exact_match, METEOR, etc. -- each TaskEvaluation row
    # holds the result of one config x one (pred, ref) pair x one metric, so
    # exactly one such value is present.
    for key, val in metrics.items():
        if key == "error":
            continue
        if key.endswith(_METRIC_METADATA_SUFFIXES):
            continue
        coerced = _coerce_metric_value(val)
        if coerced is None:
            continue
        return coerced

    return None


# Explicit export surface. ``from ._common import *`` binds exactly these names,
# so the concern submodules (core / distributions / by_task_model) no longer
# need to repeat an explicit import block just to dodge F405 — this single list
# documents the full shared surface once. It is every public name this module
# binds (every import above plus ``logger``/``router``), and the underscore-
# prefixed score helpers (which ``*`` would otherwise skip) are listed
# explicitly so the submodules that call them keep resolving via the star.
__all__ = [
    # stdlib / typing
    "logging",
    "datetime",
    "timezone",
    "Any",
    "Dict",
    "List",
    "Optional",
    # fastapi
    "APIRouter",
    "Depends",
    "HTTPException",
    "Query",
    "Request",
    "status",
    # sqlalchemy
    "func",
    "literal_column",
    "select",
    "AsyncSession",
    "Session",
    # auth_module
    "User",
    "require_user",
    # database
    "get_async_db",
    "get_db",
    # models
    "DBEvaluationRun",
    "HumanEvaluationSession",
    "LikertScaleEvaluation",
    "PreferenceRanking",
    # project_models
    "Annotation",
    "Project",
    "Task",
    # routers.evaluations.helpers / routers.projects.helpers
    "EvaluationResultsResponse",
    "check_project_accessible",
    "check_project_accessible_async",
    "get_org_context_from_request",
    # this module
    "logger",
    "router",
    "_METRIC_METADATA_SUFFIXES",
    "_coerce_metric_value",
    "_extract_primary_score",
]
