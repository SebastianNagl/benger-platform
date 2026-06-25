"""Read-only spaced-repetition (SRS) endpoints for flashcard decks (issue #35).

A deck is a project and each card is a task; ``FlashcardSrsState`` holds the
per-user SM-2 schedule. This router is **read-only** — it answers "what's due"
and "deck stats". The SM-2 write path (computing the next schedule from a
rating) is proprietary and lives in the extended ``flashcards`` router/worker;
keeping the algorithm out of platform is the open-core split (platform owns the
persistence + generic reads, extended owns the scheduling logic).

Access is the standard project-access check — decks are the student's own
private projects (sharing applies to exams, not decks).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from database import get_async_db
from project_models import FlashcardSrsState, Task

from routers.projects.deps import ProjectAccess, require_project_access

router = APIRouter()


@router.get("/{project_id}/srs/due")
async def get_due_cards(
    project_id: str,
    limit: int = Query(50, ge=1, le=500),
    access: ProjectAccess = Depends(require_project_access()),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Return the task ids of cards due for review *now* for the current user.

    "Due" = a never-seen card (no SRS row yet, i.e. state new) OR a card whose
    ``due_at`` has passed. Ordered new-cards-last so a session front-loads
    review cards (the cards at risk of being forgotten), matching Anki.
    """
    now = datetime.now(timezone.utc)
    uid = str(current_user.id)

    stmt = (
        select(Task.id, FlashcardSrsState.due_at, FlashcardSrsState.state)
        .select_from(Task)
        .outerjoin(
            FlashcardSrsState,
            (FlashcardSrsState.task_id == Task.id)
            & (FlashcardSrsState.user_id == uid),
        )
        .where(
            Task.project_id == project_id,
            or_(
                FlashcardSrsState.id.is_(None),  # never reviewed -> new -> due
                FlashcardSrsState.due_at.is_(None),
                FlashcardSrsState.due_at <= now,
            ),
        )
        # Review cards (have a due date) before brand-new cards.
        .order_by(FlashcardSrsState.due_at.is_(None), FlashcardSrsState.due_at.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return {
        "project_id": project_id,
        "due_count": len(rows),
        "task_ids": [r.id for r in rows],
    }


@router.get("/{project_id}/srs/stats")
async def get_srs_stats(
    project_id: str,
    access: ProjectAccess = Depends(require_project_access()),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Per-deck SRS summary for the current user: card counts by state + due.

    ``new`` counts cards the user has never reviewed (no SRS row) plus rows
    explicitly in the ``new`` state, so it stays correct on a freshly imported
    deck before any review has written state rows.
    """
    now = datetime.now(timezone.utc)
    uid = str(current_user.id)

    total_cards = (
        await db.execute(
            select(func.count(Task.id)).where(Task.project_id == project_id)
        )
    ).scalar_one()

    # Cards with an SRS row, bucketed by state.
    state_rows = (
        await db.execute(
            select(FlashcardSrsState.state, func.count(FlashcardSrsState.id))
            .where(
                FlashcardSrsState.project_id == project_id,
                FlashcardSrsState.user_id == uid,
            )
            .group_by(FlashcardSrsState.state)
        )
    ).all()
    by_state = {state: count for state, count in state_rows}
    seen = sum(by_state.values())

    due_count = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .outerjoin(
                FlashcardSrsState,
                (FlashcardSrsState.task_id == Task.id)
                & (FlashcardSrsState.user_id == uid),
            )
            .where(
                Task.project_id == project_id,
                or_(
                    FlashcardSrsState.id.is_(None),
                    FlashcardSrsState.due_at.is_(None),
                    FlashcardSrsState.due_at <= now,
                ),
            )
        )
    ).scalar_one()

    return {
        "project_id": project_id,
        "total_cards": total_cards,
        # never-seen cards collapse into "new" alongside explicit new-state rows
        "new": (total_cards - seen) + by_state.get("new", 0),
        "learning": by_state.get("learning", 0),
        "review": by_state.get("review", 0),
        "relearning": by_state.get("relearning", 0),
        "due_now": due_count,
    }
