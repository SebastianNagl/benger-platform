"""
Dashboard and analytics endpoints.
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from models import EvaluationRun, Generation, ResponseGeneration
from project_models import Annotation, Task
from redis_cache import RedisCache
from routers.projects.helpers import (
    _metric_key_is_real,
    _scored_pairs_query,
    get_accessible_project_ids,
)
from services.aggregate_summaries import read_dashboard_sum

logger = logging.getLogger(__name__)

# Initialize cache
cache = RedisCache()

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _live_evaluations_count(db: Session, accessible_ids):
    """Fallback path when project_summaries hasn't been populated yet.

    Mirrors the original code at services/api/routers/dashboard.py — pulls
    (subject, metric) pairs and applies the noise filter in Python. Kept
    for new-project safety so brand-new projects show accurate stats before
    the next `recompute_aggregates` cycle.
    """
    pairs_q = _scored_pairs_query(db).distinct()
    if accessible_ids is not None:
        pairs_q = pairs_q.filter(EvaluationRun.project_id.in_(accessible_ids))
    return sum(1 for _pid, _sub, mk in pairs_q.all() if _metric_key_is_real(mk))


def _live_dashboard_counts(db: Session, accessible_ids):
    """Belt-and-braces live counts for tasks / annotations / generations
    when project_summaries hasn't been populated yet. Mirrors the per-
    project predicates in services.aggregate_summaries._compute_project_summary
    so the fallback values match what the beat task would write.

    Brand-new projects (created since the last recompute_aggregates cycle)
    have no project_summaries rows, so reads through read_dashboard_sum
    return 0 across the board. Without this fallback the dashboard would
    show flat-zero stats for hours until the 12h cron — confusing to users
    and a regression vs. the original live-counting implementation.
    """
    task_q = select(func.count(Task.id))
    ann_q = select(func.count(Annotation.id)).where(
        Annotation.was_cancelled == False,  # noqa: E712
        func.jsonb_array_length(Annotation.result) > 0,
    )
    gen_q = select(func.count(ResponseGeneration.id))
    if accessible_ids is not None:
        task_q = task_q.where(Task.project_id.in_(accessible_ids))
        ann_q = ann_q.where(Annotation.project_id.in_(accessible_ids))
        gen_q = gen_q.where(ResponseGeneration.project_id.in_(accessible_ids))

    return {
        "total_tasks": int(db.execute(task_q).scalar() or 0),
        "annotations_count": int(db.execute(ann_q).scalar() or 0),
        "generations_count": int(db.execute(gen_q).scalar() or 0),
    }


@router.get("/stats")
async def get_dashboard_stats(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Returns dashboard statistics scoped to the user's organization context:
    - project_count: Total projects accessible to user
    - task_count: Total tasks (issues) across all accessible projects
    - projects_with_generations: Projects that have LLM generated answers
    - projects_with_evaluations: Projects that have completed evaluations

    Reads from the precomputed `project_summaries` table (refreshed by the
    `recompute_aggregates` Celery beat task every 12h). Brand-new projects
    that haven't been picked up by a refresh yet fall back to a live count
    so the dashboard never shows stale-zero. The existing 5-min Redis TTL
    smooths repeated requests in both cases.
    """
    org_context = request.headers.get("X-Organization-Context")

    # `v3` bumps invalidate the old in-Python-aggregation cache values when
    # this deploy lands — see services.aggregate_summaries.read_dashboard_sum
    # for the new read shape.
    cache_key = f"dashboard_stats:v3:{current_user.id}:{org_context or 'private'}"

    cached_stats = cache.get(cache_key)
    if cached_stats:
        logger.debug(f"Dashboard stats cache hit for user {current_user.id}")
        return cached_stats

    try:
        accessible_ids = get_accessible_project_ids(db, current_user, org_context)

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
        sums = read_dashboard_sum(db, accessible_ids, period="overall")

        # `project_count` from project_summaries reflects rows that have been
        # precomputed at least once. For brand-new projects we'd undercount
        # until the next recompute cycle — fall back to a direct count when
        # the precomputed row count looks suspiciously low.
        project_count = sums["project_count"]
        if accessible_ids is None:
            true_total = db.execute(text("SELECT COUNT(*) FROM projects")).scalar() or 0
            if project_count < true_total:
                project_count = int(true_total)
        else:
            true_total = len(accessible_ids)
            if project_count < true_total:
                project_count = int(true_total)

        evaluations_count = sums["evaluation_pairs_count"]
        if evaluations_count == 0 and (
            accessible_ids is None or len(accessible_ids) > 0
        ):
            # Belt-and-braces: brand-new projects with no project_summaries
            # rows yet shouldn't render a flat zero if there ARE evaluations.
            evaluations_count = _live_evaluations_count(db, accessible_ids)

        task_count = int(sums["total_tasks"])
        annotation_count = int(sums["annotations_count"])
        generations_count = int(sums["generations_count"])

        # Same belt-and-braces for the other three counters: if any one of
        # them is 0 against a non-empty accessible_ids set, the corresponding
        # project_summaries rows haven't been populated yet for that scope.
        # Fall back to a live count to match what recompute_aggregates would
        # eventually write.
        if (
            (accessible_ids is None or len(accessible_ids) > 0)
            and (task_count == 0 or annotation_count == 0 or generations_count == 0)
        ):
            live = _live_dashboard_counts(db, accessible_ids)
            task_count = max(task_count, live["total_tasks"])
            annotation_count = max(annotation_count, live["annotations_count"])
            generations_count = max(generations_count, live["generations_count"])

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
        logger.error(f"Error getting dashboard stats: {str(e)}")
        return {
            "project_count": 0,
            "task_count": 0,
            "annotation_count": 0,
            "projects_with_generations": 0,
            "projects_with_evaluations": 0,
        }
