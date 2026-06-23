"""
Shared helper functions for projects API.

These functions provide common operations used across multiple project endpoints.
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from sqlalchemy import case, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload

from models import (
    EvaluationRun,
    Generation,
    OrganizationMembership,
    OrganizationRole,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
    TaskAssignment,
)
from project_schemas import ProjectResponse


# Re-export the noise filter from /shared. Single source of truth lives in
# metric_filters so the API, the worker, and the aggregate-summaries
# refresh job agree on what counts as a "real" metric — historically the
# worker couldn't import this module at all, so the live and precomputed
# paths could silently disagree. See services/shared/metric_filters.py.
from metric_filters import (  # noqa: F401 — re-exported for legacy callers
    _METRIC_EXCLUDED_KEYS,
    _METRIC_NOISE_SUFFIXES,
    _metric_key_is_real,
)


def _scored_pairs_query(db: Session):
    """Base query that yields (project_id, subject_id, metric_key) for every
    (annotation|generation, metric) pair that has at least one scored row in a
    completed evaluation run. Caller adds project filters + DISTINCT."""
    subject_expr = func.coalesce(
        TaskEvaluation.annotation_id, TaskEvaluation.generation_id
    )
    metrics_jsonb = cast(TaskEvaluation.metrics, JSONB)
    return (
        db.query(
            EvaluationRun.project_id,
            subject_expr.label("subject_id"),
            func.jsonb_object_keys(metrics_jsonb).label("metric_key"),
        )
        .select_from(TaskEvaluation)
        .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
        .filter(
            EvaluationRun.status == "completed",
            subject_expr.isnot(None),
            TaskEvaluation.metrics.isnot(None),
            func.jsonb_typeof(metrics_jsonb) == "object",
        )
    )


def _async_scored_pairs_select():
    """select()-based twin of :func:`_scored_pairs_query` for the async lane.

    Yields (project_id, subject_id, metric_key) for every (subject, metric)
    pair with a scored row in a completed run. Caller adds project filters +
    ``.distinct()`` exactly like the sync builder.
    """
    subject_expr = func.coalesce(
        TaskEvaluation.annotation_id, TaskEvaluation.generation_id
    )
    metrics_jsonb = cast(TaskEvaluation.metrics, JSONB)
    return (
        select(
            EvaluationRun.project_id,
            subject_expr.label("subject_id"),
            func.jsonb_object_keys(metrics_jsonb).label("metric_key"),
        )
        .select_from(TaskEvaluation)
        .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
        .where(
            EvaluationRun.status == "completed",
            subject_expr.isnot(None),
            TaskEvaluation.metrics.isnot(None),
            func.jsonb_typeof(metrics_jsonb) == "object",
        )
    )


def _generation_models_count(project: Project) -> int:
    selected = (project.generation_config or {}).get("selected_configuration") or {}
    models = selected.get("models") or []
    return len(models)


def _evaluation_methods_count(project: Project) -> int:
    """Number of distinct evaluation methods configured on the project.

    Counts entries in evaluation_config.evaluation_configs (new shape, one
    entry per field × method) and falls back to selected_methods (legacy
    per-field map).
    """
    eval_cfg = project.evaluation_config or {}
    new_shape = eval_cfg.get("evaluation_configs") or []
    if new_shape:
        return len(new_shape)
    legacy = eval_cfg.get("selected_methods") or {}
    return len(legacy)


def _mix_progress(parts: List[tuple]) -> float:
    """parts = [(completed, expected), ...] across stages. Stages with
    expected == 0 are ignored so the bar isn't permanently stuck at 0 when
    a stage is enabled but hasn't been configured yet."""
    relevant = [(c, e) for (c, e) in parts if e > 0]
    if not relevant:
        return 0.0
    completed_sum = sum(c for c, _ in relevant)
    expected_sum = sum(e for _, e in relevant)
    return min(100.0, (completed_sum / expected_sum) * 100)


def _progress_parts(
    project: Optional[Project],
    response: ProjectResponse,
    completed_generations: int,
) -> List[tuple]:
    """Per-stage (completed, expected) tuples gated on enable_* flags.

    Stages with expected == 0 (e.g. evaluation enabled but no eval methods
    configured yet) are still returned; _mix_progress skips them so the
    progress bar isn't pinned at 0 forever for half-configured projects.
    """
    if project is None:
        return []

    parts: List[tuple] = []

    if getattr(project, "enable_annotation", True):
        parts.append((response.completed_tasks_count, response.task_count))

    gen_models = _generation_models_count(project)
    if getattr(project, "enable_generation", True):
        # One ResponseGeneration is expected per (task × configured model).
        parts.append((completed_generations, response.task_count * gen_models))

    if getattr(project, "enable_evaluation", True):
        # One EvaluationRun is expected per (configured model × configured
        # eval method). Cap the completed count at expected so a
        # mis-tracked re-run can't push progress over 100 %.
        eval_methods = _evaluation_methods_count(project)
        expected_eval = gen_models * eval_methods
        completed_eval = (
            min(response.evaluations_completed_count, expected_eval)
            if expected_eval > 0
            else 0
        )
        parts.append((completed_eval, expected_eval))

    return parts


def apply_mixed_progress(
    project: Project,
    response: ProjectResponse,
    completed_generations: int,
) -> None:
    """Set response.progress_percentage to the per-stage mix gated on enable_* flags.

    Shared by `calculate_project_stats` (single-project path) and the
    batch path in list_projects so both produce identical numbers.
    """
    response.progress_percentage = _mix_progress(
        _progress_parts(project, response, completed_generations)
    )


