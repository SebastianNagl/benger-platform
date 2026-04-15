"""Annotation management endpoints."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from project_models import Annotation, Project, Task, TaskAssignment
from project_schemas import AnnotationCreate, AnnotationResponse
from routers.projects.helpers import (
    check_project_accessible,
    check_task_assigned_to_user,
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

    # Create annotation
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

    # Enforce maximum annotations limit (if not a cancelled annotation)
    if not annotation.was_cancelled and annotation.result and len(annotation.result) > 0:
        # Count existing non-cancelled annotations for this task
        existing_annotations = (
            db.query(Annotation)
            .filter(
                Annotation.task_id == task_id,
                Annotation.was_cancelled == False,
                Annotation.result != None,
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

    # Update task counters for submitted annotations (those with actual results)
    if annotation.result and len(annotation.result) > 0:
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
                    Annotation.was_cancelled == False,
                    Annotation.result != None,
                    cast(Annotation.result, String) != "[]",
                )
                .count()
            ) + 1  # Add 1 for the current annotation being created

            # Label Studio approach: Task is labeled when it meets minimum annotation requirement
            if non_cancelled_annotations >= project.min_annotations_per_task:
                task.is_labeled = True

    # Task completion status is tracked on the task itself
    # No need to update project-level counter as it's calculated dynamically

    db.add(db_annotation)

    # Clear server-side draft now that annotation is submitted
    from project_models import TaskDraft

    db.query(TaskDraft).filter(
        TaskDraft.task_id == task_id,
        TaskDraft.user_id == current_user.id,
    ).delete()

    db.commit()
    db.refresh(db_annotation)

    # Mark task assignment as completed in manual/auto mode
    if (
        project
        and project.assignment_mode in ["manual", "auto"]
        and not db_annotation.was_cancelled
        and db_annotation.result
    ):
        assignment = (
            db.query(TaskAssignment)
            .filter(
                TaskAssignment.task_id == task_id,
                TaskAssignment.user_id == current_user.id,
                TaskAssignment.status.in_(["assigned", "in_progress"]),
            )
            .first()
        )
        if assignment:
            assignment.status = "completed"
            assignment.completed_at = datetime.now(timezone.utc)
            db.commit()

    # Update report annotations section after annotation creation (Issue #770)
    try:
        import logging

        from report_service import update_report_annotations_section

        logger = logging.getLogger(__name__)
        update_report_annotations_section(db, task.project_id)
        logger.info(f"✅ Updated report annotations section for project {task.project_id}")
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update report annotations section: {e}")
        # Don't fail the annotation creation

    return db_annotation


@router.get("/tasks/{task_id}/annotations", response_model=List[AnnotationResponse])
async def list_task_annotations(
    task_id: str,  # Accept string task IDs
    request: Request,
    all_users: bool = False,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List annotations for a task.

    By default returns only the current user's annotations (data isolation).
    Pass all_users=true to get all annotations (for read-only result views).

    Returns submitted annotations (those with non-empty result).
    Drafts are local-only (stored in browser localStorage), not on server.
    """

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

    query = (
        db.query(Annotation)
        .filter(
            Annotation.task_id == task_id,
            Annotation.result != None,
            cast(Annotation.result, String) != "[]",
        )
    )

    if not all_users:
        query = query.filter(Annotation.completed_by == current_user.id)

    return query.all()


@router.patch("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: str,
    annotation_update: AnnotationCreate,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Update an existing annotation"""

    # Find the annotation
    db_annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not db_annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, db_annotation.project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Enforce task assignment in manual/auto mode
    project = db.query(Project).filter(Project.id == db_annotation.project_id).first()
    if project and not check_task_assigned_to_user(db, current_user, db_annotation.task_id, project):
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Check if user owns this annotation or has admin rights
    if db_annotation.completed_by != current_user.id and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Can only update your own annotations")

    # Track if was_cancelled status changed for counter updates
    was_cancelled_changed = False
    old_was_cancelled = db_annotation.was_cancelled

    # Update the annotation
    if annotation_update.result is not None:
        db_annotation.result = annotation_update.result
    if annotation_update.was_cancelled is not None:
        if db_annotation.was_cancelled != annotation_update.was_cancelled:
            was_cancelled_changed = True
        db_annotation.was_cancelled = annotation_update.was_cancelled
    if annotation_update.lead_time is not None:
        db_annotation.lead_time = annotation_update.lead_time

    # Update task counters if cancelled status changed
    if was_cancelled_changed:
        task = db.query(Task).filter(Task.id == db_annotation.task_id).first()
        if task:
            if annotation_update.was_cancelled and not old_was_cancelled:
                # Changed from not cancelled to cancelled
                task.cancelled_annotations += 1
            elif not annotation_update.was_cancelled and old_was_cancelled:
                # Changed from cancelled to not cancelled
                task.cancelled_annotations -= 1

    # Update timestamp
    db_annotation.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(db_annotation)

    # Update report annotations section (silent failure to not block annotation update)
    try:
        import logging

        from report_service import update_report_annotations_section

        logger = logging.getLogger(__name__)
        update_report_annotations_section(db, db_annotation.project_id)
        logger.info(f"Updated report annotations section for project {db_annotation.project_id}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update report annotations section: {e}")

    return db_annotation
