"""
Generation Task List endpoints for Issue #495.
Provides paginated task list with per-model generation status.
"""

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import String, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_async_db
from models import Generation as DBGeneration
from models import ResponseGeneration as DBResponseGeneration
from models import User as DBUser
from project_models import Project, ProjectOrganization, Task
from routers.generation_revoke import (
    generation_run_task_ids,
    send_generation_trial,
)
from routers.projects.helpers import (
    check_project_accessible_async,
    check_project_write_access_async,
    enforce_project_write_window_async,
    get_org_context_from_request,
)


router = APIRouter(prefix="/api/generation-tasks", tags=["generation-tasks"])

# Celery app
from celery_client import get_celery_app  # noqa: E402


logger = logging.getLogger(__name__)
celery_app = get_celery_app()

# Issue #106: when a trigger omits explicit task_ids, the handler dispatches
# for every task in the project. The dispatch itself is synchronous (one
# ResponseGeneration row per cell plus N Celery sends), so an unbounded
# fallback turns a single request into an OOM/timeout risk on huge projects.
# Callers above this bound must page through explicit task_ids.
GENERATION_FALLBACK_MAX_TASKS = 10_000


# ============= Request/Response Models =============


class TaskGenerationStatus(BaseModel):
    """Status of generation for a single task-model-structure combination"""

    task_id: str
    model_id: str
    structure_key: Optional[str] = None  # Issue #762: Include structure key
    status: Optional[str] = None  # 'completed', 'failed', 'running', 'pending', None
    generation_id: Optional[str] = None
    generated_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result_preview: Optional[str] = None  # First 100 chars of result
    # Multi-run progress (migration 041). All three default to None when the
    # caller queries a non-existent combination; for legacy single-run rows
    # they're populated as (1, 1, 0) by the backfill.
    runs_requested: Optional[int] = None
    runs_completed: Optional[int] = None
    runs_failed: Optional[int] = None


class TaskWithGenerationStatus(BaseModel):
    """Task with generation status for each model-structure combination"""

    id: str
    data: Dict[str, Any]
    meta: Optional[Dict[str, Any]] = None
    created_at: datetime
    generation_status: Dict[
        str, List[TaskGenerationStatus]
    ]  # key: model_id, value: list of statuses (one per structure)


class PaginatedTaskGenerationResponse(BaseModel):
    """Paginated response for task generation status"""

    tasks: List[TaskWithGenerationStatus]
    total: int
    page: int
    page_size: int
    total_pages: int
    models: List[str]  # List of model IDs configured for this project
    structures: List[str]  # List of structure keys configured for this project (Issue #762)


class GenerationParameters(BaseModel):
    """Parameters for LLM generation"""

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, ge=100, le=16000)
    # Phase 6.6: explicit seed for variance studies. Default 42 keeps
    # the historical determinism behavior. Providers that don't accept
    # a seed (Anthropic, Google, DeepInfra) record None on the row.
    seed: int = Field(default=42, ge=0)


class GenerationRequest(BaseModel):
    """Request to start generation"""

    mode: str = Field(..., pattern="^(all|missing|single)$", description="Generate all, only missing, or a specific task-model cell")
    model_ids: Optional[List[str]] = None  # If not provided, use all project models
    task_ids: Optional[List[str]] = None  # If not provided, use all project tasks
    structure_keys: Optional[List[str]] = None  # If not provided, use active_structures from config
    parameters: Optional[GenerationParameters] = None  # LLM generation parameters
    model_configs: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Per-model settings: {model_id: {max_tokens: int, reasoning_effort?: str, thinking_budget?: int}}",
    )
    # Multi-run override: when set, this trigger generates N trials per
    # (task, model, structure) regardless of the project default. None falls
    # back to project.generation_config.runs_per_task (or 1 if unset).
    runs_per_task: Optional[int] = Field(default=None, ge=1, le=25)


class GenerationResponse(BaseModel):
    """Response from generation request"""

    project_id: str
    mode: str
    tasks_queued: int
    models_count: int
    generation_job_ids: List[str]
    estimated_time_seconds: Optional[int] = None
    message: str


class GenerationResultRequest(BaseModel):
    """Request to get generation result"""

    task_id: str
    model_id: str


