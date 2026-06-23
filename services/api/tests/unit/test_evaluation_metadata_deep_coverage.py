"""
Unit tests for routers/evaluations/metadata/* to increase branch coverage.
Direct handler invocation (no TestClient) so pytest-cov tracks coverage.

Covers: get_evaluated_models, get_configured_methods, get_evaluation_history,
get_significance_tests, compute_project_statistics (all aggregation types,
compare_models, correlation, bootstrap, Cohen's d, Cliff's delta, fallback).

The metadata handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``), so the old
``MagicMock(spec=Session)`` + ``db.query.side_effect`` pattern is inert. These
tests now seed real rows via the SAVEPOINT-isolated ``async_test_db``
AsyncSession and call the handlers directly with that session. Access is
exercised either by seeding a superadmin user (``check_project_accessible_async``
short-circuits True) or by patching ``check_project_accessible_async`` on the
submodule where each handler lives.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from auth_module.models import User as AuthUser
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
)
from models import User as DBUser
from project_models import Project, Task


def _uid() -> str:
    return str(uuid.uuid4())


def _mock_request(headers=None):
    mock = Mock()
    mock.headers = headers or {"X-Organization-Context": "private"}
    mock.state = Mock(spec=[])
    return mock


async def _make_user(db, *, is_superadmin=True):
    """Seed a real User row and return it."""
    u = DBUser(
        id=_uid(),
        username=f"meta-deep-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Meta Deep User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


def _auth_user(db_user: DBUser) -> AuthUser:
    """Build the Pydantic AuthUser the handlers receive as ``current_user``.

    ``check_project_accessible_async`` reads ``user.is_superadmin`` and
    ``user.id`` (querying memberships by id when not superadmin), so the
    AuthUser.id must equal the seeded DB user's id.
    """
    return AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )


async def _make_project(db, owner, *, evaluation_config=None, generation_config=None):
    proj = Project(
        id=_uid(),
        title=f"Meta Deep {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config=evaluation_config,
        generation_config=generation_config,
    )
    db.add(proj)
    await db.flush()
    return proj


async def _seed_eval_graph(
    db,
    owner,
    project,
    *,
    model_scores,
    metric="bleu",
    field_name="answer",
    eval_metrics=None,
):
    """Seed a full evaluation data graph for ``project``.

    ``model_scores`` maps ``model_id -> [score, score, ...]``. For each model
    we create a ResponseGeneration + one Generation/TaskEvaluation per score,
    all hanging off a shared EvaluationRun + EvaluationJudgeRun. Every
    TaskEvaluation carries ``metrics={metric: score}`` so the handlers'
    ``await db.execute(select(...))`` queries return real per-sample data.
    """
    now = datetime.now(timezone.utc)
    for model_id, scores in model_scores.items():
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            model_id=model_id,
            status="completed",
            created_by=owner.id,
            started_at=now,
            completed_at=now,
        )
        db.add(rg)
        await db.flush()

        er = EvaluationRun(
            id=_uid(),
            project_id=project.id,
            model_id=model_id,
            evaluation_type_ids=[metric],
            metrics=(eval_metrics if eval_metrics is not None else {metric: 0.7}),
            status="completed",
            samples_evaluated=len(scores),
            has_sample_results=True,
            created_by=owner.id,
            created_at=now,
            completed_at=now,
        )
        db.add(er)
        await db.flush()

        jr = EvaluationJudgeRun(
            id=_uid(),
            evaluation_id=er.id,
            judge_model_id=None,
            run_index=0,
            status="completed",
        )
        db.add(jr)
        await db.flush()

        for i, score in enumerate(scores):
            task = Task(
                id=_uid(),
                project_id=project.id,
                data={"text": f"Task {model_id}-{i}"},
                inner_id=i + 1,
                created_by=owner.id,
            )
            db.add(task)
            await db.flush()

            gen = Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=task.id,
                model_id=model_id,
                run_index=i,
                case_data=json.dumps(task.data),
                response_content=f"r-{i}",
                label_config_version="v1",
                status="completed",
                parse_status="success",
            )
            db.add(gen)
            await db.flush()

            te = TaskEvaluation(
                id=_uid(),
                evaluation_id=er.id,
                judge_run_id=jr.id,
                task_id=task.id,
                generation_id=gen.id,
                field_name=field_name,
                evaluation_config_id=None,
                answer_type="text",
                ground_truth={"value": "ref"},
                prediction={"value": f"hyp-{i}"},
                metrics={metric: score},
                passed=True,
                created_at=now,
            )
            db.add(te)
    await db.commit()


# ---------------------------------------------------------------------------
# get_evaluated_models
# ---------------------------------------------------------------------------


class TestEvaluatedModelsDeep:
    @pytest.mark.asyncio
    async def test_include_configured_with_models_and_scores(self, async_test_db):
        from routers.evaluations.metadata import get_evaluated_models

        user = await _make_user(async_test_db)
        proj = await _make_project(
            async_test_db,
            user,
            generation_config={
                "selected_configuration": {"models": ["gpt-4", "claude-3"]}
            },
        )
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"gpt-4": [0.85, 0.80], "claude-3": [0.90]},
        )

        result = await get_evaluated_models(
            request=_mock_request(),
            project_id=proj.id,
            include_configured=True,
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert isinstance(result, list)
        model_ids = {r["model_id"] for r in result}
        assert "gpt-4" in model_ids
        assert "claude-3" in model_ids

    @pytest.mark.asyncio
    async def test_no_models_returns_empty_list(self, async_test_db):
        from routers.evaluations.metadata import get_evaluated_models

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, generation_config=None)
        await async_test_db.commit()

        result = await get_evaluated_models(
            request=_mock_request(),
            project_id=proj.id,
            include_configured=False,
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.metadata import get_evaluated_models

        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await get_evaluated_models(
                request=_mock_request(),
                project_id="missing",
                include_configured=False,
                db=async_test_db,
                current_user=_auth_user(user),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.metadata import get_evaluated_models

        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc:
                await get_evaluated_models(
                    request=_mock_request(),
                    project_id=proj.id,
                    include_configured=False,
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_exception_returns_500(self, async_test_db):
        from routers.evaluations.metadata import get_evaluated_models

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        # The project lookup succeeds, then the access check raises an
        # unexpected error which the handler wraps into a 500.
        with patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            side_effect=RuntimeError("DB connection lost"),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_evaluated_models(
                    request=_mock_request(),
                    project_id=proj.id,
                    include_configured=False,
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_without_include_configured_sorts_by_score_desc(self, async_test_db):
        from routers.evaluations.metadata import get_evaluated_models

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, generation_config=None)
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"gpt-4": [0.85], "claude-3": [0.50]},
        )

        result = await get_evaluated_models(
            request=_mock_request(),
            project_id=proj.id,
            include_configured=False,
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert isinstance(result, list)
        assert len(result) == 2
        # Sorted by average score descending.
        scores = [r["average_score"] for r in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# get_configured_methods
# ---------------------------------------------------------------------------


class TestConfiguredMethodsDeep:
    @pytest.mark.asyncio
    async def test_no_evaluation_config(self, async_test_db):
        from routers.evaluations.metadata import get_configured_methods

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user, evaluation_config=None)
        await async_test_db.commit()

        result = await get_configured_methods(
            request=_mock_request(),
            project_id=proj.id,
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result["fields"] == []

    @pytest.mark.asyncio
    async def test_no_selected_methods(self, async_test_db):
        from routers.evaluations.metadata import get_configured_methods

        user = await _make_user(async_test_db)
        proj = await _make_project(
            async_test_db,
            user,
            evaluation_config={"available_methods": {"field1": {}}, "selected_methods": {}},
        )
        await async_test_db.commit()

        result = await get_configured_methods(
            request=_mock_request(),
            project_id=proj.id,
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result["fields"] == []

    @pytest.mark.asyncio
    async def test_with_automated_and_human_methods(self, async_test_db):
        from routers.evaluations.metadata import get_configured_methods

        user = await _make_user(async_test_db)
        proj = await _make_project(
            async_test_db,
            user,
            evaluation_config={
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
            },
        )
        # Seed real TaskEvaluation rows whose metrics carry BOTH bleu and
        # llm_judge_quality keys so the jsonb_object_keys aggregation marks
        # has_results=True for the llm_judge_quality method.
        now = datetime.now(timezone.utc)
        rg = ResponseGeneration(
            id=_uid(), project_id=proj.id, model_id="gpt-4", status="completed",
            created_by=user.id, started_at=now, completed_at=now,
        )
        async_test_db.add(rg)
        await async_test_db.flush()
        er = EvaluationRun(
            id=_uid(), project_id=proj.id, model_id="gpt-4",
            evaluation_type_ids=["bleu", "llm_judge_quality"],
            metrics={"bleu": 0.6}, status="completed", samples_evaluated=3,
            has_sample_results=True, created_by=user.id,
            created_at=now, completed_at=now,
        )
        async_test_db.add(er)
        await async_test_db.flush()
        jr = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id="gpt-4", run_index=0,
            status="completed",
        )
        async_test_db.add(jr)
        await async_test_db.flush()
        for i in range(3):
            task = Task(
                id=_uid(), project_id=proj.id, data={"text": f"T{i}"},
                inner_id=i + 1, created_by=user.id,
            )
            async_test_db.add(task)
            await async_test_db.flush()
            gen = Generation(
                id=_uid(), generation_id=rg.id, task_id=task.id, model_id="gpt-4",
                run_index=i, case_data=json.dumps(task.data), response_content=f"r-{i}",
                label_config_version="v1", status="completed", parse_status="success",
            )
            async_test_db.add(gen)
            await async_test_db.flush()
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id, judge_run_id=jr.id, task_id=task.id,
                generation_id=gen.id, field_name="answer_field", evaluation_config_id=None,
                answer_type="text", ground_truth={"value": "ref"},
                prediction={"value": f"hyp-{i}"},
                metrics={"bleu": 0.5, "llm_judge_quality": 0.7},
                passed=True, created_at=now,
            )
            async_test_db.add(te)
        await async_test_db.commit()

        result = await get_configured_methods(
            request=_mock_request(),
            project_id=proj.id,
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert len(result["fields"]) == 1
        field = result["fields"][0]
        assert field["field_name"] == "answer"
        assert len(field["automated_methods"]) == 2
        assert len(field["human_methods"]) == 1
        llm_method = [
            m for m in field["automated_methods"] if m["method_name"] == "llm_judge_quality"
        ]
        assert len(llm_method) == 1
        assert llm_method[0]["method_type"] == "llm-judge"
        assert llm_method[0]["has_results"] == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.metadata import get_configured_methods

        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await get_configured_methods(
                request=_mock_request(),
                project_id="missing",
                db=async_test_db,
                current_user=_auth_user(user),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.metadata import get_configured_methods

        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user, evaluation_config={})
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc:
                await get_configured_methods(
                    request=_mock_request(),
                    project_id=proj.id,
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_exception_returns_500(self, async_test_db):
        from routers.evaluations.metadata import get_configured_methods

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_configured_methods(
                    request=_mock_request(),
                    project_id=proj.id,
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# get_evaluation_history
# ---------------------------------------------------------------------------


class TestEvaluationHistoryDeep:
    # Issue #111: /evaluation-history was rewritten to aggregate TaskEvaluation
    # rows by (date, model, config_id, metric) and return {series: [...]}.
    # Data-path coverage moved to fixture-based tests in
    # test_evaluation_metadata_endpoints.py::TestEvaluationHistoryPerConfig
    # — the old DBEvaluationRun.metrics mocks no longer exercise the new code.
    # Auth/error-handling tests stay here because they don't touch the data path.

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.metadata import get_evaluation_history

        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await get_evaluation_history(
                request=_mock_request(),
                project_id="missing",
                model_ids=["gpt-4"],
                metrics=["bleu"],
                evaluation_config_ids=None,
                start_date=None,
                end_date=None,
                db=async_test_db,
                current_user=_auth_user(user),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.metadata import get_evaluation_history

        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc:
                await get_evaluation_history(
                    request=_mock_request(),
                    project_id=proj.id,
                    model_ids=["gpt-4"],
                    metrics=["bleu"],
                    evaluation_config_ids=None,
                    start_date=None,
                    end_date=None,
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_exception_returns_500(self, async_test_db):
        from routers.evaluations.metadata import get_evaluation_history

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.history.check_project_accessible_async",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_evaluation_history(
                    request=_mock_request(),
                    project_id=proj.id,
                    model_ids=["gpt-4"],
                    metrics=["bleu"],
                    evaluation_config_ids=None,
                    start_date=None,
                    end_date=None,
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# get_significance_tests
# ---------------------------------------------------------------------------


class TestSignificanceTestsDeep:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.metadata import get_significance_tests

        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await get_significance_tests(
                request=_mock_request(),
                project_id="missing",
                model_ids=["a", "b"],
                metrics=["bleu"],
                db=async_test_db,
                current_user=_auth_user(user),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.metadata import get_significance_tests

        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.significance.check_project_accessible_async",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc:
                await get_significance_tests(
                    request=_mock_request(),
                    project_id=proj.id,
                    model_ids=["a", "b"],
                    metrics=["bleu"],
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_stats_not_available(self, async_test_db):
        from routers.evaluations.metadata import get_significance_tests

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch("routers.leaderboards.STATS_AVAILABLE", False):
            result = await get_significance_tests(
                request=_mock_request(),
                project_id=proj.id,
                model_ids=["a", "b"],
                metrics=["bleu"],
                db=async_test_db,
                current_user=_auth_user(user),
            )
        assert result["comparisons"] == []
        assert "not available" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_with_scores_and_direct_evaluations(self, async_test_db):
        from routers.evaluations.metadata import get_significance_tests

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        # model-a: two sample scores; model-b: two sample scores. Both pass
        # the >=2 threshold so a real Welch comparison runs.
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"model-a": [0.85, 0.90], "model-b": [0.70, 0.72]},
            eval_metrics={"bleu": 0.75},
        )

        result = await get_significance_tests(
            request=_mock_request(),
            project_id=proj.id,
            model_ids=["model-a", "model-b"],
            metrics=["bleu"],
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert "comparisons" in result
        assert len(result["comparisons"]) >= 1

    @pytest.mark.asyncio
    async def test_insufficient_scores_returns_default(self, async_test_db):
        from routers.evaluations.metadata import get_significance_tests

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        # One sample per model and no extra run-level metrics → fewer than 2
        # scores each → handler emits the default (p_value=1.0) comparison.
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"model-a": [0.85], "model-b": [0.70]},
            eval_metrics={},
        )

        result = await get_significance_tests(
            request=_mock_request(),
            project_id=proj.id,
            model_ids=["model-a", "model-b"],
            metrics=["bleu"],
            db=async_test_db,
            current_user=_auth_user(user),
        )
        comps = result["comparisons"]
        assert len(comps) == 1
        assert comps[0]["p_value"] == 1.0
        assert comps[0]["significant"] == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_exception_returns_500(self, async_test_db):
        from routers.evaluations.metadata import get_significance_tests

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.significance.check_project_accessible_async",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_significance_tests(
                    request=_mock_request(),
                    project_id=proj.id,
                    model_ids=["a", "b"],
                    metrics=["bleu"],
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# compute_project_statistics
# ---------------------------------------------------------------------------


class TestComputeStatisticsDeep:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await compute_project_statistics(
                http_request=_mock_request(),
                project_id="missing",
                request=StatisticsRequest(metrics=["bleu"], aggregation="model"),
                db=async_test_db,
                current_user=_auth_user(user),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db, is_superadmin=False)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.statistics.check_project_accessible_async",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc:
                await compute_project_statistics(
                    http_request=_mock_request(),
                    project_id=proj.id,
                    request=StatisticsRequest(metrics=["bleu"], aggregation="model"),
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_completed_evaluations(self, async_test_db):
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with pytest.raises(HTTPException) as exc:
            await compute_project_statistics(
                http_request=_mock_request(),
                project_id=proj.id,
                request=StatisticsRequest(metrics=["bleu"], aggregation="model"),
                db=async_test_db,
                current_user=_auth_user(user),
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_model_aggregation_with_sample_results(self, async_test_db):
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"gpt-4": [0.85, 0.90, 0.80]},
        )

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id=proj.id,
            request=StatisticsRequest(metrics=["bleu"], aggregation="model", methods=["ci"]),
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result.aggregation == "model"
        assert "bleu" in result.metrics
        assert "gpt-4" in result.by_model

    @pytest.mark.asyncio
    async def test_field_aggregation(self, async_test_db):
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"gpt-4": [0.85, 0.90]},
            field_name="answer",
        )
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"gpt-4": [0.75]},
            field_name="summary",
        )

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id=proj.id,
            request=StatisticsRequest(metrics=["bleu"], aggregation="field", methods=["ci"]),
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result.aggregation == "field"
        assert result.by_field is not None
        assert "answer" in result.by_field

    @pytest.mark.asyncio
    async def test_sample_aggregation(self, async_test_db):
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"gpt-4": [0.85, 0.90]},
            field_name="default",
        )

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id=proj.id,
            request=StatisticsRequest(metrics=["bleu"], aggregation="sample", methods=["ci"]),
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result.aggregation == "sample"
        assert result.raw_scores is not None
        assert len(result.raw_scores) == 2

    @pytest.mark.asyncio
    async def test_compare_models_filter(self, async_test_db):
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={"gpt-4": [0.85], "claude-3": [0.90]},
            field_name="default",
        )

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id=proj.id,
            request=StatisticsRequest(
                metrics=["bleu"],
                aggregation="model",
                methods=["ci"],
                compare_models=["gpt-4", "missing-model"],
            ),
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result.warnings is not None

    @pytest.mark.asyncio
    async def test_pairwise_ttest_and_effect_sizes(self, async_test_db):
        """Cover: ttest, cohens_d, cliffs_delta, bootstrap pairwise comparisons."""
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await _seed_eval_graph(
            async_test_db,
            user,
            proj,
            model_scores={
                "model-a": [0.80, 0.82, 0.84, 0.86, 0.88],
                "model-b": [0.60, 0.62, 0.64, 0.66, 0.68],
            },
            field_name="default",
        )

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id=proj.id,
            request=StatisticsRequest(
                metrics=["bleu"],
                aggregation="model",
                methods=["ttest", "cohens_d", "cliffs_delta"],
            ),
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result.pairwise_comparisons is not None
        assert len(result.pairwise_comparisons) >= 1

    @pytest.mark.asyncio
    async def test_correlation(self, async_test_db):
        """Cover: correlation method with multiple metrics."""
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        # Seed rows carrying BOTH bleu and rouge per TaskEvaluation so the
        # correlation matrix has >=3 paired samples per metric.
        now = datetime.now(timezone.utc)
        rg = ResponseGeneration(
            id=_uid(), project_id=proj.id, model_id="gpt-4", status="completed",
            created_by=user.id, started_at=now, completed_at=now,
        )
        async_test_db.add(rg)
        await async_test_db.flush()
        er = EvaluationRun(
            id=_uid(), project_id=proj.id, model_id="gpt-4",
            evaluation_type_ids=["bleu", "rouge"],
            metrics={"bleu": 0.85, "rouge": 0.80}, status="completed",
            samples_evaluated=5, has_sample_results=True, created_by=user.id,
            created_at=now, completed_at=now,
        )
        async_test_db.add(er)
        await async_test_db.flush()
        jr = EvaluationJudgeRun(
            id=_uid(), evaluation_id=er.id, judge_model_id=None, run_index=0,
            status="completed",
        )
        async_test_db.add(jr)
        await async_test_db.flush()
        for i in range(5):
            task = Task(
                id=_uid(), project_id=proj.id, data={"text": f"T{i}"},
                inner_id=i + 1, created_by=user.id,
            )
            async_test_db.add(task)
            await async_test_db.flush()
            gen = Generation(
                id=_uid(), generation_id=rg.id, task_id=task.id, model_id="gpt-4",
                run_index=i, case_data=json.dumps(task.data), response_content=f"r-{i}",
                label_config_version="v1", status="completed", parse_status="success",
            )
            async_test_db.add(gen)
            await async_test_db.flush()
            te = TaskEvaluation(
                id=_uid(), evaluation_id=er.id, judge_run_id=jr.id, task_id=task.id,
                generation_id=gen.id, field_name="default", evaluation_config_id=None,
                answer_type="text", ground_truth={"value": "ref"},
                prediction={"value": f"hyp-{i}"},
                metrics={"bleu": 0.80 + i * 0.02, "rouge": 0.75 + i * 0.03},
                passed=True, created_at=now,
            )
            async_test_db.add(te)
        await async_test_db.commit()

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id=proj.id,
            request=StatisticsRequest(
                metrics=["bleu", "rouge"],
                aggregation="overall",
                methods=["ci", "correlation"],
            ),
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result.correlations is not None

    @pytest.mark.asyncio
    async def test_fallback_to_eval_level_metrics(self, async_test_db):
        """Cover: no sample results -> fallback to evaluation-level metrics."""
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        # A completed EvaluationRun with run-level metrics but NO
        # TaskEvaluation sample rows → handler falls back to eval-level metrics
        # and warns about it.
        now = datetime.now(timezone.utc)
        er = EvaluationRun(
            id=_uid(), project_id=proj.id, model_id="gpt-4",
            evaluation_type_ids=["bleu"], metrics={"bleu": 0.85},
            status="completed", samples_evaluated=0, has_sample_results=False,
            created_by=user.id, created_at=now, completed_at=now,
        )
        async_test_db.add(er)
        await async_test_db.commit()

        result = await compute_project_statistics(
            http_request=_mock_request(),
            project_id=proj.id,
            request=StatisticsRequest(metrics=["bleu"], aggregation="model", methods=["ci"]),
            db=async_test_db,
            current_user=_auth_user(user),
        )
        assert result.warnings is not None
        assert any(
            "sample-level" in w.lower() or "evaluation-level" in w.lower()
            for w in result.warnings
        )

    @pytest.mark.asyncio
    async def test_exception_returns_500(self, async_test_db):
        from routers.evaluations.metadata import StatisticsRequest, compute_project_statistics

        user = await _make_user(async_test_db)
        proj = await _make_project(async_test_db, user)
        await async_test_db.commit()

        with patch(
            "routers.evaluations.metadata.statistics.check_project_accessible_async",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc:
                await compute_project_statistics(
                    http_request=_mock_request(),
                    project_id=proj.id,
                    request=StatisticsRequest(metrics=["bleu"], aggregation="model"),
                    db=async_test_db,
                    current_user=_auth_user(user),
                )
        assert exc.value.status_code == 500
