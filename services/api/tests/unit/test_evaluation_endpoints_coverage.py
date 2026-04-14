"""
Unit tests for routers/evaluations/ — status.py, validation.py, metadata.py, config.py.
Covers endpoint logic with mocked DB.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException


# ============= evaluation/status.py =============


class TestGetEvaluationStatus:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.evaluations.status import get_evaluation_status
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_evaluation_status(evaluation_id="eval-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.status import get_evaluation_status
        db = Mock()
        evaluation = Mock(project_id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = evaluation
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.status.check_project_accessible", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await get_evaluation_status(evaluation_id="eval-1", request=request, current_user=user, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_success(self):
        from routers.evaluations.status import get_evaluation_status
        db = Mock()
        evaluation = Mock(id="eval-1", project_id="proj-1", status="completed", error_message=None)
        db.query.return_value.filter.return_value.first.return_value = evaluation
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.status.check_project_accessible", return_value=True):
            result = await get_evaluation_status(evaluation_id="eval-1", request=request, current_user=user, db=db)
            assert result.id == "eval-1"
            assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_with_error_message(self):
        from routers.evaluations.status import get_evaluation_status
        db = Mock()
        evaluation = Mock(id="eval-1", project_id="proj-1", status="failed", error_message="Metric computation failed")
        db.query.return_value.filter.return_value.first.return_value = evaluation
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.status.check_project_accessible", return_value=True):
            result = await get_evaluation_status(evaluation_id="eval-1", request=request, current_user=user, db=db)
            assert result.message == "Metric computation failed"


class TestStreamEvaluationStatus:
    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.status import stream_evaluation_status
        db = Mock()
        evaluation = Mock(project_id="proj-1")
        db.query.return_value.filter.return_value.first.return_value = evaluation
        user = Mock(id="user-1")
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.status.check_project_accessible", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await stream_evaluation_status(evaluation_id="eval-1", request=request, current_user=user, db=db)
            assert exc_info.value.status_code == 403


# ============= evaluation/validation.py =============


class TestValidateEvaluationConfig:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.validation import validate_evaluation_config
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await validate_evaluation_config(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.validation import validate_evaluation_config
        db = Mock()
        project = Mock()
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.validation.check_project_accessible", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await validate_evaluation_config(project_id="proj-1", request=request, current_user=user, db=db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_matching_fields(self):
        from routers.evaluations.validation import validate_evaluation_config
        db = Mock()
        project = Mock(
            generation_config={"prompt_structures": [{"output_fields": ["answer", "reasoning"]}]},
            evaluation_config={"detected_answer_types": [{"name": "answer"}, {"name": "reasoning"}]},
        )
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.validation.check_project_accessible", return_value=True):
            result = await validate_evaluation_config(project_id="proj-1", request=request, current_user=user, db=db)
            assert result.valid is True

    @pytest.mark.asyncio
    async def test_missing_fields(self):
        from routers.evaluations.validation import validate_evaluation_config
        db = Mock()
        project = Mock(
            generation_config={"prompt_structures": [{"output_fields": ["answer"]}]},
            evaluation_config={"detected_answer_types": [{"name": "reasoning"}]},
        )
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.validation.check_project_accessible", return_value=True):
            result = await validate_evaluation_config(project_id="proj-1", request=request, current_user=user, db=db)
            assert result.valid is False

    @pytest.mark.asyncio
    async def test_no_configs(self):
        from routers.evaluations.validation import validate_evaluation_config
        db = Mock()
        project = Mock(generation_config=None, evaluation_config=None)
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.validation.check_project_accessible", return_value=True):
            result = await validate_evaluation_config(project_id="proj-1", request=request, current_user=user, db=db)
            assert result.valid is False


# ============= evaluation/metadata.py =============


class TestGetEvaluatedModels:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.metadata import get_evaluated_models
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_evaluated_models(request=request, project_id="proj-1", include_configured=False, db=db, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self):
        from routers.evaluations.metadata import get_evaluated_models
        db = Mock()
        project = Mock()
        db.query.return_value.filter.return_value.first.return_value = project
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await get_evaluated_models(request=request, project_id="proj-1", include_configured=False, db=db, current_user=user)
            assert exc_info.value.status_code == 403


# ============= evaluation/config.py =============


class TestGetProjectEvaluationConfig:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.config import get_project_evaluation_config
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_project_evaluation_config(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestDetectAnswerTypes:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.config import detect_answer_types
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await detect_answer_types(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestGetFieldTypesForLlmJudge:
    @pytest.mark.asyncio
    async def test_project_not_found(self):
        from routers.evaluations.config import get_field_types_for_llm_judge
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_field_types_for_llm_judge(project_id="proj-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404
