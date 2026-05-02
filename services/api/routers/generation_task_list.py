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
from sqlalchemy import String, case, func
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from models import Generation as DBGeneration
from models import ResponseGeneration as DBResponseGeneration
from models import User as DBUser
from project_models import Project, Task
from routers.projects.helpers import (
    check_project_accessible,
    check_project_write_access,
    get_org_context_from_request,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generation-tasks", tags=["generation-tasks"])

# Celery app
from celery_client import get_celery_app

celery_app = get_celery_app()


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


def get_project_with_permissions(
    project_id: str, current_user: User, db: Session, request: Optional[Request] = None
) -> Project:
    """Get project and verify user permissions using centralized access check."""

    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    org_context = get_org_context_from_request(request) if request else None
    if not check_project_accessible(db, current_user, project_id, org_context, project=project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    return project


def get_single_task_generation_status(
    task_id: str, model_id: str, structure_key: Optional[str], db: Session
) -> TaskGenerationStatus:
    """Get generation status for a specific task-model-structure combination"""

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

    # Get preview of result if completed
    result_preview = None
    if generation.status == "completed" and generation.result:
        result_str = (
            json.dumps(generation.result)
            if isinstance(generation.result, dict)
            else str(generation.result)
        )
        result_preview = result_str[:100] + "..." if len(result_str) > 100 else result_str

    return TaskGenerationStatus(
        task_id=task_id,
        model_id=model_id,
        structure_key=structure_key,
        status=generation.status,
        generation_id=generation.id,
        generated_at=generation.completed_at or generation.created_at,
        error_message=generation.error_message if generation.status == "failed" else None,
        result_preview=result_preview,
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
    db: Session = Depends(get_db),
):
    """
    Get paginated list of tasks with generation status for each configured model.
    Feature flag: generation
    """

    # Get project and verify permissions
    project = get_project_with_permissions(project_id, current_user, db, request)

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

    # Build base query for tasks
    query = db.query(Task).filter(Task.project_id == project_id)

    # Apply search filter if provided
    if search:
        # Escape ILIKE wildcards in user input
        escaped_search = search.replace('%', r'\%').replace('_', r'\_')
        query = query.filter(func.cast(Task.data, String).ilike(f"%{escaped_search}%"))

    # When status_filter is set, we must check generation status per task before
    # paginating (status lives outside the tasks table). Load all matching tasks
    # first, filter, then paginate in Python.
    if status_filter:
        tasks = query.all()
    else:
        total = query.count()
        offset = (page - 1) * page_size
        tasks = query.offset(offset).limit(page_size).all()

    # Build response with generation status for each task
    task_responses = []
    for task in tasks:
        # Get generation status for each model-structure combination
        generation_status = {}
        for model_id in model_ids:
            model_statuses = []
            for structure_key in structure_keys:
                task_status = get_single_task_generation_status(
                    task.id, model_id, structure_key, db
                )
                model_statuses.append(task_status.model_dump() if task_status else None)
            generation_status[model_id] = model_statuses

        # Apply status filter if provided
        if status_filter:
            if status_filter == "not_generated":
                has_matching_status = any(
                    any(
                        not status_obj or status_obj.get('status') is None
                        for status_obj in statuses_list
                    )
                    for statuses_list in generation_status.values()
                )
            else:
                has_matching_status = any(
                    any(
                        status_obj and status_obj.get('status') == status_filter
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

    # When status_filter is active, paginate the filtered results in Python
    if status_filter:
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
    db: Session = Depends(get_db),
):
    """
    Start bulk generation for all or missing task-model combinations.
    Uses parallel processing for optimal performance.
    Feature flag: generation
    """

    # Get project and verify permissions
    project = get_project_with_permissions(project_id, current_user, db, raw_request)

    # Starting generation is a contribute-level action — block public-tier
    # ANNOTATOR visitors, allow CONTRIBUTOR / org members / creator / superadmin.
    if not check_project_write_access(db, current_user, project_id):
        raise HTTPException(
            status_code=403,
            detail="Only contributors or admins can start generation for this project",
        )

    # Extract organization context for API key resolution (Issue #1180)
    org_context = raw_request.headers.get("X-Organization-Context")
    org_id = org_context if org_context and org_context != "private" else None

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
        config_updated = True
        logger.info(
            f"Updated generation parameters for project {project_id}: "
            f"temperature={request.parameters.temperature}, max_tokens={request.parameters.max_tokens}"
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
        generation_config["selected_configuration"] = selected_config
        project.generation_config = generation_config
        db.add(project)
        db.commit()

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

    # Get tasks to process
    if request.task_ids:
        tasks = (
            db.query(Task)
            .filter(Task.project_id == project_id, Task.id.in_(request.task_ids))
            .all()
        )
    else:
        tasks = db.query(Task).filter(Task.project_id == project_id).all()

    if not tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No tasks found to generate"
        )

    # Determine which task-model-structure combinations to generate
    tasks_to_queue = []

    for task in tasks:
        for model_id in model_ids:
            for structure_key in structure_keys:
                # Check if we should generate this combination
                should_generate = False

                if request.mode in ("all", "single"):
                    should_generate = True
                else:  # mode == "missing"
                    # Check the MOST RECENT generation for this task-model-structure combination
                    # This allows retrying failed tasks even if older completed records exist
                    query = db.query(DBResponseGeneration).filter(
                        DBResponseGeneration.task_id == task.id,
                        DBResponseGeneration.model_id == model_id,
                    )

                    # Add structure_key filter if specified
                    if structure_key is not None:
                        query = query.filter(DBResponseGeneration.structure_key == structure_key)
                    else:
                        # For backward compatibility, check for NULL structure_key
                        query = query.filter(DBResponseGeneration.structure_key.is_(None))

                    # Get the most recent record by created_at
                    latest = query.order_by(DBResponseGeneration.created_at.desc()).first()

                    # Generate if no record exists OR if the latest record failed
                    should_generate = (latest is None) or (latest.status == "failed")

                if should_generate:
                    tasks_to_queue.append((task.id, model_id, structure_key))

    # When running in "all" mode, cancel existing pending/running generations for this project
    # to avoid wasting API costs on duplicates that will be overwritten
    cancelled_count = 0
    if request.mode == "all":
        # Get all pending/running generation IDs for this project to revoke from Celery
        pending_generations = (
            db.query(DBResponseGeneration)
            .filter(
                DBResponseGeneration.project_id == project_id,
                DBResponseGeneration.status.in_(["pending", "running"]),
            )
            .all()
        )

        # Revoke tasks from Celery queue
        for gen in pending_generations:
            try:
                # Revoke the task - this removes it from queue if not started
                celery_app.control.revoke(gen.id, terminate=False)
            except Exception as e:
                logger.warning(f"Failed to revoke task {gen.id}: {e}")

        # Mark all pending/running generations as cancelled in database
        cancelled_count = (
            db.query(DBResponseGeneration)
            .filter(
                DBResponseGeneration.project_id == project_id,
                DBResponseGeneration.status.in_(["pending", "running"]),
            )
            .update(
                {
                    "status": "cancelled",
                    "error_message": "Cancelled - superseded by new generation run",
                    "completed_at": datetime.now(),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        logger.info(
            f"Cancelled {cancelled_count} existing pending/running generations for project {project_id}"
        )

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
            created_by=current_user.id,
            organization_id=org_id,  # Issue #1180: Track org context
            created_at=datetime.now(),
        )
        db.add(generation)
        generation_job_ids.append(generation_id)

        # Determine if we should force regeneration based on mode
        force_rerun = request.mode in ("all", "single")

        # Collect task info for later dispatch
        celery_tasks_to_dispatch.append(
            (generation_id, project_id, task_id, model_id, structure_key, force_rerun, org_id)
        )

    # Commit all generation records BEFORE dispatching Celery tasks
    # This ensures workers can find the records in the database
    db.commit()

    # Now dispatch all Celery tasks after records are committed
    for gen_id, proj_id, t_id, m_id, s_key, force, o_id in celery_tasks_to_dispatch:
        celery_app.send_task(
            "tasks.generate_response",
            args=[gen_id, proj_id, t_id, m_id, s_key, force, o_id],
            queue="generation",
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
    db: Session = Depends(get_db),
):
    """
    Get generation results for a task-model combination.

    When structure_key is provided, returns only the result for that structure.
    When omitted, returns all structures (one result per structure_key).
    When include_history is True, returns all generations ordered newest-first
    instead of deduplicating to the most recent per structure.
    """

    # Get task to check project permissions
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found"
        )

    # Verify user has access to the project
    get_project_with_permissions(task.project_id, current_user, db, request)

    # Get generation records for this task-model combination
    query = db.query(DBResponseGeneration).filter(
        DBResponseGeneration.task_id == task_id,
        DBResponseGeneration.model_id == model_id,
    )

    if structure_key is not None:
        query = query.filter(DBResponseGeneration.structure_key == structure_key)

    generations = query.order_by(
        DBResponseGeneration.structure_key, DBResponseGeneration.created_at.desc()
    ).all()

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
            db.query(DBGeneration)
            .filter(DBGeneration.generation_id.in_(completed_ids))
            .order_by(DBGeneration.created_at)
            .all()
        )
        for g in all_individual:
            individual_map[g.generation_id].append(g)

    # Batch-resolve created_by user IDs to display names
    user_ids = {g.created_by for g in generations_to_process if g.created_by}
    user_map = {}
    if user_ids:
        users = db.query(DBUser).filter(DBUser.id.in_(user_ids)).all()
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
