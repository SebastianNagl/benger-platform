"""Project questionnaires: settings, answers, export.

One questionnaire per project and moment (``before_task``, ``after_submit``,
``korrektur``; see ``shared/questionnaires.py``), all answers in one store.
Editors configure them (``PUT /questionnaires/{trigger}``, validated on save)
and read the answers (``/questionnaire-responses``, a wide CSV at
``/questionnaire-responses/export.csv``). Participants and graders ask
whether one is due (``/questionnaires/{trigger}/status``) and answer it
(``POST /questionnaires/{trigger}/responses``).

The post-annotation questionnaire routes of issue #1208 stay for one release
and now read and write the after_submit questionnaire:
``POST /tasks/{task_id}/questionnaire-response`` and the default view of
``GET /questionnaire-responses`` (after_submit answers, same fields).
"""

import csv
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_async_db
from project_models import ProjectQuestionnaireVersion, QuestionnaireResponse
from project_schemas import (
    PostAnnotationResponseCreate,
    PostAnnotationResponseOut,
    QuestionnaireAnswerCreate,
    QuestionnaireConfigValidate,
    QuestionnaireUpdate,
)
from questionnaires import (
    AFTER_SUBMIT,
    KORREKTUR,
    QUESTIONNAIRE_TRIGGERS,
    WIDE_CSV_BASE_COLUMNS,
    question_columns,
    wide_row,
)
from routers.projects.deps import ProjectAccess, require_project_access
from routers.projects.helpers import (
    check_task_assigned_to_user_async,
    check_user_can_edit_project_async,
    enforce_seb_async,
    require_write_tier,
)
from services import questionnaire_service as qs

router = APIRouter()

_EDIT = dict(
    min_role="edit",
    access_denied_detail="You don't have access to this project",
    edit_denied_detail="Not authorized to change or read this project's questionnaires",
)
_SOLVER = dict(
    access_denied_detail="You don't have access to this project",
    allow_participant=True,
)


def _raise(exc: qs.QuestionnaireError):
    raise HTTPException(status_code=exc.status, detail=exc.detail) from None


# --------------------------------------------------------------------------- #
# Settings (editors) and what a solver needs to render one
# --------------------------------------------------------------------------- #


@router.get("/{project_id}/questionnaires")
async def list_project_questionnaires(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(**_SOLVER)),
):
    """The project's three questionnaires. Editors get every moment with its
    settings; everyone else only the switched-on ones of the moments they
    answer (participants never see the graders' Korrektur questionnaire)."""
    rows = await qs.list_questionnaires(db, project_id)
    await db.commit()  # keeps an after_submit row made from the #1208 columns
    can_edit = access.tier == "full" and await check_user_can_edit_project_async(
        db, current_user, project_id
    )
    items = []
    for trigger in QUESTIONNAIRE_TRIGGERS:
        item = qs.serialize_questionnaire(trigger, rows.get(trigger))
        if not can_edit:
            if not item["active"]:
                continue
            if trigger == KORREKTUR and access.tier != "full":
                continue
        items.append(item)
    return {"questionnaires": items, "can_edit": bool(can_edit)}


@router.post("/{project_id}/questionnaires/validate")
async def validate_project_questionnaire(
    project_id: str,
    payload: QuestionnaireConfigValidate,
    access: ProjectAccess = Depends(require_project_access(**_EDIT)),
):
    """Check a questionnaire XML with the rules a save applies."""
    errors = qs.validate_config(payload.config)
    return {"valid": not errors, "errors": errors}


@router.put("/{project_id}/questionnaires/{trigger}")
async def update_project_questionnaire(
    project_id: str,
    trigger: str,
    payload: QuestionnaireUpdate,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(**_EDIT)),
):
    """Save one moment's questionnaire (validated; a changed XML is a new
    version)."""
    try:
        row = await qs.save_questionnaire(
            db,
            access.project,
            trigger,
            enabled=payload.enabled,
            config=payload.config,
            required=payload.required,
            frequency=payload.frequency,
            user_id=current_user.id,
        )
    except qs.QuestionnaireError as exc:
        await db.rollback()
        _raise(exc)
    await db.commit()
    await db.refresh(row)
    return qs.serialize_questionnaire(trigger, row)


