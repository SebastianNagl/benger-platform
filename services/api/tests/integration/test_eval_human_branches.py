"""Behavioral integration tests for the human-evaluation session router.

Target: ``services/api/routers/evaluations/human.py`` (mounted at prefix
``/api/evaluations`` via ``routers/evaluations/__init__.py``). This file drives
end-to-end HTTP round-trips and asserts persisted DB rows for the uncovered
endpoint branches:

  POST   /human/session/start ....... 403 (non-editor), 404 (missing project),
                                      happy-path persist (likert + preference).
  GET    /human/next-item ........... 404 (unknown/foreign session), 400
                                      (session not active), the
                                      session-completes-when-no-tasks 404 +
                                      side-effect status flip, and the
                                      no-LLM-response 200 next item.
  POST   /human/likert .............. 404 (foreign/wrong-type session),
                                      multi-dimension persist + items_evaluated
                                      bump + comment-per-dimension mapping.
  POST   /human/preference .......... 404 (foreign/wrong-type session),
                                      persist + items_evaluated bump.
  GET    /human/session/{id}/progress 404, 403 (non-owner non-superadmin),
                                      percentage arithmetic (partial + zero
                                      total).
  GET    /human/sessions/{project_id} 403 (no project access), ordered list
                                      shape.
  GET    /human/config/{project_id} . 404, 403, the no-eval-config empty
                                      shape, the selected-methods extraction +
                                      likert-dimension lift, and the default
                                      dimensions fallback.
  DELETE /human/session/{id} ........ 404, 403 (non-owner non-superadmin),
                                      cascade delete of likert + preference
                                      rows.

Async migration note
--------------------
Every human handler except ``start_human_evaluation_session`` was moved to the
async DB lane (``Depends(get_async_db)``). The sync ``client`` / ``test_db``
fixtures only override ``get_db``, so they no longer reach those handlers (the
async handlers read through a separate ``get_async_db``-bound connection that
never sees the rolled-back sync savepoint). The async classes here therefore
seed rows through ``async_test_db`` and drive the surface via
``async_test_client``; the current user is set with the ``_as_user``
contextmanager (overriding ``require_user``).

``TestStartSession`` keeps the sync ``client`` / ``test_db`` approach because
``start_human_evaluation_session`` is still a sync handler.

Access model recap (routers/projects/helpers):
  * A superadmin always passes ``check_project_accessible_async`` /
    ``auth_service.check_project_access_async`` (used for the 200 paths).
  * A private project owned by another user is unreachable by a non-creator
    non-superadmin (used for the 403 paths).
  * Session ownership (``evaluator_id == current_user.id``) governs next-item,
    progress, and delete — independent of project access.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from auth_module.models import User as AuthUser
from auth_module.dependencies import require_user
from main import app
from models import (
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
    User as DBUser,
)
from project_models import Project, ProjectOrganization, Task
from sqlalchemy import select

BASE = "/api/evaluations"


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user, *, is_superadmin=True):
    """Override require_user with an auth User mirroring ``db_user``."""
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=getattr(db_user, "created_at", None) or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, is_superadmin=True):
    u = DBUser(
        id=_uid(),
        username=f"hu-int-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Human Eval Int User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _setup_project(db, owner, *, num_tasks=2, is_private=False,
                         evaluation_config=None):
    """Create a project owned by ``owner`` with ``num_tasks`` tasks."""
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Human Eval {pid[:6]}",
        created_by=owner.id,
        is_private=is_private,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        evaluation_config=evaluation_config,
    )
    db.add(p)
    await db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=pid,
            data={"text": f"Human task #{i}", "content": f"Content {i}"},
            inner_id=i + 1, created_by=owner.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return p, tasks


async def _make_session(db, project, evaluator_id, *, session_type="likert",
                        status="active", items_evaluated=0, total_items=2,
                        session_config=None):
    s = HumanEvaluationSession(
        id=_uid(),
        project_id=project.id,
        evaluator_id=evaluator_id,
        session_type=session_type,
        items_evaluated=items_evaluated,
        total_items=total_items,
        status=status,
        session_config=session_config or {"field_name": "answer"},
        created_at=datetime.now(timezone.utc),
    )
    db.add(s)
    await db.flush()
    return s


# ===========================================================================
# POST /human/session/start  (SYNC handler — keeps sync fixtures)
# ===========================================================================


def _h(auth_headers, org, role="admin"):
    return {**auth_headers[role], "X-Organization-Context": org.id}


def _setup_project_sync(db, admin, org, *, num_tasks=2, is_private=False, link_org=True,
                        evaluation_config=None):
    """Sync seeding helper for the still-sync start-session endpoint."""
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Human Eval {pid[:6]}",
        created_by=admin.id,
        is_private=is_private,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        evaluation_config=evaluation_config,
    )
    db.add(p)
    db.flush()

    if link_org:
        db.add(ProjectOrganization(
            id=_uid(), project_id=pid,
            organization_id=org.id, assigned_by=admin.id,
        ))
        db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=pid,
            data={"text": f"Human task #{i}", "content": f"Content {i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return p, tasks


@pytest.mark.integration
class TestStartSession:
    def test_non_editor_gets_403(self, client, test_db, test_users, auth_headers, test_org):
        """An annotator (only PROJECT_VIEW, not editor) cannot start a
        session — check_user_can_edit_project returns False → 403."""
        p, _ = _setup_project_sync(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/session/start",
            json={"project_id": p.id, "session_type": "likert"},
            headers=_h(auth_headers, test_org, role="annotator"),
        )
        assert resp.status_code == 403, resp.text
        assert "only project editors" in resp.json()["detail"]

    def test_missing_project_404(self, client, test_db, test_users, auth_headers):
        """A superadmin passes the editor gate (check_user_can_edit_project is
        True for superadmin) but the project lookup misses → 404."""
        resp = client.post(
            f"{BASE}/human/session/start",
            json={"project_id": f"missing-{uuid.uuid4().hex}", "session_type": "likert"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_likert_session_persists_with_dimensions(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A likert session stamps the requested dimensions into session_config
        and sets total_items to the project's task count."""
        p, tasks = _setup_project_sync(test_db, test_users[0], test_org, num_tasks=3)
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/session/start",
            json={
                "project_id": p.id,
                "session_type": "likert",
                "field_name": "answer",
                "dimensions": ["correctness", "style"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_type"] == "likert"
        assert body["total_items"] == 3
        assert body["status"] == "active"
        assert body["session_config"]["dimensions"] == ["correctness", "style"]
        assert body["session_config"]["field_name"] == "answer"

        # DB state: a row landed with evaluator = admin, the dimensions stored.
        row = test_db.query(HumanEvaluationSession).filter_by(id=body["id"]).one()
        assert row.evaluator_id == test_users[0].id
        assert row.session_config["dimensions"] == ["correctness", "style"]
        assert row.total_items == 3

    def test_preference_session_nulls_dimensions(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A preference session forces session_config.dimensions to None (the
        ``if session_type == 'likert'`` ternary's False arm)."""
        p, tasks = _setup_project_sync(test_db, test_users[0], test_org, num_tasks=2)
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/session/start",
            json={
                "project_id": p.id,
                "session_type": "preference",
                "dimensions": ["ignored"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_type"] == "preference"
        assert body["session_config"]["dimensions"] is None

        row = test_db.query(HumanEvaluationSession).filter_by(id=body["id"]).one()
        assert row.session_config["dimensions"] is None


# ===========================================================================
# GET /human/next-item  (ASYNC)
# ===========================================================================


@pytest.mark.integration
class TestNextItem:
    @pytest.mark.asyncio
    async def test_foreign_session_404(self, async_test_client, async_test_db):
        """A session owned by another user is invisible (the query filters on
        evaluator_id == current_user.id) → 404."""
        owner = await _make_user(async_test_db)
        requester = await _make_user(async_test_db, is_superadmin=False)
        p, _ = await _setup_project(async_test_db, owner)
        s = await _make_session(async_test_db, p, owner.id)
        await async_test_db.commit()

        with _as_user(requester, is_superadmin=False):
            resp = await async_test_client.get(
                f"{BASE}/human/next-item?session_id={s.id}"
            )
        assert resp.status_code == 404, resp.text
        assert "not found or unauthorized" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_inactive_session_400(self, async_test_client, async_test_db):
        """A completed session is not active → the 400 branch."""
        owner = await _make_user(async_test_db)
        p, _ = await _setup_project(async_test_db, owner)
        s = await _make_session(async_test_db, p, owner.id, status="completed")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/human/next-item?session_id={s.id}"
            )
        assert resp.status_code == 400, resp.text
        assert "not active" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_no_more_tasks_completes_session_404(
        self, async_test_client, async_test_db
    ):
        """An active session on a project with zero tasks hits the
        ``not next_task`` branch: status flips to 'completed', completed_at is
        stamped, and a 404 'session completed' is raised."""
        owner = await _make_user(async_test_db)
        p, _ = await _setup_project(async_test_db, owner, num_tasks=0)
        s = await _make_session(async_test_db, p, owner.id, total_items=0)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/human/next-item?session_id={s.id}"
            )
        assert resp.status_code == 404, resp.text
        assert "session completed" in resp.json()["detail"]

        # Side-effect: the session was flipped to completed + timestamped.
        # Refresh within the async path so attribute reads don't trigger a
        # lazy (sync) reload on an expired instance.
        await async_test_db.refresh(s)
        assert s.status == "completed"
        assert s.completed_at is not None

    @pytest.mark.asyncio
    async def test_returns_next_task_without_llm_responses(
        self, async_test_client, async_test_db
    ):
        """With tasks present and no LLM generations, the next unevaluated task
        is returned with an empty responses list and item_number = evaluated+1."""
        owner = await _make_user(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, num_tasks=2)
        s = await _make_session(
            async_test_db, p, owner.id, items_evaluated=0, total_items=2
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/human/next-item?session_id={s.id}"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_id"] == s.id
        assert body["item_number"] == 1
        assert body["total_items"] == 2
        assert body["responses"] == []
        assert body["task_id"] in {t.id for t in tasks}


# ===========================================================================
# POST /human/likert  (ASYNC)
# ===========================================================================


@pytest.mark.integration
class TestSubmitLikert:
    @pytest.mark.asyncio
    async def test_wrong_type_session_404(self, async_test_client, async_test_db):
        """Submitting likert to a preference session misses the
        session_type=='likert' filter → 404."""
        owner = await _make_user(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, num_tasks=1)
        s = await _make_session(async_test_db, p, owner.id, session_type="preference")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/human/likert",
                json={
                    "session_id": s.id,
                    "task_id": tasks[0].id,
                    "response_id": "resp-1",
                    "ratings": {"correctness": 4},
                },
            )
        assert resp.status_code == 404, resp.text
        assert "not found or unauthorized" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_persists_one_row_per_dimension_and_bumps_progress(
        self, async_test_client, async_test_db
    ):
        """Each rated dimension yields a LikertScaleEvaluation row; comments map
        per-dimension; the session's items_evaluated increments by one."""
        owner = await _make_user(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, num_tasks=1)
        s = await _make_session(async_test_db, p, owner.id, items_evaluated=2)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/human/likert",
                json={
                    "session_id": s.id,
                    "task_id": tasks[0].id,
                    "response_id": "resp-A",
                    "ratings": {"correctness": 5, "style": 3},
                    "comments": {"correctness": "spot on"},
                    "time_spent_seconds": 42,
                },
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # items_evaluated bumped from 2 to 3 (one item, not one per dimension).
        assert body["items_evaluated"] == 3

        # DB state: two rows (one per dimension); the comment only attaches to
        # the dimension that had one.
        rows = (
            await async_test_db.execute(
                select(LikertScaleEvaluation).where(
                    LikertScaleEvaluation.session_id == s.id
                )
            )
        ).scalars().all()
        assert len(rows) == 2
        by_dim = {r.dimension: r for r in rows}
        assert by_dim["correctness"].rating == 5
        assert by_dim["correctness"].comment == "spot on"
        assert by_dim["correctness"].time_spent_seconds == 42
        assert by_dim["style"].rating == 3
        assert by_dim["style"].comment is None

        await async_test_db.refresh(s)
        assert s.items_evaluated == 3


# ===========================================================================
# POST /human/preference  (ASYNC)
# ===========================================================================


@pytest.mark.integration
class TestSubmitPreference:
    @pytest.mark.asyncio
    async def test_wrong_type_session_404(self, async_test_client, async_test_db):
        """Submitting preference to a likert session misses the
        session_type=='preference' filter → 404."""
        owner = await _make_user(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, num_tasks=1)
        s = await _make_session(async_test_db, p, owner.id, session_type="likert")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/human/preference",
                json={
                    "session_id": s.id,
                    "task_id": tasks[0].id,
                    "response_a_id": "a",
                    "response_b_id": "b",
                    "winner": "a",
                },
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_persists_ranking_and_bumps_progress(
        self, async_test_client, async_test_db
    ):
        """A preference submission writes one PreferenceRanking row carrying the
        winner/confidence/reasoning and bumps items_evaluated."""
        owner = await _make_user(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, num_tasks=1)
        s = await _make_session(
            async_test_db, p, owner.id, session_type="preference", items_evaluated=0
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"{BASE}/human/preference",
                json={
                    "session_id": s.id,
                    "task_id": tasks[0].id,
                    "response_a_id": "resp-a",
                    "response_b_id": "resp-b",
                    "winner": "b",
                    "confidence": 0.8,
                    "reasoning": "B is more complete",
                    "time_spent_seconds": 30,
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items_evaluated"] == 1

        rows = (
            await async_test_db.execute(
                select(PreferenceRanking).where(PreferenceRanking.session_id == s.id)
            )
        ).scalars().all()
        assert len(rows) == 1
        r = rows[0]
        assert r.winner == "b"
        assert r.confidence == 0.8
        assert r.reasoning == "B is more complete"
        assert r.response_a_id == "resp-a"
        assert r.response_b_id == "resp-b"


# ===========================================================================
# GET /human/session/{session_id}/progress  (ASYNC)
# ===========================================================================


@pytest.mark.integration
class TestProgress:
    @pytest.mark.asyncio
    async def test_missing_session_404(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                f"{BASE}/human/session/missing-{uuid.uuid4().hex}/progress"
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_owner_non_superadmin_403(self, async_test_client, async_test_db):
        """A session owned by one user, requested by another (not owner, not
        superadmin) → 403."""
        owner = await _make_user(async_test_db)
        requester = await _make_user(async_test_db, is_superadmin=False)
        p, _ = await _setup_project(async_test_db, owner)
        s = await _make_session(async_test_db, p, owner.id)
        await async_test_db.commit()

        with _as_user(requester, is_superadmin=False):
            resp = await async_test_client.get(
                f"{BASE}/human/session/{s.id}/progress"
            )
        assert resp.status_code == 403, resp.text
        assert "permission" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_partial_progress_percentage(self, async_test_client, async_test_db):
        """items_evaluated=15 / total_items=30 → 50.0 percent."""
        owner = await _make_user(async_test_db)
        p, _ = await _setup_project(async_test_db, owner)
        s = await _make_session(
            async_test_db, p, owner.id, items_evaluated=15, total_items=30
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/human/session/{s.id}/progress"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items_evaluated"] == 15
        assert body["total_items"] == 30
        assert body["progress_percentage"] == pytest.approx(50.0)
        assert body["session_id"] == s.id

    @pytest.mark.asyncio
    async def test_zero_total_items_gives_zero_percentage(
        self, async_test_client, async_test_db
    ):
        """total_items=0 short-circuits the percentage to 0.0 (avoids div-by-0)."""
        owner = await _make_user(async_test_db)
        p, _ = await _setup_project(async_test_db, owner)
        s = await _make_session(
            async_test_db, p, owner.id, items_evaluated=0, total_items=0
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(
                f"{BASE}/human/session/{s.id}/progress"
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["progress_percentage"] == pytest.approx(0.0)


# ===========================================================================
# GET /human/sessions/{project_id}  (ASYNC)
# ===========================================================================


@pytest.mark.integration
class TestListSessions:
    @pytest.mark.asyncio
    async def test_no_project_access_403(self, async_test_client, async_test_db):
        """A private project the requester cannot reach → 403."""
        owner = await _make_user(async_test_db)
        requester = await _make_user(async_test_db, is_superadmin=False)
        p, _ = await _setup_project(async_test_db, owner, is_private=True)
        await async_test_db.commit()

        with _as_user(requester, is_superadmin=False):
            resp = await async_test_client.get(f"{BASE}/human/sessions/{p.id}")
        assert resp.status_code == 403, resp.text
        assert "access" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_lists_sessions_newest_first(self, async_test_client, async_test_db):
        """All sessions for the project come back ordered created_at DESC."""
        owner = await _make_user(async_test_db)
        p, _ = await _setup_project(async_test_db, owner)
        s_old = await _make_session(async_test_db, p, owner.id, session_type="likert")
        s_old.created_at = datetime.now(timezone.utc).replace(microsecond=0)
        # Newer one by forcing a strictly larger created_at.
        s_new = await _make_session(async_test_db, p, owner.id, session_type="preference")
        s_new.created_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/human/sessions/{p.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [row["id"] for row in body]
        assert set(ids) == {s_old.id, s_new.id}
        # Newest first.
        assert ids[0] == s_new.id


# ===========================================================================
# GET /human/config/{project_id}  (ASYNC)
# ===========================================================================


@pytest.mark.integration
class TestHumanConfig:
    @pytest.mark.asyncio
    async def test_missing_project_404(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                f"{BASE}/human/config/missing-{uuid.uuid4().hex}"
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_access_denied_403(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        requester = await _make_user(async_test_db, is_superadmin=False)
        p, _ = await _setup_project(async_test_db, owner, is_private=True)
        await async_test_db.commit()

        with _as_user(requester, is_superadmin=False):
            resp = await async_test_client.get(f"{BASE}/human/config/{p.id}")
        assert resp.status_code == 403, resp.text
        assert "permission" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_no_eval_config_returns_empty_shape(
        self, async_test_client, async_test_db
    ):
        """A project with evaluation_config=None returns the empty-config
        envelope (no available_dimensions default kicks in here)."""
        owner = await _make_user(async_test_db)
        p, _ = await _setup_project(async_test_db, owner, evaluation_config=None)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/human/config/{p.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {
            "project_id": p.id,
            "human_methods": {},
            "available_dimensions": [],
        }

    @pytest.mark.asyncio
    async def test_extracts_human_methods_and_likert_dimensions(
        self, async_test_client, async_test_db
    ):
        """selected_methods with human entries surface in human_methods; a
        likert_scale method carrying parameters.dimensions lifts those into
        available_dimensions."""
        cfg = {
            "selected_methods": {
                "answer": {
                    "automated": ["bleu"],
                    "human": [
                        {
                            "name": "likert_scale",
                            "parameters": {"dimensions": ["correctness", "completeness"]},
                        }
                    ],
                },
                # summary has no human entry → excluded from human_methods.
                "summary": {"automated": ["rouge"]},
            }
        }
        owner = await _make_user(async_test_db)
        p, _ = await _setup_project(async_test_db, owner, evaluation_config=cfg)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/human/config/{p.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "answer" in body["human_methods"]
        assert "summary" not in body["human_methods"]
        assert set(body["available_dimensions"]) == {"correctness", "completeness"}
        assert body["evaluation_config"] == cfg

    @pytest.mark.asyncio
    async def test_default_dimensions_when_no_likert_params(
        self, async_test_client, async_test_db
    ):
        """A human method without likert dimensions falls back to the four
        canonical defaults."""
        cfg = {
            "selected_methods": {
                "answer": {"human": ["preference"]},
            }
        }
        owner = await _make_user(async_test_db)
        p, _ = await _setup_project(async_test_db, owner, evaluation_config=cfg)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.get(f"{BASE}/human/config/{p.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "answer" in body["human_methods"]
        assert set(body["available_dimensions"]) == {
            "correctness", "completeness", "style", "usability",
        }


# ===========================================================================
# DELETE /human/session/{session_id}  (ASYNC)
# ===========================================================================


@pytest.mark.integration
class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_missing_session_404(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.delete(
                f"{BASE}/human/session/missing-{uuid.uuid4().hex}"
            )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_owner_non_superadmin_403(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        requester = await _make_user(async_test_db, is_superadmin=False)
        p, _ = await _setup_project(async_test_db, owner)
        s = await _make_session(async_test_db, p, owner.id)
        await async_test_db.commit()

        with _as_user(requester, is_superadmin=False):
            resp = await async_test_client.delete(f"{BASE}/human/session/{s.id}")
        assert resp.status_code == 403, resp.text
        assert "permission" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_cascades_likert_and_preference(
        self, async_test_client, async_test_db
    ):
        """Deleting a session also removes its child Likert + Preference rows,
        then the session itself."""
        owner = await _make_user(async_test_db)
        p, tasks = await _setup_project(async_test_db, owner, num_tasks=1)
        s = await _make_session(async_test_db, p, owner.id)
        # Seed one likert and one preference row under the session.
        async_test_db.add(LikertScaleEvaluation(
            id=_uid(), session_id=s.id, task_id=tasks[0].id,
            response_id="r1", dimension="correctness", rating=4,
        ))
        async_test_db.add(PreferenceRanking(
            id=_uid(), session_id=s.id, task_id=tasks[0].id,
            response_a_id="a", response_b_id="b", winner="a",
        ))
        await async_test_db.commit()

        # Sanity: children exist before delete.
        likert_before = (
            await async_test_db.execute(
                select(LikertScaleEvaluation).where(
                    LikertScaleEvaluation.session_id == s.id
                )
            )
        ).scalars().all()
        pref_before = (
            await async_test_db.execute(
                select(PreferenceRanking).where(PreferenceRanking.session_id == s.id)
            )
        ).scalars().all()
        assert len(likert_before) == 1
        assert len(pref_before) == 1

        with _as_user(owner):
            resp = await async_test_client.delete(f"{BASE}/human/session/{s.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["session_id"] == s.id

        # DB state: everything gone.
        async_test_db.expire_all()
        sess_after = (
            await async_test_db.execute(
                select(HumanEvaluationSession).where(HumanEvaluationSession.id == s.id)
            )
        ).scalar_one_or_none()
        likert_after = (
            await async_test_db.execute(
                select(LikertScaleEvaluation).where(
                    LikertScaleEvaluation.session_id == s.id
                )
            )
        ).scalars().all()
        pref_after = (
            await async_test_db.execute(
                select(PreferenceRanking).where(PreferenceRanking.session_id == s.id)
            )
        ).scalars().all()
        assert sess_after is None
        assert likert_after == []
        assert pref_after == []

    @pytest.mark.asyncio
    async def test_owner_can_delete_own_session(self, async_test_client, async_test_db):
        """A non-superadmin session owner can delete their own session (the
        ``evaluator_id == current_user.id`` arm of the permission check)."""
        owner = await _make_user(async_test_db)
        actor = await _make_user(async_test_db, is_superadmin=False)
        p, _ = await _setup_project(async_test_db, owner)
        # Session owned by the (non-superadmin) actor; the actor deletes it.
        s = await _make_session(async_test_db, p, actor.id)
        await async_test_db.commit()

        with _as_user(actor, is_superadmin=False):
            resp = await async_test_client.delete(f"{BASE}/human/session/{s.id}")
        assert resp.status_code == 200, resp.text
        async_test_db.expire_all()
        sess_after = (
            await async_test_db.execute(
                select(HumanEvaluationSession).where(HumanEvaluationSession.id == s.id)
            )
        ).scalar_one_or_none()
        assert sess_after is None
