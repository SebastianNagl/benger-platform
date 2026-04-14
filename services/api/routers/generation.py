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
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from models import Generation as DBLLMResponse
from models import ResponseGeneration as DBResponseGeneration
from project_models import Project, Task
from redis_cache import get_redis_client
from routers.projects.helpers import check_project_accessible, get_accessible_project_ids, get_org_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generation", tags=["generation"])

# WebSocket router for real-time updates (separate prefix to avoid /api/generation/ws nesting)
ws_router = APIRouter(prefix="/api/ws", tags=["websocket"])

# Celery app
from celery_client import get_celery_app

celery_app = get_celery_app()

# Environment configuration
import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


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
    db: Session = Depends(get_db),
):
    """
    Get the status of a specific response generation job
    """
    generation = (
        db.query(DBResponseGeneration).filter(DBResponseGeneration.id == generation_id).first()
    )

    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response generation '{generation_id}' not found",
        )

    # Check project access via the generation's task
    task = db.query(Task).filter(Task.id == generation.task_id).first()
    org_context = get_org_context_from_request(request)
    if task and not check_project_accessible(db, current_user, task.project_id, org_context):
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
    db: Session = Depends(get_db),
):
    """
    Stop a running or pending generation
    """
    try:
        # Get the generation record
        generation = (
            db.query(DBResponseGeneration).filter(DBResponseGeneration.id == generation_id).first()
        )

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

        db.commit()

        # Try to revoke the Celery task if it exists
        try:
            celery_app.control.revoke(generation.celery_task_id, terminate=True)
        except Exception as revoke_error:
            logger.warning(f"Could not revoke Celery task: {revoke_error}")

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
    db: Session = Depends(get_db),
):
    """
    Pause a running generation
    """
    try:
        # Get the generation record
        generation = (
            db.query(DBResponseGeneration).filter(DBResponseGeneration.id == generation_id).first()
        )

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

        db.commit()

        # Store task progress in Redis for later resume
        redis_client = get_redis_client()
        if redis_client:
            redis_client.set(
                f"generation_pause_{generation_id}",
                json.dumps(
                    {
                        "progress": generation.current_progress,
                        "completed_tasks": generation.completed_tasks,
                        "paused_at": datetime.now().isoformat(),
                    }
                ),
                ex=86400,  # Expire after 24 hours
            )

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


