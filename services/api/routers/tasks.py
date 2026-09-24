"""
Global tasks API router for cross-project task management.
Provides endpoints to list, filter, and manage tasks across all projects.
"""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.types import String

from auth_module import User as AuthUser
from auth_module import require_user
from database import get_async_db
from models import Organization, OrganizationMembership
from org_groups import attachment_group_clause
from project_models import Project, ProjectOrganization, Task, TaskAssignment
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
    """The CANDIDATE projects of the cross-project data surface.

    The projects the caller is connected to (org attachments of active
    memberships); every non-deleted project for
    superadmins. Not an access decision on its own: the endpoints below pass
    the candidates through :func:`_resolve_data_scope`, which applies the
    per-project access tiers and task scoping.
    """
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

    # Combine all accessible project IDs
    project_ids = set()
    project_ids.update([p.id for p in org_projects])
    project_ids.update([p.id for p in public_projects])

    return list(project_ids)


class _DataScope:
    """The caller's per-request view of the cross-project data surface.

    Computed once per request by :func:`_resolve_data_scope` and reused by
    every filter, the count, the payload and the export, so the per-project
    decisions never run per task (or per search):

    - ``project_ids``: the candidate projects the caller may open through the
      per-project endpoints (the tier of ``get_project_access_tier_async``),
      minus pre-open windows they cannot read.
    - ``bound``: per project, ``None`` (editor tier, full ``task.data``) or
      the label-config-bound fields a blinded caller may see.
    - ``attempted_only`` / ``assigned_only``: projects whose rows are narrowed
      like the per-project listing narrows them (own submissions for the
      attempted tier; open assignments for org ANNOTATORs in manual / auto
      assignment mode).
    """

    __slots__ = ("user_id", "project_ids", "bound", "attempted_only", "assigned_only")

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.project_ids: List[str] = []
        self.bound: Dict[str, Optional[Set[str]]] = {}
        self.attempted_only: Set[str] = set()
        self.assigned_only: Set[str] = set()

    def is_blinded(self, project_id: str) -> bool:
        return self.bound.get(project_id) is not None

    def blinded_ids(self) -> List[str]:
        return [pid for pid in self.project_ids if self.is_blinded(pid)]

    def editor_ids(self) -> List[str]:
        return [pid for pid in self.project_ids if not self.is_blinded(pid)]

    def task_clause(self):
        """SQL condition over ``Task``: the rows the caller may see."""
        from routers.projects.helpers import own_active_annotation_exists

        narrowed = self.attempted_only | self.assigned_only
        clauses = []
        unscoped = [pid for pid in self.project_ids if pid not in narrowed]
        if unscoped:
            clauses.append(Task.project_id.in_(unscoped))
        if self.attempted_only:
            clauses.append(
                and_(
                    Task.project_id.in_(sorted(self.attempted_only)),
                    own_active_annotation_exists(self.user_id),
                )
            )
        if self.assigned_only:
            clauses.append(
                and_(
                    Task.project_id.in_(sorted(self.assigned_only)),
                    exists().where(
                        TaskAssignment.task_id == Task.id,
                        TaskAssignment.user_id == self.user_id,
                        # Same as the per-project listing: completed
                        # assignments drop out of the annotator's list.
                        TaskAssignment.status != "completed",
                    ),
                )
            )
        return or_(*clauses) if clauses else false()


