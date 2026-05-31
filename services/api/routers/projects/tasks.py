"""Task management endpoints."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import String, and_, func, or_
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from models import EvaluationRun, Generation, TaskEvaluation, User
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)
from project_schemas import SkipTaskRequest, SkipTaskResponse, TaskResponse
from routers.projects.helpers import (
    check_project_accessible,
    check_task_assigned_to_user,
    check_user_can_edit_project,
    get_org_context_from_request,
    get_user_with_memberships,
)

router = APIRouter()


@router.get("/{project_id}/tasks")
async def list_project_tasks(
    project_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    only_labeled: Optional[bool] = None,
    only_unlabeled: Optional[bool] = None,
    only_assigned: Optional[bool] = None,  # Filter for assigned tasks
    exclude_my_annotations: Optional[bool] = None,  # Exclude tasks current user has annotated
    search: Optional[str] = Query(
        None,
        description="ILIKE match against the task's JSON data or task id.",
    ),
    date_from: Optional[str] = Query(
        None, description="ISO date; lower bound on Task.created_at."
    ),
    date_to: Optional[str] = Query(
        None, description="ISO date; upper bound on Task.created_at."
    ),
    sort_by: Optional[str] = Query(
        None,
        description=(
            "id | created | completed | annotations | generations. Overrides the "
            "project's randomize_task_order when set."
        ),
    ),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    ids_only: bool = Query(
        False,
        description=(
            "When true, skip pagination + assignment enrichment and return "
            "only the matching task IDs. Used by the data tab's "
            "'select all matching' affordance so bulk operations can act on "
            "the full filtered set without paging through 50-row windows."
        ),
    ),
    ids_limit: int = Query(
        10_000,
        ge=1,
        le=100_000,
        description="Safety cap on the ids_only response.",
    ),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    List tasks in a project with role-based visibility

    Role-based access:
    - Superadmin/Admin: See all tasks
    - Contributor/Manager: See all tasks in their projects
    - Annotator: Only see tasks assigned to them (if assignment_mode is 'manual' or 'auto')
    """

    # Verify project exists and user has access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check user's role and apply visibility rules
    user_with_memberships = get_user_with_memberships(db, current_user.id)

    # Determine user's role in the organization
    user_role = None
    if current_user.is_superadmin:
        user_role = "superadmin"
    elif user_with_memberships and user_with_memberships.organization_memberships:
        # Get project organizations
        project_org_ids = (
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        )
        project_org_ids = [org_id[0] for org_id in project_org_ids]

        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    query = db.query(Task).filter(Task.project_id == project_id)

    # Apply role-based filtering
    if user_role in ["ANNOTATOR", "annotator"] and project.assignment_mode in [
        "manual",
        "auto",
    ]:
        # Annotators only see tasks assigned to them
        query = query.join(
            TaskAssignment,
            and_(
                TaskAssignment.task_id == Task.id,
                TaskAssignment.user_id == current_user.id,
                TaskAssignment.status != "completed",  # Don't show completed assignments
            ),
        )
    elif only_assigned:
        # Show only tasks with assignments (for managers/admins)
        query = query.join(TaskAssignment)

    # Apply filters
    if only_labeled:
        query = query.filter(Task.is_labeled == True)  # noqa: E712
    elif only_unlabeled:
        query = query.filter(Task.is_labeled == False)  # noqa: E712

    # Exclude tasks the current user has already annotated
    if exclude_my_annotations:
        query = query.outerjoin(
            Annotation,
            and_(
                Annotation.task_id == Task.id,
                Annotation.completed_by == current_user.id,
                Annotation.was_cancelled == False,  # noqa: E712
                Annotation.result.isnot(None),
                func.length(func.cast(Annotation.result, String)) > 2,
            ),
        ).filter(Annotation.id == None)  # noqa: E711

    # Exclude skipped tasks based on skip_queue setting
    skip_queue = getattr(project, 'skip_queue', 'requeue_for_others')
    if exclude_my_annotations and skip_queue != 'requeue_for_me':
        # Exclude tasks this user has skipped (requeue_for_others or ignore_skipped)
        my_skips = db.query(SkippedTask.task_id).filter(
            SkippedTask.project_id == project_id,
            SkippedTask.skipped_by == current_user.id,
        )
        query = query.filter(Task.id.notin_(my_skips))

    if skip_queue == 'ignore_skipped':
        # Exclude tasks that ANY user has skipped
        any_skips = db.query(SkippedTask.task_id).filter(
            SkippedTask.project_id == project_id,
        )
        query = query.filter(Task.id.notin_(any_skips))

    # Server-side search across the task's JSON payload + id. Mirrors the
    # client-side filter that AnnotationTab used to apply after loading every
    # task into memory.
    if search:
        escaped = search.replace('%', r'\%').replace('_', r'\_')
        like = f"%{escaped}%"
        query = query.filter(
            or_(
                func.cast(Task.data, String).ilike(like),
                func.cast(Task.id, String).ilike(like),
            )
        )

    # created_at range; tolerate either YYYY-MM-DD or full ISO.
    def _parse_date(raw: Optional[str]):
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    start_dt = _parse_date(date_from)
    end_dt = _parse_date(date_to)
    if start_dt is not None:
        query = query.filter(Task.created_at >= start_dt)
    if end_dt is not None:
        query = query.filter(Task.created_at <= end_dt)

    # Apply ordering. An explicit `sort_by` from the client takes precedence
    # over the project's randomize_task_order — list views need deterministic
    # ordering for pagination, the labeling cycle is the consumer that wants
    # randomization. Tie-break on Task.id so OFFSET pagination stays
    # total-stable when many rows share a sort key (see migration 044 thread:
    # batch-imported rows share an exact created_at).
    direction = (lambda c: c.desc() if sort_order == "desc" else c.asc())

    if sort_by in {"id", "created", "completed", "annotations", "generations"}:
        sort_columns = {
            "id": Task.id,
            "created": Task.created_at,
            "completed": Task.is_labeled,
            "annotations": Task.total_annotations,
            "generations": None,  # handled below — needs a join
        }
        if sort_by == "generations":
            # LEFT JOIN aggregate so tasks without generations still appear.
            gen_count_subq = (
                db.query(
                    Generation.task_id.label("task_id"),
                    func.count(Generation.id).label("c"),
                )
                .group_by(Generation.task_id)
                .subquery()
            )
            query = query.outerjoin(
                gen_count_subq, gen_count_subq.c.task_id == Task.id
            ).order_by(direction(func.coalesce(gen_count_subq.c.c, 0)), Task.id)
        else:
            query = query.order_by(direction(sort_columns[sort_by]), Task.id)
    elif project.randomize_task_order:
        # hashtext (not md5) — md5() is unavailable on FIPS-restricted Postgres builds.
        query = query.order_by(
            func.hashtext(func.concat(Task.id, current_user.id)),
            Task.id,
        )
    else:
        query = query.order_by(Task.created_at, Task.id)

    # Get total count before pagination
    total = query.count()

    # `ids_only` short-circuit — used by the data tab's "select all matching"
    # bulk-operation flow. Skip the pagination, generation-counts, and
    # assignment-enrichment work below and just return the filtered IDs.
    # `ids_limit` caps the response so a 100k-task project can't blow up
    # the client.
    if ids_only:
        id_rows = query.with_entities(Task.id).limit(ids_limit).all()
        return {
            "ids": [tid for (tid,) in id_rows],
            "total": total,
            "truncated": total > ids_limit,
        }

    # Pagination
    tasks = query.offset((page - 1) * page_size).limit(page_size).all()

    task_ids = [task.id for task in tasks]

    # Per-task generation counts in one grouped query.
    generation_counts: Dict[str, int] = {}
    if task_ids:
        gen_counts = (
            db.query(Generation.task_id, func.count(Generation.id))
            .filter(Generation.task_id.in_(task_ids))
            .group_by(Generation.task_id)
            .all()
        )
        generation_counts = {task_id: count for task_id, count in gen_counts}

    # Bulk-fetch all assignments for the page + the users they reference. Two
    # IN queries replace the previous per-task and per-assignment lookups
    # (which scaled as page_size + page_size × ~5 assignees per task).
    assignments_by_task: Dict[str, List[TaskAssignment]] = {tid: [] for tid in task_ids}
    users_by_id: Dict[str, User] = {}
    if task_ids:
        page_assignments = (
            db.query(TaskAssignment).filter(TaskAssignment.task_id.in_(task_ids)).all()
        )
        for assn in page_assignments:
            assignments_by_task.setdefault(assn.task_id, []).append(assn)
        user_ids = {a.user_id for a in page_assignments if a.user_id}
        if user_ids:
            user_rows = db.query(User).filter(User.id.in_(user_ids)).all()
            users_by_id = {u.id: u for u in user_rows}

    # Enrich tasks with assignment information
    result = []
    for task in tasks:
        task_dict = {
            "id": task.id,
            "inner_id": task.inner_id,
            "data": task.data,
            "meta": task.meta,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "is_labeled": task.is_labeled,
            "total_annotations": task.total_annotations,
            "cancelled_annotations": task.cancelled_annotations,
            "total_generations": generation_counts.get(task.id, 0),
            "project_id": task.project_id,
            "llm_responses": getattr(task, "llm_responses", None),
            "llm_evaluations": getattr(task, "llm_evaluations", None),
            "assignments": [],
            # Keep tags for backward compatibility temporarily
            "tags": task.meta.get("tags", []) if task.meta else [],
        }

        for assignment in assignments_by_task.get(task.id, []):
            assigned_user = users_by_id.get(assignment.user_id)
            if assigned_user is None:
                continue
            task_dict["assignments"].append(
                {
                    "id": assignment.id,
                    "user_id": assignment.user_id,
                    "user_name": assigned_user.name,
                    "user_email": assigned_user.email,
                    "status": assignment.status,
                    "priority": getattr(assignment, "priority", 0),
                    "due_date": getattr(assignment, "due_date", None),
                    "assigned_at": assignment.assigned_at,
                }
            )

        result.append(task_dict)

    # Return paginated response
    import math

    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/{project_id}/next")
