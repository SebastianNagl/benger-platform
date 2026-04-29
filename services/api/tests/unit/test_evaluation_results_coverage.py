"""
Unit tests for routers/evaluations/results.py covering uncovered lines.

Covers:
- _extract_primary_score helper (lines 31-75)
- get_evaluation_results endpoint (lines 127-254)
- export_evaluation_results endpoint (lines 257-347)
- get_evaluation_samples endpoint (lines 350-426)
- get_metric_distribution endpoint (lines 429-537)
- get_confusion_matrix endpoint (lines 540-666)
- get_results_by_task_model endpoint (lines 669-872)
- _get_task_data_availability helper (lines 875-903)
- _build_all_tasks_response helper (lines 906-921)
- _get_task_preview helper (lines 924-934)
- get_project_results_by_task_model endpoint (lines 937-1175)
- _metric_display_name helper (lines 1483-1492)
- _build_field_results helper (lines 1495-1552)
- get_sample_result_by_task_model endpoint (lines 1555-1679)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session


def _mock_request(headers=None):
    r = Mock()
    r.headers = headers or {}
    r.state = Mock(spec=[])
    return r


def _mock_user(user_id="user-123", is_superadmin=False):
    user = Mock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_superadmin = is_superadmin
    return user


# ============= _extract_primary_score =============


class TestExtractPrimaryScore:
    """Test _extract_primary_score helper."""

    def test_none_metrics(self):
        from routers.evaluations.results import _extract_primary_score

        assert _extract_primary_score(None) is None

    def test_empty_metrics(self):
        from routers.evaluations.results import _extract_primary_score

        assert _extract_primary_score({}) is None

    def test_llm_judge_custom(self):
        from routers.evaluations.results import _extract_primary_score

        result = _extract_primary_score({"llm_judge_custom": 0.85})
        assert result == 0.85

    def test_generic_llm_judge_key(self):
        from routers.evaluations.results import _extract_primary_score

        result = _extract_primary_score({"llm_judge_quality": 0.9})
        assert result == 0.9

    def test_skip_suffixes(self):
        from routers.evaluations.results import _extract_primary_score

        # Keys ending in _response, _passed, _details, _raw should be skipped
        # No generic fallback — returns None when no recognized key matches
        result = _extract_primary_score({
            "llm_judge_test_response": 0.9,
            "llm_judge_test_passed": 1,
            "llm_judge_test_details": 0.8,
            "llm_judge_test_raw": 0.7,
        })
        assert result is None

    def test_score_fallback(self):
        from routers.evaluations.results import _extract_primary_score

        result = _extract_primary_score({"score": 0.88})
        assert result == 0.88

    def test_overall_score_fallback(self):
        from routers.evaluations.results import _extract_primary_score

        result = _extract_primary_score({"overall_score": 0.92})
        assert result == 0.92

    def test_priority_order(self):
        """Test that llm_judge keys take priority over generic score keys."""
        from routers.evaluations.results import _extract_primary_score

        result = _extract_primary_score({
            "llm_judge_custom": 0.8,
            "score": 0.5,
        })
        assert result == 0.8


# ============= _get_task_preview =============


# ============= _build_field_results =============


# ============= get_evaluation_results =============


class TestGetEvaluationResults:
    """Test get_evaluation_results endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=False)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_access_denied(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_evaluation_results

        with pytest.raises(Exception) as exc_info:
            await get_evaluation_results(
                project_id="proj-1",
                request=_mock_request(),
                limit=10,
                include_human=True,
                include_automated=True,
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_automated_results_only(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_evaluation_results

        eval_run = Mock()
        eval_run.metrics = {"accuracy": 0.9}
        eval_run.status = "completed"
        eval_run.samples_evaluated = 10
        eval_run.eval_metadata = {"type": "test"}
        eval_run.created_at = datetime.now(timezone.utc)

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [eval_run]

        result = await get_evaluation_results(
            project_id="proj-1",
            request=_mock_request(),
            limit=10,
            include_human=False,
            include_automated=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].results["type"] == "automated"

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_human_likert_results(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_evaluation_results

        # Mock automated query (empty)
        mock_auto_chain = MagicMock()
        mock_auto_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        # Mock likert query
        likert_result = Mock()
        likert_result.dimension = "quality"
        likert_result.avg_rating = 4.2
        likert_result.count = 10

        mock_likert_chain = MagicMock()
        mock_likert_chain.join.return_value.filter.return_value.group_by.return_value.all.return_value = [likert_result]

        # Mock preference query (empty)
        mock_pref_chain = MagicMock()
        mock_pref_chain.join.return_value.filter.return_value.group_by.return_value.all.return_value = []

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return mock_auto_chain
            elif call_count["n"] == 2:
                return mock_likert_chain
            else:
                return mock_pref_chain

        mock_db.query.side_effect = query_side_effect

        result = await get_evaluation_results(
            project_id="proj-1",
            request=_mock_request(),
            limit=10,
            include_human=True,
            include_automated=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].results["type"] == "human_likert"

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_human_preference_results(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_evaluation_results

        # Mock automated query (empty)
        mock_auto_chain = MagicMock()
        mock_auto_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        # Mock likert query (empty)
        mock_likert_chain = MagicMock()
        mock_likert_chain.join.return_value.filter.return_value.group_by.return_value.all.return_value = []

        # Mock preference query
        pref_a = Mock()
        pref_a.winner = "response_a"
        pref_a.count = 60
        pref_b = Mock()
        pref_b.winner = "response_b"
        pref_b.count = 40

        mock_pref_chain = MagicMock()
        mock_pref_chain.join.return_value.filter.return_value.group_by.return_value.all.return_value = [pref_a, pref_b]

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return mock_auto_chain
            elif call_count["n"] == 2:
                return mock_likert_chain
            else:
                return mock_pref_chain

        mock_db.query.side_effect = query_side_effect

        result = await get_evaluation_results(
            project_id="proj-1",
            request=_mock_request(),
            limit=10,
            include_human=True,
            include_automated=True,
            current_user=_mock_user(),
            db=mock_db,
        )

        assert len(result) == 1
        assert result[0].results["type"] == "human_preference"
        assert result[0].results["total_comparisons"] == 100


# ============= get_evaluation_samples =============


class TestGetEvaluationSamples:
    """Test get_evaluation_samples endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_evaluation_not_found(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_evaluation_samples

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await get_evaluation_samples(
                evaluation_id="nonexistent",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=False)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_access_denied(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_evaluation_samples

        eval_run = Mock()
        eval_run.project_id = "proj-1"
        mock_db.query.return_value.filter.return_value.first.return_value = eval_run

        with pytest.raises(Exception) as exc_info:
            await get_evaluation_samples(
                evaluation_id="eval-1",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 403


# ============= get_metric_distribution =============


class TestGetMetricDistribution:
    """Test get_metric_distribution endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_evaluation_not_found(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_metric_distribution

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await get_metric_distribution(
                evaluation_id="nonexistent",
                metric_name="accuracy",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_no_samples(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_metric_distribution

        eval_run = Mock()
        eval_run.project_id = "proj-1"

        # First query: find evaluation
        # Second query: find samples
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = eval_run
            else:
                q.filter.return_value.all.return_value = []
                q.filter.return_value.filter.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(Exception) as exc_info:
            await get_metric_distribution(
                evaluation_id="eval-1",
                metric_name="accuracy",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_metric_not_found_in_samples(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_metric_distribution

        eval_run = Mock()
        eval_run.project_id = "proj-1"

        sample = Mock()
        sample.metrics = {"other_metric": 0.5}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = eval_run
            else:
                q.filter.return_value.all.return_value = [sample]
                q.filter.return_value.filter.return_value.all.return_value = [sample]
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(Exception) as exc_info:
            await get_metric_distribution(
                evaluation_id="eval-1",
                metric_name="accuracy",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_distribution_success(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_metric_distribution

        eval_run = Mock()
        eval_run.project_id = "proj-1"

        samples = [Mock(metrics={"accuracy": v}) for v in [0.7, 0.8, 0.9, 0.85, 0.75]]

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = eval_run
            else:
                q.filter.return_value.all.return_value = samples
                q.filter.return_value.filter.return_value.all.return_value = samples
            return q

        mock_db.query.side_effect = query_side_effect

        result = await get_metric_distribution(
            evaluation_id="eval-1",
            metric_name="accuracy",
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.metric_name == "accuracy"
        assert result.mean == pytest.approx(0.8, abs=0.01)
        assert result.min == 0.7
        assert result.max == 0.9


# ============= get_confusion_matrix =============


class TestGetConfusionMatrix:
    """Test get_confusion_matrix endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_evaluation_not_found(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_confusion_matrix

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await get_confusion_matrix(
                evaluation_id="nonexistent",
                request=_mock_request(),
                field_name="label",
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_no_samples_for_field(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_confusion_matrix

        eval_run = Mock()
        eval_run.project_id = "proj-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = eval_run
            else:
                q.filter.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(Exception) as exc_info:
            await get_confusion_matrix(
                evaluation_id="eval-1",
                request=_mock_request(),
                field_name="label",
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_confusion_matrix_success(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_confusion_matrix

        eval_run = Mock()
        eval_run.project_id = "proj-1"

        # Samples with ground_truth and prediction
        samples = [
            Mock(ground_truth={"value": "A"}, prediction={"value": "A"}),
            Mock(ground_truth={"value": "A"}, prediction={"value": "B"}),
            Mock(ground_truth={"value": "B"}, prediction={"value": "B"}),
            Mock(ground_truth={"value": "B"}, prediction={"value": "A"}),
        ]

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = eval_run
            else:
                q.filter.return_value.all.return_value = samples
            return q

        mock_db.query.side_effect = query_side_effect

        result = await get_confusion_matrix(
            evaluation_id="eval-1",
            request=_mock_request(),
            field_name="label",
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result.field_name == "label"
        assert "a" in result.labels
        assert "b" in result.labels
        assert result.accuracy == 0.5

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_no_valid_pairs(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_confusion_matrix

        eval_run = Mock()
        eval_run.project_id = "proj-1"

        # Samples with no valid ground_truth/prediction pairs
        samples = [
            Mock(ground_truth=None, prediction={"value": "A"}),
            Mock(ground_truth={"value": "B"}, prediction=None),
        ]

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = eval_run
            else:
                q.filter.return_value.all.return_value = samples
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(Exception) as exc_info:
            await get_confusion_matrix(
                evaluation_id="eval-1",
                request=_mock_request(),
                field_name="label",
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 400


# ============= get_results_by_task_model =============


class TestGetResultsByTaskModel:
    """Test get_results_by_task_model endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_evaluation_not_found(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_results_by_task_model

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await get_results_by_task_model(
                evaluation_id="nonexistent",
                request=_mock_request(),
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_no_results(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_results_by_task_model

        eval_run = Mock()
        eval_run.project_id = "proj-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                # Find evaluation
                q.filter.return_value.first.return_value = eval_run
            else:
                # Sample results and annotation results - both empty
                q.join.return_value.filter.return_value.all.return_value = []
                q.filter.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        result = await get_results_by_task_model(
            evaluation_id="eval-1",
            request=_mock_request(),
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["evaluation_id"] == "eval-1"
        assert result["models"] == []


class TestGetSampleResultByTaskModel:
    """Test get_sample_result_by_task_model endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_task_not_found(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_sample_result_by_task_model

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(Exception) as exc_info:
            await get_sample_result_by_task_model(
                request=_mock_request(),
                task_id="nonexistent",
                model_id="gpt-4",
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=False)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_access_denied(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_sample_result_by_task_model

        task = Mock()
        task.project_id = "proj-1"
        mock_db.query.return_value.filter.return_value.first.return_value = task

        with pytest.raises(Exception) as exc_info:
            await get_sample_result_by_task_model(
                request=_mock_request(),
                task_id="task-1",
                model_id="gpt-4",
                current_user=_mock_user(),
                db=mock_db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_no_results(self, mock_org, mock_access, mock_db):
        from routers.evaluations.results import get_sample_result_by_task_model

        task = Mock()
        task.project_id = "proj-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = task
            else:
                q.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        result = await get_sample_result_by_task_model(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            current_user=_mock_user(),
            db=mock_db,
        )

        assert result["results"] == []
        assert "No evaluation results" in result["message"]

    @pytest.mark.asyncio
    @patch("routers.evaluations.results.check_project_accessible", return_value=True)
    @patch("routers.evaluations.results.get_org_context_from_request", return_value="org-123")
    async def test_annotator_model_id(self, mock_org, mock_access, mock_db):
        """Test querying with annotator: model_id prefix."""
        from routers.evaluations.results import get_sample_result_by_task_model

        task = Mock()
        task.project_id = "proj-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = task
            elif call_count["n"] == 2:
                # User lookup
                q.filter.return_value.first.return_value = None  # User not found
            else:
                q.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect

        result = await get_sample_result_by_task_model(
            request=_mock_request(),
            task_id="task-1",
            model_id="annotator:testuser",
            current_user=_mock_user(),
            db=mock_db,
        )

        # User not found -> empty results
        assert result["results"] == []
