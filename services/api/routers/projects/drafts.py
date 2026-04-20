"""Draft persistence endpoints for annotation crash recovery."""

import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from project_models import Project, TaskDraft
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
