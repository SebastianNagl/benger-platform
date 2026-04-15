"""
Unit tests for routers/evaluations/metadata.py to increase branch coverage.
Direct handler invocation (no TestClient) so pytest-cov tracks coverage.

Covers: get_evaluated_models, get_configured_methods, get_evaluation_history,
get_significance_tests, compute_project_statistics (all aggregation types,
compare_models, correlation, bootstrap, Cohen's d, Cliff's delta, fallback).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth_module.models import User


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


def _mock_request(headers=None):
    mock = Mock()
    mock.headers = headers or {"X-Organization-Context": "private"}
    mock.state = Mock(spec=[])
    return mock


def _mock_db():
    mock_db = MagicMock(spec=Session)
    return mock_db


# ---------------------------------------------------------------------------
# get_evaluated_models
# ---------------------------------------------------------------------------


class TestEvaluatedModelsDeep:
    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_include_configured_with_models_and_scores(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_evaluated_models

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        project.generation_config = {
            "selected_configuration": {"models": ["gpt-4", "claude-3"]}
        }

        eval_run = Mock()
        eval_run.model_id = "gpt-4"
        eval_run.samples_evaluated = 10
        eval_run.completed_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        eval_run.metrics = {"bleu": 0.85, "rouge": 0.70}

        eval_run2 = Mock()
        eval_run2.model_id = "claude-3"
        eval_run2.samples_evaluated = 5
        eval_run2.completed_at = datetime(2025, 5, 1, tzinfo=timezone.utc)
        eval_run2.metrics = {"bleu": 0.90}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q
            mock_q.outerjoin.return_value = mock_q
            mock_q.distinct.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] <= 5:
                mock_q.all.return_value = []
            else:
                mock_q.all.return_value = [eval_run, eval_run2]

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_evaluated_models(
            request=_mock_request(),
            project_id="p-1",
            include_configured=True,
            db=db,
            current_user=_make_user(),
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_no_models_returns_empty_list(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_evaluated_models

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        project.generation_config = None

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q
            mock_q.distinct.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_evaluated_models(
            request=_mock_request(),
            project_id="p-1",
            include_configured=False,
            db=db,
            current_user=_make_user(),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.metadata import get_evaluated_models

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_evaluated_models(
                request=_mock_request(),
                project_id="missing",
                include_configured=False,
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=False)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_access_denied(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_evaluated_models

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        db.query.return_value.filter.return_value.first.return_value = project

        with pytest.raises(HTTPException) as exc:
            await get_evaluated_models(
                request=_mock_request(),
                project_id="p-1",
                include_configured=False,
                db=db,
                current_user=_make_user(is_superadmin=False),
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_exception_returns_500(self):
        from routers.evaluations.metadata import get_evaluated_models

        db = _mock_db()
        db.query.side_effect = RuntimeError("DB connection lost")

        with pytest.raises(HTTPException) as exc:
            await get_evaluated_models(
                request=_mock_request(),
                project_id="p-1",
                include_configured=False,
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_without_include_configured_sorts_by_score_desc(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_evaluated_models

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        project.generation_config = None

        gen_model = Mock()
        gen_model.model_id = "gpt-4"

        eval_run = Mock()
        eval_run.model_id = "gpt-4"
        eval_run.samples_evaluated = 10
        eval_run.completed_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        eval_run.metrics = {"bleu": 0.85}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q
            mock_q.distinct.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen_model]
            elif call_count["n"] <= 5:
                mock_q.all.return_value = []
            else:
                mock_q.all.return_value = [eval_run]

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_evaluated_models(
            request=_mock_request(),
            project_id="p-1",
            include_configured=False,
            db=db,
            current_user=_make_user(),
        )
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_configured_methods
# ---------------------------------------------------------------------------


class TestConfiguredMethodsDeep:
    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_no_evaluation_config(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_configured_methods

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        project.evaluation_config = None
        db.query.return_value.filter.return_value.first.return_value = project

        result = await get_configured_methods(
            request=_mock_request(),
            project_id="p-1",
            db=db,
            current_user=_make_user(),
        )
        assert result["fields"] == []

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_no_selected_methods(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_configured_methods

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {"available_methods": {"field1": {}}, "selected_methods": {}}
        db.query.return_value.filter.return_value.first.return_value = project

        result = await get_configured_methods(
            request=_mock_request(),
            project_id="p-1",
            db=db,
            current_user=_make_user(),
        )
        assert result["fields"] == []

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_with_automated_and_human_methods(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_configured_methods

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {
            "available_methods": {
                "answer": {"type": "text", "to_name": "answer_field"},
            },
            "selected_methods": {
                "answer": {
                    "automated": [
                        "bleu",
                        {"name": "llm_judge_quality", "parameters": {"model": "gpt-4"}},
                    ],
                    "human": ["manual_score"],
                    "field_mapping": "answer_field",
                },
            },
        }

        eval_run = Mock()
        eval_run.model_id = "gpt-4"
        eval_run.metrics = {"bleu": 0.85, "llm_judge_quality": 0.92}
        eval_run.completed_at = datetime(2025, 7, 1, tzinfo=timezone.utc)

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            else:
                mock_q.all.return_value = [eval_run]

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_configured_methods(
            request=_mock_request(),
            project_id="p-1",
            db=db,
            current_user=_make_user(),
        )
        assert len(result["fields"]) == 1
        field = result["fields"][0]
        assert field["field_name"] == "answer"
        assert len(field["automated_methods"]) == 2
        assert len(field["human_methods"]) == 1
        llm_method = [m for m in field["automated_methods"] if m["method_name"] == "llm_judge_quality"]
        assert len(llm_method) == 1
        assert llm_method[0]["method_type"] == "llm-judge"
        assert llm_method[0]["has_results"] is True

    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.metadata import get_configured_methods

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_configured_methods(
                request=_mock_request(),
                project_id="missing",
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=False)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_access_denied(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_configured_methods

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {}
        db.query.return_value.filter.return_value.first.return_value = project

        with pytest.raises(HTTPException) as exc:
            await get_configured_methods(
                request=_mock_request(),
                project_id="p-1",
                db=db,
                current_user=_make_user(is_superadmin=False),
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_exception_returns_500(self):
        from routers.evaluations.metadata import get_configured_methods

        db = _mock_db()
        db.query.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            await get_configured_methods(
                request=_mock_request(),
                project_id="p-1",
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# get_evaluation_history
# ---------------------------------------------------------------------------


class TestEvaluationHistoryDeep:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.metadata import get_evaluation_history

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_evaluation_history(
                request=_mock_request(),
                project_id="missing",
                model_ids=["gpt-4"],
                metric="bleu",
                start_date=None,
                end_date=None,
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=False)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_access_denied(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_evaluation_history

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        db.query.return_value.filter.return_value.first.return_value = project

        with pytest.raises(HTTPException) as exc:
            await get_evaluation_history(
                request=_mock_request(),
                project_id="p-1",
                model_ids=["gpt-4"],
                metric="bleu",
                start_date=None,
                end_date=None,
                db=db,
                current_user=_make_user(is_superadmin=False),
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_with_date_filters_and_ci(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_evaluation_history

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval1 = Mock()
        eval1.model_id = "gpt-4"
        eval1.metrics = {"bleu": 0.85}
        eval1.created_at = datetime(2025, 6, 15, tzinfo=timezone.utc)
        eval1.samples_evaluated = 10
        eval1.eval_metadata = {
            "confidence_intervals": {"bleu": {"lower": 0.80, "upper": 0.90}}
        }

        eval2 = Mock()
        eval2.model_id = "gpt-4"
        eval2.metrics = {"rouge": 0.70}
        eval2.created_at = datetime(2025, 6, 20, tzinfo=timezone.utc)
        eval2.samples_evaluated = 5
        eval2.eval_metadata = None

        eval3 = Mock()
        eval3.model_id = "gpt-4"
        eval3.metrics = {"bleu": "not_a_number"}
        eval3.created_at = datetime(2025, 6, 25, tzinfo=timezone.utc)
        eval3.samples_evaluated = 0
        eval3.eval_metadata = None

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            else:
                mock_q.all.return_value = [eval1, eval2, eval3]

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_evaluation_history(
            request=_mock_request(),
            project_id="p-1",
            model_ids=["gpt-4"],
            metric="bleu",
            start_date="2025-06-01T00:00:00",
            end_date="2025-06-30T00:00:00",
            db=db,
            current_user=_make_user(),
        )
        assert result["metric"] == "bleu"
        assert len(result["data"]) == 1
        assert result["data"][0]["ci_lower"] is not None

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_no_ci_in_metadata(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_evaluation_history

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval1 = Mock()
        eval1.model_id = "gpt-4"
        eval1.metrics = {"bleu": 0.85}
        eval1.created_at = datetime(2025, 6, 15, tzinfo=timezone.utc)
        eval1.samples_evaluated = 10
        eval1.eval_metadata = {"some_other_key": True}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            else:
                mock_q.all.return_value = [eval1]

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_evaluation_history(
            request=_mock_request(),
            project_id="p-1",
            model_ids=["gpt-4"],
            metric="bleu",
            start_date=None,
            end_date=None,
            db=db,
            current_user=_make_user(),
        )
        dp = result["data"][0]
        assert dp["ci_lower"] is None
        assert dp["ci_upper"] is None

    @pytest.mark.asyncio
    async def test_exception_returns_500(self):
        from routers.evaluations.metadata import get_evaluation_history

        db = _mock_db()
        db.query.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            await get_evaluation_history(
                request=_mock_request(),
                project_id="p-1",
                model_ids=["gpt-4"],
                metric="bleu",
                start_date=None,
                end_date=None,
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# get_significance_tests
# ---------------------------------------------------------------------------


class TestSignificanceTestsDeep:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.metadata import get_significance_tests

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_significance_tests(
                request=_mock_request(),
                project_id="missing",
                model_ids=["a", "b"],
                metrics=["bleu"],
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=False)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_access_denied(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_significance_tests

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        db.query.return_value.filter.return_value.first.return_value = project

        with pytest.raises(HTTPException) as exc:
            await get_significance_tests(
                request=_mock_request(),
                project_id="p-1",
                model_ids=["a", "b"],
                metrics=["bleu"],
                db=db,
                current_user=_make_user(is_superadmin=False),
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_stats_not_available(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_significance_tests

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        db.query.return_value.filter.return_value.first.return_value = project

        with patch("routers.leaderboards.STATS_AVAILABLE", False):
            result = await get_significance_tests(
                request=_mock_request(),
                project_id="p-1",
                model_ids=["a", "b"],
                metrics=["bleu"],
                db=db,
                current_user=_make_user(),
            )
        assert result["comparisons"] == []
        assert "not available" in result.get("message", "")

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_with_scores_and_direct_evaluations(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_significance_tests

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        sample1 = Mock()
        sample1.model_id = "model-a"
        sample1.metrics = {"bleu": 0.85}

        sample2 = Mock()
        sample2.model_id = "model-a"
        sample2.metrics = {"bleu": 0.90}

        sample3 = Mock()
        sample3.model_id = "model-b"
        sample3.metrics = {"bleu": 0.70}

        direct_eval = Mock()
        direct_eval.model_id = "model-b"
        direct_eval.metrics = {"bleu": 0.75}

        sample4 = Mock()
        sample4.model_id = "model-a"
        sample4.metrics = None

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [sample1, sample2, sample3, sample4]
            else:
                mock_q.all.return_value = [direct_eval]

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_significance_tests(
            request=_mock_request(),
            project_id="p-1",
            model_ids=["model-a", "model-b"],
            metrics=["bleu"],
            db=db,
            current_user=_make_user(),
        )
        assert "comparisons" in result
        assert len(result["comparisons"]) >= 1

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_insufficient_scores_returns_default(self, mock_org, mock_access):
        from routers.evaluations.metadata import get_significance_tests

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        sample1 = Mock()
        sample1.model_id = "model-a"
        sample1.metrics = {"bleu": 0.85}

        sample2 = Mock()
        sample2.model_id = "model-b"
        sample2.metrics = {"bleu": 0.70}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [sample1, sample2]
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_significance_tests(
            request=_mock_request(),
            project_id="p-1",
            model_ids=["model-a", "model-b"],
            metrics=["bleu"],
            db=db,
            current_user=_make_user(),
        )
        comps = result["comparisons"]
        assert len(comps) == 1
        assert comps[0]["p_value"] == 1.0
        assert comps[0]["significant"] is False

    @pytest.mark.asyncio
    async def test_exception_returns_500(self):
        from routers.evaluations.metadata import get_significance_tests

        db = _mock_db()
        db.query.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            await get_significance_tests(
                request=_mock_request(),
                project_id="p-1",
                model_ids=["a", "b"],
                metrics=["bleu"],
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# compute_project_statistics
# ---------------------------------------------------------------------------


class TestComputeStatisticsDeep:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await compute_project_statistics(
                http_request=_mock_request(),
                project_id="missing",
                request=StatisticsRequest(metrics=["bleu"], aggregation="model"),
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=False)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_access_denied(self, mock_org, mock_access):
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"
        db.query.return_value.filter.return_value.first.return_value = project

        with pytest.raises(HTTPException) as exc:
            await compute_project_statistics(
                http_request=_mock_request(),
                project_id="p-1",
                request=StatisticsRequest(metrics=["bleu"], aggregation="model"),
                db=db,
                current_user=_make_user(is_superadmin=False),
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_no_completed_evaluations(self, mock_org, mock_access):
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc:
            await compute_project_statistics(
                http_request=_mock_request(),
                project_id="p-1",
                request=StatisticsRequest(metrics=["bleu"], aggregation="model"),
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_model_aggregation_with_sample_results(self, mock_org, mock_access):
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.metrics = {"bleu": 0.85}
        eval_run.model_id = "gpt-4"

        sample1 = SimpleNamespace(task_id="t1", field_name="answer", metrics={"bleu": 0.85}, model_id="gpt-4")
        sample2 = SimpleNamespace(task_id="t2", field_name="answer", metrics={"bleu": 0.90}, model_id="gpt-4")
        sample3 = SimpleNamespace(task_id="t3", field_name="answer", metrics={"bleu": 0.80}, model_id="gpt-4")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [eval_run]
            elif call_count["n"] == 3:
                mock_q.all.return_value = [sample1, sample2, sample3]
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id="p-1",
            request=StatisticsRequest(metrics=["bleu"], aggregation="model", methods=["ci"]),
            db=db,
            current_user=_make_user(),
        )
        assert result.aggregation == "model"
        assert "bleu" in result.metrics
        assert "gpt-4" in result.by_model

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_field_aggregation(self, mock_org, mock_access):
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.metrics = {"bleu": 0.85}
        eval_run.model_id = "gpt-4"

        sample1 = SimpleNamespace(task_id="t1", field_name="answer", metrics={"bleu": 0.85}, model_id="gpt-4")
        sample2 = SimpleNamespace(task_id="t2", field_name="answer", metrics={"bleu": 0.90}, model_id="gpt-4")
        sample3 = SimpleNamespace(task_id="t3", field_name="summary", metrics={"bleu": 0.75}, model_id="gpt-4")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [eval_run]
            elif call_count["n"] == 3:
                mock_q.all.return_value = [sample1, sample2, sample3]
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id="p-1",
            request=StatisticsRequest(metrics=["bleu"], aggregation="field", methods=["ci"]),
            db=db,
            current_user=_make_user(),
        )
        assert result.aggregation == "field"
        assert result.by_field is not None
        assert "answer" in result.by_field

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_sample_aggregation(self, mock_org, mock_access):
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.metrics = {"bleu": 0.85}
        eval_run.model_id = "gpt-4"

        sample1 = SimpleNamespace(task_id="t1", field_name=None, metrics={"bleu": 0.85}, model_id="gpt-4")
        sample2 = SimpleNamespace(task_id="t2", field_name=None, metrics={"bleu": 0.90}, model_id="gpt-4")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [eval_run]
            elif call_count["n"] == 3:
                mock_q.all.return_value = [sample1, sample2]
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id="p-1",
            request=StatisticsRequest(metrics=["bleu"], aggregation="sample", methods=["ci"]),
            db=db,
            current_user=_make_user(),
        )
        assert result.aggregation == "sample"
        assert result.raw_scores is not None
        assert len(result.raw_scores) == 2

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_compare_models_filter(self, mock_org, mock_access):
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.metrics = {"bleu": 0.85}
        eval_run.model_id = "gpt-4"

        sample1 = SimpleNamespace(task_id="t1", field_name=None, metrics={"bleu": 0.85}, model_id="gpt-4")
        sample2 = SimpleNamespace(task_id="t2", field_name=None, metrics={"bleu": 0.90}, model_id="claude-3")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [eval_run]
            elif call_count["n"] == 3:
                mock_q.all.return_value = [sample1, sample2]
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id="p-1",
            request=StatisticsRequest(
                metrics=["bleu"],
                aggregation="model",
                methods=["ci"],
                compare_models=["gpt-4", "missing-model"],
            ),
            db=db,
            current_user=_make_user(),
        )
        assert result.warnings is not None

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_pairwise_ttest_and_effect_sizes(self, mock_org, mock_access):
        """Cover: ttest, cohens_d, cliffs_delta, bootstrap pairwise comparisons."""
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.metrics = {"bleu": 0.85}
        eval_run.model_id = "gpt-4"

        samples = []
        for i in range(5):
            samples.append(SimpleNamespace(
                task_id=f"t{i}", field_name=None,
                metrics={"bleu": 0.80 + i * 0.02}, model_id="model-a"
            ))
        for i in range(5):
            samples.append(SimpleNamespace(
                task_id=f"t{i+5}", field_name=None,
                metrics={"bleu": 0.60 + i * 0.02}, model_id="model-b"
            ))

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [eval_run]
            elif call_count["n"] == 3:
                mock_q.all.return_value = samples
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id="p-1",
            request=StatisticsRequest(
                metrics=["bleu"],
                aggregation="model",
                methods=["ttest", "cohens_d", "cliffs_delta"],
            ),
            db=db,
            current_user=_make_user(),
        )
        assert result.pairwise_comparisons is not None
        assert len(result.pairwise_comparisons) >= 1

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_correlation(self, mock_org, mock_access):
        """Cover: correlation method with multiple metrics."""
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.metrics = {"bleu": 0.85, "rouge": 0.80}
        eval_run.model_id = "gpt-4"

        samples = []
        for i in range(5):
            samples.append(SimpleNamespace(
                task_id=f"t{i}", field_name=None,
                metrics={"bleu": 0.80 + i * 0.02, "rouge": 0.75 + i * 0.03},
                model_id="gpt-4",
            ))

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [eval_run]
            elif call_count["n"] == 3:
                mock_q.all.return_value = samples
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id="p-1",
            request=StatisticsRequest(
                metrics=["bleu", "rouge"],
                aggregation="overall",
                methods=["ci", "correlation"],
            ),
            db=db,
            current_user=_make_user(),
        )
        assert result.correlations is not None

    @pytest.mark.asyncio
    @patch("routers.evaluations.metadata.check_project_accessible", return_value=True)
    @patch("routers.evaluations.metadata.get_org_context_from_request", return_value="private")
    async def test_fallback_to_eval_level_metrics(self, mock_org, mock_access):
        """Cover: no sample results -> fallback to evaluation-level metrics."""
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        project = Mock()
        project.id = "p-1"

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.metrics = {"bleu": 0.85}
        eval_run.model_id = "gpt-4"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.join.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = project
            elif call_count["n"] == 2:
                mock_q.all.return_value = [eval_run]
            else:
                # No sample results
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id="p-1",
            request=StatisticsRequest(metrics=["bleu"], aggregation="model", methods=["ci"]),
            db=db,
            current_user=_make_user(),
        )
        assert result.warnings is not None
        assert any("sample-level" in w.lower() or "evaluation-level" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_exception_returns_500(self):
        from routers.evaluations.metadata import compute_project_statistics, StatisticsRequest

        db = _mock_db()
        db.query.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            await compute_project_statistics(
                http_request=_mock_request(),
                project_id="p-1",
                request=StatisticsRequest(metrics=["bleu"], aggregation="model"),
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 500
