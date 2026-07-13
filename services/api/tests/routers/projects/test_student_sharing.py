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


async def _make_deck(db, owner, *, title="Stapel BGB AT") -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=title,
        created_by=owner.id,
        is_private=True,
        kind="flashcard_deck",
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
        assert r.json()["kind"] == "flashcard_deck"


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
        assert by_pid[listed_deck.id]["kind"] == "flashcard_deck"
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
                "kind": "flashcard_deck",
                "origin": "student",
            },
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["kind"] == "flashcard_deck"
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

    def _eval_row(metric_key: str, value: float, grade_points: int, created_at):
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
        )

    # AI judge first (0.83 → 12 Punkte), human Korrektur later (0.66 → 8
    # Punkte): "best" is the max, "last" is the later human row, and both
    # rows on ONE annotation are ONE attempt.
    db.add(_eval_row("llm_judge_falloesung", 0.83, 12, t0))
    db.add(_eval_row("korrektur_falloesung", 0.66, 8, t0 + timedelta(minutes=5)))
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
