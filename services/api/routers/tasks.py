"""
Global tasks API router for cross-project task management.
Provides endpoints to list, filter, and manage tasks across all projects.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.types import String

from auth_module import User as AuthUser
from auth_module import require_user
from database import get_db
from models import Organization, OrganizationMembership
from project_models import Project, ProjectMember, ProjectOrganization, Task
from project_schemas import PaginatedResponse


# Define TaskResponse schema
class TaskResponse(BaseModel):
    id: str
    project_id: str
    project: Dict[str, Any]
    data: Any  # Can be Dict, List, or other JSON-serializable type
    meta: Dict[str, Any]
    is_labeled: bool
    assigned_to: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: Optional[datetime]
    annotations_count: int

    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/data", tags=["data-management"])


def get_user_accessible_projects(db: Session, user: AuthUser) -> List[str]:
    """Get list of project IDs that the user has access to."""
    # Superadmins can access everything
    if user.is_superadmin:
        projects = db.query(Project.id).all()
        return [p.id for p in projects]

    # Get user's organizations
    user_orgs = (
        db.query(OrganizationMembership.organization_id)
        .filter(OrganizationMembership.user_id == user.id)
        .subquery()
    )

    # Get projects from user's organizations (private projects)
    # Get projects linked to user's organizations (private projects)
    org_projects = (
        db.query(Project.id)
        .join(ProjectOrganization, ProjectOrganization.project_id == Project.id)
        .filter(ProjectOrganization.organization_id.in_(user_orgs))
        .all()
    )

    # Note: All projects are considered accessible for now
    # TODO: Add public/private project visibility if needed
    public_projects = []

    # Get projects where user is a member
    member_projects = (
        db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user.id).all()
    )

    # Combine all accessible project IDs
    project_ids = set()
    project_ids.update([p.id for p in org_projects])
    project_ids.update([p.id for p in public_projects])
    project_ids.update([p.project_id for p in member_projects])

    return list(project_ids)


@router.get("/", response_model=PaginatedResponse[TaskResponse])
async def list_all_tasks(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    project_ids: Optional[List[str]] = Query(None, description="Filter by project IDs"),
    status: Optional[str] = Query(
        None, pattern="^(all|completed|incomplete|in_progress)$", description="Filter by status"
    ),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned user ID"),
    search: Optional[str] = Query(None, description="Search in task data and metadata"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    date_from: Optional[datetime] = Query(None, description="Filter tasks created after this date"),
    date_to: Optional[datetime] = Query(None, description="Filter tasks created before this date"),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    List all tasks across projects with pagination and filtering.

    This endpoint provides a global view of all tasks the user has access to,
    with comprehensive filtering and sorting capabilities.
    """

    # No feature flag check needed - page access is controlled by data_page flag

    # Get accessible projects for the user
    accessible_projects = get_user_accessible_projects(db, current_user)

    # If project_ids filter is provided, intersect with accessible projects
    if project_ids:
        filtered_project_ids = list(set(project_ids) & set(accessible_projects))
        if not filtered_project_ids:
            # User doesn't have access to any of the requested projects
            return PaginatedResponse(items=[], total=0, page=page, page_size=page_size, pages=0)
    else:
        filtered_project_ids = accessible_projects

    # Build base query with project information
    query = (
        db.query(Task)
        .join(Project)
        .options(joinedload(Task.project), joinedload(Task.assigned_user))
        .filter(Task.project_id.in_(filtered_project_ids))
    )

    # Apply status filter
    if status and status != 'all':
        if status == 'completed':
            query = query.filter(Task.is_labeled == True)
        elif status == 'incomplete':
            query = query.filter(Task.is_labeled == False)
        elif status == 'in_progress':
            query = query.filter(and_(Task.assigned_to.isnot(None), Task.is_labeled == False))

    # Apply assigned user filter
    if assigned_to:
        query = query.filter(Task.assigned_to == assigned_to)

    # Apply date range filter
    if date_from:
        query = query.filter(Task.created_at >= date_from)
    if date_to:
        query = query.filter(Task.created_at <= date_to)

    # Apply search filter (searches in data and meta fields)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                func.cast(Task.data, String).ilike(search_pattern),
                func.cast(Task.meta, String).ilike(search_pattern),
                Task.id.ilike(search_pattern),
            )
        )

    # Get total count before pagination
    total_count = query.count()

    # Apply sorting
    if hasattr(Task, sort_by):
        order_column = getattr(Task, sort_by)
        if sort_order == "desc":
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
    else:
        # Default sorting
        query = query.order_by(Task.created_at.desc())

    # Apply pagination
    offset = (page - 1) * page_size
    tasks = query.offset(offset).limit(page_size).all()

    # Format tasks for response
    task_responses = []
    for task in tasks:
        # Get annotation count
        annotation_count = len(task.annotations) if hasattr(task, 'annotations') else 0

        # Get the organization for this project
        from project_models import ProjectOrganization

        project_org = (
            db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == task.project_id)
            .first()
        )

        org_name = None
        if project_org:
            org = (
                db.query(Organization)
                .filter(Organization.id == project_org.organization_id)
                .first()
            )
            if org:
                org_name = org.name

        task_response = TaskResponse(
            id=task.id,
            project_id=task.project_id,
            project={
                "id": task.project.id,
                "title": task.project.title,
                "organization": org_name,
            },
            data=task.data,
            meta=task.meta or {},
            is_labeled=task.is_labeled,
            assigned_to=task.assigned_user if task.assigned_to else None,
            created_at=task.created_at,
            updated_at=task.updated_at,
            annotations_count=annotation_count,
        )
        task_responses.append(task_response)

    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size

    return PaginatedResponse(
        items=task_responses,
        total=total_count,
        page=page,
        page_size=page_size,
        pages=total_pages,
    )


