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


async def _make_deck(db, owner, *, title="Stapel BGB AT", kind="flashcard_collection") -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=title,
        created_by=owner.id,
        is_private=True,
        kind=kind,
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


@pytest.mark.asyncio
async def test_vertretbar_onboarding_endpoint_persists_without_side_effects(
    async_test_client, async_test_db
):
    """POST /me/vertretbar-onboarding stamps the completion timestamp (extended
    plan-choice modal gate) and, like the ui-mode endpoint, must NOT trigger any
    profile-confirmation side effects."""
    user = await _make_user(async_test_db)
    assert user.vertretbar_onboarding_completed_at is None

    with _as_user(user):
        r = await async_test_client.post("/api/auth/me/vertretbar-onboarding")
        assert r.status_code == 200
        assert r.json()["vertretbar_onboarding_completed_at"] is not None

    row = (
        await async_test_db.execute(select(User).where(User.id == user.id))
    ).scalar_one()
    assert row.vertretbar_onboarding_completed_at is not None
    assert row.profile_confirmed_at is None
    assert not row.mandatory_profile_completed


@pytest.mark.asyncio
async def test_auth_me_surfaces_vertretbar_onboarding_flag(
    async_test_client, async_test_db
):
    """The one-time modal gates on user.vertretbar_onboarding_completed_at read
    from the user-hydration endpoints, so both /auth/me (fallback) and
    /auth/me/contexts (primary) must carry the flag — null before, set after."""
    user = await _make_user(async_test_db)

    with _as_user(user):
        before_me = await async_test_client.get("/api/auth/me")
        assert before_me.status_code == 200
        assert before_me.json()["vertretbar_onboarding_completed_at"] is None
        # /contexts nests the user payload under "user" (the frontend reads
        # contexts.user to hydrate the auth store).
        before_ctx = await async_test_client.get("/api/auth/me/contexts")
        assert before_ctx.status_code == 200
        assert before_ctx.json()["user"]["vertretbar_onboarding_completed_at"] is None

        await async_test_client.post("/api/auth/me/vertretbar-onboarding")

        after_me = await async_test_client.get("/api/auth/me")
        assert after_me.json()["vertretbar_onboarding_completed_at"] is not None
        after_ctx = await async_test_client.get("/api/auth/me/contexts")
        assert after_ctx.json()["user"]["vertretbar_onboarding_completed_at"] is not None


_MODERN_LAYOUT = {
    "mode": "modern",
    "case_position": "left",
    "notes_position": "right",
    "outline_position": "none",
}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exam_layout_endpoint_persists_without_side_effects(
    async_test_client, async_test_db
):
    """PUT /me/exam-layout stores the complete layout object and, like the
    ui-mode endpoint, must NOT trigger any profile-confirmation side effects."""
    user = await _make_user(async_test_db)
    with _as_user(user):
        r = await async_test_client.put(
            "/api/auth/me/exam-layout", json={"exam_layout_prefs": _MODERN_LAYOUT}
        )
        assert r.status_code == 200, r.text
        assert r.json()["exam_layout_prefs"] == _MODERN_LAYOUT

    row = (
        await async_test_db.execute(select(User).where(User.id == user.id))
    ).scalar_one()
    assert row.exam_layout_prefs == _MODERN_LAYOUT
    assert row.profile_confirmed_at is None
    assert not row.mandatory_profile_completed


