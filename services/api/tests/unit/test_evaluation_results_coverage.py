"""
Unit tests for routers/evaluations/results.py covering uncovered lines.

Covers:
- _extract_primary_score helper (pure)
- get_evaluation_results endpoint (core.py)
- get_evaluation_samples endpoint (core.py)
- get_metric_distribution endpoint (distributions.py)
- get_confusion_matrix endpoint (distributions.py)
- get_results_by_task_model endpoint (by_task_model.py)
- get_sample_result_by_task_model endpoint (by_task_model.py)

The results package was migrated sync->async: every handler takes
``db: AsyncSession = Depends(get_async_db)`` and does
``await db.execute(select(...))`` then ``.scalar_one_or_none()`` /
``.scalars().all()``, and awaits ``check_project_accessible_async(...)``.
A ``MagicMock(spec=Session)`` no longer models the ``await db.execute(...)``
surface, so the handler-level tests below call the coroutine handlers with a
real ``async_test_db`` AsyncSession (seeding the rows they need) and patch the
async access helper with an AsyncMock to drive the accessibility branch.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Project, Task


def _uid() -> str:
    return str(uuid.uuid4())


def _make_request(org_context="org-123"):
    """A plain request whose state carries the org context.

    ``get_org_context_from_request`` is a sync helper that reads
    ``request.state.organization_context`` — we don't patch it, we just feed
    it a real-looking request.
    """
    r = Mock()
    r.headers = {}
    r.state.organization_context = org_context
    return r


def _mock_user(user_id="user-123", is_superadmin=False):
    user = Mock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_superadmin = is_superadmin
    return user


# ---------------------------------------------------------------------------
# Async seed helpers
# ---------------------------------------------------------------------------


async def _seed_user(db, *, username=None):
    u = User(
        id=_uid(),
        username=username or f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Results Unit User",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(db, creator):
    p = Project(
        id=_uid(),
        title=f"Results Unit {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_task(db, project, *, inner_id=1):
    t = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": f"Eval task {inner_id}", "content": f"Content {inner_id}"},
        created_by=project.created_by,
    )
    db.add(t)
    await db.flush()
    return t


async def _seed_eval_run(db, project, creator, *, status="completed", metrics=None):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4",
        evaluation_type_ids=["accuracy", "f1"],
        status=status,
        metrics=metrics or {"accuracy": 0.9, "f1": 0.82},
        samples_evaluated=10,
        eval_metadata={"type": "test"},
        created_by=creator.id,
    )
    db.add(er)
    await db.flush()
    # Migration 043 made TaskEvaluation.judge_run_id NOT NULL. Rows that
    # insert TaskEvaluations need a parent judge run; use the catch-all
    # shape (judge_model_id=NULL, run_index=0) that orphan backfill uses.
    judge_run = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(judge_run)
    await db.flush()
    er._test_judge_run = judge_run
    return er


async def _seed_generation(db, task, *, model_id="gpt-4"):
    """A minimal, FK-valid generation (ResponseGeneration parent + Generation child)."""
    rg = ResponseGeneration(
        id=_uid(),
        project_id=task.project_id,
        task_id=task.id,
        model_id=model_id,
        status="completed",
        created_by=task.created_by,
    )
    db.add(rg)
    await db.flush()
    gen = Generation(
        id=_uid(),
        generation_id=rg.id,
        task_id=task.id,
        model_id=model_id,
        run_index=0,
        case_data="{}",
        response_content="x",
        status="completed",
        parse_status="success",
    )
    db.add(gen)
    await db.flush()
    return gen


async def _seed_task_evaluation(
    db,
    eval_run,
    task,
    *,
    metrics=None,
    generation=None,
    annotation=None,
    field_name="answer",
    answer_type="choices",
    ground_truth=None,
    prediction=None,
    passed=True,
):
    # uq_task_evaluations_cell keys a row on its scored subject
    # (generation_id / annotation_id / created_by), not its task_id. Synthesize
    # a distinct generation when no subject is supplied so sibling rows in the
    # same run+field don't collapse to one cell and collide.
    if generation is None and annotation is None:
        generation = await _seed_generation(db, task)
    te = TaskEvaluation(
        id=_uid(),
        evaluation_id=eval_run.id,
        judge_run_id=eval_run._test_judge_run.id,
        task_id=task.id,
        generation_id=generation.id if generation else None,
        annotation_id=annotation.id if annotation else None,
        field_name=field_name,
        answer_type=answer_type,
        metrics=metrics if metrics is not None else {"score": 0.9},
        passed=passed,
        ground_truth=ground_truth if ground_truth is not None else {"value": "Ja"},
        prediction=prediction if prediction is not None else {"value": "Ja"},
    )
    db.add(te)
    await db.flush()
    return te


async def _seed_human_session(db, project, evaluator, *, session_type="likert"):
    s = HumanEvaluationSession(
        id=_uid(),
        project_id=project.id,
        evaluator_id=evaluator.id,
        session_type=session_type,
        status="completed",
    )
    db.add(s)
    await db.flush()
    return s


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


# ============= get_evaluation_results =============


class TestGetEvaluationResults:
    """Test get_evaluation_results endpoint."""

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_evaluation_results

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(Exception) as exc_info:
                await get_evaluation_results(
                    project_id="proj-1",
                    request=_make_request(),
                    limit=10,
                    include_human=True,
                    include_automated=True,
                    current_user=_mock_user(),
                    db=async_test_db,
                )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_automated_results_only(self, async_test_db):
        from routers.evaluations.results import get_evaluation_results

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        await _seed_eval_run(
            async_test_db, project, creator, metrics={"accuracy": 0.9}
        )
        await async_test_db.commit()

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_evaluation_results(
                project_id=project.id,
                request=_make_request(),
                limit=10,
                include_human=False,
                include_automated=True,
                current_user=_mock_user(),
                db=async_test_db,
            )

        assert len(result) == 1
        assert result[0].results["type"] == "automated"

    @pytest.mark.asyncio
    async def test_human_likert_results(self, async_test_db):
        from routers.evaluations.results import get_evaluation_results

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        task = await _seed_task(async_test_db, project)
        session = await _seed_human_session(
            async_test_db, project, creator, session_type="likert"
        )
        # A few likert ratings on the "quality" dimension -> aggregated row.
        for rating in (4, 5, 4, 4):
            async_test_db.add(
                LikertScaleEvaluation(
                    id=_uid(),
                    session_id=session.id,
                    task_id=task.id,
                    response_id="resp-1",
                    dimension="quality",
                    rating=rating,
                )
            )
        await async_test_db.commit()

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_evaluation_results(
                project_id=project.id,
                request=_make_request(),
                limit=10,
                include_human=True,
                include_automated=False,
                current_user=_mock_user(),
                db=async_test_db,
            )

        assert len(result) == 1
        assert result[0].results["type"] == "human_likert"

    @pytest.mark.asyncio
    async def test_human_preference_results(self, async_test_db):
        from routers.evaluations.results import get_evaluation_results

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        task = await _seed_task(async_test_db, project)
        session = await _seed_human_session(
            async_test_db, project, creator, session_type="preference"
        )
        # 60 "a" winners + 40 "b" winners -> total_comparisons == 100.
        for _ in range(60):
            async_test_db.add(
                PreferenceRanking(
                    id=_uid(),
                    session_id=session.id,
                    task_id=task.id,
                    response_a_id="a",
                    response_b_id="b",
                    winner="a",
                )
            )
        for _ in range(40):
            async_test_db.add(
                PreferenceRanking(
                    id=_uid(),
                    session_id=session.id,
                    task_id=task.id,
                    response_a_id="a",
                    response_b_id="b",
                    winner="b",
                )
            )
        await async_test_db.commit()

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_evaluation_results(
                project_id=project.id,
                request=_make_request(),
                limit=10,
                include_human=True,
                include_automated=False,
                current_user=_mock_user(),
                db=async_test_db,
            )

        assert len(result) == 1
        assert result[0].results["type"] == "human_preference"
        assert result[0].results["total_comparisons"] == 100


# ============= get_evaluation_samples =============


class TestGetEvaluationSamples:
    """Test get_evaluation_samples endpoint."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_db):
        from routers.evaluations.results import get_evaluation_samples

        # No eval run seeded -> scalar_one_or_none() is None -> 404.
        with pytest.raises(Exception) as exc_info:
            await get_evaluation_samples(
                evaluation_id="nonexistent",
                request=_make_request(),
                current_user=_mock_user(),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.results import get_evaluation_samples

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project, creator)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.results.core.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(Exception) as exc_info:
                await get_evaluation_samples(
                    evaluation_id=eval_run.id,
                    request=_make_request(),
                    current_user=_mock_user(),
                    db=async_test_db,
                )
        assert exc_info.value.status_code == 403


