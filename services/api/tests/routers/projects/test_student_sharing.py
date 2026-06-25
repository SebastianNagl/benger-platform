"""Integration tests for the student exam-sharing + view-mode endpoints (#35).

Drives the security-critical share lifecycle (create → join with consent →
roster → withdraw / evict), the password + lifecycle gates, and the
write-once kind/origin + preferred_ui_mode plumbing through the real async
HTTP stack.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import User
from project_models import Project, ProjectShareMember


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


async def _make_user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"student-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Student",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_exam(db, owner) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title="Probeklausur BGB AT",
        created_by=owner.id,
        is_private=True,
        kind="exam",
        origin="student",
    )
    db.add(p)
    await db.commit()
    return p


@pytest.mark.integration
@pytest.mark.asyncio
async def test_share_lifecycle_join_roster_withdraw(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    invitee = await _make_user(async_test_db)
    exam = await _make_exam(async_test_db, owner)

    # Owner mints a share link.
    with _as_user(owner):
        r = await async_test_client.post(
            f"/api/projects/{exam.id}/shares", json={"password": "klausur2026"}
        )
        assert r.status_code == 201, r.text
        token = r.json()["token"]
        assert token and len(token) >= 20  # urlsafe(32) entropy

    # Invitee cannot join with the wrong password.
    with _as_user(invitee):
        r = await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "wrong", "gdpr_consent": True},
        )
        assert r.status_code == 403

        # Joining requires consent.
        r = await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "klausur2026", "gdpr_consent": False},
        )
        assert r.status_code == 400

        # Correct password + consent → joined.
        r = await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "klausur2026", "gdpr_consent": True},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "joined"

    # Owner sees the consented invitee on the roster.
    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{exam.id}/shares/roster")
        assert r.status_code == 200
        roster = r.json()
        assert len(roster) == 1
        assert roster[0]["user_id"] == invitee.id

    # Invitee withdraws (GDPR) → roster empties.
    with _as_user(invitee):
        r = await async_test_client.delete(f"/api/shares/{token}/membership")
        assert r.status_code == 204
    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{exam.id}/shares/roster")
        assert r.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoked_link_blocks_join(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    invitee = await _make_user(async_test_db)
    exam = await _make_exam(async_test_db, owner)

    with _as_user(owner):
        r = await async_test_client.post(
            f"/api/projects/{exam.id}/shares", json={"password": "pw12"}
        )
        share_id = r.json()["id"]
        token = r.json()["token"]
        r = await async_test_client.delete(
            f"/api/projects/{exam.id}/shares/{share_id}"
        )
        assert r.status_code == 204

    with _as_user(invitee):
        r = await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "pw12", "gdpr_consent": True},
        )
        assert r.status_code == 410  # gone


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_uses_enforced(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    a = await _make_user(async_test_db)
    b = await _make_user(async_test_db)
    exam = await _make_exam(async_test_db, owner)

    with _as_user(owner):
        r = await async_test_client.post(
            f"/api/projects/{exam.id}/shares",
            json={"password": "pw12", "max_uses": 1},
        )
        token = r.json()["token"]

    with _as_user(a):
        r = await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "pw12", "gdpr_consent": True},
        )
        assert r.status_code == 200
    with _as_user(b):
        r = await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "pw12", "gdpr_consent": True},
        )
        assert r.status_code == 410  # cap reached


@pytest.mark.integration
@pytest.mark.asyncio
async def test_owner_can_evict_member(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    invitee = await _make_user(async_test_db)
    exam = await _make_exam(async_test_db, owner)

    with _as_user(owner):
        token = (
            await async_test_client.post(
                f"/api/projects/{exam.id}/shares", json={"password": "pw12"}
            )
        ).json()["token"]
    with _as_user(invitee):
        await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "pw12", "gdpr_consent": True},
        )
    with _as_user(owner):
        r = await async_test_client.delete(
            f"/api/projects/{exam.id}/shares/roster/{invitee.id}"
        )
        assert r.status_code == 204
        r = await async_test_client.get(f"/api/projects/{exam.id}/shares/roster")
        assert r.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preferred_ui_mode_endpoint_persists_without_side_effects(
    async_test_client, async_test_db
):
    user = await _make_user(async_test_db)
    with _as_user(user):
        r = await async_test_client.put(
            "/api/auth/me/ui-mode", json={"preferred_ui_mode": "student"}
        )
        assert r.status_code == 200
        assert r.json()["preferred_ui_mode"] == "student"

    # Persisted on the row; the dedicated endpoint must NOT stamp profile
    # confirmation (that side effect belongs to PUT /profile only).
    row = (
        await async_test_db.execute(select(User).where(User.id == user.id))
    ).scalar_one()
    assert row.preferred_ui_mode == "student"
    assert row.profile_confirmed_at is None
    assert not row.mandatory_profile_completed


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dashboard_reads_are_valid_sql(async_test_client, async_test_db):
    """Score-history (.as_float on JSON) + retention (CASE) must execute.

    These power the dashboard charts; both previously risked a Postgres error
    (JSONB-only accessor / bool->float cast). Empty data should yield [].
    """
    user = await _make_user(async_test_db)
    with _as_user(user):
        r = await async_test_client.get("/api/student/score-history")
        assert r.status_code == 200
        assert r.json() == []
        r = await async_test_client.get("/api/student/retention")
        assert r.status_code == 200
        assert r.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_srs_stats_empty_deck(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    deck = Project(
        id=str(uuid.uuid4()),
        title="Deck",
        created_by=owner.id,
        is_private=True,
        kind="flashcard_deck",
        origin="student",
    )
    async_test_db.add(deck)
    await async_test_db.commit()
    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{deck.id}/srs/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0 and body["due_today"] == 0
        r = await async_test_client.get(f"/api/projects/{deck.id}/srs/due")
        assert r.status_code == 200
        assert r.json() == {"cards": [], "total": 0}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kind_origin_write_once_on_create(async_test_client, async_test_db):
    user = await _make_user(async_test_db)
    with _as_user(user):
        r = await async_test_client.post(
            "/api/projects/",
            json={
                "title": "Deck",
                "is_private": True,
                "kind": "flashcard_deck",
                "origin": "student",
            },
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["kind"] == "flashcard_deck"
        assert body["origin"] == "student"