async def _resolve_data_scope(
    db: AsyncSession, user: AuthUser, candidate_ids: Iterable[str]
) -> _DataScope:
    """Apply the per-project access decision to the candidate projects.

    Mirrors ``require_project_access(allow_participant=True)`` plus the
    per-project task listing (``routers/projects/tasks/listing.py``), using
    the batched list helpers the project list stamps its tiers with, so the
    work is a fixed number of queries per request whatever the org size:

    - tier: full (``get_accessible_project_ids_async``, with the archived
      carve-out of ``check_project_accessible``) > participant
      (``get_participant_project_ids_async``) > attempted
      (``get_attempted_project_ids_async``); no tier = not listed;
    - read window: pre-open projects are hidden unless the caller can edit
      them or holds the attempted tier (``enforce_project_read_window``);
    - task scoping: attempted tier → own submissions; org ANNOTATOR on a
      manual / auto assignment project → own open assignments;
    - blinding: the effective role of ``resolve_project_roles_batch_async``
      through ``bound_fields_for_role`` (same decision as
      ``annotator_bound_fields_or_none_async``).

    Superadmins keep every candidate unnarrowed and unblinded.
    """
    from org_groups import get_user_group_context_async
    from project_window import project_reads_allowed
    from routers.projects.helpers import (
        TIER_ATTEMPTED,
        TIER_FULL,
        TIER_PARTICIPANT,
        _memberships_of,
        get_accessible_project_ids_async,
        get_attempted_project_ids_async,
        get_participant_project_ids_async,
        get_user_with_memberships_async,
        resolve_project_roles_batch_async,
    )
    from routers.projects.tasks.blinding import bound_fields_for_role
    from routers.projects.tasks.listing import (
        annotator_sees_assigned_only,
        listing_org_role,
    )

    scope = _DataScope(str(user.id))
    ids = sorted({str(pid) for pid in candidate_ids})
    if not ids:
        return scope
    if user.is_superadmin:
        scope.project_ids = ids
        scope.bound = {pid: None for pid in ids}
        return scope

    projects = (
        (
            await db.execute(
                select(Project)
                .options(selectinload(Project.project_organizations))
                .where(Project.id.in_(ids), Project.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    if not projects:
        return scope

    uid = str(user.id)
    full_ids = {str(pid) for pid in (await get_accessible_project_ids_async(db, user) or [])}
    participant_ids = set(await get_participant_project_ids_async(db, uid))
    attempted_ids = await get_attempted_project_ids_async(db, uid)
    memberships = list(_memberships_of(await get_user_with_memberships_async(db, uid)))
    user_groups = await get_user_group_context_async(db, uid)
    roles = await resolve_project_roles_batch_async(
        db, user, projects, memberships=memberships, user_groups=user_groups
    )

    for project in sorted(projects, key=lambda p: str(p.id)):
        pid = str(project.id)
        role, can_edit = roles.get(pid, (None, False))
        archived = bool(getattr(project, "is_archived", False))
        if pid in full_ids and not (archived and role == "ANNOTATOR"):
            tier = TIER_FULL
        elif pid in participant_ids and not archived:
            tier = TIER_PARTICIPANT
        elif pid in attempted_ids:
            tier = TIER_ATTEMPTED
        else:
            continue
        if not project_reads_allowed(project) and tier != TIER_ATTEMPTED and not can_edit:
            continue
        scope.project_ids.append(pid)
        scope.bound[pid] = bound_fields_for_role(role, project)
        if tier == TIER_ATTEMPTED:
            scope.attempted_only.add(pid)
        elif annotator_sees_assigned_only(
            listing_org_role(
                memberships, [po.organization_id for po in project.project_organizations]
            ),
            project,
        ):
            scope.assigned_only.add(pid)
    return scope


async def _accessible_scope(
    db: AsyncSession, user: AuthUser, project_ids: Optional[Iterable[str]] = None
) -> _DataScope:
    """The request's :class:`_DataScope`, optionally narrowed to ``project_ids``."""
    candidates = set(await get_user_accessible_projects(db, user))
    if project_ids:
        candidates &= set(project_ids)
    return await _resolve_data_scope(db, user, candidates)


def _visible_assignee_id(task: Task, scope: _DataScope) -> Optional[str]:
    """``task.assigned_to`` as the caller may see it: editors see every
    assignment, blinded callers only their own (per-project listing rule)."""
    if not task.assigned_to:
        return None
    if scope.is_blinded(task.project_id) and str(task.assigned_to) != scope.user_id:
        return None
    return task.assigned_to


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
    # No feature flag check needed - page access is controlled by data_page flag

    # The per-project access decision (tier, read window, task scoping,
    # blinding), resolved once for the whole request.
    scope = await _accessible_scope(db, current_user, project_ids)
    if not scope.project_ids:
        return PaginatedResponse(items=[], total=0, page=page, page_size=page_size, pages=0)
    visible = scope.task_clause()

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
        .where(visible)
    )
    count_stmt = select(func.count()).select_from(Task).where(visible)

    # Apply status filter
    if status and status != 'all':
        if status == 'completed':
            cond = Task.is_labeled == True  # noqa: E712
        elif status == 'incomplete':
            cond = Task.is_labeled == False  # noqa: E712
        elif status == 'in_progress':
            # On blinded projects "assigned" means assigned to the caller —
            # whether someone else holds a task is editor data.
            assigned_cond = Task.assigned_to.isnot(None)
            blinded_pids = scope.blinded_ids()
            if blinded_pids:
                assigned_cond = or_(
                    and_(Task.project_id.notin_(blinded_pids), assigned_cond),
                    Task.assigned_to == scope.user_id,
                )
            cond = and_(assigned_cond, Task.is_labeled == False)  # noqa: E712
        else:
            cond = None
        if cond is not None:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

    # Apply assigned user filter. Other users' assignments are editor data:
    # on blinded projects the filter only ever matches the caller's own rows,
    # so it cannot be used to probe who is assigned what.
    if assigned_to:
        assignee_pids = (
            scope.project_ids if assigned_to == scope.user_id else scope.editor_ids()
        )
        cond = (
            and_(Task.project_id.in_(assignee_pids), Task.assigned_to == assigned_to)
            if assignee_pids
            else false()
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

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
            visible_data_keys_by_project_async,
            visible_keys_match,
        )

        full_pids = scope.editor_ids()
        data_keys = await visible_data_keys_by_project_async(
            db, {pid: scope.bound[pid] for pid in scope.blinded_ids()}
        )
        blinded_by_keys: Dict[tuple, List[str]] = {}
        for pid, keys in data_keys.items():
            if keys:
                blinded_by_keys.setdefault(tuple(sorted(keys)), []).append(pid)

        data_clauses = []
        if full_pids:
            data_clauses.append(
                and_(
                    Task.project_id.in_(full_pids),
                    func.cast(Task.data, String).ilike(search_pattern),
                )
            )
        for keys, pids in blinded_by_keys.items():
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

    # Apply sorting. Ordering by the assignee would group rows by other
    # users' hidden assignments, so blinded callers fall back to the default.
    if sort_by == "assigned_to" and scope.blinded_ids():
        stmt = stmt.order_by(Task.created_at.desc())
    elif hasattr(Task, sort_by):
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
    page_decisions = scope.bound
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

    # Tasks the caller may see (same per-project decision as the listing)
    scope = await _accessible_scope(db, current_user)
    tasks_result = await db.execute(
        select(Task).where(and_(Task.id.in_(task_ids), scope.task_clause()))
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

    # Tasks the caller may see (same per-project decision as the listing)
    scope = await _accessible_scope(db, current_user)
    tasks_result = await db.execute(
        select(Task).where(and_(Task.id.in_(task_ids), scope.task_clause()))
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
    # The per-project access decision (tier, read window, task scoping,
    # blinding), resolved once — same scope as the listing.
    scope = await _accessible_scope(db, current_user)

    # Build query — eager-load project so task.project.title doesn't lazy-load.
    stmt = (
        select(Task)
        .join(Project)
        .options(joinedload(Task.project))
        .where(scope.task_clause())
    )

    # Filter by specific task IDs if provided
    if task_ids:
        stmt = stmt.where(Task.id.in_(task_ids))

    tasks_result = await db.execute(stmt)
    tasks = tasks_result.unique().scalars().all()

    # Annotator blinding, same as the listing above.
    decisions = scope.bound
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
                    "assigned_to": _visible_assignee_id(task, scope),
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
                    _visible_assignee_id(task, scope) or "",
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
