"""
Unit tests for routers/evaluations/results.py to increase coverage.
Tests score extraction, per-sample results, export, and comparison endpoints.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from main import app
from auth_module.models import User
from auth_module.dependencies import require_user
from models import EvaluationRun, User as DBUser
from project_models import Project


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


async def _seed_eval_run(async_test_db, project_id=None):
    """Insert an owner User + Project + a minimal valid EvaluationRun (FKs:
    evaluation_runs.project_id -> projects.id, projects.created_by -> users.id)
    and return the EvaluationRun.
    """
    if project_id is None:
        project_id = f"p-{uuid.uuid4()}"
    owner_id = f"seed-user-{uuid.uuid4()}"

    owner = DBUser(
        id=owner_id,
        username=f"seed_{owner_id}",
        email=f"{owner_id}@example.com",
        name="Seed User",
    )
    async_test_db.add(owner)
    await async_test_db.flush()

    project = Project(id=project_id, title="Seed Project", created_by=owner_id)
    async_test_db.add(project)
    await async_test_db.flush()

    er = EvaluationRun(
        id=str(uuid.uuid4()),
        project_id=project_id,
        model_id="gpt-4",
        evaluation_type_ids=[],
        metrics={},
        status="completed",
        created_by=owner_id,
    )
    async_test_db.add(er)
    await async_test_db.commit()
    return er


# ---------------------------------------------------------------------------
# _extract_primary_score helper
# ---------------------------------------------------------------------------


class TestExtractPrimaryScore:
    def test_none_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score(None) is None

    def test_empty_metrics(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score({}) is None

    def test_llm_judge_custom(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": 0.8}
        assert _extract_primary_score(metrics) == 0.8

    def test_score_key(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"score": 0.9}
        assert _extract_primary_score(metrics) == 0.9

    def test_overall_score_key(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"overall_score": 0.85}
        assert _extract_primary_score(metrics) == 0.85

    def test_llm_judge_arbitrary(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_accuracy": 0.7}
        assert _extract_primary_score(metrics) == 0.7

    def test_ignores_non_numeric(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": "not_a_number"}
        result = _extract_primary_score(metrics)
        assert result is None or isinstance(result, (int, float))

    def test_priority_order(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {
            "llm_judge_custom": 0.5,
            "score": 0.3,
        }
        assert _extract_primary_score(metrics) == 0.5


# ---------------------------------------------------------------------------
# GET /evaluations/results/{project_id} - list evaluation results
# ---------------------------------------------------------------------------


class TestGetProjectEvaluationResults:
    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        # Access is checked FIRST, before any DB lookup — the patch alone drives 403.
        user = _make_user(is_superadmin=False)
        app.dependency_overrides[require_user] = lambda: user
        try:
            with patch(
                "routers.evaluations.results.core.check_project_accessible_async",
                new=AsyncMock(return_value=False),
            ):
                resp = await async_test_client.get("/api/evaluations/results/p-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.asyncio
    async def test_returns_ok_for_accessible_project(self, async_test_client, async_test_db):
        # Superadmin short-circuits access to True; empty results is a valid 200 ([]).
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = await async_test_client.get("/api/evaluations/results/p-1")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(require_user, None)


# ---------------------------------------------------------------------------
# GET /evaluations/{evaluation_id}/samples
# ---------------------------------------------------------------------------


class TestGetEvaluationSamples:
    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_client, async_test_db):
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = await async_test_client.get("/api/evaluations/nonexistent/samples")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        er = await _seed_eval_run(async_test_db)
        user = _make_user(is_superadmin=False)
        app.dependency_overrides[require_user] = lambda: user
        try:
            with patch(
                "routers.evaluations.results.core.check_project_accessible_async",
                new=AsyncMock(return_value=False),
            ):
                resp = await async_test_client.get(f"/api/evaluations/{er.id}/samples")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(require_user, None)


# ---------------------------------------------------------------------------
# GET /evaluations/{evaluation_id}/metrics/{metric}/distribution
# ---------------------------------------------------------------------------


class TestGetMetricDistribution:
    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_client, async_test_db):
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = await async_test_client.get(
                "/api/evaluations/nonexistent/metrics/bleu/distribution"
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        er = await _seed_eval_run(async_test_db)
        user = _make_user(is_superadmin=False)
        app.dependency_overrides[require_user] = lambda: user
        try:
            with patch(
                "routers.evaluations.results.distributions.check_project_accessible_async",
                new=AsyncMock(return_value=False),
            ):
                resp = await async_test_client.get(
                    f"/api/evaluations/{er.id}/metrics/bleu/distribution"
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(require_user, None)


# ---------------------------------------------------------------------------
# POST /evaluations/export/{project_id}
# ---------------------------------------------------------------------------


class TestExportEvaluations:
    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        # Export checks access first — the patch alone drives 403, no seeding needed.
        user = _make_user(is_superadmin=False)
        app.dependency_overrides[require_user] = lambda: user
        try:
            with patch(
                "routers.evaluations.results.core.check_project_accessible_async",
                new=AsyncMock(return_value=False),
            ):
                resp = await async_test_client.post("/api/evaluations/export/p-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(require_user, None)


# ---------------------------------------------------------------------------
# GET /{evaluation_id}/results/by-task-model
# ---------------------------------------------------------------------------


class TestResultsByTaskModel:
    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_client, async_test_db):
        user = _make_user()
        app.dependency_overrides[require_user] = lambda: user
        try:
            resp = await async_test_client.get(
                "/api/evaluations/nonexistent/results/by-task-model"
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(require_user, None)

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        er = await _seed_eval_run(async_test_db)
        user = _make_user(is_superadmin=False)
        app.dependency_overrides[require_user] = lambda: user
        try:
            with patch(
                "routers.evaluations.results.by_task_model.check_project_accessible_async",
                new=AsyncMock(return_value=False),
            ):
                resp = await async_test_client.get(
                    f"/api/evaluations/{er.id}/results/by-task-model"
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.pop(require_user, None)