@router.get("/{project_id}/questionnaires/{trigger}/versions")
async def list_questionnaire_versions(
    project_id: str,
    trigger: str,
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(**_EDIT)),
):
    """Every saved text of one moment's questionnaire, newest first."""
    try:
        qs.check_trigger(trigger)
    except qs.QuestionnaireError as exc:
        _raise(exc)
    row = await qs.get_questionnaire(db, project_id, trigger)
    if row is None:
        return {"versions": []}
    versions = (
        await db.execute(
            select(ProjectQuestionnaireVersion)
            .where(ProjectQuestionnaireVersion.questionnaire_id == row.id)
            .order_by(ProjectQuestionnaireVersion.version.desc())
        )
    ).scalars().all()
    return {
        "versions": [
            {
                "version": v.version,
                "config": v.config,
                "config_hash": v.config_hash,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "created_by": v.created_by,
            }
            for v in versions
        ]
    }


# --------------------------------------------------------------------------- #
# Answering (participants for before_task / after_submit, graders for korrektur)
# --------------------------------------------------------------------------- #


async def _solver_subject(
    db: AsyncSession,
    access: ProjectAccess,
    user: AuthUser,
    request: Request,
    trigger: str,
    *,
    task_id: Optional[str],
    annotation_id: Optional[str],
    task_evaluation_id: Optional[str],
    writing: bool,
) -> qs.Subject:
    project = access.project
    if trigger != KORREKTUR:
        if writing:
            # The attempted (read-only) tier passes the dependency but may not write.
            require_write_tier(access.tier)
        await enforce_seb_async(db, user, project, request, tier=access.tier)
    elif access.tier != "full":
        raise HTTPException(status_code=403, detail="Only graders answer this questionnaire")

    async def task_visible(tid: str) -> bool:
        return await check_task_assigned_to_user_async(db, user, tid, project)

    return await qs.resolve_subject(
        db,
        project,
        trigger,
        user.id,
        task_id=task_id,
        annotation_id=annotation_id,
        task_evaluation_id=task_evaluation_id,
        task_visible=task_visible if trigger != KORREKTUR else None,
    )


@router.get("/{project_id}/questionnaires/{trigger}/status")
async def questionnaire_status(
    project_id: str,
    trigger: str,
    request: Request,
    task_id: Optional[str] = Query(None),
    annotation_id: Optional[str] = Query(None),
    task_evaluation_id: Optional[str] = Query(None),
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(**_SOLVER)),
):
    """Whether the caller still has to answer this moment's questionnaire,
    and the questionnaire to render when so. Read-only access (the
    attempted tier) never owes one."""
    try:
        qs.check_trigger(trigger)
        row = await qs.get_questionnaire(db, project_id, trigger)
        await db.commit()  # keeps an after_submit row made from the #1208 columns
        if row is None or not qs.is_active(row) or access.tier == "attempted":
            return {"due": False, "questionnaire": None}
        subject = await _solver_subject(
            db,
            access,
            current_user,
            request,
            trigger,
            task_id=task_id,
            annotation_id=annotation_id,
            task_evaluation_id=task_evaluation_id,
            writing=False,
        )
    except qs.QuestionnaireError as exc:
        _raise(exc)
    due = await qs.is_due(db, row, current_user.id, subject)
    return {
        "due": due,
        "questionnaire": qs.serialize_questionnaire(trigger, row) if due else None,
    }


@router.post("/{project_id}/questionnaires/{trigger}/responses")
async def submit_questionnaire_answer(
    project_id: str,
    trigger: str,
    payload: QuestionnaireAnswerCreate,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(**_SOLVER)),
):
    """Answer (or, when it is optional, skip) this moment's questionnaire."""
    try:
        qs.check_trigger(trigger)
        row = await qs.get_questionnaire(db, project_id, trigger)
        if row is None or not qs.is_active(row):
            raise qs.QuestionnaireError(
                400,
                "questionnaire_not_enabled",
                "Questionnaire is not enabled for this project",
            )
        subject = await _solver_subject(
            db,
            access,
            current_user,
            request,
            trigger,
            task_id=payload.task_id,
            annotation_id=payload.annotation_id,
            task_evaluation_id=payload.task_evaluation_id,
            writing=True,
        )
        answer = await qs.record_answer(
            db,
            access.project,
            row,
            current_user.id,
            subject,
            result=payload.result,
            skipped=payload.skipped,
        )
    except qs.QuestionnaireError as exc:
        _raise(exc)
    return qs.serialize_response(answer)


# --------------------------------------------------------------------------- #
# Reading the answers (editors)
# --------------------------------------------------------------------------- #


