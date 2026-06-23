"""
Unit tests for routers/evaluations/ — status.py, validation.py, metadata.py, config.py.

These call the coroutine handlers directly. After the async-DB migration the
handlers read via ``await db.execute(select(...))``, so a plain ``Mock()`` db
fails on ``await``. The handler-level tests now pass a real ``async_test_db``
AsyncSession (seeding the rows they need) and patch the async access helper
(``check_project_accessible_async`` / ``auth_service.check_project_access_async``)
to drive the 403 branch. ``stream_evaluation_status`` is still sync internally
(opens its own ``next(get_db())``), so that test keeps the Mock lane.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from models import EvaluationRun, User
from project_models import Project


def _uid() -> str:
    return str(uuid.uuid4())


def _make_request():
    request = Mock()
    request.state.organization_context = None
    return request


async def _seed_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"evcov-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Eval Cov User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(db, owner, **kwargs):
    p = Project(
        id=_uid(),
        title=f"Eval Cov {uuid.uuid4().hex[:6]}",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        **kwargs,
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_eval_run(db, owner, project, *, status="completed", error_message=None):
    run = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id="gpt-4o",
        evaluation_type_ids=["test"],
        metrics={"acc": 0.9},
        status=status,
        error_message=error_message,
        samples_evaluated=10,
        created_by=owner.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    return run


# ============= evaluation/status.py =============


class TestGetEvaluationStatus:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_db):
        from routers.evaluations.status import get_evaluation_status

        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_evaluation_status(
                evaluation_id="eval-1",
                request=_make_request(),
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.status import get_evaluation_status

        owner = await _seed_user(async_test_db)
        user = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, owner)
        run = await _seed_eval_run(async_test_db, owner, project)
        await async_test_db.commit()
        with patch(
            "routers.evaluations.status.check_project_accessible_async",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_evaluation_status(
                    evaluation_id=run.id,
                    request=_make_request(),
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_success(self, async_test_db):
        from routers.evaluations.status import get_evaluation_status

        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        run = await _seed_eval_run(async_test_db, owner, project, status="completed")
        await async_test_db.commit()
        # Superadmin owner short-circuits the access check.
        result = await get_evaluation_status(
            evaluation_id=run.id,
            request=_make_request(),
            current_user=owner,
            db=async_test_db,
        )
        assert result.id == run.id
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_with_error_message(self, async_test_db):
        from routers.evaluations.status import get_evaluation_status

        owner = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, owner)
        run = await _seed_eval_run(
            async_test_db, owner, project, status="failed",
            error_message="Metric computation failed",
        )
        await async_test_db.commit()
        result = await get_evaluation_status(
            evaluation_id=run.id,
            request=_make_request(),
            current_user=owner,
            db=async_test_db,
        )
        assert result.message == "Metric computation failed"


class TestStreamEvaluationStatus:
    @pytest.mark.asyncio
    async def test_access_denied(self):
        """stream_evaluation_status dropped its `db: Session` parameter in
        commit 7c61a79 (prod-stability WS-session-leak fix) — the handler
        now opens its own per-iteration session inside the generator,
        rather than holding the request-scoped session for the lifetime
        of the SSE stream. It remains synchronous internally, so this test
        keeps the Mock(spec=Session) lane.
        """
        from routers.evaluations.status import stream_evaluation_status
        user = Mock(id="user-1")
        request = Mock()
        request.state.organization_context = None
        evaluation = Mock(project_id="proj-1")
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = evaluation
        with patch("routers.evaluations.status.get_db", return_value=iter([mock_db])), \
             patch("routers.evaluations.status.check_project_accessible", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await stream_evaluation_status(evaluation_id="eval-1", request=request, current_user=user)
            assert exc_info.value.status_code == 403


# ============= evaluation/validation.py =============


class TestValidateEvaluationConfig:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.validation import validate_evaluation_config

        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await validate_evaluation_config(
                project_id="proj-1",
                request=_make_request(),
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.validation import validate_evaluation_config

        owner = await _seed_user(async_test_db)
        user = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, owner)
        await async_test_db.commit()
        with patch(
            "routers.evaluations.validation.check_project_accessible_async",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await validate_evaluation_config(
                    project_id=project.id,
                    request=_make_request(),
                    current_user=user,
                    db=async_test_db,
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_matching_fields(self, async_test_db):
        from routers.evaluations.validation import validate_evaluation_config

        owner = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            owner,
            generation_config={"prompt_structures": [{"output_fields": ["answer", "reasoning"]}]},
            evaluation_config={"detected_answer_types": [{"name": "answer"}, {"name": "reasoning"}]},
        )
        await async_test_db.commit()
        result = await validate_evaluation_config(
            project_id=project.id,
            request=_make_request(),
            current_user=owner,
            db=async_test_db,
        )
        assert result.valid == True  # noqa: E712

    @pytest.mark.asyncio
    async def test_missing_fields(self, async_test_db):
        from routers.evaluations.validation import validate_evaluation_config

        owner = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            owner,
            generation_config={"prompt_structures": [{"output_fields": ["answer"]}]},
            evaluation_config={"detected_answer_types": [{"name": "reasoning"}]},
        )
        await async_test_db.commit()
        result = await validate_evaluation_config(
            project_id=project.id,
            request=_make_request(),
            current_user=owner,
            db=async_test_db,
        )
        assert result.valid == False  # noqa: E712

    @pytest.mark.asyncio
    async def test_no_configs(self, async_test_db):
        from routers.evaluations.validation import validate_evaluation_config

        owner = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db, owner, generation_config=None, evaluation_config=None
        )
        await async_test_db.commit()
        result = await validate_evaluation_config(
            project_id=project.id,
            request=_make_request(),
            current_user=owner,
            db=async_test_db,
        )
        assert result.valid == False  # noqa: E712


# ============= evaluation/metadata.py =============


class TestGetEvaluatedModels:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.metadata import get_evaluated_models

        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_evaluated_models(
                request=_make_request(),
                project_id="proj-1",
                include_configured=False,
                db=async_test_db,
                current_user=user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_db):
        from routers.evaluations.metadata import get_evaluated_models

        owner = await _seed_user(async_test_db)
        user = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, owner)
        await async_test_db.commit()
        with patch(
            "routers.evaluations.metadata.models_methods.check_project_accessible_async",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_evaluated_models(
                    request=_make_request(),
                    project_id=project.id,
                    include_configured=False,
                    db=async_test_db,
                    current_user=user,
                )
            assert exc_info.value.status_code == 403


# ============= evaluation/config.py =============


class TestGetProjectEvaluationConfig:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.config import get_project_evaluation_config

        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_project_evaluation_config(
                project_id="proj-1",
                request=_make_request(),
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404


class TestDetectAnswerTypes:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.config import detect_answer_types

        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await detect_answer_types(
                project_id="proj-1",
                request=_make_request(),
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404


class TestGetFieldTypesForLlmJudge:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_db):
        from routers.evaluations.config import get_field_types_for_llm_judge

        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with pytest.raises(HTTPException) as exc_info:
            await get_field_types_for_llm_judge(
                project_id="proj-1",
                request=_make_request(),
                current_user=user,
                db=async_test_db,
            )
        assert exc_info.value.status_code == 404
