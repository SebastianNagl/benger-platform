"""Read-only spaced-repetition (SRS) endpoints for flashcard decks (issue #35).

A deck is a project and each card is a task; ``FlashcardSrsState`` holds the
per-user SM-2 schedule. This router is **read-only** for scheduling — it answers
"what's due" and "deck stats", and applies the per-user daily caps. The SM-2
write path (computing the next schedule from a rating) is proprietary and lives
in the extended ``flashcards`` router/worker; keeping the algorithm out of
platform is the open-core split (platform owns the persistence + generic reads +
the generic LIMIT, extended owns the scheduling logic and the settings UI).

Daily limits (Anki-style) are stored per-(user, collection) in
``FlashcardSrsSettings`` and enforced here, so the extended review UI needs no
queue logic — it just receives an already-capped queue.

Access is ``_require_deck_read_access`` — the owner, or a consented share member
studying a discovered deck.
"""

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from database import get_async_db
from project_models import (
    FlashcardReview,
    FlashcardSrsSettings,
    FlashcardSrsState,
    Project,
    Task,
)

from routers.projects.helpers import (
    check_project_accessible_async,
    get_org_context_from_request,
    get_student_read_access_async,
)

router = APIRouter()

# --- Daily-limit defaults + day rollover ------------------------------------ #
# Anki's own defaults; German law students coming from Anki expect these.
NEW_PER_DAY_DEFAULT = 20
REVIEW_PER_DAY_DEFAULT = 200
# Day boundary: 04:00 Europe/Berlin (Anki's default hour) so late-night cramming
# still counts as the previous day. Single-TZ audience → no per-user setting yet.
ROLLOVER_HOUR = 4
ROLLOVER_TZ = "Europe/Berlin"


