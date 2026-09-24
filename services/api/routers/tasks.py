"""
Global tasks API router for cross-project task management.
Provides endpoints to list, filter, and manage tasks across all projects.
"""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.types import String

from auth_module import User as AuthUser
from auth_module import require_user
from database import get_async_db
from models import Organization, OrganizationMembership
from org_groups import attachment_group_clause
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
    # Display label of the assigned user (LMS accounts may appear by
    # pseudonym); non-editors only ever see their own assignment.
    assigned_to: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    annotations_count: int

    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/data", tags=["data-management"])


async def get_user_accessible_projects(db: AsyncSession, user: AuthUser) -> List[str]:
    """Get list of project IDs that the user has access to."""
    # Superadmins can access everything
    if user.is_superadmin:
        result = await db.execute(select(Project.id).where(Project.deleted_at.is_(None)))
        return [row[0] for row in result.all()]

    # Get projects linked to user's organizations (active memberships only —
    # a deactivated membership must not grant continued access to that org's
    # task data). Grouped attachments are eligible only for their group's
    # members / the org's ORG_ADMINs / the creator (shared/org_groups rule).
    org_result = await db.execute(
        select(Project.id)
        .join(ProjectOrganization, ProjectOrganization.project_id == Project.id)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id
            == ProjectOrganization.organization_id,
        )
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active == True,  # noqa: E712
            Project.deleted_at.is_(None),
            attachment_group_clause(
                ProjectOrganization,
                str(user.id),
                membership=OrganizationMembership,
                project=Project,
            ),
        )
    )
    org_projects = org_result.all()

    # Note: All projects are considered accessible for now
    # TODO: Add public/private project visibility if needed
    public_projects = []

    # Get projects where user is a member
    member_result = await db.execute(
        select(ProjectMember.project_id)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(ProjectMember.user_id == user.id, Project.deleted_at.is_(None))
    )
    member_projects = member_result.all()

    # Combine all accessible project IDs
    project_ids = set()
    project_ids.update([p.id for p in org_projects])
    project_ids.update([p.id for p in public_projects])
    project_ids.update([p.project_id for p in member_projects])

    return list(project_ids)


async def _blinding_by_project(
    db: AsyncSession, user: AuthUser, projects: Iterable[Project]
) -> Dict[str, Optional[Set[str]]]:
    """Per-project annotator-blinding decision for the cross-project surface.

    Reuses the exact decision the per-project serving endpoints apply
    (routers/projects/tasks/blinding.py): ``None`` = editor tier, full
    ``task.data``; a set = the label-config-bound fields the caller may see.
    """
    from routers.projects.tasks.blinding import annotator_bound_fields_or_none_async

    decisions: Dict[str, Optional[Set[str]]] = {}
    for project in projects:
        if project.id not in decisions:
            decisions[project.id] = await annotator_bound_fields_or_none_async(
                db, user, project
            )
    return decisions


async def _revealed_ids_by_project(
    db: AsyncSession,
    user: AuthUser,
    tasks: Iterable[Task],
    decisions: Dict[str, Optional[Set[str]]],
) -> Set[str]:
    """Task ids a blinded caller may see in full via the post-submit reveal."""
    from routers.projects.tasks.blinding import revealed_task_ids_async

    by_project: Dict[str, List[Task]] = {}
    for task in tasks:
        if decisions.get(task.project_id) is not None:
            by_project.setdefault(task.project_id, []).append(task)
    revealed: Set[str] = set()
    for project_tasks in by_project.values():
        revealed |= await revealed_task_ids_async(
            db, user, project_tasks[0].project, [t.id for t in project_tasks]
        )
    return revealed


def _served_task_data(
    task: Task,
    decisions: Dict[str, Optional[Set[str]]],
    revealed_ids: Set[str],
):
    """``task.data`` as the caller may see it (full or blinded)."""
    from routers.projects.tasks.blinding import blind_task_data

    bound = decisions.get(task.project_id)
    if bound is None or task.id in revealed_ids:
        return task.data
    return blind_task_data(task.data, bound)


