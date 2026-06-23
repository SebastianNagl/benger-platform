"""
Unit tests for routers/evaluations/config.py to increase coverage.
Tests evaluation config CRUD, answer type detection, and field types.

The GET evaluation-config / detect-answer-types / field-types handlers were
migrated to the async DB lane (``Depends(get_async_db)`` + ``await
db.execute(select(...))``), so the ``db.query``-Mock / ``get_db``-override
pattern no longer reaches them. Those branches now seed real rows via
``async_test_db`` and drive the surface through ``async_test_client``. The PUT
update-config handler stays sync and keeps the legacy ``client`` / ``get_db``
mock pattern unchanged.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from database import get_db
from models import User
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


async def _seed_user(db, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"ece-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Eval Config Ext User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(db, owner, **kwargs):
    proj = Project(
        id=_uid(),
        title=f"Eval Config Ext {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        **kwargs,
    )
    db.add(proj)
    await db.commit()
    return proj


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_db.query.return_value = mock_q
    return mock_db


# ---------------------------------------------------------------------------
# get_project_evaluation_config
# ---------------------------------------------------------------------------


class TestGetProjectEvaluationConfig:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/evaluation-config")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, user, evaluation_config=None)

        with _as_user(user), patch(
            "routers.evaluations.config.auth_service.check_project_access_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_label_config(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            evaluation_config=None,
            label_config=None,
            label_config_version=None,
        )

        with _as_user(user), patch(
            "routers.evaluations.config.auth_service.check_project_access_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected_answer_types"] == []

    @pytest.mark.asyncio
    async def test_existing_config(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            label_config="<View><TextArea name='answer'/></View>",
            label_config_version="v1",
            evaluation_config={
                "detected_answer_types": [{"name": "answer", "type": "text"}],
                "available_methods": {},
                "selected_methods": {},
                "label_config_version": "v1",
            },
        )

        with _as_user(user), patch(
            "routers.evaluations.config.auth_service.check_project_access_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_force_regenerate(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            label_config="<View><TextArea name='answer' toName='text'/></View>",
            label_config_version="v2",
            evaluation_config={"label_config_version": "v1"},
        )

        with _as_user(user), patch(
            "routers.evaluations.config.auth_service.check_project_access_async",
            return_value=True,
        ), patch("routers.evaluations.config.generate_evaluation_config") as mock_gen:
            mock_gen.return_value = {
                "detected_answer_types": [],
                "available_methods": {},
                "selected_methods": {},
                "label_config_version": "v2",
            }
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config?force_regenerate=true"
            )
            assert resp.status_code == 200
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_lazy_migration_derive_configs(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            label_config="<View><TextArea name='answer'/></View>",
            label_config_version="v1",
            evaluation_config={
                "detected_answer_types": [],
                "available_methods": {},
                "selected_methods": {
                    "answer": {
                        "automated": ["bleu"],
                        "field_mapping": {
                            "prediction_field": "pred",
                            "reference_field": "ref",
                        },
                    }
                },
                "label_config_version": "v1",
            },
        )

        with _as_user(user), patch(
            "routers.evaluations.config.auth_service.check_project_access_async",
            return_value=True,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "evaluation_configs" in data


# ---------------------------------------------------------------------------
# update_project_evaluation_config
# ---------------------------------------------------------------------------


class TestUpdateProjectEvaluationConfig:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.put(
                "/api/evaluations/projects/nonexistent/evaluation-config",
                json={"selected_methods": {}},
            )
            assert resp.status_code == 404
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
            with patch("routers.evaluations.config.check_project_accessible", return_value=False):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={"selected_methods": {}},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_invalid_field_in_selected_methods(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config_version = "v1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={
                        "selected_methods": {"nonexistent_field": {}},
                        "available_methods": {"answer": {"available_metrics": ["bleu"], "available_human": []}},
                    },
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_invalid_metric(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config_version = "v1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={
                        "selected_methods": {
                            "answer": {
                                "automated": ["nonexistent_metric"],
                            }
                        },
                        "available_methods": {
                            "answer": {
                                "available_metrics": ["bleu"],
                                "available_human": [],
                            }
                        },
                    },
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_successful_update(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        project = Mock()
        project.id = "p-1"
        project.label_config_version = "v1"
        project.evaluation_config = {}

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.evaluations.config.check_project_accessible", return_value=True), \
                 patch("sqlalchemy.orm.attributes.flag_modified"):
                resp = client.put(
                    "/api/evaluations/projects/p-1/evaluation-config",
                    json={
                        "selected_methods": {
                            "answer": {"automated": ["bleu"]}
                        },
                        "available_methods": {
                            "answer": {
                                "available_metrics": ["bleu"],
                                "available_human": [],
                            }
                        },
                    },
                )
                assert resp.status_code == 200
                assert "message" in resp.json()
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# detect_answer_types
# ---------------------------------------------------------------------------


class TestDetectAnswerTypes:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/detect-answer-types"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_no_label_config(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, user, label_config=None)

        with _as_user(user), patch(
            "routers.evaluations.config.check_project_accessible_async", return_value=True
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/detect-answer-types"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected_types"] == []

    @pytest.mark.asyncio
    async def test_with_label_config(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            label_config="<View><TextArea name='answer' toName='text'/></View>",
            evaluation_config=None,
        )

        with _as_user(user), patch(
            "routers.evaluations.config.check_project_accessible_async", return_value=True
        ), patch("routers.evaluations.config.generate_evaluation_config") as mock_gen:
            mock_gen.return_value = {
                "detected_answer_types": [{"name": "answer", "type": "text"}],
                "available_methods": {"answer": {"available_metrics": ["bleu"]}},
            }
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/detect-answer-types"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["detected_types"]) == 1


# ---------------------------------------------------------------------------
# get_field_types_for_llm_judge
# ---------------------------------------------------------------------------


class TestGetFieldTypesForLLMJudge:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/nonexistent/field-types"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_no_label_config(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, user, label_config=None)

        with _as_user(user), patch(
            "routers.evaluations.config.check_project_accessible_async", return_value=True
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/field-types"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["field_types"] == {}

    @pytest.mark.asyncio
    async def test_with_field_types(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            label_config="<View><TextArea name='answer'/></View>",
            evaluation_config=None,
        )

        with _as_user(user), patch(
            "routers.evaluations.config.check_project_accessible_async", return_value=True
        ), patch("routers.evaluations.config.generate_evaluation_config") as mock_gen:
            mock_gen.return_value = {
                "available_methods": {
                    "answer": {
                        "type": "text",
                        "tag": "TextArea",
                        "llm_judge_criteria": ["correctness", "completeness"],
                    }
                }
            }
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/field-types"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data["field_types"]
        assert data["field_types"]["answer"]["type"] == "text"

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, user, label_config="<View/>")

        with _as_user(user), patch(
            "routers.evaluations.config.check_project_accessible_async", return_value=False
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/field-types"
            )
        assert resp.status_code == 403
