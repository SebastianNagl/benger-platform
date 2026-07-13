"""Personal student-dashboard reads (issue #35).

Generic, user-scoped reads over platform tables that the extended dashboard
widgets render:
- score-history: the current user's exam attempt scores over time (across their
  own student exam projects), feeding the ScoreOverTime chart.
- retention: flashcard "true retention" over time from the append-only
  ``flashcard_reviews`` log, feeding the RetentionChart.

Mounted at ``/api/student`` in ``main.py``. No proprietary logic — the extended
widgets own presentation; this only shapes the data.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from database import get_async_db
from models import TaskEvaluation
from project_models import Annotation, FlashcardReview, Project, Task
from routers.projects.helpers import attempt_score_from_metrics

router = APIRouter(prefix="/api/student", tags=["student-dashboard"])


@router.get("/score-history")
async def score_history(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    limit: int = Query(200, ge=1, le=1000),
):
    """The current user's exam attempt scores over time.

    One point per graded attempt on the user's own student exam projects
    (``origin='student'``, ``kind='exam'``): the unified 0..1 ``value`` of the
    evaluation attached to the user's annotation, extracted from the
    nested-canonical ``metrics`` shape via
    :func:`routers.projects.helpers.attempt_score_from_metrics` (no metric
    writer produces a top-level ``value``), with the project title and
    timestamp. Ascending by time so the chart plots a progress curve.
    """
    uid = str(current_user.id)
    stmt = (
        select(
            Project.id.label("project_id"),
            Project.title.label("title"),
            TaskEvaluation.metrics.label("metrics"),
            Annotation.created_at.label("attempted_at"),
        )
        .select_from(TaskEvaluation)
        .join(Annotation, Annotation.id == TaskEvaluation.annotation_id)
        .join(Task, Task.id == TaskEvaluation.task_id)
        .join(Project, Project.id == Task.project_id)
        .where(
            Annotation.completed_by == uid,
            Project.origin == "student",
            Project.kind == "exam",
        )
        .order_by(Annotation.created_at.asc(), TaskEvaluation.created_at.asc())
    )
    rows = (await db.execute(stmt)).all()
    out = []
    for r in rows:
        score = attempt_score_from_metrics(r.metrics)
        if score is None:
            continue
        out.append(
            {
                "project_id": r.project_id,
                "title": r.title,
                "score": score,
                "attempted_at": r.attempted_at.isoformat() if r.attempted_at else None,
            }
        )
        if len(out) >= limit:
            break
    return out


@router.get("/retention")
async def retention(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    days: int = Query(30, ge=1, le=365),
):
    """Flashcard "true retention" + review volume per day, last ``days`` days.

    True retention (Anki sense) = share of *review-state* card reviews rated
    Good/Easy (a lapse — Again — counts as a miss). Computed from the
    append-only ``flashcard_reviews`` log so it reflects history, not the
    mutable current SRS snapshot. Only reviews whose rating is a real grade are
    counted; ``project_id`` is left out so it spans all the user's decks.
    """
    uid = str(current_user.id)
    day = func.date_trunc("day", FlashcardReview.reviewed_at)
    # "again" = a miss; good/easy = a hit; "hard" is a borderline pass we count
    # as a hit (it still recalled the card), matching Anki's true-retention.
    # CASE (not a bool->float cast, which Postgres rejects).
    is_hit = func.sum(case((FlashcardReview.rating != "again", 1.0), else_=0.0))
    stmt = (
        select(
            day.label("day"),
            func.count(FlashcardReview.id).label("reviews"),
            is_hit.label("hits"),
        )
        .where(FlashcardReview.user_id == uid)
        .group_by(day)
        .order_by(day.asc())
    )
    rows = (await db.execute(stmt)).all()
    out = []
    for r in rows:
        reviews = r.reviews or 0
        hits = r.hits or 0
        out.append(
            {
                "day": r.day.isoformat() if r.day else None,
                "reviews": reviews,
                "retention": (hits / reviews) if reviews else None,
            }
        )
    return out
