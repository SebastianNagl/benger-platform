"""
Dashboard and analytics endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import User, require_user
from database import get_async_db
from models import Generation
from project_models import Annotation, Task
from redis_cache import RedisCache
from routers.projects.helpers import get_accessible_project_ids
from aggregate_summaries import (
    count_eval_pairs_by_project_async,
    read_dashboard_sum_async,
    unsummarized_project_ids_async,
)

logger = logging.getLogger(__name__)

# Initialize cache
cache = RedisCache()

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


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


@router.get("/stats")
async def get_dashboard_stats(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Returns dashboard statistics scoped to the user's organization context:
    - project_count: Total projects accessible to user
    - task_count: Total tasks (issues) across all accessible projects
    - projects_with_generations: Projects that have LLM generated answers
    - projects_with_evaluations: Projects that have completed evaluations

    Reads from the precomputed `project_summaries` table (refreshed by the
    `recompute_aggregates` Celery beat task every hour). Brand-new projects
    that haven't been picked up by a refresh yet fall back to a live count
    so the dashboard never shows stale-zero. The existing 5-min Redis TTL
    smooths repeated requests in both cases. When the counts cannot be
    computed (database error or statement timeout) the endpoint answers 503
    rather than a set of zeros.
    """
    # The stats cover every project the user may reach through any of their
    # organizations; the selected organization of the client plays no part,
    # so the cache is keyed by user only (`v4`).
    cache_key = f"dashboard_stats:v4:{current_user.id}"

    cached_stats = cache.get(cache_key)
    if cached_stats:
        logger.debug(f"Dashboard stats cache hit for user {current_user.id}")
        return cached_stats

    try:
        # Dashboard is a global aggregate view; preserve the legacy "superadmin
        # sees everything" semantics here. The narrowing default introduced for
        # /api/projects only applies to the projects browser.
        #
        # `get_accessible_project_ids` is sync-only (sync `db.query`, lives in
        # the off-limits routers/projects/helpers.py with no async twin). Bridge
        # it onto a sync Session bound to THIS async session's connection via
        # `db.run_sync(...)` so it runs inside the same transaction without a
        # second connection. Lambda is needed because `include_all_private` is a
        # keyword-only-style arg the run_sync positional callable can't pass.
        accessible_ids = await db.run_sync(
            lambda sync_db: get_accessible_project_ids(
                sync_db, current_user, include_all_private=True
            )
        )

        if accessible_ids is not None and not accessible_ids:
            stats = {
                "project_count": 0,
                "task_count": 0,
                "annotation_count": 0,
                "projects_with_generations": 0,
                "projects_with_evaluations": 0,
            }
            cache.set(cache_key, stats, ttl=300)
            return stats

        # All counters come from the precomputed project_summaries table.
        sums = await read_dashboard_sum_async(db, accessible_ids, period="overall")

        # `project_count` from project_summaries reflects rows that have been
        # precomputed at least once. For brand-new projects we'd undercount
        # until the next recompute cycle — fall back to a direct count when
        # the precomputed row count looks suspiciously low.
        project_count = sums["project_count"]
        if accessible_ids is None:
            # Soft-deleted projects are excluded, as in project_summaries and
            # in get_accessible_project_ids; counting them showed more
            # projects on the tile than the projects list holds.
            true_total = (
                await db.execute(
                    text("SELECT COUNT(*) FROM projects WHERE deleted_at IS NULL")
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

        stats = {
            "project_count": project_count,
            "task_count": task_count,
            "annotation_count": annotation_count,
            "projects_with_generations": generations_count,
            "projects_with_evaluations": evaluations_count,
        }

        cache.set(cache_key, stats, ttl=300)
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
