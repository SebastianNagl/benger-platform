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
    check_project_accessible,
    check_project_accessible_async,
    check_task_assigned_to_user,
    check_task_assigned_to_user_async,
    get_org_context_from_request,
)

router = APIRouter()


@router.post("/tasks/{task_id}/annotations", response_model=AnnotationResponse)
async def create_annotation(
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

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, task.project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Enforce task assignment in manual/auto mode (Label Studio aligned: task is invisible)
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if project and not check_task_assigned_to_user(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")

    # ---- Duplicate-submit guard (strict-timer race + auto-then-manual) ------
    # A strict-timer task has two writers: the client auto-submit (this
    # endpoint) AND the server-side timer worker (auto_submit_expired_timer),
    # plus a manual submit can land after an auto-submit. Without coordination
    # they each INSERT a near-identical row, so one student ends up with 2-4
    # duplicate annotations on a single task (each then graded -> wasted tokens).
    # Serialize concurrent submits for the SAME (task, user) with a
    # transaction-scoped advisory lock (the worker takes the same lock), then,
    # if an active annotation already exists, UPDATE it in place so the latest
    # content wins and there is exactly one annotation per (task, user).
    # Scoped to strict-timer projects: that is the only place the duplicate
    # race exists (the server-side auto_submit_expired_timer worker runs only
    # for strict timers), so non-timer annotation behavior is unchanged.
    existing_annotation = None
    if (
        not (annotation.was_cancelled or False)
        and getattr(project, "strict_timer_enabled", False)
    ):
        from sqlalchemy import text as _sql_text

        db.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"annsubmit:{task_id}:{current_user.id}"},
        )
        existing_annotation = (
            db.query(Annotation)
            .filter(
                Annotation.task_id == task_id,
                Annotation.completed_by == current_user.id,
                Annotation.was_cancelled == False,  # noqa: E712
            )
            .order_by(Annotation.created_at.desc())
            .first()
        )

    # Generate annotation ID
    import uuid

    annotation_id = str(uuid.uuid4())

    server_lead_time = annotation.lead_time

    # Derive ai_assisted from instruction variant's ai_allowed flag (Issue #1272)
    ai_assisted = False
    if annotation.instruction_variant and project.conditional_instructions:
        for variant in project.conditional_instructions:
            if variant.get("id") == annotation.instruction_variant:
                ai_assisted = variant.get("ai_allowed", False)
                break

    # Create the annotation — or, when a duplicate submit lands, update the
    # existing one in place (latest content wins, no second row).
    if existing_annotation is not None:
        db_annotation = existing_annotation
        db_annotation.result = annotation.result
        db_annotation.draft = annotation.draft
        db_annotation.lead_time = server_lead_time
        db_annotation.active_duration_ms = annotation.active_duration_ms
        db_annotation.focused_duration_ms = annotation.focused_duration_ms
        db_annotation.tab_switches = annotation.tab_switches or 0
        db_annotation.instruction_variant = annotation.instruction_variant
        db_annotation.ai_assisted = ai_assisted
        db_annotation.auto_submitted = annotation.auto_submitted or False
    else:
        db_annotation = Annotation(
            id=annotation_id,
            task_id=task_id,  # Already a string now
            project_id=task.project_id,
            completed_by=current_user.id,
            result=annotation.result,
            draft=annotation.draft,
            was_cancelled=annotation.was_cancelled or False,
            lead_time=server_lead_time,
            # Enhanced timing (Issue #1208)
            active_duration_ms=annotation.active_duration_ms,
            focused_duration_ms=annotation.focused_duration_ms,
            tab_switches=annotation.tab_switches or 0,
            instruction_variant=annotation.instruction_variant,
            ai_assisted=ai_assisted,
        )

    # Enforce maximum annotations limit (if not a cancelled annotation).
    # Skipped on the update-in-place path — it reuses the student's existing
    # row, so it cannot push the task over its annotation limit.
    if existing_annotation is None and not annotation.was_cancelled and annotation.result and len(annotation.result) > 0:
        # Count existing non-cancelled annotations for this task
        existing_annotations = (
            db.query(Annotation)
            .filter(
                Annotation.task_id == task_id,
                Annotation.was_cancelled == False,  # noqa: E712
                Annotation.result != None,  # noqa: E711
                cast(Annotation.result, String) != "[]",
            )
            .count()
        )

        # Check if adding this annotation would exceed the maximum
        # maximum_annotations == 0 means unlimited
        if project.maximum_annotations > 0 and existing_annotations >= project.maximum_annotations:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum annotations limit reached ({project.maximum_annotations}). Cannot add more annotations to this task.",
            )

    # Update task counters for submitted annotations (those with actual
    # results). Only on a NEW row — the update-in-place path adds no annotation,
    # so the counters must not move.
    if existing_annotation is None and annotation.result and len(annotation.result) > 0:
        # total_annotations = ALL completed annotations (cancelled + not cancelled)
        task.total_annotations += 1

        if annotation.was_cancelled:
            task.cancelled_annotations += 1

        # Update task labeling status based on non-cancelled annotations
        if not annotation.was_cancelled:
            # Count non-cancelled annotations for this task (including the new one)
            non_cancelled_annotations = (
                db.query(Annotation)
                .filter(
                    Annotation.task_id == task_id,
                    Annotation.was_cancelled == False,  # noqa: E712
                    Annotation.result != None,  # noqa: E711
                    cast(Annotation.result, String) != "[]",
                )
                .count()
            ) + 1  # Add 1 for the current annotation being created

            # Label Studio approach: Task is labeled when it meets minimum annotation requirement
            if non_cancelled_annotations >= project.min_annotations_per_task:
                task.is_labeled = True

    # Task completion status is tracked on the task itself
    # No need to update project-level counter as it's calculated dynamically

    if existing_annotation is None:
        db.add(db_annotation)

    # Clear server-side draft now that annotation is submitted
    from project_models import TaskDraft

    db.query(TaskDraft).filter(
        TaskDraft.task_id == task_id,
        TaskDraft.user_id == current_user.id,
    ).delete()

    db.commit()
    db.refresh(db_annotation)

    # Notify extended features (e.g. timer session completion)
    from extensions import on_annotation_created
    on_annotation_created(db, task_id, current_user.id, db_annotation.id, task.project_id)

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
            db, task_id=task_id, user_id=current_user.id,
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
            queue="default",
        )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to enqueue report annotations update: {e}")
        # Don't fail the annotation creation

    return db_annotation


