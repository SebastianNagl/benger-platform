"""Integration tests for Anki-style daily card limits (issue #35).

Drives the per-(user, collection) caps through the real async HTTP stack:
- new_per_day caps how many never-seen cards enter the queue;
- a new card already introduced today no longer counts as new (log-derived);
- learning/relearning cards are EXEMPT from the caps;
- review_per_day also gates new cards (Anki-faithful "review gates new");
- the settings endpoint round-trips and NULL clears to the default.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from project_models import FlashcardReview, FlashcardSrsState, Project, Task
from models import User


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"student-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Student",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_deck(db, owner) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title="Stapel BGB AT",
        created_by=owner.id,
        is_private=True,
        kind="flashcard_collection",
        origin="student",
    )
    db.add(p)
    await db.flush()
    return p


async def _make_card(db, project, inner_id, *, front, deck=None) -> Task:
    data = {"front": front, "back": f"{front}-back", "tags": []}
    if deck:
        data["deck"] = deck
    t = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        inner_id=inner_id,
        data=data,
    )
    db.add(t)
    await db.flush()
    return t


async def _srs(db, task, user, project, *, state, due_at) -> FlashcardSrsState:
    s = FlashcardSrsState(
        id=str(uuid.uuid4()),
        task_id=task.id,
        user_id=user.id,
        project_id=project.id,
        state=state,
        due_at=due_at,
    )
    db.add(s)
    await db.flush()
    return s


async def _review(db, task, user, project, *, reviewed_at, rating="good") -> None:
    db.add(
        FlashcardReview(
            id=str(uuid.uuid4()),
            task_id=task.id,
            user_id=user.id,
            project_id=project.id,
            mode="quick",
            rating=rating,
            reviewed_at=reviewed_at,
        )
    )
    await db.flush()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_new_per_day_caps_the_due_queue(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner)
    for i in range(5):
        await _make_card(async_test_db, deck, i + 1, front=f"C{i+1}")
    await async_test_db.commit()

    with _as_user(owner):
        r = await async_test_client.put(
            f"/api/projects/{deck.id}/srs/settings",
            json={"new_per_day": 2, "review_per_day": 200},
        )
        assert r.status_code == 200, r.text

        due = (await async_test_client.get(f"/api/projects/{deck.id}/srs/due")).json()
        assert due["total"] == 2  # only 2 of 5 new cards

        stats = (
            await async_test_client.get(f"/api/projects/{deck.id}/srs/stats")
        ).json()
        assert stats["new_cap"] == 2
        assert stats["new_count"] == 5
        assert stats["new_available"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cards_introduced_today_no_longer_count_as_new(
    async_test_client, async_test_db
):
    now = datetime.now(timezone.utc)
    owner = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner)
    cards = [await _make_card(async_test_db, deck, i + 1, front=f"C{i+1}") for i in range(5)]
    # Two cards already introduced today: a review row dated now + learning state
    # not-yet-due (so they're neither "new" nor in the due learning slice).
    for c in cards[:2]:
        await _srs(
            async_test_db, c, owner, deck, state="learning", due_at=now + timedelta(minutes=10)
        )
        await _review(async_test_db, c, owner, deck, reviewed_at=now)
    await async_test_db.commit()

    with _as_user(owner):
        await async_test_client.put(
            f"/api/projects/{deck.id}/srs/settings",
            json={"new_per_day": 2, "review_per_day": 200},
        )
        due = (await async_test_client.get(f"/api/projects/{deck.id}/srs/due")).json()
        # Budget (2) already spent by today's 2 introductions → 0 new, despite 3 left.
        assert due["total"] == 0

        stats = (
            await async_test_client.get(f"/api/projects/{deck.id}/srs/stats")
        ).json()
        assert stats["new_introduced_today"] == 2
        assert stats["new_available"] == 0
        assert stats["new_count"] == 3  # the 2 introduced are now 'learning'


@pytest.mark.integration
@pytest.mark.asyncio
async def test_learning_cards_are_exempt_from_caps(async_test_client, async_test_db):
    now = datetime.now(timezone.utc)
    owner = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner)
    card = await _make_card(async_test_db, deck, 1, front="L1")
    await _srs(async_test_db, card, owner, deck, state="learning", due_at=now - timedelta(minutes=1))
    await async_test_db.commit()

    with _as_user(owner):
        # Hard zero on both caps — a due learning card must STILL appear.
        await async_test_client.put(
            f"/api/projects/{deck.id}/srs/settings",
            json={"new_per_day": 0, "review_per_day": 0},
        )
        due = (await async_test_client.get(f"/api/projects/{deck.id}/srs/due")).json()
        assert due["total"] == 1
        assert due["cards"][0]["front"] == "L1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_review_limit_gates_new_cards(async_test_client, async_test_db):
    """Anki-faithful: a review backlog that fills review_per_day suppresses new."""
    now = datetime.now(timezone.utc)
    owner = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner)
    # 3 due review-state cards (introduced on a prior day; not yet reviewed today).
    reviews = [await _make_card(async_test_db, deck, i + 1, front=f"R{i+1}") for i in range(3)]
    for c in reviews:
        await _srs(async_test_db, c, owner, deck, state="review", due_at=now - timedelta(hours=1))
    # 5 brand-new cards.
    news = [await _make_card(async_test_db, deck, 100 + i, front=f"N{i+1}") for i in range(5)]
    await async_test_db.commit()

    with _as_user(owner):
        # review cap = 3, exactly consumed by the 3 due reviews → 0 new.
        await async_test_client.put(
            f"/api/projects/{deck.id}/srs/settings",
            json={"new_per_day": 20, "review_per_day": 3},
        )
        due = (await async_test_client.get(f"/api/projects/{deck.id}/srs/due")).json()
        fronts = {c["front"] for c in due["cards"]}
        assert due["total"] == 3
        assert fronts == {"R1", "R2", "R3"}
        assert not any(f.startswith("N") for f in fronts)

        # Lift the review cap → new cards flow again (3 review + 5 new).
        await async_test_client.put(
            f"/api/projects/{deck.id}/srs/settings",
            json={"new_per_day": 20, "review_per_day": 200},
        )
        due2 = (await async_test_client.get(f"/api/projects/{deck.id}/srs/due")).json()
        assert due2["total"] == 8


@pytest.mark.integration
@pytest.mark.asyncio
async def test_settings_roundtrip_and_null_clears_to_default(
    async_test_client, async_test_db
):
    owner = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner)
    await async_test_db.commit()

    with _as_user(owner):
        r = await async_test_client.put(
            f"/api/projects/{deck.id}/srs/settings",
            json={"new_per_day": 7, "review_per_day": 50},
        )
        body = r.json()
        assert body["new_per_day"] == 7 and body["review_per_day"] == 50
        assert body["effective_new_per_day"] == 7

        got = (
            await async_test_client.get(f"/api/projects/{deck.id}/srs/settings")
        ).json()
        assert got["new_per_day"] == 7 and got["review_per_day"] == 50

        # Clearing falls back to the system defaults.
        cleared = (
            await async_test_client.put(
                f"/api/projects/{deck.id}/srs/settings",
                json={"new_per_day": None, "review_per_day": None},
            )
        ).json()
        assert cleared["new_per_day"] is None
        assert cleared["effective_new_per_day"] == body["new_per_day_default"]
        assert cleared["effective_review_per_day"] == body["review_per_day_default"]
