"""Post-annotation questionnaire endpoints (Issue #1208)."""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_async_db
from project_models import Annotation, PostAnnotationResponse, Task
from project_schemas import PostAnnotationResponseCreate, PostAnnotationResponseOut
from routers.projects.deps import ProjectAccess, require_project_access
from routers.projects.helpers import (
    check_task_assigned_to_user_async,
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
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(
        require_project_access(access_denied_detail="You don't have access to this project")
    ),
):
    """Submit a post-annotation questionnaire response."""

    project = access.project

    if not project.questionnaire_enabled:
        raise HTTPException(status_code=400, detail="Questionnaire is not enabled for this project")

    task = (
        await db.execute(
            select(Task).where(Task.id == task_id, Task.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Enforce task assignment in manual/auto mode
    if not await check_task_assigned_to_user_async(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")

    annotation = (
        await db.execute(
            select(Annotation).where(
                Annotation.id == payload.annotation_id,
                Annotation.task_id == task_id,
                Annotation.completed_by == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Check for duplicate response
    # .first(): annotation_id has no DB unique constraint (this guard is the
    # only enforcement), so pre-existing duplicates must yield the 400 below,
    # not a MultipleResultsFound 500. Matches the sync original's .first().
    existing = (
        await db.execute(
            select(PostAnnotationResponse).where(
                PostAnnotationResponse.annotation_id == payload.annotation_id
            )
        )
    ).scalars().first()
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
    await db.commit()
    await db.refresh(db_response)

    return db_response


@router.get(
    "/{project_id}/questionnaire-responses",
    response_model=List[PostAnnotationResponseOut],
)
async def list_questionnaire_responses(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(
        require_project_access(
            min_role="edit",
            access_denied_detail="You don't have access to this project",
            edit_denied_detail="Not authorized to view questionnaire responses",
        )
    ),
):
    """List all questionnaire responses for a project."""

    responses = (
        await db.execute(
            select(PostAnnotationResponse)
            .where(PostAnnotationResponse.project_id == project_id)
            .order_by(PostAnnotationResponse.created_at.desc())
        )
    ).scalars().all()

    return responses
