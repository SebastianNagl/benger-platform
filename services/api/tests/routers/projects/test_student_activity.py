"""Integration tests for GET /api/student/activity (the Lernstatistik heatmaps).

- flashcard reviews are counted per calendar day, cut in the requested time zone;
- exam submissions come back once per (day, exam project), cancelled
  annotations, non-exam projects, soft-deleted exams and other users excluded;
- rows older than the window are dropped; an unknown time zone is a 422.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from models import User
from project_models import Annotation, FlashcardReview, Project, Task


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


async def _make_project(db, owner, *, kind, deleted=False) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=f"Projekt {kind}",
        created_by=owner.id,
        is_private=True,
        kind=kind,
        origin="student",
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db.add(p)
    await db.flush()
    return p


async def _make_task(db, project, inner_id=1) -> Task:
    t = Task(id=str(uuid.uuid4()), project_id=project.id, inner_id=inner_id, data={"text": "x"})
    db.add(t)
    await db.flush()
    return t


async def _review(db, task, user, project, reviewed_at) -> None:
    db.add(
        FlashcardReview(
            id=str(uuid.uuid4()),
            task_id=task.id,
            user_id=user.id,
            project_id=project.id,
            mode="quick",
            rating="good",
            reviewed_at=reviewed_at,
        )
    )
    await db.flush()


async def _submit(db, task, user, created_at, *, cancelled=False) -> None:
    db.add(
        Annotation(
            id=str(uuid.uuid4()),
            task_id=task.id,
            project_id=task.project_id,
            completed_by=user.id,
            result=[],
            was_cancelled=cancelled,
            created_at=created_at,
        )
    )
    await db.flush()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_activity_empty(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    with _as_user(user):
        r = await async_test_client.get("/api/student/activity")
    assert r.status_code == 200
    assert r.json() == {"flashcards": [], "exams": []}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_activity_counts_reviews_per_local_day(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    deck = await _make_project(async_test_db, user, kind="flashcard_collection")
    card = await _make_task(async_test_db, deck)
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=3)
    # 23:30 UTC is already the next day in Berlin (UTC+1 / +2).
    late = base.replace(hour=23, minute=30)
    await _review(async_test_db, card, user, deck, base)
    await _review(async_test_db, card, user, deck, base + timedelta(minutes=5))
    await _review(async_test_db, card, user, deck, late)
    # Outside the window and another user's review: both ignored.
    await _review(async_test_db, card, user, deck, base - timedelta(days=400))
    other = await _make_user(async_test_db)
    await _review(async_test_db, card, other, deck, base)
    await async_test_db.commit()

    day = base.date()
    with _as_user(user):
        r = await async_test_client.get("/api/student/activity")
        assert r.status_code == 200
        assert r.json()["flashcards"] == [{"day": day.isoformat(), "reviews": 3}]

        r = await async_test_client.get("/api/student/activity", params={"tz": "Europe/Berlin"})
        assert r.status_code == 200
        assert r.json()["flashcards"] == [
            {"day": day.isoformat(), "reviews": 2},
            {"day": (day + timedelta(days=1)).isoformat(), "reviews": 1},
        ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_activity_lists_submitted_exams_per_day(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    exam = await _make_project(async_test_db, user, kind="exam")
    t1 = await _make_task(async_test_db, exam, 1)
    t2 = await _make_task(async_test_db, exam, 2)
    deck = await _make_project(async_test_db, user, kind="flashcard_collection")
    deck_task = await _make_task(async_test_db, deck)
    deleted = await _make_project(async_test_db, user, kind="exam", deleted=True)
    deleted_task = await _make_task(async_test_db, deleted)
    cancelled = await _make_project(async_test_db, user, kind="exam")
    cancelled_task = await _make_task(async_test_db, cancelled)

    when = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=8)
    # Two tasks of the same exam on the same day collapse into one row.
    await _submit(async_test_db, t1, user, when)
    await _submit(async_test_db, t2, user, when + timedelta(hours=1))
    await _submit(async_test_db, deck_task, user, when)
    await _submit(async_test_db, deleted_task, user, when)
    await _submit(async_test_db, cancelled_task, user, when, cancelled=True)
    await async_test_db.commit()

    with _as_user(user):
        r = await async_test_client.get("/api/student/activity")
    assert r.status_code == 200
    assert r.json()["exams"] == [{"day": when.date().isoformat(), "project_id": exam.id}]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_activity_rejects_unknown_time_zone(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    with _as_user(user):
        r = await async_test_client.get("/api/student/activity", params={"tz": "Mars/Olympus"})
    assert r.status_code == 422