@pytest.mark.asyncio
async def test_exam_layout_validation_and_defaults(async_test_client, async_test_db):
    """The Pydantic layer owns the shape: minimal bodies complete to the
    canonical object, bad literals 422, unknown keys never reach the row,
    null clears, and a classic write keeps the stored docking positions."""
    user = await _make_user(async_test_db)

    async def _row():
        return (
            await async_test_db.execute(select(User).where(User.id == user.id))
        ).scalar_one()

    with _as_user(user):
        # Minimal modern body -> panel-position defaults fill in.
        r = await async_test_client.put(
            "/api/auth/me/exam-layout", json={"exam_layout_prefs": {"mode": "modern"}}
        )
        assert r.status_code == 200, r.text
        assert r.json()["exam_layout_prefs"] == {
            "mode": "modern",
            "case_position": "left",
            "notes_position": "right",
            "outline_position": "right",
        }

        # Invalid literals are rejected by validation.
        r = await async_test_client.put(
            "/api/auth/me/exam-layout",
            json={"exam_layout_prefs": {"mode": "sideways"}},
        )
        assert r.status_code == 422
        r = await async_test_client.put(
            "/api/auth/me/exam-layout",
            json={"exam_layout_prefs": {"mode": "modern", "case_position": "none"}},
        )
        assert r.status_code == 422

        # Unknown keys are dropped (extra='ignore'), never stored.
        r = await async_test_client.put(
            "/api/auth/me/exam-layout",
            json={"exam_layout_prefs": {**_MODERN_LAYOUT, "case_width": 480}},
        )
        assert r.status_code == 200
        assert "case_width" not in r.json()["exam_layout_prefs"]
        assert (await _row()).exam_layout_prefs == _MODERN_LAYOUT

        # A classic write stores the full object — docking positions survive
        # the round-trip instead of being reset.
        r = await async_test_client.put(
            "/api/auth/me/exam-layout",
            json={
                "exam_layout_prefs": {
                    "mode": "classic",
                    "case_position": "right",
                    "notes_position": "none",
                    "outline_position": "left",
                }
            },
        )
        assert r.status_code == 200
        assert (await _row()).exam_layout_prefs == {
            "mode": "classic",
            "case_position": "right",
            "notes_position": "none",
            "outline_position": "left",
        }

        # Drag-resized panel widths: optional, bounded, and only stored once
        # actually set (exclude_none keeps the canonical shape lean).
        r = await async_test_client.put(
            "/api/auth/me/exam-layout",
            json={"exam_layout_prefs": {"mode": "modern", "left_panel_width": 500}},
        )
        assert r.status_code == 200
        stored = (await _row()).exam_layout_prefs
        assert stored["left_panel_width"] == 500
        assert "right_panel_width" not in stored

        r = await async_test_client.put(
            "/api/auth/me/exam-layout",
            json={"exam_layout_prefs": {"mode": "modern", "left_panel_width": 100}},
        )
        assert r.status_code == 422
        r = await async_test_client.put(
            "/api/auth/me/exam-layout",
            json={"exam_layout_prefs": {"mode": "modern", "right_panel_width": 9000}},
        )
        assert r.status_code == 422

        # Explicit null clears back to never-configured.
        r = await async_test_client.put(
            "/api/auth/me/exam-layout", json={"exam_layout_prefs": None}
        )
        assert r.status_code == 200
        assert r.json()["exam_layout_prefs"] is None
        assert (await _row()).exam_layout_prefs is None


@pytest.mark.asyncio
async def test_auth_me_surfaces_exam_layout_prefs(async_test_client, async_test_db):
    """The labeling hosts resolve the layout preference from the boot fetch,
    so /auth/me (fallback), /auth/me/contexts (primary), and /auth/profile must
    all carry it — null before, the stored object after."""
    user = await _make_user(async_test_db)

    with _as_user(user):
        assert (await async_test_client.get("/api/auth/me")).json()[
            "exam_layout_prefs"
        ] is None
        assert (await async_test_client.get("/api/auth/me/contexts")).json()["user"][
            "exam_layout_prefs"
        ] is None
        assert (await async_test_client.get("/api/auth/profile")).json()[
            "exam_layout_prefs"
        ] is None

        await async_test_client.put(
            "/api/auth/me/exam-layout", json={"exam_layout_prefs": _MODERN_LAYOUT}
        )

        assert (await async_test_client.get("/api/auth/me")).json()[
            "exam_layout_prefs"
        ] == _MODERN_LAYOUT
        assert (await async_test_client.get("/api/auth/me/contexts")).json()["user"][
            "exam_layout_prefs"
        ] == _MODERN_LAYOUT
        assert (await async_test_client.get("/api/auth/profile")).json()[
            "exam_layout_prefs"
        ] == _MODERN_LAYOUT


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
        kind="flashcard_collection",
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
async def test_share_info_returns_kind(async_test_client, async_test_db):
    """The join-page preview exposes the project kind so the client can route to
    the exam vs deck surface after joining (issue #35 discovery)."""
    owner = await _make_user(async_test_db)
    invitee = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner)
    with _as_user(owner):
        token = (
            await async_test_client.post(
                f"/api/projects/{deck.id}/shares", json={"password": "pw12"}
            )
        ).json()["token"]
    with _as_user(invitee):
        r = await async_test_client.get(f"/api/shares/{token}")
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "flashcard_collection"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_lists_only_listed_student_shares(
    async_test_client, async_test_db
):
    """GET /shares/discover surfaces listed student exams + decks (not unlisted,
    not the caller's own), tags kind, and marks already-joined items."""
    owner = await _make_user(async_test_db)
    browser = await _make_user(async_test_db)
    listed_exam = await _make_exam(async_test_db, owner)
    unlisted_exam = await _make_exam(async_test_db, owner)
    listed_deck = await _make_deck(async_test_db, owner)

    with _as_user(owner):
        listed_token = (
            await async_test_client.post(
                f"/api/projects/{listed_exam.id}/shares",
                json={"password": "pw12", "is_listed": True},
            )
        ).json()["token"]
        await async_test_client.post(
            f"/api/projects/{unlisted_exam.id}/shares",
            json={"password": "pw12", "is_listed": False},
        )
        await async_test_client.post(
            f"/api/projects/{listed_deck.id}/shares",
            json={"password": "pw12", "is_listed": True},
        )

    with _as_user(browser):
        r = await async_test_client.get("/api/shares/discover")
        assert r.status_code == 200, r.text
        by_pid = {it["project_id"]: it for it in r.json()}
        assert listed_exam.id in by_pid
        assert listed_deck.id in by_pid
        assert unlisted_exam.id not in by_pid  # listing is opt-in
        assert by_pid[listed_exam.id]["kind"] == "exam"
        assert by_pid[listed_deck.id]["kind"] == "flashcard_collection"
        assert by_pid[listed_exam.id]["already_member"] is False
        assert "owner_name" in by_pid[listed_exam.id]

    # Owner does not see their OWN shares in the directory.
    with _as_user(owner):
        r = await async_test_client.get("/api/shares/discover")
        assert all(it["project_id"] != listed_exam.id for it in r.json())

    # After joining, the item flips to already_member.
    with _as_user(browser):
        await async_test_client.post(
            f"/api/shares/{listed_token}/join",
            json={"password": "pw12", "gdpr_consent": True},
        )
        r = await async_test_client.get("/api/shares/discover")
        by_pid = {it["project_id"]: it for it in r.json()}
        assert by_pid[listed_exam.id]["already_member"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoked_link_not_discoverable(async_test_client, async_test_db):
    owner = await _make_user(async_test_db)
    browser = await _make_user(async_test_db)
    exam = await _make_exam(async_test_db, owner)
    with _as_user(owner):
        res = (
            await async_test_client.post(
                f"/api/projects/{exam.id}/shares",
                json={"password": "pw12", "is_listed": True},
            )
        ).json()
        await async_test_client.delete(
            f"/api/projects/{exam.id}/shares/{res['id']}"
        )
    with _as_user(browser):
        r = await async_test_client.get("/api/shares/discover")
        assert all(it["project_id"] != exam.id for it in r.json())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_srs_reads_allow_consented_member_deny_stranger(
    async_test_client, async_test_db
):
    """A consented share member can study a shared deck (own per-user SRS); a
    stranger is denied (issue #35 deck discovery)."""
    owner = await _make_user(async_test_db)
    member = await _make_user(async_test_db)
    stranger = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner)

    with _as_user(owner):
        token = (
            await async_test_client.post(
                f"/api/projects/{deck.id}/shares",
                json={"password": "pw12", "is_listed": True},
            )
        ).json()["token"]

    with _as_user(member):
        await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "pw12", "gdpr_consent": True},
        )
        assert (
            await async_test_client.get(f"/api/projects/{deck.id}/srs/due")
        ).status_code == 200
        assert (
            await async_test_client.get(f"/api/projects/{deck.id}/srs/stats")
        ).status_code == 200

    with _as_user(stranger):
        assert (
            await async_test_client.get(f"/api/projects/{deck.id}/srs/due")
        ).status_code == 403


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
                "kind": "flashcard_collection",
                "origin": "student",
            },
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["kind"] == "flashcard_collection"
        assert body["origin"] == "student"


async def _seed_graded_attempt(db, exam, student, *, grader_id):
    """Task + student annotation + AI-judge and human-Korrektur evaluation rows.

    Persists the nested-canonical ``metrics`` shape every writer produces
    (``{"<metric>": {"value": ...}}``) — the roster/score-history regression
    this file guards is that readers must extract the nested value, not a
    top-level ``metrics->>'value'`` no writer ever wrote.
    """
    from datetime import timedelta

    from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation
    from project_models import Annotation, Task

    t0 = datetime.now(timezone.utc)
    task = Task(
        id=str(uuid.uuid4()),
        project_id=exam.id,
        data={"sachverhalt": "A verkauft B ein Auto.", "musterloesung": "..."},
        inner_id=1,
    )
    db.add(task)
    await db.flush()
    annotation = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=exam.id,
        completed_by=student.id,
        result=[{"from_name": "loesung", "value": {"text": ["Anspruch aus § 433 II BGB..."]}}],
    )
    db.add(annotation)
    run = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=exam.id,
        model_id="immediate",
        evaluation_type_ids=[],
        metrics={},
        created_by=grader_id,
    )
    db.add(run)
    await db.flush()
    judge_run = EvaluationJudgeRun(
        id=str(uuid.uuid4()), evaluation_id=run.id, judge_model_id="gpt-5.4-mini"
    )
    db.add(judge_run)
    await db.flush()

    def _eval_row(metric_key: str, value: float, grade_points: int, created_at, created_by):
        return TaskEvaluation(
            id=str(uuid.uuid4()),
            evaluation_id=run.id,
            judge_run_id=judge_run.id,
            task_id=task.id,
            annotation_id=annotation.id,
            field_name="loesung",
            answer_type="long_text",
            ground_truth="...",
            prediction="Anspruch aus § 433 II BGB...",
            metrics={
                metric_key: {
                    "value": value,
                    "method": metric_key,
                    "details": {
                        "raw_score": int(value * 100),
                        "grade_points": grade_points,
                        "passed": grade_points >= 4,
                    },
                    "error": None,
                }
            },
            passed=grade_points >= 4,
            created_at=created_at,
            created_by=created_by,
        )

    # AI judge first (0.83 → 12 Punkte), human Korrektur later (0.66 → 8
    # Punkte): "best" is the max, "last" is the later human row, and both
    # rows on ONE annotation are ONE attempt. They must differ by grader:
    # uq_task_evaluations_cell (migration 049) is unique per grader, so the
    # AI row is grader-less (created_by=None) and the human Korrektur row
    # carries the grader — otherwise the two rows collide on the same cell.
    db.add(_eval_row("llm_judge_falloesung", 0.83, 12, t0, None))
    db.add(_eval_row("korrektur_falloesung", 0.66, 8, t0 + timedelta(minutes=5), grader_id))
    await db.commit()
    return annotation


@pytest.mark.integration
@pytest.mark.asyncio
async def test_roster_scores_read_nested_canonical_metrics(
    async_test_client, async_test_db
):
    """Regression: roster/cohort scores were dead because readers looked for a
    top-level ``metrics->>'value'`` that no metric writer produces."""
    owner = await _make_user(async_test_db)
    invitee = await _make_user(async_test_db)
    exam = await _make_exam(async_test_db, owner)

    with _as_user(owner):
        r = await async_test_client.post(
            f"/api/projects/{exam.id}/shares", json={"password": "klausur2026"}
        )
        token = r.json()["token"]
    with _as_user(invitee):
        r = await async_test_client.post(
            f"/api/shares/{token}/join",
            json={"password": "klausur2026", "gdpr_consent": True},
        )
        assert r.status_code == 200

    await _seed_graded_attempt(async_test_db, exam, invitee, grader_id=owner.id)

    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{exam.id}/shares/roster")
        assert r.status_code == 200, r.text
        (member,) = r.json()
        assert member["user_id"] == invitee.id
        assert member["best_score"] == pytest.approx(0.83)
        assert member["last_score"] == pytest.approx(0.66)  # later human row wins
        assert member["attempts"] == 1  # two eval rows, one annotation

        r = await async_test_client.get(f"/api/projects/{exam.id}/cohort-leaderboard")
        assert r.status_code == 200
        (ranked,) = r.json()
        assert ranked["best_score"] == pytest.approx(0.83)
        assert ranked["rank"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_score_history_reads_nested_canonical_metrics(
    async_test_client, async_test_db
):
    """Same regression for the student dashboard's /score-history curve."""
    owner = await _make_user(async_test_db)
    student = await _make_user(async_test_db)
    exam = await _make_exam(async_test_db, owner)
    await _seed_graded_attempt(async_test_db, exam, student, grader_id=owner.id)

    with _as_user(student):
        r = await async_test_client.get("/api/student/score-history")
        assert r.status_code == 200, r.text
        points = r.json()
        assert len(points) == 2  # one point per evaluation row, ascending
        assert points[0]["score"] == pytest.approx(0.83)
        assert points[1]["score"] == pytest.approx(0.66)
        assert points[0]["project_id"] == exam.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_score_history_labels_sources_and_excludes_batch_runs(
    async_test_client, async_test_db
):
    """Issue #322: points carry a ``source`` lane label ('ki' for the
    immediate grading, 'human' for Korrektur runs), and batch/research runs
    (any other model_id — they grade BOTH tier variants of every exam) are
    excluded so the curve doesn't double-count."""
    from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation
    from project_models import Annotation, Task

    owner = await _make_user(async_test_db)
    student = await _make_user(async_test_db)
    exam = await _make_exam(async_test_db, owner)
    task = Task(
        id=str(uuid.uuid4()),
        project_id=exam.id,
        data={"sachverhalt": "S", "musterloesung": "M"},
        inner_id=1,
    )
    async_test_db.add(task)
    await async_test_db.flush()
    annotation = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=exam.id,
        completed_by=student.id,
        result=[{"from_name": "loesung", "value": {"text": ["..."]}}],
    )
    async_test_db.add(annotation)
    await async_test_db.flush()

    async def _run_with_row(model_id, metric_key, value, *, judge_model, created_by):
        run = EvaluationRun(
            id=str(uuid.uuid4()),
            project_id=exam.id,
            model_id=model_id,
            evaluation_type_ids=[],
            metrics={},
            created_by=owner.id,
        )
        async_test_db.add(run)
        await async_test_db.flush()
        jr = EvaluationJudgeRun(
            id=str(uuid.uuid4()), evaluation_id=run.id, judge_model_id=judge_model
        )
        async_test_db.add(jr)
        await async_test_db.flush()
        async_test_db.add(
            TaskEvaluation(
                id=str(uuid.uuid4()),
                evaluation_id=run.id,
                judge_run_id=jr.id,
                task_id=task.id,
                annotation_id=annotation.id,
                field_name="loesung",
                answer_type="long_text",
                ground_truth="M",
                prediction="...",
                metrics={
                    metric_key: {"value": value, "method": metric_key, "error": None}
                },
                passed=True,
                created_by=created_by,
            )
        )

    await _run_with_row(
        "immediate", "llm_judge_falloesung", 0.8, judge_model="gpt-5.4-mini",
        created_by=None,
    )
    # Human Korrektur run: model_id='human', judge_model_id NULL (prod shape).
    await _run_with_row(
        "human", "korrektur_falloesung", 0.6, judge_model=None, created_by=owner.id
    )
    # A batch/research run on the same annotation must NOT surface.
    await _run_with_row(
        "gpt-5.4-mini", "llm_judge_falloesung", 0.99, judge_model="gpt-5.4-mini",
        created_by=owner.id,
    )
    await async_test_db.commit()

    with _as_user(student):
        r = await async_test_client.get("/api/student/score-history")
        assert r.status_code == 200, r.text
        points = r.json()
    assert len(points) == 2
    by_source = {p["source"]: p for p in points}
    assert by_source["ki"]["score"] == pytest.approx(0.8)
    assert by_source["human"]["score"] == pytest.approx(0.6)
    assert not any(p["score"] == pytest.approx(0.99) for p in points)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_collection_kind_deck_shares_list_and_join(async_test_client, async_test_db):
    """The current student collections are kind='flashcard_collection' (the
    legacy cases above use 'flashcard_collection'); both list in the directory and
    join to the deck surface."""
    owner = await _make_user(async_test_db)
    member = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner, kind="flashcard_collection")

    with _as_user(owner):
        token = (
            await async_test_client.post(
                f"/api/projects/{deck.id}/shares",
                json={"password": "pw12", "is_listed": True},
            )
        ).json()["token"]

    with _as_user(member):
        listed = {r["project_id"]: r for r in (await async_test_client.get("/api/shares/discover")).json()}
        assert listed[deck.id]["kind"] == "flashcard_collection"
        info = (await async_test_client.get(f"/api/shares/{token}")).json()
        assert info["kind"] == "flashcard_collection"
        r = await async_test_client.post(
            f"/api/shares/{token}/join", json={"password": "pw12", "gdpr_consent": True}
        )
        assert r.status_code == 200 and r.json()["status"] == "joined"
        assert (await async_test_client.get(f"/api/projects/{deck.id}/srs/due")).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_join_is_rate_limited_before_the_password_check(
    async_test_client, async_test_db, monkeypatch
):
    """Brute-force guard: when the shared limiter reports the user is over
    budget, join returns 429 with Retry-After and never touches the link (the
    limiter itself is a no-op under TESTING=true, so we force its verdict)."""
    owner = await _make_user(async_test_db)
    member = await _make_user(async_test_db)
    deck = await _make_deck(async_test_db, owner)
    with _as_user(owner):
        token = (
            await async_test_client.post(
                f"/api/projects/{deck.id}/shares", json={"password": "pw12"}
            )
        ).json()["token"]

    seen = {}

    async def _limited(request, endpoint, limits, user=None):
        seen["endpoint"], seen["limits"], seen["user"] = endpoint, limits, user
        return {"error": "Rate limit exceeded", "retry_after": 42}

    from rate_limiter import rate_limiter

    monkeypatch.setattr(rate_limiter, "check_rate_limit", _limited)
    with _as_user(member):
        r = await async_test_client.post(
            f"/api/shares/{token}/join", json={"password": "pw12", "gdpr_consent": True}
        )
    assert r.status_code == 429
    assert r.headers["retry-after"] == "42"
    assert seen["endpoint"] == "share_join"
    assert seen["limits"] == {"minute": (10, 60), "hour": (30, 3600)}
    assert str(seen["user"].id) == member.id
    # Not joined.
    with _as_user(member):
        assert (await async_test_client.get(f"/api/projects/{deck.id}/srs/due")).status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_score_history_scope_all_includes_research_projects(
    async_test_client, async_test_db
):
    """benger dashboard: scope=all drops the origin/kind filter so graded
    attempts on research projects count too; the default stays student-only."""
    owner = await _make_user(async_test_db)
    student = await _make_user(async_test_db)
    research = Project(
        id=str(uuid.uuid4()), title="Forschung", created_by=owner.id,
        is_private=False, is_public=True, public_role="ANNOTATOR",
    )
    async_test_db.add(research)
    await async_test_db.commit()
    await _seed_graded_attempt(async_test_db, research, student, grader_id=owner.id)

    with _as_user(student):
        r = await async_test_client.get("/api/student/score-history")
        assert r.status_code == 200 and r.json() == []
        r = await async_test_client.get("/api/student/score-history", params={"scope": "all"})
        assert r.status_code == 200, r.text
        points = r.json()
        assert len(points) == 2
        assert {p["project_id"] for p in points} == {research.id}
        assert points[0]["kind"] is None
