"""Post-annotation questionnaire endpoints (Issue #1208)."""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from project_models import Annotation, PostAnnotationResponse, Project, Task
from project_schemas import PostAnnotationResponseCreate, PostAnnotationResponseOut
from routers.projects.helpers import (
    check_project_accessible,
    check_task_assigned_to_user,
    check_user_can_edit_project,
    get_org_context_from_request,
)

router = APIRouter()


@router.post(
    "/{project_id}/tasks/{task_id}/questionnaire-response",
    response_model=PostAnnotationResponseOut,
)
async def submit_questionnaire_response(
    project_id: str,
    task_id: str,
    payload: PostAnnotationResponseCreate,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Submit a post-annotation questionnaire response."""

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check org-context-aware project access
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="You don't have access to this project")

    if not project.questionnaire_enabled:
        raise HTTPException(status_code=400, detail="Questionnaire is not enabled for this project")

    task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Enforce task assignment in manual/auto mode
    if not check_task_assigned_to_user(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")

    annotation = (
        db.query(Annotation)
        .filter(
            Annotation.id == payload.annotation_id,
            Annotation.task_id == task_id,
            Annotation.completed_by == current_user.id,
        )
        .first()
    )
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Check for duplicate response
    existing = (
        db.query(PostAnnotationResponse)
        .filter(PostAnnotationResponse.annotation_id == payload.annotation_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Questionnaire response already submitted for this annotation"
        )

    db_response = PostAnnotationResponse(
        id=str(uuid.uuid4()),
        annotation_id=payload.annotation_id,
        task_id=task_id,
        project_id=project_id,
        user_id=current_user.id,
        result=payload.result,
    )

    db.add(db_response)
    db.commit()
    db.refresh(db_response)

    return db_response


@router.get(
    "/{project_id}/questionnaire-responses",
    response_model=List[PostAnnotationResponseOut],
)
async def list_questionnaire_responses(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List all questionnaire responses for a project."""

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check org-context-aware project access
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="You don't have access to this project")

    # Permission check: creator, superadmin, org admin, or contributor
    if not check_user_can_edit_project(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Not authorized to view questionnaire responses")

    responses = (
        db.query(PostAnnotationResponse)
        .filter(PostAnnotationResponse.project_id == project_id)
        .order_by(PostAnnotationResponse.created_at.desc())
        .all()
    )

    return responses
