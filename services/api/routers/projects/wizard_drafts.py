"""Creation-wizard drafts (CORE 2.55, migration 141).

The creation wizard of an exam creates a real project when the teacher leaves
its first step, so the tasks and grading sheets exist (and can be generated
and checked) before "Create". Until then the project is a draft:
``is_wizard_draft = true``, private, no organization rows, never listed
(``project_models.project_listable``). Where the finished project will live
(the target organization and group, validated with the create rules), the
wizard state and the expiry are kept in ``project_wizard_drafts``. The finish
route applies the visibility and the organizations and clears the flag in one
transaction, as the last write of the wizard, so a project becomes visible to
others only once it is complete.

Routes (all under ``/api/projects``):

- ``POST /wizard-drafts``: create (idempotent per ``client_key``).
- ``GET /wizard-drafts``: the caller's unfinished drafts.
- ``GET /{id}/wizard-draft``: state, version, step, target, expiry.
- ``PUT /{id}/wizard-draft``: save the state (``if_version``; 409
  ``draft_version_conflict``, 413 ``draft_state_too_large``), optionally move
  the target.
- ``POST /{id}/wizard-draft/finish``: finish (idempotent per ``client_key``).
- ``DELETE /{id}/wizard-draft``: discard (soft delete, then the batched
  purge); ``DELETE /{id}`` on a draft does the same.
- ``GET /{id}/wizard-draft/tasks`` and ``PUT /{id}/wizard-draft/tasks/{tid}``:
  the wizard's task sync (row hashes, the sheets a change would set aside,
  in-place replacement of a changed row).

Only the creator (and superadmins) may use a draft. A deleted draft (discarded
or swept after :data:`wizard_drafts.WIZARD_DRAFT_RETENTION`) answers 404
``draft_expired``.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_async_db
from models import Organization, User
from project_models import (
    Project,
    ProjectOrganization,
    ProjectWizardDraft,
    RubricGenerationJob,
    Task,
    TaskRubric,
)
from project_schemas import ProjectResponse
from routers.projects.helpers import (
    get_project_access_tier_async,
    require_org_key_own_organization,
)
from services.label_config.validator import LabelConfigValidator
from task_rubric_service import archive_task_rubric
from wizard_drafts import WIZARD_DRAFT_STATE_MAX_BYTES, draft_expires_at

logger = logging.getLogger(__name__)

router = APIRouter()

#: Statuses of a rubric generation job that has not ended yet.
_RUNNING_GENERATION_STATUSES = ("queued", "running")


def _error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message, **extra}
    )


def _expired() -> HTTPException:
    return _error(
        404,
        "draft_expired",
        "This draft no longer exists: it was discarded or expired after 30 days "
        "without changes.",
    )


def _not_a_draft() -> HTTPException:
    return _error(409, "not_wizard_draft", "This project is not a wizard draft")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WizardDraftTarget(BaseModel):
    target_organization_id: Optional[str] = Field(None, max_length=64)
    target_group_id: Optional[str] = Field(None, max_length=64)


class WizardDraftCreate(WizardDraftTarget):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    kind: Optional[str] = Field(None, max_length=32)
    label_config: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=16)
    client_key: str = Field(..., min_length=1, max_length=64)
    state: Optional[Dict[str, Any]] = None
    step_id: Optional[str] = Field(None, max_length=64)


class WizardDraftSave(WizardDraftTarget):
    state: Optional[Dict[str, Any]] = None
    step_id: Optional[str] = Field(None, max_length=64)
    if_version: int = Field(..., ge=1)


class WizardDraftAttachment(BaseModel):
    organization_id: str = Field(..., min_length=1, max_length=64)
    group_id: Optional[str] = Field(None, max_length=64)


class WizardDraftFinish(BaseModel):
    client_key: str = Field(..., min_length=1, max_length=64)
    visibility: Literal["private", "organization", "public"]
    public_role: Optional[Literal["ANNOTATOR", "CONTRIBUTOR"]] = None
    organization_attachments: List[WizardDraftAttachment] = Field(default_factory=list)


class WizardDraftTaskUpdate(BaseModel):
    data: Dict[str, Any]
    row_hash: str = Field(..., min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _summary(project: Project, draft: ProjectWizardDraft) -> Dict[str, Any]:
    return {
        "project_id": project.id,
        "title": project.title,
        "kind": project.kind,
        "icon": project.icon,
        "step_id": draft.step_id,
        "target_organization_id": draft.target_organization_id,
        "target_group_id": draft.target_group_id,
        "created_at": _iso(draft.created_at),
        "touched_at": _iso(draft.touched_at),
        "expires_at": _iso(draft_expires_at(draft.touched_at)),
    }


def _payload(project: Project, draft: ProjectWizardDraft) -> Dict[str, Any]:
    return {
        **_summary(project, draft),
        "client_key": draft.client_key,
        "state": draft.state,
        "state_version": draft.state_version,
    }


def _state_size(state: Optional[Dict[str, Any]]) -> int:
    if state is None:
        return 0
    return len(json.dumps(state, separators=(",", ":"), default=str).encode("utf-8"))


def _check_state_size(state: Optional[Dict[str, Any]]) -> None:
    if _state_size(state) > WIZARD_DRAFT_STATE_MAX_BYTES:
        raise _error(
            413,
            "draft_state_too_large",
            "The wizard state is larger than 2 MB and was not saved",
        )


async def _validate_target(
    db: AsyncSession,
    user,
    org_id: Optional[str],
    group_id: Optional[str],
    *,
    request: Optional[Request] = None,
) -> None:
    """The creation target of ``POST /projects``, checked with its rules for
    ``user`` but stored on the draft instead of inserting an organization
    row. With ``request``, an organization access key must name its own
    organization (``require_org_key_own_organization``)."""
    from routers.projects.crud import (
        _require_attachment_creator_role,
        _require_attachment_member,
        _validate_group_attachment,
    )

    if group_id and not org_id:
        raise HTTPException(status_code=400, detail="A group needs its organization")
    if request is not None:
        require_org_key_own_organization(request, org_id)
    if not org_id:
        return
    exists = (
        await db.execute(select(Organization.id).where(Organization.id == org_id))
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="Target organization not found")
    if group_id:
        await _require_attachment_member(db, user, org_id)
        await _validate_group_attachment(db, user, org_id, group_id)
    else:
        await _require_attachment_creator_role(db, user, org_id)


async def _load_project(
    db: AsyncSession, project_id: str, current_user, *, lock: bool = False
) -> Project:
    """The draft project for its creator or a superadmin. 404 when missing,
    404 ``draft_expired`` when deleted, 403 for anyone else, 409
    ``not_wizard_draft`` for a regular project."""
    stmt = select(Project).where(Project.id == project_id)
    if lock:
        stmt = stmt.with_for_update()
    project = (await db.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not current_user.is_superadmin and str(project.created_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Only the creator can use this draft")
    if project.deleted_at is not None:
        raise _expired()
    return project


async def _draft_row(db: AsyncSession, project_id: str, *, lock: bool = False):
    stmt = select(ProjectWizardDraft).where(ProjectWizardDraft.project_id == project_id)
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def _load_draft(db: AsyncSession, project_id: str, current_user, *, lock: bool = False):
    project = await _load_project(db, project_id, current_user, lock=lock)
    if not project.is_wizard_draft:
        raise _not_a_draft()
    draft = await _draft_row(db, project_id, lock=lock)
    if draft is None:
        raise _not_a_draft()
    return project, draft


async def _project_response(db: AsyncSession, current_user, project_id: str) -> ProjectResponse:
    from routers.projects.crud import _apply_caller_fields, _creator_label

    project = (
        await db.execute(
            select(Project)
            .options(
                joinedload(Project.creator),
                selectinload(Project.organizations),
                selectinload(Project.project_organizations).joinedload(
                    ProjectOrganization.organization
                ),
            )
            .where(Project.id == project_id)
        )
    ).scalars().unique().one()
    response = ProjectResponse.from_orm(project)
    response.created_by_name = await _creator_label(db, project, current_user)
    tier = await get_project_access_tier_async(db, current_user, project_id, project=project)
    await _apply_caller_fields(db, current_user, project, response, tier)
    return response


def _row_index(meta) -> Optional[int]:
    """The wizard row a draft task was imported from (``meta.
    wizard_row_index``), or None for a task the wizard did not import."""
    value = meta.get("wizard_row_index") if isinstance(meta, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _row_order(row):
    """Sort key of the task list: wizard position first (the nested import
    numbers ``inner_id`` per import run, so a later run restarts at 1), then
    the tasks without one by ``inner_id``."""
    tid, inner_id, meta, created = row
    index = _row_index(meta)
    return (
        index is None,
        index if index is not None else 0,
        inner_id if inner_id is not None else 0,
        created or datetime.min.replace(tzinfo=timezone.utc),
        str(tid),
    )


async def _existing_for_key(db: AsyncSession, current_user, client_key: str):
    """The payload of the caller's draft with ``client_key``, or None; 409
    when that draft was discarded or finished."""
    existing = (
        await db.execute(
            select(Project, ProjectWizardDraft)
            .join(ProjectWizardDraft, ProjectWizardDraft.project_id == Project.id)
            .where(
                ProjectWizardDraft.created_by == str(current_user.id),
                ProjectWizardDraft.client_key == client_key,
            )
        )
    ).first()
    if existing is None:
        return None
    project, draft = existing
    if project.deleted_at is not None:
        raise _error(409, "draft_discarded", "This draft was discarded")
    if not project.is_wizard_draft:
        raise _error(409, "draft_finished", "This draft was finished", project_id=project.id)
    return _payload(project, draft)


def _touch(draft: ProjectWizardDraft) -> None:
    draft.touched_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Create and list
# ---------------------------------------------------------------------------


@router.post("/wizard-drafts")
async def create_wizard_draft(
    body: WizardDraftCreate,
    request: Request,
    response: Response,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create the wizard draft of a new project (201), or return the
    caller's draft with the same ``client_key`` (200), so a double "Next"
    creates one draft. The target is validated like ``POST /projects`` and
    kept on the draft; the project itself is private, without organization
    rows and without the organization's creation notification. 409
    ``draft_discarded`` when the key belongs to a discarded draft."""
    existing = await _existing_for_key(db, current_user, body.client_key)
    if existing is not None:
        response.status_code = 200
        return existing

    await _validate_target(
        db,
        current_user,
        body.target_organization_id,
        body.target_group_id,
        request=request,
    )
    if body.label_config is not None:
        is_valid, errors = LabelConfigValidator.validate(body.label_config)
        if not is_valid:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid label configuration", "errors": errors},
            )
    _check_state_size(body.state)

    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        title=body.title,
        description=body.description,
        created_by=current_user.id,
        label_config=body.label_config,
        is_private=True,
        is_public=False,
        public_role=None,
        kind=body.kind,
        icon=body.icon,
        is_wizard_draft=True,
    )
    db.add(project)
    await db.flush()
    draft = ProjectWizardDraft(
        project_id=project_id,
        created_by=str(current_user.id),
        client_key=body.client_key,
        target_organization_id=body.target_organization_id or None,
        target_group_id=body.target_group_id or None,
        state=body.state,
        state_version=1,
        step_id=body.step_id,
    )
    db.add(draft)
    try:
        await db.commit()
    except IntegrityError:
        # A second request with the same key committed first.
        await db.rollback()
        existing = await _existing_for_key(db, current_user, body.client_key)
        if existing is None:
            raise
        response.status_code = 200
        return existing

    # Like POST /projects: the report draft for progressive building (the
    # purge removes it with the project if the draft is discarded).
    from routers.projects.crud import _create_initial_report_draft_sync

    try:
        await run_in_threadpool(
            _create_initial_report_draft_sync, project_id, current_user.id
        )
    except Exception as e:
        logger.error(f"Failed to create initial report draft: {e}")

    await db.refresh(project)
    await db.refresh(draft)
    response.status_code = 201
    return _payload(project, draft)