def _trigger_filter(trigger: Optional[str]) -> Optional[List[str]]:
    """``None`` -> the after_submit answers (the #1208 view); ``all`` -> every
    moment; else the one moment named."""
    if trigger is None:
        return [AFTER_SUBMIT]
    if trigger == "all":
        return list(QUESTIONNAIRE_TRIGGERS)
    if trigger not in QUESTIONNAIRE_TRIGGERS:
        raise HTTPException(
            status_code=422,
            detail="trigger must be 'all' or one of " + ", ".join(QUESTIONNAIRE_TRIGGERS),
        )
    return [trigger]


@router.get("/{project_id}/questionnaire-responses")
async def list_questionnaire_responses(
    project_id: str,
    trigger: Optional[str] = Query(
        None, description="'all', or one moment; default: the after_submit answers"
    ),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(**_EDIT)),
) -> List[Dict[str, Any]]:
    """The project's questionnaire answers, newest first."""
    triggers = _trigger_filter(trigger)
    rows = (
        await db.execute(
            select(QuestionnaireResponse)
            .where(
                QuestionnaireResponse.project_id == project_id,
                QuestionnaireResponse.trigger.in_(triggers),
            )
            .order_by(QuestionnaireResponse.created_at.desc())
        )
    ).scalars().all()
    return [qs.serialize_response(row) for row in rows]


@router.get("/{project_id}/questionnaire-responses/export.csv")
async def export_questionnaire_responses_csv(
    project_id: str,
    trigger: str = Query(
        "all", description="'all' (question columns prefixed by moment) or one moment"
    ),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access(**_EDIT)),
):
    """Wide CSV: one row per answer, one column per question. With
    ``trigger=all`` the question columns read ``<moment>.<question>``."""
    triggers = _trigger_filter(trigger)
    rows = (
        await db.execute(
            select(QuestionnaireResponse)
            .where(
                QuestionnaireResponse.project_id == project_id,
                QuestionnaireResponse.trigger.in_(triggers),
            )
            .order_by(QuestionnaireResponse.trigger, QuestionnaireResponse.created_at)
        )
    ).scalars().all()
    prefixed = len(triggers) > 1

    def column(row_trigger: str, name: str) -> str:
        return f"{row_trigger}.{name}" if prefixed else name

    question_cols: Dict[str, None] = {}
    for t in triggers:
        for name in question_columns(r.result for r in rows if r.trigger == t):
            question_cols.setdefault(column(t, name), None)

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=[*WIDE_CSV_BASE_COLUMNS, *question_cols], extrasaction="ignore"
    )
    writer.writeheader()
    for r in rows:
        line: Dict[str, Any] = {
            "response_id": r.id,
            "trigger": r.trigger,
            "questionnaire_version": r.questionnaire_version,
            "config_hash": r.config_hash,
            "user_id": r.user_id,
            "task_id": r.task_id,
            "annotation_id": r.annotation_id,
            "task_evaluation_id": r.task_evaluation_id,
            "skipped": "true" if r.skipped else "false",
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for name, value in wide_row(r.result).items():
            line[column(r.trigger, name)] = value
        writer.writerow(line)

    filename = f"questionnaire-responses-{project_id}-{trigger}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Issue #1208 route, kept for one release (writes the after_submit answer)
# --------------------------------------------------------------------------- #


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
    access: ProjectAccess = Depends(require_project_access(**_SOLVER)),
):
    """Submit a post-annotation questionnaire response (the after_submit
    questionnaire). Deprecated: use ``POST /questionnaires/after_submit/responses``."""
    require_write_tier(access.tier)
    await enforce_seb_async(db, current_user, access.project, request, tier=access.tier)

    row = await qs.get_questionnaire(db, project_id, AFTER_SUBMIT)
    if row is None or not row.enabled:
        raise HTTPException(status_code=400, detail="Questionnaire is not enabled for this project")
    if not await qs._task_of_project(db, project_id, task_id) or not (
        await check_task_assigned_to_user_async(db, current_user, task_id, access.project)
    ):
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        subject = await qs.resolve_subject(
            db,
            access.project,
            AFTER_SUBMIT,
            current_user.id,
            task_id=task_id,
            annotation_id=payload.annotation_id,
            task_evaluation_id=None,
        )
        answer = await qs.record_answer(
            db,
            access.project,
            row,
            current_user.id,
            subject,
            result=payload.result,
            skipped=False,
            require_config=False,
        )
    except qs.QuestionnaireError as exc:
        if exc.detail.get("code") == "questionnaire_already_answered":
            raise HTTPException(
                status_code=400,
                detail="Questionnaire response already submitted for this annotation",
            ) from None
        if exc.status in (400, 404):
            # The #1208 route answered these with a plain message.
            raise HTTPException(status_code=exc.status, detail=exc.detail["message"]) from None
        _raise(exc)
    return answer
