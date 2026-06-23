"""
Unit tests for routers/evaluations/human.py to increase branch coverage.
Covers all human evaluation session endpoints.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User as AuthUser
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_user
from models import HumanEvaluationSession
from models import User as DBUser
from project_models import Project, Task


def _make_user(is_superadmin=True, user_id="user-123"):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.join.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.distinct.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user, *, is_superadmin=True):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_db_user(db, *, is_superadmin=True):
    u = DBUser(
        id=_uid(),
        username=f"hu-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Human Eval User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, owner, *, num_tasks=0, evaluation_config=None):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Human Eval {pid[:6]}",
        created_by=owner.id,
        is_private=False,
        evaluation_config=evaluation_config,
    )
    db.add(p)
    await db.flush()
    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=pid,
            data={"text": f"task #{i}"},
            inner_id=i + 1,
            created_by=owner.id,
        )
        db.add(t)
        tasks.append(t)
    await db.flush()
    return p, tasks


async def _make_session(
    db, project, evaluator_id, *, session_type="likert", status="active",
    items_evaluated=0, total_items=2, session_config=None,
):
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
    await db.commit()
    return s


# ---------------------------------------------------------------------------
# Start Session
# ---------------------------------------------------------------------------


class TestStartHumanEvaluationSession:
    def test_permission_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.helpers.check_user_can_edit_project", return_value=False):
                resp = client.post(
                    "/api/evaluations/human/session/start",
                    json={"project_id": "p-1", "session_type": "likert"},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.helpers.check_user_can_edit_project", return_value=True):
                resp = client.post(
                    "/api/evaluations/human/session/start",
                    json={"project_id": "p-1", "session_type": "likert"},
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_start_likert_session(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.count.return_value = 5
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.helpers.check_user_can_edit_project", return_value=True):
                resp = client.post(
                    "/api/evaluations/human/session/start",
                    json={
                        "project_id": "p-1",
                        "session_type": "likert",
                        "dimensions": ["correctness", "completeness"],
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["session_type"] == "likert"
                assert data["total_items"] == 5
        finally:
            app.dependency_overrides.clear()

    def test_start_preference_session(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.count.return_value = 3
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.projects.helpers.check_user_can_edit_project", return_value=True):
                resp = client.post(
                    "/api/evaluations/human/session/start",
                    json={"project_id": "p-1", "session_type": "preference"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["session_type"] == "preference"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Get Next Item
# ---------------------------------------------------------------------------


class TestGetNextEvaluationItem:
    """get_next_evaluation_item is async (Depends(get_async_db))."""

    @pytest.mark.asyncio
    async def test_session_not_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/human/next-item?session_id=nonexistent"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_session_not_active(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        p, _ = await _make_project(async_test_db, user)
        s = await _make_session(async_test_db, p, user.id, status="completed")
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/human/next-item?session_id={s.id}"
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_no_more_items(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        # Project with zero tasks → no next task → session-completed 404.
        p, _ = await _make_project(async_test_db, user, num_tasks=0)
        s = await _make_session(
            async_test_db, p, user.id, status="active",
            items_evaluated=5, total_items=5,
        )
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/human/next-item?session_id={s.id}"
            )
        assert resp.status_code == 404
        assert "completed" in resp.json()["detail"].lower()

    # test_next_item_preference_session removed: The mock DB was too shallow
    # to cover the preference session code path (querying PreferenceRanking
    # and Task models). The test originally accepted 500 to hide the crash.
    # The likert branch is tested properly in test_no_more_items above.


# ---------------------------------------------------------------------------
# Submit Likert Rating
# ---------------------------------------------------------------------------


class TestSubmitLikertRating:
    """submit_likert_rating is async (Depends(get_async_db))."""

    @pytest.mark.asyncio
    async def test_session_not_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/evaluations/human/likert",
                json={
                    "session_id": "nonexistent",
                    "task_id": "t-1",
                    "response_id": "r-1",
                    "ratings": {"correctness": 4},
                },
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_success(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        p, tasks = await _make_project(async_test_db, user, num_tasks=1)
        s = await _make_session(
            async_test_db, p, user.id, session_type="likert", items_evaluated=0
        )
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/evaluations/human/likert",
                json={
                    "session_id": s.id,
                    "task_id": tasks[0].id,
                    "response_id": "r-1",
                    "ratings": {"correctness": 4, "completeness": 5},
                    "comments": {"correctness": "Good!"},
                    "time_spent_seconds": 30,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["items_evaluated"] == 1


# ---------------------------------------------------------------------------
# Submit Preference Ranking
# ---------------------------------------------------------------------------


class TestSubmitPreferenceRanking:
    """submit_preference_ranking is async (Depends(get_async_db))."""

    @pytest.mark.asyncio
    async def test_session_not_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/evaluations/human/preference",
                json={
                    "session_id": "nonexistent",
                    "task_id": "t-1",
                    "response_a_id": "ra",
                    "response_b_id": "rb",
                    "winner": "a",
                },
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_success(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        p, tasks = await _make_project(async_test_db, user, num_tasks=1)
        s = await _make_session(
            async_test_db, p, user.id, session_type="preference", items_evaluated=0
        )
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/evaluations/human/preference",
                json={
                    "session_id": s.id,
                    "task_id": tasks[0].id,
                    "response_a_id": "ra",
                    "response_b_id": "rb",
                    "winner": "a",
                    "confidence": 0.9,
                    "reasoning": "Response A was more complete",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["items_evaluated"] == 1


# ---------------------------------------------------------------------------
# Session Progress
# ---------------------------------------------------------------------------


class TestSessionProgress:
    """get_human_evaluation_progress is async (Depends(get_async_db))."""

    @pytest.mark.asyncio
    async def test_session_not_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/human/session/nonexistent/progress"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_permission_denied(self, async_test_client, async_test_db):
        owner = await _make_db_user(async_test_db)
        requester = await _make_db_user(async_test_db, is_superadmin=False)
        p, _ = await _make_project(async_test_db, owner)
        s = await _make_session(async_test_db, p, owner.id)
        # Non-owner, non-superadmin requests another user's session → 403.
        with _as_user(requester, is_superadmin=False):
            resp = await async_test_client.get(
                f"/api/evaluations/human/session/{s.id}/progress"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_progress_success(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        p, _ = await _make_project(async_test_db, user)
        s = await _make_session(
            async_test_db, p, user.id, items_evaluated=3, total_items=10
        )
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/human/session/{s.id}/progress"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items_evaluated"] == 3
        assert data["progress_percentage"] == 30.0


# ---------------------------------------------------------------------------
# Get Sessions for Project
# ---------------------------------------------------------------------------


class TestGetSessionsForProject:
    """get_human_evaluation_sessions is async (Depends(get_async_db))."""

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()
        with _as_user(user, is_superadmin=False), patch(
            "routers.evaluations.human.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get("/api/evaluations/human/sessions/p-1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_sessions(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        p, _ = await _make_project(async_test_db, user)
        await _make_session(
            async_test_db, p, user.id, session_type="likert",
            items_evaluated=5, total_items=10,
        )
        # Superadmin short-circuits access; assert the persisted session lists.
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/human/sessions/{p.id}"
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Get Human Evaluation Config
# ---------------------------------------------------------------------------


class TestGetHumanEvaluationConfig:
    """get_human_evaluation_config is async (Depends(get_async_db)).

    Access is checked via ``auth_service.check_project_access_async``; a
    superadmin short-circuits that check to True.
    """

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/human/config/nonexistent"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_no_evaluation_config(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        p, _ = await _make_project(async_test_db, user, evaluation_config=None)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/human/config/{p.id}"
            )
        assert resp.status_code == 200
        assert resp.json()["human_methods"] == {}

    @pytest.mark.asyncio
    async def test_with_human_methods(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        p, _ = await _make_project(
            async_test_db,
            user,
            evaluation_config={
                "selected_methods": {
                    "answer": {
                        "human": [
                            {
                                "name": "likert_scale",
                                "parameters": {"dimensions": ["correctness"]},
                            }
                        ]
                    }
                }
            },
        )
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/human/config/{p.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data["human_methods"]


# ---------------------------------------------------------------------------
# Delete Session
# ---------------------------------------------------------------------------


class TestDeleteHumanEvaluationSession:
    """delete_human_evaluation_session is async (Depends(get_async_db))."""

    @pytest.mark.asyncio
    async def test_session_not_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.delete(
                "/api/evaluations/human/session/nonexistent"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_permission_denied(self, async_test_client, async_test_db):
        owner = await _make_db_user(async_test_db)
        requester = await _make_db_user(async_test_db, is_superadmin=False)
        p, _ = await _make_project(async_test_db, owner)
        s = await _make_session(async_test_db, p, owner.id)
        with _as_user(requester, is_superadmin=False):
            resp = await async_test_client.delete(
                f"/api/evaluations/human/session/{s.id}"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_success(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        p, _ = await _make_project(async_test_db, user)
        s = await _make_session(async_test_db, p, user.id)
        with _as_user(user):
            resp = await async_test_client.delete(
                f"/api/evaluations/human/session/{s.id}"
            )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()
