"""
Evaluation status and SSE streaming endpoints.
"""

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from auth_module import User, require_user
from database import get_db
from models import EvaluationRun as DBEvaluationRun
from models import EvaluationType as DBEvaluationType
from routers.evaluations.helpers import (
    EvaluationResult,
    EvaluationStatus,
    EvaluationTypeResponse,
    get_evaluation_types_for_task_type,
)
from routers.projects.helpers import check_project_accessible, get_accessible_project_ids, get_org_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/evaluation/status/{evaluation_id}", response_model=EvaluationStatus)
async def get_evaluation_status(
    evaluation_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get the status of a specific evaluation.
    """
    evaluation = db.query(DBEvaluationRun).filter(DBEvaluationRun.id == evaluation_id).first()

    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation '{evaluation_id}' not found",
        )

    # Check project access
    if not check_project_accessible(db, current_user, evaluation.project_id, get_org_context_from_request(request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this evaluation's project",
        )

    return EvaluationStatus(
        id=evaluation.id,
        status=evaluation.status,
        message=evaluation.error_message or "Evaluation status",
    )


@router.get("/stream/{evaluation_id}")
async def stream_evaluation_status(
    evaluation_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Stream evaluation status updates via Server-Sent Events.

    Provides real-time status updates for an evaluation, including:
    - status: pending, running, completed, failed
    - samples_evaluated: number of samples processed
    - error_message: any error that occurred

    Events:
    - 'status': Sent when status changes
    - 'done': Sent when evaluation completes or fails, then stream closes
    - 'error': Sent if there's an error fetching status

    Authentication:
    - Uses cookie-based authentication (withCredentials: true from EventSource)
    """
    # Check project access before starting stream
    evaluation = db.query(DBEvaluationRun).filter(DBEvaluationRun.id == evaluation_id).first()
    if evaluation and not check_project_accessible(db, current_user, evaluation.project_id, get_org_context_from_request(request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this evaluation's project",
        )

    logger.info(f"SSE stream started for evaluation {evaluation_id} by user {current_user.id}")

    async def event_generator():
        last_status = None
        last_samples = None
        max_iterations = 600  # Maximum 10 minutes of streaming (600 x 1 second)
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                # Refresh the session to get latest data
                db.expire_all()
                evaluation = db.query(DBEvaluationRun).filter(DBEvaluationRun.id == evaluation_id).first()

                if not evaluation:
                    yield {"event": "error", "data": json.dumps({"error": "Evaluation not found"})}
                    break

                current_status = evaluation.status
                current_samples = evaluation.samples_evaluated or 0

                # Only send update if status or samples changed
                if current_status != last_status or current_samples != last_samples:
                    status_data = {
                        "status": current_status,
                        "samples_evaluated": current_samples,
                        "error_message": evaluation.error_message,
                    }

                    yield {"event": "status", "data": json.dumps(status_data)}

                    last_status = current_status
                    last_samples = current_samples

                # Send done event and close stream when evaluation finishes
                if current_status in ["completed", "failed"]:
                    done_data = {
                        "status": current_status,
                        "samples_evaluated": current_samples,
                        "error_message": evaluation.error_message,
                    }
                    yield {"event": "done", "data": json.dumps(done_data)}
                    break

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error streaming evaluation status: {str(e)}")
                yield {"event": "error", "data": json.dumps({"error": str(e)})}
                break

    return EventSourceResponse(event_generator())


@router.get("/evaluations", response_model=List[EvaluationResult])
async def get_evaluations(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get all evaluation results scoped to the user's organization context.

    Users can view evaluations for projects assigned to their organizations.
    """
    org_context = request.headers.get("X-Organization-Context")
    accessible_ids = get_accessible_project_ids(db, current_user, org_context)

    # Query evaluations from database, ordered by creation date (newest first)
    query = db.query(DBEvaluationRun).order_by(DBEvaluationRun.created_at.desc())

    if accessible_ids is not None:
        if not accessible_ids:
            return []
        query = query.filter(DBEvaluationRun.project_id.in_(accessible_ids))

    db_evaluations = query.all()

    # Convert to response model
    results = []
    for eval in db_evaluations:
        results.append(
            EvaluationResult(
                id=eval.id,
                project_id=eval.project_id,
                model_id=eval.model_id,
                metrics=eval.metrics,
                created_at=eval.created_at,
                status=eval.status,
                metadata=eval.eval_metadata,
                samples_evaluated=eval.samples_evaluated,
            )
        )

    return results


@router.get("/evaluation-types", response_model=List[EvaluationTypeResponse])
async def get_evaluation_types(
    task_type_id: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get all available evaluation types from the database.
    Optionally filter by task type or category.
    """
    try:
        query = db.query(DBEvaluationType).filter(DBEvaluationType.is_active.is_(True))

        # Filter by task type if specified
        if task_type_id:
            # Use database-agnostic filtering
            task_type_evaluation_types = get_evaluation_types_for_task_type(db, task_type_id)
            task_type_ids = [et.id for et in task_type_evaluation_types]
            query = query.filter(DBEvaluationType.id.in_(task_type_ids))

        # Filter by category if specified
        if category:
            query = query.filter(DBEvaluationType.category == category)

        evaluation_types = query.all()

        result = []
        for eval_type in evaluation_types:
            result.append(
                EvaluationTypeResponse(
                    id=eval_type.id,
                    name=eval_type.name,
                    description=eval_type.description,
                    category=eval_type.category,
                    higher_is_better=eval_type.higher_is_better,
                    value_range=eval_type.value_range,
                    applicable_project_types=eval_type.applicable_project_types,
                    is_active=eval_type.is_active,
                )
            )

        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving evaluation types: {str(e)}",
        )


@router.get(
    "/evaluation-types/{evaluation_type_id}",
    response_model=EvaluationTypeResponse,
)
async def get_evaluation_type(
    evaluation_type_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get a specific evaluation type by ID
    """
    try:
        eval_type = (
            db.query(DBEvaluationType)
            .filter(
                DBEvaluationType.id == evaluation_type_id,
                DBEvaluationType.is_active.is_(True),
            )
            .first()
        )

        if not eval_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation type '{evaluation_type_id}' not found",
            )

        return EvaluationTypeResponse(
            id=eval_type.id,
            name=eval_type.name,
            description=eval_type.description,
            category=eval_type.category,
            higher_is_better=eval_type.higher_is_better,
            value_range=eval_type.value_range,
            applicable_project_types=eval_type.applicable_project_types,
            is_active=eval_type.is_active,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving evaluation type: {str(e)}",
        )


@router.get("/supported-metrics")
async def get_supported_metrics(
    current_user: User = Depends(require_user),
):
    """
    Get all supported evaluation metrics.
    Returns a comprehensive list of all available automated and human evaluation metrics.
    """
    from evaluation_config import AnswerType, get_metrics_for_answer_type

    # Get all unique metrics across all answer types (core + extended)
    all_metrics = set()
    for answer_type in AnswerType:
        metrics = get_metrics_for_answer_type(answer_type)
        all_metrics.update(metrics)

    # Sort and return
    sorted_metrics = sorted(list(all_metrics))

    return {
        "supported_metrics": sorted_metrics,
        "metrics": sorted_metrics,  # Alias for compatibility
        "count": len(sorted_metrics),
    }
