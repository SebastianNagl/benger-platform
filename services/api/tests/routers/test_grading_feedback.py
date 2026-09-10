"""Integration tests for the platform grading-feedback reads and table shape.

Covers ``GET /api/projects/{id}/grading-feedback/mine`` (self-owned rows, no
project gate), ``GET .../summary`` (editor-gated, anonymized) and the
superadmin ``GET /api/admin/grading-feedback/export`` (CSV/JSON), plus the
``grading_feedback`` constraints the extended upsert relies on. The write
path itself lives in benger_extended and is covered by its behavioral suite,
so rows are seeded directly here.

Async pattern (see tests/routers/projects/test_student_sharing.py): seed via
``async_test_db``, drive the real ASGI app via ``async_test_client``, and
override ``require_user`` with ``_as_user`` so no JWT round-trip is needed.
"""

from __future__ import annotations

import csv
import io
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from models import User
from project_models import Annotation, GradingFeedback, Project, Task
from routers.grading_feedback import EXPORT_COLUMNS


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
        username=f"gf-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Solver",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, owner, *, title="Probeklausur BGB AT", kind="exam") -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=title,
        created_by=owner.id,
        is_private=True,
        kind=kind,
        origin="student",
    )
    db.add(p)
    await db.flush()
    return p


async def _make_task(db, project, *, inner_id=1) -> Task:
    t = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        data={"sachverhalt": "Der A klagt gegen B."},
        inner_id=inner_id,
    )
    db.add(t)
    await db.flush()
    return t


async def _make_annotation(db, task, user) -> Annotation:
    a = Annotation(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=task.project_id,
        completed_by=user.id,
        result=[],
    )
    db.add(a)
    await db.flush()
    return a


async def _make_feedback(
    db,
    *,
    annotation,
    user,
    source="llm",
    rating="up",
    comment=None,
    judge_model_id="gpt-5-mini",
    grade_points=12.0,
    passed=True,
) -> GradingFeedback:
    fb = GradingFeedback(
        id=str(uuid.uuid4()),
        project_id=annotation.project_id,
        task_id=annotation.task_id,
        annotation_id=annotation.id,
        user_id=user.id,
        grading_source=source,
        judge_model_id=judge_model_id if source == "llm" else None,
        grade_points=grade_points,
        passed=passed,
        rating=rating,
        comment=comment,
        context={"metric_keys": ["llm_judge_falloesung"]},
    )
    db.add(fb)
    await db.flush()
    return fb