@router.post("/bulk-assign")
async def bulk_assign_tasks(
    task_ids: List[str],
    user_id: str,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Bulk assign multiple tasks to a user.
    Requires appropriate permissions for each task's project.
    """
    # No feature flag check needed - page access is controlled by data_page flag

    # Get accessible projects for the user
    accessible_projects = get_user_accessible_projects(db, current_user)

    # Get tasks and verify access
    tasks = (
        db.query(Task)
        .filter(and_(Task.id.in_(task_ids), Task.project_id.in_(accessible_projects)))
        .all()
    )

    if len(tasks) != len(task_ids):
        raise HTTPException(
            status_code=403, detail="You don't have permission to assign some of the selected tasks"
        )

    # Update assignments
    for task in tasks:
        task.assigned_to = user_id
        task.updated_at = datetime.utcnow()

    db.commit()

    return {"message": f"Successfully assigned {len(tasks)} tasks to user {user_id}"}


@router.post("/bulk-update-status")
async def bulk_update_task_status(
    task_ids: List[str],
    is_labeled: bool,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Bulk update the completion status of multiple tasks.
    Requires appropriate permissions for each task's project.
    """
    # No feature flag check needed - page access is controlled by data_page flag

    # Get accessible projects for the user
    accessible_projects = get_user_accessible_projects(db, current_user)

    # Get tasks and verify access
    tasks = (
        db.query(Task)
        .filter(and_(Task.id.in_(task_ids), Task.project_id.in_(accessible_projects)))
        .all()
    )

    if len(tasks) != len(task_ids):
        raise HTTPException(
            status_code=403, detail="You don't have permission to update some of the selected tasks"
        )

    # Update status
    for task in tasks:
        task.is_labeled = is_labeled
        task.updated_at = datetime.utcnow()

    db.commit()

    status = "completed" if is_labeled else "incomplete"
    return {"message": f"Successfully marked {len(tasks)} tasks as {status}"}


@router.post("/export")
async def export_tasks(
    task_ids: Optional[List[str]] = None,
    format: str = Query("json", pattern="^(json|csv)$"),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Export selected tasks or all accessible tasks in specified format.
    """
    import csv
    import io
    import json

    from fastapi.responses import Response

    # No feature flag check needed - page access is controlled by data_page flag
    # Get accessible projects for the user
    accessible_projects = get_user_accessible_projects(db, current_user)

    # Build query
    query = db.query(Task).join(Project).filter(Task.project_id.in_(accessible_projects))

    # Filter by specific task IDs if provided
    if task_ids:
        query = query.filter(Task.id.in_(task_ids))

    tasks = query.all()

    if format == "json":
        # Export as JSON
        export_data = {
            "tasks": [],
            "export_date": datetime.utcnow().isoformat(),
            "total_tasks": len(tasks),
        }

        for task in tasks:
            export_data["tasks"].append(
                {
                    "id": task.id,
                    "project_id": task.project_id,
                    "project_title": task.project.title,
                    "data": task.data,
                    "meta": task.meta,
                    "is_labeled": task.is_labeled,
                    "assigned_to": task.assigned_to,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                }
            )

        content = json.dumps(export_data, indent=2)
        media_type = "application/json"
        filename = f"tasks_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

    else:  # CSV format
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(
            [
                "task_id",
                "project_id",
                "project_title",
                "is_labeled",
                "assigned_to",
                "created_at",
                "updated_at",
            ]
        )

        # Write data rows
        for task in tasks:
            writer.writerow(
                [
                    task.id,
                    task.project_id,
                    task.project.title,
                    task.is_labeled,
                    task.assigned_to or "",
                    task.created_at.isoformat() if task.created_at else "",
                    task.updated_at.isoformat() if task.updated_at else "",
                ]
            )

        content = output.getvalue()
        media_type = "text/csv"
        filename = f"tasks_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