class GenerationResultResponse(BaseModel):
    """Generation result for a specific task-model combination"""

    task_id: str
    model_id: str
    generation_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    generated_at: Optional[datetime] = None
    generation_time_seconds: Optional[float] = None
    prompt_used: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    structure_key: Optional[str] = None  # Issue #762: Prompt structure key
    created_by: Optional[str] = None  # Issue #1372: User ID who triggered generation
    created_by_name: Optional[str] = None  # Issue #1372: Resolved display name


class MultipleGenerationResultsResponse(BaseModel):
    """Multiple generation results for a task-model combination (one per structure)"""

    task_id: str
    model_id: str
    results: List[GenerationResultResponse]


# ============= Helper Functions =============


async def get_project_with_permissions(
    project_id: str,
    current_user: User,
    db: AsyncSession,
    request: Optional[Request] = None,
) -> Project:
    """Get project and verify user permissions using centralized access check."""

    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    org_context = get_org_context_from_request(request) if request else None
    if not await check_project_accessible_async(
        db, current_user, project_id, org_context, project=project
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    return project


def _status_from_row(
    row: DBResponseGeneration,
    *,
    task_id: str,
    model_id: str,
    structure_key: Optional[str],
) -> TaskGenerationStatus:
    """Materialize a TaskGenerationStatus from a ResponseGeneration row.

    The cell coordinates are passed explicitly rather than read off the row
    so the returned status carries the *requested* cell label even when
    the row matched on the NULL-structure_key legacy fallback.
    """
    result_preview = None
    if row.status == "completed" and row.result:
        result_str = (
            json.dumps(row.result)
            if isinstance(row.result, dict)
            else str(row.result)
        )
        result_preview = result_str[:100] + "..." if len(result_str) > 100 else result_str

    return TaskGenerationStatus(
        task_id=task_id,
        model_id=model_id,
        structure_key=structure_key,
        status=row.status,
        generation_id=row.id,
        generated_at=row.completed_at or row.created_at,
        error_message=row.error_message if row.status == "failed" else None,
        result_preview=result_preview,
        runs_requested=getattr(row, "runs_requested", None),
        runs_completed=getattr(row, "runs_completed", None),
        runs_failed=getattr(row, "runs_failed", None),
    )


async def _bulk_latest_generations(
    db: AsyncSession,
    project_id: str,
    task_ids: List[str],
    model_ids: List[str],
) -> Dict[tuple, DBResponseGeneration]:
    """Latest ResponseGeneration row per (task_id, model_id, structure_key) for
    the given page of tasks. Returns {(task_id, model_id, structure_key): row}.

    Backed by the composite index added in migration 052
    (`ix_response_generations_cell`). One round-trip replaces the per-cell
    SELECT loop in `get_task_generation_status`.
    """
    if not task_ids or not model_ids:
        return {}

    rows = (
        await db.execute(
            select(DBResponseGeneration)
            .where(
                DBResponseGeneration.project_id == project_id,
                DBResponseGeneration.task_id.in_(task_ids),
                DBResponseGeneration.model_id.in_(model_ids),
            )
            .distinct(
                DBResponseGeneration.task_id,
                DBResponseGeneration.model_id,
                DBResponseGeneration.structure_key,
            )
            .order_by(
                DBResponseGeneration.task_id,
                DBResponseGeneration.model_id,
                DBResponseGeneration.structure_key,
                DBResponseGeneration.created_at.desc(),
            )
        )
    ).scalars().all()
    return {(r.task_id, r.model_id, r.structure_key): r for r in rows}


def _resolve_cell(
    bulk: Dict[tuple, DBResponseGeneration],
    task_id: str,
    model_id: str,
    structure_key: Optional[str],
) -> Optional[DBResponseGeneration]:
    """Look up the latest row for a (task, model, structure) cell, falling
    back to a legacy NULL-structure row when the exact key is missing.

    Mirrors the case-ordering in the old per-cell query: prefer the exact
    match, accept the NULL row as a last resort.
    """
    exact = bulk.get((task_id, model_id, structure_key))
    if exact is not None:
        return exact
    if structure_key is not None:
        return bulk.get((task_id, model_id, None))
    return None


def get_single_task_generation_status(
    task_id: str, model_id: str, structure_key: Optional[str], db: Session
) -> TaskGenerationStatus:
    """Per-cell helper kept for compatibility with code paths that only need
    one status (e.g. tests, ad-hoc lookups). The list endpoint uses
    `_bulk_latest_generations` to avoid the per-cell SELECT.

    Stays SYNC (``db: Session``): no migrated request handler calls this —
    it is exercised only by ``db.query``-mocking unit tests and ad-hoc
    lookups. Migrating it would break those mock-based tests for no runtime
    benefit, so the sync compatibility shim is intentionally retained."""

    # Query for the most recent generation for this task-model-structure combination
    base_filter = db.query(DBResponseGeneration).filter(
        DBResponseGeneration.task_id == task_id, DBResponseGeneration.model_id == model_id
    )

    # Match exact structure_key, falling back to legacy NULL responses
    if structure_key is not None:
        generation = base_filter.filter(
            (DBResponseGeneration.structure_key == structure_key)
            | (DBResponseGeneration.structure_key.is_(None))
        ).order_by(
            # Prefer exact match over NULL fallback
            case((DBResponseGeneration.structure_key == structure_key, 0), else_=1),
            DBResponseGeneration.created_at.desc(),
        ).first()
    else:
        generation = base_filter.filter(
            DBResponseGeneration.structure_key.is_(None)
        ).order_by(DBResponseGeneration.created_at.desc()).first()

    if not generation:
        return TaskGenerationStatus(
            task_id=task_id, model_id=model_id, structure_key=structure_key, status=None
        )
    return _status_from_row(
        generation,
        task_id=task_id,
        model_id=model_id,
        structure_key=structure_key,
    )


# ============= Endpoints =============


@router.get("/projects/{project_id}/task-status", response_model=PaginatedTaskGenerationResponse)
async def get_task_generation_status(
    project_id: str,
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    search: Optional[str] = Query(None, description="Search in task data"),
    status_filter: Optional[str] = Query(None, description="Filter by generation status"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get paginated list of tasks with generation status for each configured model.
    Feature flag: generation
    """

    # Get project and verify permissions
    project = await get_project_with_permissions(project_id, current_user, db, request)

    # Get configured models and structures for this project
    generation_config = project.generation_config or {}
    selected_config = generation_config.get("selected_configuration", {})
    model_ids = selected_config.get("models", [])

    # Get structure keys from prompt_structures (matching GenerationControlModal behavior)
    # This fixes the mismatch where generation uses prompt_structures keys but status used active_structures
    prompt_structures = generation_config.get("prompt_structures", {})
    if isinstance(prompt_structures, dict):
        structure_keys = list(prompt_structures.keys()) if prompt_structures else []
    elif isinstance(prompt_structures, list):
        structure_keys = [ps.get("key", str(i)) for i, ps in enumerate(prompt_structures)]
    else:
        structure_keys = []

    # If no structures configured, use None for backward compatibility
    if not structure_keys:
        structure_keys = [None]

    logger.debug(f"Project {project_id}: model_ids={model_ids}, structure_keys={structure_keys}")

    if not model_ids:
        # Return empty response if no models configured
        return PaginatedTaskGenerationResponse(
            tasks=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            models=[],
            structures=[],
        )

    # Build base query for tasks. Accumulate WHERE clauses so the same set of
    # filters drives both the COUNT and the paginated row fetch.
    task_where = [Task.project_id == project_id]

    # Apply search filter if provided
    if search:
        # Escape ILIKE wildcards in user input
        escaped_search = search.replace('%', r'\%').replace('_', r'\_')
        task_where.append(func.cast(Task.data, String).ilike(f"%{escaped_search}%"))

    if status_filter and status_filter != "not_generated":
        # Narrow the task set to ids that have at least one cell whose *latest*
        # row matches `status_filter`. Done as a CTE-like subquery so the outer
        # task scan keeps its pagination shape — no need to load every matching
        # task into memory like the legacy code did.
        latest_subq = (
            select(
                DBResponseGeneration.task_id.label("task_id"),
                DBResponseGeneration.status.label("status"),
            )
            .where(
                DBResponseGeneration.project_id == project_id,
                DBResponseGeneration.model_id.in_(model_ids),
            )
            .distinct(
                DBResponseGeneration.task_id,
                DBResponseGeneration.model_id,
                DBResponseGeneration.structure_key,
            )
            .order_by(
                DBResponseGeneration.task_id,
                DBResponseGeneration.model_id,
                DBResponseGeneration.structure_key,
                DBResponseGeneration.created_at.desc(),
            )
            .subquery()
        )
        matching_ids_subq = (
            select(latest_subq.c.task_id)
            .where(latest_subq.c.status == status_filter)
            .distinct()
        )
        task_where.append(Task.id.in_(matching_ids_subq))
        total = (
            await db.execute(
                select(func.count()).select_from(Task).where(*task_where)
            )
        ).scalar() or 0
        offset = (page - 1) * page_size
        tasks = (
            await db.execute(
                select(Task).where(*task_where).offset(offset).limit(page_size)
            )
        ).scalars().all()
    elif status_filter == "not_generated":
        # "Missing somewhere" can't be expressed cleanly in SQL (we need to
        # enumerate (task, model, structure) absences). Load all candidate
        # tasks once, bulk-fetch their latest rows, filter, paginate. Single
        # bulk query instead of per-cell SELECTs.
        tasks = (
            await db.execute(select(Task).where(*task_where))
        ).scalars().all()
    else:
        total = (
            await db.execute(
                select(func.count()).select_from(Task).where(*task_where)
            )
        ).scalar() or 0
        offset = (page - 1) * page_size
        tasks = (
            await db.execute(
                select(Task).where(*task_where).offset(offset).limit(page_size)
            )
        ).scalars().all()

    # Bulk-fetch latest ResponseGeneration rows for the resolved task page in
    # one round-trip — replaces the per-cell loop that fired
    # `rows × models × structures` SELECTs.
    page_task_ids = [t.id for t in tasks]
    bulk = await _bulk_latest_generations(db, project_id, page_task_ids, model_ids)

    task_responses = []
    for task in tasks:
        generation_status = {}
        for model_id in model_ids:
            model_statuses = []
            for structure_key in structure_keys:
                row = _resolve_cell(bulk, task.id, model_id, structure_key)
                if row is None:
                    status_obj = TaskGenerationStatus(
                        task_id=task.id,
                        model_id=model_id,
                        structure_key=structure_key,
                        status=None,
                    )
                else:
                    status_obj = _status_from_row(
                        row,
                        task_id=task.id,
                        model_id=model_id,
                        structure_key=structure_key,
                    )
                model_statuses.append(status_obj.model_dump())
            generation_status[model_id] = model_statuses

        if status_filter == "not_generated":
            has_matching_status = any(
                any(
                    not status_obj or status_obj.get('status') is None
                    for status_obj in statuses_list
                )
                for statuses_list in generation_status.values()
            )
            if not has_matching_status:
                continue

        task_responses.append(
            TaskWithGenerationStatus(
                id=task.id,
                data=task.data or {},
                meta=task.meta,
                created_at=task.created_at,
                generation_status=generation_status,
            )
        )

    if status_filter == "not_generated":
        total = len(task_responses)
        offset = (page - 1) * page_size
        task_responses = task_responses[offset : offset + page_size]

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size

    # Filter out None from structures for response
    structures_for_response = [s for s in structure_keys if s is not None]

    return PaginatedTaskGenerationResponse(
        tasks=task_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        models=model_ids,
        structures=structures_for_response,
    )


@router.post("/projects/{project_id}/generate", response_model=GenerationResponse)
async def start_generation(
    project_id: str,
    request: GenerationRequest,
    raw_request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Start bulk generation for all or missing task-model combinations.
    Uses parallel processing for optimal performance.
    Feature flag: generation

    Celery dispatch note: the per-cell ``celery_app.send_task`` /
    ``celery_app.control.revoke`` calls are non-blocking broker operations
    (no request-DB session). They are called directly from this async handler
    AFTER the awaited ``db.commit()`` that persists the ResponseGeneration
    rows, preserving the sync version's "commit rows, then dispatch" ordering
    so workers can always find the rows they are sent.
    """

    # Get project and verify permissions
    project = await get_project_with_permissions(
        project_id, current_user, db, raw_request
    )

    # Starting generation is a contribute-level action — block public-tier
    # ANNOTATOR visitors, allow CONTRIBUTOR / org members / creator / superadmin.
    if not await check_project_write_access_async(db, current_user, project_id):
        raise HTTPException(
            status_code=403,
            detail="Only contributors or admins can start generation for this project",
        )

    # Timed access window: no generation runs outside [start, end] for the
    # access group (editors exempt). No-op when the project has no window.
    await enforce_project_write_window_async(db, current_user, project)

    # Extract organization context for API key resolution (Issue #1180).
    # The frontend sets X-Organization-Context when the user has an explicit
    # org tab selected. When it's missing/"private" we fall back to the
    # project's M2M `project_organizations` link — otherwise org-level
    # `require_private_keys: False` settings are silently bypassed for any
    # request triggered from the Private tab.
    org_context = raw_request.headers.get("X-Organization-Context")
    org_id = org_context if org_context and org_context != "private" else None
    if org_id is None:
        linked_org_ids = [
            row[0]
            for row in (
                await db.execute(
                    select(ProjectOrganization.organization_id).where(
                        ProjectOrganization.project_id == project_id
                    )
                )
            ).all()
        ]
        if len(linked_org_ids) == 1:
            org_id = linked_org_ids[0]
        # If zero: project has no org → user-key fallback is appropriate.
        # If multiple: caller must disambiguate via the header; leave None
        # so the resolver continues to use the user's personal keys rather
        # than guessing which org's keys to spend.

    # Get generation configuration
    generation_config = project.generation_config or {}
    selected_config = generation_config.get("selected_configuration", {})

    # Update parameters in generation_config if provided
    config_updated = False
    if request.parameters:
        if "parameters" not in selected_config:
            selected_config["parameters"] = {}
        selected_config["parameters"]["temperature"] = request.parameters.temperature
        selected_config["parameters"]["max_tokens"] = request.parameters.max_tokens
        # Phase 6.6: persist the per-run seed so workers and audit
        # rows reflect the exact value the user requested.
        selected_config["parameters"]["seed"] = request.parameters.seed
        config_updated = True
        logger.info(
            f"Updated generation parameters for project {project_id}: "
            f"temperature={request.parameters.temperature}, "
            f"max_tokens={request.parameters.max_tokens}, "
            f"seed={request.parameters.seed}"
        )

    # Update per-model configs if provided
    if request.model_configs:
        selected_config["model_configs"] = request.model_configs
        config_updated = True
        logger.info(
            f"Updated per-model configs for project {project_id}: {list(request.model_configs.keys())}"
        )

    # Save config changes if any
    if config_updated:
        from sqlalchemy.orm.attributes import flag_modified

        generation_config["selected_configuration"] = selected_config
        project.generation_config = generation_config
        # JSONB mutation guard: SQLAlchemy doesn't detect in-place dict edits,
        # so without flag_modified the assignment above would not persist
        # (the parent dict identity didn't change). Without this, the worker
        # reads stale generation_config and falls back to SYSTEM_DEFAULTS for
        # every parameter — silently dropping the per-trigger override.
        flag_modified(project, "generation_config")
        db.add(project)
        await db.commit()

    # Get models to use
    if request.model_ids:
        model_ids = request.model_ids
    else:
        # Use all configured models
        model_ids = selected_config.get("models", [])

    if not model_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No models configured for generation"
        )

    # BYOM guard: custom ("custom-...") model ids must exist, be active, and
    # be visible to the TRIGGERING user (creator / public / org-shared /
    # superadmin). Official catalog ids pass through untouched — they keep
    # the provider-key resolution downstream.
    custom_model_ids = [m for m in model_ids if isinstance(m, str) and m.startswith("custom-")]
    if custom_model_ids:
        from models import LLMModel as DBLLMModel
        from routers.model_access import get_accessible_model_ids_async

        custom_rows = (
            await db.execute(
                select(DBLLMModel.id, DBLLMModel.is_active).where(
                    DBLLMModel.id.in_(custom_model_ids)
                )
            )
        ).all()
        active_by_id = {row_id: row_active for row_id, row_active in custom_rows}
        unusable = sorted(
            m for m in custom_model_ids
            if m not in active_by_id or not active_by_id[m]
        )
        if unusable:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown or inactive custom model(s): {', '.join(unusable)}",
            )

        accessible_ids = set(await get_accessible_model_ids_async(db, current_user))
        denied = sorted(m for m in custom_model_ids if m not in accessible_ids)
        if denied:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for custom model(s): {', '.join(denied)}",
            )

    # Validate single mode requires exactly one task and one model
    if request.mode == "single":
        if not request.task_ids or len(request.task_ids) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Single mode requires exactly one task_id",
            )
        if not request.model_ids or len(request.model_ids) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Single mode requires exactly one model_id",
            )

    # Get structure keys to use (Issue #762)
    if request.structure_keys:
        structure_keys = request.structure_keys
    else:
        # Use prompt_structures keys (matching task-status endpoint behavior)
        prompt_structures = generation_config.get("prompt_structures", {})
        if isinstance(prompt_structures, dict):
            structure_keys = list(prompt_structures.keys()) if prompt_structures else []
        elif isinstance(prompt_structures, list):
            structure_keys = [ps.get("key", str(i)) for i, ps in enumerate(prompt_structures)]
        else:
            structure_keys = []

    # Validate requested structure_keys against available structures
    if request.structure_keys:
        prompt_structures = generation_config.get("prompt_structures", {})
        if isinstance(prompt_structures, dict):
            available_keys = set(prompt_structures.keys())
        elif isinstance(prompt_structures, list):
            available_keys = {ps.get("key", str(i)) for i, ps in enumerate(prompt_structures)}
        else:
            available_keys = set()

        if available_keys:
            invalid_keys = set(request.structure_keys) - available_keys
            if invalid_keys:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown structure keys: {sorted(invalid_keys)}. Available: {sorted(available_keys)}",
                )

    # If no structures specified, use None (backward compatibility)
    if not structure_keys:
        structure_keys = [None]
        logger.info(
            f"No prompt structures configured for project {project_id}, "
            "using default generation without structure_key"
        )

    # Get tasks to process. Only IDs are needed for dispatch — loading full
    # rows pulled every Task.data JSONB blob into memory (issue #106).
    if request.task_ids:
        task_ids = [
            row[0]
            for row in (
                await db.execute(
                    select(Task.id).where(
                        Task.project_id == project_id, Task.id.in_(request.task_ids)
                    )
                )
            ).all()
        ]
    else:
        task_count = (
            await db.execute(
                select(func.count(Task.id)).where(Task.project_id == project_id)
            )
        ).scalar()
        if task_count > GENERATION_FALLBACK_MAX_TASKS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Project has {task_count} tasks, above the "
                    f"{GENERATION_FALLBACK_MAX_TASKS}-task limit for triggering "
                    "generation without explicit task_ids. Pass task_ids in batches."
                ),
            )
        task_ids = [
            row[0]
            for row in (
                await db.execute(
                    select(Task.id).where(Task.project_id == project_id)
                )
            ).all()
        ]

    if not task_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No tasks found to generate"
        )

    # Determine which task-model-structure combinations to generate
    tasks_to_queue = []

    # Issue #83: Bulk-fetch the latest status per (task_id, model_id, structure_key)
    # in a single round-trip instead of one SELECT per cell. For projects with
    # thousands of cells, the per-cell scan exceeded the browser's fetch-abort
    # threshold even though the handler completed correctly server-side.
    latest_status: Dict[tuple, str] = {}
    if request.mode == "missing":
        latest_rows = (
            await db.execute(
                select(
                    DBResponseGeneration.task_id,
                    DBResponseGeneration.model_id,
                    DBResponseGeneration.structure_key,
                    DBResponseGeneration.status,
                )
                .where(
                    DBResponseGeneration.project_id == project_id,
                    DBResponseGeneration.task_id.in_(task_ids),
                    DBResponseGeneration.model_id.in_(model_ids),
                )
                .distinct(
                    DBResponseGeneration.task_id,
                    DBResponseGeneration.model_id,
                    DBResponseGeneration.structure_key,
                )
                .order_by(
                    DBResponseGeneration.task_id,
                    DBResponseGeneration.model_id,
                    DBResponseGeneration.structure_key,
                    DBResponseGeneration.created_at.desc(),
                )
            )
        ).all()
        latest_status = {
            (r.task_id, r.model_id, r.structure_key): r.status for r in latest_rows
        }

    for task_id in task_ids:
        for model_id in model_ids:
            for structure_key in structure_keys:
                if request.mode in ("all", "single"):
                    should_generate = True
                else:  # mode == "missing"
                    latest = latest_status.get((task_id, model_id, structure_key))
                    should_generate = (latest is None) or (latest == "failed")

                if should_generate:
                    tasks_to_queue.append((task_id, model_id, structure_key))

    # When running in "all" mode, cancel existing pending/running generations for this project
    # to avoid wasting API costs on duplicates that will be overwritten
    cancelled_count = 0
    if request.mode == "all":
        # Get all pending/running generations for this project to revoke from
        # Celery. We need ``runs_requested`` AND ``dispatch_epoch`` because the
        # fan-out task ids are ``{gen_id}:{run_idx}:{epoch}`` (not the bare
        # generation id — revoking the bare id was a silent no-op). The epoch
        # pins the revoke to the CURRENT dispatch generation.
        pending_generations = (
            await db.execute(
                select(
                    DBResponseGeneration.id,
                    DBResponseGeneration.runs_requested,
                    DBResponseGeneration.dispatch_epoch,
                ).where(
                    DBResponseGeneration.project_id == project_id,
                    DBResponseGeneration.status.in_(["pending", "running"]),
                )
            )
        ).all()

        # Revoke tasks from Celery queue (non-blocking broker control call —
        # no request-DB session, stays a direct call from the async handler).
        for gen_id, runs_requested, dispatch_epoch in pending_generations:
            try:
                # Revoke the whole fan-out — removes queued tasks and SIGTERMs
                # in-flight ones, so superseded runs stop burning API budget.
                celery_app.control.revoke(
                    generation_run_task_ids(gen_id, runs_requested, dispatch_epoch),
                    terminate=True,
                )
            except Exception as e:
                logger.warning(f"Failed to revoke tasks for generation {gen_id}: {e}")

        # Mark all pending/running generations as cancelled in database
        cancelled_count = (
            await db.execute(
                update(DBResponseGeneration)
                .where(
                    DBResponseGeneration.project_id == project_id,
                    DBResponseGeneration.status.in_(["pending", "running"]),
                )
                .values(
                    status="cancelled",
                    error_message="Cancelled - superseded by new generation run",
                    completed_at=datetime.now(),
                )
                .execution_options(synchronize_session=False)
            )
        ).rowcount
        await db.commit()
        logger.info(
            f"Cancelled {cancelled_count} existing pending/running generations for project {project_id}"
        )

    # Resolve runs-per-task: per-trigger override → project default → 1.
    # Capped at 25 by the request schema; project default is also bounded
    # in the project-config router. The chosen value is stored on the
    # parent ResponseGeneration so retries and dashboard counters use the
    # value that was active when the trigger fired, not whatever the project
    # default happens to be at retry time.
    if request.runs_per_task != None:  # noqa: E711
        runs_per_task = request.runs_per_task
    else:
        runs_per_task = int(generation_config.get("runs_per_task", 1) or 1)
        runs_per_task = max(1, min(25, runs_per_task))

    # Always use parallel processing for better performance
    # Queue generation jobs
    generation_job_ids = []
    celery_tasks_to_dispatch = []

    # First, create ALL database records
    for task_id, model_id, structure_key in tasks_to_queue:
        # Create generation record
        generation_id = str(uuid.uuid4())
        generation = DBResponseGeneration(
            id=generation_id,
            project_id=project_id,
            task_id=task_id,
            model_id=model_id,
            structure_key=structure_key,  # Issue #762: Pass structure_key
            status="pending",
            runs_requested=runs_per_task,
            runs_completed=0,
            runs_failed=0,
            created_by=current_user.id,
            organization_id=org_id,  # Issue #1180: Track org context
            created_at=datetime.now(),
        )
        db.add(generation)
        generation_job_ids.append(generation_id)

        # Determine if we should force regeneration based on mode
        force_rerun = request.mode in ("all", "single")

        # Fan out N trial jobs per cell (one Celery job per run_index).
        for run_index in range(runs_per_task):
            celery_tasks_to_dispatch.append(
                (generation_id, project_id, task_id, model_id, structure_key, force_rerun, org_id, run_index)
            )

    # Commit all generation records BEFORE dispatching Celery tasks
    # This ensures workers can find the records in the database
    await db.commit()

    # Now dispatch all Celery tasks after records are committed (non-blocking
    # enqueue calls — no request-DB session, so they stay direct calls). Each
    # job gets a deterministic task id (``{gen_id}:{run_idx}:{epoch}``) so the
    # stop and supersede paths can revoke the whole fan-out from the persisted
    # ``runs_requested`` count — see generation_revoke.py. The initial fan-out is
    # always ``epoch=0`` (the row's ``dispatch_epoch`` default); resume/retry bump
    # it.
    for gen_id, proj_id, t_id, m_id, s_key, force, o_id, run_idx in celery_tasks_to_dispatch:
        send_generation_trial(
            celery_app,
            generation_id=gen_id,
            project_id=proj_id,
            task_id=t_id,
            model_id=m_id,
            structure_key=s_key,
            force_rerun=force,
            organization_id=o_id,
            run_index=run_idx,
            epoch=0,
        )

    # Estimate completion time (rough estimate for parallel processing)
    estimated_time = (
        len(tasks_to_queue) // len(model_ids) * 5 if model_ids else len(tasks_to_queue) * 5
    )

    # Count unique structures (excluding None)
    unique_structures = len([s for s in structure_keys if s is not None])
    structure_info = f" and {unique_structures} structures" if unique_structures > 0 else ""

    return GenerationResponse(
        project_id=project_id,
        mode=request.mode,
        tasks_queued=len(tasks_to_queue),
        models_count=len(model_ids),
        generation_job_ids=generation_job_ids,
        estimated_time_seconds=estimated_time,
        message=f"Queued {len(tasks_to_queue)} generation jobs for {len(model_ids)} models{structure_info}",
    )


