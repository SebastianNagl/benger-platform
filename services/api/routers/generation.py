"""
Generation endpoints.
Handles LLM response generation and generation configurations.

Issue #759: Database prompts system removed in favor of generation_structure.
All prompt configuration is now handled via project.generation_structure JSONB field.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import case as sa_case, delete, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from auth_module import User, WebSocketAuthError, require_user, verify_token_for_websocket
from auth_module.user_service import get_user_by_id
from database import get_async_db, get_db
from models import Generation as DBLLMResponse
from models import ResponseGeneration as DBResponseGeneration
from project_models import Task
from redis_cache import get_redis_client
from routers.generation_revoke import (
    generation_run_task_ids,
    send_generation_trial,
)
from routers.projects.helpers import (
    check_project_accessible,
    check_project_accessible_async,
    get_accessible_project_ids_async,
    get_org_context_from_request,
)


router = APIRouter(prefix="/api/generation", tags=["generation"])

# WebSocket router for real-time updates (separate prefix to avoid /api/generation/ws nesting)
ws_router = APIRouter(prefix="/api/ws", tags=["websocket"])

# Celery app
from celery_client import get_celery_app  # noqa: E402

celery_app = get_celery_app()

# Environment configuration
from app.core.config import get_settings  # noqa: E402


logger = logging.getLogger(__name__)
ENVIRONMENT = get_settings().environment


# ============= Helper Functions =============


# REFACTORED: Replaced duplicate permission logic with centralized authorization service
# The _user_can_edit_project function has been replaced with auth_service.can_edit_project()
# This eliminates code duplication and provides consistent permission checking across the application


# ============= Request/Response Models =============


class EvaluationStatus(BaseModel):
    """Model for evaluation/generation status"""

    id: str
    status: str  # pending, running, completed, failed, stopped
    message: Optional[str] = None
    progress: Optional[float] = None


class GenerationConfigCreate(BaseModel):
    """Request model for creating generation configuration"""

    project_id: str = Field(..., description="Project ID this configuration belongs to")
    llm_model_ids: List[str] = Field(..., description="List of LLM model IDs to use for generation")
    generation_prompts: Optional[Dict[str, str]] = Field(
        None, description="Optional custom prompts for generation"
    )
    model_configs: Optional[Dict[str, Dict[str, Any]]] = Field(
        None, description="Model-specific configurations"
    )


class GenerationConfigUpdate(BaseModel):
    """Request model for updating generation configuration"""

    llm_model_ids: Optional[List[str]] = Field(
        None, description="List of LLM model IDs to use for generation"
    )
    generation_prompts: Optional[Dict[str, str]] = Field(
        None, description="Optional custom prompts for generation"
    )
    model_configs: Optional[Dict[str, Dict[str, Any]]] = Field(
        None, description="Model-specific configurations"
    )
    is_active: Optional[bool] = Field(None, description="Whether the configuration is active")


class GenerationConfigResponse(BaseModel):
    """Response model for generation configuration"""

    id: str
    project_id: str
    llm_model_ids: List[str]
    generation_prompts: Optional[Dict[str, str]] = None
    model_configs: Optional[Dict[str, Dict[str, Any]]] = None
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class GenerateFromConfigRequest(BaseModel):
    """Request model for generating responses using a generation config"""

    force_rerun: bool = Field(
        False, description="Force re-generation even if responses already exist"
    )


class GenerateFromConfigResponse(BaseModel):
    """Response model for generation using generation config"""

    config_id: str
    project_id: str
    generation_ids: List[str]
    status: str
    message: str
    started_at: datetime


# ============= Generation Status Endpoints =============


@router.get("/status/{generation_id}", response_model=EvaluationStatus)
async def get_generation_status(
    generation_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get the status of a specific response generation job
    """
    generation = (
        await db.execute(
            select(DBResponseGeneration).where(DBResponseGeneration.id == generation_id)
        )
    ).scalar_one_or_none()

    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response generation '{generation_id}' not found",
        )

    # Check project access via the generation's task
    task = (
        await db.execute(select(Task).where(Task.id == generation.task_id))
    ).scalar_one_or_none()
    org_context = get_org_context_from_request(request)
    if task and not await check_project_accessible_async(
        db, current_user, task.project_id, org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this generation's project",
        )

    return EvaluationStatus(
        id=generation.id,
        status=generation.status,
        message=generation.error_message or "Generation status",
        progress=None,  # Could be enhanced later with actual progress
    )


