"""Bulk operations for projects."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from notification_service import notify_project_archived, notify_project_deleted
from project_models import Project, ProjectMember, ProjectOrganization, Task
from routers.projects.helpers import check_user_can_edit_project

router = APIRouter()


@router.post("/bulk-delete")
async def bulk_delete_projects(
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
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
            project = db.query(Project).filter(Project.id == project_id).first()
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
            project_org = (
                db.query(ProjectOrganization.organization_id)
                .filter(ProjectOrganization.project_id == project_id)
                .first()
            )
            organization_id = project_org[0] if project_org else None

            # Delete associated records first to avoid foreign key constraint violations
            # ProjectMember and ProjectOrganization are already imported at the top of the file

            # Delete project organizations
            db.query(ProjectOrganization).filter(
                ProjectOrganization.project_id == project_id
            ).delete(synchronize_session=False)

            # Delete project members
            db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete(
                synchronize_session=False
            )

            # Delete associated tasks and annotations
            # NOTE: Annotation table doesn't exist yet - skipping deletion
            # db.query(Annotation).filter(Annotation.project_id == project_id).delete(
            #     synchronize_session=False
            # )
            db.query(Task).filter(Task.project_id == project_id).delete(synchronize_session=False)

            # Delete the project
            db.delete(project)

            # Commit this individual project deletion
            db.commit()
            deleted_count += 1
            logger.info(f"Successfully deleted project {project_id}")

            # Send notification about project deletion
            try:
                notify_project_deleted(
                    db=db,
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
                db.rollback()
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
    db: Session = Depends(get_db),
):
    """Bulk archive multiple projects"""

    project_ids = data.get("project_ids", [])
    archived_count = 0

    for project_id in project_ids:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            continue

        # Check permission - creator, superadmin, org admin, or contributor
        if not check_user_can_edit_project(db, current_user, project.id):
            continue

        project.is_archived = True
        archived_count += 1

        # Send notification about project archival
        try:
            notify_project_archived(
                db=db,
                project_id=project.id,
                project_title=project.title,
                archived_by_user_id=current_user.id,
                archived_by_username=current_user.name,
                # Get first organization for backward compatibility
                organization_id=(
                    db.query(ProjectOrganization.organization_id)
                    .filter(ProjectOrganization.project_id == project_id)
                    .first()[0]
                    if db.query(ProjectOrganization)
                    .filter(ProjectOrganization.project_id == project_id)
                    .first()
                    else None
                ),
            )
        except Exception as e:
            # Log notification error but don't fail archival
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send project archival notification: {e}")

    db.commit()

    return {"archived": archived_count}


@router.post("/bulk-unarchive")
async def bulk_unarchive_projects(
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk unarchive multiple projects"""

    project_ids = data.get("project_ids", [])
    unarchived_count = 0

    for project_id in project_ids:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            continue

        # Check permission - creator, superadmin, org admin, or contributor
        if not check_user_can_edit_project(db, current_user, project.id):
            continue

        project.is_archived = False
        unarchived_count += 1

    db.commit()

    return {"unarchived": unarchived_count}
