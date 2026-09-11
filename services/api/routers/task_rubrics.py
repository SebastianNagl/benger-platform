"""Per-task grading rubrics (Bewertungsbogen): reads, stateless parse, writes.

Platform owns the ``task_rubrics`` persistence, the structure contract
(``services/shared/rubric_structure.py``), the write-side invariants
(``services/shared/task_rubric_service.py``) and these generic endpoints:

- ``GET  /api/projects/{id}/task-rubrics[?task_id=&status=]`` / ``GET …/{rubric_id}``
- ``POST /api/task-rubrics/parse`` — stateless file → structure (XLSX/DOCX);
  no project needed because the exam create modal and the wizard upload
  before a project exists. Nothing is persisted.
- ``POST /api/projects/{id}/task-rubrics`` — create from a structure
  (``source="human"``), optionally activated.
- ``PUT  …/{rubric_id}`` — edit; a rubric that already scored gradings is
  cloned (response carries ``replaced_rubric_id``).
- ``POST …/{rubric_id}/activate`` / ``…/archive``.

Reads keep the project-view gate (org-context aware); writes use the
editor gate (creator / superadmin / org ADMIN+CONTRIBUTOR). The AI
generation workflow and the Vertretbar exam flows live in benger_extended
and call the same shared service.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.authorization import Permission, auth_service
from auth_module import User, require_user
from database import get_async_db
from project_models import Project, Task, TaskRubric, project_is_deleted
from routers.projects.helpers import (
    check_user_can_edit_project_async,
    get_org_context_from_request,
)
from rubric_structure import render_structure_text
from services.rubric_import import MAX_RUBRIC_FILE_BYTES, RubricImportError, parse_rubric_file
from task_rubric_service import (
    UNSET,
    RubricValidationError,
    activate_task_rubric,
    archive_task_rubric,
    create_task_rubric,
    edit_task_rubric,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/task-rubrics",
    tags=["task-rubrics"],
)
parse_router = APIRouter(prefix="/api/task-rubrics", tags=["task-rubrics"])


class TaskRubricResponse(BaseModel):
    id: str
    task_id: str
    project_id: str
    title: Optional[str] = None
    criteria: Dict[str, Any]
    total_points: float
    structure: Optional[Dict[str, Any]] = None
    grade_scale: Optional[Dict[str, Any]] = None
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


class TaskRubricWriteResponse(TaskRubricResponse):
    """Edit response: ``replaced_rubric_id`` is set when the edit produced a clone."""

    replaced_rubric_id: Optional[str] = None


class ParsedRubricResponse(BaseModel):
    title: Optional[str] = None
    structure: Dict[str, Any]
    criteria: Dict[str, Any]
    total_points: float
    grade_scale: Optional[Dict[str, Any]] = None
    # The same key in PERCENT of the sheet total — what the client offers as
    # the EXAM's Notenschlüssel. ``None`` when the file carried
    # no readable key.
    grade_scale_percent: Optional[Dict[str, Any]] = None
    warnings: List[Dict[str, Any]] = []
    source_format: str
    rendered_text: str


class TaskRubricCreate(BaseModel):
    task_id: str
    title: Optional[str] = None
    structure: Dict[str, Any]
    grade_scale: Optional[Dict[str, Any]] = None
    activate: bool = False


class TaskRubricUpdate(BaseModel):
    """Omitted fields are left alone; ``grade_scale: null`` clears the scale."""

    title: Optional[str] = None
    structure: Optional[Dict[str, Any]] = None
    grade_scale: Optional[Dict[str, Any]] = None


class RubricStatusResponse(BaseModel):
    id: str
    task_id: str
    status: str
    source: str
    title: Optional[str] = None


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


async def _get_editable_project(project_id: str, current_user: User, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project or project_is_deleted(project):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    if not await check_user_can_edit_project_async(db, current_user, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this project",
        )
    return project


async def _get_project_task(db: AsyncSession, project_id: str, task_id: str) -> Task:
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.project_id == project_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found in project {project_id}",
        )
    return task


async def _get_project_rubric(db: AsyncSession, project_id: str, rubric_id: str) -> TaskRubric:
    result = await db.execute(
        select(TaskRubric).where(
            TaskRubric.id == rubric_id, TaskRubric.project_id == project_id
        )
    )
    rubric = result.scalar_one_or_none()
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} not found",
        )
    return rubric


def _status_response(rubric: TaskRubric) -> RubricStatusResponse:
    return RubricStatusResponse(
        id=rubric.id,
        task_id=rubric.task_id,
        status=rubric.status,
        source=rubric.source,
        title=rubric.title,
    )


# ---------------------------------------------------------------------------
# Stateless parse
# ---------------------------------------------------------------------------


@parse_router.post("/parse", response_model=ParsedRubricResponse)
async def parse_task_rubric_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_user),
):
    """Turn an uploaded Korrekturbogen (XLSX/DOCX) into a rubric structure.

    Deterministic heuristics (no LLM); the response includes the reviewer
    warnings and the judge-facing rendering so the outline editor can show
    exactly what the judge will read. Nothing is persisted.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    data = await file.read()
    if len(data) > MAX_RUBRIC_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Document exceeds the {MAX_RUBRIC_FILE_BYTES // (1024 * 1024)} MB limit.",
        )
    try:
        result = await run_in_threadpool(parse_rubric_file, file.filename, data)
    except RubricImportError as exc:
        raise HTTPException(status_code=422, detail=exc.to_detail())
    except Exception:
        logger.exception("Rubric import failed for %s", file.filename)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "parse_failed",
                "message": "Die Datei konnte nicht als Korrekturbogen gelesen werden.",
                "warnings": [],
            },
        )
    rendered = render_structure_text(
        result["structure"],
        result["total_points"],
        result["grade_scale"],
        title=result["title"],
        include_grade_scale=True,
    )
    return {**result, "rendered_text": rendered}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


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
    return await _get_project_rubric(db, project_id, rubric_id)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


