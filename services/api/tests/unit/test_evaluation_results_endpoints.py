"""
Unit tests for routers/evaluations/results.py — covers helper functions and endpoint logic.

The results router package was migrated to the async DB lane: every handler now
takes ``db: AsyncSession = Depends(get_async_db)`` and does
``await db.execute(select(...))`` instead of ``db.query(...).filter(...)``, and
calls the async access helper ``check_project_accessible_async``. So the
handler-level tests seed real rows into the SAVEPOINT-isolated ``async_test_db``
fixture and patch the async access helper (an ``AsyncMock``) to drive the
accessibility branch — ``db.query`` Mocks no longer model the ``await
db.execute(...)`` surface the handlers use.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from routers.evaluations.results import (
    _extract_primary_score,
    _get_task_data_availability,
    _build_all_tasks_response,
)


# ============= seeding helpers =============


def _uid() -> str:
    return str(uuid.uuid4())


def _make_request(org_context="org-1"):
    request = Mock()
    request.state.organization_context = org_context
    return request


def _mock_user(is_superadmin=False):
    user = Mock()
    user.is_superadmin = is_superadmin
    return user


async def _seed_user(db, is_superadmin=False):
    from models import User

    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="U",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(db, creator):
    from project_models import Project

    p = Project(
        id=_uid(),
        title="P",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_task(db, project, *, inner_id=1, creator=None):
    from project_models import Task

    creator_id = creator.id if creator else project.created_by
    t = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": f"task text {inner_id}", "input": f"q {inner_id}"},
        created_by=creator_id,
        updated_by=creator_id,
    )
    db.add(t)
    await db.flush()
    return t


async def _seed_generation(db, project, task, *, model_id="gpt-4o"):
    """Create a ResponseGeneration parent + Generation child for a task."""
    from models import Generation, ResponseGeneration

    rg = ResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task.id,
        model_id=model_id,
        status="completed",
        created_by=project.created_by,
    )
    db.add(rg)
    await db.flush()
    gen = Generation(
        id=_uid(),
        generation_id=rg.id,
        task_id=task.id,
        model_id=model_id,
        run_index=0,
        case_data=json.dumps(task.data),
        response_content=f"gen for {task.id}",
        status="completed",
    )
    db.add(gen)
    await db.flush()
    return gen


async def _seed_annotation(db, project, task, completer):
    from project_models import Annotation

    ann = Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        result=[{"from_name": "text", "type": "textarea", "value": {"text": ["a"]}}],
        completed_by=completer.id,
        was_cancelled=False,
    )
    db.add(ann)
    await db.flush()
    return ann


async def _seed_eval_run(db, project, *, metrics=None, status="completed"):
    from models import EvaluationRun

    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["exact_match"],
        metrics=metrics if metrics is not None else {"accuracy": 0.9},
        eval_metadata={"type": "auto"},
        status=status,
        samples_evaluated=10,
        has_sample_results=True,
        created_by=project.created_by,
    )
    db.add(er)
    await db.flush()
    return er


async def _seed_human_session(db, project, evaluator, *, session_type="likert"):
    from models import HumanEvaluationSession

    sess = HumanEvaluationSession(
        id=_uid(),
        project_id=project.id,
        evaluator_id=evaluator.id,
        session_type=session_type,
        items_evaluated=1,
        status="completed",
    )
    db.add(sess)
    await db.flush()
    return sess


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


# ============= _get_task_data_availability =============


class TestGetTaskDataAvailability:
    """Tests for _get_task_data_availability DB query helper (async)."""

    @pytest.mark.asyncio
    async def test_empty_task_ids(self, async_test_db):
        # Coroutine short-circuits on the empty list before touching the DB,
        # but it's still a coroutine so it must be awaited.
        result = await _get_task_data_availability(async_test_db, [])
        assert result == (set(), {}, {})

    @pytest.mark.asyncio
    async def test_with_task_ids(self, async_test_db):
        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        t1 = await _seed_task(async_test_db, project, inner_id=1)
        t2 = await _seed_task(async_test_db, project, inner_id=2)

        # Two distinct generation models on task-1, one on task-2.
        await _seed_generation(async_test_db, project, t1, model_id="gpt-4")
        await _seed_generation(async_test_db, project, t1, model_id="claude-3")
        await _seed_generation(async_test_db, project, t2, model_id="gpt-4")

        # An annotation on each task -> both have annotations.
        await _seed_annotation(async_test_db, project, t1, creator)
        await _seed_annotation(async_test_db, project, t2, creator)

        await async_test_db.commit()

        tasks_with_ann, gen_models, _ann_displays = await _get_task_data_availability(
            async_test_db, [t1.id, t2.id]
        )

        assert tasks_with_ann == {t1.id, t2.id}
        assert gen_models[t1.id] == {"gpt-4", "claude-3"}
        assert gen_models[t2.id] == {"gpt-4"}


# ============= _build_all_tasks_response =============


class TestBuildAllTasksResponse:
    """Tests for _build_all_tasks_response."""

    @pytest.mark.asyncio
    async def test_empty_project(self, async_test_db):
        # A project with no tasks -> empty preview rows -> empty response.
        # _get_task_data_availability short-circuits on the empty task list.
        result = await _build_all_tasks_response(async_test_db, "proj-empty")
        assert result == []


# ============= Endpoint tests via direct function calls =============


class TestGetEvaluationResults:
    """Tests for the get_evaluation_results endpoint handler."""

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_evaluation_results

        user = _mock_user()
        request = _make_request("org-1")

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_evaluation_results(
                    project_id="proj-1",
                    request=request,
                    limit=10,
                    include_human=True,
                    include_automated=True,
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_automated_only(self, async_test_db):
        from routers.evaluations.results import get_evaluation_results

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        await _seed_eval_run(async_test_db, project, metrics={"accuracy": 0.9})
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_evaluation_results(
                project_id=project.id,
                request=request,
                limit=10,
                include_human=False,
                include_automated=True,
                current_user=user,
                db=async_test_db,
            )
            assert len(result) == 1
            assert result[0].results["type"] == "automated"

    @pytest.mark.asyncio
    async def test_human_likert_results(self, async_test_db):
        from models import LikertScaleEvaluation
        from routers.evaluations.results import get_evaluation_results

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        task = await _seed_task(async_test_db, project)
        # Seed no EvaluationRun -> automated section is empty.
        session = await _seed_human_session(
            async_test_db, project, creator, session_type="likert"
        )
        # Two likert rows for the same dimension -> avg 4.5.
        for rating in (4, 5):
            async_test_db.add(
                LikertScaleEvaluation(
                    id=_uid(),
                    session_id=session.id,
                    task_id=task.id,
                    response_id=_uid(),
                    dimension="quality",
                    rating=rating,
                )
            )
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_evaluation_results(
                project_id=project.id,
                request=request,
                limit=10,
                include_human=True,
                include_automated=True,
                current_user=user,
                db=async_test_db,
            )
            assert len(result) == 1
            assert result[0].results["type"] == "human_likert"
            assert (
                result[0].results["dimensions"]["quality"]["average_rating"] == 4.5
            )

    @pytest.mark.asyncio
    async def test_human_preference_results(self, async_test_db):
        from models import PreferenceRanking
        from routers.evaluations.results import get_evaluation_results

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        task = await _seed_task(async_test_db, project)
        # No EvaluationRun and no likert -> only the preference section is set.
        session = await _seed_human_session(
            async_test_db, project, creator, session_type="preference"
        )
        # 30 wins for model_a, 20 for model_b -> 60% / 40%, total 50.
        for _ in range(30):
            async_test_db.add(
                PreferenceRanking(
                    id=_uid(),
                    session_id=session.id,
                    task_id=task.id,
                    response_a_id=_uid(),
                    response_b_id=_uid(),
                    winner="model_a",
                )
            )
        for _ in range(20):
            async_test_db.add(
                PreferenceRanking(
                    id=_uid(),
                    session_id=session.id,
                    task_id=task.id,
                    response_a_id=_uid(),
                    response_b_id=_uid(),
                    winner="model_b",
                )
            )
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_evaluation_results(
                project_id=project.id,
                request=request,
                limit=10,
                include_human=True,
                include_automated=True,
                current_user=user,
                db=async_test_db,
            )
            assert len(result) == 1
            assert result[0].results["type"] == "human_preference"
            assert result[0].results["total_comparisons"] == 50
            assert result[0].results["percentages"]["model_a"] == 60.0


class TestGetEvaluationSamples:
    """Tests for get_evaluation_samples endpoint."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_db):
        from routers.evaluations.results import get_evaluation_samples

        user = _mock_user()
        request = _make_request(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_evaluation_samples(
                evaluation_id=_uid(),
                request=request,
                field_name=None,
                passed=None,
                page=1,
                page_size=50,
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_evaluation_samples

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project)
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_evaluation_samples(
                    evaluation_id=eval_run.id,
                    request=request,
                    field_name=None,
                    passed=None,
                    page=1,
                    page_size=50,
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403


class TestGetMetricDistribution:
    """Tests for get_metric_distribution endpoint."""

    @pytest.mark.asyncio
    async def test_not_found(self, async_test_db):
        from routers.evaluations.results import get_metric_distribution

        user = _mock_user()
        request = _make_request(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_metric_distribution(
                evaluation_id=_uid(),
                metric_name="accuracy",
                request=request,
                field_name=None,
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_metric_distribution

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project)
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_metric_distribution(
                    evaluation_id=eval_run.id,
                    metric_name="accuracy",
                    request=request,
                    field_name=None,
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403


class TestGetConfusionMatrix:
    """Tests for get_confusion_matrix endpoint."""

    @pytest.mark.asyncio
    async def test_not_found(self, async_test_db):
        from routers.evaluations.results import get_confusion_matrix

        user = _mock_user()
        request = _make_request(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_confusion_matrix(
                evaluation_id=_uid(),
                request=request,
                field_name="answer",
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_confusion_matrix

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project)
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_confusion_matrix(
                    evaluation_id=eval_run.id,
                    request=request,
                    field_name="answer",
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403


class TestGetResultsByTaskModel:
    """Tests for get_results_by_task_model endpoint."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_db):
        from routers.evaluations.results import get_results_by_task_model

        user = _mock_user()
        request = _make_request(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_results_by_task_model(
                evaluation_id=_uid(),
                request=request,
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_results_by_task_model

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project)
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_results_by_task_model(
                    evaluation_id=eval_run.id,
                    request=request,
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403


class TestGetSampleResultByTaskModel:
    """Tests for get_sample_result_by_task_model endpoint."""

    @pytest.mark.asyncio
    async def test_task_not_found(self, async_test_db):
        from routers.evaluations.results import get_sample_result_by_task_model

        user = _mock_user()
        request = _make_request(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_sample_result_by_task_model(
                request=request,
                task_id=_uid(),
                model_id="gpt-4",
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_sample_result_by_task_model

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        task = await _seed_task(async_test_db, project)
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_sample_result_by_task_model(
                    request=request,
                    task_id=task.id,
                    model_id="gpt-4",
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403


class TestExportEvaluationResults:
    """Tests for export_evaluation_results endpoint."""

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import export_evaluation_results

        user = _mock_user()
        request = _make_request("org-1")

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await export_evaluation_results(
                    project_id="proj-1",
                    request=request,
                    format="json",
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403


class TestGetProjectResultsByTaskModel:
    """Tests for get_project_results_by_task_model endpoint."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.results import get_project_results_by_task_model

        user = _mock_user()
        request = _make_request(None)

        with pytest.raises(HTTPException) as exc_info:
            await get_project_results_by_task_model(
                project_id=_uid(),
                request=request,
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_project_results_by_task_model

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        await async_test_db.commit()

        user = _mock_user()
        request = _make_request(None)

        with patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_project_results_by_task_model(
                    project_id=project.id,
                    request=request,
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403