async def get_next_task(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get next task for current user to annotate - supports multi-user annotation

    Fixed Issue #254: Multi-user annotation bug where tasks were marked as completed globally.

    Changes:
    - Uses LEFT JOIN to filter out tasks already annotated by CURRENT USER only
    - Maintains backward compatibility with global is_labeled field for analytics
    - Returns user-specific completion metrics (user_completed_tasks field)
    - Enables multiple users to independently annotate the same tasks

    Returns:
        dict: Contains task, remaining tasks for user, user completion metrics
    """

    # Check if project uses task assignment
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"detail": "Project not found", "task": None}

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Find next task based on assignment mode
    if project.assignment_mode == "manual":
        # Manual mode: only return pre-assigned tasks
        assignment = (
            db.query(TaskAssignment)
            .join(Task)
            .filter(
                Task.project_id == project_id,
                TaskAssignment.user_id == current_user.id,
                TaskAssignment.status.in_(["assigned", "in_progress"]),
            )
            .order_by(
                TaskAssignment.priority.desc(),
                TaskAssignment.due_date.asc().nullsfirst(),
                Task.created_at,
            )
            .first()
        )

        if not assignment:
            return {"detail": "No more assigned tasks", "task": None}

        next_task = db.query(Task).filter(Task.id == assignment.task_id).first()

        # Update assignment status to in_progress if it was assigned
        if assignment.status == "assigned":
            assignment.status = "in_progress"
            assignment.started_at = datetime.now()
            db.commit()

    elif project.assignment_mode == "auto":
        # Auto mode (pull model): resume existing assignment or auto-assign on demand

        # Phase 1: Check for existing active assignment (resume in-progress work)
        # Exclude tasks the user has skipped (skip creates SkippedTask but
        # doesn't cancel the assignment, so we filter here)
        user_skipped_tasks = db.query(SkippedTask.task_id).filter(
            SkippedTask.project_id == project_id,
            SkippedTask.skipped_by == current_user.id,
        )
        assignment = (
            db.query(TaskAssignment)
            .join(Task)
            .filter(
                Task.project_id == project_id,
                TaskAssignment.user_id == current_user.id,
                TaskAssignment.status.in_(["assigned", "in_progress"]),
                TaskAssignment.task_id.notin_(user_skipped_tasks),
            )
            .order_by(
                TaskAssignment.priority.desc(),
                TaskAssignment.due_date.asc().nullsfirst(),
                Task.created_at,
            )
            .first()
        )

        if assignment:
            next_task = db.query(Task).filter(Task.id == assignment.task_id).first()
            if assignment.status == "assigned":
                assignment.status = "in_progress"
                assignment.started_at = datetime.now()
                db.commit()
        else:
            # Phase 2: Auto-assign a new task on demand

            # Determine ordering: randomized per-user or sequential
            if project.randomize_task_order:
                order_clause = func.hashtext(func.concat(Task.id, current_user.id))
            else:
                order_clause = Task.created_at

            # Build skip exclusion queries (same pattern as open mode)
            skip_queue = getattr(project, 'skip_queue', 'requeue_for_others')
            my_skips_query = None
            any_skips_query = None

            if skip_queue != 'requeue_for_me':
                my_skips_query = db.query(SkippedTask.task_id).filter(
                    SkippedTask.project_id == project_id,
                    SkippedTask.skipped_by == current_user.id,
                )

            if skip_queue == 'ignore_skipped':
                any_skips_query = db.query(SkippedTask.task_id).filter(
                    SkippedTask.project_id == project_id,
                )

            # Find candidate task: not annotated by this user
            # Use NOT IN subquery instead of outerjoin (FOR UPDATE requires no outer joins)
            user_annotated_tasks = db.query(Annotation.task_id).filter(
                Annotation.completed_by == current_user.id,
                Annotation.task_id.in_(
                    db.query(Task.id).filter(Task.project_id == project_id)
                ),
            )

            candidate_query = (
                db.query(Task)
                .filter(
                    Task.project_id == project_id,
                    Task.id.notin_(user_annotated_tasks),
                )
            )

            # Enforce maximum_annotations: exclude tasks at the limit
            if project.maximum_annotations > 0:
                # Exclude tasks with enough completed non-cancelled annotations
                fully_annotated = (
                    db.query(Annotation.task_id)
                    .filter(
                        Annotation.project_id == project_id,
                        Annotation.was_cancelled == False,  # noqa: E712
                        Annotation.result != None,  # noqa: E711
                        func.length(func.cast(Annotation.result, String)) > 2,
                    )
                    .group_by(Annotation.task_id)
                    .having(func.count(Annotation.id) >= project.maximum_annotations)
                )
                candidate_query = candidate_query.filter(
                    Task.id.notin_(fully_annotated)
                )

                # Also exclude tasks with enough active assignments (reserved slots)
                # Prevents wasteful double-assignment when users request /next sequentially
                tasks_at_max_assignments = (
                    db.query(TaskAssignment.task_id)
                    .join(Task)
                    .filter(
                        Task.project_id == project_id,
                        TaskAssignment.status.in_(["assigned", "in_progress"]),
                    )
                    .group_by(TaskAssignment.task_id)
                    .having(func.count(TaskAssignment.id) >= project.maximum_annotations)
                )
                candidate_query = candidate_query.filter(
                    Task.id.notin_(tasks_at_max_assignments)
                )

            # Apply skip exclusions
            if my_skips_query is not None:
                candidate_query = candidate_query.filter(Task.id.notin_(my_skips_query))
            if any_skips_query is not None:
                candidate_query = candidate_query.filter(Task.id.notin_(any_skips_query))

            # Concurrency-safe: SELECT FOR UPDATE SKIP LOCKED
            # If another transaction locks a row, skip it and take the next one
            candidate_task = (
                candidate_query
                .order_by(order_clause)
                .with_for_update(skip_locked=True)
                .first()
            )

            if candidate_task:
                # Create assignment on the fly (self-assignment)
                new_assignment = TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=candidate_task.id,
                    user_id=current_user.id,
                    assigned_by=current_user.id,
                    status="in_progress",
                    started_at=datetime.now(),
                )
                db.add(new_assignment)
                db.commit()
                next_task = candidate_task
            else:
                next_task = None

    else:
        # Open mode - find any task the user hasn't annotated
        # Note: Annotation and sqlalchemy functions already imported at module level

        # Determine ordering: randomized per-user or sequential
        if project.randomize_task_order:
            order_clause = func.hashtext(func.concat(Task.id, current_user.id))
        else:
            order_clause = Task.created_at

        # First, check if user has any tasks with drafts (incomplete annotations)
        # A draft has: draft field populated, result field empty
        task_with_draft = (
            db.query(Task)
            .join(Annotation, Annotation.task_id == Task.id)
            .filter(
                Task.project_id == project_id,
                Annotation.completed_by == current_user.id,
                Annotation.draft.isnot(None),
                func.length(func.cast(Annotation.draft, String)) > 2,  # Not empty "[]"
                or_(
                    Annotation.result.is_(None),
                    func.length(func.cast(Annotation.result, String)) <= 2,  # Empty "[]" or null
                ),
            )
            .order_by(order_clause)
            .first()
        )

        # Build skip exclusion queries based on skip_queue setting
        skip_queue = getattr(project, 'skip_queue', 'requeue_for_others')
        my_skips_query = None
        any_skips_query = None

        if skip_queue != 'requeue_for_me':
            my_skips_query = db.query(SkippedTask.task_id).filter(
                SkippedTask.project_id == project_id,
                SkippedTask.skipped_by == current_user.id,
            )

        if skip_queue == 'ignore_skipped':
            any_skips_query = db.query(SkippedTask.task_id).filter(
                SkippedTask.project_id == project_id,
            )

        if task_with_draft:
            # Return the task with draft to continue where user left off
            next_task = task_with_draft
        else:
            # No draft found, find any task the user hasn't annotated yet
            unannotated_query = (
                db.query(Task)
                .filter(Task.project_id == project_id)
                .outerjoin(
                    Annotation,
                    and_(
                        Annotation.task_id == Task.id,
                        Annotation.completed_by == current_user.id,
                    ),
                )
                .filter(Annotation.id == None)  # User hasn't annotated this task  # noqa: E711
            )

            # Apply skip exclusions
            if my_skips_query is not None:
                unannotated_query = unannotated_query.filter(Task.id.notin_(my_skips_query))
            if any_skips_query is not None:
                unannotated_query = unannotated_query.filter(Task.id.notin_(any_skips_query))

            next_task = unannotated_query.order_by(order_clause).first()

    if not next_task:
        return {"detail": "No more tasks to label", "task": None}

    # Calculate user-specific completion metrics
    total_tasks = db.query(Task).filter(Task.project_id == project_id).count()

    # Count tasks completed by current user
    user_completed_tasks = (
        db.query(Task)
        .join(Annotation, Annotation.task_id == Task.id)
        .filter(Task.project_id == project_id, Annotation.completed_by == current_user.id)
        .count()
    )

    # Count tasks remaining for current user (tasks they haven't annotated)
    remaining_tasks = (
        db.query(Task)
        .filter(Task.project_id == project_id)
        .outerjoin(
            Annotation,
            and_(
                Annotation.task_id == Task.id,
                Annotation.completed_by == current_user.id,
            ),
        )
        .filter(Annotation.id == None)  # noqa: E711
        .count()
    )

    current_position = user_completed_tasks + 1  # Position of current task (1-indexed)

    # Serialize task to dict (ORM objects don't auto-serialize in plain dicts)
    total_generations = (
        db.query(func.count(Generation.id))
        .filter(Generation.task_id == next_task.id)
        .scalar() or 0
    )
    task_dict = {
        "id": next_task.id,
        "inner_id": next_task.inner_id,
        "data": next_task.data,
        "meta": next_task.meta,
        "created_at": next_task.created_at,
        "updated_at": next_task.updated_at,
        "is_labeled": next_task.is_labeled,
        "total_annotations": next_task.total_annotations,
        "cancelled_annotations": next_task.cancelled_annotations,
        "total_generations": total_generations,
        "project_id": next_task.project_id,
    }

    return {
        "task": task_dict,
        "project_id": project_id,
        "remaining": remaining_tasks,
        "current_position": current_position,
        "total_tasks": total_tasks,
        "user_completed_tasks": user_completed_tasks,  # New field for user-specific tracking
    }


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get specific task details"""

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

    # Get generation count for this task
    total_generations = (
        db.query(func.count(Generation.id)).filter(Generation.task_id == task_id).scalar() or 0
    )

    # Return full task with meta field (Label Studio aligned)
    task_dict = {
        "id": task.id,
        "data": task.data,
        "meta": task.meta,  # Full metadata, not just tags
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "is_labeled": task.is_labeled,
        "total_annotations": task.total_annotations,
        "cancelled_annotations": task.cancelled_annotations,
        "total_generations": total_generations,
        "project_id": task.project_id,
        "inner_id": task.inner_id,
        "comment_count": task.comment_count,
        "unresolved_comment_count": task.unresolved_comment_count,
        "last_comment_updated_at": task.last_comment_updated_at,
        "comment_authors": task.comment_authors,
        "file_upload_id": task.file_upload_id,
        "created_by": task.created_by,
        "updated_by": task.updated_by,
        # Keep tags for backward compatibility temporarily
        "tags": task.meta.get("tags", []) if task.meta else [],
    }

    return task_dict


@router.patch("/tasks/{task_id}/metadata")
async def update_task_metadata(
    task_id: str,
    metadata: dict,
    request: Request,
    merge: bool = Query(True, description="Merge with existing metadata or replace"),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Update task metadata (Label Studio aligned approach)

    This is the simplified way to update any metadata including tags.
    If merge=True (default), merges with existing metadata.
    If merge=False, replaces all metadata.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, task.project_id, org_context):
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
    db.commit()
    db.refresh(task)

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
    db: Session = Depends(get_db),
):
    """
    Update metadata for multiple tasks (Label Studio aligned approach)

    This replaces the complex bulk-tag and bulk-untag endpoints.
    """
    tasks = db.query(Task).filter(Task.id.in_(task_ids)).all()

    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found")

    # Check access for all tasks' projects
    org_context = get_org_context_from_request(request)
    checked_projects = set()
    for task in tasks:
        if task.project_id not in checked_projects:
            if not check_project_accessible(db, current_user, task.project_id, org_context):
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

    db.commit()

    return {
        "updated_count": updated_count,
        "task_ids": task_ids,
        "metadata": metadata,
        "message": f"Updated metadata for {updated_count} tasks",
    }


