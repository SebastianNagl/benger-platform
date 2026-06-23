"""Task metadata update endpoints (single + bulk)."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


@router.patch("/tasks/{task_id}/metadata")
async def update_task_metadata(
    task_id: str,
    metadata: dict,
    request: Request,
    merge: bool = Query(True, description="Merge with existing metadata or replace"),
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update task metadata (Label Studio aligned approach)

    This is the simplified way to update any metadata including tags.
    If merge=True (default), merges with existing metadata.
    If merge=False, replaces all metadata.
    """
    task = (
        await db.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    org_context = get_org_context_from_request(request)
    if not await check_project_accessible_async(
        db, current_user, task.project_id, org_context
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    # Initialize meta if it doesn't exist
    if task.meta == None:  # noqa: E711
        task.meta = {}

    if merge:
        # Merge with existing metadata
        task.meta = {**task.meta, **metadata}
    else:
        # Replace all metadata
        task.meta = metadata

    # Mark the field as modified for SQLAlchemy
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(task, "meta")

    db.add(task)
    await db.commit()
    await db.refresh(task)

    return {
        "id": task.id,
        "meta": task.meta,
        "message": "Metadata updated successfully",
    }


@router.patch("/tasks/bulk-metadata")
async def bulk_update_task_metadata(
    task_ids: List[str],
    metadata: dict,
    request: Request,
    merge: bool = Query(True, description="Merge with existing metadata or replace"),
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update metadata for multiple tasks (Label Studio aligned approach)

    This replaces the complex bulk-tag and bulk-untag endpoints.
    """
    tasks = (
        await db.execute(select(Task).where(Task.id.in_(task_ids)))
    ).scalars().all()

    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found")

    # Check access for all tasks' projects
    org_context = get_org_context_from_request(request)
    checked_projects = set()
    for task in tasks:
        if task.project_id not in checked_projects:
            if not await check_project_accessible_async(
                db, current_user, task.project_id, org_context
            ):
                raise HTTPException(status_code=403, detail="Access denied")
            checked_projects.add(task.project_id)

    updated_count = 0
    for task in tasks:
        # Initialize meta if it doesn't exist
        if task.meta == None:  # noqa: E711
            task.meta = {}

        if merge:
            # Merge with existing metadata
            task.meta = {**task.meta, **metadata}
        else:
            # Replace all metadata
            task.meta = metadata

        # Mark the field as modified for SQLAlchemy
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(task, "meta")

        db.add(task)
        updated_count += 1

    await db.commit()

    return {
        "updated_count": updated_count,
        "task_ids": task_ids,
        "metadata": metadata,
        "message": f"Updated metadata for {updated_count} tasks",
    }