# ============= get_metric_distribution =============


class TestGetMetricDistribution:
    """Test get_metric_distribution endpoint."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_db):
        from routers.evaluations.results import get_metric_distribution

        with pytest.raises(Exception) as exc_info:
            await get_metric_distribution(
                evaluation_id="nonexistent",
                metric_name="accuracy",
                request=_make_request(),
                current_user=_mock_user(),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_samples(self, async_test_db):
        from routers.evaluations.results import get_metric_distribution

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project, creator)
        await async_test_db.commit()

        # Eval run exists but no TaskEvaluation rows -> 404 "No samples".
        with patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            with pytest.raises(Exception) as exc_info:
                await get_metric_distribution(
                    evaluation_id=eval_run.id,
                    metric_name="accuracy",
                    request=_make_request(),
                    field_name=None,
                    current_user=_mock_user(),
                    db=async_test_db,
                )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_metric_not_found_in_samples(self, async_test_db):
        from routers.evaluations.results import get_metric_distribution

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        task = await _seed_task(async_test_db, project)
        eval_run = await _seed_eval_run(async_test_db, project, creator)
        # Sample carries a different metric key, so "accuracy" is absent.
        await _seed_task_evaluation(
            async_test_db, eval_run, task, metrics={"other_metric": 0.5}
        )
        await async_test_db.commit()

        with patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            with pytest.raises(Exception) as exc_info:
                await get_metric_distribution(
                    evaluation_id=eval_run.id,
                    metric_name="accuracy",
                    request=_make_request(),
                    field_name=None,
                    current_user=_mock_user(),
                    db=async_test_db,
                )
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_distribution_success(self, async_test_db):
        from routers.evaluations.results import get_metric_distribution

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project, creator)
        # >=5 rows each with metrics={"accuracy": v}; each gets a distinct
        # generation via the seed helper so the cell-uniqueness constraint holds.
        for i, v in enumerate([0.7, 0.8, 0.9, 0.85, 0.75]):
            task = await _seed_task(async_test_db, project, inner_id=i + 1)
            await _seed_task_evaluation(
                async_test_db, eval_run, task, metrics={"accuracy": v}
            )
        await async_test_db.commit()

        with patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_metric_distribution(
                evaluation_id=eval_run.id,
                metric_name="accuracy",
                request=_make_request(),
                field_name=None,
                current_user=_mock_user(),
                db=async_test_db,
            )

        assert result.metric_name == "accuracy"
        assert result.mean == pytest.approx(0.8, abs=0.01)
        assert result.min == 0.7
        assert result.max == 0.9


# ============= get_confusion_matrix =============


class TestGetConfusionMatrix:
    """Test get_confusion_matrix endpoint."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_db):
        from routers.evaluations.results import get_confusion_matrix

        with pytest.raises(Exception) as exc_info:
            await get_confusion_matrix(
                evaluation_id="nonexistent",
                request=_make_request(),
                field_name="label",
                current_user=_mock_user(),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_samples_for_field(self, async_test_db):
        from routers.evaluations.results import get_confusion_matrix

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project, creator)
        await async_test_db.commit()

        # No TaskEvaluation rows for field "label" -> 404.
        with patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            with pytest.raises(Exception) as exc_info:
                await get_confusion_matrix(
                    evaluation_id=eval_run.id,
                    request=_make_request(),
                    field_name="label",
                    current_user=_mock_user(),
                    db=async_test_db,
                )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_confusion_matrix_success(self, async_test_db):
        from routers.evaluations.results import get_confusion_matrix

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project, creator)
        # 4 rows: (A,A) (A,B) (B,B) (B,A) -> 2 correct / 4 -> accuracy 0.5.
        pairs = [
            ({"value": "A"}, {"value": "A"}),
            ({"value": "A"}, {"value": "B"}),
            ({"value": "B"}, {"value": "B"}),
            ({"value": "B"}, {"value": "A"}),
        ]
        for i, (gt, pred) in enumerate(pairs):
            task = await _seed_task(async_test_db, project, inner_id=i + 1)
            await _seed_task_evaluation(
                async_test_db,
                eval_run,
                task,
                field_name="label",
                ground_truth=gt,
                prediction=pred,
            )
        await async_test_db.commit()

        with patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_confusion_matrix(
                evaluation_id=eval_run.id,
                request=_make_request(),
                field_name="label",
                current_user=_mock_user(),
                db=async_test_db,
            )

        assert result.field_name == "label"
        assert "a" in result.labels
        assert "b" in result.labels
        assert result.accuracy == 0.5

    @pytest.mark.asyncio
    async def test_no_valid_pairs(self, async_test_db):
        from routers.evaluations.results import get_confusion_matrix

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project, creator)
        # Rows present for the field, but each is missing a gt or a pred.
        # ground_truth/prediction are NOT NULL columns, so model the "missing"
        # side as an empty dict — falsy, so the handler's
        # ``gt = sample.ground_truth.get("value") if sample.ground_truth else None``
        # resolves to None and the (gt, pred) pair is dropped -> no valid
        # pairs -> 400.
        rows = [
            ({}, {"value": "A"}),
            ({"value": "B"}, {}),
        ]
        for i, (gt, pred) in enumerate(rows):
            task = await _seed_task(async_test_db, project, inner_id=i + 1)
            await _seed_task_evaluation(
                async_test_db,
                eval_run,
                task,
                field_name="label",
                ground_truth=gt,
                prediction=pred,
            )
        await async_test_db.commit()

        with patch(
            "routers.evaluations.results.distributions.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            with pytest.raises(Exception) as exc_info:
                await get_confusion_matrix(
                    evaluation_id=eval_run.id,
                    request=_make_request(),
                    field_name="label",
                    current_user=_mock_user(),
                    db=async_test_db,
                )
        assert exc_info.value.status_code == 400


# ============= get_results_by_task_model =============


class TestGetResultsByTaskModel:
    """Test get_results_by_task_model endpoint."""

    @pytest.mark.asyncio
    async def test_evaluation_not_found(self, async_test_db):
        from routers.evaluations.results import get_results_by_task_model

        with pytest.raises(Exception) as exc_info:
            await get_results_by_task_model(
                evaluation_id="nonexistent",
                request=_make_request(),
                current_user=_mock_user(),
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_results(self, async_test_db):
        from routers.evaluations.results import get_results_by_task_model

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        eval_run = await _seed_eval_run(async_test_db, project, creator)
        await async_test_db.commit()

        # Eval run exists but no TaskEvaluations -> empty-shape response.
        with patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_results_by_task_model(
                evaluation_id=eval_run.id,
                request=_make_request(),
                current_user=_mock_user(),
                db=async_test_db,
            )

        assert result["evaluation_id"] == eval_run.id
        assert result["models"] == []


class TestGetSampleResultByTaskModel:
    """Test get_sample_result_by_task_model endpoint."""

    @pytest.mark.asyncio
    async def test_task_not_found(self, async_test_db):
        from routers.evaluations.results import get_sample_result_by_task_model

        with pytest.raises(Exception) as exc_info:
            await get_sample_result_by_task_model(
                request=_make_request(),
                task_id="nonexistent",
                model_id="gpt-4",
                current_user=_mock_user(),
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

        with patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(Exception) as exc_info:
                await get_sample_result_by_task_model(
                    request=_make_request(),
                    task_id=task.id,
                    model_id="gpt-4",
                    current_user=_mock_user(),
                    db=async_test_db,
                )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_results(self, async_test_db):
        from routers.evaluations.results import get_sample_result_by_task_model

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        task = await _seed_task(async_test_db, project)
        await async_test_db.commit()

        # Task exists + access granted, but no TaskEvaluations for this
        # task/model -> empty results with the "no results" message.
        with patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_sample_result_by_task_model(
                request=_make_request(),
                task_id=task.id,
                model_id="gpt-4",
                include_history=True,
                generation_id=None,
                current_user=_mock_user(),
                db=async_test_db,
            )

        assert result["results"] == []
        assert "No evaluation results" in result["message"]

    @pytest.mark.asyncio
    async def test_annotator_model_id(self, async_test_db):
        """Test querying with annotator: model_id prefix for an unknown user."""
        from routers.evaluations.results import get_sample_result_by_task_model

        creator = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, creator)
        task = await _seed_task(async_test_db, project)
        await async_test_db.commit()

        # No user matches the "annotator:nobody" display name -> empty results.
        with patch(
            "routers.evaluations.results.by_task_model.check_project_accessible_async",
            new=AsyncMock(return_value=True),
        ):
            result = await get_sample_result_by_task_model(
                request=_make_request(),
                task_id=task.id,
                model_id="annotator:nobody",
                current_user=_mock_user(),
                db=async_test_db,
            )

        # User not found -> empty results
        assert result["results"] == []