@router.put("/{project_id}/tasks/{task_id}")
async def update_task_data(
    project_id: str,
    task_id: str,
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Update task data - Superadmin only

    Request body:
    {
        "data": {
            "field_name": "new_value",
            ...
        }
    }

    This endpoint allows superadmins to edit individual task data fields.
    It maintains an audit log of all changes.
    """
    from datetime import datetime

    # Check if user is superadmin
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can edit task data")

    # Verify project exists and user has access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify task exists and belongs to the project
    task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()

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
        db.commit()
        db.refresh(task)

        # Calculate generation count from Generation table
        total_generations = (
            db.query(func.count(Generation.id)).filter(Generation.task_id == task_id).scalar() or 0
        )

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
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update task data: {str(e)}")


@router.post("/{project_id}/tasks/bulk-delete")
async def bulk_delete_tasks(
    project_id: str,
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk delete tasks in a project"""

    task_ids = data.get("task_ids", [])

    # Verify project exists and user has access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check permission - creator, superadmin, org admin, or contributor
    if not check_user_can_edit_project(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Permission denied")

    deleted_count = 0

    for task_id in task_ids:
        # Delete annotations first
        # NOTE: Annotation table doesn't exist yet - skipping deletion
        # db.query(Annotation).filter(Annotation.task_id == task_id).delete()
        pass

        # Delete task
        result = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).delete()

        if result > 0:
            deleted_count += 1

    # task_count is a response-time computed field (see calculate_project_stats),
    # not a stored Project column. The previous `project.task_count = …` write
    # here was a dead store on the SQLAlchemy instance — removed.

    db.commit()

    # Update report data section (silent failure to not block deletion)
    try:
        import logging

        from report_service import update_report_data_section

        logger = logging.getLogger(__name__)
        update_report_data_section(db, project_id)
        logger.info(f"Updated report data section for project {project_id}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update report data section: {e}")

    return {"deleted": deleted_count}


@router.post("/{project_id}/tasks/bulk-export")
def bulk_export_tasks(
    project_id: str,
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk export tasks from a project.

    Streams the response chunk-by-chunk and uses `yield_per` on the heavy
    queries so peak memory stays bounded regardless of project size.
    Previously the handler loaded every task / annotation / generation /
    evaluation row into Python with `.all()`, built one nested dict, and
    `json.dumps(...)`-ed it with `indent=2` — that OOMKilled the API pod on
    2026-05-18 when a 581-task / 8k-generation / 57k-eval project was
    exported (1.5 GiB container limit).

    Also `def` (not `async def`) so FastAPI runs it in the threadpool — the
    sync DB iteration no longer blocks the event loop during the export.
    """
    task_ids = data.get("task_ids", [])
    format = data.get("format", "json")

    if format not in ("json", "csv", "tsv"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    # Project + access check up front (still uses the request-scoped session;
    # closes naturally when the threadpool worker returns).
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Capture scalars now — we'll reference them inside the generator after
    # the closure has been handed off to StreamingResponse.
    project_title = project.title
    exported_at_iso = datetime.now().isoformat()
    filename_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    from routers.projects._export_stream import (
        BATCH_SIZE as _BATCH_SIZE,
        build_batch_objs as _build_batch_objs_shared,
        stream_export_json,
    )
    from routers.projects.serializers import build_judge_model_lookup

    # Local closure over `db` so the CSV/TSV path below can keep its
    # existing 2-arg call signature.
    def _build_batch_objs(batch, eval_run_by_id, judge_model_lookup):
        return _build_batch_objs_shared(db, batch, eval_run_by_id, judge_model_lookup)

    # The streaming generators below capture the request-scoped `db` via
    # closure. FastAPI keeps the Depends(get_db) session open until the
    # response body is fully consumed (i.e. until the generator returns),
    # so iterating `yield_per` against it is safe. The per-iteration-session
    # pattern that fixes the WS/SSE leaks does NOT apply here: exports are
    # short-lived and continuously query the DB, not idle in transaction.

    def _json_stream():
        yield from stream_export_json(
            db,
            project_id,
            task_ids,
            header_fields={
                "project_id": project_id,
                "project_title": project_title,
                "exported_at": exported_at_iso,
            },
        )

    def _csv_or_tsv_stream(delimiter: str):
        """Stream CSV/TSV one task at a time. Each row is `task_id, task_data,
        is_labeled, annotation_count, generation_count, evaluation_count, created_at`
        (matches the legacy shape)."""
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=delimiter)
        writer.writerow([
            "task_id", "task_data", "is_labeled",
            "annotation_count", "generation_count", "evaluation_count",
            "created_at",
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()

        eval_runs = db.query(EvaluationRun).filter(
            EvaluationRun.project_id == project_id
        ).all()
        eval_run_by_id = {er.id: er for er in eval_runs}
        judge_model_lookup = build_judge_model_lookup(eval_runs, db)

        task_q = db.query(Task).filter(
            Task.id.in_(task_ids), Task.project_id == project_id
        )

        def _write_obj(obj):
            writer.writerow([
                obj["id"],
                json.dumps(obj["data"]),
                obj["is_labeled"],
                len(obj["annotations"]),
                len(obj["generations"]),
                len(obj["evaluations"]),
                obj["created_at"],
            ])
            chunk = buf.getvalue()
            buf.seek(0)
            buf.truncate()
            return chunk

        batch: list = []
        for task in task_q.yield_per(_BATCH_SIZE):
            batch.append(task)
            if len(batch) >= _BATCH_SIZE:
                for obj in _build_batch_objs(batch, eval_run_by_id, judge_model_lookup):
                    yield _write_obj(obj)
                batch = []
        for obj in _build_batch_objs(batch, eval_run_by_id, judge_model_lookup):
            yield _write_obj(obj)

    from fastapi.responses import StreamingResponse

    if format == "json":
        gen, media_type, ext = _json_stream(), "application/json", "json"
    elif format == "csv":
        gen, media_type, ext = _csv_or_tsv_stream(","), "text/csv", "csv"
    else:  # tsv
        gen, media_type, ext = _csv_or_tsv_stream("\t"), "text/tab-separated-values", "tsv"

    filename = f"tasks_export_{project_id}_{filename_ts}.{ext}"
    return StreamingResponse(
        gen,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{project_id}/tasks/bulk-archive")
async def bulk_archive_tasks(
    project_id: str,
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk archive tasks in a project"""

    task_ids = data.get("task_ids", [])

    # Verify project exists and user has access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check permission
    if project.created_by != current_user.id and not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Permission denied")

    archived_count = 0

    for task_id in task_ids:
        task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()

        if task:
            # Mark task as archived (add is_archived field if not exists)
            task.meta = task.meta or {}
            task.meta["is_archived"] = True
            archived_count += 1

    db.commit()

    return {"archived": archived_count}


@router.post("/{project_id}/tasks/{task_id}/skip", response_model=SkipTaskResponse)
async def skip_task(
    project_id: str,
    task_id: str,
    skip_request: SkipTaskRequest,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Skip a task with optional comment

    If project has require_comment_on_skip=True, comment must be provided
    Creates a skip record in the database to track skipped tasks
    """

    # Verify task exists and belongs to project
    task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get project to check require_comment_on_skip setting
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Enforce task assignment in manual/auto mode (Label Studio aligned: task is invisible)
    if not check_task_assigned_to_user(db, current_user, task_id, project):
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
    db.commit()
    db.refresh(skip_record)

    return skip_record


# Sensitive fields that should not be exposed for field mapping
SENSITIVE_FIELD_PATTERNS = {
    "annotations",
    "annotation",
    "reference_answer",
    "reference",
    "ground_truth",
    "correct_answer",
    "expected_output",
    "label",
    "labels",
    "gold_standard",
}


def extract_fields_from_data(data: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
    """
    Recursively extract field paths from task data.

    Args:
        data: Task data dictionary
        prefix: Current path prefix for nested fields

    Returns:
        List of field info dictionaries
    """
    fields = []

    if not isinstance(data, dict):
        return fields

    for key, value in data.items():
        # Skip sensitive fields
        if key.lower() in SENSITIVE_FIELD_PATTERNS:
            continue

        full_path = f"${prefix}.{key}" if prefix else f"${key}"
        display_name = key.replace("_", " ").title()

        # Determine data type and sample value
        if isinstance(value, str):
            data_type = "string"
            sample = value[:100] + "..." if len(value) > 100 else value
        elif isinstance(value, dict):
            data_type = "object"
            sample = "{...}"
            # Recursively extract nested fields
            nested_prefix = f"{prefix}.{key}" if prefix else key
            nested_fields = extract_fields_from_data(value, nested_prefix)
            fields.extend(nested_fields)
        elif isinstance(value, list):
            data_type = "array"
            sample = f"[{len(value)} items]"
        elif isinstance(value, (int, float)):
            data_type = "number"
            sample = str(value)
        elif isinstance(value, bool):
            data_type = "boolean"
            sample = str(value)
        else:
            data_type = "unknown"
            sample = str(value)[:50] if value else None

        fields.append(
            {
                "path": full_path,
                "display_name": display_name,
                "sample_value": sample,
                "data_type": data_type,
                "is_nested": bool(prefix),
            }
        )

    return fields


@router.get("/{project_id}/task-fields")
async def get_task_data_fields(
    project_id: str,
    request: Request,
    sample_count: int = Query(default=5, ge=1, le=20),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Discover available fields from task data for field mapping.

    Scans sample tasks in the project to find all available field names,
    including nested fields (e.g., $context.jurisdiction, $prompts.prompt_clean).

    Filters out sensitive fields like ground_truth, annotations, etc.

    Reusable endpoint for:
    - LLM Judge field mapping
    - Generation prompt structures
    - Annotation configuration (reference panel)

    Args:
        project_id: Project to scan
        sample_count: Number of tasks to sample (default 5, max 20)

    Returns:
        TaskFieldsResponse with discovered fields and sample data
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get sample tasks
    tasks = db.query(Task).filter(Task.project_id == project_id).limit(sample_count).all()

    if not tasks:
        return {
            "project_id": project_id,
            "fields": [],
            "sample_task_count": 0,
        }

    # Aggregate fields from all sample tasks
    all_fields: Dict[str, Dict[str, Any]] = {}

    for task in tasks:
        if not task.data:
            continue

        task_fields = extract_fields_from_data(task.data)

        for field in task_fields:
            # Keep first sample value encountered
            if field["path"] not in all_fields:
                all_fields[field["path"]] = field

    # Sort fields: top-level first, then nested, alphabetically within each group
    sorted_fields = sorted(all_fields.values(), key=lambda f: (f["is_nested"], f["path"]))

    return {
        "project_id": project_id,
        "fields": sorted_fields,
        "sample_task_count": len(tasks),
    }