async def _require_deck_read_access(
    project_id: str,
    request: Request,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
) -> Project:
    """Read access for a deck's SRS endpoints: standard project access OR a
    consented share member OR an active marketplace entitlement (issue #35 deck
    discovery + vendor marketplace).

    A joiner studying a shared deck — or a student who bought / was unlocked a
    vendor deck — is not the owner; they get participant-level read access via
    ``ProjectShareMember`` / ``MarketplaceEntitlement``. Kept as a local
    dependency so this stays OUT of the generic ``check_project_accessible``
    (which also gates exports/settings — see helpers.get_share_access_async).
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Deck not found")
    org_context = get_org_context_from_request(request)
    if await check_project_accessible_async(
        db, current_user, project_id, org_context, project=project
    ):
        return project
    if await get_student_read_access_async(db, current_user, project_id):
        return project
    raise HTTPException(status_code=403, detail="Access denied")


def _deck_scope_clause(deck: str | None):
    """SQL clause restricting cards to a deck *and its subdecks* (or all cards).

    A project (collection) holds cards whose ``data['deck']`` is a ``::``-nested
    Anki deck path (e.g. ``"Jura::BGB::AT"``). Scoping to ``"Jura::BGB"`` must
    include the deck itself **and** every subdeck (``"Jura::BGB::AT"``, …) but
    NOT a sibling like ``"Jura::BGBX"`` — hence the exact match OR the
    ``deck + "::"`` prefix. ``startswith(autoescape=True)`` escapes any ``%``/
    ``_`` in the user-supplied deck name. ``None``/empty selects the whole
    collection.
    """
    if not deck:
        return None
    # ``Task.data`` is typed as the generic SQLAlchemy ``JSON`` (the model's
    # JSONB switch keys off ``DATABASE_URL`` but the API sets ``DATABASE_URI``),
    # so the JSONB-only ``.astext`` accessor is unavailable — use the generic
    # ``.as_string()`` (same convention as shares.py / multi_field/run.py).
    col = Task.data["deck"].as_string()
    return or_(col == deck, col.startswith(deck + "::", autoescape=True))


def _srs_day_window(now_utc: datetime) -> tuple[datetime, datetime]:
    """Half-open ``[start, end)`` UTC range for the current SRS 'day'.

    The day rolls at ``ROLLOVER_HOUR`` local (``ROLLOVER_TZ``), so a review at
    01:00 counts toward the previous calendar day. ``zoneinfo`` makes the offset
    DST-correct (CET/CEST). Querying ``reviewed_at >= start AND < end`` (no
    ``DATE()`` cast) keeps the (user_id, reviewed_at) index usable.
    """
    tz = ZoneInfo(ROLLOVER_TZ)
    local = now_utc.astimezone(tz)
    anchor = (local - timedelta(hours=ROLLOVER_HOUR)).date()
    start_local = datetime(
        anchor.year, anchor.month, anchor.day, ROLLOVER_HOUR, tzinfo=tz
    )
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _settings_row(db: AsyncSession, uid: str, project_id: str):
    return (
        await db.execute(
            select(FlashcardSrsSettings).where(
                FlashcardSrsSettings.user_id == uid,
                FlashcardSrsSettings.project_id == project_id,
            )
        )
    ).scalar_one_or_none()


def _caps_from_row(row) -> tuple[int, int]:
    """(new_per_day, review_per_day) with system-default fallback for NULLs."""
    new_cap = (
        row.new_per_day
        if row and row.new_per_day is not None
        else NEW_PER_DAY_DEFAULT
    )
    review_cap = (
        row.review_per_day
        if row and row.review_per_day is not None
        else REVIEW_PER_DAY_DEFAULT
    )
    return new_cap, review_cap


async def _today_counts(
    db: AsyncSession,
    uid: str,
    project_id: str,
    scope,
    day_start: datetime,
    day_end: datetime,
) -> tuple[int, int]:
    """(new_introduced_today, reviews_today) for this user+project[+deck scope].

    Derived purely from the append-only review log:
    - a card is "introduced today" iff its FIRST-ever review (``MIN(reviewed_at)``)
      falls in today's window — Anki counts a new card once, at introduction;
    - "reviews today" counts review events in the window on cards introduced on a
      PRIOR day (``first_at < day_start``) — i.e. genuine reviews, excluding a
      new card's same-day introduction + learning steps (which belong to the new
      counter, not the review cap), matching Anki.
    """
    first_sub = (
        select(
            FlashcardReview.task_id.label("tid"),
            func.min(FlashcardReview.reviewed_at).label("first_at"),
        )
        .where(
            FlashcardReview.user_id == uid,
            FlashcardReview.project_id == project_id,
        )
        .group_by(FlashcardReview.task_id)
        .subquery()
    )

    new_stmt = select(func.count()).select_from(first_sub)
    if scope is not None:
        new_stmt = new_stmt.join(Task, Task.id == first_sub.c.tid).where(scope)
    new_stmt = new_stmt.where(
        first_sub.c.first_at >= day_start, first_sub.c.first_at < day_end
    )
    new_today = (await db.execute(new_stmt)).scalar_one()

    rev_stmt = (
        select(func.count())
        .select_from(FlashcardReview)
        .join(first_sub, first_sub.c.tid == FlashcardReview.task_id)
        .where(
            FlashcardReview.user_id == uid,
            FlashcardReview.project_id == project_id,
            FlashcardReview.reviewed_at >= day_start,
            FlashcardReview.reviewed_at < day_end,
            first_sub.c.first_at < day_start,
        )
    )
    if scope is not None:
        rev_stmt = rev_stmt.join(Task, Task.id == FlashcardReview.task_id).where(scope)
    reviews_today = (await db.execute(rev_stmt)).scalar_one()
    return new_today, reviews_today


@router.get("/{project_id}/srs/due")
async def get_due_cards(
    project_id: str,
    limit: int = Query(50, ge=1, le=500),
    deck: str | None = Query(
        None,
        description="Restrict to a deck path and its subdecks within the collection.",
    ),
    _access: Project = Depends(_require_deck_read_access),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Return the cards due for the current user, respecting the daily caps.

    Three slices, concatenated then page-capped:
    1. learning/relearning due cards — UNCAPPED (Anki exempts intraday learning);
    2. review due cards — capped at the remaining ``review_per_day`` budget;
    3. new (never-seen) cards — capped at the remaining ``new_per_day`` budget
       AND, Anki-faithfully, by the review budget left after the review slice
       (so a large review backlog suppresses new cards).

    ``deck`` optionally scopes the queue to one deck (and its subdecks).
    """
    now = datetime.now(timezone.utc)
    uid = str(current_user.id)
    scope = _deck_scope_clause(deck)
    scope_filter = [scope] if scope is not None else []

    day_start, day_end = _srs_day_window(now)
    new_cap, review_cap = _caps_from_row(await _settings_row(db, uid, project_id))
    new_today, reviews_today = await _today_counts(
        db, uid, project_id, scope, day_start, day_end
    )

    def _card(r):
        data = r.data or {}
        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = tags.split()
        return {
            "task_id": r.id,
            "front": str(data.get("front") or data.get("Vorderseite") or ""),
            "back": str(data.get("back") or data.get("Rückseite") or ""),
            "tags": [str(t) for t in tags],
            "due_at": r.due_at.isoformat() if r.due_at else None,
        }

    # Slices 1+2: due, non-new cards (bounded by what's actually due).
    due_rows = (
        await db.execute(
            select(
                Task.id, Task.data, FlashcardSrsState.due_at, FlashcardSrsState.state
            )
            .select_from(Task)
            .join(
                FlashcardSrsState,
                (FlashcardSrsState.task_id == Task.id)
                & (FlashcardSrsState.user_id == uid),
            )
            .where(
                Task.project_id == project_id,
                FlashcardSrsState.state.in_(("learning", "relearning", "review")),
                FlashcardSrsState.due_at.isnot(None),
                FlashcardSrsState.due_at <= now,
                *scope_filter,
            )
            .order_by(FlashcardSrsState.due_at.asc())
        )
    ).all()
    learning_rows = [r for r in due_rows if r.state in ("learning", "relearning")]
    review_rows = [r for r in due_rows if r.state == "review"]

    remaining_review = max(0, review_cap - reviews_today)
    review_capped = review_rows[:remaining_review]
    review_budget_after = max(0, remaining_review - len(review_capped))

    remaining_new = max(0, new_cap - new_today)
    effective_new = min(remaining_new, review_budget_after)

    new_rows = []
    if effective_new > 0:
        new_rows = (
            await db.execute(
                select(Task.id, Task.data, FlashcardSrsState.due_at)
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
                        FlashcardSrsState.state == "new",
                    ),
                    *scope_filter,
                )
                .order_by(Task.inner_id.asc())
                .limit(effective_new)
            )
        ).all()

    ordered = learning_rows + review_capped + list(new_rows)
    cards = [_card(r) for r in ordered][:limit]
    return {"cards": cards, "total": len(cards)}