# --------------------------------------------------------------------------- mine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mine_returns_only_own_rows_and_filters_by_annotation(
    async_test_client, async_test_db
):
    db = async_test_db
    owner = await _make_user(db)
    alice = await _make_user(db)
    bob = await _make_user(db)
    exam = await _make_project(db, owner)
    task1 = await _make_task(db, exam, inner_id=1)
    task2 = await _make_task(db, exam, inner_id=2)
    a1 = await _make_annotation(db, task1, alice)
    a2 = await _make_annotation(db, task2, alice)
    b1 = await _make_annotation(db, task1, bob)
    await _make_feedback(db, annotation=a1, user=alice, source="llm", rating="up")
    await _make_feedback(
        db, annotation=a1, user=alice, source="human", rating=None, comment="Danke!"
    )
    await _make_feedback(db, annotation=a2, user=alice, source="llm", rating="down")
    await _make_feedback(db, annotation=b1, user=bob, source="llm", rating="up")
    await db.commit()

    with _as_user(alice):
        r = await async_test_client.get(f"/api/projects/{exam.id}/grading-feedback/mine")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 3
        assert all("user_id" not in row and "context" not in row for row in rows)

        r = await async_test_client.get(
            f"/api/projects/{exam.id}/grading-feedback/mine?annotation_id={a1.id}"
        )
        assert r.status_code == 200
        by_source = {row["grading_source"]: row for row in r.json()}
        assert set(by_source) == {"llm", "human"}
        assert by_source["llm"]["rating"] == "up"
        assert by_source["llm"]["judge_model_id"] == "gpt-5-mini"
        assert by_source["llm"]["grade_points"] == 12.0
        assert by_source["human"]["rating"] is None
        assert by_source["human"]["comment"] == "Danke!"

    with _as_user(bob):
        r = await async_test_client.get(f"/api/projects/{exam.id}/grading-feedback/mine")
        assert [row["annotation_id"] for row in r.json()] == [b1.id]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mine_stranger_gets_empty_list(async_test_client, async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    alice = await _make_user(db)
    stranger = await _make_user(db)
    exam = await _make_project(db, owner)
    task = await _make_task(db, exam)
    ann = await _make_annotation(db, task, alice)
    await _make_feedback(db, annotation=ann, user=alice)
    await db.commit()

    with _as_user(stranger):
        r = await async_test_client.get(f"/api/projects/{exam.id}/grading-feedback/mine")
        assert r.status_code == 200
        assert r.json() == []


# ------------------------------------------------------------------------ summary


@pytest.mark.integration
@pytest.mark.asyncio
async def test_summary_counts_and_anonymized_comments(async_test_client, async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    alice = await _make_user(db)
    bob = await _make_user(db)
    exam = await _make_project(db, owner)
    task = await _make_task(db, exam, inner_id=7)
    a = await _make_annotation(db, task, alice)
    b = await _make_annotation(db, task, bob)
    await _make_feedback(db, annotation=a, user=alice, source="llm", rating="up", comment="Zu streng")
    await _make_feedback(db, annotation=b, user=bob, source="llm", rating="down")
    await _make_feedback(db, annotation=a, user=alice, source="human", rating="down", comment="Unfair")
    await _make_feedback(
        db, annotation=b, user=bob, source="general", rating=None,
        comment="Der Editor hakt auf dem Handy.", grade_points=None, passed=None,
    )
    await db.commit()

    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{exam.id}/grading-feedback/summary")
        assert r.status_code == 200, r.text
        body = r.json()

    assert body["project_id"] == exam.id
    assert body["total"] == 4
    assert body["totals"]["llm"] == {"up": 1, "down": 1, "comments": 1}
    assert body["totals"]["human"] == {"up": 0, "down": 1, "comments": 1}
    assert body["totals"]["general"] == {"up": 0, "down": 0, "comments": 1}
    assert len(body["comments"]) == 3
    assert {c["comment"] for c in body["comments"]} == {
        "Zu streng", "Unfair", "Der Editor hakt auf dem Handy."
    }
    for c in body["comments"]:
        assert "user_id" not in c
        assert c["task_inner_id"] == 7
        assert c["grading_source"] in ("llm", "human", "general")
    assert "alice" not in r.text.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_summary_stranger_forbidden_superadmin_allowed(async_test_client, async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    stranger = await _make_user(db)
    admin = await _make_user(db, superadmin=True)
    exam = await _make_project(db, owner)
    await db.commit()

    with _as_user(stranger):
        r = await async_test_client.get(f"/api/projects/{exam.id}/grading-feedback/summary")
        assert r.status_code == 403
    with _as_user(admin):
        r = await async_test_client.get(f"/api/projects/{exam.id}/grading-feedback/summary")
        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["comments"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_summary_deleted_project_404_for_owner(async_test_client, async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    admin = await _make_user(db, superadmin=True)
    exam = await _make_project(db, owner)
    exam.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    with _as_user(owner):
        r = await async_test_client.get(f"/api/projects/{exam.id}/grading-feedback/summary")
        assert r.status_code == 404
    with _as_user(admin):
        r = await async_test_client.get(f"/api/projects/{exam.id}/grading-feedback/summary")
        assert r.status_code == 200

    with _as_user(owner):
        r = await async_test_client.get(
            f"/api/projects/{uuid.uuid4()}/grading-feedback/summary"
        )
        assert r.status_code == 404


# ------------------------------------------------------------------------- export


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_requires_superadmin(async_test_client, async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    await db.commit()
    with _as_user(owner):
        r = await async_test_client.get("/api/admin/grading-feedback/export")
        assert r.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_csv_json_and_filters(async_test_client, async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    alice = await _make_user(db)
    admin = await _make_user(db, superadmin=True)
    exam = await _make_project(db, owner, title="Klausur Eins")
    other = await _make_project(db, owner, title="Klausur Zwei", kind="exam")
    t1 = await _make_task(db, exam, inner_id=3)
    t2 = await _make_task(db, other, inner_id=1)
    a1 = await _make_annotation(db, t1, alice)
    a2 = await _make_annotation(db, t2, alice)
    await _make_feedback(db, annotation=a1, user=alice, rating="up", comment="Gut, aber knapp")
    await _make_feedback(db, annotation=a2, user=alice, rating="down")
    await db.commit()

    with _as_user(admin):
        r = await async_test_client.get("/api/admin/grading-feedback/export")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        assert 'filename="grading_feedback_' in r.headers["content-disposition"]
        reader = csv.DictReader(io.StringIO(r.text))
        assert reader.fieldnames == EXPORT_COLUMNS
        rows = list(reader)
        assert len(rows) == 2
        by_project = {row["project_id"]: row for row in rows}
        assert by_project[exam.id]["project_title"] == "Klausur Eins"
        assert by_project[exam.id]["project_kind"] == "exam"
        assert by_project[exam.id]["task_inner_id"] == "3"
        assert by_project[exam.id]["user_id"] == alice.id
        assert by_project[exam.id]["judge_model_id"] == "gpt-5-mini"
        assert by_project[exam.id]["comment"] == "Gut, aber knapp"
        assert "llm_judge_falloesung" in by_project[exam.id]["context"]

        r = await async_test_client.get("/api/admin/grading-feedback/export?format=json")
        assert r.status_code == 200
        payload = r.json()
        assert len(payload) == 2
        assert payload[0]["context"] == {"metric_keys": ["llm_judge_falloesung"]}
        assert {p["rating"] for p in payload} == {"up", "down"}

        r = await async_test_client.get(
            f"/api/admin/grading-feedback/export?format=json&project_id={other.id}"
        )
        assert [p["project_title"] for p in r.json()] == ["Klausur Zwei"]

        r = await async_test_client.get(
            "/api/admin/grading-feedback/export?format=json&since=2100-01-01T00:00:00Z"
        )
        assert r.json() == []

        r = await async_test_client.get("/api/admin/grading-feedback/export?format=json&limit=1")
        assert len(r.json()) == 1

        r = await async_test_client.get("/api/admin/grading-feedback/export?format=xml")
        assert r.status_code == 422


# -------------------------------------------------------------------- constraints


@pytest.mark.integration
@pytest.mark.asyncio
async def test_one_row_per_user_annotation_source(async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    alice = await _make_user(db)
    exam = await _make_project(db, owner)
    task = await _make_task(db, exam)
    ann = await _make_annotation(db, task, alice)
    await _make_feedback(db, annotation=ann, user=alice, source="llm", rating="up")
    # A second source on the same submission is fine ...
    await _make_feedback(db, annotation=ann, user=alice, source="human", rating="up")
    # ... a second row for the same (user, annotation, source) is not.
    with pytest.raises(IntegrityError):
        await _make_feedback(db, annotation=ann, user=alice, source="llm", rating="down")
    await db.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_enum_is_checked(async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    alice = await _make_user(db)
    exam = await _make_project(db, owner)
    task = await _make_task(db, exam)
    ann = await _make_annotation(db, task, alice)
    with pytest.raises(IntegrityError):
        await _make_feedback(db, annotation=ann, user=alice, rating="meh")
    await db.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_source_enum_is_checked(async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    alice = await _make_user(db)
    exam = await _make_project(db, owner)
    task = await _make_task(db, exam)
    ann = await _make_annotation(db, task, alice)
    with pytest.raises(IntegrityError):
        await _make_feedback(db, annotation=ann, user=alice, source="robot")
    await db.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_row_is_rejected(async_test_db):
    db = async_test_db
    owner = await _make_user(db)
    alice = await _make_user(db)
    exam = await _make_project(db, owner)
    task = await _make_task(db, exam)
    ann = await _make_annotation(db, task, alice)
    with pytest.raises(IntegrityError):
        await _make_feedback(db, annotation=ann, user=alice, rating=None, comment=None)
    await db.rollback()