@router.post("/{generation_id}/resume")
async def resume_generation(
    generation_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Resume a paused generation
    """
    try:
        # Get the generation record
        generation = (
            db.query(DBResponseGeneration).filter(DBResponseGeneration.id == generation_id).first()
        )

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

        # Restore task progress from Redis
        redis_client = get_redis_client()
        saved_progress = None
        if redis_client:
            saved_data = redis_client.get(f"generation_pause_{generation_id}")
            if saved_data:
                saved_progress = json.loads(saved_data)

        # Update generation status
        generation.status = "running"
        generation.resumed_at = datetime.now()

        db.commit()

        # Re-dispatch the generation task with saved progress
        # Fetch project with generation already loaded
        project = db.query(Project).filter(Project.id == generation.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{generation.project_id}' not found",
            )
        config_data = {
            "project_id": generation.project_id,
            "generation_config": project.generation_config,
            "force_rerun": False,
            "user_id": current_user.id,
            "resume_from": saved_progress,
        }

        task = celery_app.send_task(
            "tasks.generate_llm_responses",
            args=[generation_id, config_data, generation.model_id, current_user.id],
            queue="celery",
        )

        generation.celery_task_id = task.id
        db.commit()

        return {
            "message": "Generation resumed successfully",
            "generation_id": generation_id,
            "status": "running",
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
    db: Session = Depends(get_db),
):
    """
    Retry a failed or stopped generation
    """
    try:
        # Get the generation record
        generation = (
            db.query(DBResponseGeneration).filter(DBResponseGeneration.id == generation_id).first()
        )

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

        # Reset generation status
        generation.status = "pending"
        generation.error_message = None
        generation.completed_at = None
        generation.current_progress = 0
        generation.completed_tasks = 0
        generation.retry_count = (generation.retry_count or 0) + 1

        db.commit()

        # Re-dispatch the generation task
        project = db.query(Project).filter(Project.id == generation.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{generation.project_id}' not found",
            )
        config_data = {
            "project_id": generation.project_id,
            "generation_config": project.generation_config,
            "force_rerun": True,
            "user_id": current_user.id,
        }

        task = celery_app.send_task(
            "tasks.generate_llm_responses",
            args=[generation_id, config_data, generation.model_id, current_user.id],
            queue="celery",
        )

        generation.celery_task_id = task.id
        db.commit()

        return {
            "message": "Generation retry started successfully",
            "generation_id": generation_id,
            "status": "pending",
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
    db: Session = Depends(get_db),
):
    """
    Delete a generation record and its associated responses
    """
    try:
        # Get the generation record
        generation = (
            db.query(DBResponseGeneration).filter(DBResponseGeneration.id == generation_id).first()
        )

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
            db.query(DBLLMResponse).filter(DBLLMResponse.generation_id == generation_id).delete()
        )

        # Delete the generation record
        db.delete(generation)
        db.commit()

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
    db: Session = Depends(get_db),
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
    if project_id and not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    try:
        query = db.query(DBLLMResponse)

        # Apply filters if provided
        if project_id:
            query = query.join(DBResponseGeneration).filter(
                DBResponseGeneration.project_id == project_id
            )
        else:
            # Scope by org context when no specific project_id provided
            org_context = request.headers.get("X-Organization-Context", "private")
            accessible_ids = get_accessible_project_ids(db, current_user, org_context)
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
                query = query.join(DBResponseGeneration).filter(
                    DBResponseGeneration.project_id.in_(accessible_ids)
                )

        if model_id:
            query = query.filter(DBLLMResponse.model_id == model_id)

        # Count by parse status
        total = query.count()

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

        success = query.filter(DBLLMResponse.parse_status == "success").count()
        failed = query.filter(DBLLMResponse.parse_status == "failed").count()
        validation_error = query.filter(DBLLMResponse.parse_status == "validation_error").count()

        # Count generations that hit max retries
        # Status would be "parse_failed_max_retries" if that status exists
        max_retries = query.filter(DBLLMResponse.status == "parse_failed_max_retries").count()

        # Calculate average retries for successful parses
        successful_gens = query.filter(DBLLMResponse.parse_status == "success").all()
        avg_retries = 0
        if successful_gens:
            total_retries = sum(
                gen.parse_metadata.get("retry_count", 1) if gen.parse_metadata else 1
                for gen in successful_gens
            )
            avg_retries = total_retries / len(successful_gens)

        # Get common parse errors
        failed_gens = query.filter(
            DBLLMResponse.parse_status.in_(["failed", "validation_error"])
        ).all()
        error_counts = {}
        for gen in failed_gens:
            error = gen.parse_error or "Unknown error"
            error_counts[error] = error_counts.get(error, 0) + 1

        common_errors = [
            {"error": error, "count": count}
            for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

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
    websocket: WebSocket, project_id: str, db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time generation progress updates.
    Clients connect to receive live updates about generation status.
    """
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

            # Create async Redis client for pub/sub
            async_redis = redis_async.Redis(
                host=redis_client.connection_pool.connection_kwargs.get('host', 'localhost'),
                port=redis_client.connection_pool.connection_kwargs.get('port', 6379),
                db=redis_client.connection_pool.connection_kwargs.get('db', 0),
                decode_responses=True,
            )
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
                    # Get latest generation status from database
                    generations = (
                        db.query(DBResponseGeneration)
                        .filter(DBResponseGeneration.project_id == project_id)
                        .order_by(DBResponseGeneration.created_at.desc())
                        .limit(5)
                        .all()
                    )

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
        except:
            pass
    finally:
        # Cleanup
        if pubsub:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

        # Close WebSocket if still open
        try:
            await websocket.close()
        except:
            pass

        logger.info(f"WebSocket connection closed for project {project_id}")
