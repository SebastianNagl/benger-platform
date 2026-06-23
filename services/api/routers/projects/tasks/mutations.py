"""Task data mutation endpoints: update data, bulk delete, bulk archive, skip."""
from fastapi.concurrency import run_in_threadpool

from database import SessionLocal

from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)
from routers.projects.deps import ProjectAccess, require_project_access


def _update_report_data_section_sync(project_id: str) -> None:
    """Run the sync ``update_report_data_section`` on a fresh short-lived sync
    session. The report service is sync-only (lives in /shared) and has no
    async twin, so the async handler must never hand it its ``AsyncSession``.
    Best-effort: failures are logged by the caller, not raised."""
    import logging

    from report_service import update_report_data_section

    logger = logging.getLogger(__name__)
    sync_db = SessionLocal()
    try:
        update_report_data_section(sync_db, project_id)
        logger.info(f"Updated report data section for project {project_id}")
    finally:
        sync_db.close()


@router.put("/{project_id}/tasks/{task_id}")
async def update_task_data(
    project_id: str,
    task_id: str,
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access()),
):
    """
    Update task data - superadmins and organization admins

    Request body:
    {
        "data": {
            "field_name": "new_value",
            ...
        }
    }

    Editing is allowed for superadmins, the project creator, and ORG_ADMIN
    members of the project's organization. It maintains an audit log of all
    changes.
    """
    from datetime import datetime

    # Project existence + read access enforced by require_project_access
    # (404 "Project not found" / 403 "Access denied").
    project = access.project

    # Only superadmins, the project creator, and org admins of the project's
    # organization may edit task data.
    if not await check_user_can_edit_task_data_async(db, current_user, project):
        raise HTTPException(
            status_code=403,
            detail="Only superadmins or organization admins can edit task data",
        )

    # Verify task exists and belongs to the project
    task = (
        await db.execute(
            select(Task).where(Task.id == task_id, Task.project_id == project_id)
        )
    ).scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found in this project")

    # Get the new data from request
    new_data = data.get("data", {})
    if not new_data:
        raise HTTPException(status_code=400, detail="No data provided for update")

    # Store original data for audit log
    original_data = task.data.copy() if task.data else {}

    # Update task data
    if task.data:
        # Merge new data with existing data
        task.data.update(new_data)
    else:
        # Set new data if task had no data
        task.data = new_data

    # Update the task's updated_at timestamp
    task.updated_at = datetime.utcnow()

    # Create audit log entry (using task's meta field for now)
    if not task.meta:
        task.meta = {}

    if "audit_log" not in task.meta:
        task.meta["audit_log"] = []

    audit_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": current_user.id,
        "user_email": current_user.email,
        "action": "data_update",
        "changes": {
            "before": {k: original_data.get(k) for k in new_data.keys()},
            "after": new_data,
        },
    }

    task.meta["audit_log"].append(audit_entry)

    # Flag the task.meta as modified to ensure SQLAlchemy picks up the change
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(task, "data")
    flag_modified(task, "meta")

    try:
        await db.commit()
        await db.refresh(task)

        # Calculate generation count from Generation table
        total_generations = (
            await db.execute(
                select(func.count(Generation.id)).where(Generation.task_id == task_id)
            )
        ).scalar() or 0

        # Return the updated task as a dictionary
        return {
            "id": task.id,
            "project": task.project_id,
            "data": task.data,
            "meta": task.meta,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "is_labeled": task.is_labeled,
            "total_annotations": task.total_annotations,
            "cancelled_annotations": task.cancelled_annotations,
            "total_generations": total_generations,
            "llm_responses": getattr(task, "llm_responses", None),
            "llm_evaluations": getattr(task, "llm_evaluations", None),
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update task data: {str(e)}")


@router.post("/{project_id}/tasks/bulk-delete")
async def bulk_delete_tasks(
    project_id: str,
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    _access: ProjectAccess = Depends(
        require_project_access(min_role="edit", edit_denied_detail="Permission denied")
    ),
):
    """Bulk delete tasks in a project"""
    from sqlalchemy import delete as sa_delete

    task_ids = data.get("task_ids", [])

    # Project existence + read access + edit permission are enforced by
    # require_project_access(min_role="edit"): 404 "Project not found",
    # 403 "Access denied" on read, 403 "Permission denied" on edit — the
    # same three checks (in the same order) the inline preamble ran via
    # check_project_accessible_async + check_user_can_edit_project_async.

    deleted_count = 0

    for task_id in task_ids:
        # Delete annotations first
        # NOTE: Annotation table doesn't exist yet - skipping deletion
        # db.query(Annotation).filter(Annotation.task_id == task_id).delete()
        pass

        # Delete task
        result = await db.execute(
            sa_delete(Task).where(Task.id == task_id, Task.project_id == project_id)
        )

        if result.rowcount > 0:
            deleted_count += 1

    # task_count is a response-time computed field (see calculate_project_stats),
    # not a stored Project column. The previous `project.task_count = …` write
    # here was a dead store on the SQLAlchemy instance — removed.

    await db.commit()

    # Update report data section (silent failure to not block deletion). The
    # report service is sync-only; run it on a fresh short-lived sync session
    # off the event loop so it never touches the AsyncSession.
    try:
        await run_in_threadpool(_update_report_data_section_sync, project_id)
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update report data section: {e}")

    return {"deleted": deleted_count}


@router.post("/{project_id}/tasks/bulk-archive")
async def bulk_archive_tasks(
    project_id: str,
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access()),
):
    """Bulk archive tasks in a project"""

    task_ids = data.get("task_ids", [])

    # Project existence + read access enforced by require_project_access
    # (404 "Project not found" / 403 "Access denied").
    project = access.project

    # Check permission (custom: creator or superadmin only — narrower than the
    # dependency's min_role="edit", so it stays inline).
    if project.created_by != current_user.id and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Permission denied")

    archived_count = 0

    for task_id in task_ids:
        task = (
            await db.execute(
                select(Task).where(Task.id == task_id, Task.project_id == project_id)
            )
        ).scalar_one_or_none()

        if task:
            # Mark task as archived (add is_archived field if not exists)
            task.meta = task.meta or {}
            task.meta["is_archived"] = True
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(task, "meta")
            archived_count += 1

    await db.commit()

    return {"archived": archived_count}


@router.post("/{project_id}/tasks/{task_id}/skip", response_model=SkipTaskResponse)
async def skip_task(
    project_id: str,
    task_id: str,
    skip_request: SkipTaskRequest,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Skip a task with optional comment

    If project has require_comment_on_skip=True, comment must be provided
    Creates a skip record in the database to track skipped tasks
    """

    # Verify task exists and belongs to project
    task = (
        await db.execute(
            select(Task).where(Task.id == task_id, Task.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get project to check require_comment_on_skip setting
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not await check_project_accessible_async(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Enforce task assignment in manual/auto mode (Label Studio aligned: task is invisible)
    if not await check_task_assigned_to_user_async(db, current_user, task_id, project):
        raise HTTPException(status_code=404, detail="Task not found")

    # Validate comment requirement
    if project.require_comment_on_skip and not skip_request.comment:
        raise HTTPException(
            status_code=400, detail="Comment is required when skipping tasks in this project"
        )

    # Generate skip record ID
    skip_id = str(uuid.uuid4())

    # Create skip record
    skip_record = SkippedTask(
        id=skip_id,
        task_id=task_id,
        project_id=project_id,
        skipped_by=current_user.id,
        comment=skip_request.comment,
    )

    db.add(skip_record)
    await db.commit()
    await db.refresh(skip_record)

    return skip_record
