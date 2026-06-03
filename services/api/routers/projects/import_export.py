"""Project import and export endpoints."""

import csv
import io
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

# Spool incoming import bodies in RAM up to this size; spill to disk above it.
# Keeps small imports allocation-free (no disk hit, no regression vs the
# previous Pydantic auto-parse path) while bounding peak heap on multi-MB
# imports — the API-side mirror of the proxy's response-streaming fix (GH #68).
_IMPORT_SPOOL_THRESHOLD = 4 * 1024 * 1024

logger = logging.getLogger(__name__)


def _logged_export_stream(
    chunk_iter: Iterator[str],
    *,
    project_id: str,
    user_id: str,
    export_format: str,
    counts: Optional[dict] = None,
) -> Iterator[bytes]:
    """Wrap an export chunk generator to emit start/completion/abort logs.

    Yields UTF-8 *bytes* (encoding once here, so the byte tally is exact and
    Starlette doesn't re-encode the str). A client disconnect surfaces as
    GeneratorExit when the response is torn down mid-flight — logged as a
    distinct WARNING from an internal error so aborted/partial downloads are
    diagnosable. Before this, the 2026-05-31 Benchathon export OOMKilled the
    pod and truncated silently with no server-side trace at all.
    """
    started = time.monotonic()
    total_bytes = 0
    logger.info(
        "export start project=%s user=%s format=%s counts=%s",
        project_id, user_id, export_format, counts or {},
    )
    try:
        for chunk in chunk_iter:
            data = chunk.encode("utf-8")
            total_bytes += len(data)
            yield data
    except GeneratorExit:
        logger.warning(
            "export aborted (client disconnect) project=%s user=%s format=%s "
            "bytes=%d elapsed=%.2fs",
            project_id, user_id, export_format, total_bytes,
            time.monotonic() - started,
        )
        raise
    except Exception:
        logger.exception(
            "export failed project=%s user=%s format=%s bytes=%d elapsed=%.2fs",
            project_id, user_id, export_format, total_bytes,
            time.monotonic() - started,
        )
        raise
    else:
        logger.info(
            "export complete project=%s user=%s format=%s bytes=%d elapsed=%.2fs",
            project_id, user_id, export_format, total_bytes,
            time.monotonic() - started,
        )


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