@router.get("/tasks/{task_id}/annotations", response_model=List[AnnotationResponse])
async def list_task_annotations(
    task_id: str,  # Accept string task IDs
    request: Request,
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
    org_context = get_org_context_from_request(request)
    if not await check_project_accessible_async(db, current_user, task.project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Enforce task assignment in manual/auto mode (Label Studio aligned: task is invisible)
    project = (
        await db.execute(select(Project).where(Project.id == task.project_id))
    ).scalar_one_or_none()
    if project and not await check_task_assigned_to_user_async(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")

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
        from sqlalchemy import or_, and_
        from models import User as DBUser
        target_user = (
            await db.execute(
                select(DBUser).where(
                    or_(
                        and_(
                            DBUser.use_pseudonym == True,  # noqa: E712
                            DBUser.pseudonym == completed_by_username,
                        ),
                        DBUser.name == completed_by_username,
                        DBUser.username == completed_by_username,
                    )
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

    org_context = get_org_context_from_request(request)
    if not await check_project_accessible_async(
        db, current_user, db_annotation.project_id, org_context
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    # Enforce task assignment in manual/auto mode
    project = (
        await db.execute(select(Project).where(Project.id == db_annotation.project_id))
    ).scalar_one_or_none()
    if project and not await check_task_assigned_to_user_async(
        db, current_user, db_annotation.task_id, project
    ):
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Check if user owns this annotation or has admin rights
    if db_annotation.completed_by != current_user.id and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Can only update your own annotations")

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
            queue="default",
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update report annotations section: {e}")

    return db_annotation
