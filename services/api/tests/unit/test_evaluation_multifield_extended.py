"""
Unit tests for routers/evaluations/multi_field.py to increase coverage.
Tests run_evaluation, get_available_fields, get_project_evaluation_results,
and get_evaluation_run_results endpoints.

``run_evaluation`` (POST /run) is still sync, so ``TestRunEvaluation`` keeps the
Mock(spec=Session) / get_db-override lane. The other three endpoints were
migrated to the async DB lane (``Depends(get_async_db)`` + ``await
db.execute``), so their tests seed real rows via ``async_test_db`` and drive the
surface through ``async_test_client`` (superadmin user → access short-circuits;
the ``*_async`` access helpers are patched only for the 403 branch).
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
    mock_q.order_by.return_value = mock_q
    mock_q.group_by.return_value = mock_q
    mock_q.distinct.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


# ---- Async helpers ---------------------------------------------------------


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


def _async_false():
    async def _f(*args, **kwargs):
        return False

    return _f


async def _seed_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"mf-ext-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Multifield Ext User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(db, owner, *, label_config='<View><Text name="text" value="$text"/></View>'):
    p = Project(
        id=_uid(),
        title=f"MF Ext {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        label_config=label_config,
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_eval_run(db, project, owner, *, eval_metadata, metrics=None, **kwargs):
    er = EvaluationRun(
        id=kwargs.pop("id", _uid()),
        project_id=project.id,
        model_id=kwargs.pop("model_id", "gpt-4"),
        evaluation_type_ids=kwargs.pop("evaluation_type_ids", ["bleu"]),
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
# run_evaluation (still SYNC)
# ---------------------------------------------------------------------------


class TestRunEvaluation:
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
                            "id": "cfg1",
                            "metric": "bleu",
                            "prediction_fields": ["pred"],
                            "reference_fields": ["ref"],
                        }
                    ],
                },
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_configs_provided(self):
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
            with patch("routers.evaluations.multi_field.run.auth_service") as mock_auth, \
                 patch("routers.evaluations.multi_field.run.resolve_user_org_for_project", return_value="org-1"):
                mock_auth.check_project_access.return_value = True
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
            with patch("routers.evaluations.multi_field.run.auth_service") as mock_auth, \
                 patch("routers.evaluations.multi_field.run.resolve_user_org_for_project", return_value="org-1"):
                mock_auth.check_project_access.return_value = True
                resp = client.post(
                    "/api/evaluations/run",
                    json={
                        "project_id": "p-1",
                        "evaluation_configs": [
                            {
                                "id": "cfg1",
                                "metric": "bleu",
                                "prediction_fields": ["pred"],
                                "reference_fields": ["ref"],
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
            with patch("routers.evaluations.multi_field.run.auth_service") as mock_auth, \
                 patch("routers.evaluations.multi_field.run.resolve_user_org_for_project", return_value="org-1"):
                mock_auth.check_project_access.return_value = False
                resp = client.post(
                    "/api/evaluations/run",
                    json={
                        "project_id": "p-1",
                        "evaluation_configs": [
                            {
                                "id": "cfg1",
                                "metric": "bleu",
                                "prediction_fields": ["pred"],
                                "reference_fields": ["ref"],
                            }
                        ],
                    },
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_successful_run(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.group_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q

        # First .first() returns project, second returns model_id tuple (model_id, count)
        first_calls = [0]

        def first_side_effect():
            first_calls[0] += 1
            if first_calls[0] == 1:
                return project
            return ("gpt-4", 10)  # model query result as tuple
        mock_q.first.side_effect = first_side_effect
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.multi_field.run.auth_service") as mock_auth, \
                 patch("routers.evaluations.multi_field.run.resolve_user_org_for_project", return_value="org-1"), \
                 patch("routers.evaluations.multi_field.run.celery_app") as mock_celery:
                mock_auth.check_project_access.return_value = True
                mock_task = Mock()
                mock_task.id = "celery-task-123"
                mock_celery.send_task.return_value = mock_task
                resp = client.post(
                    "/api/evaluations/run",
                    json={
                        "project_id": "p-1",
                        "evaluation_configs": [
                            {
                                "id": "cfg1",
                                "metric": "bleu",
                                "prediction_fields": ["pred"],
                                "reference_fields": ["ref"],
                            }
                        ],
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "started"
                assert data["evaluation_configs_count"] == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_available_fields (ASYNC)
# ---------------------------------------------------------------------------


class TestGetAvailableFields:
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
        project = await _seed_project(async_test_db, owner, label_config=None)
        await async_test_db.commit()
        with _as_user(viewer), patch(
            "routers.evaluations.multi_field.fields.auth_service.check_project_access_async",
            new=_async_false(),
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/available-fields"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_project_fields(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner, label_config=None)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/available-fields"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "model_response_fields" in data
        assert "human_annotation_fields" in data
        assert "reference_fields" in data


# ---------------------------------------------------------------------------
# get_project_evaluation_results (ASYNC)
# ---------------------------------------------------------------------------


class TestGetProjectEvaluationResults:
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
    async def test_access_denied(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        viewer = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, owner)
        await async_test_db.commit()
        with _as_user(viewer), patch(
            "routers.evaluations.multi_field.results.auth_service.check_project_access_async",
            new=_async_false(),
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_results(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["evaluations"] == []

    @pytest.mark.asyncio
    async def test_with_evaluation_results(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await _seed_eval_run(
            async_test_db,
            project,
            owner,
            id="eval-1-" + _uid()[:8],
            model_id="gpt-4",
            samples_evaluated=10,
            completed_at=datetime.now(timezone.utc),
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfg1", "metric": "bleu"}],
                "samples_passed": 8,
                "samples_failed": 2,
                "samples_skipped": 0,
            },
            metrics={"cfg1|pred|ref|bleu": 0.85},
        )
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/project/{project.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["evaluations"][0]["evaluation_id"].startswith("eval-1-")

    @pytest.mark.asyncio
    async def test_latest_only_false(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        await _seed_eval_run(
            async_test_db,
            project,
            owner,
            model_id="gpt-4",
            samples_evaluated=10,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime.now(timezone.utc),
            eval_metadata={
                "evaluation_type": "evaluation",
                "samples_passed": 0,
                "samples_failed": 0,
                "samples_skipped": 0,
            },
        )
        await _seed_eval_run(
            async_test_db,
            project,
            owner,
            model_id="gpt-3.5",
            samples_evaluated=5,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            completed_at=datetime.now(timezone.utc),
            eval_metadata={
                "evaluation_type": "evaluation",
                "samples_passed": 0,
                "samples_failed": 0,
                "samples_skipped": 0,
            },
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
# get_evaluation_run_results (ASYNC)
# ---------------------------------------------------------------------------


class TestGetEvaluationRunResults:
    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_client, async_test_db):
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
            eval_metadata={"evaluation_type": "something_else"},
        )
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{er.id}"
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        viewer = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, owner)
        er = await _seed_eval_run(
            async_test_db,
            project,
            owner,
            eval_metadata={"evaluation_type": "evaluation"},
        )
        await async_test_db.commit()
        with _as_user(viewer), patch(
            "routers.evaluations.multi_field.results.check_project_accessible_async",
            new=_async_false(),
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{er.id}"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_successful_results(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        er = await _seed_eval_run(
            async_test_db,
            project,
            owner,
            samples_evaluated=10,
            completed_at=datetime.now(timezone.utc),
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfg1"}],
                "samples_passed": 8,
                "samples_failed": 1,
                "samples_skipped": 1,
            },
            metrics={
                "cfg1|answer|reference|bleu": 0.85,
                "cfg1|answer|reference|rouge_l": 0.9,
            },
        )
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{er.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["evaluation_id"] == er.id
        assert data["samples_evaluated"] == 10
        assert "cfg1" in data["results_by_config"]

    @pytest.mark.asyncio
    async def test_no_eval_metadata(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        er = await _seed_eval_run(
            async_test_db,
            project,
            owner,
            eval_metadata=None,
        )
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(
                f"/api/evaluations/run/results/{er.id}"
            )
        assert resp.status_code == 400