from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile  # noqa: E402
from fastapi.responses import (  # noqa: E402
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from sqlalchemy.orm import Session  # noqa: E402

from auth_module import require_user  # noqa: E402
from auth_module.models import User as AuthUser  # noqa: E402
from celery_client import send_task_safe  # noqa: E402
from database import get_db  # noqa: E402
from object_storage import object_storage  # noqa: E402
from routers.projects._export_stream import (  # noqa: E402
    EXPORT_FORMAT_MEDIA_TYPES,
    build_json_export_header_fields,
    stream_comprehensive_project_data_json,
    stream_export_flat_csv,
    stream_export_json,
    stream_export_label_studio,
    stream_export_txt,
)
from routers.projects._import_stream import (  # noqa: E402,F401
    _IMPORT_BATCH,  # re-exported for tests/integration/test_import_streaming_batch.py
    ImportValidationError,
    convert_from_label_studio_format,
    run_full_project_import,
    run_nested_import,
)
from models import (  # noqa: E402
    ExportJob,
    ImportJob,
    JobStatus,
    User,
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


@router.post("/{project_id}/import")
async def import_project_data(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Import tasks and annotations into an existing project.

    Supports Label Studio format with BenGER extensions.
    """
    # Stream the request body into a seekable spool, then hand it to the shared
    # streaming driver (issue #158). run_nested_import parses incrementally with
    # ijson and inserts in flush-batched passes, so a 583MB export no longer
    # balloons to O(file) resident. The same driver backs the async import
    # worker, keeping the sync and async import paths identical.
    spooled = tempfile.SpooledTemporaryFile(max_size=_IMPORT_SPOOL_THRESHOLD)
    try:
        async for chunk in request.stream():
            spooled.write(chunk)

        # Access checks run before the parse now that the import body lives in
        # run_nested_import; an inaccessible/missing project short-circuits
        # without touching the (potentially huge) payload.
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        # Importing tasks is a write/contribute action — require ORG_ADMIN or
        # CONTRIBUTOR effective role. Public-tier ANNOTATOR visitors are blocked.
        if not check_project_write_access(db, current_user, project_id):
            raise HTTPException(
                status_code=403,
                detail="Only contributors or admins can import tasks into this project",
            )

        return run_nested_import(db, project_id, spooled, current_user.id)

    except ImportValidationError as e:
        # Malformed / mistyped payload -> the same 4xx the inline parser raised.
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except HTTPException:
        # Validation / access errors keep their status code; roll back any rows
        # flushed before the failure so nothing partial commits.
        db.rollback()
        raise
    except Exception as e:
        # Rollback on any error
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to import data: {str(e)}")
    finally:
        spooled.close()


@router.get("/{project_id}/export")
async def export_project(
    project_id: str,
    request: Request,
    format: str = Query("json", pattern="^(json|csv|tsv|txt|label_studio)$"),
    download: bool = Query(True),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Export project data and annotations in various formats"""

    # Verify project exists and user has access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Every format streams via a per-format generator in export_stream. The
    # legacy in-memory builder that loaded the whole project (tasks +
    # annotations + generations + task_evaluations) into one dict and
    # json.dumps()-ed it is gone — it peaked past the 3Gi API memory limit on
    # the Benchathon project (~8k task_evaluations, ~400 MB output) and
    # OOMKilled the pod mid-response (#158).
    if format == "json":
        # Header (project metadata + count tallies) is built by the shared
        # helper so the async worker export emits a byte-identical header.
        header_fields = build_json_export_header_fields(db, project)
        project_header = header_fields["project"]

        headers = {}
        if download:
            filename = f"{project.title.replace(' ', '_')}_export.json"
            headers["Content-Disposition"] = f"attachment; filename={filename}"

        return StreamingResponse(
            _logged_export_stream(
                stream_export_json(
                    db, project_id, task_ids=None, header_fields=header_fields
                ),
                project_id=project_id,
                user_id=current_user.id,
                export_format="json",
                counts={
                    "tasks": project_header["task_count"],
                    "annotations": project_header["annotation_count"],
                    "generations": project_header["generation_count"],
                    "evaluation_runs": project_header["evaluation_run_count"],
                    "task_evaluations": project_header["task_evaluation_count"],
                },
            ),
            media_type="application/json",
            headers=headers,
        )

    if format in ("csv", "tsv"):
        delimiter = "," if format == "csv" else "\t"
        media_type = "text/csv" if format == "csv" else "text/tab-separated-values"
        ext = "csv" if format == "csv" else "tsv"
        headers = {}
        if download:
            filename = f"{project.title.replace(' ', '_')}_export.{ext}"
            headers["Content-Disposition"] = f"attachment; filename={filename}"
        return StreamingResponse(
            _logged_export_stream(
                stream_export_flat_csv(db, project_id, delimiter=delimiter),
                project_id=project_id,
                user_id=current_user.id,
                export_format=format,
            ),
            media_type=media_type,
            headers=headers,
        )

    if format == "label_studio":
        headers = {}
        if download:
            filename = f"{project.title.replace(' ', '_')}_label_studio.json"
            headers["Content-Disposition"] = f"attachment; filename={filename}"
        return StreamingResponse(
            _logged_export_stream(
                stream_export_label_studio(db, project_id),
                project_id=project_id,
                user_id=current_user.id,
                export_format="label_studio",
            ),
            media_type="application/json",
            headers=headers,
        )

    # txt — the only remaining format (json/csv/tsv/label_studio short-circuit
    # above). Streamed too so peak memory stays bounded; the Query() pattern
    # rejects anything else before we ever reach this point.
    headers = {}
    if download:
        filename = f"{project.title.replace(' ', '_')}_export.txt"
        headers["Content-Disposition"] = f"attachment; filename={filename}"
    return StreamingResponse(
        _logged_export_stream(
            stream_export_txt(db, project_id, project.title, project.description),
            project_id=project_id,
            user_id=current_user.id,
            export_format="txt",
        ),
        media_type="text/plain",
        headers=headers,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Async export jobs (issue #158)
#
# The synchronous GET /export above streams the whole project through the API
# request thread — fine for small projects, but it OOMKilled the pod on the
# Benchathon export. These endpoints move the bulk data plane off the request
# path: POST enqueues a worker that streams the export into object storage; the
# client polls GET .../{job_id} and then downloads via a short-lived presigned
# URL (GET .../{job_id}/download), so the bytes never transit the API or the
# browser-RAM Blob. The legacy GET /export stays as the small-export fallback.
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
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create an async export job and enqueue the worker that streams it.

    Access mirrors the synchronous GET /export (read access to the project).
    Returns 202 with the job id; the client polls GET .../{job_id} for status.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Async export needs object storage to hand the client a presigned download
    # URL. With the local backend the worker writes to its own pod's disk, which
    # the API can't serve cross-pod — so refuse here (409) and let the client
    # fall back to the synchronous streaming export. This keeps the whole async
    # path inert until MinIO is enabled (STORAGE_TYPE set).
    if object_storage.storage_backend == "local":
        raise HTTPException(
            status_code=409,
            detail="Async export unavailable: object storage is not configured.",
        )

    job = ExportJob(
        id=str(uuid.uuid4()),
        project_id=project_id,
        requested_by=current_user.id,
        format=format,
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
# The inverse of the async export flow. The synchronous POST /import and
# POST /import-project above stream-parse the uploaded body in the request
# thread, which is bounded now (ijson) but still ties up an API worker for the
# whole parse of a multi-GB file. These endpoints move that off the request
# path: the client first gets a presigned upload URL (POST .../imports/upload-url)
# and PUTs the file straight to object storage, then POST .../imports creates an
# ImportJob and enqueues a worker that downloads + stream-imports it. The client
# polls GET .../imports/{job_id}. Inert until object storage is configured (409
# on the local backend), so the frontend falls back to the synchronous path.
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
    """Hand the client a presigned URL to upload an import artifact to storage.

    Write access to the project is required (same gate as POST /import). The key
    is scoped to ``imports/.../{project_id}/`` so the later POST .../imports can
    verify the uploaded object belongs to this project. Inert on the local
    backend (409) — the client then falls back to the synchronous import.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_write_access(db, current_user, project_id):
        raise HTTPException(
            status_code=403,
            detail="Only contributors or admins can import tasks into this project",
        )

    if object_storage.storage_backend == "local":
        raise HTTPException(
            status_code=409,
            detail="Async import unavailable: object storage is not configured.",
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
    here so a client can't point the worker at an arbitrary object. Inert on the
    local backend (409). Returns 202 with the job id.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_write_access(db, current_user, project_id):
        raise HTTPException(
            status_code=403,
            detail="Only contributors or admins can import tasks into this project",
        )

    if object_storage.storage_backend == "local":
        raise HTTPException(
            status_code=409,
            detail="Async import unavailable: object storage is not configured.",
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


@router.post("/bulk-export")
async def bulk_export_projects(
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk export multiple projects"""

    project_ids = data.get("project_ids", [])
    format = data.get("format", "json")
    include_data = data.get("include_data", True)

    org_context = get_org_context_from_request(request)

    export_data = {
        "projects": [],
        "exported_at": datetime.now().isoformat(),
        "format": format,
    }

    for project_id in project_ids:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            continue

        # Check access permission via org-context-aware helper
        if not check_project_accessible(db, current_user, project_id, org_context):
            continue

        # Calculate counts dynamically
        task_count = db.query(Task).filter(Task.project_id == project.id).count()
        annotation_count = (
            db.query(Annotation)
            .filter(Annotation.project_id == project.id, Annotation.was_cancelled == False)  # noqa: E712
            .count()
        )

        project_data = {
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

        if include_data:
            # Include tasks and annotations
            tasks = db.query(Task).filter(Task.project_id == project_id).all()
            # NOTE: Annotation table doesn't exist yet - returning empty list
            annotations = (
                []
            )  # db.query(Annotation).filter(Annotation.project_id == project_id).all()

            project_data["tasks"] = []
            for task in tasks:
                task_data = {
                    "id": task.id,
                    "data": task.data,
                    "meta": task.meta,
                    "is_labeled": task.is_labeled,
                    "created_at": (task.created_at.isoformat() if task.created_at else None),
                }

                # Add annotations for this task
                task_annotations = [a for a in annotations if a.task_id == task.id]
                task_data["annotations"] = []
                for ann in task_annotations:
                    task_data["annotations"].append(
                        {
                            "id": ann.id,
                            "result": ann.result,
                            "completed_by": ann.completed_by,
                            "created_at": (ann.created_at.isoformat() if ann.created_at else None),
                            "was_cancelled": ann.was_cancelled,
                        }
                    )

                project_data["tasks"].append(task_data)

        export_data["projects"].append(project_data)

    # Format the response
    if format == "json":
        content = json.dumps(export_data, indent=2)
        media_type = "application/json"
        filename = f"projects_bulk_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    elif format == "csv":
        # For CSV, we'll create a simplified flat structure
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
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

        # Data rows
        for project in export_data["projects"]:
            writer.writerow(
                [
                    project["id"],
                    project["title"],
                    project.get("description", ""),
                    project["task_count"],
                    project["annotation_count"],
                    project["created_at"],
                ]
            )

        content = output.getvalue()
        media_type = "text/csv"
        filename = f"projects_bulk_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    return Response(
        content=content,
        media_type=media_type,
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


@router.post("/import-project")
async def import_full_project(
    request: Request,
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Import a complete project from a comprehensive export JSON file.

    This endpoint creates a new project with all associated data including:
    - Project configuration
    - All tasks with metadata
    - All annotations
    - All LLM generations
    - All evaluations
    - Project members and assignments (mapped to current users)

    Handles conflicts by:
    - Auto-renaming project if name exists
    - Generating new UUIDs for all entities
    - Mapping users to existing users by email (or creating placeholders)

    Returns: Created project information with import statistics
    """
    get_org_context_from_request(request)
    # Extract the upload into a seekable spool, then hand it to the shared
    # streaming driver (run_full_project_import), which parses incrementally
    # with ijson instead of json.load-ing the whole document — a 583MB
    # comprehensive export balloons to 2-4GB resident and OOM-kills the pod
    # (issue #158). zip inner streams are non-seekable, so we copy the inner
    # JSON into the spool with a bounded buffer (shutil.copyfileobj) rather than
    # reading it whole.
    spooled = tempfile.SpooledTemporaryFile(max_size=_IMPORT_SPOOL_THRESHOLD)
    try:
        if file.filename.endswith('.zip'):
            try:
                with zipfile.ZipFile(file.file, 'r') as zip_file:
                    json_files = [f for f in zip_file.namelist() if f.endswith('.json')]
                    if not json_files:
                        raise HTTPException(
                            status_code=400, detail="ZIP file contains no JSON files"
                        )
                    # Use first JSON file found (for single project import)
                    with zip_file.open(json_files[0]) as inner_json:
                        shutil.copyfileobj(inner_json, spooled)
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="Invalid ZIP file format")
        elif file.filename.endswith('.json'):
            shutil.copyfileobj(file.file, spooled)
        else:
            raise HTTPException(status_code=400, detail="Only JSON and ZIP files are supported")

        # Hand the spooled inner JSON to the shared streaming driver. It parses
        # incrementally with ijson and inserts each entity array in FK-dependency
        # order with flush-batched passes, committing once at the end (issue
        # #158). The same driver backs the async import worker.
        return run_full_project_import(db, spooled, current_user.id)

    except ImportValidationError as e:
        # Unsupported version / missing project / malformed JSON / no-org user ->
        # the same 400 the inline parser raised.
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except HTTPException:
        # Validation / access errors keep their status; roll back any rows
        # flushed by an earlier batch so a partial project can't persist.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        spooled.close()