@router.get("/wizard-drafts")
async def list_wizard_drafts(
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The caller's unfinished drafts, most recently changed first (also for
    superadmins: only their own)."""
    rows = (
        await db.execute(
            select(Project, ProjectWizardDraft)
            .join(ProjectWizardDraft, ProjectWizardDraft.project_id == Project.id)
            .where(
                Project.created_by == str(current_user.id),
                Project.is_wizard_draft.is_(True),
                Project.deleted_at.is_(None),
                ProjectWizardDraft.finished_at.is_(None),
            )
            .order_by(ProjectWizardDraft.touched_at.desc(), Project.id)
        )
    ).all()
    return {"items": [_summary(project, draft) for project, draft in rows]}


# ---------------------------------------------------------------------------
# One draft
# ---------------------------------------------------------------------------


@router.get("/{project_id}/wizard-draft")
async def get_wizard_draft(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    project, draft = await _load_draft(db, project_id, current_user)
    return _payload(project, draft)


@router.put("/{project_id}/wizard-draft")
async def save_wizard_draft(
    project_id: str,
    body: WizardDraftSave,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Save the wizard state and step. ``if_version`` must be the version the
    client last read or saved (409 ``draft_version_conflict`` with
    ``current_version`` otherwise, e.g. a second tab saved in between). A body
    with ``target_organization_id`` / ``target_group_id`` moves the target
    (validated like the create). Bumps ``touched_at``, which restarts the
    retention."""
    project, draft = await _load_draft(db, project_id, current_user, lock=True)
    if draft.finished_at is not None:
        raise _not_a_draft()
    if draft.state_version != body.if_version:
        raise _error(
            409,
            "draft_version_conflict",
            "The draft was changed elsewhere",
            current_version=draft.state_version,
        )
    _check_state_size(body.state)
    fields = body.model_fields_set
    if "target_organization_id" in fields or "target_group_id" in fields:
        org_id = (
            body.target_organization_id
            if "target_organization_id" in fields
            else draft.target_organization_id
        ) or None
        group_id = (
            body.target_group_id if "target_group_id" in fields else draft.target_group_id
        ) or None
        if not org_id:
            group_id = None
        if (org_id, group_id) != (draft.target_organization_id, draft.target_group_id):
            await _validate_target(db, current_user, org_id, group_id, request=request)
            draft.target_organization_id = org_id
            draft.target_group_id = group_id
    if "state" in fields:
        draft.state = body.state
        flag_modified(draft, "state")
    if "step_id" in fields:
        draft.step_id = body.step_id
    draft.state_version += 1
    _touch(draft)
    await db.commit()
    await db.refresh(draft)
    return _payload(project, draft)


