"""
Unit tests for routers/generation.py — covers endpoint access control and logic.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException


class TestGetGenerationStatus:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.generation import get_generation_status
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        request = Mock()
        request.state.organization_context = None
        with pytest.raises(HTTPException) as exc_info:
            await get_generation_status(generation_id="gen-1", request=request, current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestStopGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.generation import stop_generation
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await stop_generation(generation_id="gen-1", current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestPauseGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.generation import pause_generation
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await pause_generation(generation_id="gen-1", current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestResumeGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.generation import resume_generation
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await resume_generation(generation_id="gen-1", current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestRetryGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.generation import retry_generation
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await retry_generation(generation_id="gen-1", current_user=user, db=db)
        assert exc_info.value.status_code == 404


class TestDeleteGeneration:
    @pytest.mark.asyncio
    async def test_not_found(self):
        from routers.generation import delete_generation
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = Mock()
        with pytest.raises(HTTPException) as exc_info:
            await delete_generation(generation_id="gen-1", current_user=user, db=db)
        assert exc_info.value.status_code == 404