async def _require_edit_rights(db: AsyncSession, user: AuthUser, tasks: Iterable[Task]) -> None:
    """403 unless ``user`` may edit EVERY project the selected tasks belong
    to. Bulk writes are all-or-nothing: a mixed selection is rejected whole."""
    from routers.projects.helpers import check_user_can_edit_project_async

    for project_id in sorted({t.project_id for t in tasks}):
        if not await check_user_can_edit_project_async(db, user, project_id):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to modify tasks in some of the selected projects",
            )


async def _upcoming_blocked_project_ids(
    db: AsyncSession, user: AuthUser, projects: Iterable[Project]
) -> Set[str]:
    """Projects whose timed window has not opened and the caller cannot edit.

    Task data of those projects is hidden from the access group until the
    window opens (editors exempt), same as the per-project read endpoints.
    """
    from project_window import project_window_state
    from routers.projects.helpers import check_user_can_edit_project_async

    blocked: Set[str] = set()
    for project in {p.id: p for p in projects}.values():
        if project_window_state(project) == "upcoming" and not (
            await check_user_can_edit_project_async(db, user, project.id)
        ):
            blocked.add(project.id)
    return blocked


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
    db: AsyncSession = Depends(get_async_db),
):
    """
    List all tasks across projects with pagination and filtering.

    This endpoint provides a global view of all tasks the user has access to,
    with comprehensive filtering and sorting capabilities.
    """
    from sqlalchemy.orm import selectinload

    # No feature flag check needed - page access is controlled by data_page flag

    # Get accessible projects for the user
    accessible_projects = await get_user_accessible_projects(db, current_user)

    # If project_ids filter is provided, intersect with accessible projects
    if project_ids:
        filtered_project_ids = list(set(project_ids) & set(accessible_projects))
        if not filtered_project_ids:
            # User doesn't have access to any of the requested projects
            return PaginatedResponse(items=[], total=0, page=page, page_size=page_size, pages=0)
    else:
        filtered_project_ids = accessible_projects

    # Timed access window: drop projects whose window has not opened yet for
    # callers who cannot edit them (the per-project endpoints 403 them).
    scope_projects = (
        (
            await db.execute(select(Project).where(Project.id.in_(filtered_project_ids)))
        )
        .scalars()
        .all()
        if filtered_project_ids
        else []
    )
    blocked_pids = await _upcoming_blocked_project_ids(db, current_user, scope_projects)
    if blocked_pids:
        scope_projects = [p for p in scope_projects if p.id not in blocked_pids]
        filtered_project_ids = [pid for pid in filtered_project_ids if pid not in blocked_pids]

    # Build base query with project information. Eager-load the relationships
    # the response reads (project / assigned_user / annotations) so the async
    # engine never triggers a lazy load (MissingGreenlet) during serialization.
    stmt = (
        select(Task)
        .join(Project)
        .options(
            joinedload(Task.project),
            joinedload(Task.assigned_user),
            selectinload(Task.annotations),
        )
        .where(Task.project_id.in_(filtered_project_ids))
    )
    count_stmt = (
        select(func.count())
        .select_from(Task)
        .where(Task.project_id.in_(filtered_project_ids))
    )

    # Apply status filter
    if status and status != 'all':
        if status == 'completed':
            cond = Task.is_labeled == True  # noqa: E712
        elif status == 'incomplete':
            cond = Task.is_labeled == False  # noqa: E712
        elif status == 'in_progress':
            cond = and_(Task.assigned_to.isnot(None), Task.is_labeled == False)  # noqa: E712
        else:
            cond = None
        if cond is not None:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

    # Apply assigned user filter
    if assigned_to:
        stmt = stmt.where(Task.assigned_to == assigned_to)
        count_stmt = count_stmt.where(Task.assigned_to == assigned_to)

    # Apply date range filter
    if date_from:
        stmt = stmt.where(Task.created_at >= date_from)
        count_stmt = count_stmt.where(Task.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Task.created_at <= date_to)
        count_stmt = count_stmt.where(Task.created_at <= date_to)

    # Apply search filter (searches in data and meta fields)
    if search:
        search_pattern = f"%{search}%"
        # Blinded projects (annotator tier) are searched ONLY over their
        # visible, config-bound top-level keys, as on the per-project task
        # listing: matching against the raw JSON would let the match count
        # reveal content of hidden reference fields.
        from routers.projects.tasks.blinding import (
            visible_keys_match,
            visible_top_level_keys,
        )

        decisions = await _blinding_by_project(db, current_user, scope_projects)
        full_pids = [pid for pid, bound in decisions.items() if bound is None]
        blinded_by_keys: Dict[tuple, List[str]] = {}
        for pid, bound in decisions.items():
            if bound is not None:
                keys = tuple(sorted(visible_top_level_keys(bound)))
                blinded_by_keys.setdefault(keys, []).append(pid)

        data_clauses = []
        if full_pids:
            data_clauses.append(
                and_(
                    Task.project_id.in_(full_pids),
                    func.cast(Task.data, String).ilike(search_pattern),
                )
            )
        for keys, pids in blinded_by_keys.items():
            if keys:
                data_clauses.append(
                    and_(
                        Task.project_id.in_(pids),
                        visible_keys_match(Task.data, keys, search_pattern),
                    )
                )
        search_cond = or_(
            *(data_clauses or [false()]),
            func.cast(Task.meta, String).ilike(search_pattern),
            Task.id.ilike(search_pattern),
        )
        stmt = stmt.where(search_cond)
        count_stmt = count_stmt.where(search_cond)

    # Get total count before pagination
    total_count = int((await db.execute(count_stmt)).scalar() or 0)

    # Apply sorting
    if hasattr(Task, sort_by):
        order_column = getattr(Task, sort_by)
        if sort_order == "desc":
            stmt = stmt.order_by(order_column.desc())
        else:
            stmt = stmt.order_by(order_column.asc())
    else:
        # Default sorting
        stmt = stmt.order_by(Task.created_at.desc())

    # Apply pagination
    offset = (page - 1) * page_size
    tasks_result = await db.execute(stmt.offset(offset).limit(page_size))
    tasks = tasks_result.unique().scalars().all()

    # Pre-fetch org names for all projects on this page in one query each,
    # avoiding an N+1 over the per-task org lookup.
    page_project_ids = list({t.project_id for t in tasks})
    org_name_by_project: Dict[str, Optional[str]] = {}
    if page_project_ids:
        org_rows = await db.execute(
            select(ProjectOrganization.project_id, Organization.name)
            .join(
                Organization,
                Organization.id == ProjectOrganization.organization_id,
            )
            .where(ProjectOrganization.project_id.in_(page_project_ids))
        )
        for pid, name in org_rows.all():
            # First org wins, mirroring the prior .first() semantics.
            org_name_by_project.setdefault(pid, name)

    # Annotator blinding: reference fields (Musterlösung, ground truth, …)
    # are stripped for non-editor tiers exactly like on the per-project task
    # endpoints; editor tiers keep the full data.
    page_decisions = await _blinding_by_project(db, current_user, [t.project for t in tasks])
    revealed_ids = await _revealed_ids_by_project(db, current_user, tasks, page_decisions)

    # Assignee: non-editors only see their OWN assignment (same rule as the
    # per-project listing); other users' identities are editor data. Editors
    # get the project-scoped name mask (LMS accounts by pseudonym unless the
    # viewer may see real names), also as on the per-project listing.
    from services.member_privacy import NameMask, project_name_masks

    visible_assignees: Dict[str, List[Any]] = {}
    for task in tasks:
        if task.assigned_to and task.assigned_user is not None:
            if page_decisions.get(task.project_id) is None:
                visible_assignees.setdefault(task.project_id, []).append(task.assigned_user)
    name_masks = (
        await project_name_masks(db, visible_assignees, viewer=current_user)
        if visible_assignees
        else {}
    )

    def _assignee_label(task: Task) -> Optional[str]:
        if not task.assigned_to or task.assigned_user is None:
            return None
        if page_decisions.get(task.project_id) is not None:
            if str(task.assigned_to) != str(current_user.id):
                return None
            return NameMask().label(task.assigned_user)
        return name_masks.get(str(task.project_id), NameMask()).label(task.assigned_user)

    # Format tasks for response
    task_responses = []
    for task in tasks:
        # Get annotation count
        annotation_count = len(task.annotations) if task.annotations is not None else 0

        org_name = org_name_by_project.get(task.project_id)

        task_response = TaskResponse(
            id=task.id,
            project_id=task.project_id,
            project={
                "id": task.project.id,
                "title": task.project.title,
                "organization": org_name,
            },
            data=_served_task_data(task, page_decisions, revealed_ids),
            meta=task.meta or {},
            is_labeled=task.is_labeled,
            assigned_to=_assignee_label(task),
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
    db: AsyncSession = Depends(get_async_db),
):
    """
    Bulk assign multiple tasks to a user.
    Requires appropriate permissions for each task's project.
    """
    # No feature flag check needed - page access is controlled by data_page flag

    # Get accessible projects for the user
    accessible_projects = await get_user_accessible_projects(db, current_user)

    # Get tasks and verify access
    tasks_result = await db.execute(
        select(Task).where(
            and_(Task.id.in_(task_ids), Task.project_id.in_(accessible_projects))
        )
    )
    tasks = tasks_result.scalars().all()

    if len(tasks) != len(task_ids):
        raise HTTPException(
            status_code=403, detail="You don't have permission to assign some of the selected tasks"
        )
    await _require_edit_rights(db, current_user, tasks)

    # Update assignments
    for task in tasks:
        task.assigned_to = user_id
        task.updated_at = datetime.utcnow()

    await db.commit()

    return {"message": f"Successfully assigned {len(tasks)} tasks to user {user_id}"}