def calculate_project_stats(
    db: Session,
    project_id: str,
    response: ProjectResponse,
    project: Optional[Project] = None,
) -> None:
    """Calculate and set project statistics on a response object.

    Progress is a weighted mix across the enable_annotation / enable_generation
    / enable_evaluation stages: sum(completed) / sum(expected) across stages
    that are both enabled and have nonzero expected work. A project with only
    annotation enabled (the historical default) behaves identically to before.

    NOTE: For batch operations (e.g., list_projects), use calculate_project_stats_batch
    instead to avoid N+1 query problem.
    """

    if project is None:
        project = db.query(Project).filter(Project.id == project_id).first()

    response.task_count = db.query(Task).filter(Task.project_id == project_id).count()
    # Count annotations that aren't cancelled
    response.annotation_count = (
        db.query(Annotation)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)  # noqa: E712
        .count()
    )
    response.completed_tasks_count = (
        db.query(Task).filter(Task.project_id == project_id, Task.is_labeled == True).count()  # noqa: E712
    )

    # Generation completion (tasks × models) — mirrors the logic in
    # calculate_generation_stats but the count is needed here too so the
    # progress mix has a numerator for the generation stage.
    completed_generations = 0
    gen_models = _generation_models_count(project) if project is not None else 0
    if response.task_count > 0 and gen_models > 0:
        completed_generations = (
            db.query(ResponseGeneration)
            .join(Task, ResponseGeneration.task_id == Task.id)
            .filter(
                Task.project_id == project_id,
                ResponseGeneration.status == "completed",
            )
            .count()
        )

    # Evaluation tallies — count distinct (subject, metric) pairs that have at
    # least one scored row in a completed run. Matches the user's intuition of
    # "how many of my answers have been evaluated on how many metrics"; the old
    # job-count masked partial coverage (a 1-job run scoring 314 of 500
    # subjects looked identical to a fully-scored run).
    #
    # Reads from the precomputed `project_summaries.evaluation_pairs_count`
    # (refreshed by the `recompute_aggregates` Celery task hourly). Falls
    # back to the original live computation when no precomputed row exists —
    # brand-new projects shouldn't render zero before the next refresh.
    from aggregate_summaries import read_project_summary

    summary = read_project_summary(db, project_id, period="overall")
    if summary is not None:
        response.evaluation_count = int(summary.evaluation_pairs_count or 0)
    else:
        pairs = (
            _scored_pairs_query(db)
            .filter(EvaluationRun.project_id == project_id)
            .distinct()
            .all()
        )
        response.evaluation_count = sum(
            1 for _pid, sub_id, mk in pairs if _metric_key_is_real(mk)
        )
    response.evaluations_completed_count = response.evaluation_count

    # Mirror to the legacy aliases so frontends reading either name see the
    # same value (the labeling page reads num_tasks for the "Task X of Y"
    # progress counter).
    response.num_tasks = response.task_count
    response.num_annotations = response.annotation_count

    apply_mixed_progress(project, response, completed_generations)


def _build_select_task_count(project_id: str):
    return select(func.count()).select_from(Task).where(Task.project_id == project_id)


def _build_select_annotation_count(project_id: str):
    return (
        select(func.count())
        .select_from(Annotation)
        .where(
            Annotation.project_id == project_id,
            Annotation.was_cancelled == False,  # noqa: E712
        )
    )


def _build_select_completed_task_count(project_id: str):
    return (
        select(func.count())
        .select_from(Task)
        .where(Task.project_id == project_id, Task.is_labeled == True)  # noqa: E712
    )


def _build_select_completed_generations(project_id: str):
    return (
        select(func.count())
        .select_from(ResponseGeneration)
        .join(Task, ResponseGeneration.task_id == Task.id)
        .where(
            Task.project_id == project_id,
            ResponseGeneration.status == "completed",
        )
    )


def _build_select_project_summary(project_id: str, period: str = "overall"):
    from models import ProjectSummary

    return select(ProjectSummary).where(
        ProjectSummary.project_id == project_id,
        ProjectSummary.period == period,
    )


async def calculate_project_stats_async(
    db: AsyncSession,
    project_id: str,
    response: ProjectResponse,
    project: Optional[Project] = None,
) -> None:
    """Async equivalent of :func:`calculate_project_stats`.

    Mirrors the sync logic exactly: per-stage counts + precomputed-summary
    read with a live fallback for brand-new projects. The summary read is
    inlined (rather than calling ``read_project_summary``) because that
    helper lives in /shared on the sync API.
    """
    if project is None:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()

    response.task_count = (
        await db.execute(_build_select_task_count(project_id))
    ).scalar() or 0
    response.annotation_count = (
        await db.execute(_build_select_annotation_count(project_id))
    ).scalar() or 0
    response.completed_tasks_count = (
        await db.execute(_build_select_completed_task_count(project_id))
    ).scalar() or 0

    completed_generations = 0
    gen_models = _generation_models_count(project) if project is not None else 0
    if response.task_count > 0 and gen_models > 0:
        completed_generations = (
            await db.execute(_build_select_completed_generations(project_id))
        ).scalar() or 0

    summary = (
        await db.execute(_build_select_project_summary(project_id))
    ).scalar_one_or_none()
    if summary is not None:
        response.evaluation_count = int(summary.evaluation_pairs_count or 0)
    else:
        pairs_result = await db.execute(
            _async_scored_pairs_select()
            .where(EvaluationRun.project_id == project_id)
            .distinct()
        )
        response.evaluation_count = sum(
            1 for _pid, sub_id, mk in pairs_result.all() if _metric_key_is_real(mk)
        )
    response.evaluations_completed_count = response.evaluation_count

    response.num_tasks = response.task_count
    response.num_annotations = response.annotation_count

    apply_mixed_progress(project, response, completed_generations)


def calculate_project_stats_batch(db: Session, project_ids: List[str]) -> Dict[str, Dict[str, int]]:
    """Calculate project statistics for multiple projects.

    Reads from the precomputed `project_summaries` table (period='overall',
    refreshed by the `recompute_aggregates` Celery task) so the common case
    is one indexed lookup keyed by `project_id IN (...)`. For brand-new
    projects that don't have a summary row yet (created between beat runs),
    falls back to live aggregation queries scoped to *only* those missing
    ids — the established 99% of the list pays nothing.

    Returns: Dict mapping project_id to stats dict with keys
    `task_count`, `completed_tasks_count`, `annotation_count`,
    `evaluation_count`, `evaluations_completed_count`.
    """
    from models import ProjectSummary
    from sqlalchemy import select as sa_select

    if not project_ids:
        return {}

    # Read all four counters from the precomputed table in one indexed query.
    summary_rows = db.execute(
        sa_select(
            ProjectSummary.project_id,
            ProjectSummary.total_tasks,
            ProjectSummary.labeled_tasks,
            ProjectSummary.annotations_count,
            ProjectSummary.evaluation_pairs_count,
        ).where(
            ProjectSummary.project_id.in_(project_ids),
            ProjectSummary.period == "overall",
        )
    ).all()

    stats_map: Dict[str, Dict[str, int]] = {}
    for pid, total, labeled, ann, eval_pairs in summary_rows:
        stats_map[pid] = {
            'task_count': int(total or 0),
            'completed_tasks_count': int(labeled or 0),
            'annotation_count': int(ann or 0),
            'evaluation_count': int(eval_pairs or 0),
            'evaluations_completed_count': int(eval_pairs or 0),
        }

    missing_summary_ids = [pid for pid in project_ids if pid not in stats_map]
    if missing_summary_ids:
        for pid in missing_summary_ids:
            stats_map[pid] = {
                'task_count': 0,
                'completed_tasks_count': 0,
                'annotation_count': 0,
                'evaluation_count': 0,
                'evaluations_completed_count': 0,
            }

        task_stats = (
            db.query(
                Task.project_id,
                func.count(Task.id).label('task_count'),
                func.sum(case((Task.is_labeled == True, 1), else_=0)).label(  # noqa: E712
                    'completed_tasks_count'
                ),
            )
            .filter(Task.project_id.in_(missing_summary_ids))
            .group_by(Task.project_id)
            .all()
        )
        for stat in task_stats:
            stats_map[stat.project_id]['task_count'] = stat.task_count or 0
            stats_map[stat.project_id]['completed_tasks_count'] = (
                stat.completed_tasks_count or 0
            )

        # Match the worker's filter (services/aggregate_summaries._compute_project_summary)
        # so freshly-created projects display the same number both before and
        # after the next recompute_aggregates cycle.
        annotation_stats = (
            db.query(
                Annotation.project_id, func.count(Annotation.id).label('annotation_count')
            )
            .filter(
                Annotation.project_id.in_(missing_summary_ids),
                Annotation.was_cancelled == False,  # noqa: E712
                Annotation.result != None,  # noqa: E711
                func.jsonb_array_length(Annotation.result) > 0,
            )
            .group_by(Annotation.project_id)
            .all()
        )
        for stat in annotation_stats:
            stats_map[stat.project_id]['annotation_count'] = stat.annotation_count or 0

        live_pairs = (
            _scored_pairs_query(db)
            .filter(EvaluationRun.project_id.in_(missing_summary_ids))
            .distinct()
            .all()
        )
        for pid, _sub_id, metric_key in live_pairs:
            if not _metric_key_is_real(metric_key):
                continue
            stats_map[pid]['evaluation_count'] += 1
            stats_map[pid]['evaluations_completed_count'] += 1

    return stats_map


def calculate_generation_stats(db: Session, project: Project, response: ProjectResponse) -> None:
    """Calculate and set generation-related statistics for the /generation page"""

    # 1. Check if project has generation_config with prompt structures (Issue #762)
    generation_config = project.generation_config or {}
    prompt_structures = generation_config.get("prompt_structures", {})
    response.generation_config_ready = bool(prompt_structures)

    # For backward compatibility, generation_prompts_ready now checks prompt structures
    response.generation_prompts_ready = bool(prompt_structures)

    # 2. Total Generation rows for this project — feeds the Statistiken
    # "Generations" tile on the project detail page (rendered conditionally
    # when > 0).
    response.generation_count = (
        db.query(func.count(Generation.id))
        .join(Task, Generation.task_id == Task.id)
        .filter(Task.project_id == project.id)
        .scalar()
    ) or 0

    # 3. Count configured models in generation_config (single source of truth)
    response.generation_models_count = 0
    if (
        project.generation_config
        and project.generation_config.get('selected_configuration')
        and project.generation_config['selected_configuration'].get('models')
    ):
        response.generation_models_count = len(
            project.generation_config['selected_configuration']['models']
        )

    # 4. Check if generation is complete for all tasks and all models
    response.generation_completed = False
    if response.task_count > 0 and response.generation_models_count > 0:
        # Get all task IDs for this project
        project_task_ids = [
            task.id for task in db.query(Task.id).filter(Task.project_id == project.id).all()
        ]

        if project_task_ids:
            # Count completed generations for tasks in this project
            completed_generations = (
                db.query(ResponseGeneration)
                .filter(
                    ResponseGeneration.task_id.in_(project_task_ids),
                    ResponseGeneration.status == 'completed',
                )
                .count()
            )

            expected_generations = response.task_count * response.generation_models_count
            response.generation_completed = completed_generations >= expected_generations


async def calculate_generation_stats_async(
    db: AsyncSession, project: Project, response: ProjectResponse
) -> None:
    """Async equivalent of :func:`calculate_generation_stats`."""
    generation_config = project.generation_config or {}
    prompt_structures = generation_config.get("prompt_structures", {})
    response.generation_config_ready = bool(prompt_structures)
    response.generation_prompts_ready = bool(prompt_structures)

    response.generation_count = (
        await db.execute(
            select(func.count(Generation.id))
            .join(Task, Generation.task_id == Task.id)
            .where(Task.project_id == project.id)
        )
    ).scalar() or 0

    response.generation_models_count = 0
    if (
        project.generation_config
        and project.generation_config.get('selected_configuration')
        and project.generation_config['selected_configuration'].get('models')
    ):
        response.generation_models_count = len(
            project.generation_config['selected_configuration']['models']
        )

    response.generation_completed = False
    if response.task_count > 0 and response.generation_models_count > 0:
        task_id_result = await db.execute(
            select(Task.id).where(Task.project_id == project.id)
        )
        project_task_ids = [row[0] for row in task_id_result.all()]

        if project_task_ids:
            completed_generations = (
                await db.execute(
                    select(func.count())
                    .select_from(ResponseGeneration)
                    .where(
                        ResponseGeneration.task_id.in_(project_task_ids),
                        ResponseGeneration.status == 'completed',
                    )
                )
            ).scalar() or 0

            expected_generations = response.task_count * response.generation_models_count
            response.generation_completed = completed_generations >= expected_generations


def calculate_generation_stats_batch(
    db: Session, projects: List[Project]
) -> Dict[str, Dict[str, int]]:
    """Batch generation stats for many projects.

    Reads from `project_summaries` (period='overall') for every project that
    has a summary row; falls back to the original two grouped queries only
    for projects the worker hasn't summarized yet. After Phase 6.2 the
    summary table carries both the total Generation count and the
    status='completed' ResponseGeneration count, so the dashboard pays
    nothing on the established 99 % of projects.

    Returns: project_id -> {generation_count, completed_generations}.
    Caller still computes config_ready / prompts_ready / models_count /
    completed in-process from each Project's generation_config (no DB hit).
    """
    from models import ProjectSummary
    from sqlalchemy import select as sa_select

    if not projects:
        return {}

    project_ids = [p.id for p in projects]

    out: Dict[str, Dict[str, int]] = {}

    # Step 1: read from the precomputed summary in one indexed query.
    summary_rows = db.execute(
        sa_select(
            ProjectSummary.project_id,
            ProjectSummary.generations_count,
            ProjectSummary.completed_response_generations_count,
        ).where(
            ProjectSummary.project_id.in_(project_ids),
            ProjectSummary.period == "overall",
        )
    ).all()
    for pid, gen_c, completed_c in summary_rows:
        out[pid] = {
            "generation_count": int(gen_c or 0),
            "completed_generations": int(completed_c or 0),
        }

    # Step 2: live fallback only for projects without a summary row yet.
    missing_summary_ids = [pid for pid in project_ids if pid not in out]
    for pid in missing_summary_ids:
        out[pid] = {"generation_count": 0, "completed_generations": 0}
    if not missing_summary_ids:
        return out

    # Query 1: total Generation rows per missing project
    gen_counts = (
        db.query(Task.project_id, func.count(Generation.id).label("c"))
        .join(Generation, Generation.task_id == Task.id)
        .filter(Task.project_id.in_(missing_summary_ids))
        .group_by(Task.project_id)
        .all()
    )

    # Query 2: completed ResponseGeneration rows per missing project
    completed_counts = (
        db.query(Task.project_id, func.count(ResponseGeneration.id).label("c"))
        .join(ResponseGeneration, ResponseGeneration.task_id == Task.id)
        .filter(
            Task.project_id.in_(missing_summary_ids),
            ResponseGeneration.status == "completed",
        )
        .group_by(Task.project_id)
        .all()
    )

    for row in gen_counts:
        out[row.project_id]["generation_count"] = row.c or 0
    for row in completed_counts:
        out[row.project_id]["completed_generations"] = row.c or 0
    return out


def apply_generation_stats(
    project: Project, response: ProjectResponse, batch_stats: Dict[str, int]
) -> None:
    """In-process variant of calculate_generation_stats: fills the same fields
    on `response` using pre-fetched per-project counts (no DB query)."""
    generation_config = project.generation_config or {}
    prompt_structures = generation_config.get("prompt_structures", {})
    response.generation_config_ready = bool(prompt_structures)
    response.generation_prompts_ready = bool(prompt_structures)
    response.generation_count = int(batch_stats.get("generation_count", 0))

    response.generation_models_count = 0
    selected = (project.generation_config or {}).get("selected_configuration") or {}
    if selected.get("models"):
        response.generation_models_count = len(selected["models"])

    response.generation_completed = False
    if response.task_count > 0 and response.generation_models_count > 0:
        expected = response.task_count * response.generation_models_count
        response.generation_completed = (
            batch_stats.get("completed_generations", 0) >= expected
        )


def get_user_with_memberships(db: Session, user_id: str) -> User:
    """Get user with organization memberships loaded (sync).

    Sync body intentionally kept on the legacy ``db.query`` API so the
    extensive ``db.query``-mocking unit tests keep passing; the async lane
    has its own ``select``-based twin below.
    """
    return (
        db.query(User)
        .options(joinedload(User.organization_memberships))
        .filter(User.id == user_id)
        .first()
    )


def _build_select_user_with_memberships(user_id: str):
    """Shared SQL builder for the async user + memberships eager load.

    joinedload keeps the memberships eagerly populated so callers can read
    ``user.organization_memberships`` in the async lane without a lazy load
    (which would raise MissingGreenlet under the async engine).
    """
    return (
        select(User)
        .options(joinedload(User.organization_memberships))
        .where(User.id == user_id)
    )


async def get_user_with_memberships_async(db: AsyncSession, user_id: str) -> User:
    """Async equivalent of :func:`get_user_with_memberships`."""
    result = await db.execute(_build_select_user_with_memberships(user_id))
    return result.unique().scalar_one_or_none()


async def get_org_membership_role_async(
    db: AsyncSession, user, org_context: Optional[str]
) -> Optional[str]:
    """Resolve the user's active role within ``org_context`` (async).

    Returns the ``OrganizationRole`` value (e.g. ``"ANNOTATOR"``) for the user's
    active membership in that org, or ``None`` when there is no org context
    (private/legacy) or no active membership. Superadmin is not special-cased
    here — callers needing the bypass should check ``user.is_superadmin`` first.
    """
    if not org_context or org_context == "private":
        return None
    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    if not user_with_memberships or not user_with_memberships.organization_memberships:
        return None
    for membership in user_with_memberships.organization_memberships:
        if membership.organization_id == org_context and membership.is_active:
            return membership.role
    return None


def get_accessible_project_ids(
    db: Session,
    user,
    org_context: Optional[str] = None,
    include_all_private: bool = False,
) -> Optional[List[str]]:
    """Get project IDs accessible to a user based on organization context.

    Args:
        db: Database session
        user: Current authenticated user (auth_module User or DB User)
        org_context: Value of X-Organization-Context header.
                     "private" or None = user's private projects only
                     org_id string = projects in that org
                     Ignored for superadmins — they always get an org-agnostic
                     view of every project across every org.
        include_all_private: Superadmin-only opt-in. When True, the helper
                     returns None (no filter) so the caller sees every project
                     in the system, including other users' private projects.
                     When False (default) a superadmin sees every org's projects
                     + public projects + their own private, but other users'
                     private projects stay hidden.

    Returns:
        List of accessible project IDs, or None for superadmins with
        include_all_private=True (no filter needed).
    """
    if user.is_superadmin:
        if include_all_private:
            return None
        # Default superadmin view: every project across every org, plus public
        # and own private. Other users' private projects stay hidden until the
        # toggle is flipped. Org context is intentionally ignored — a
        # superadmin's projects browser is org-agnostic.
        rows = (
            db.query(Project.id)
            .filter(
                or_(
                    Project.is_private == False,  # noqa: E712
                    Project.created_by == str(user.id),
                )
            )
            .all()
        )
        seen = set()
        result = []
        for r in rows:
            if r.id not in seen:
                seen.add(r.id)
                result.append(r.id)
        return result

    public_ids = [
        r.id for r in db.query(Project.id).filter(Project.is_public == True).all()  # noqa: E712
    ]

    if not org_context or org_context == "private":
        rows = (
            db.query(Project.id)
            .filter(
                Project.is_private == True,  # noqa: E712
                Project.created_by == str(user.id),
            )
            .all()
        )
        seen = set()
        result = []
        for r in rows:
            if r.id not in seen:
                seen.add(r.id)
                result.append(r.id)
        for pid in public_ids:
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    # Org mode: verify membership then get org projects. Superadmins are
    # already handled above and never reach this branch.
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    user_org_ids = []
    if user_with_memberships and user_with_memberships.organization_memberships:
        user_org_ids = [
            m.organization_id for m in user_with_memberships.organization_memberships if m.is_active
        ]

    if org_context not in user_org_ids:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization",
        )

    rows = (
        db.query(ProjectOrganization.project_id)
        .filter(ProjectOrganization.organization_id == org_context)
        .all()
    )
    seen = set()
    result = []
    for r in rows:
        if r.project_id not in seen:
            seen.add(r.project_id)
            result.append(r.project_id)
    for pid in public_ids:
        if pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result


def _dedup_preserve_order(ids, extra=()):
    """Dedup an id list preserving first-seen order, then append `extra` ids
    that weren't already present (also order-preserving). Shared by the
    sync/async accessible-project-id helpers."""
    seen = set()
    result = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            result.append(i)
    for i in extra:
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result


async def get_accessible_project_ids_async(
    db: AsyncSession,
    user,
    org_context: Optional[str] = None,
    include_all_private: bool = False,
) -> Optional[List[str]]:
    """Async equivalent of :func:`get_accessible_project_ids`."""
    if user.is_superadmin:
        if include_all_private:
            return None
        rows = (
            await db.execute(
                select(Project.id).where(
                    or_(
                        Project.is_private == False,  # noqa: E712
                        Project.created_by == str(user.id),
                    )
                )
            )
        ).all()
        return _dedup_preserve_order([r.id for r in rows])

    public_rows = (
        await db.execute(
            select(Project.id).where(Project.is_public == True)  # noqa: E712
        )
    ).all()
    public_ids = [r.id for r in public_rows]

    if not org_context or org_context == "private":
        rows = (
            await db.execute(
                select(Project.id).where(
                    Project.is_private == True,  # noqa: E712
                    Project.created_by == str(user.id),
                )
            )
        ).all()
        return _dedup_preserve_order([r.id for r in rows], public_ids)

    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    user_org_ids = []
    if user_with_memberships and user_with_memberships.organization_memberships:
        user_org_ids = [
            m.organization_id
            for m in user_with_memberships.organization_memberships
            if m.is_active
        ]

    if org_context not in user_org_ids:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization",
        )

    rows = (
        await db.execute(
            select(ProjectOrganization.project_id).where(
                ProjectOrganization.organization_id == org_context
            )
        )
    ).all()
    return _dedup_preserve_order([r.project_id for r in rows], public_ids)


def get_org_context_from_request(request: Request) -> Optional[str]:
    """Extract organization context from request.

    Checks request.state (set by OrgContextMiddleware) first,
    falls back to X-Organization-Context header.
    """
    if hasattr(request, "state") and hasattr(request.state, "organization_context"):
        return request.state.organization_context
    return request.headers.get("X-Organization-Context")


def _decide_project_accessible_context_mode(
    user, project, org_context, project_org_ids, user_with_memberships
) -> bool:
    """Org-context-mode decision (pure; no DB). Mirrors the inline logic."""
    if getattr(project, "is_private", False):
        return str(user.id) == str(project.created_by)

    if org_context == "private":
        return False

    if org_context not in project_org_ids:
        return False

    if not user_with_memberships or not user_with_memberships.organization_memberships:
        return False

    return any(
        m.organization_id == org_context and m.is_active
        for m in user_with_memberships.organization_memberships
    )


def _decide_project_accessible_legacy_mode(
    user, project, project_org_ids, user_with_memberships
) -> bool:
    """Legacy-mode (org_context=None) decision (pure; no DB)."""
    if getattr(project, "is_private", False):
        return str(user.id) == str(project.created_by)

    if not project_org_ids:
        return str(user.id) == str(project.created_by)

    if not user_with_memberships or not user_with_memberships.organization_memberships:
        return False

    user_org_ids = {
        m.organization_id for m in user_with_memberships.organization_memberships if m.is_active
    }
    return bool(user_org_ids & set(project_org_ids))


def check_project_accessible(
    db: Session,
    user,
    project_id: str,
    org_context: Optional[str] = None,
    project: Optional[Project] = None,
) -> bool:
    """Check if a user can access a specific project (sync).

    Args:
        db: Database session
        user: Current authenticated user
        project_id: Project to check access for
        org_context: Value of X-Organization-Context header.
            When provided, enforces context-aware checking:
            - "private" -> only creator's own private projects
            - org_id -> project must belong to that org, user must be member
            When None, falls back to legacy behavior (any org membership).
        project: Optional pre-loaded Project object to avoid redundant DB query.
    """
    if user.is_superadmin:
        return True

    if project is None:
        project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False

    # Archived projects are read-only to annotators: an annotator who is
    # otherwise a member loses access once a project is archived. Higher roles
    # (and the creator/superadmin, who already short-circuit above / resolve to
    # ORG_ADMIN) keep access so they can view and unarchive.
    if getattr(project, "is_archived", False):
        if get_effective_project_role(db, user, project) == "ANNOTATOR":
            return False

    # Public projects are readable by every authenticated user regardless of context.
    if getattr(project, "is_public", False) is True:
        return True

    # Context-aware mode
    if org_context is not None:
        # A user's own private project is always accessible to its creator,
        # regardless of which org context the request carries. On an org
        # subdomain the frontend always sends X-Organization-Context: <org id>,
        # so without this a private project becomes unreadable/unconfigurable
        # by the very user who created it.
        if getattr(project, "is_private", False):
            return str(user.id) == str(project.created_by)

        if org_context == "private":
            # Private context but project is not private -> no access
            return False

        # Org mode: project must belong to this specific org
        # AND user must be an active member of this org
        project_org_ids = [
            r.organization_id
            for r in db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        ]
        if org_context not in project_org_ids:
            return False

        user_with_memberships = get_user_with_memberships(db, str(user.id))
        if not user_with_memberships or not user_with_memberships.organization_memberships:
            return False

        return any(
            m.organization_id == org_context and m.is_active
            for m in user_with_memberships.organization_memberships
        )

    # Legacy mode (org_context=None): backward compatibility
    if getattr(project, "is_private", False):
        return str(user.id) == str(project.created_by)

    project_org_ids = [
        r.organization_id
        for r in db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    ]
    if not project_org_ids:
        return str(user.id) == str(project.created_by)

    user_with_memberships = get_user_with_memberships(db, str(user.id))
    if not user_with_memberships or not user_with_memberships.organization_memberships:
        return False

    user_org_ids = {
        m.organization_id for m in user_with_memberships.organization_memberships if m.is_active
    }
    return bool(user_org_ids & set(project_org_ids))


async def check_project_accessible_async(
    db: AsyncSession,
    user,
    project_id: str,
    org_context: Optional[str] = None,
    project: Optional[Project] = None,
) -> bool:
    """Async equivalent of :func:`check_project_accessible`."""
    if user.is_superadmin:
        return True

    if project is None:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
    if not project:
        return False

    if getattr(project, "is_archived", False):
        if await get_effective_project_role_async(db, user, project) == "ANNOTATOR":
            return False

    if getattr(project, "is_public", False) is True:
        return True

    org_result = await db.execute(_build_select_project_org_ids(project_id))
    project_org_ids = list(org_result.scalars().all())
    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))

    if org_context is not None:
        return _decide_project_accessible_context_mode(
            user, project, org_context, project_org_ids, user_with_memberships
        )
    return _decide_project_accessible_legacy_mode(
        user, project, project_org_ids, user_with_memberships
    )


def _build_select_org_admin_membership(user_id, project_org_ids):
    """Shared SQL builder: is `user` an active ORG_ADMIN of any of these orgs?"""
    return (
        select(OrganizationMembership.id)
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id.in_(project_org_ids),
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    )


def check_user_can_edit_task_data(db: Session, user, project: Project) -> bool:
    """Whether a user may edit the `data` of a task within the given project.

    Allowed: superadmins, the project creator, and active ORG_ADMIN members of
    any organization the project belongs to. Mirrors the frontend notion of
    getEffectiveProjectRole(...) == 'ORG_ADMIN'. This governs *who* may edit;
    callers still verify project/task access separately.
    """
    if user.is_superadmin:
        return True
    if str(user.id) == str(project.created_by):
        return True

    project_org_ids = [
        r.organization_id
        for r in db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project.id)
        .all()
    ]
    if not project_org_ids:
        return False

    admin_membership = (
        db.query(OrganizationMembership.id)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id.in_(project_org_ids),
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )
    return admin_membership is not None


async def check_user_can_edit_task_data_async(db: AsyncSession, user, project: Project) -> bool:
    """Async equivalent of :func:`check_user_can_edit_task_data`."""
    if user.is_superadmin:
        return True
    if str(user.id) == str(project.created_by):
        return True

    org_result = await db.execute(_build_select_project_org_ids(project.id))
    project_org_ids = list(org_result.scalars().all())
    if not project_org_ids:
        return False

    admin_result = await db.execute(
        _build_select_org_admin_membership(user.id, project_org_ids)
    )
    return admin_result.first() is not None


def check_task_assigned_to_user(
    db: Session,
    user,
    task_id: str,
    project: Project,
) -> bool:
    """Check if a task is assigned to the user when in manual/auto assignment mode.

    Aligned with Label Studio Enterprise: unassigned tasks should be invisible
    to annotators (404), not forbidden (403). Callers decide the HTTP status.

    Returns True if:
    - Project assignment_mode is 'open' (no restrictions)
    - User is superadmin
    - User's org role is not ANNOTATOR (admins/contributors bypass)
    - User has an active assignment for this task

    Returns False only when an annotator tries to access an unassigned task
    in manual/auto mode.
    """
    if getattr(project, "assignment_mode", "open") == "open":
        return True

    if user.is_superadmin:
        return True

    # Resolve user role from org memberships
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    user_role = None
    if user_with_memberships and user_with_memberships.organization_memberships:
        project_org_ids = [
            r.organization_id
            for r in db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project.id)
            .all()
        ]
        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    # Non-annotator roles (admin, contributor) bypass assignment checks
    if user_role and user_role.upper() not in ["ANNOTATOR"]:
        return True

    # Check if user has any assignment for this task (including completed)
    # Completed assignments still grant read access so annotators can review their work
    assignment = (
        db.query(TaskAssignment)
        .filter(
            TaskAssignment.task_id == task_id,
            TaskAssignment.user_id == str(user.id),
            TaskAssignment.status.in_(["assigned", "in_progress", "completed"]),
        )
        .first()
    )
    return assignment is not None


def _build_select_task_assignment(task_id, user_id):
    """Shared SQL builder: active/read-granting assignment of task to user."""
    return select(TaskAssignment).where(
        TaskAssignment.task_id == task_id,
        TaskAssignment.user_id == str(user_id),
        TaskAssignment.status.in_(["assigned", "in_progress", "completed"]),
    )


async def check_task_assigned_to_user_async(
    db: AsyncSession,
    user,
    task_id: str,
    project: Project,
) -> bool:
    """Async equivalent of :func:`check_task_assigned_to_user`."""
    if getattr(project, "assignment_mode", "open") == "open":
        return True

    if user.is_superadmin:
        return True

    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    user_role = None
    if user_with_memberships and user_with_memberships.organization_memberships:
        org_result = await db.execute(_build_select_project_org_ids(project.id))
        project_org_ids = list(org_result.scalars().all())
        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    if user_role and user_role.upper() not in ["ANNOTATOR"]:
        return True

    # .scalars().first() (NOT scalar_one_or_none): the (task_id, user_id) key is
    # only partially unique (WHERE target_type='task'); item-level Korrektur
    # assignments allow multiple rows per (task_id, user_id), so one_or_none
    # would raise MultipleResultsFound → 500. Matches the sync twin's .first().
    assignment_result = await db.execute(_build_select_task_assignment(task_id, user.id))
    return assignment_result.scalars().first() is not None


def _build_select_project_org_ids(project_id: str):
    """Shared SQL builder for the org ids a project is assigned to."""
    return select(ProjectOrganization.organization_id).where(
        ProjectOrganization.project_id == project_id
    )


def _resolve_effective_role(
    user, project: Project, user_with_memberships, project_org_ids
) -> Optional[str]:
    """Pure resolution logic shared by the sync/async role helpers.

    Takes already-loaded data (no DB access) so both lanes share identical
    semantics — only the two reads (memberships + project org ids) differ
    between sync and async.
    """
    if user_with_memberships and user_with_memberships.organization_memberships:
        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                return membership.role

    if getattr(project, "is_public", False) is True and getattr(project, "public_role", None):
        return project.public_role

    return None


def get_effective_project_role(
    db: Session,
    user,
    project: Project,
) -> Optional[str]:
    """Resolve the effective role a user holds within a project (sync).

    Returns one of: "ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", or None.
    Resolution order:
      1. Superadmin or project creator → ORG_ADMIN.
      2. Active org membership in any org assigned to this project → that role.
      3. Project is public and user has no other claim → project.public_role.
      4. Otherwise → None.

    Sync body kept on the legacy ``db.query`` API to preserve the existing
    ``db.query``-mocking unit tests; the async twin lives below.
    """
    if user.is_superadmin or str(project.created_by) == str(user.id):
        return "ORG_ADMIN"

    user_with_memberships = get_user_with_memberships(db, str(user.id))
    project_org_ids = [
        r.organization_id
        for r in db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project.id)
        .all()
    ]
    return _resolve_effective_role(
        user, project, user_with_memberships, project_org_ids
    )


async def get_effective_project_role_async(
    db: AsyncSession,
    user,
    project: Project,
) -> Optional[str]:
    """Async equivalent of :func:`get_effective_project_role`."""
    if user.is_superadmin or str(project.created_by) == str(user.id):
        return "ORG_ADMIN"

    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    result = await db.execute(_build_select_project_org_ids(project.id))
    project_org_ids = list(result.scalars().all())
    return _resolve_effective_role(
        user, project, user_with_memberships, project_org_ids
    )


def check_project_write_access(
    db: Session,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Check if a user can perform a write/contribute action on a project.

    Combines read access + role gate. The role check honours the public_role
    fallback for public-tier visitors:
      - public_role=ANNOTATOR  → blocked (only ORG_ADMIN/CONTRIBUTOR allowed)
      - public_role=CONTRIBUTOR → allowed
      - org-member with allowed role → allowed
      - creator + superadmin → always allowed (via get_effective_project_role)

    Use for endpoints that mutate task/annotation/generation data on a project
    (e.g. import, generate, bulk delete) where the documented public_role
    contract should be enforced.
    """
    if user.is_superadmin:
        return True

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False

    role = get_effective_project_role(db, user, project)
    return role in allowed_roles


async def check_project_write_access_async(
    db: AsyncSession,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Async equivalent of :func:`check_project_write_access`."""
    if user.is_superadmin:
        return True

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        return False

    role = await get_effective_project_role_async(db, user, project)
    return role in allowed_roles


def check_user_can_edit_project(
    db: Session,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Check if a user can edit a project (creator, superadmin, or allowed org role).

    Used for project updates, bulk task operations, and other write actions.
    Does NOT check project accessibility — call check_project_accessible first.
    """
    if user.is_superadmin:
        return True

    # Check if user is the project creator
    project = db.query(Project).filter(Project.id == project_id).first()
    if project and str(project.created_by) == str(user.id):
        return True

    # Check org role
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    if user_with_memberships and user_with_memberships.organization_memberships:
        project_org_ids = [
            r.organization_id
            for r in db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        ]
        for membership in user_with_memberships.organization_memberships:
            if (
                membership.organization_id in project_org_ids
                and membership.is_active
                and membership.role in allowed_roles
            ):
                return True

    return False


async def check_user_can_edit_project_async(
    db: AsyncSession,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Async equivalent of :func:`check_user_can_edit_project`."""
    if user.is_superadmin:
        return True

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project and str(project.created_by) == str(user.id):
        return True

    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    if user_with_memberships and user_with_memberships.organization_memberships:
        org_result = await db.execute(_build_select_project_org_ids(project_id))
        project_org_ids = list(org_result.scalars().all())
        for membership in user_with_memberships.organization_memberships:
            if (
                membership.organization_id in project_org_ids
                and membership.is_active
                and membership.role in allowed_roles
            ):
                return True

    return False


# NOTE: the canonical project-access dependency is `require_project_access` in
# routers/projects/deps.py (returns a ProjectAccess container, supports
# min_role="edit"). An earlier, simpler view-only variant that lived here was
# removed — every router adopts the deps.py one.


def _format_project_organizations(project_orgs) -> List[Dict[str, Any]]:
    """Pure shaping shared by the sync/async org-list helpers."""
    return [
        {
            "id": po.organization.id,
            "name": po.organization.name,
        }
        for po in project_orgs
        if po.organization  # Filter out any with missing organization references
    ]


def get_project_organizations(db: Session, project_id: str) -> List[Dict[str, Any]]:
    """Get all organizations assigned to a project"""
    project_orgs = (
        db.query(ProjectOrganization)
        .options(joinedload(ProjectOrganization.organization))
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    )

    return _format_project_organizations(project_orgs)


async def get_project_organizations_async(
    db: AsyncSession, project_id: str
) -> List[Dict[str, Any]]:
    """Async equivalent of :func:`get_project_organizations`."""
    result = await db.execute(
        select(ProjectOrganization)
        .options(joinedload(ProjectOrganization.organization))
        .where(ProjectOrganization.project_id == project_id)
    )
    return _format_project_organizations(result.scalars().unique().all())