@router.post("/{generation_id}/stop")
async def stop_generation(
    generation_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Stop a running or pending generation

    Celery dispatch note: ``celery_app.control.revoke`` is a non-blocking
    broker control call (no request-DB session); it stays a direct call after
    the awaited DB commit, exactly as the sync version ordered it.
    """
    try:
        # Get the generation record
        generation = (
            await db.execute(
                select(DBResponseGeneration).where(DBResponseGeneration.id == generation_id).with_for_update()
            )
        ).scalar_one_or_none()

        if not generation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found"
            )

        # Check if user owns this generation or is superadmin
        if not current_user.is_superadmin and generation.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only stop your own generations",
            )

        # Only allow stopping pending/running generations
        if generation.status not in ["pending", "running"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot stop generation with status: {generation.status}",
            )

        # Update generation status
        generation.status = "stopped"
        generation.completed_at = datetime.now()
        generation.error_message = f"Stopped by user {current_user.username}"

        await db.commit()

        # Revoke the whole fan-out so a stopped generation actually stops
        # burning API budget. Every dispatch path (initial + resume/retry) fans
        # out ``tasks.generate_response`` jobs with deterministic ids
        # (``{gen_id}:{run_idx}:{epoch}``); reconstruct them from
        # ``runs_requested`` + the CURRENT ``dispatch_epoch``. ``terminate=True``
        # SIGTERMs in-flight trials and drops queued ones.
        try:
            celery_app.control.revoke(
                generation_run_task_ids(
                    generation_id, generation.runs_requested, generation.dispatch_epoch
                ),
                terminate=True,
            )
        except Exception as revoke_error:
            logger.warning(f"Could not revoke Celery tasks: {revoke_error}")

        return {
            "message": "Generation stopped successfully",
            "generation_id": generation_id,
            "status": "stopped",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping generation {generation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error stopping generation: {str(e)}",
        )


@router.post("/{generation_id}/pause")
async def pause_generation(
    generation_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Pause a running generation
    """
    try:
        # Get the generation record
        generation = (
            await db.execute(
                select(DBResponseGeneration).where(DBResponseGeneration.id == generation_id).with_for_update()
            )
        ).scalar_one_or_none()

        if not generation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found"
            )

        # Check if user owns this generation or is superadmin
        if not current_user.is_superadmin and generation.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only pause your own generations",
            )

        # Only allow pausing running generations
        if generation.status != "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot pause generation with status: {generation.status}",
            )

        # Update generation status
        generation.status = "paused"
        generation.paused_at = datetime.now()

        await db.commit()

        # Actually stop the in-flight work — pause is a no-op otherwise: the
        # worker would run to completion and the derived finalization would
        # overwrite "paused" with "completed"/"failed". Revoke the whole fan-out
        # (same deterministic-id scheme as stop, pinned to the CURRENT epoch); the
        # worker also honors the "paused" DB status as a backstop, and resume
        # bumps the epoch and re-dispatches whatever run_indices aren't yet done.
        try:
            celery_app.control.revoke(
                generation_run_task_ids(
                    generation_id, generation.runs_requested, generation.dispatch_epoch
                ),
                terminate=True,
            )
        except Exception as revoke_error:
            logger.warning(f"Could not revoke Celery tasks on pause: {revoke_error}")

        return {
            "message": "Generation paused successfully",
            "generation_id": generation_id,
            "status": "paused",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing generation {generation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error pausing generation: {str(e)}",
        )


async def _prepare_missing_trials(db: AsyncSession, generation) -> list:
    """Reconcile a generation's DB state for a re-run and return the run_indices
    still to generate. The caller bumps ``dispatch_epoch`` and commits BEFORE
    dispatching (via :func:`_commit_and_dispatch`) so the worker reads the
    reconciled state, never a half-written one.

    Both resume and retry use this so a multi-run generation
    (``runs_requested > 1``) regenerates ALL its missing trials — not just
    ``run_index=0``, which is all the old single-job dispatch did.

    "Missing" == a run_index with NO child row yet. A run_index that produced a
    child of ANY status (``completed``, ``parse_failed``, …) is considered
    present — exactly how the worker's ``COUNT(DISTINCT run_index)`` derivation
    counts it. So we re-dispatch only the truly-missing (failed-without-a-row)
    trials and never DELETE an existing child: parse-failure provenance and the
    ``TaskEvaluation.generation_id`` links of kept trials survive a retry, and
    there is no stale child to collide with on ``uq(generation_id, run_index)``.

    Revoking the prior fan-out's survivors is the CALLER's job, done AFTER the
    commit (off the row lock) — see :func:`_commit_and_dispatch`. We do not revoke
    here: that would hold the ``FOR UPDATE`` lock across a synchronous broker call
    on the event loop.

    ``runs_completed`` is reconciled to the count of present trials and
    ``runs_failed`` reset to 0; the worker re-derives both as the re-dispatched
    trials finish.
    """
    runs_requested = generation.runs_requested or 1

    present_run_indices = set(
        (
            await db.execute(
                select(DBLLMResponse.run_index)
                .where(DBLLMResponse.generation_id == generation.id)
                .distinct()
            )
        ).scalars().all()
    )
    missing = [i for i in range(runs_requested) if i not in present_run_indices]

    # Clamp to runs_requested so a corrupt over-count can't leave the parent
    # stuck (a prior bug could persist a run_index >= runs_requested).
    generation.runs_completed = min(len(present_run_indices), runs_requested)
    generation.runs_failed = 0
    return missing


def _dispatch_generation_trials(generation, run_indices: list) -> None:
    """Fan out one ``tasks.generate_response`` per run_index with the
    deterministic, epoch-stamped task id ``{gen_id}:{run_idx}:{epoch}`` (revocable
    by stop/pause/supersede). Reads ``generation.dispatch_epoch`` — the caller must
    have bumped it to the NEW epoch before commit so these ids weren't in the
    prior epoch's revoked set. ``force_rerun=True`` because the runs are
    known-missing; a residual race where a slow survivor re-writes the run_index
    is caught idempotently by the worker's ``uq(generation_id, run_index)``
    collision handling. Call AFTER the DB commit (``AsyncSessionLocal`` is
    ``expire_on_commit=False``, so the generation's attributes stay loaded)."""
    epoch = generation.dispatch_epoch or 0
    for run_index in run_indices:
        send_generation_trial(
            celery_app,
            generation_id=generation.id,
            project_id=generation.project_id,
            task_id=generation.task_id,
            model_id=generation.model_id,
            structure_key=generation.structure_key,
            force_rerun=True,  # the run is known-missing
            organization_id=generation.organization_id,
            run_index=run_index,
            epoch=epoch,
        )


async def _commit_and_dispatch(
    db: AsyncSession, generation, missing: list, prior_epoch: int
) -> None:
    """Commit the reconciled state, then (off the row lock) revoke the prior
    epoch's survivors and fan out the missing trials at the new epoch.

    Ordering matters:
    1. ``commit`` first — releases the ``FOR UPDATE`` lock so the subsequent
       synchronous broker calls don't pin it on the event loop (and the worker
       reads a fully reconciled row).
    2. Revoke the PRIOR epoch's fan-out (best-effort) to stop any survivor still
       burning API budget. This can't discard the re-dispatch below: that runs at
       ``dispatch_epoch`` (already bumped), a different id than ``prior_epoch``.
    3. Dispatch the missing trials. If the broker fails mid-dispatch, flip the
       generation to ``failed`` (retry-eligible) and commit that — otherwise a
       partial dispatch would strand it in ``running`` with no API recovery path
       (retry only accepts failed/stopped).
    """
    await db.commit()

    try:
        celery_app.control.revoke(
            generation_run_task_ids(
                generation.id, generation.runs_requested, prior_epoch
            ),
            terminate=True,
        )
    except Exception as revoke_error:
        logger.warning(
            f"Could not revoke prior fan-out (epoch {prior_epoch}) for "
            f"{generation.id}: {revoke_error}"
        )

    try:
        _dispatch_generation_trials(generation, missing)
    except Exception as dispatch_error:
        logger.error(
            f"Dispatch failed for generation {generation.id}: {dispatch_error}"
        )
        generation.status = "failed"
        generation.error_message = f"Dispatch failed: {dispatch_error}"
        generation.completed_at = datetime.now()
        await db.commit()
        raise


@router.post("/{generation_id}/resume")
async def resume_generation(
    generation_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Resume a paused generation

    Celery dispatch note: ``celery_app.send_task`` is a non-blocking enqueue
    (no request-DB session); it is called directly between the awaited DB
    commits, exactly as the sync version ordered it.
    """
    try:
        # Get the generation record
        generation = (
            await db.execute(
                select(DBResponseGeneration).where(DBResponseGeneration.id == generation_id).with_for_update()
            )
        ).scalar_one_or_none()

        if not generation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found"
            )

        # Check if user owns this generation or is superadmin
        if not current_user.is_superadmin and generation.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only resume your own generations",
            )

        # Only allow resuming paused generations
        if generation.status != "paused":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot resume generation with status: {generation.status}",
            )

        generation.status = "running"
        generation.resumed_at = datetime.now()

        # Compute the run_indices with no child yet (handles multi-run: the old
        # code re-ran only run_index=0).
        missing = await _prepare_missing_trials(db, generation)
        if not missing:
            # Nothing left to generate — the run is already complete. Short-circuit
            # WITHOUT bumping the epoch or hitting the broker: every run_index
            # already produced a child, so there are no survivors to revoke and no
            # trials to dispatch.
            generation.status = "completed"
            generation.completed_at = datetime.now()
            await db.commit()
            return {
                "message": "Generation resumed successfully",
                "generation_id": generation_id,
                "status": generation.status,
            }

        # Bump the dispatch epoch so the re-dispatched trials get FRESH task ids
        # the prior (paused) epoch's revoke can't discard. Capture the prior epoch
        # so _commit_and_dispatch can revoke its survivors off the lock.
        prior_epoch = generation.dispatch_epoch or 0
        generation.dispatch_epoch = prior_epoch + 1
        await _commit_and_dispatch(db, generation, missing, prior_epoch)

        return {
            "message": "Generation resumed successfully",
            "generation_id": generation_id,
            "status": generation.status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming generation {generation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resuming generation: {str(e)}",
        )


@router.post("/{generation_id}/retry")
async def retry_generation(
    generation_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Retry a failed or stopped generation

    Celery dispatch note: ``celery_app.send_task`` is a non-blocking enqueue
    (no request-DB session); it is called directly between the awaited DB
    commits, exactly as the sync version ordered it.
    """
    try:
        # Get the generation record
        generation = (
            await db.execute(
                select(DBResponseGeneration).where(DBResponseGeneration.id == generation_id).with_for_update()
            )
        ).scalar_one_or_none()

        if not generation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found"
            )

        # Check if user owns this generation or is superadmin
        if not current_user.is_superadmin and generation.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only retry your own generations",
            )

        # Only allow retrying failed or stopped generations
        if generation.status not in ["failed", "stopped"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot retry generation with status: {generation.status}",
            )

        # Reset the lifecycle fields, then re-dispatch every run_index that has
        # no child yet (multi-run: the old code re-ran only run_index=0 via a
        # single umbrella job). _prepare_missing_trials reconciles the counters;
        # _commit_and_dispatch revokes the prior epoch's survivors off the lock.
        generation.status = "running"
        generation.error_message = None
        generation.completed_at = None
        generation.retry_count = (generation.retry_count or 0) + 1

        missing = await _prepare_missing_trials(db, generation)
        if not missing:
            # Every trial already produced a row — nothing to retry. Short-circuit
            # WITHOUT bumping the epoch or hitting the broker (no survivors, no
            # dispatch). retry_count still increments (the user did request it).
            generation.status = "completed"
            generation.completed_at = datetime.now()
            await db.commit()
            return {
                "message": "Generation retry started successfully",
                "generation_id": generation_id,
                "status": generation.status,
                "retry_count": generation.retry_count,
            }

        # Bump the dispatch epoch so re-dispatched trials get fresh, un-revoked
        # task ids; capture the prior epoch for the survivor revoke.
        prior_epoch = generation.dispatch_epoch or 0
        generation.dispatch_epoch = prior_epoch + 1
        await _commit_and_dispatch(db, generation, missing, prior_epoch)

        return {
            "message": "Generation retry started successfully",
            "generation_id": generation_id,
            "status": generation.status,
            "retry_count": generation.retry_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying generation {generation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrying generation: {str(e)}",
        )


@router.delete("/{generation_id}")
async def delete_generation(
    generation_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Delete a generation record and its associated responses
    """
    try:
        # Get the generation record
        generation = (
            await db.execute(
                select(DBResponseGeneration).where(DBResponseGeneration.id == generation_id).with_for_update()
            )
        ).scalar_one_or_none()

        if not generation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found"
            )

        # Check if user owns this generation or is superadmin
        if not current_user.is_superadmin and generation.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own generations",
            )

        # Don't allow deleting running generations
        if generation.status == "running":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete running generation. Stop it first.",
            )

        # Delete associated LLM responses
        deleted_responses = (
            await db.execute(
                delete(DBLLMResponse)
                .where(DBLLMResponse.generation_id == generation_id)
                .execution_options(synchronize_session=False)
            )
        ).rowcount

        # Delete the generation record
        await db.delete(generation)
        await db.commit()

        return {
            "message": "Generation deleted successfully",
            "generation_id": generation_id,
            "deleted_responses": deleted_responses,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting generation {generation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting generation: {str(e)}",
        )


# ============= Parse Metrics Endpoints =============


@router.get("/parse-metrics")
async def get_parse_metrics(
    request: Request,
    project_id: Optional[str] = None,
    model_id: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
):
    """Get parsing success/failure metrics for LLM responses

    Returns metrics about how well LLM responses are being parsed, including:
    - Parse success/failure rates
    - Validation errors
    - Average retries until success
    - Common parse errors

    Can be filtered by project_id and/or model_id.
    """
    # Verify project access if project_id is provided
    org_context = get_org_context_from_request(request)
    if project_id and not await check_project_accessible_async(
        db, current_user, project_id, org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    try:
        # Build the shared WHERE-clause filters once; reuse across the three
        # aggregation selects below. A `.join(DBResponseGeneration)` is added
        # only on the project-scoped branches (mirrors the sync query chain).
        needs_join = False
        where_clauses = []

        # Apply filters if provided
        if project_id:
            needs_join = True
            where_clauses.append(DBResponseGeneration.project_id == project_id)
        else:
            # Scope by org context when no specific project_id provided
            org_context = request.headers.get("X-Organization-Context", "private")
            # Cross-project metrics view; preserve legacy "superadmin sees
            # everything" semantics. Narrowing only applies to /api/projects.
            accessible_ids = await get_accessible_project_ids_async(
                db, current_user, org_context, include_all_private=True
            )
            if accessible_ids is not None:
                if not accessible_ids:
                    return {
                        "total_generations": 0,
                        "parse_success": 0,
                        "parse_failed": 0,
                        "parse_validation_error": 0,
                        "parse_failed_max_retries": 0,
                        "parse_success_rate": 0,
                        "avg_retries_until_success": 0,
                        "common_parse_errors": [],
                    }
                needs_join = True
                where_clauses.append(
                    DBResponseGeneration.project_id.in_(accessible_ids)
                )

        if model_id:
            where_clauses.append(DBLLMResponse.model_id == model_id)

        def _apply_scope(stmt):
            """Attach the shared join + filters to a select() over DBLLMResponse."""
            if needs_join:
                stmt = stmt.join(
                    DBResponseGeneration,
                    DBLLMResponse.generation_id == DBResponseGeneration.id,
                )
            if where_clauses:
                stmt = stmt.where(*where_clauses)
            return stmt

        # All five counts in one aggregation pass — previously ran as five
        # separate `query.filter(...).count()` calls, each a full scan of
        # the filtered set. `SUM(CASE WHEN ...)` collapses them to one row.
        agg_stmt = _apply_scope(
            select(
                sa_func.count(DBLLMResponse.id).label("total"),
                sa_func.coalesce(
                    sa_func.sum(
                        sa_case((DBLLMResponse.parse_status == "success", 1), else_=0)
                    ),
                    0,
                ).label("success"),
                sa_func.coalesce(
                    sa_func.sum(
                        sa_case((DBLLMResponse.parse_status == "failed", 1), else_=0)
                    ),
                    0,
                ).label("failed"),
                sa_func.coalesce(
                    sa_func.sum(
                        sa_case(
                            (DBLLMResponse.parse_status == "validation_error", 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("validation_error"),
                sa_func.coalesce(
                    sa_func.sum(
                        sa_case(
                            (DBLLMResponse.status == "parse_failed_max_retries", 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("max_retries"),
            ).select_from(DBLLMResponse)
        )
        agg_row = (await db.execute(agg_stmt)).one()

        total = int(agg_row.total or 0)
        success = int(agg_row.success or 0)
        failed = int(agg_row.failed or 0)
        validation_error = int(agg_row.validation_error or 0)
        max_retries = int(agg_row.max_retries or 0)

        if total == 0:
            return {
                "total_generations": 0,
                "parse_success": 0,
                "parse_failed": 0,
                "parse_validation_error": 0,
                "parse_failed_max_retries": 0,
                "parse_success_rate": 0,
                "avg_retries_until_success": 0,
                "common_parse_errors": [],
            }

        # Average retries for successful parses — fetch only the column we
        # need, not the full row (parse_metadata can be a heavy JSON blob).
        avg_retries = 0
        if success:
            metadata_stmt = _apply_scope(
                select(DBLLMResponse.parse_metadata)
                .select_from(DBLLMResponse)
                .where(DBLLMResponse.parse_status == "success")
            )
            metadata_rows = (await db.execute(metadata_stmt)).all()
            total_retries = sum(
                (md or {}).get("retry_count", 1) for (md,) in metadata_rows
            )
            # `if metadata_rows` is truthy even when `len(metadata_rows) == 0`
            # if the value is a Mock or other truthy-empty container, which
            # gave a ZeroDivisionError under unit tests. Check the length
            # directly so the guard matches the divisor.
            avg_retries = (
                total_retries / len(metadata_rows)
                if len(metadata_rows) > 0
                else 0
            )

        # Common parse errors — group in SQL instead of streaming every
        # failed row to Python. ORDER BY DESC + LIMIT keeps the top-5 in
        # the database.
        error_label = sa_func.coalesce(
            DBLLMResponse.parse_error, "Unknown error"
        ).label("error")
        error_stmt = (
            _apply_scope(
                select(
                    error_label,
                    sa_func.count(DBLLMResponse.id).label("count"),
                )
                .select_from(DBLLMResponse)
                .where(
                    DBLLMResponse.parse_status.in_(["failed", "validation_error"])
                )
            )
            .group_by("error")
            .order_by(sa_func.count(DBLLMResponse.id).desc())
            .limit(5)
        )
        error_rows = (await db.execute(error_stmt)).all()
        common_errors = [{"error": e, "count": int(c)} for e, c in error_rows]

        return {
            "total_generations": total,
            "parse_success": success,
            "parse_failed": failed,
            "parse_validation_error": validation_error,
            "parse_failed_max_retries": max_retries,
            "parse_success_rate": success / total if total > 0 else 0,
            "avg_retries_until_success": avg_retries,
            "common_parse_errors": common_errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting parse metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch parse metrics: {str(e)}",
        )


# ============= WebSocket Endpoints =============


@ws_router.websocket("/projects/{project_id}/generation-progress")
async def generation_progress_websocket(
    websocket: WebSocket,
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    WebSocket endpoint for real-time generation progress updates.
    Clients connect to receive live updates about generation status.

    Auth: cookie-based JWT validated before `accept()`. `db` is taken via
    Depends so test dependency overrides apply; we close it explicitly
    after the access check so it does NOT linger for the WS lifetime.
    The polling fallback opens fresh sessions per iteration instead of
    holding one across `await asyncio.sleep(2)` (see 2026-05-18 postmortem).

    Stays SYNC (``Depends(get_db)``): this handler owns its own session
    lifecycle — it ``db.close()``es the auth session before the upgrade and
    spins up a fresh per-iteration sync session (``next(get_db())``) inside
    the polling loop so no connection is held across ``asyncio.sleep``. That
    explicit open/close-per-iteration model + the sync ``get_user_by_id`` /
    ``check_project_accessible`` calls don't have async twins that fit the WS
    lifecycle cleanly, so it is left on the sync lane.
    """
    # Authenticate + authorize BEFORE the upgrade.
    try:
        payload = verify_token_for_websocket(websocket)
    except WebSocketAuthError as e:
        logger.info(f"WS auth rejected for project {project_id}: {e}")
        await websocket.close(code=4401)
        return

    user_id = payload.get("user_id")
    try:
        user = get_user_by_id(db, user_id) if user_id else None
        if not user or not check_project_accessible(db, user, project_id):
            await websocket.close(code=4403)
            return
    finally:
        db.close()

    await websocket.accept()

    redis_client = None
    pubsub = None

    try:
        # Initialize Redis connection for pub/sub
        redis_client = get_redis_client()

        # Subscribe to project-specific generation channel
        channel_name = f"generation:progress:{project_id}"

        # Use async Redis if available
        if hasattr(redis_client, 'pubsub'):
            import redis.asyncio as redis_async

            # Forward every connection arg the sync client used (host, port,
            # db, password, ssl, etc.) so the async pubsub client AUTHs the
            # same way. Prior shape dropped the password — subscribes
            # appeared to succeed but the server never actually registered
            # the subscription, so PUBLISH returned 0 subscribers and no
            # update ever reached the WS client. See the matching fix in
            # routers/evaluations/ws.py (commit b6529dc).
            kwargs = dict(redis_client.connection_pool.connection_kwargs)
            kwargs.pop("connection_class", None)
            kwargs["decode_responses"] = True
            async_redis = redis_async.Redis(**kwargs)
            pubsub = async_redis.pubsub()
            await pubsub.subscribe(channel_name)

            # Send initial connection confirmation
            await websocket.send_json(
                {
                    "type": "connection",
                    "status": "connected",
                    "project_id": project_id,
                    "message": "Connected to generation progress updates",
                }
            )

            # Listen for messages from Redis and forward to WebSocket
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        # Parse the message data
                        data = json.loads(message['data'])

                        # Forward to WebSocket client
                        await websocket.send_json(data)

                        # If generation is complete, we can close after a delay
                        if data.get('status') in ['completed', 'failed', 'stopped']:
                            await asyncio.sleep(2)  # Give client time to process
                            break

                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse Redis message: {message['data']}")
                    except Exception as e:
                        logger.error(f"Error forwarding message to WebSocket: {e}")
        else:
            # Fallback: Poll database for status updates
            await websocket.send_json(
                {
                    "type": "connection",
                    "status": "connected_polling",
                    "project_id": project_id,
                    "message": "Connected with polling fallback",
                }
            )

            while True:
                try:
                    # Open a per-iteration session so we never hold a
                    # connection across `await asyncio.sleep(2)`. The fallback
                    # path runs whenever Redis is unavailable; same pool-leak
                    # rules apply as the primary path.
                    poll_db = next(get_db())
                    try:
                        generations = (
                            poll_db.query(DBResponseGeneration)
                            .filter(DBResponseGeneration.project_id == project_id)
                            .order_by(DBResponseGeneration.created_at.desc())
                            .limit(5)
                            .all()
                        )
                    finally:
                        poll_db.close()

                    if generations:
                        # Send status update
                        status_data = {
                            "type": "progress",
                            "project_id": project_id,
                            "generations": [
                                {
                                    "id": gen.id,
                                    "model_id": gen.model_id,
                                    "status": gen.status,
                                    "progress": getattr(gen, 'progress', None),
                                    "message": gen.error_message
                                    if gen.status == "failed"
                                    else None,
                                }
                                for gen in generations
                            ],
                            "timestamp": datetime.now().isoformat(),
                        }

                        await websocket.send_json(status_data)

                        # Check if all generations are complete
                        all_complete = all(
                            gen.status in ['completed', 'failed', 'stopped'] for gen in generations
                        )

                        if all_complete:
                            await websocket.send_json(
                                {
                                    "type": "complete",
                                    "project_id": project_id,
                                    "message": "All generation tasks completed",
                                    "generations": status_data["generations"],
                                }
                            )
                            break

                    # Poll every 2 seconds
                    await asyncio.sleep(2)

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error in WebSocket polling loop: {e}")
                    await asyncio.sleep(2)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for project {project_id}")
    except Exception as e:
        logger.error(f"WebSocket error for project {project_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "message": f"WebSocket error: {str(e)}"})
        except:  # noqa: E722
            pass
    finally:
        # Cleanup
        if pubsub:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

        # Close WebSocket if still open
        try:
            await websocket.close()
        except:  # noqa: E722
            pass

        logger.info(f"WebSocket connection closed for project {project_id}")
