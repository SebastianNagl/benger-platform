"""
Human evaluation session endpoints (Likert scale, preference ranking).
"""

import logging
import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.authorization import Permission, auth_service
from auth_module import User, require_user
from database import get_db
from models import EvaluationRun as DBEvaluationRun
from models import Generation as DBLLMResponse
from models import HumanEvaluationSession, LikertScaleEvaluation, PreferenceRanking
from project_models import Project, Task
from routers.evaluations.helpers import extract_metric_name
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter()


# ============= Request/Response Models =============


class HumanEvaluationSessionCreate(BaseModel):
    """Request model for creating a human evaluation session"""

    project_id: str
    session_type: str  # 'likert' or 'preference'
    field_name: Optional[str] = None  # Which field to evaluate
    dimensions: Optional[List[str]] = None  # For Likert scale


class HumanEvaluationSessionResponse(BaseModel):
    """Response model for human evaluation session"""

    id: str
    project_id: str
    evaluator_id: str
    session_type: str
    items_evaluated: int
    total_items: Optional[int]
    status: str
    session_config: Optional[Dict[str, Any]]
    created_at: datetime


class LikertRatingSubmit(BaseModel):
    """Request model for submitting Likert scale ratings"""

    session_id: str
    task_id: str
    response_id: str
    ratings: Dict[str, int]  # dimension -> rating (1-5)
    comments: Optional[Dict[str, str]] = None  # dimension -> comment
    time_spent_seconds: Optional[int] = None


class PreferenceRankingSubmit(BaseModel):
    """Request model for submitting preference ranking"""

    session_id: str
    task_id: str
    response_a_id: str
    response_b_id: str
    winner: str  # 'a', 'b', or 'tie'
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    time_spent_seconds: Optional[int] = None


class NextEvaluationItem(BaseModel):
    """Response model for next item to evaluate"""

    task_id: str
    task_data: Dict[str, Any]
    responses: List[Dict[str, Any]]  # Anonymized responses
    item_number: int
    total_items: int
    session_id: str


# ============= Endpoints =============


@router.post("/evaluations/human/session/start", response_model=HumanEvaluationSessionResponse)
async def start_human_evaluation_session(
    request: HumanEvaluationSessionCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Start a new human evaluation session.

    Only superadmins can start human evaluation sessions.
    """
    try:
        # Check if user has project edit permission (superadmin, creator, org admin, contributor)
        from routers.projects.helpers import check_user_can_edit_project

        if not check_user_can_edit_project(db, current_user, request.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied - only project editors can start evaluation sessions",
            )

        # Verify project exists
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{request.project_id}' not found",
            )

        # Create session configuration
        session_config = {
            "field_name": request.field_name,
            "dimensions": request.dimensions if request.session_type == 'likert' else None,
            "randomized": True,
            "allow_skip": True,
        }

        # Count total items to evaluate
        total_items = db.query(Task).filter(Task.project_id == request.project_id).count()

        # Create the session
        session = HumanEvaluationSession(
            id=str(uuid.uuid4()),
            project_id=request.project_id,
            evaluator_id=current_user.id,
            session_type=request.session_type,
            items_evaluated=0,
            total_items=total_items,
            status="active",
            session_config=session_config,
            created_at=datetime.now(),
        )

        db.add(session)
        db.commit()

        return HumanEvaluationSessionResponse(
            id=session.id,
            project_id=session.project_id,
            evaluator_id=session.evaluator_id,
            session_type=session.session_type,
            items_evaluated=session.items_evaluated,
            total_items=session.total_items,
            status=session.status,
            session_config=session.session_config,
            created_at=session.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start evaluation session: {str(e)}",
        )


@router.get("/evaluations/human/next-item", response_model=NextEvaluationItem)
async def get_next_evaluation_item(
    session_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get the next item to evaluate in a human evaluation session.
    """
    try:
        # Get the session
        session = (
            db.query(HumanEvaluationSession)
            .filter(
                HumanEvaluationSession.id == session_id,
                HumanEvaluationSession.evaluator_id == current_user.id,
            )
            .first()
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or unauthorized",
            )

        if session.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session is not active",
            )

        # Get already evaluated tasks in this session
        if session.session_type == "likert":
            evaluated_task_ids = (
                db.query(LikertScaleEvaluation.task_id)
                .filter(LikertScaleEvaluation.session_id == session_id)
                .distinct()
                .all()
            )
            evaluated_task_ids = [t[0] for t in evaluated_task_ids]
        else:  # preference
            evaluated_task_ids = (
                db.query(PreferenceRanking.task_id)
                .filter(PreferenceRanking.session_id == session_id)
                .distinct()
                .all()
            )
            evaluated_task_ids = [t[0] for t in evaluated_task_ids]

        # Get next unevaluated task
        next_task = (
            db.query(Task)
            .filter(
                Task.project_id == session.project_id,
                ~Task.id.in_(evaluated_task_ids) if evaluated_task_ids else True,
            )
            .first()
        )

        if not next_task:
            # No more tasks to evaluate
            session.status = "completed"
            session.completed_at = datetime.now()
            db.commit()

            # HTTP 204 should not have a body, use 404 for "no more items"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No more items to evaluate - session completed",
            )

        # Get responses for this task (LLM responses and/or human annotations)
        responses = []

        # Get LLM responses
        llm_responses = db.query(DBLLMResponse).filter(DBLLMResponse.task_id == next_task.id).all()

        for resp in llm_responses:
            responses.append(
                {
                    "id": resp.id,
                    "type": "llm",
                    "content": resp.response_text,
                    "metadata": {
                        "model_id": resp.model_id,
                        "anonymized_name": f"Response_{chr(65 + len(responses))}",  # A, B, C...
                    },
                }
            )

        # For preference ranking, randomize order
        if session.session_type == "preference" and len(responses) >= 2:
            random.shuffle(responses)
            responses = responses[:2]  # Only compare 2 at a time

        return NextEvaluationItem(
            task_id=next_task.id,
            task_data=next_task.data,
            responses=responses,
            item_number=session.items_evaluated + 1,
            total_items=session.total_items,
            session_id=session.id,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get next evaluation item: {str(e)}",
        )


