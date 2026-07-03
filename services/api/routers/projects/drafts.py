"""Draft persistence endpoints for annotation crash recovery."""

import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from project_models import Project, TaskDraft, TaskDraftCheckpoint
from routers.projects.helpers import (
    check_project_accessible,
    check_task_assigned_to_user,
    get_org_context_from_request,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.put("/{project_id}/tasks/{task_id}/draft")
async def save_draft(
    project_id: str,
    task_id: str,
    request: Request,
    body: Dict[str, Any] = Body(...),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Save draft annotation data for a task.

    Called periodically by the frontend (every 30s) when annotations change.
    Upserts into task_drafts table for crash recovery.
    """
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    project = db.query(Project).filter(Project.id == project_id).first()
    if project and not check_task_assigned_to_user(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")

    draft_result = body.get("result", [])

    existing_draft = (
        db.query(TaskDraft)
        .filter(
            TaskDraft.task_id == task_id,
            TaskDraft.user_id == current_user.id,
        )
        .first()
    )

    if existing_draft:
        existing_draft.draft_result = draft_result
    else:
        db.add(TaskDraft(
            id=str(uuid.uuid4()),
            task_id=task_id,
            user_id=current_user.id,
            project_id=project_id,
            draft_result=draft_result,
        ))

    db.commit()

    # Notify extended features (e.g. timer session draft mirroring)
    from extensions import on_draft_saved
    on_draft_saved(db, task_id, current_user.id, project_id, draft_result)

    return {"status": "ok"}


# Max checkpoint snapshots retained per (task, user). A 2.5h exam at the 5-min
# interval produces ~30 snapshots, so this never prunes a normal sitting; it
# only bounds pathological growth.
CHECKPOINT_RETENTION = 200


def _draft_has_content(draft_result: Any) -> bool:
    """True if the draft payload carries any non-empty field content.

    Backstop for the client-side content guard so empty/no-op snapshots are not
    persisted. Recognises the markdown (``value.markdown``), plain-text
    (``value.text``/string) and span (``value.spans``) annotation shapes.
    """
    if not isinstance(draft_result, list):
        return False
    for entry in draft_result:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, dict):
            md = value.get("markdown")
            if isinstance(md, str) and md.strip():
                return True
            text = value.get("text")
            if isinstance(text, str) and text.strip():
                return True
            if value.get("spans") or (isinstance(text, list) and text):
                return True
    return False


def _require_task_access(db, request, current_user, project_id, task_id):
    """Shared access guard (mirrors save_draft); returns the Project or raises."""
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")
    project = db.query(Project).filter(Project.id == project_id).first()
    if project and not check_task_assigned_to_user(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")
    return project


@router.post("/{project_id}/tasks/{task_id}/checkpoint")
async def save_checkpoint(
    project_id: str,
    task_id: str,
    request: Request,
    body: Dict[str, Any] = Body(...),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Append a restorable draft checkpoint (opt-in).

    Unlike the live ``/draft`` upsert, this is append-only and is NOT deleted on
    submit, so the annotator can restore an earlier snapshot. No-op unless the
    project has ``restorable_checkpoints_enabled``; empty payloads are skipped;
    history is capped at ``CHECKPOINT_RETENTION`` per (task, user).
    """
    project = _require_task_access(db, request, current_user, project_id, task_id)

    if not (project and project.restorable_checkpoints_enabled):
        # Feature off for this project — accept the call as a harmless no-op.
        return {"status": "disabled"}

    draft_result = body.get("result", [])
    if not _draft_has_content(draft_result):
        return {"status": "skipped_empty"}

    checkpoint = TaskDraftCheckpoint(
        id=str(uuid.uuid4()),
        task_id=task_id,
        user_id=current_user.id,
        project_id=project_id,
        draft_result=draft_result,
    )
    db.add(checkpoint)
    db.commit()
    db.refresh(checkpoint)

    # Prune oldest snapshots beyond the retention cap for this (task, user).
    stale_ids = [
        row.id
        for row in (
            db.query(TaskDraftCheckpoint.id)
            .filter(
                TaskDraftCheckpoint.task_id == task_id,
                TaskDraftCheckpoint.user_id == current_user.id,
            )
            .order_by(TaskDraftCheckpoint.created_at.desc())
            .offset(CHECKPOINT_RETENTION)
            .all()
        )
    ]
    if stale_ids:
        db.query(TaskDraftCheckpoint).filter(
            TaskDraftCheckpoint.id.in_(stale_ids)
        ).delete(synchronize_session=False)
        db.commit()

    return {
        "status": "ok",
        "checkpoint_id": checkpoint.id,
        "created_at": checkpoint.created_at.isoformat(),
    }


@router.get("/{project_id}/tasks/{task_id}/checkpoints")
async def list_checkpoints(
    project_id: str,
    task_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List the current user's checkpoint snapshots for a task (newest first).

    Metadata only — the full snapshot is fetched via the by-id endpoint.
    """
    _require_task_access(db, request, current_user, project_id, task_id)

    rows = (
        db.query(TaskDraftCheckpoint)
        .filter(
            TaskDraftCheckpoint.task_id == task_id,
            TaskDraftCheckpoint.user_id == current_user.id,
        )
        .order_by(TaskDraftCheckpoint.created_at.desc())
        .all()
    )
    return {
        "checkpoints": [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "size": len(str(row.draft_result)) if row.draft_result else 0,
            }
            for row in rows
        ]
    }


@router.get("/{project_id}/tasks/{task_id}/checkpoints/{checkpoint_id}")
async def get_checkpoint(
    project_id: str,
    task_id: str,
    checkpoint_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Fetch a single checkpoint's full snapshot (scoped to the current user)."""
    _require_task_access(db, request, current_user, project_id, task_id)

    checkpoint = (
        db.query(TaskDraftCheckpoint)
        .filter(
            TaskDraftCheckpoint.id == checkpoint_id,
            TaskDraftCheckpoint.task_id == task_id,
            TaskDraftCheckpoint.user_id == current_user.id,
        )
        .first()
    )
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    return {
        "id": checkpoint.id,
        "created_at": checkpoint.created_at.isoformat(),
        "result": checkpoint.draft_result,
    }