@router.post("/bulk-update-status")
async def bulk_update_task_status(
    task_ids: List[str],
    is_labeled: bool,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Bulk update the completion status of multiple tasks.
    Requires appropriate permissions for each task's project.
    """
    # No feature flag check needed - page access is controlled by data_page flag

    # Get accessible projects for the user
    accessible_projects = await get_user_accessible_projects(db, current_user)

    # Get tasks and verify access
    tasks_result = await db.execute(
        select(Task).where(
            and_(Task.id.in_(task_ids), Task.project_id.in_(accessible_projects))
        )
    )
    tasks = tasks_result.scalars().all()

    if len(tasks) != len(task_ids):
        raise HTTPException(
            status_code=403, detail="You don't have permission to update some of the selected tasks"
        )
    await _require_edit_rights(db, current_user, tasks)

    # Update status
    for task in tasks:
        task.is_labeled = is_labeled
        task.updated_at = datetime.utcnow()

    await db.commit()

    status = "completed" if is_labeled else "incomplete"
    return {"message": f"Successfully marked {len(tasks)} tasks as {status}"}


@router.post("/export")
async def export_tasks(
    task_ids: Optional[List[str]] = None,
    format: str = Query("json", pattern="^(json|csv)$"),
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
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
    accessible_projects = await get_user_accessible_projects(db, current_user)

    # Build query — eager-load project so task.project.title doesn't lazy-load.
    stmt = (
        select(Task)
        .join(Project)
        .options(joinedload(Task.project))
        .where(Task.project_id.in_(accessible_projects))
    )

    # Filter by specific task IDs if provided
    if task_ids:
        stmt = stmt.where(Task.id.in_(task_ids))

    tasks_result = await db.execute(stmt)
    tasks = tasks_result.unique().scalars().all()

    # Timed access window: drop tasks whose project has not opened yet, unless
    # the user can edit that project (owner/admin/contributor exempt). Batched
    # over the distinct upcoming projects so the edit check runs at most once
    # each (usually zero). task.project is eager-loaded above.
    blocked_pids = await _upcoming_blocked_project_ids(
        db, current_user, [t.project for t in tasks]
    )
    if blocked_pids:
        tasks = [t for t in tasks if t.project_id not in blocked_pids]

    # Annotator blinding, same as the listing above.
    decisions = await _blinding_by_project(db, current_user, [t.project for t in tasks])
    revealed_ids = await _revealed_ids_by_project(db, current_user, tasks, decisions)

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
                    "data": _served_task_data(task, decisions, revealed_ids),
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