@router.get("/generation-result", response_model=MultipleGenerationResultsResponse)
async def get_generation_result(
    request: Request,
    task_id: str = Query(..., description="Task ID"),
    model_id: str = Query(..., description="Model ID"),
    structure_key: Optional[str] = Query(None, description="Structure key (optional)"),
    include_history: bool = Query(False, description="Include all historical generations, not just the most recent per structure"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get generation results for a task-model combination.

    When structure_key is provided, returns only the result for that structure.
    When omitted, returns all structures (one result per structure_key).
    When include_history is True, returns all generations ordered newest-first
    instead of deduplicating to the most recent per structure.
    """

    # Get task to check project permissions
    task = (
        await db.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found"
        )

    # Verify user has access to the project
    await get_project_with_permissions(task.project_id, current_user, db, request)

    # Get generation records for this task-model combination
    gen_stmt = select(DBResponseGeneration).where(
        DBResponseGeneration.task_id == task_id,
        DBResponseGeneration.model_id == model_id,
    )

    if structure_key is not None:
        gen_stmt = gen_stmt.where(DBResponseGeneration.structure_key == structure_key)

    generations = (
        await db.execute(
            gen_stmt.order_by(
                DBResponseGeneration.structure_key,
                DBResponseGeneration.created_at.desc(),
            )
        )
    ).scalars().all()

    if not generations:
        return MultipleGenerationResultsResponse(
            task_id=task_id, model_id=model_id, results=[]
        )

    # Conditional deduplication (Issue #1372)
    if include_history:
        generations_to_process = generations
    else:
        # Default: group by structure_key and take most recent for each
        structure_map = {}
        for gen in generations:
            if gen.structure_key not in structure_map:
                structure_map[gen.structure_key] = gen
        generations_to_process = list(structure_map.values())

    # Batch-fetch individual Generation records (fixes N+1 query pattern)
    completed_ids = [g.id for g in generations_to_process if g.status == "completed"]
    individual_map: Dict[str, list] = defaultdict(list)
    if completed_ids:
        all_individual = (
            await db.execute(
                select(DBGeneration)
                .where(DBGeneration.generation_id.in_(completed_ids))
                .order_by(DBGeneration.created_at)
            )
        ).scalars().all()
        for g in all_individual:
            individual_map[g.generation_id].append(g)

    # Batch-resolve created_by user IDs to display names
    user_ids = {g.created_by for g in generations_to_process if g.created_by}
    user_map = {}
    if user_ids:
        users = (
            await db.execute(select(DBUser).where(DBUser.id.in_(user_ids)))
        ).scalars().all()
        user_map = {u.id: u.name for u in users}

    # Build response
    results = []
    for generation in generations_to_process:
        generation_time = None
        if generation.completed_at and generation.created_at:
            generation_time = (generation.completed_at - generation.created_at).total_seconds()

        result_data = generation.result
        if generation.status == "completed":
            individual_generations = individual_map.get(generation.id, [])
            if individual_generations:
                if len(individual_generations) > 1:
                    result_data = {
                        "generations": [
                            {
                                "generated_text": g.response_content,
                                "created_at": g.created_at.isoformat() if g.created_at else None,
                                "usage_stats": g.usage_stats,
                            }
                            for g in individual_generations
                        ]
                    }
                else:
                    g = individual_generations[0]
                    result_data = {
                        "generated_text": g.response_content,
                        "created_at": g.created_at.isoformat() if g.created_at else None,
                        "usage_stats": g.usage_stats,
                    }

        results.append(
            GenerationResultResponse(
                task_id=task_id,
                model_id=model_id,
                generation_id=generation.id,
                status=generation.status,
                result=result_data,
                generated_at=generation.completed_at or generation.created_at,
                generation_time_seconds=generation_time,
                prompt_used=generation.prompt_used,
                parameters=generation.parameters,
                error_message=generation.error_message,
                structure_key=generation.structure_key,
                created_by=generation.created_by,
                created_by_name=user_map.get(generation.created_by),
            )
        )

    return MultipleGenerationResultsResponse(task_id=task_id, model_id=model_id, results=results)