@router.post("/{project_id}/wizard-draft/finish")
async def finish_wizard_draft(
    project_id: str,
    body: WizardDraftFinish,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Finish the draft: apply the visibility and the organization rows,
    clear the flag and mark the draft row finished, in one transaction; then
    notify the first organization as ``POST /projects`` does.

    The creator's right to create in each organization and group is checked
    again with the create rules (memberships change while a draft waits). A
    repeated finish with the same ``client_key`` returns the project; any
    other finish of a non-draft answers 409 ``not_wizard_draft``; a draft the
    sweep removed answers 404 ``draft_expired``.
    """
    project = await _load_project(db, project_id, current_user, lock=True)
    draft = await _draft_row(db, project_id, lock=True)
    if not project.is_wizard_draft:
        if draft is not None and draft.finished_at is not None and draft.client_key == body.client_key:
            await db.rollback()
            return await _project_response(db, current_user, project_id)
        raise _not_a_draft()
    if draft is None or draft.client_key != body.client_key:
        raise _error(409, "draft_key_mismatch", "This finish belongs to another wizard session")

    attachments: List[WizardDraftAttachment] = []
    if body.visibility == "organization":
        attachments = body.organization_attachments
        if not attachments:
            raise HTTPException(
                status_code=400,
                detail="At least one organization is required for an organization project",
            )
        seen = set()
        for att in attachments:
            if att.organization_id in seen:
                raise HTTPException(
                    status_code=400,
                    detail=f"Organization {att.organization_id} listed more than once",
                )
            seen.add(att.organization_id)
    require_org_key_own_organization(
        request, attachments[0].organization_id if attachments else None
    )

    # Re-validate with the creator's rights (a superadmin may finish a
    # draft for its creator, but never widen it past what they may create).
    creator = (
        await db.execute(select(User).where(User.id == project.created_by))
    ).scalar_one()
    for att in attachments:
        await _validate_target(db, creator, att.organization_id, att.group_id)

    if body.visibility == "public":
        project.is_private = False
        project.is_public = True
        project.public_role = body.public_role or "ANNOTATOR"
    elif body.visibility == "organization":
        project.is_private = False
        project.is_public = False
        project.public_role = None
        for att in attachments:
            db.add(
                ProjectOrganization(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    organization_id=att.organization_id,
                    group_id=att.group_id or None,
                    assigned_by=str(current_user.id),
                )
            )
    else:
        project.is_private = True
        project.is_public = False
        project.public_role = None
    project.is_wizard_draft = False
    draft.finished_at = datetime.now(timezone.utc)
    draft.state = None
    flag_modified(draft, "state")
    await db.commit()

    if attachments:
        from routers.projects.crud import _notify_project_created_sync

        try:
            await run_in_threadpool(
                _notify_project_created_sync,
                project_id=str(project_id),
                project_title=str(project.title),
                creator_name=str(creator.name),
                organization_id=str(attachments[0].organization_id),
                creator_id=str(creator.id),
            )
        except Exception as e:
            logger.error(f"Failed to send project creation notification: {e}")

    return await _project_response(db, current_user, project_id)


async def discard_wizard_draft(db: AsyncSession, current_user, project: Project) -> Dict[str, Any]:
    """Stamp ``deleted_at`` on the draft ``project`` and queue its batched
    purge (``requested_by`` = the draft's creator). No deletion notification
    is sent: nobody else ever saw the draft. When the queue is unavailable the
    draft stays deleted and the daily sweep queues the purge again."""
    from routers.projects.crud import enqueue_purge_job, serialize_purge_job

    if project.deleted_at is None:
        project.deleted_at = datetime.now(timezone.utc)
        project.deleted_by = str(current_user.id)
        await db.commit()
    creator = await db.get(User, project.created_by)
    try:
        job = await enqueue_purge_job(db, creator, project)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        return {"message": "Draft discarded", "purge_job": None}
    return {"message": "Draft discarded", "purge_job": serialize_purge_job(job)}


@router.delete("/{project_id}/wizard-draft")
async def delete_wizard_draft(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Discard the draft: soft delete, then the batched purge. Repeating it
    on a discarded draft queues the purge again (nothing else happens)."""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not current_user.is_superadmin and str(project.created_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Only the creator can use this draft")
    if not project.is_wizard_draft:
        raise _not_a_draft()
    return await discard_wizard_draft(db, current_user, project)


# ---------------------------------------------------------------------------
# Task sync
# ---------------------------------------------------------------------------


@router.get("/{project_id}/wizard-draft/tasks")
async def list_wizard_draft_tasks(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The draft's tasks in wizard row order with the row hash and position
    the wizard stored (``meta.wizard_row_hash`` / ``meta.wizard_row_index``;
    tasks without a position follow, by ``inner_id``), their grading sheets
    that are not archived (status and check state) and the number of rubric
    generations still running for them: what the wizard matches its rows
    against and what a change would set aside."""
    await _load_draft(db, project_id, current_user)
    rows = (
        await db.execute(
            select(Task.id, Task.inner_id, Task.meta, Task.created_at).where(
                Task.project_id == project_id
            )
        )
    ).all()
    tasks = sorted(rows, key=_row_order)
    sheets: Dict[str, List[Dict[str, Any]]] = {}
    for rid, tid, rstatus, review_state in (
        await db.execute(
            select(TaskRubric.id, TaskRubric.task_id, TaskRubric.status, TaskRubric.review_state)
            .where(TaskRubric.project_id == project_id, TaskRubric.status != "archived")
            .order_by(TaskRubric.created_at)
        )
    ).all():
        sheets.setdefault(str(tid), []).append(
            {"id": rid, "status": rstatus, "review_state": review_state}
        )
    generating = {
        str(tid): int(n)
        for tid, n in (
            await db.execute(
                select(RubricGenerationJob.task_id, func.count(RubricGenerationJob.id))
                .where(
                    RubricGenerationJob.project_id == project_id,
                    RubricGenerationJob.status.in_(_RUNNING_GENERATION_STATUSES),
                    RubricGenerationJob.task_id.is_not(None),
                )
                .group_by(RubricGenerationJob.task_id)
            )
        ).all()
    }
    return {
        "items": [
            {
                "id": tid,
                "inner_id": inner_id,
                "row_index": _row_index(meta),
                "row_hash": meta.get("wizard_row_hash") if isinstance(meta, dict) else None,
                "sheets": sheets.get(str(tid), []),
                "generating": generating.get(str(tid), 0),
            }
            for tid, inner_id, meta, _created in tasks
        ]
    }


@router.put("/{project_id}/wizard-draft/tasks/{task_id}")
async def replace_wizard_draft_task(
    project_id: str,
    task_id: str,
    body: WizardDraftTaskUpdate,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Replace the data of one draft task with the changed wizard row (the
    task keeps its id and position) and store the row's hash. Its grading
    sheets that are not archived are archived in the same transaction, since
    they were made for the old content; their check log stays."""
    project, draft = await _load_draft(db, project_id, current_user, lock=True)
    if not body.data:
        raise HTTPException(status_code=400, detail="No data provided for update")
    task = (
        await db.execute(
            select(Task).where(Task.id == task_id, Task.project_id == project_id)
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found in this project")
    rubrics = (
        await db.execute(
            select(TaskRubric).where(
                TaskRubric.task_id == task_id, TaskRubric.status != "archived"
            )
        )
    ).scalars().all()
    archived = []
    for rubric in rubrics:
        await archive_task_rubric(db, rubric, task)
        archived.append(rubric.id)
    task.data = dict(body.data)
    meta = dict(task.meta) if isinstance(task.meta, dict) else {}
    meta["wizard_row_hash"] = body.row_hash
    task.meta = meta
    task.updated_by = str(current_user.id)
    flag_modified(task, "data")
    flag_modified(task, "meta")
    _touch(draft)
    await db.commit()
    return {
        "id": task.id,
        "inner_id": task.inner_id,
        "row_hash": body.row_hash,
        "archived_sheet_ids": archived,
    }
