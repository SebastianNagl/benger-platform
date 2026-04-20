"""
Unit tests for routers/evaluations/results.py — covers helper functions and endpoint logic.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch, AsyncMock

import pytest
from fastapi import HTTPException

from routers.evaluations.results import (
    _extract_primary_score,
    _get_task_preview,
    _get_task_data_availability,
    _build_all_tasks_response,
)


# ============= _extract_primary_score =============


class TestExtractPrimaryScore:
    """Tests for _extract_primary_score score extraction priority."""

    def test_none_metrics(self):
        assert _extract_primary_score(None) is None

    def test_empty_metrics(self):
        assert _extract_primary_score({}) is None

    def test_custom_llm_judge_first_priority(self):
        metrics = {
            "llm_judge_custom": 0.75,
            "llm_judge_coherence": 0.6,
            "score": 0.9,
        }
        assert _extract_primary_score(metrics) == 0.75

    def test_generic_llm_judge_key(self):
        metrics = {
            "llm_judge_accuracy": 0.95,
            "score": 0.7,
        }
        assert _extract_primary_score(metrics) == 0.95

    def test_generic_llm_judge_skips_response_suffix(self):
        metrics = {
            "llm_judge_accuracy_response": "some text",
            "score": 0.7,
        }
        assert _extract_primary_score(metrics) == 0.7

    def test_generic_llm_judge_skips_passed_suffix(self):
        metrics = {
            "llm_judge_accuracy_passed": True,
            "score": 0.6,
        }
        assert _extract_primary_score(metrics) == 0.6

    def test_generic_llm_judge_skips_details_suffix(self):
        metrics = {
            "llm_judge_accuracy_details": {"info": "data"},
            "score": 0.6,
        }
        assert _extract_primary_score(metrics) == 0.6

    def test_generic_llm_judge_skips_raw_suffix(self):
        metrics = {
            "llm_judge_accuracy_raw": 42,
            "score": 0.6,
        }
        assert _extract_primary_score(metrics) == 0.6

    def test_score_fallback(self):
        metrics = {"score": 0.88}
        assert _extract_primary_score(metrics) == 0.88

    def test_overall_score_fallback(self):
        metrics = {"overall_score": 0.72}
        assert _extract_primary_score(metrics) == 0.72

    def test_score_takes_priority_over_overall_score(self):
        metrics = {"score": 0.5, "overall_score": 0.9}
        assert _extract_primary_score(metrics) == 0.5

    def test_non_numeric_score_ignored(self):
        metrics = {"score": "not_a_number"}
        assert _extract_primary_score(metrics) is None

    def test_float_zero_is_valid(self):
        metrics = {"score": 0.0}
        assert _extract_primary_score(metrics) == 0.0

    def test_integer_score(self):
        metrics = {"llm_judge_custom": 18}
        assert _extract_primary_score(metrics) == 18


# ============= _get_task_preview =============


class TestGetTaskDataAvailability:
    """Tests for _get_task_data_availability DB query helper."""

    def test_empty_task_ids(self):
        db = Mock()
        result = _get_task_data_availability(db, [])
        assert result == (set(), {})

    def test_with_task_ids(self):
        db = Mock()

        # Mock annotation query
        mock_ann_query = MagicMock()
        mock_gen_query = MagicMock()

        def query_side_effect(model):
            if hasattr(model, '__name__') and model.__name__ == 'task_id':
                return mock_ann_query
            return MagicMock()

        # Setup annotation results
        ann_chain = MagicMock()
        ann_chain.filter.return_value = ann_chain
        ann_chain.distinct.return_value = ann_chain
        ann_chain.all.return_value = [("task-1",), ("task-2",)]

        # Setup generation results
        gen_chain = MagicMock()
        gen_chain.filter.return_value = gen_chain
        gen_chain.distinct.return_value = gen_chain
        gen_row1 = Mock(task_id="task-1", model_id="gpt-4")
        gen_row2 = Mock(task_id="task-1", model_id="claude-3")
        gen_row3 = Mock(task_id="task-2", model_id="gpt-4")
        gen_chain.all.return_value = [gen_row1, gen_row2, gen_row3]

        db.query.side_effect = [ann_chain, gen_chain]

        tasks_with_ann, gen_models = _get_task_data_availability(db, ["task-1", "task-2"])

        assert tasks_with_ann == {"task-1", "task-2"}
        assert "task-1" in gen_models
        assert gen_models["task-1"] == {"gpt-4", "claude-3"}
        assert gen_models["task-2"] == {"gpt-4"}


# ============= _build_all_tasks_response =============


class TestBuildAllTasksResponse:
    """Tests for _build_all_tasks_response."""

    @patch("routers.evaluations.results._get_task_data_availability")
    def test_empty_project(self, mock_availability):
        mock_availability.return_value = (set(), {})

        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = []

        result = _build_all_tasks_response(db, "proj-empty")
        assert result == []


# ============= Endpoint tests via direct function calls =============


class TestGetEvaluationResults:
    """Tests for the get_evaluation_results endpoint handler."""

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.results import get_evaluation_results

        db = Mock()
        user = Mock()
        request = Mock()
        request.state.organization_context = "org-1"

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_evaluation_results(
                    project_id="proj-1",
                    request=request,
                    limit=10,
                    include_human=True,
                    include_automated=True,
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_automated_only(self):
        from routers.evaluations.results import get_evaluation_results

        db = Mock()
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        eval_run = Mock(
            metrics={"accuracy": 0.9},
            status="completed",
            samples_evaluated=10,
            eval_metadata={"type": "auto"},
            created_at=datetime(2025, 1, 1),
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [eval_run]
        db.query.return_value = mock_query

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=True
        ):
            result = await get_evaluation_results(
                project_id="proj-1",
                request=request,
                limit=10,
                include_human=False,
                include_automated=True,
                current_user=user,
                db=db,
            )
            assert len(result) == 1
            assert result[0].results["type"] == "automated"

    @pytest.mark.asyncio
    async def test_human_likert_results(self):
        from routers.evaluations.results import get_evaluation_results

        db = Mock()
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        # First query returns empty for automated
        mock_auto_query = MagicMock()
        mock_auto_query.filter.return_value = mock_auto_query
        mock_auto_query.order_by.return_value = mock_auto_query
        mock_auto_query.limit.return_value = mock_auto_query
        mock_auto_query.all.return_value = []

        # Likert results
        likert_row = Mock(dimension="quality", avg_rating=4.5, count=10)
        mock_likert_query = MagicMock()
        mock_likert_query.join.return_value = mock_likert_query
        mock_likert_query.filter.return_value = mock_likert_query
        mock_likert_query.group_by.return_value = mock_likert_query
        mock_likert_query.all.return_value = [likert_row]

        # Preference results
        mock_pref_query = MagicMock()
        mock_pref_query.join.return_value = mock_pref_query
        mock_pref_query.filter.return_value = mock_pref_query
        mock_pref_query.group_by.return_value = mock_pref_query
        mock_pref_query.all.return_value = []

        db.query.side_effect = [mock_auto_query, mock_likert_query, mock_pref_query]

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=True
        ):
            result = await get_evaluation_results(
                project_id="proj-1",
                request=request,
                limit=10,
                include_human=True,
                include_automated=True,
                current_user=user,
                db=db,
            )
            assert len(result) == 1
            assert result[0].results["type"] == "human_likert"
            assert result[0].results["dimensions"]["quality"]["average_rating"] == 4.5

    @pytest.mark.asyncio
    async def test_human_preference_results(self):
        from routers.evaluations.results import get_evaluation_results

        db = Mock()
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        # Empty auto results
        mock_auto = MagicMock()
        mock_auto.filter.return_value = mock_auto
        mock_auto.order_by.return_value = mock_auto
        mock_auto.limit.return_value = mock_auto
        mock_auto.all.return_value = []

        # Empty likert
        mock_likert = MagicMock()
        mock_likert.join.return_value = mock_likert
        mock_likert.filter.return_value = mock_likert
        mock_likert.group_by.return_value = mock_likert
        mock_likert.all.return_value = []

        # Preference results
        pref_a = Mock(winner="model_a", count=30)
        pref_b = Mock(winner="model_b", count=20)
        mock_pref = MagicMock()
        mock_pref.join.return_value = mock_pref
        mock_pref.filter.return_value = mock_pref
        mock_pref.group_by.return_value = mock_pref
        mock_pref.all.return_value = [pref_a, pref_b]

        db.query.side_effect = [mock_auto, mock_likert, mock_pref]

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=True
        ):
            result = await get_evaluation_results(
                project_id="proj-1",
                request=request,
                limit=10,
                include_human=True,
                include_automated=True,
                current_user=user,
                db=db,
            )
            assert len(result) == 1
            assert result[0].results["type"] == "human_preference"
            assert result[0].results["total_comparisons"] == 50
            assert result[0].results["percentages"]["model_a"] == 60.0


class TestGetEvaluationSamples:
    """Tests for get_evaluation_samples endpoint."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self):
        from routers.evaluations.results import get_evaluation_samples

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with pytest.raises(HTTPException) as exc_info:
            await get_evaluation_samples(
                evaluation_id="eval-1",
                request=request,
                field_name=None,
                passed=None,
                page=1,
                page_size=50,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.results import get_evaluation_samples

        db = Mock()
        evaluation = Mock(project_id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = evaluation
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_evaluation_samples(
                    evaluation_id="eval-1",
                    request=request,
                    field_name=None,
                    passed=None,
                    page=1,
                    page_size=50,
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403


class TestGetMetricDistribution:
    """Tests for get_metric_distribution endpoint."""

    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.evaluations.results import get_metric_distribution

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with pytest.raises(HTTPException) as exc_info:
            await get_metric_distribution(
                evaluation_id="eval-1",
                metric_name="accuracy",
                request=request,
                field_name=None,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.results import get_metric_distribution

        db = Mock()
        evaluation = Mock(project_id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = evaluation
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_metric_distribution(
                    evaluation_id="eval-1",
                    metric_name="accuracy",
                    request=request,
                    field_name=None,
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403


class TestGetConfusionMatrix:
    """Tests for get_confusion_matrix endpoint."""

    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.evaluations.results import get_confusion_matrix

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with pytest.raises(HTTPException) as exc_info:
            await get_confusion_matrix(
                evaluation_id="eval-1",
                request=request,
                field_name="answer",
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.results import get_confusion_matrix

        db = Mock()
        evaluation = Mock(project_id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = evaluation
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_confusion_matrix(
                    evaluation_id="eval-1",
                    request=request,
                    field_name="answer",
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403


class TestGetResultsByTaskModel:
    """Tests for get_results_by_task_model endpoint."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self):
        from routers.evaluations.results import get_results_by_task_model

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with pytest.raises(HTTPException) as exc_info:
            await get_results_by_task_model(
                evaluation_id="eval-1",
                request=request,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.results import get_results_by_task_model

        db = Mock()
        evaluation = Mock(project_id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = evaluation
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_results_by_task_model(
                    evaluation_id="eval-1",
                    request=request,
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403


class TestGetSampleResultByTaskModel:
    """Tests for get_sample_result_by_task_model endpoint."""

    @pytest.mark.asyncio
    async def test_task_not_found(self):
        from routers.evaluations.results import get_sample_result_by_task_model

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with pytest.raises(HTTPException) as exc_info:
            await get_sample_result_by_task_model(
                request=request,
                task_id="task-1",
                model_id="gpt-4",
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.results import get_sample_result_by_task_model

        db = Mock()
        task = Mock(project_id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = task
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_sample_result_by_task_model(
                    request=request,
                    task_id="task-1",
                    model_id="gpt-4",
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403


class TestExportEvaluationResults:
    """Tests for export_evaluation_results endpoint."""

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.results import export_evaluation_results

        db = Mock()
        user = Mock()
        request = Mock()
        request.state.organization_context = "org-1"

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await export_evaluation_results(
                    project_id="proj-1",
                    request=request,
                    format="json",
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403


class TestGetProjectResultsByTaskModel:
    """Tests for get_project_results_by_task_model endpoint."""

    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.results import get_project_results_by_task_model

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with pytest.raises(HTTPException) as exc_info:
            await get_project_results_by_task_model(
                project_id="proj-1",
                request=request,
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.results import get_project_results_by_task_model

        db = Mock()
        project = Mock()
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None

        with patch(
            "routers.evaluations.results.check_project_accessible", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_project_results_by_task_model(
                    project_id="proj-1",
                    request=request,
                    current_user=user,
                    db=db,
                )
            assert exc_info.value.status_code == 403

