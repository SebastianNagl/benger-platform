"""
Shared imports, router, and request/response models for the multi_field
evaluation endpoints package.

This module is the single home for everything used by more than one
submodule: the module-level imports, the shared `router`, and all the
Pydantic request/response models. Each concern submodule does
``from ._common import *`` and then re-imports the specific names it needs
by hand so that ``patch("routers.evaluations.multi_field.<sub>.<name>")``
reaches both the handler and any helper that the handler calls internally.
"""

import hashlib
import json as _stdjson
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.authorization import Permission, auth_service
from auth_module import User, require_user
from database import get_async_db, get_db
from models import EvaluationRun as DBEvaluationRun
from models import Generation as DBLLMResponse
from models import ResponseGeneration as DBResponseGeneration
from project_models import Annotation, Project, Task
from routers.evaluations.helpers import celery_app, resolve_user_org_for_project
from routers.projects.helpers import (
    check_project_accessible,
    check_project_accessible_async,
    enforce_project_write_window,
    get_org_context_from_request,
)
from services.evaluation.human_eval_runs import (
    get_or_create_human_eval_run,
    get_or_create_human_eval_run_async,
    is_human_graded_metric,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============= Request/Response Models =============


class EvaluationConfigItem(BaseModel):
    """Single evaluation configuration item"""

    id: str
    metric: str
    display_name: Optional[str] = None
    metric_parameters: Optional[Dict[str, Any]] = None
    prediction_fields: List[str]
    reference_fields: List[str]
    enabled: bool = True


class EvaluationRunRequest(BaseModel):
    """Request model for running evaluation"""

    project_id: str
    evaluation_configs: List[EvaluationConfigItem]
    batch_size: int = 100
    label_config_version: Optional[str] = None
    force_rerun: bool = False  # If True, re-evaluate all; if False, only evaluate missing
    task_ids: Optional[List[str]] = None  # Filter to specific tasks (for single-cell re-evaluation)
    model_ids: Optional[List[str]] = None  # Filter to specific models (for single-cell re-evaluation)
    annotator_user_ids: Optional[List[str]] = None  # Filter annotation-side judge fan-out to specific annotators
    # (H) Top-level seed mirrors GenerationRequest.parameters.seed. When set,
    # every metric_parameters block in this run inherits the seed unless it
    # carries its own metric_parameters.seed (per-config override wins for
    # backward-compat). The worker reads this via the
    # `_top_level_seed` key the trigger threads into eval_metadata at
    # dispatch time.
    seed: Optional[int] = None


class EvaluationRunResponse(BaseModel):
    """Response model for evaluation run"""

    evaluation_id: str
    project_id: str
    status: str
    message: str
    evaluation_configs_count: int
    task_id: Optional[str] = None
    started_at: datetime
    # IDs of human-graded singleton runs that were ensured (created or
    # already existed) as part of this request. Empty when no human-graded
    # metrics were configured.
    human_eval_run_ids: List[str] = []


class AvailableFieldsResponse(BaseModel):
    """Response model for available fields"""

    model_response_fields: List[str]
    human_annotation_fields: List[str]
    reference_fields: List[str]
    all_fields: List[str]


class CancelEvaluationResponse(BaseModel):
    """Result of cancelling one or many evaluation runs."""

    cancelled_run_ids: List[str]
    failed_child_judge_run_count: int
    preserved_task_evaluation_count: int
    message: str


class EvaluationLifecycleResponse(BaseModel):
    """Result of a pause/resume/retry lifecycle action on a run (issue #198).

    ``changed`` is False when the run was not in a state the action applies
    to (e.g. pausing an already-completed run) — the handler then reports
    the current state instead of erroring, mirroring cancel's idempotent
    style so double-clicks and stale UIs don't surface scary failures.
    """

    evaluation_id: str
    action: str  # pause | resume | retry
    changed: bool
    previous_status: Optional[str] = None
    status: str
    retry_count: Optional[int] = None
    celery_task_id: Optional[str] = None
    message: str


# Explicit export surface. ``from ._common import *`` binds exactly these names,
# so the concern submodules (run / cancel / fields / results) no longer need to
# repeat an explicit import block just to dodge F405 — this single list documents
# the full shared surface once. It is every public name this module binds (each
# top-level import plus ``logger``/``router`` and the request/response models).
# ``_stdjson`` is intentionally omitted: it is underscore-prefixed, so the star
# never bound it, and ``run.py`` imports it explicitly where it is needed.
__all__ = [
    # stdlib / typing
    "hashlib",
    "logging",
    "uuid",
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
    # pydantic
    "BaseModel",
    # sqlalchemy
    "func",
    "select",
    "AsyncSession",
    "Session",
    # app.core.authorization
    "Permission",
    "auth_service",
    # auth_module
    "User",
    "require_user",
    # database
    "get_async_db",
    "get_db",
    # models
    "DBEvaluationRun",
    "DBLLMResponse",
    "DBResponseGeneration",
    # project_models
    "Annotation",
    "Project",
    "Task",
    # routers.evaluations.helpers
    "celery_app",
    "resolve_user_org_for_project",
    # routers.projects.helpers
    "check_project_accessible",
    "check_project_accessible_async",
    "enforce_project_write_window",
    "get_org_context_from_request",
    # services.evaluation.human_eval_runs
    "get_or_create_human_eval_run",
    "get_or_create_human_eval_run_async",
    "is_human_graded_metric",
    # this module
    "logger",
    "router",
    "EvaluationConfigItem",
    "EvaluationRunRequest",
    "EvaluationRunResponse",
    "AvailableFieldsResponse",
    "CancelEvaluationResponse",
    "EvaluationLifecycleResponse",
]
