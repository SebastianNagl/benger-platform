"""Read endpoints: list project tasks, next task, single task."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)
from routers.projects.deps import ProjectAccess, require_project_access


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
    db: AsyncSession = Depends(get_async_db),
    access: ProjectAccess = Depends(require_project_access()),
):
    """
    List tasks in a project with role-based visibility

    Role-based access:
    - Superadmin/Admin: See all tasks
    - Contributor/Manager: See all tasks in their projects
    - Annotator: Only see tasks assigned to them (if assignment_mode is 'manual' or 'auto')
    """

    # Project existence + read access enforced by require_project_access
    # (404 "Project not found" / 403 "Access denied"). The loaded project is
    # reused below for assignment_mode / randomize_task_order / etc.
    project = access.project

    # Check user's role and apply visibility rules
    user_with_memberships = await get_user_with_memberships_async(db, current_user.id)

    # Determine user's role in the organization
    user_role = None
    if current_user.is_superadmin:
        user_role = "superadmin"
    elif user_with_memberships and user_with_memberships.organization_memberships:
        # Get project organizations
        org_rows = (
            await db.execute(
                select(ProjectOrganization.organization_id).where(
                    ProjectOrganization.project_id == project_id
                )
            )
        ).all()
        project_org_ids = [org_id[0] for org_id in org_rows]

        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    query = select(Task).where(Task.project_id == project_id)

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
        query = query.where(Task.is_labeled == True)  # noqa: E712
    elif only_unlabeled:
        query = query.where(Task.is_labeled == False)  # noqa: E712

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
        ).where(Annotation.id == None)  # noqa: E711

    # Exclude skipped tasks based on skip_queue setting
    skip_queue = getattr(project, 'skip_queue', 'requeue_for_others')
    if exclude_my_annotations and skip_queue != 'requeue_for_me':
        # Exclude tasks this user has skipped (requeue_for_others or ignore_skipped)
        my_skips = select(SkippedTask.task_id).where(
            SkippedTask.project_id == project_id,
            SkippedTask.skipped_by == current_user.id,
        )
        query = query.where(Task.id.notin_(my_skips))

    if skip_queue == 'ignore_skipped':
        # Exclude tasks that ANY user has skipped
        any_skips = select(SkippedTask.task_id).where(
            SkippedTask.project_id == project_id,
        )
        query = query.where(Task.id.notin_(any_skips))

    # Server-side search across the task's JSON payload + id. Mirrors the
    # client-side filter that AnnotationTab used to apply after loading every
    # task into memory.
    if search:
        escaped = search.replace('%', r'\%').replace('_', r'\_')
        like = f"%{escaped}%"
        query = query.where(
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
        query = query.where(Task.created_at >= start_dt)
    if end_dt is not None:
        query = query.where(Task.created_at <= end_dt)

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
                select(
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

    # Get total count before pagination. Count over the filtered query as a
    # subquery (ordering stripped — irrelevant to the count and disallowed in
    # some scalar contexts) so all joins/filters above are preserved.
    count_stmt = select(func.count()).select_from(
        query.order_by(None).subquery()
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    # `ids_only` short-circuit — used by the data tab's "select all matching"
    # bulk-operation flow. Skip the pagination, generation-counts, and
    # assignment-enrichment work below and just return the filtered IDs.
    # `ids_limit` caps the response so a 100k-task project can't blow up
    # the client.
    if ids_only:
        id_rows = (
            await db.execute(query.with_only_columns(Task.id).limit(ids_limit))
        ).all()
        return {
            "ids": [tid for (tid,) in id_rows],
            "total": total,
            "truncated": total > ids_limit,
        }

    # Pagination
    tasks = (
        await db.execute(
            query.offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()

    task_ids = [task.id for task in tasks]

    # Per-task generation counts + the distinct model ids that produced them.
    # The model list drives the per-task "all generations" modal (one tab per
    # model); the count stays the total Generation row count so the two agree.
    generation_counts: Dict[str, int] = {}
    generation_models_by_task: Dict[str, List[str]] = {tid: [] for tid in task_ids}
    if task_ids:
        gen_counts = (
            await db.execute(
                select(Generation.task_id, func.count(Generation.id))
                .where(Generation.task_id.in_(task_ids))
                .group_by(Generation.task_id)
            )
        ).all()
        generation_counts = {task_id: count for task_id, count in gen_counts}

        gen_model_rows = (
            await db.execute(
                select(Generation.task_id, Generation.model_id)
                .where(
                    Generation.task_id.in_(task_ids),
                    Generation.model_id.isnot(None),
                )
                .distinct()
            )
        ).all()
        for tid, mid in gen_model_rows:
            if mid and mid not in generation_models_by_task.setdefault(tid, []):
                generation_models_by_task[tid].append(mid)

    # Bulk-fetch all assignments for the page + the users they reference. Two
    # IN queries replace the previous per-task and per-assignment lookups
    # (which scaled as page_size + page_size × ~5 assignees per task).
    assignments_by_task: Dict[str, List[TaskAssignment]] = {tid: [] for tid in task_ids}
    users_by_id: Dict[str, User] = {}
    # Distinct people who actually DID work on each task, kept separate from
    # assignments because they live on different structures: annotators =
    # who submitted an annotation (Annotation.completed_by); reviewers = who
    # reviewed one (Annotation.reviewed_by, set post-hoc by the review
    # workflow). Graders (Korrektur) stay inside `assignments` and are split
    # out client-side via the assignment `target_type`.
    annotators_by_task: Dict[str, List[str]] = {tid: [] for tid in task_ids}
    reviewers_by_task: Dict[str, List[str]] = {tid: [] for tid in task_ids}
    if task_ids:
        page_assignments = (
            await db.execute(
                select(TaskAssignment).where(TaskAssignment.task_id.in_(task_ids))
            )
        ).scalars().all()
        for assn in page_assignments:
            assignments_by_task.setdefault(assn.task_id, []).append(assn)

        annotator_rows = (
            await db.execute(
                select(Annotation.task_id, Annotation.completed_by)
                .where(
                    Annotation.task_id.in_(task_ids),
                    Annotation.completed_by.isnot(None),
                    Annotation.was_cancelled == False,  # noqa: E712
                    Annotation.result.isnot(None),
                    func.cast(Annotation.result, String) != "[]",
                )
                .distinct()
            )
        ).all()
        for tid, uid in annotator_rows:
            if uid and uid not in annotators_by_task.setdefault(tid, []):
                annotators_by_task[tid].append(uid)

        reviewer_rows = (
            await db.execute(
                select(Annotation.task_id, Annotation.reviewed_by)
                .where(
                    Annotation.task_id.in_(task_ids),
                    Annotation.reviewed_by.isnot(None),
                )
                .distinct()
            )
        ).all()
        for tid, uid in reviewer_rows:
            if uid and uid not in reviewers_by_task.setdefault(tid, []):
                reviewers_by_task[tid].append(uid)

        user_ids = {a.user_id for a in page_assignments if a.user_id}
        user_ids |= {uid for uids in annotators_by_task.values() for uid in uids}
        user_ids |= {uid for uids in reviewers_by_task.values() for uid in uids}
        if user_ids:
            user_rows = (
                await db.execute(select(User).where(User.id.in_(user_ids)))
            ).scalars().all()
            users_by_id = {u.id: u for u in user_rows}

    def _people(uids: List[str]) -> List[Dict[str, str]]:
        """Resolve a list of user ids to lightweight {id, name} dicts,
        skipping ids whose User row wasn't fetched (e.g. deleted user)."""
        people = []
        for uid in uids:
            resolved = users_by_id.get(uid)
            if resolved is not None:
                people.append({"id": uid, "name": resolved.name})
        return people

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
            "generation_models": generation_models_by_task.get(task.id, []),
            "project_id": task.project_id,
            "llm_responses": getattr(task, "llm_responses", None),
            "llm_evaluations": getattr(task, "llm_evaluations", None),
            "assignments": [],
            # Who actually annotated / reviewed this task (distinct from the
            # assignment list above). Annotators come from completed_by,
            # reviewers from reviewed_by; both are [{id, name}].
            "annotators": _people(annotators_by_task.get(task.id, [])),
            "reviewers": _people(reviewers_by_task.get(task.id, [])),
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
                    # 'task' = annotator assignment; 'annotation'/'generation'
                    # = item-level Korrektur grader assignment. The client
                    # splits the "Assigned To" and "Graders" columns on this.
                    "target_type": getattr(assignment, "target_type", "task")
                    or "task",
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
    db: AsyncSession = Depends(get_async_db),
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
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        return {"detail": "Project not found", "task": None}

    org_context = get_org_context_from_request(request)
    if not await check_project_accessible_async(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Find next task based on assignment mode
    if project.assignment_mode == "manual":
        # Manual mode: only return pre-assigned tasks
        assignment = (
            await db.execute(
                select(TaskAssignment)
                .join(Task)
                .where(
                    Task.project_id == project_id,
                    TaskAssignment.user_id == current_user.id,
                    TaskAssignment.status.in_(["assigned", "in_progress"]),
                )
                .order_by(
                    TaskAssignment.priority.desc(),
                    TaskAssignment.due_date.asc().nullsfirst(),
                    Task.created_at,
                )
            )
        ).scalars().first()

        if not assignment:
            return {"detail": "No more assigned tasks", "task": None}

        next_task = (
            await db.execute(select(Task).where(Task.id == assignment.task_id))
        ).scalar_one_or_none()

        # Update assignment status to in_progress if it was assigned
        if assignment.status == "assigned":
            assignment.status = "in_progress"
            assignment.started_at = datetime.now()
            await db.commit()

    elif project.assignment_mode == "auto":
        # Auto mode (pull model): resume existing assignment or auto-assign on demand

        # Phase 1: Check for existing active assignment (resume in-progress work)
        # Exclude tasks the user has skipped (skip creates SkippedTask but
        # doesn't cancel the assignment, so we filter here)
        user_skipped_tasks = select(SkippedTask.task_id).where(
            SkippedTask.project_id == project_id,
            SkippedTask.skipped_by == current_user.id,
        )
        assignment = (
            await db.execute(
                select(TaskAssignment)
                .join(Task)
                .where(
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
            )
        ).scalars().first()

        if assignment:
            next_task = (
                await db.execute(select(Task).where(Task.id == assignment.task_id))
            ).scalar_one_or_none()
            if assignment.status == "assigned":
                assignment.status = "in_progress"
                assignment.started_at = datetime.now()
                await db.commit()
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
                my_skips_query = select(SkippedTask.task_id).where(
                    SkippedTask.project_id == project_id,
                    SkippedTask.skipped_by == current_user.id,
                )

            if skip_queue == 'ignore_skipped':
                any_skips_query = select(SkippedTask.task_id).where(
                    SkippedTask.project_id == project_id,
                )

            # Find candidate task: not annotated by this user
            # Use NOT IN subquery instead of outerjoin (FOR UPDATE requires no outer joins)
            user_annotated_tasks = select(Annotation.task_id).where(
                Annotation.completed_by == current_user.id,
                Annotation.task_id.in_(
                    select(Task.id).where(Task.project_id == project_id)
                ),
            )

            candidate_query = (
                select(Task)
                .where(
                    Task.project_id == project_id,
                    Task.id.notin_(user_annotated_tasks),
                )
            )

            # Enforce maximum_annotations: exclude tasks at the limit
            if project.maximum_annotations > 0:
                # Exclude tasks with enough completed non-cancelled annotations
                fully_annotated = (
                    select(Annotation.task_id)
                    .where(
                        Annotation.project_id == project_id,
                        Annotation.was_cancelled == False,  # noqa: E712
                        Annotation.result != None,  # noqa: E711
                        func.length(func.cast(Annotation.result, String)) > 2,
                    )
                    .group_by(Annotation.task_id)
                    .having(func.count(Annotation.id) >= project.maximum_annotations)
                )
                candidate_query = candidate_query.where(
                    Task.id.notin_(fully_annotated)
                )

                # Also exclude tasks with enough active assignments (reserved slots)
                # Prevents wasteful double-assignment when users request /next sequentially
                tasks_at_max_assignments = (
                    select(TaskAssignment.task_id)
                    .join(Task)
                    .where(
                        Task.project_id == project_id,
                        TaskAssignment.status.in_(["assigned", "in_progress"]),
                    )
                    .group_by(TaskAssignment.task_id)
                    .having(func.count(TaskAssignment.id) >= project.maximum_annotations)
                )
                candidate_query = candidate_query.where(
                    Task.id.notin_(tasks_at_max_assignments)
                )

            # Apply skip exclusions
            if my_skips_query is not None:
                candidate_query = candidate_query.where(Task.id.notin_(my_skips_query))
            if any_skips_query is not None:
                candidate_query = candidate_query.where(Task.id.notin_(any_skips_query))

            # Concurrency-safe: SELECT FOR UPDATE SKIP LOCKED
            # If another transaction locks a row, skip it and take the next one
            candidate_task = (
                await db.execute(
                    candidate_query
                    .order_by(order_clause)
                    .with_for_update(skip_locked=True)
                )
            ).scalars().first()

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
                await db.commit()
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
            await db.execute(
                select(Task)
                .join(Annotation, Annotation.task_id == Task.id)
                .where(
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
            )
        ).scalars().first()

        # Build skip exclusion queries based on skip_queue setting
        skip_queue = getattr(project, 'skip_queue', 'requeue_for_others')
        my_skips_query = None
        any_skips_query = None

        if skip_queue != 'requeue_for_me':
            my_skips_query = select(SkippedTask.task_id).where(
                SkippedTask.project_id == project_id,
                SkippedTask.skipped_by == current_user.id,
            )

        if skip_queue == 'ignore_skipped':
            any_skips_query = select(SkippedTask.task_id).where(
                SkippedTask.project_id == project_id,
            )

        if task_with_draft:
            # Return the task with draft to continue where user left off
            next_task = task_with_draft
        else:
            # No draft found, find any task the user hasn't annotated yet
            unannotated_query = (
                select(Task)
                .where(Task.project_id == project_id)
                .outerjoin(
                    Annotation,
                    and_(
                        Annotation.task_id == Task.id,
                        Annotation.completed_by == current_user.id,
                    ),
                )
                .where(Annotation.id == None)  # User hasn't annotated this task  # noqa: E711
            )

            # Apply skip exclusions
            if my_skips_query is not None:
                unannotated_query = unannotated_query.where(Task.id.notin_(my_skips_query))
            if any_skips_query is not None:
                unannotated_query = unannotated_query.where(Task.id.notin_(any_skips_query))

            next_task = (
                await db.execute(unannotated_query.order_by(order_clause))
            ).scalars().first()

    if not next_task:
        return {"detail": "No more tasks to label", "task": None}

    # Calculate user-specific completion metrics
    total_tasks = (
        await db.execute(
            select(func.count()).select_from(Task).where(Task.project_id == project_id)
        )
    ).scalar() or 0

    # Count tasks completed by current user. Mirrors the original
    # join-then-count (counts Task×Annotation rows, not distinct tasks).
    user_completed_tasks = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .join(Annotation, Annotation.task_id == Task.id)
            .where(
                Task.project_id == project_id,
                Annotation.completed_by == current_user.id,
            )
        )
    ).scalar() or 0

    # Count tasks remaining for current user (tasks they haven't annotated)
    remaining_tasks = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .outerjoin(
                Annotation,
                and_(
                    Annotation.task_id == Task.id,
                    Annotation.completed_by == current_user.id,
                ),
            )
            .where(
                Task.project_id == project_id,
                Annotation.id == None,  # noqa: E711
            )
        )
    ).scalar() or 0

    current_position = user_completed_tasks + 1  # Position of current task (1-indexed)

    # Serialize task to dict (ORM objects don't auto-serialize in plain dicts)
    total_generations = (
        await db.execute(
            select(func.count(Generation.id)).where(Generation.task_id == next_task.id)
        )
    ).scalar() or 0
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
    db: AsyncSession = Depends(get_async_db),
):
    """Get specific task details"""

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

    # Enforce task assignment in manual/auto mode (Label Studio aligned: task is invisible)
    project = (
        await db.execute(select(Project).where(Project.id == task.project_id))
    ).scalar_one_or_none()
    if project and not await check_task_assigned_to_user_async(
        db, current_user, task_id, project
    ):
        raise HTTPException(status_code=404, detail="Task not found")

    # Get generation count for this task
    total_generations = (
        await db.execute(
            select(func.count(Generation.id)).where(Generation.task_id == task_id)
        )
    ).scalar() or 0

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