@router.post("", response_model=TaskRubricResponse, status_code=status.HTTP_201_CREATED)
async def create_task_rubric_endpoint(
    project_id: str,
    body: TaskRubricCreate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a hand-written / imported rubric (``source="human"``) for a task."""
    await _get_editable_project(project_id, current_user, db)
    task = await _get_project_task(db, project_id, body.task_id)
    try:
        rubric = await create_task_rubric(
            db,
            task=task,
            project_id=project_id,
            actor_id=str(current_user.id),
            structure=body.structure,
            grade_scale=body.grade_scale,
            title=body.title,
            source="human",
            status="active" if body.activate else "candidate",
        )
    except RubricValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Bewertungsbogen: {exc}")
    await db.commit()
    # Server-generated columns (updated_at on UPDATE) are expired after the
    # flush; refresh explicitly so response serialization does no lazy IO.
    await db.refresh(rubric)
    return rubric


@router.put("/{rubric_id}", response_model=TaskRubricWriteResponse)
async def update_task_rubric_endpoint(
    project_id: str,
    rubric_id: str,
    body: TaskRubricUpdate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Edit title / structure / grade scale.

    Graded rubrics are cloned instead of rewritten: the response is the row
    that now carries the edit and ``replaced_rubric_id`` names the archived
    original (clients re-point to ``id``).
    """
    await _get_editable_project(project_id, current_user, db)
    rubric = await _get_project_rubric(db, project_id, rubric_id)
    task = await _get_project_task(db, project_id, rubric.task_id)
    fields = body.model_fields_set
    if "structure" in fields and body.structure is None:
        raise HTTPException(
            status_code=422, detail="Invalid Bewertungsbogen: structure cannot be null"
        )
    try:
        result = await edit_task_rubric(
            db,
            rubric,
            task,
            structure=body.structure if "structure" in fields else UNSET,
            grade_scale=body.grade_scale if "grade_scale" in fields else UNSET,
            title=body.title if "title" in fields else UNSET,
            actor_id=str(current_user.id),
        )
    except RubricValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Bewertungsbogen: {exc}")
    await db.commit()
    await db.refresh(result)
    payload = TaskRubricResponse.model_validate(result).model_dump()
    return TaskRubricWriteResponse(
        **payload, replaced_rubric_id=rubric.id if result.id != rubric.id else None
    )


@router.post("/{rubric_id}/activate", response_model=RubricStatusResponse)
async def activate_task_rubric_endpoint(
    project_id: str,
    rubric_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Make this rubric the task's active one (the previous active → candidate)."""
    await _get_editable_project(project_id, current_user, db)
    rubric = await _get_project_rubric(db, project_id, rubric_id)
    task = await _get_project_task(db, project_id, rubric.task_id)
    await activate_task_rubric(db, rubric, task)
    await db.commit()
    await db.refresh(rubric)
    return _status_response(rubric)


@router.post("/{rubric_id}/archive", response_model=RubricStatusResponse)
async def archive_task_rubric_endpoint(
    project_id: str,
    rubric_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Archive this rubric (removes the task-data mirror when it was active)."""
    await _get_editable_project(project_id, current_user, db)
    rubric = await _get_project_rubric(db, project_id, rubric_id)
    task = await _get_project_task(db, project_id, rubric.task_id)
    await archive_task_rubric(db, rubric, task)
    await db.commit()
    await db.refresh(rubric)
    return _status_response(rubric)
