"""Annotation management endpoints."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_async_db, get_db
from project_models import Annotation, Project, Task
from project_schemas import AnnotationCreate, AnnotationResponse
from utils.assignment_helpers import (
    mark_assignment_completed as _mark_assignment_completed,
)
from routers.projects.helpers import (
    check_task_assigned_to_user,
    check_task_assigned_to_user_async,
    enforce_project_read_window_async,
    enforce_project_write_window,
    enforce_project_write_window_async,
    enforce_seb,
    enforce_seb_async,
    get_effective_project_role_async,
    get_project_access_tier,
    get_project_access_tier_async,
    require_write_tier,
    TIER_ATTEMPTED,
    user_attempted_task_async,
)

router = APIRouter()


@router.post("/tasks/{task_id}/annotations", response_model=AnnotationResponse)
def create_annotation(
    task_id: str,  # Accept string task IDs
    annotation: AnnotationCreate,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create annotation for a task"""

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Participants (consented share member, entitled/enrolled student,
    # university-org member on an org-shared exam) hold the narrow tier and
    # may ATTEMPT the task even when check_project_accessible refuses. Keeps
    # the submit gate consistent with the read gates (task listing / next).
    # The attempted tier (read access through an own submission) never
    # submits again — coded 403.
    tier = get_project_access_tier(db, current_user, task.project_id)
    require_write_tier(tier)

    # Enforce task assignment in manual/auto mode (Label Studio aligned: task is invisible)
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if project and not check_task_assigned_to_user(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")

    # Timed access window: the access group may only submit while the window is
    # open; editors (owner / admin / contributor) are exempt. No-op when the
    # project has no window. Guards manual submits AND client-present auto-submits
    # (both land here); the server-side timer worker is gated separately.
    if project is not None:
        enforce_project_write_window(db, current_user, project)
        # Safe Exam Browser: client submits (manual and client auto-submit)
        # must come from SEB; the server-side timer worker never lands here.
        enforce_seb(db, current_user, project, request, tier=tier)

    # Overlay integrity checks (the strict exam timer) run last, right before
    # the write. The server-side timer auto-submit never lands here.
    _run_before_annotation_write(
        db, task_id=task_id, user_id=current_user.id, project_id=task.project_id
    )

    return persist_annotation_submission(
        db, task=task, project=project, user_id=current_user.id, annotation=annotation
    )


def _run_before_annotation_write(
    db: Session,
    *,
    task_id: str,
    user_id: str,
    project_id: str,
    annotation_id: Optional[str] = None,
    is_update: bool = False,
) -> None:
    """Run the ``before_annotation_write`` hook for a client write.

    Sync on purpose: the update handler bridges it through
    ``AsyncSession.run_sync``. A refusal (``AnnotationWriteRejected``)
    becomes the HTTP error it names; any other exception propagates and
    fails the request, so nothing is written either way.
    """
    from extension_activation import use_context
    from extensions import AnnotationWriteRejected, before_annotation_write

    try:
        with use_context(project_id=project_id):
            before_annotation_write(
                db,
                task_id,
                user_id,
                project_id,
                annotation_id=annotation_id,
                is_update=is_update,
            )
    except AnnotationWriteRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def persist_annotation_submission(
    db: Session,
    *,
    task: Task,
    project: Optional[Project],
    user_id: str,
    annotation: AnnotationCreate,
) -> Annotation:
    """Store ``annotation`` as ``user_id``'s submission for ``task``.

    The persistence half of :func:`create_annotation`, shared with callers
    that submit on someone's behalf (the extended solution upload): the
    one-active-annotation guard, the maximum-annotations limit, the task
    counters, draft cleanup, the ``on_annotation_created`` hook (timer
    completion, immediate evaluation), assignment completion and the report
    refresh. Access, window and SEB checks are the caller's job; this
    function assumes the submission is allowed. Returns the stored row, a
    fresh one or the existing active one updated in place.
    """
    task_id = task.id
    # Derive ai_assisted from instruction variant's ai_allowed flag (Issue #1272)
    ai_assisted = False
    if annotation.instruction_variant and project.conditional_instructions:
        for variant in project.conditional_instructions:
            if variant.get("id") == annotation.instruction_variant:
                ai_assisted = variant.get("ai_allowed", False)
                break

    # The persistence core (one active annotation per task+user under an
    # advisory lock, update-in-place, maximum-annotations limit, counters,
    # draft cleanup, IntegrityError race fallback) is shared with the
    # server-side writers: shared/annotation_submission.py.
    from annotation_submission import MaximumAnnotationsReached, persist_submission

    try:
        db_annotation = persist_submission(
            db,
            task=task,
            project=project,
            user_id=user_id,
            fields={
                "result": annotation.result,
                "draft": annotation.draft,
                "lead_time": annotation.lead_time,
                "active_duration_ms": annotation.active_duration_ms,
                "focused_duration_ms": annotation.focused_duration_ms,
                "tab_switches": annotation.tab_switches,
                "instruction_variant": annotation.instruction_variant,
                "ai_assisted": ai_assisted,
                "auto_submitted": annotation.auto_submitted,
            },
            was_cancelled=bool(annotation.was_cancelled),
        )
    except MaximumAnnotationsReached as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Notify extended features (e.g. timer session completion). The
    # project's organizations decide which packages are active for it.
    from extension_activation import use_context
    from extensions import on_annotation_created

    with use_context(project_id=task.project_id):
        on_annotation_created(db, task_id, user_id, db_annotation.id, task.project_id)

    # Mark task assignment as completed in manual/auto mode. Delegates to the
    # shared helper so the same status-flip semantics apply across annotation
    # and korrektur surfaces.
    if (
        project
        and project.assignment_mode in ["manual", "auto"]
        and not db_annotation.was_cancelled
        and db_annotation.result
    ):
        # Module-level import done once at startup — issue #30 PR 1 noted that
        # function-local imports of `utils.*` fail at request time because the
        # uvicorn worker's cwd doesn't keep /app on sys.path.
        _mark_assignment_completed(
            db, task_id=task_id, user_id=user_id,
        )

    # Report annotation section refresh (Issue #770) — dispatch to Celery so
    # the request thread doesn't pay for a COUNT + GROUP BY across every
    # annotation in the project on every save. The worker reads from the
    # same `annotations` table, so eventual consistency is exactly what the
    # report view expects.
    try:
        import logging

        from celery_client import get_celery_app

        logger = logging.getLogger(__name__)
        get_celery_app().send_task(
            "tasks.update_report_annotations_async",
            args=[task.project_id],
        )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to enqueue report annotations update: {e}")
        # Don't fail the annotation creation

    return db_annotation


@router.get("/tasks/{task_id}/annotations", response_model=List[AnnotationResponse])
async def list_task_annotations(
    task_id: str,  # Accept string task IDs
    all_users: bool = False,
    completed_by_username: Optional[str] = Query(None, description="Filter by annotator username"),
    latest_only: bool = Query(False, description="Return only the latest annotation per annotator"),
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List annotations for a task.

    By default returns only the current user's annotations (data isolation).
    Pass all_users=true to get all annotations (for read-only result views).
    Pass completed_by_username to filter to a specific annotator.
    Pass latest_only=true to deduplicate to the most recent annotation per annotator.

    Returns submitted annotations (those with non-empty result).
    Drafts are local-only (stored in browser localStorage), not on server.
    """

    task = (
        await db.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    tier = await get_project_access_tier_async(db, current_user, task.project_id)
    if tier is None:
        raise HTTPException(status_code=403, detail="Access denied")

    # Enforce task assignment in manual/auto mode (Label Studio aligned: task is invisible)
    project = (
        await db.execute(select(Project).where(Project.id == task.project_id))
    ).scalar_one_or_none()
    if project and not await check_task_assigned_to_user_async(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")
    # Attempted tier: only the tasks the caller submitted exist for them, and
    # they only ever see their own rows.
    if tier == TIER_ATTEMPTED:
        if not await user_attempted_task_async(db, current_user.id, task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        all_users = False
        completed_by_username = None

    # Other users' annotations are editor material: annotators and
    # participants always get their own rows only, whatever the query says.
    if project is not None and (all_users or completed_by_username):
        role = await get_effective_project_role_async(db, current_user, project)
        if role not in ("ORG_ADMIN", "CONTRIBUTOR"):
            all_users = False
            completed_by_username = None

    # Timed access window: hide data from the access group before the window
    # opens (editors exempt, attempted exempt). No-op without a window.
    if project is not None:
        await enforce_project_read_window_async(db, current_user, project, tier=tier)

    stmt = (
        select(Annotation)
        .where(
            Annotation.task_id == task_id,
            Annotation.result != None,  # noqa: E711
            cast(Annotation.result, String) != "[]",
        )
    )

    if completed_by_username:
        # The eval-results table builds annotator column ids as
        # `annotator:<display>` where display is pseudonym (if use_pseudonym)
        # → name → username (see results.py:get_results_by_task_model). The
        # detail modal then passes that display string back here as
        # `completed_by_username`. Resolve via the same precedence so users
        # whose display name comes from `name` or `pseudonym` (e.g. the
        # imported "Imported User <hash>" cohort) still match.
        # Each field only matches when it IS the user's display label, and
        # only users who annotated this task are candidates: a real name or
        # login never resolves a user shown by pseudonym (D8), so the filter
        # cannot serve as a lookup of who is behind a pseudonym.
        from sqlalchemy import and_, exists, or_
        from models import User as DBUser

        # ``pseudonym if (use_pseudonym and pseudonym) else (name or username)``
        shows_alias = and_(
            DBUser.use_pseudonym.is_(True),
            DBUser.pseudonym.isnot(None),
            DBUser.pseudonym != "",
        )
        has_name = and_(DBUser.name.isnot(None), DBUser.name != "")
        target_user = (
            await db.execute(
                select(DBUser).where(
                    exists().where(
                        Annotation.task_id == task_id,
                        Annotation.completed_by == DBUser.id,
                    ),
                    or_(
                        and_(shows_alias, DBUser.pseudonym == completed_by_username),
                        and_(
                            ~shows_alias,
                            has_name,
                            DBUser.name == completed_by_username,
                        ),
                        and_(
                            ~shows_alias,
                            ~has_name,
                            DBUser.username == completed_by_username,
                        ),
                    ),
                )
            )
            # .first(): DBUser.name is non-unique, so a display-name collision
            # would make scalar_one_or_none raise MultipleResultsFound (500).
        ).scalars().first()
        if not target_user:
            return []
        stmt = stmt.where(Annotation.completed_by == target_user.id)
    elif not all_users:
        stmt = stmt.where(Annotation.completed_by == current_user.id)

    stmt = stmt.order_by(Annotation.created_at.desc())
    annotations = (await db.execute(stmt)).scalars().all()

    if latest_only:
        seen = set()
        deduplicated = []
        for ann in annotations:
            if ann.completed_by not in seen:
                seen.add(ann.completed_by)
                deduplicated.append(ann)
        annotations = deduplicated

    return annotations


@router.patch("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: str,
    annotation_update: AnnotationCreate,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Update an existing annotation"""

    # Find the annotation
    db_annotation = (
        await db.execute(select(Annotation).where(Annotation.id == annotation_id))
    ).scalar_one_or_none()
    if not db_annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # None -> "Access denied"; attempted -> coded read-only 403 (an edit is a write).
    tier = await get_project_access_tier_async(
        db, current_user, db_annotation.project_id
    )
    require_write_tier(tier)

    # Enforce task assignment in manual/auto mode
    project = (
        await db.execute(select(Project).where(Project.id == db_annotation.project_id))
    ).scalar_one_or_none()
    if project and not await check_task_assigned_to_user_async(
        db, current_user, db_annotation.task_id, project
    ):
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Timed access window: the access group can't edit an annotation once the
    # window has closed (immutable after) or before it opens; editors exempt.
    if project is not None:
        await enforce_project_write_window_async(db, current_user, project)
        await enforce_seb_async(db, current_user, project, request, tier=tier)

    # Check if user owns this annotation or has admin rights
    if db_annotation.completed_by != current_user.id and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Can only update your own annotations")

    # Overlay integrity checks (the strict exam timer) before any write. The
    # hook is sync and takes a sync session, hence run_sync on this session's
    # connection (same transaction, same pattern as the eval-config hook).
    hook_task_id = db_annotation.task_id
    hook_user_id = current_user.id
    hook_project_id = db_annotation.project_id
    await db.run_sync(
        lambda session: _run_before_annotation_write(
            session,
            task_id=hook_task_id,
            user_id=hook_user_id,
            project_id=hook_project_id,
            annotation_id=annotation_id,
            is_update=True,
        )
    )

    # Track if was_cancelled status changed for counter updates
    was_cancelled_changed = False
    old_was_cancelled = db_annotation.was_cancelled

    # Update the annotation
    if annotation_update.result != None:  # noqa: E711
        db_annotation.result = annotation_update.result
    if annotation_update.was_cancelled != None:  # noqa: E711
        if db_annotation.was_cancelled != annotation_update.was_cancelled:
            was_cancelled_changed = True
        db_annotation.was_cancelled = annotation_update.was_cancelled
    if annotation_update.lead_time != None:  # noqa: E711
        db_annotation.lead_time = annotation_update.lead_time

    # Update task counters if cancelled status changed
    if was_cancelled_changed:
        task = (
            await db.execute(select(Task).where(Task.id == db_annotation.task_id))
        ).scalar_one_or_none()
        if task:
            if annotation_update.was_cancelled and not old_was_cancelled:
                # Changed from not cancelled to cancelled
                task.cancelled_annotations += 1
            elif not annotation_update.was_cancelled and old_was_cancelled:
                # Changed from cancelled to not cancelled
                task.cancelled_annotations -= 1

    # Update timestamp
    db_annotation.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(db_annotation)

    # Report annotation section refresh — same Celery dispatch as the create
    # path. Update routes through the same hot edit loop, so we keep the
    # aggregation off the request thread here too.
    try:
        import logging

        from celery_client import get_celery_app

        logger = logging.getLogger(__name__)
        get_celery_app().send_task(
            "tasks.update_report_annotations_async",
            args=[db_annotation.project_id],
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update report annotations section: {e}")

    return db_annotation
