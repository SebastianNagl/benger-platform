"""Project import and export endpoints."""

import csv
import io
import json
import logging
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Issue #964: Span annotation format conversion functions
def convert_to_label_studio_format(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert BenGER annotation format to Label Studio format for export.
    Flattens span annotations: one result with spans array -> multiple results.

    BenGER format:
    {"from_name": "label", "type": "labels", "value": {"spans": [...]}}

    Label Studio format:
    [{"id": "span-1", "from_name": "label", "type": "labels", "value": {"start": 0, "end": 10, ...}}]
    """
    if not results or not isinstance(results, list):
        return results

    output = []
    for result in results:
        # Handle span/labels type with nested spans array
        if result.get("type") == "labels" and isinstance(result.get("value"), dict):
            spans = result["value"].get("spans", [])
            if spans and isinstance(spans, list):
                # Flatten: create one result per span
                for span in spans:
                    output.append(
                        {
                            "id": span.get("id", str(uuid.uuid4())),
                            "from_name": result.get("from_name"),
                            "to_name": result.get("to_name"),
                            "type": "labels",
                            "value": {
                                "start": span.get("start"),
                                "end": span.get("end"),
                                "text": span.get("text", ""),
                                "labels": span.get("labels", []),
                            },
                        }
                    )
            else:
                # No spans array, pass through as-is
                output.append(result)
        else:
            # Non-span annotations pass through unchanged
            output.append(result)

    return output


from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request  # noqa: E402
from fastapi.responses import (  # noqa: E402
    JSONResponse,
    RedirectResponse,
    Response,
)
from sqlalchemy.orm import Session  # noqa: E402

from auth_module import require_user  # noqa: E402
from auth_module.models import User as AuthUser  # noqa: E402
from celery_client import send_task_safe  # noqa: E402
from database import get_db  # noqa: E402
from object_storage import object_storage  # noqa: E402
from routers.projects._export_stream import (  # noqa: E402
    EXPORT_FORMAT_MEDIA_TYPES,
    stream_comprehensive_project_data_json,
)
from routers.projects._import_stream import (  # noqa: E402,F401
    _IMPORT_BATCH,  # re-exported for tests/integration/test_import_streaming_batch.py
    convert_from_label_studio_format,  # re-exported: shared driver used by tests
    run_full_project_import,  # re-exported: shared driver used by tests
    run_nested_import,  # re-exported: shared driver used by tests
)
from models import (  # noqa: E402
    ExportJob,
    ImportJob,
    JobStatus,
)
from project_models import (  # noqa: E402
    Annotation,
    Project,
    Task,
)
from routers.projects.helpers import (  # noqa: E402
    check_project_accessible,
    check_project_write_access,
    get_org_context_from_request,
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Async export jobs (issue #158)
#
# Object storage is the only export path. POST enqueues a worker that streams
# the export into object storage; the client polls GET .../{job_id} and then
# downloads via a short-lived presigned URL (GET .../{job_id}/download), so the
# bulk bytes never transit the API request thread or a browser-RAM Blob. The
# synchronous GET /export this replaced OOMKilled the pod on the Benchathon
# export.
# ─────────────────────────────────────────────────────────────────────────────


def _serialize_export_job(job: ExportJob) -> dict:
    return {
        "job_id": job.id,
        "project_id": job.project_id,
        "format": job.format,
        "status": job.status,
        "progress": job.progress,
        "byte_size": job.byte_size,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
    }


def _load_export_job_for_read(
    db: Session, request: Request, current_user: AuthUser, project_id: str, job_id: str
) -> ExportJob:
    """Fetch an ExportJob enforcing scope + authz, or raise the right HTTP error.

    A job is readable by its requester or by anyone with write access to the
    project (so an admin can see a colleague's export). 404 (not 403) when the
    job belongs to a different project so we don't leak job-id existence across
    projects.
    """
    job = db.query(ExportJob).filter(ExportJob.id == job_id).first()
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Export job not found")
    if str(job.requested_by) != str(current_user.id) and not check_project_write_access(
        db, current_user, project_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    return job


@router.post("/{project_id}/exports", status_code=202)
async def create_export_job(
    project_id: str,
    request: Request,
    format: str = Query(
        "json",
        pattern="^(json|csv|tsv|txt|label_studio|comprehensive|ndjson|ndjson_gz)$",
    ),
    data: Optional[dict] = Body(default=None),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create an async export job and enqueue the worker that streams it.

    Read access to the project is required. Returns 202 with the job id; the
    client polls GET .../{job_id} for status.

    Optional body ``{"task_ids": [...]}`` restricts the export to a task subset
    (selected/filtered export). Subset export is json-only — a non-empty
    ``task_ids`` with any other format is rejected (422).
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    task_ids = (data or {}).get("task_ids")
    if task_ids is not None:
        if not isinstance(task_ids, list) or not all(
            isinstance(t, str) for t in task_ids
        ):
            raise HTTPException(
                status_code=422, detail="task_ids must be a list of strings"
            )
        if not task_ids:
            task_ids = None  # empty subset == whole project
    if task_ids and format != "json":
        raise HTTPException(
            status_code=422,
            detail="Subset export (task_ids) is only supported for the json format",
        )

    job = ExportJob(
        id=str(uuid.uuid4()),
        project_id=project_id,
        requested_by=current_user.id,
        format=format,
        task_ids=task_ids,
        status=JobStatus.PENDING.value,
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        result = send_task_safe(
            "tasks.export_project", args=[job.id], queue="default"
        )
        job.celery_task_id = getattr(result, "id", None)
        db.commit()
    except Exception as exc:
        # Enqueue failed even after the client's reconnect retry — mark the job
        # failed so it isn't left pending forever, and surface 503.
        logger.error("Failed to enqueue export job %s: %s", job.id, exc)
        job.status = JobStatus.FAILED.value
        job.error_message = f"Failed to enqueue export: {exc}"
        db.commit()
        raise HTTPException(
            status_code=503, detail="Export queue unavailable, please retry"
        )

    return JSONResponse(
        status_code=202,
        content={"job_id": job.id, "status": job.status},
    )


@router.get("/{project_id}/exports/{job_id}")
async def get_export_job(
    project_id: str,
    job_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return the status of an export job (poll target for the client)."""
    job = _load_export_job_for_read(db, request, current_user, project_id, job_id)
    return _serialize_export_job(job)


@router.get("/{project_id}/exports/{job_id}/download")
async def download_export_job(
    project_id: str,
    job_id: str,
    request: Request,
    json: bool = Query(False),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Redirect to a short-lived presigned download URL for a finished export.

    The object key is read from the DB row, never from the client. Responds 404
    until the job is completed, 410 once the stored artifact has expired. With
    ``?json=1`` the presigned URL is returned in the body instead of a 302 (lets
    the frontend trigger an anchor download without following the redirect).
    """
    job = _load_export_job_for_read(db, request, current_user, project_id, job_id)

    if job.status != JobStatus.COMPLETED.value or not job.object_key:
        raise HTTPException(status_code=404, detail="Export not ready")
    if job.expires_at is not None and job.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Export has expired; re-export")

    _media_type, ext = EXPORT_FORMAT_MEDIA_TYPES.get(
        job.format or "json", ("application/octet-stream", "dat")
    )
    project = db.query(Project).filter(Project.id == project_id).first()
    safe_title = ((project.title if project else None) or "project").replace(" ", "_")
    filename = f"{safe_title}_export.{ext}"

    url = object_storage.get_download_url(
        job.object_key,
        expires_in=300,
        response_content_type=_media_type,
        response_content_disposition=f'attachment; filename="{filename}"',
    )

    if json:
        return {"url": url, "expires_in": 300}
    return RedirectResponse(url=url, status_code=302)


# ─────────────────────────────────────────────────────────────────────────────
# Async import jobs (issue #158)
#
# The inverse of the async export flow and the only import path: the client
# first gets a presigned upload URL (POST .../imports/upload-url) and PUTs the
# file straight to object storage, then POST .../imports creates an ImportJob and
# enqueues a worker that downloads + stream-imports it. The client polls
# GET .../imports/{job_id}. Object storage is mandatory (no local fallback).
#
# Two surfaces: the project-scoped routes below (/{project_id}/imports*) add
# tasks to an EXISTING project (nested label-studio format); the non-project
# routes (/project-imports*) further down create a NEW project from a
# comprehensive-format file (ImportJob.project_id is NULL until the worker
# creates the project and back-fills it).
# ─────────────────────────────────────────────────────────────────────────────

# Cap presigned import uploads so a client can't push an unbounded object into
# storage. 2 GiB comfortably covers the 583MB incident file with headroom.
_IMPORT_UPLOAD_MAX_BYTES = 2 * 1024 * 1024 * 1024


def _serialize_import_job(job: ImportJob) -> dict:
    return {
        "job_id": job.id,
        "project_id": job.project_id,
        "format": job.format,
        "status": job.status,
        "progress": job.progress,
        "byte_size": job.byte_size,
        "error_message": job.error_message,
        "result": job.result,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
    }


def _load_import_job_for_read(
    db: Session, current_user: AuthUser, project_id: str, job_id: str
) -> ImportJob:
    """Fetch an ImportJob enforcing scope + authz, or raise the right HTTP error.

    Mirrors ``_load_export_job_for_read``: readable by its requester or by anyone
    with write access to the project. 404 (not 403) when the job belongs to a
    different project so job-id existence doesn't leak across projects.
    """
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Import job not found")
    if str(job.requested_by) != str(current_user.id) and not check_project_write_access(
        db, current_user, project_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    return job


@router.post("/{project_id}/imports/upload-url")
async def create_import_upload_url(
    project_id: str,
    request: Request,
    filename: str = Query("import.json"),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Hand the client a presigned URL to upload a nested-import artifact.

    Write access to the project is required. The key is scoped to
    ``imports/.../{project_id}/`` so the later POST .../imports can verify the
    uploaded object belongs to this project.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_write_access(db, current_user, project_id):
        raise HTTPException(
            status_code=403,
            detail="Only contributors or admins can import tasks into this project",
        )

    upload = object_storage.get_upload_url(
        filename=filename,
        file_type="imports",
        user_id=project_id,
        content_type="application/json",
        max_size=_IMPORT_UPLOAD_MAX_BYTES,
    )
    return upload


@router.post("/{project_id}/imports", status_code=202)
async def create_import_job(
    project_id: str,
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create an async import job for an already-uploaded artifact and enqueue it.

    Body: ``{"object_key": "imports/.../{project_id}/..."}``. The key must live
    under the import prefix AND be scoped to this project — both are checked
    here so a client can't point the worker at an arbitrary object. Returns 202
    with the job id.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_write_access(db, current_user, project_id):
        raise HTTPException(
            status_code=403,
            detail="Only contributors or admins can import tasks into this project",
        )

    object_key = (data or {}).get("object_key")
    if not isinstance(object_key, str) or not object_key:
        raise HTTPException(status_code=400, detail="object_key is required")
    # The key was minted by create_import_upload_url for THIS project. Reject
    # anything outside the import prefix or not scoped to this project so a
    # client can't redirect the worker at someone else's upload.
    if not object_key.startswith("imports/") or f"/{project_id}/" not in object_key:
        raise HTTPException(status_code=400, detail="Invalid object_key")

    job = ImportJob(
        id=str(uuid.uuid4()),
        project_id=project_id,
        requested_by=current_user.id,
        object_key=object_key,
        status=JobStatus.PENDING.value,
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        result = send_task_safe(
            "tasks.import_project", args=[job.id], queue="default"
        )
        job.celery_task_id = getattr(result, "id", None)
        db.commit()
    except Exception as exc:
        logger.error("Failed to enqueue import job %s: %s", job.id, exc)
        job.status = JobStatus.FAILED.value
        job.error_message = f"Failed to enqueue import: {exc}"
        db.commit()
        raise HTTPException(
            status_code=503, detail="Import queue unavailable, please retry"
        )

    return JSONResponse(
        status_code=202,
        content={"job_id": job.id, "status": job.status},
    )


@router.get("/{project_id}/imports/{job_id}")
async def get_import_job(
    project_id: str,
    job_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return the status of an import job (poll target for the client)."""
    job = _load_import_job_for_read(db, current_user, project_id, job_id)
    return _serialize_import_job(job)


# ─────────────────────────────────────────────────────────────────────────────
# Async full-project import (non-project-scoped)
#
# Creates a NEW project from a comprehensive-format export. There is no
# project_id yet, so these routes live under the literal /project-imports prefix
# (the worker creates the project and back-fills ImportJob.project_id). The key
# is scoped to the requesting user instead of a project.
# ─────────────────────────────────────────────────────────────────────────────


def _load_full_import_job_for_read(
    db: Session, current_user: AuthUser, job_id: str
) -> ImportJob:
    """Fetch a full-project ImportJob (project-creating) enforcing requester authz.

    Until the worker creates the project there's no project to scope access to,
    so a full-project import job is readable only by the user who requested it.
    """
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    if str(job.requested_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    return job


@router.post("/project-imports/upload-url")
async def create_full_import_upload_url(
    request: Request,
    filename: str = Query("import.json"),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Hand the client a presigned URL to upload a full-project import artifact.

    Any authenticated user may import a project (same gate as the create-project
    flow). The key is scoped to ``imports/.../{user_id}/`` so the later
    POST /project-imports can verify the uploaded object belongs to this user.
    """
    upload = object_storage.get_upload_url(
        filename=filename,
        file_type="imports",
        user_id=current_user.id,
        content_type="application/json",
        max_size=_IMPORT_UPLOAD_MAX_BYTES,
    )
    return upload


@router.post("/project-imports", status_code=202)
async def create_full_import_job(
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create a full-project (create-new) import job and enqueue it.

    Body: ``{"object_key": "imports/.../{user_id}/..."}``. The key must live
    under the import prefix AND be scoped to this user — both checked here so a
    client can't point the worker at someone else's upload. The job's
    ``project_id`` is NULL until the worker creates the project. Returns 202.
    """
    object_key = (data or {}).get("object_key")
    if not isinstance(object_key, str) or not object_key:
        raise HTTPException(status_code=400, detail="object_key is required")
    if not object_key.startswith("imports/") or f"/{current_user.id}/" not in object_key:
        raise HTTPException(status_code=400, detail="Invalid object_key")

    job = ImportJob(
        id=str(uuid.uuid4()),
        project_id=None,
        requested_by=current_user.id,
        object_key=object_key,
        status=JobStatus.PENDING.value,
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        result = send_task_safe(
            "tasks.import_project", args=[job.id], queue="default"
        )
        job.celery_task_id = getattr(result, "id", None)
        db.commit()
    except Exception as exc:
        logger.error("Failed to enqueue full-project import job %s: %s", job.id, exc)
        job.status = JobStatus.FAILED.value
        job.error_message = f"Failed to enqueue import: {exc}"
        db.commit()
        raise HTTPException(
            status_code=503, detail="Import queue unavailable, please retry"
        )

    return JSONResponse(
        status_code=202,
        content={"job_id": job.id, "status": job.status},
    )


@router.get("/project-imports/{job_id}")
async def get_full_import_job(
    job_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return the status of a full-project import job (poll target)."""
    job = _load_full_import_job_for_read(db, current_user, job_id)
    return _serialize_import_job(job)


# Task batch for the bulk-export JSON spool below; matches the import side's
# flush cadence (_IMPORT_BATCH) rather than export_stream's eval-aware batching
# because this endpoint serializes tasks only.
_BULK_EXPORT_TASK_BATCH = 200


@router.post("/bulk-export")
async def bulk_export_projects(
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk export multiple projects (multi-project admin export).

    Stays synchronous by design (see CLAUDE.md "Object storage"), but must not
    hold the selection in RAM: the JSON body is spooled to a tempfile with each
    project's tasks streamed straight into it via yield_per + expunge, so peak
    memory scales with one task batch, not with N projects' tasks. The legacy
    builder loaded every task of every selected project and json.dumps-ed the
    whole thing — the same O(dataset) shape that OOMKilled the pod on the
    bulk-export-full path on 2026-05-31.
    """
    project_ids = data.get("project_ids", [])
    format = data.get("format", "json")
    include_data = data.get("include_data", True)

    if format not in ("json", "csv"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    org_context = get_org_context_from_request(request)

    # Light per-project metadata only; tasks never enter this list.
    project_metas = []
    for project_id in project_ids:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            continue

        # Check access permission via org-context-aware helper
        if not check_project_accessible(db, current_user, project_id, org_context):
            continue

        task_count = db.query(Task).filter(Task.project_id == project.id).count()
        annotation_count = (
            db.query(Annotation)
            .filter(Annotation.project_id == project.id, Annotation.was_cancelled == False)  # noqa: E712
            .count()
        )

        project_metas.append(
            {
                "id": project.id,
                "title": project.title,
                "description": project.description,
                "created_at": (project.created_at.isoformat() if project.created_at else None),
                "created_by": project.created_by,
                "task_count": task_count,
                "annotation_count": annotation_count,
                "label_config": project.label_config,
                "expert_instruction": project.expert_instruction,
            }
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if format == "csv":
        # CSV is metadata-only rows — O(#projects), no spooling needed.
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "project_id",
                "project_title",
                "description",
                "task_count",
                "annotation_count",
                "created_at",
            ]
        )
        for meta in project_metas:
            writer.writerow(
                [
                    meta["id"],
                    meta["title"],
                    meta.get("description", ""),
                    meta["task_count"],
                    meta["annotation_count"],
                    meta["created_at"],
                ]
            )
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename="
                f"projects_bulk_export_{timestamp}.csv"
            },
        )

    filename = f"projects_bulk_export_{timestamp}.json"
    spool = tempfile.NamedTemporaryFile(
        prefix="benger-bulk-export-", suffix=".json", delete=False
    )
    spool_path = spool.name
    spool.close()  # FileResponse opens it; we just needed the path.

    try:
        with open(spool_path, "w", encoding="utf-8") as out:
            out.write('{"projects": [')
            for idx, meta in enumerate(project_metas):
                if idx:
                    out.write(", ")
                head = json.dumps(meta, ensure_ascii=False)
                if not include_data:
                    out.write(head)
                    continue
                # json.dumps of a non-empty dict always ends in '}'; strip it
                # to splice the streamed `tasks` array into the same object.
                out.write(head[:-1] + ', "tasks": [')
                first = True
                task_q = db.query(Task).filter(Task.project_id == meta["id"])
                for task in task_q.yield_per(_BULK_EXPORT_TASK_BATCH):
                    if not first:
                        out.write(", ")
                    out.write(
                        json.dumps(
                            {
                                "id": task.id,
                                "data": task.data,
                                "meta": task.meta,
                                "is_labeled": task.is_labeled,
                                "created_at": (
                                    task.created_at.isoformat() if task.created_at else None
                                ),
                                # Annotation export was never implemented on
                                # this endpoint (the legacy builder hardcoded
                                # an empty list); the key stays so the response
                                # shape is unchanged.
                                "annotations": [],
                            },
                            ensure_ascii=False,
                        )
                    )
                    first = False
                    db.expunge(task)
                out.write("]}")
            out.write(
                '], "exported_at": '
                + json.dumps(datetime.now().isoformat())
                + ', "format": '
                + json.dumps(format)
                + "}"
            )
    except BaseException:
        # If anything blows up mid-build, don't leak the tempfile.
        try:
            os.unlink(spool_path)
        except OSError:
            pass
        raise

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    return FileResponse(
        path=spool_path,
        media_type="application/json",
        filename=filename,
        background=BackgroundTask(os.unlink, spool_path),
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/bulk-export-full")
async def bulk_export_full_projects(
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Export complete projects as individual JSON files in a ZIP archive.

    This endpoint provides full project migration capabilities by exporting
    all project data including tasks, annotations, generations, evaluations,
    and user assignments.

    Request body:
    {
        "project_ids": ["project-1", "project-2", ...]
    }

    Returns: ZIP file containing individual project JSON files
    """
    project_ids = data.get("project_ids", [])
    if not project_ids:
        raise HTTPException(status_code=400, detail="No project IDs provided")

    org_context = get_org_context_from_request(request)

    logger.info(
        "bulk-export-full: %d project(s) requested by %s",
        len(project_ids),
        current_user.email,
    )

    # Write the ZIP to a tempfile on disk and stream each project's JSON
    # directly into its zip entry via `json.dump`, which writes chunks as it
    # walks the object tree. Previous revisions held the full zip in a
    # BytesIO AND `json.dumps()`-d each project's dict into a giant string
    # before adding it — for a Benchathon-sized project that's ~3× the
    # row-set's RAM and OOMKilled the API pod on 2026-05-31. With the
    # on-disk zip + incremental writer, peak memory now scales with one
    # project's Python dict, not with N projects' serialized output.
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"benger_projects_export_{timestamp}.zip"
    zip_fd = tempfile.NamedTemporaryFile(
        prefix="benger-bulk-export-full-", suffix=".zip", delete=False
    )
    zip_path = zip_fd.name
    zip_fd.close()  # FileResponse opens it; we just needed the path.

    exported_count = 0
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for project_id in project_ids:
                try:
                    project = db.query(Project).filter(Project.id == project_id).first()
                    if not project:
                        logger.warning(
                            "bulk-export-full: project %s not found, skipping",
                            project_id,
                        )
                        continue

                    if not check_project_accessible(db, current_user, project_id, org_context):
                        logger.warning(
                            "bulk-export-full: access denied for project %s, skipping",
                            project_id,
                        )
                        continue

                    safe_title = "".join(
                        c for c in project.title if c.isalnum() or c in (' ', '-', '_')
                    ).rstrip()
                    safe_title = safe_title[:50]
                    entry_name = f"{safe_title}_{project_id[:8]}.json"

                    # Stream each project's JSON straight into its zip entry
                    # via `stream_comprehensive_project_data_json` — the helper
                    # yields chunks with `yield_per` so the full clone payload
                    # (tasks + annotations + generations + task_evaluations
                    # in mode="full") never lives in RAM as one dict. zip.open(
                    # ..., 'w') returns a binary writer; we encode each text
                    # chunk to UTF-8 and write directly so we don't stack a
                    # TextIOWrapper buffer on top of zip's deflate stream.
                    with zip_file.open(entry_name, 'w') as raw_entry:
                        for chunk in stream_comprehensive_project_data_json(
                            db, project_id
                        ):
                            raw_entry.write(chunk.encode("utf-8"))

                    exported_count += 1

                except Exception as e:
                    logger.error(
                        "bulk-export-full: error exporting project %s: %s",
                        project_id,
                        e,
                        exc_info=True,
                    )
                    continue
    except BaseException:
        # If anything blows up mid-build, don't leak the tempfile.
        try:
            os.unlink(zip_path)
        except OSError:
            pass
        raise

    if exported_count == 0:
        try:
            os.unlink(zip_path)
        except OSError:
            pass
        raise HTTPException(status_code=404, detail="No projects could be exported")

    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_filename,
        background=BackgroundTask(os.unlink, zip_path),
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"},
    )
