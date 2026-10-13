"""``/api/v1`` export jobs: full project exports through object storage.

An export carries the unblinded ``task.data`` (reference solutions
included), so it needs ``exports:read`` and ``tasks:read_reference`` on the
key and a full-data role (ORG_ADMIN or CONTRIBUTOR) of the key's user on the
project, checked again on every read. The job machinery is the platform's
(``routers/projects/import_export.py``): a worker streams the export to
object storage, the client polls the job and follows a short-lived presigned
redirect.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scopes import scopes_satisfied
from auth_module import require_user
from auth_module.principal import get_principal
from database import get_async_db
from models import ExportJob, JobStatus
from project_models import Project
from routers.projects.deps import ProjectAccess
from routers.projects.helpers import can_read_all_task_content_async
from routers.projects.import_export import enqueue_export_job, export_download_url
from routers.v1._deps import (
    SCOPES_ATTR,
    _insufficient_scope,
    key_may_see_project,
    require_scope,
    v1_project_access,
)
from routers.v1._errors import V1Error
from routers.v1._idempotency import IdempotencyContext, idempotent
from routers.v1._schemas import ERROR_RESPONSES, ExportCreate, ExportJobOut

router = APIRouter(tags=["exports"])

REFERENCE_SCOPE = "tasks:read_reference"


def also_require(*scopes: str):
    """Scope check for a route whose main dependency already authenticated
    and rate-limited the request (``require_scope`` would count it twice).
    Declare it after that dependency."""
    needed = frozenset(scopes)

    async def _also_require(request: Request, user=Depends(require_user)) -> None:
        principal = get_principal(request)
        if principal is not None and principal.is_api_key:
            if not scopes_satisfied(principal.scopes, needed):
                raise _insufficient_scope(needed)

    setattr(_also_require, SCOPES_ATTR, needed)
    return _also_require


def _iso(value):
    return value.isoformat() if value is not None else None


def serialize_export_job_public(job: ExportJob) -> Dict[str, Any]:
    done = job.status == JobStatus.COMPLETED.value and bool(job.object_key)
    return {
        "id": job.id,
        "project_id": job.project_id,
        "format": job.format,
        "status": job.status,
        "progress": job.progress,
        "byte_size": job.byte_size,
        "error_message": job.error_message,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "expires_at": _iso(job.expires_at),
        "download_url": f"/api/v1/exports/{job.id}/download" if done else None,
    }


def _job_not_found() -> V1Error:
    return V1Error(404, "export_not_found", "Export job not found")


async def _load_job(db: AsyncSession, request: Request, user, job_id: str) -> ExportJob:
    """The job, if the caller may read it now: its project must still be
    visible to the credential and the caller must hold a full-data role
    there (sessions may also read their own jobs, as in the browser API).
    Everything else answers 404 so job ids cannot be probed."""
    job = (await db.execute(select(ExportJob).where(ExportJob.id == job_id))).scalar_one_or_none()
    if job is None:
        raise _job_not_found()
    project = (
        await db.execute(select(Project).where(Project.id == job.project_id))
    ).scalar_one_or_none()
    if project is None or (project.deleted_at is not None and not user.is_superadmin):
        raise _job_not_found()
    principal = get_principal(request)
    if not await key_may_see_project(db, principal, project):
        raise _job_not_found()
    own_session_job = (
        (principal is None or not principal.is_api_key)
        and str(job.requested_by) == str(user.id)
    )
    if not own_session_job and not await can_read_all_task_content_async(db, user, project):
        raise _job_not_found()
    return job


@router.post(
    "/projects/{project_id}/exports",
    status_code=202,
    response_model=ExportJobOut,
    responses={**ERROR_RESPONSES, 404: {"description": "Project not found"}},
    summary="Start a project export",
)
async def create_export(
    request: Request,
    body: Optional[ExportCreate] = Body(None),
    access: ProjectAccess = Depends(v1_project_access("exports:read")),
    _reference: None = Depends(also_require(REFERENCE_SCOPE)),
    idem: IdempotencyContext = Depends(idempotent()),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Queue an export of the whole project (or of ``task_ids``, json only).
    Poll ``GET /api/v1/exports/{id}`` until ``status`` is ``completed``."""
    body = body or ExportCreate()
    project = access.project
    if not await can_read_all_task_content_async(db, user, project):
        raise V1Error(
            403,
            "forbidden",
            "Exports need the ORG_ADMIN or CONTRIBUTOR role on the project",
        )
    job = await enqueue_export_job(db, user, project, body.format, body.task_ids)
    await db.refresh(job)  # server-side updated_at after the enqueue commit
    content = serialize_export_job_public(job)
    await idem.save(202, content)
    return JSONResponse(
        status_code=202,
        content=content,
        headers={"Location": f"/api/v1/exports/{job.id}"},
    )


@router.get(
    "/exports/{job_id}",
    response_model=ExportJobOut,
    responses={**ERROR_RESPONSES, 404: {"description": "Export job not found"}},
    summary="Read an export job",
)
async def get_export(
    job_id: str,
    request: Request,
    _principal=Depends(require_scope("exports:read")),
    _reference: None = Depends(also_require(REFERENCE_SCOPE)),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    return serialize_export_job_public(await _load_job(db, request, user, job_id))


@router.get(
    "/exports/{job_id}/download",
    status_code=302,
    response_class=RedirectResponse,
    responses={
        **ERROR_RESPONSES,
        302: {"description": "Redirect to a presigned download URL (valid 5 minutes)"},
        404: {"description": "Unknown job or export not ready yet"},
        410: {"description": "The export expired; start a new one"},
    },
    summary="Download a finished export",
)
async def download_export(
    job_id: str,
    request: Request,
    _principal=Depends(require_scope("exports:read")),
    _reference: None = Depends(also_require(REFERENCE_SCOPE)),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    job = await _load_job(db, request, user, job_id)
    try:
        url = await export_download_url(db, job)
    except HTTPException as exc:
        if exc.status_code == 410:
            raise V1Error(410, "export_expired", "The export expired; start a new one")
        if exc.status_code == 404:
            raise V1Error(404, "export_not_ready", "The export is not finished yet")
        raise
    return RedirectResponse(url=url, status_code=302)
