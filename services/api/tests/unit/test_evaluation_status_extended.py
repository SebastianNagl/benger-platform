"""
Unit tests for routers/evaluations/status.py to increase coverage.
Tests evaluation status, SSE streaming, evaluation types, and supported metrics.
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
from models import EvaluationRun as DBEvaluationRun
from models import EvaluationType as DBEvaluationType
from models import User as DBUser


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
        username=f"evste-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Eval Status User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_eval_run(db, *, project_id=None, status="completed", error_message=None):
    run = DBEvaluationRun(
        id=_uid(),
        project_id=project_id,
        model_id="gpt-4",
        evaluation_type_ids=[],
        metrics={},
        status=status,
        error_message=error_message,
        samples_evaluated=10,
        created_by="owner",
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    return run


async def _seed_eval_type(db, *, type_id, name="BLEU", category="text", is_active=True):
    et = DBEvaluationType(
        id=type_id,
        name=name,
        description=f"{name} score",
        category=category,
        higher_is_better=True,
        value_range={"min": 0, "max": 1},
        applicable_project_types=[],
        is_active=is_active,
    )
    db.add(et)
    await db.commit()
    return et


# ---------------------------------------------------------------------------
# get_evaluation_status
# ---------------------------------------------------------------------------


class TestGetEvaluationStatus:
    """get_evaluation_status is async (Depends(get_async_db))."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/evaluation/status/nonexistent"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db, is_superadmin=False)
        run = await _seed_eval_run(async_test_db, project_id=None, status="running")
        with _as_user(user, is_superadmin=False), patch(
            "routers.evaluations.status.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/evaluation/status/{run.id}"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_success(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        run = await _seed_eval_run(
            async_test_db, project_id=None, status="completed", error_message="Done"
        )
        # Superadmin short-circuits the access check to True.
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/evaluation/status/{run.id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run.id
        assert data["status"] == "completed"


# ---------------------------------------------------------------------------
# get_evaluations (list all)
# ---------------------------------------------------------------------------


class TestGetEvaluations:
    def test_empty_list(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.order_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=None):
                resp = client.get("/api/evaluations/")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_with_results(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.project_id = "p-1"
        eval_run.model_id = "gpt-4"
        eval_run.metrics = {"bleu": 0.8}
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.status = "completed"
        eval_run.eval_metadata = {"key": "value"}
        eval_run.samples_evaluated = 10

        mock_q = MagicMock()
        mock_q.order_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=None):
                resp = client.get("/api/evaluations/")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) == 1
                assert data[0]["id"] == "eval-1"
        finally:
            app.dependency_overrides.clear()

    def test_no_accessible_projects(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=[]):
                resp = client.get("/api/evaluations/")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_with_org_scoped_results(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)
        mock_db = _mock_db()

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.project_id = "p-1"
        eval_run.model_id = "gpt-4"
        eval_run.metrics = {}
        eval_run.created_at = datetime.now(timezone.utc)
        eval_run.status = "completed"
        eval_run.eval_metadata = {}
        eval_run.samples_evaluated = 5

        mock_q = MagicMock()
        mock_q.order_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_accessible_project_ids", return_value=["p-1"]):
                resp = client.get("/api/evaluations/")
                assert resp.status_code == 200
                assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_evaluation_types
# ---------------------------------------------------------------------------


class TestGetEvaluationTypes:
    def test_empty_types(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_with_types(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_type = Mock()
        eval_type.id = "bleu"
        eval_type.name = "BLEU Score"
        eval_type.description = "Bilingual Evaluation Understudy"
        eval_type.category = "text"
        eval_type.higher_is_better = True
        eval_type.value_range = {"min": 0, "max": 1}
        eval_type.applicable_project_types = ["text_generation"]
        eval_type.is_active = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [eval_type]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["id"] == "bleu"
        finally:
            app.dependency_overrides.clear()

    def test_filter_by_category(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        eval_type = Mock()
        eval_type.id = "bleu"
        eval_type.name = "BLEU"
        eval_type.description = "bleu"
        eval_type.category = "text"
        eval_type.higher_is_better = True
        eval_type.value_range = {}
        eval_type.applicable_project_types = []
        eval_type.is_active = True

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [eval_type]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/evaluation-types?category=text")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_filter_by_task_type(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.status.get_evaluation_types_for_task_type", return_value=[]):
                resp = client.get("/api/evaluations/evaluation-types?task_type_id=text_gen")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# get_evaluation_type (single)
# ---------------------------------------------------------------------------


class TestGetEvaluationType:
    """get_evaluation_type (single, by id) is async (Depends(get_async_db))."""

    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/evaluation-types/nonexistent"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_found(self, async_test_client, async_test_db):
        user = await _make_db_user(async_test_db)
        type_id = f"bleu-{_uid()[:8]}"
        await _seed_eval_type(async_test_db, type_id=type_id, name="BLEU")
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/evaluation-types/{type_id}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == type_id


# ---------------------------------------------------------------------------
# get_supported_metrics
# ---------------------------------------------------------------------------


class TestDeriveEvaluationConfigs:
    """Test the _derive_evaluation_configs_from_selected_methods helper."""

    def test_empty_selected_methods(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        result = _derive_evaluation_configs_from_selected_methods({})
        assert result == []

    def test_non_dict_selections(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        result = _derive_evaluation_configs_from_selected_methods({"field1": "not_a_dict"})
        assert result == []

    def test_with_string_metrics(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["bleu", "rouge_l"],
                "field_mapping": {
                    "prediction_field": "pred_answer",
                    "reference_field": "ref_answer",
                },
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 2
        assert result[0]["metric"] == "bleu"
        assert result[0]["prediction_fields"] == ["pred_answer"]
        assert result[0]["reference_fields"] == ["ref_answer"]
        assert result[1]["metric"] == "rouge_l"

    def test_with_dict_metrics_and_parameters(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "text": {
                "automated": [
                    {"name": "llm_judge", "parameters": {"model": "gpt-4"}}
                ],
                "field_mapping": {
                    "prediction_field": "pred",
                    "reference_field": "ref",
                },
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 1
        assert result[0]["metric"] == "llm_judge"
        assert result[0]["metric_parameters"] == {"model": "gpt-4"}

    def test_with_no_field_mapping(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": ["bleu"],
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert len(result) == 1
        # Should use field_name as default for both pred and ref
        assert result[0]["prediction_fields"] == ["answer"]
        assert result[0]["reference_fields"] == ["answer"]

    def test_with_empty_metric_name(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods
        selected = {
            "answer": {
                "automated": [{"name": ""}],
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(selected)
        assert result == []  # Empty name should be skipped
