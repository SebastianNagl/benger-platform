"""Bulk operations for projects."""

import logging

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import SessionLocal, get_async_db
from notification_service import notify_project_archived, notify_project_deleted
from project_models import Project, ProjectMember, ProjectOrganization, Task
from routers.projects.helpers import check_user_can_edit_project_async

router = APIRouter()


def _notify_project_deleted_sync(**kwargs) -> None:
    """Run the sync ``notify_project_deleted`` on a fresh short-lived sync
    session so the async handler never hands its ``AsyncSession`` to the sync
    notification path (which queries + commits on ``db``)."""
    sync_db = SessionLocal()
    try:
        notify_project_deleted(db=sync_db, **kwargs)
    finally:
        sync_db.close()


def _notify_project_archived_sync(**kwargs) -> None:
    """Run the sync ``notify_project_archived`` on a fresh short-lived sync
    session (see :func:`_notify_project_deleted_sync`)."""
    sync_db = SessionLocal()
    try:
        notify_project_archived(db=sync_db, **kwargs)
    finally:
        sync_db.close()


@router.post("/bulk-delete")
async def bulk_delete_projects(
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Bulk delete multiple projects"""

    project_ids = data.get("project_ids", [])

    logger = logging.getLogger(__name__)
    logger.info(f"Bulk delete requested for projects: {project_ids} by user: {current_user.email}")

    # Verify user has permission to delete each project
    deleted_count = 0
    failed_projects = []

    for project_id in project_ids:
        try:
            # Each project deletion in its own transaction block
            project = (
                await db.execute(select(Project).where(Project.id == project_id))
            ).scalar_one_or_none()
            if not project:
                logger.warning(f"Project {project_id} not found")
                failed_projects.append({"id": project_id, "reason": "Project not found"})
                continue

            # Check permission - only creator or superadmin can delete
            if project.created_by != current_user.id and not current_user.is_superadmin:
                logger.warning(
                    f"User {current_user.email} lacks permission to delete project {project_id} (created by {project.created_by}, user is_superadmin: {current_user.is_superadmin})"
                )
                failed_projects.append({"id": project_id, "reason": "Permission denied"})
                continue

            logger.info(f"Deleting project {project_id} ({project.title})")

            # Store project info for notification before deletion
            project_title = project.title
            # Get organization_id from ProjectOrganization table
            organization_id = (
                await db.execute(
                    select(ProjectOrganization.organization_id)
                    .where(ProjectOrganization.project_id == project_id)
                    .limit(1)
                )
            ).scalar_one_or_none()

            # Delete associated records first to avoid foreign key constraint violations
            # ProjectMember and ProjectOrganization are already imported at the top of the file

            # Delete project organizations
            await db.execute(
                ProjectOrganization.__table__.delete().where(
                    ProjectOrganization.project_id == project_id
                )
            )

            # Delete project members
            await db.execute(
                ProjectMember.__table__.delete().where(
                    ProjectMember.project_id == project_id
                )
            )

            # Delete associated tasks. Annotations (annotations table) are
            # removed automatically by the DB: their task_id and project_id FKs
            # both carry ON DELETE CASCADE (migration 001_complete_baseline), so
            # this raw DELETE on tasks (and the project delete below) cascades to
            # annotations. No explicit annotation delete is needed.
            await db.execute(Task.__table__.delete().where(Task.project_id == project_id))

            # Delete the project
            await db.delete(project)

            # Commit this individual project deletion
            await db.commit()
            deleted_count += 1
            logger.info(f"Successfully deleted project {project_id}")

            # Send notification about project deletion (sync-only path; run on a
            # short-lived sync session off the event loop). Failures don't fail
            # the deletion.
            try:
                await run_in_threadpool(
                    _notify_project_deleted_sync,
                    project_id=project_id,
                    project_title=project_title,
                    deleted_by_user_id=current_user.id,
                    deleted_by_username=current_user.name,
                    organization_id=organization_id,
                )
            except Exception as e:
                # Log notification error but don't fail deletion
                logger.error(f"Failed to send project deletion notification: {e}")

        except Exception as project_error:
            logger.error(f"Failed to delete project {project_id}: {project_error}")
            failed_projects.append({"id": project_id, "reason": str(project_error)})
            try:
                await db.rollback()
            except Exception as rollback_error:
                logger.error(
                    f"Failed to rollback transaction for project {project_id}: {rollback_error}"
                )
            continue

    logger.info(
        f"Bulk delete completed. Deleted {deleted_count} projects, failed {len(failed_projects)}"
    )

    return {
        "deleted": deleted_count,
        "failed": len(failed_projects),
        "failed_projects": failed_projects,
    }


@router.post("/bulk-archive")
async def bulk_archive_projects(
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Bulk archive multiple projects"""

    project_ids = data.get("project_ids", [])
    archived_count = 0

    for project_id in project_ids:
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if not project:
            continue

        # Check permission - creator, superadmin, org admin, or contributor
        if not await check_user_can_edit_project_async(db, current_user, project.id):
            continue

        project.is_archived = True
        archived_count += 1

        # Resolve the first org assignment for the notification (backward
        # compatibility) before dispatching to the sync notification path.
        first_org_id = (
            await db.execute(
                select(ProjectOrganization.organization_id)
                .where(ProjectOrganization.project_id == project_id)
                .limit(1)
            )
        ).scalar_one_or_none()

        # Send notification about project archival (sync-only path; run on a
        # short-lived sync session off the event loop).
        try:
            await run_in_threadpool(
                _notify_project_archived_sync,
                project_id=project.id,
                project_title=project.title,
                archived_by_user_id=current_user.id,
                archived_by_username=current_user.name,
                organization_id=first_org_id,
            )
        except Exception as e:
            # Log notification error but don't fail archival
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send project archival notification: {e}")

    await db.commit()

    return {"archived": archived_count}


@router.post("/bulk-unarchive")
async def bulk_unarchive_projects(
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Bulk unarchive multiple projects"""

    project_ids = data.get("project_ids", [])
    unarchived_count = 0

    for project_id in project_ids:
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if not project:
            continue

        # Check permission - creator, superadmin, org admin, or contributor
        if not await check_user_can_edit_project_async(db, current_user, project.id):
            continue

        project.is_archived = False
        unarchived_count += 1

    await db.commit()

    return {"unarchived": unarchived_count}
