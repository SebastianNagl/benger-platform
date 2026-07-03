"""
Unit tests for routers/evaluations/multi_field.py to increase branch coverage.
Covers run evaluation, available fields, and project evaluation results endpoints.

The available-fields and results endpoints were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``), so the
``db.query``-Mock / ``get_db``-override pattern no longer reaches those
handlers. Their tests now seed real rows via ``async_test_db`` and drive the
surface through ``async_test_client`` (superadmin user → access short-circuits;
the access helpers are patched with ``AsyncMock`` only for the 403 branch).
``run_evaluation`` (POST /run) is still sync, so ``TestRunEvaluation`` keeps the
Mock(spec=Session) lane.
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
from database import get_db
from auth_module.dependencies import require_user
from models import EvaluationRun, User
from project_models import Project


def _uid() -> str:
    return str(uuid.uuid4())


def _make_user(is_superadmin=True, user_id="user-123"):
    return AuthUser(
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
    mock_q.outerjoin.return_value = mock_q
    mock_q.group_by.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.distinct.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


# ---- Async helpers (seed real rows for the migrated endpoints) -------------


@contextmanager
def _as_user(db_user: User):
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


async def _seed_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"mf-unit-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Multifield Unit User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(db, owner):
    p = Project(
        id=_uid(),
        title=f"MF Unit {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_eval_run(db, project, owner, *, eval_metadata, metrics=None, **kwargs):
    er = EvaluationRun(
        id=kwargs.pop("id", _uid()),
        project_id=project.id,
        model_id=kwargs.pop("model_id", "gpt-4"),
        evaluation_type_ids=kwargs.pop("evaluation_type_ids", ["rouge_l"]),
        metrics=metrics or {},
        eval_metadata=eval_metadata,
        status=kwargs.pop("status", "completed"),
        samples_evaluated=kwargs.pop("samples_evaluated", 0),
        created_by=owner.id,
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        completed_at=kwargs.pop("completed_at", None),
        **kwargs,
    )
    db.add(er)
    await db.flush()
    return er


# ---------------------------------------------------------------------------
# Run Evaluation (still SYNC — Mock(spec=Session) lane)
# ---------------------------------------------------------------------------


class TestRunEvaluation:
    @pytest.fixture(autouse=True)
    def _noop_write_window(self):
        # Dev-body addition: run_evaluation now calls enforce_project_write_window
        # before the config-validation branches. No-op it so these mock-db unit
        # tests exercise the 400/403/404/200 logic they target.
        with patch("routers.evaluations.multi_field.run.enforce_project_write_window"):
            yield

    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.post(
                "/api/evaluations/run",
                json={
                    "project_id": "nonexistent",
                    "evaluation_configs": [
                        {
                            "id": "c1",
                            "metric": "rouge_l",
                            "prediction_fields": ["answer"],
                            "reference_fields": ["gold"],
                        }
                    ],
                },
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_configs(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.multi_field.run.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                with patch("routers.evaluations.multi_field.run.resolve_user_org_for_project", return_value=None):
                    resp = client.post(
                        "/api/evaluations/run",
                        json={
                            "project_id": "p-1",
                            "evaluation_configs": [],
                        },
                    )
                    assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_no_enabled_configs(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.multi_field.run.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = True
                with patch("routers.evaluations.multi_field.run.resolve_user_org_for_project", return_value=None):
                    resp = client.post(
                        "/api/evaluations/run",
                        json={
                            "project_id": "p-1",
                            "evaluation_configs": [
                                {
                                    "id": "c1",
                                    "metric": "rouge_l",
                                    "prediction_fields": ["answer"],
                                    "reference_fields": ["gold"],
                                    "enabled": False,
                                }
                            ],
                        },
                    )
                    assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.multi_field.run.auth_service") as mock_auth:
                mock_auth.check_project_access.return_value = False
                with patch("routers.evaluations.multi_field.run.resolve_user_org_for_project", return_value=None):
                    resp = client.post(
                        "/api/evaluations/run",
                        json={
                            "project_id": "p-1",
                            "evaluation_configs": [
                                {
                                    "id": "c1",
                                    "metric": "rouge_l",
                                    "prediction_fields": ["answer"],
                                    "reference_fields": ["gold"],
                                }
                            ],
                        },
                    )
                    assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Available Fields (ASYNC)
# ---------------------------------------------------------------------------


class TestAvailableFields:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/available-fields"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        viewer = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, owner)
        await async_test_db.commit()
        with _as_user(viewer), patch(
            "routers.evaluations.multi_field.fields.auth_service.check_project_access_async",
            new_callable=lambda: _async_false(),
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/available-fields"
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Project Evaluation Results (ASYNC)
# ---------------------------------------------------------------------------


class TestProjectEvaluationResults:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/run/results/project/nonexistent"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_with_results(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await _seed_eval_run(
            async_test_db,
            project,
            owner,
            model_id="gpt-4",
            status="completed",
            samples_evaluated=10,
            completed_at=datetime.now(timezone.utc),
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "c1", "metric": "rouge_l"}],
                "samples_passed": 8,
                "samples_failed": 2,
                "samples_skipped": 0,
            },
            metrics={"c1|answer|gold|rouge_l": 0.85},
        )
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["evaluations"][0]["model_id"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_latest_only_false(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await _seed_eval_run(
            async_test_db,
            project,
            owner,
            model_id="gpt-4",
            samples_evaluated=5,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            eval_metadata={"evaluation_type": "evaluation", "configs": []},
        )
        await _seed_eval_run(
            async_test_db,
            project,
            owner,
            model_id="claude-3",
            samples_evaluated=3,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            eval_metadata={"evaluation_type": "evaluation"},
        )
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}?latest_only=false"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2


# ---------------------------------------------------------------------------
# Get Evaluation Run Results (ASYNC)
# ---------------------------------------------------------------------------


class TestGetEvaluationRunResults:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/run/results/nonexistent"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_not_evaluation_run(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        er = await _seed_eval_run(
            async_test_db,
            project,
            owner,
            eval_metadata={"evaluation_type": "generation"},
        )
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{er.id}"
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_success(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        er = await _seed_eval_run(
            async_test_db,
            project,
            owner,
            status="completed",
            samples_evaluated=6,
            completed_at=datetime.now(timezone.utc),
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [],
                "samples_passed": 5,
                "samples_failed": 1,
                "samples_skipped": 0,
            },
            metrics={"c1|answer|gold|rouge_l": 0.85},
        )
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{er.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "results_by_config" in data


def _async_false():
    async def _f(*args, **kwargs):
        return False

    return _f