@router.post("/evaluations/human/likert")
async def submit_likert_rating(
    request: LikertRatingSubmit,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Submit Likert scale ratings for a response.
    """
    try:
        # Verify session
        session = (
            db.query(HumanEvaluationSession)
            .filter(
                HumanEvaluationSession.id == request.session_id,
                HumanEvaluationSession.evaluator_id == current_user.id,
                HumanEvaluationSession.session_type == "likert",
            )
            .first()
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or unauthorized",
            )

        # Create Likert evaluations for each dimension
        for dimension, rating in request.ratings.items():
            evaluation = LikertScaleEvaluation(
                id=str(uuid.uuid4()),
                session_id=request.session_id,
                task_id=request.task_id,
                response_id=request.response_id,
                dimension=dimension,
                rating=rating,
                comment=request.comments.get(dimension) if request.comments else None,
                time_spent_seconds=request.time_spent_seconds,
                created_at=datetime.now(),
            )
            db.add(evaluation)

        # Update session progress
        session.items_evaluated += 1
        session.updated_at = datetime.now()

        db.commit()

        return {
            "message": "Likert ratings submitted successfully",
            "items_evaluated": session.items_evaluated,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit Likert rating: {str(e)}",
        )


@router.post("/evaluations/human/preference")
async def submit_preference_ranking(
    request: PreferenceRankingSubmit,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Submit blind preference ranking between two responses.
    """
    try:
        # Verify session
        session = (
            db.query(HumanEvaluationSession)
            .filter(
                HumanEvaluationSession.id == request.session_id,
                HumanEvaluationSession.evaluator_id == current_user.id,
                HumanEvaluationSession.session_type == "preference",
            )
            .first()
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or unauthorized",
            )

        # Create preference ranking
        ranking = PreferenceRanking(
            id=str(uuid.uuid4()),
            session_id=request.session_id,
            task_id=request.task_id,
            response_a_id=request.response_a_id,
            response_b_id=request.response_b_id,
            winner=request.winner,
            confidence=request.confidence,
            reasoning=request.reasoning,
            time_spent_seconds=request.time_spent_seconds,
            created_at=datetime.now(),
        )

        db.add(ranking)

        # Update session progress
        session.items_evaluated += 1
        session.updated_at = datetime.now()

        db.commit()

        return {
            "message": "Preference ranking submitted successfully",
            "items_evaluated": session.items_evaluated,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit preference ranking: {str(e)}",
        )


@router.get("/evaluations/human/session/{session_id}/progress")
async def get_human_evaluation_progress(
    session_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get progress information for a human evaluation session.
    """
    try:
        # Get the session
        session = (
            db.query(HumanEvaluationSession).filter(HumanEvaluationSession.id == session_id).first()
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        # Check permissions - user must be session owner or superadmin
        if not current_user.is_superadmin and session.evaluator_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this session",
            )

        # Calculate progress percentage
        progress_percentage = 0.0
        if session.total_items and session.total_items > 0:
            progress_percentage = (session.items_evaluated / session.total_items) * 100

        return {
            "session_id": session.id,
            "project_id": session.project_id,
            "items_evaluated": session.items_evaluated,
            "total_items": session.total_items,
            "progress_percentage": progress_percentage,
            "status": session.status,
            "session_type": session.session_type,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session progress: {str(e)}",
        )


@router.get("/evaluations/human/sessions/{project_id}")
async def get_human_evaluation_sessions(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get all human evaluation sessions for a project.
    """
    # Check project access
    if not check_project_accessible(db, current_user, project_id, get_org_context_from_request(request)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this project",
        )

    try:
        sessions = (
            db.query(HumanEvaluationSession)
            .filter(HumanEvaluationSession.project_id == project_id)
            .order_by(HumanEvaluationSession.created_at.desc())
            .all()
        )

        return [
            HumanEvaluationSessionResponse(
                id=s.id,
                project_id=s.project_id,
                evaluator_id=s.evaluator_id,
                session_type=s.session_type,
                items_evaluated=s.items_evaluated,
                total_items=s.total_items,
                status=s.status,
                session_config=s.session_config,
                created_at=s.created_at,
            )
            for s in sessions
        ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evaluation sessions: {str(e)}",
        )


@router.get("/evaluations/human/config/{project_id}")
async def get_human_evaluation_config(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get human evaluation configuration for a project.

    Returns the evaluation_config with human evaluation methods if configured.
    """
    try:
        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        # Check access permissions
        org_context = get_org_context_from_request(request)
        if not auth_service.check_project_access(
            current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this project's evaluation config",
            )

        # Get evaluation config with human methods
        if not project.evaluation_config:
            return {
                "project_id": project_id,
                "human_methods": {},
                "available_dimensions": [],
            }

        # Extract human evaluation methods from config
        human_methods = {}
        available_dimensions = []

        selected_methods = project.evaluation_config.get("selected_methods", {})
        for field_name, config in selected_methods.items():
            human_selections = config.get("human", [])
            if human_selections:
                human_methods[field_name] = human_selections

                # Extract dimensions for Likert scale
                for method in human_selections:
                    method_name = extract_metric_name(method)
                    if method_name == "likert_scale":
                        if isinstance(method, dict) and "parameters" in method:
                            dimensions = method["parameters"].get("dimensions", [])
                            available_dimensions.extend(dimensions)

        return {
            "project_id": project_id,
            "human_methods": human_methods,
            "available_dimensions": list(set(available_dimensions))
            if available_dimensions
            else [
                "correctness",
                "completeness",
                "style",
                "usability",
            ],
            "evaluation_config": project.evaluation_config,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get human evaluation config: {str(e)}",
        )


@router.delete("/evaluations/human/session/{session_id}")
async def delete_human_evaluation_session(
    session_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Delete a human evaluation session and all associated evaluations.

    Only superadmins or the session creator can delete a session.
    """
    try:
        # Get the session
        session = (
            db.query(HumanEvaluationSession).filter(HumanEvaluationSession.id == session_id).first()
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        # Check permissions - only superadmin or session creator can delete
        if not current_user.is_superadmin and session.evaluator_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this session",
            )

        # Delete associated Likert evaluations
        db.query(LikertScaleEvaluation).filter(
            LikertScaleEvaluation.session_id == session_id
        ).delete()

        # Delete associated preference rankings
        db.query(PreferenceRanking).filter(PreferenceRanking.session_id == session_id).delete()

        # Delete the session
        db.delete(session)
        db.commit()

        return {
            "message": "Human evaluation session deleted successfully",
            "session_id": session_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )
