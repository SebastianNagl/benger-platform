"""
Dashboard and analytics endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import User, require_user
from database import get_async_db
from models import (
    AnalysisRun,
    EvaluationRun,
    Generation,
    OrganizationGroup,
    OrganizationGroupMembership,
    OrganizationMembership,
    OrganizationRole,
    TaskEvaluation,
)
from project_models import Annotation, Project, Task, project_listable
from project_window import project_writes_allowed
from redis_cache import RedisCache
from routers.projects.helpers import (
    attempt_score_from_metrics,
    get_accessible_project_ids,
    get_accessible_project_ids_async,
    get_participant_project_ids_async,
)
from aggregate_summaries import (
    count_eval_pairs_by_project_async,
    read_dashboard_sum_async,
    unsummarized_project_ids_async,
)

logger = logging.getLogger(__name__)

# Initialize cache
cache = RedisCache()

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# The two views of GET /stats (the response's ``scope``).
SCOPE_OVERVIEW = "overview"
SCOPE_PERSONAL = "personal"

# The personal view changes with every answer the user submits, so it is
# cached for a minute only; the overview keeps its five minutes.
OVERVIEW_TTL = 300
PERSONAL_TTL = 60

# The evaluation runs a student sees the result of: the immediate KI grading
# and the human Korrektur (as in /api/student/score-history). Batch and
# research runs grade for the teachers and are never shown to the student.
STUDENT_VISIBLE_RUN_MODELS = ("immediate", "human")


async def sees_overview_async(db: AsyncSession, user) -> bool:
    """Whether the user gets the overview of the dashboard (``scope``
    ``"overview"``) rather than the personal view.

    Teachers and admins keep the overview: superadmins, users with an active
    ORG_ADMIN or CONTRIBUTOR membership, users who hold the Contributor or
    Admin role in a group of an organization they are an active member of
    (the group role :func:`org_groups.attachment_role` gives on the group's
    projects), and users who created a project that is listed (not a wizard
    draft, not deleted). Everyone else, annotators and students of an
    organization and users without any membership such as students who
    joined an exam by share link, gets the personal view.
    """
    if user.is_superadmin:
        return True
    uid = str(user.id)
    staff_roles = (OrganizationRole.ORG_ADMIN, OrganizationRole.CONTRIBUTOR)
    org_staff = select(OrganizationMembership.id).where(
        OrganizationMembership.user_id == uid,
        OrganizationMembership.is_active == True,  # noqa: E712
        OrganizationMembership.role.in_(staff_roles),
    )
    group_staff = (
        select(OrganizationGroupMembership.id)
        .join(
            OrganizationGroup,
            OrganizationGroup.id == OrganizationGroupMembership.group_id,
        )
        .join(
            OrganizationMembership,
            and_(
                OrganizationMembership.organization_id
                == OrganizationGroup.organization_id,
                OrganizationMembership.user_id == uid,
                OrganizationMembership.is_active == True,  # noqa: E712
            ),
        )
        .where(
            OrganizationGroupMembership.user_id == uid,
            OrganizationGroupMembership.role.in_(staff_roles),
        )
    )
    own_project = select(Project.id).where(
        Project.created_by == uid, project_listable()
    )
    return bool(
        (
            await db.execute(
                select(
                    or_(exists(org_staff), exists(group_staff), exists(own_project))
                )
            )
        ).scalar()
    )


def _submitted_by(user_id: str):
    """SQL condition over ``Annotation``: a submitted answer of the user (not
    cancelled, with a result), the predicate the overview's annotation count
    uses for everyone's answers."""
    return and_(
        Annotation.completed_by == user_id,
        Annotation.was_cancelled == False,  # noqa: E712
        func.jsonb_array_length(Annotation.result) > 0,
    )


async def _personal_stats_async(db: AsyncSession, user) -> dict:
    """The dashboard counters of a user who only answers tasks.

    Only the user's own data, and only what they can open:

    - ``open_exams`` / ``open_tasks``: the tasks the user is handed to answer
      (full or participant tier, the access decision of the cross-project
      data surface: read window, exams an overlay keeps closed, own open
      assignments on assignment projects) in projects whose window takes
      answers now, without a submitted answer of theirs and not already
      filled up by others (``maximum_annotations``); ``open_exams`` counts
      the exams among them that still hold such a task.
    - ``submitted_answers``: the user's submitted annotations in projects
      that still exist (an own submission stays readable to its author).
    - ``released_results``: the submitted answers with a result the student
      sees: a score of the immediate grading or of the human Korrektur,
      never a teacher's batch run and never a feedback draft the teacher has
      not released (:func:`attempt_score_from_metrics`).
    """
    from routers.tasks import _resolve_data_scope

    uid = str(user.id)
    candidates = set(await get_accessible_project_ids_async(db, user) or [])
    candidates |= set(await get_participant_project_ids_async(db, uid))
    scope = await _resolve_data_scope(db, user, candidates)

    open_tasks = 0
    open_exams = 0
    if scope.project_ids:
        projects = (
            await db.execute(
                select(Project).where(Project.id.in_(scope.project_ids))
            )
        ).scalars().all()
        writable = {str(p.id): p for p in projects if project_writes_allowed(p)}
        if writable:
            answered_by_me = exists().where(
                Annotation.task_id == Task.id, _submitted_by(uid)
            )
            answers = (
                select(func.count(Annotation.id))
                .where(
                    Annotation.task_id == Task.id,
                    Annotation.was_cancelled == False,  # noqa: E712
                    func.jsonb_array_length(Annotation.result) > 0,
                )
                .correlate(Task)
                .scalar_subquery()
            )
            rows = (
                await db.execute(
                    select(Task.project_id, func.count(Task.id))
                    .join(Project, Project.id == Task.project_id)
                    .where(
                        scope.answerable_task_clause(writable),
                        ~answered_by_me,
                        or_(
                            Project.maximum_annotations == 0,
                            answers < Project.maximum_annotations,
                        ),
                    )
                    .group_by(Task.project_id)
                )
            ).all()
            for project_id, count in rows:
                open_tasks += int(count)
                if writable[str(project_id)].kind == "exam":
                    open_exams += 1

    submitted_answers = (
        await db.execute(
            select(func.count(Annotation.id))
            .join(Project, Project.id == Annotation.project_id)
            .where(_submitted_by(uid), project_listable())
        )
    ).scalar() or 0

    graded = (
        await db.execute(
            select(Annotation.id, TaskEvaluation.metrics)
            .select_from(TaskEvaluation)
            .join(Annotation, Annotation.id == TaskEvaluation.annotation_id)
            .join(Project, Project.id == Annotation.project_id)
            .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
            .where(
                _submitted_by(uid),
                project_listable(),
                EvaluationRun.model_id.in_(STUDENT_VISIBLE_RUN_MODELS),
            )
        )
    ).all()
    released_results = len(
        {
            annotation_id
            for annotation_id, metrics in graded
            if attempt_score_from_metrics(metrics) is not None
        }
    )

    return {
        "scope": SCOPE_PERSONAL,
        "open_exams": open_exams,
        "open_tasks": open_tasks,
        "submitted_answers": int(submitted_answers),
        "released_results": released_results,
    }


async def _live_evaluations_count_async(db: AsyncSession, project_ids):
    """Live evaluation count of `project_ids` - the projects without a
    project_summaries row yet. Same statement the refresh writes the
    summaries with (`count_eval_pairs_by_project`), so a project shows the
    same number before and after its first refresh.
    """
    counts = await count_eval_pairs_by_project_async(db, list(project_ids))
    return sum(counts.values())


async def _live_dashboard_counts_async(db: AsyncSession, project_ids):
    """Live tasks / annotations / generations of `project_ids` - the
    projects without a project_summaries row yet.

    Mirrors the per-project predicates in
    aggregate_summaries._compute_project_summary so the values match what
    the refresh will write - critically, generations counts only Generation
    rows with parse_status="success", not raw ResponseGeneration rows.
    """
    project_ids = list(project_ids)
    task_q = select(func.count(Task.id)).where(Task.project_id.in_(project_ids))
    ann_q = select(func.count(Annotation.id)).where(
        Annotation.project_id.in_(project_ids),
        Annotation.was_cancelled == False,  # noqa: E712
        func.jsonb_array_length(Annotation.result) > 0,
    )
    gen_q = (
        select(func.count(Generation.id))
        .join(Task, Generation.task_id == Task.id)
        .where(
            Task.project_id.in_(project_ids),
            Generation.parse_status == "success",
        )
    )
    return {
        "total_tasks": int((await db.execute(task_q)).scalar() or 0),
        "annotations_count": int((await db.execute(ann_q)).scalar() or 0),
        "generations_count": int((await db.execute(gen_q)).scalar() or 0),
    }


async def _analyses_count_async(db: AsyncSession, accessible_ids) -> int:
    """Completed analysis runs of the projects in ``accessible_ids`` (every
    listed project when None), counted live: analysis runs are few, and the
    count reads ``ix_analysis_runs_project_created``. The projects' own
    count (``routers.projects.helpers.count_analysis_runs_by_project``)
    counts the same runs, so the tile equals the sum over the projects."""
    stmt = (
        select(func.count(AnalysisRun.id))
        .join(Project, Project.id == AnalysisRun.project_id)
        .where(AnalysisRun.status == "completed", project_listable())
    )
    if accessible_ids is not None:
        stmt = stmt.where(AnalysisRun.project_id.in_(list(accessible_ids)))
    return int((await db.execute(stmt)).scalar() or 0)


def _overview_stats(
    project_count: int,
    task_count: int,
    annotation_count: int,
    generations_count: int,
    evaluations_count: int,
    analyses_count: int,
) -> dict:
    """The overview answer. ``projects_with_generations`` and
    ``projects_with_evaluations`` are the old names of ``generations_count``
    and ``evaluations_count`` (they always carried those counts, not the
    number of projects that have any) and stay as aliases with the same
    values for older clients."""
    return {
        "scope": SCOPE_OVERVIEW,
        "project_count": project_count,
        "task_count": task_count,
        "annotation_count": annotation_count,
        "generations_count": generations_count,
        "evaluations_count": evaluations_count,
        "analyses_count": analyses_count,
        "projects_with_generations": generations_count,
        "projects_with_evaluations": evaluations_count,
    }


@router.get("/stats")
async def get_dashboard_stats(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Returns the dashboard statistics in one of two views (``scope``).

    ``scope: "personal"`` for users who only answer tasks (no staff role in
    an organization or group, no own listed project, not superadmin;
    :func:`sees_overview_async`):
    their own counters only (:func:`_personal_stats_async`), never totals of
    the organization's projects or other people's answers.

    ``scope: "overview"`` for teachers and admins, over every project the
    user may reach through any of their organizations:
    - project_count: Total projects accessible to user
    - task_count: Total tasks (issues) across all accessible projects
    - annotation_count: Submitted annotations in those projects
    - generations_count: Successfully parsed LLM generations in those projects
    - evaluations_count: Evaluated cells (subject, evaluation config, metric
      with a scored row of a completed run), as each project's own count
    - analyses_count: Completed analysis runs in those projects
    - projects_with_generations, projects_with_evaluations: aliases of
      generations_count and evaluations_count (:func:`_overview_stats`)

    The overview reads from the precomputed `project_summaries` table (refreshed by the
    `recompute_aggregates` Celery beat task every hour). Brand-new projects
    that haven't been picked up by a refresh yet fall back to a live count
    so the dashboard never shows stale-zero. The existing 5-min Redis TTL
    smooths repeated requests in both cases. When the counts cannot be
    computed (database error or statement timeout) the endpoint answers 503
    rather than a set of zeros.
    """
    # The selected organization of the client plays no part, so the cache is
    # keyed by user and by the view their roles give them now: a role change
    # switches the view at once instead of serving the other view's numbers
    # from the cache (`v5`).
    try:
        scope = (
            SCOPE_OVERVIEW
            if await sees_overview_async(db, current_user)
            else SCOPE_PERSONAL
        )
    except Exception as e:
        logger.error(f"Error resolving the dashboard view: {e!r}")
        raise HTTPException(
            status_code=503,
            detail="Dashboard statistics are temporarily unavailable.",
        )
    # The analyses tile belongs to variant_experiments (core 2.74); the
    # answer is part of the cache key so a switched flag shows at once.
    from feature_flags.deps import flag_on
    from feature_flags.registry import VARIANT_EXPERIMENTS

    experiments = await flag_on(db, current_user, VARIANT_EXPERIMENTS)
    cache_key = f"dashboard_stats:v6:{current_user.id}:{scope}:{int(experiments)}"

    cached_stats = cache.get(cache_key)
    if cached_stats:
        logger.debug(f"Dashboard stats cache hit for user {current_user.id}")
        return cached_stats

    try:
        if scope == SCOPE_PERSONAL:
            stats = await _personal_stats_async(db, current_user)
            cache.set(cache_key, stats, ttl=PERSONAL_TTL)
            return stats

        # Dashboard is a global aggregate view; preserve the legacy "superadmin
        # sees everything" semantics here. The narrowing default introduced for
        # /api/projects only applies to the projects browser.
        #
        # The sync `get_accessible_project_ids` runs on a sync Session bound to
        # THIS async session's connection via `db.run_sync(...)`, inside the
        # same transaction without a second connection.
        accessible_ids = await db.run_sync(
            lambda sync_db: get_accessible_project_ids(
                sync_db, current_user, include_all_private=True
            )
        )

        if accessible_ids is not None and not accessible_ids:
            stats = _overview_stats(0, 0, 0, 0, 0, 0)
            cache.set(cache_key, stats, ttl=OVERVIEW_TTL)
            return stats

        # All counters come from the precomputed project_summaries table.
        sums = await read_dashboard_sum_async(db, accessible_ids, period="overall")

        # `project_count` from project_summaries reflects rows that have been
        # precomputed at least once. For brand-new projects we'd undercount
        # until the next recompute cycle — fall back to a direct count when
        # the precomputed row count looks suspiciously low.
        project_count = sums["project_count"]
        if accessible_ids is None:
            # Soft-deleted projects and creation-wizard drafts are excluded,
            # as in project_summaries and in get_accessible_project_ids;
            # counting them showed more projects on the tile than the
            # projects list holds.
            true_total = (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM projects "
                        "WHERE deleted_at IS NULL AND NOT is_wizard_draft"
                    )
                )
            ).scalar() or 0
            if project_count < true_total:
                project_count = int(true_total)
        else:
            true_total = len(accessible_ids)
            if project_count < true_total:
                project_count = int(true_total)

        # Every counter is the sum of the precomputed project rows. Projects
        # without a row yet (created since the last refresh, or a fresh
        # database before its first refresh) are counted live and added, so
        # they neither show as zero nor make the endpoint recount projects
        # that already have their numbers. Before, a zero sum sent the
        # evaluation count into a live scan over every accessible project,
        # past the statement timeout on a large database.
        task_count = int(sums["total_tasks"])
        annotation_count = int(sums["annotations_count"])
        generations_count = int(sums["generations_count"])
        evaluations_count = int(sums["evaluation_pairs_count"])

        unsummarized = await unsummarized_project_ids_async(
            db, accessible_ids, period="overall"
        )
        if unsummarized:
            live = await _live_dashboard_counts_async(db, unsummarized)
            task_count += live["total_tasks"]
            annotation_count += live["annotations_count"]
            generations_count += live["generations_count"]
            evaluations_count += await _live_evaluations_count_async(db, unsummarized)

        stats = _overview_stats(
            project_count,
            task_count,
            annotation_count,
            generations_count,
            evaluations_count,
            await _analyses_count_async(db, accessible_ids) if experiments else 0,
        )

        cache.set(cache_key, stats, ttl=OVERVIEW_TTL)
        logger.debug(f"Dashboard stats cached for user {current_user.id}")

        return stats

    except Exception as e:
        # Never answer zeros as if they were real counts: when the live
        # fallback above runs into the statement timeout (project_summaries
        # empty, large task_evaluations table) the dashboard used to show
        # "0 projects" while dozens existed. A 503 lets the client show the
        # tiles as unavailable and retry; nothing is cached, so the next
        # request tries again.
        logger.error(f"Error getting dashboard stats: {e!r}")
        raise HTTPException(
            status_code=503,
            detail="Dashboard statistics are temporarily unavailable.",
        )