@router.get("/{project_id}/srs/stats")
async def get_srs_stats(
    project_id: str,
    deck: str | None = Query(
        None,
        description="Restrict to a deck path and its subdecks within the collection.",
    ),
    _access: Project = Depends(_require_deck_read_access),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Per-deck SRS summary for the current user: counts, caps, and what's
    actually available today under the daily limits.

    ``new_available``/``review_available`` mirror the capped ``/due`` queue so the
    review-session header matches what the student will be shown.
    """
    now = datetime.now(timezone.utc)
    uid = str(current_user.id)
    scope = _deck_scope_clause(deck)
    scope_filter = [scope] if scope is not None else []

    total_cards = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id, *scope_filter
            )
        )
    ).scalar_one()

    # Cards with an SRS row, bucketed by state.
    state_stmt = select(
        FlashcardSrsState.state, func.count(FlashcardSrsState.id)
    ).where(
        FlashcardSrsState.project_id == project_id,
        FlashcardSrsState.user_id == uid,
    )
    if scope is not None:
        state_stmt = state_stmt.join(
            Task, Task.id == FlashcardSrsState.task_id
        ).where(scope)
    state_rows = (
        await db.execute(state_stmt.group_by(FlashcardSrsState.state))
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
                *scope_filter,
            )
        )
    ).scalar_one()

    # Due review-state cards only (for the review-gates-new budget calculation).
    due_review_count = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .join(
                FlashcardSrsState,
                (FlashcardSrsState.task_id == Task.id)
                & (FlashcardSrsState.user_id == uid),
            )
            .where(
                Task.project_id == project_id,
                FlashcardSrsState.state == "review",
                FlashcardSrsState.due_at.isnot(None),
                FlashcardSrsState.due_at <= now,
                *scope_filter,
            )
        )
    ).scalar_one()

    # Due learning/relearning cards (uncapped slice — exempt from the limits).
    due_learning_count = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .join(
                FlashcardSrsState,
                (FlashcardSrsState.task_id == Task.id)
                & (FlashcardSrsState.user_id == uid),
            )
            .where(
                Task.project_id == project_id,
                FlashcardSrsState.state.in_(("learning", "relearning")),
                FlashcardSrsState.due_at.isnot(None),
                FlashcardSrsState.due_at <= now,
                *scope_filter,
            )
        )
    ).scalar_one()

    new_count = (total_cards - seen) + by_state.get("new", 0)
    learning = by_state.get("learning", 0) + by_state.get("relearning", 0)
    review = by_state.get("review", 0)

    # Daily-limit-aware availability (mirrors /due).
    day_start, day_end = _srs_day_window(now)
    new_cap, review_cap = _caps_from_row(await _settings_row(db, uid, project_id))
    new_today, reviews_today = await _today_counts(
        db, uid, project_id, scope, day_start, day_end
    )
    remaining_review = max(0, review_cap - reviews_today)
    review_shown = min(due_review_count, remaining_review)
    review_budget_after = max(0, remaining_review - review_shown)
    remaining_new = max(0, new_cap - new_today)
    new_available = min(remaining_new, review_budget_after, new_count)
    # Total cards the capped /due queue will actually serve right now (learning is
    # exempt, reviews capped, new gated) — drives the "start session" gating so a
    # 0-budget deck doesn't offer an empty session.
    due_available = due_learning_count + review_shown + new_available

    return {
        # Frontend SrsStats contract.
        "total": total_cards,
        "due_today": due_count,
        "new_count": new_count,
        "learning": learning,
        "review": review,
        # Daily-limit fields (issue #35 caps).
        "new_cap": new_cap,
        "review_cap": review_cap,
        "new_introduced_today": new_today,
        "reviews_today": reviews_today,
        "new_available": new_available,
        "review_available": remaining_review,
        "due_available": due_available,
    }


# --- Per-(user, collection) daily-limit settings ---------------------------- #
class SrsSettingsBody(BaseModel):
    """Daily caps to set; ``None`` clears the override (falls back to default)."""

    new_per_day: int | None = Field(None, ge=0, le=9999)
    review_per_day: int | None = Field(None, ge=0, le=9999)


def _settings_payload(row) -> dict:
    new_cap, review_cap = _caps_from_row(row)
    return {
        "new_per_day": row.new_per_day if row else None,
        "review_per_day": row.review_per_day if row else None,
        "new_per_day_default": NEW_PER_DAY_DEFAULT,
        "review_per_day_default": REVIEW_PER_DAY_DEFAULT,
        "effective_new_per_day": new_cap,
        "effective_review_per_day": review_cap,
    }


@router.get("/{project_id}/srs/settings")
async def get_srs_settings(
    project_id: str,
    _access: Project = Depends(_require_deck_read_access),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The current user's daily caps for this collection (or the defaults)."""
    row = await _settings_row(db, str(current_user.id), project_id)
    return _settings_payload(row)


@router.put("/{project_id}/srs/settings")
async def update_srs_settings(
    project_id: str,
    body: SrsSettingsBody,
    _access: Project = Depends(_require_deck_read_access),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Upsert the current user's daily caps for this collection.

    The row is keyed by ``user_id`` = the caller, so a share member only ever
    edits their OWN pace on a deck they joined — deck read access suffices.
    """
    uid = str(current_user.id)
    row = await _settings_row(db, uid, project_id)
    if row is None:
        row = FlashcardSrsSettings(
            id=str(uuid.uuid4()), user_id=uid, project_id=project_id
        )
        db.add(row)
    row.new_per_day = body.new_per_day
    row.review_per_day = body.review_per_day
    await db.commit()
    await db.refresh(row)
    return _settings_payload(row)
