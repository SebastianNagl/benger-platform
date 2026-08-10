"""Read endpoints for per-task grading rubrics (Bewertungsbogen).

Platform owns the ``task_rubrics`` persistence and these generic reads; the
write side (generation, activation, editing) is workflow logic and lives in
the benger_extended router. See the TaskRubric model docstring in
``services/shared/project_models.py``.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Permission, auth_service
from auth_module import User, require_user
from database import get_async_db
from project_models import Project, TaskRubric
from routers.projects.helpers import get_org_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/task-rubrics",
    tags=["task-rubrics"],
)


class TaskRubricResponse(BaseModel):
    id: str
    task_id: str
    project_id: str
    title: Optional[str] = None
    criteria: Dict[str, Any]
    total_points: int
    source: str
    generator_model_id: Optional[str] = None
    prompt_key: Optional[str] = None
    prompt_version: Optional[str] = None
    generation_metadata: Optional[Dict[str, Any]] = None
    status: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


async def _get_viewable_project(
    project_id: str, request: Request, current_user: User, db: AsyncSession
) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    org_context = get_org_context_from_request(request)
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this project",
        )
    return project


@router.get("", response_model=List[TaskRubricResponse])
async def list_task_rubrics(
    project_id: str,
    request: Request,
    task_id: Optional[str] = Query(None, description="Limit to one task"),
    rubric_status: Optional[str] = Query(
        None, alias="status", description="Filter: candidate | active | archived"
    ),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List rubrics for a project, newest first.

    ``?task_id=`` scopes to one task; ``?status=active`` yields at most one
    row per task (partial unique index).
    """
    await _get_viewable_project(project_id, request, current_user, db)

    stmt = select(TaskRubric).where(TaskRubric.project_id == project_id)
    if task_id:
        stmt = stmt.where(TaskRubric.task_id == task_id)
    if rubric_status:
        stmt = stmt.where(TaskRubric.status == rubric_status)
    stmt = stmt.order_by(TaskRubric.created_at.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{rubric_id}", response_model=TaskRubricResponse)
async def get_task_rubric(
    project_id: str,
    rubric_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    await _get_viewable_project(project_id, request, current_user, db)

    result = await db.execute(
        select(TaskRubric).where(
            TaskRubric.id == rubric_id, TaskRubric.project_id == project_id
        )
    )
    rubric = result.scalar_one_or_none()
    if not rubric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} not found",
        )
    return rubric
