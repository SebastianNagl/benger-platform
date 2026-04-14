"""
Dashboard and analytics endpoints.
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from redis_cache import RedisCache
from routers.projects.helpers import get_accessible_project_ids

logger = logging.getLogger(__name__)

# Initialize cache
cache = RedisCache()

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


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
    """
    org_context = request.headers.get("X-Organization-Context")

    # Create cache key based on user ID and org context
    cache_key = f"dashboard_stats:{current_user.id}:{org_context or 'private'}"

    # Try to get from cache first
    cached_stats = cache.get(cache_key)
    if cached_stats:
        logger.debug(f"Dashboard stats cache hit for user {current_user.id}")
        return cached_stats

    try:
        accessible_ids = get_accessible_project_ids(db, current_user, org_context)

        if accessible_ids is not None and not accessible_ids:
            # No accessible projects - return zeros
            stats = {
                "project_count": 0,
                "task_count": 0,
                "annotation_count": 0,
                "projects_with_generations": 0,
                "projects_with_evaluations": 0,
            }
            cache.set(cache_key, stats, ttl=300)
            return stats

        if accessible_ids is None:
            # Superadmin: see all projects
            stats_query = text(
                """
                SELECT
                    (SELECT COUNT(*) FROM projects) as project_count,
                    (SELECT COUNT(*) FROM tasks) as task_count,
                    (SELECT COUNT(*) FROM annotations WHERE jsonb_array_length(result) > 0 AND was_cancelled = false) as annotation_count,
                    (SELECT COUNT(*) FROM generations) as projects_with_generations,
                    (SELECT COUNT(*) FROM task_evaluations) as projects_with_evaluations
            """
            )
            result = db.execute(stats_query).fetchone()
        else:
            # Scoped to accessible project IDs
            placeholders = ", ".join([f":pid_{i}" for i in range(len(accessible_ids))])
            stats_query_str = f"""
                WITH accessible_projects AS (
                    SELECT p.id FROM projects p WHERE p.id IN ({placeholders})
                )
                SELECT
                    (SELECT COUNT(*) FROM accessible_projects) as project_count,
                    (SELECT COUNT(*) FROM tasks t
                     INNER JOIN accessible_projects ap ON t.project_id = ap.id) as task_count,
                    (SELECT COUNT(*) FROM annotations a
                     INNER JOIN tasks t ON a.task_id = t.id
                     INNER JOIN accessible_projects ap ON t.project_id = ap.id
                     WHERE jsonb_array_length(a.result) > 0 AND a.was_cancelled = false) as annotation_count,
                    (SELECT COUNT(*) FROM generations g
                     INNER JOIN tasks t ON g.task_id = t.id
                     INNER JOIN accessible_projects ap ON t.project_id = ap.id) as projects_with_generations,
                    (SELECT COUNT(*) FROM task_evaluations te
                     INNER JOIN evaluation_runs er ON te.evaluation_id = er.id
                     INNER JOIN accessible_projects ap ON er.project_id = ap.id) as projects_with_evaluations
            """
            bind_params = {f"pid_{i}": pid for i, pid in enumerate(accessible_ids)}
            stats_query = text(stats_query_str).bindparams(**bind_params)
            result = db.execute(stats_query).fetchone()

        stats = {
            "project_count": result.project_count if result else 0,
            "task_count": result.task_count if result else 0,
            "annotation_count": result.annotation_count if result else 0,
            "projects_with_generations": result.projects_with_generations if result else 0,
            "projects_with_evaluations": result.projects_with_evaluations if result else 0,
        }

        # Cache the results for 5 minutes (dashboard stats don't change frequently)
        cache.set(cache_key, stats, ttl=300)
        logger.debug(f"Dashboard stats cached for user {current_user.id}")

        return stats

    except Exception as e:
        logger.error(f"Error getting dashboard stats: {str(e)}")
        # Return default values on error
        return {
            "project_count": 0,
            "task_count": 0,
            "annotation_count": 0,
            "projects_with_generations": 0,
            "projects_with_evaluations": 0,
        }
