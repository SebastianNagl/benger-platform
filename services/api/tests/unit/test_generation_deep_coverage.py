"""
Unit tests for routers/generation.py to increase branch coverage.
Direct handler invocation (no TestClient) so pytest-cov tracks coverage.

Covers: get_generation_status, stop_generation, pause_generation,
resume_generation, retry_generation, delete_generation, get_parse_metrics.
"""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth_module.models import User


def _make_user(is_superadmin=False, user_id="user-123"):
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
    return MagicMock(spec=Session)


def _make_generation(gen_id="gen-1", status_val="running", created_by="user-123"):
    gen = Mock()
    gen.id = gen_id
    gen.status = status_val
    gen.created_by = created_by
    gen.celery_task_id = "celery-task-1"
    gen.project_id = "proj-1"
    gen.model_id = "gpt-4"
    gen.task_id = "task-1"
    gen.error_message = None
    gen.completed_at = None
    gen.current_progress = 50
    gen.completed_tasks = 5
    gen.retry_count = 0
    gen.paused_at = None
    gen.resumed_at = None
    return gen


# ---------------------------------------------------------------------------
# get_generation_status
# ---------------------------------------------------------------------------


class TestGetGenerationStatus:
    @pytest.mark.asyncio
    @patch("routers.generation.check_project_accessible", return_value=True)
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_generation_found(self, mock_org, mock_access):
        from routers.generation import get_generation_status

        db = _mock_db()
        gen = _make_generation(status_val="completed")
        gen.error_message = "Done"

        task = Mock()
        task.project_id = "proj-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = task
            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_status(
            generation_id="gen-1",
            request=_mock_request(),
            current_user=_make_user(),
            db=db,
        )
        assert result.status == "completed"
        assert result.id == "gen-1"

    @pytest.mark.asyncio
    async def test_generation_not_found(self):
        from routers.generation import get_generation_status

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_generation_status(
                generation_id="missing",
                request=_mock_request(),
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.generation.check_project_accessible", return_value=False)
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_generation_access_denied(self, mock_org, mock_access):
        from routers.generation import get_generation_status

        db = _mock_db()
        gen = _make_generation()
        task = Mock()
        task.project_id = "proj-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = task
            return mock_q

        db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc:
            await get_generation_status(
                generation_id="gen-1",
                request=_mock_request(),
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# stop_generation
# ---------------------------------------------------------------------------


class TestStopGeneration:
    @pytest.mark.asyncio
    @patch("routers.generation.celery_app")
    async def test_stop_success(self, mock_celery):
        from routers.generation import stop_generation

        db = _mock_db()
        gen = _make_generation(status_val="running")
        db.query.return_value.filter.return_value.first.return_value = gen
        mock_celery.control.revoke = Mock()

        result = await stop_generation(
            generation_id="gen-1",
            current_user=_make_user(),
            db=db,
        )
        assert result["status"] == "stopped"
        assert gen.status == "stopped"
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_stop_not_found(self):
        from routers.generation import stop_generation

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await stop_generation(
                generation_id="missing",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_stop_forbidden_non_owner(self):
        from routers.generation import stop_generation

        db = _mock_db()
        gen = _make_generation(status_val="running", created_by="other-user")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await stop_generation(
                generation_id="gen-1",
                current_user=_make_user(is_superadmin=False),
                db=db,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.generation.celery_app")
    async def test_superadmin_can_stop_others(self, mock_celery):
        from routers.generation import stop_generation

        db = _mock_db()
        gen = _make_generation(status_val="running", created_by="other-user")
        db.query.return_value.filter.return_value.first.return_value = gen
        mock_celery.control.revoke = Mock()

        result = await stop_generation(
            generation_id="gen-1",
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_invalid_status(self):
        from routers.generation import stop_generation

        db = _mock_db()
        gen = _make_generation(status_val="completed")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await stop_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_stop_generic_exception(self):
        from routers.generation import stop_generation

        db = _mock_db()
        db.query.side_effect = RuntimeError("DB down")

        with pytest.raises(HTTPException) as exc:
            await stop_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# pause_generation
# ---------------------------------------------------------------------------


class TestPauseGeneration:
    @pytest.mark.asyncio
    @patch("routers.generation.get_redis_client")
    async def test_pause_success(self, mock_redis_fn):
        from routers.generation import pause_generation

        db = _mock_db()
        gen = _make_generation(status_val="running")
        db.query.return_value.filter.return_value.first.return_value = gen
        mock_redis_fn.return_value = Mock()

        result = await pause_generation(
            generation_id="gen-1",
            current_user=_make_user(),
            db=db,
        )
        assert result["status"] == "paused"
        assert gen.status == "paused"

    @pytest.mark.asyncio
    async def test_pause_not_found(self):
        from routers.generation import pause_generation

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await pause_generation(
                generation_id="missing",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_pause_forbidden_non_owner(self):
        from routers.generation import pause_generation

        db = _mock_db()
        gen = _make_generation(status_val="running", created_by="other-user")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await pause_generation(
                generation_id="gen-1",
                current_user=_make_user(is_superadmin=False),
                db=db,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.generation.get_redis_client")
    async def test_superadmin_can_pause_others(self, mock_redis_fn):
        from routers.generation import pause_generation

        db = _mock_db()
        gen = _make_generation(status_val="running", created_by="other-user")
        db.query.return_value.filter.return_value.first.return_value = gen
        mock_redis_fn.return_value = Mock()

        result = await pause_generation(
            generation_id="gen-1",
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result["status"] == "paused"

    @pytest.mark.asyncio
    async def test_pause_invalid_status(self):
        from routers.generation import pause_generation

        db = _mock_db()
        gen = _make_generation(status_val="completed")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await pause_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.generation.get_redis_client")
    async def test_pause_redis_none(self, mock_redis_fn):
        """Cover: redis_client is None -> skip redis storage."""
        from routers.generation import pause_generation

        db = _mock_db()
        gen = _make_generation(status_val="running")
        db.query.return_value.filter.return_value.first.return_value = gen
        mock_redis_fn.return_value = None

        result = await pause_generation(
            generation_id="gen-1",
            current_user=_make_user(),
            db=db,
        )
        assert result["status"] == "paused"

    @pytest.mark.asyncio
    async def test_pause_generic_exception(self):
        from routers.generation import pause_generation

        db = _mock_db()
        db.query.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            await pause_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# resume_generation
# ---------------------------------------------------------------------------


class TestResumeGeneration:
    @pytest.mark.asyncio
    @patch("routers.generation.celery_app")
    @patch("routers.generation.get_redis_client")
    async def test_resume_success_with_redis_progress(self, mock_redis_fn, mock_celery):
        from routers.generation import resume_generation

        db = _mock_db()
        gen = _make_generation(status_val="paused")
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {"selected_configuration": {"models": ["gpt-4"]}}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = project
            return mock_q

        db.query.side_effect = query_side_effect

        mock_redis = Mock()
        mock_redis.get.return_value = json.dumps(
            {"progress": 50, "completed_tasks": 5, "paused_at": "2025-06-15T10:00:00"}
        )
        mock_redis_fn.return_value = mock_redis

        mock_task = Mock()
        mock_task.id = "new-celery-id"
        mock_celery.send_task.return_value = mock_task

        result = await resume_generation(
            generation_id="gen-1",
            current_user=_make_user(),
            db=db,
        )
        assert result["status"] == "running"

    @pytest.mark.asyncio
    @patch("routers.generation.celery_app")
    @patch("routers.generation.get_redis_client")
    async def test_resume_success_no_redis(self, mock_redis_fn, mock_celery):
        from routers.generation import resume_generation

        db = _mock_db()
        gen = _make_generation(status_val="paused")
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = project
            return mock_q

        db.query.side_effect = query_side_effect
        mock_redis = Mock()
        mock_redis.get.return_value = None
        mock_redis_fn.return_value = mock_redis
        mock_task = Mock()
        mock_task.id = "new-celery-id"
        mock_celery.send_task.return_value = mock_task

        result = await resume_generation(
            generation_id="gen-1",
            current_user=_make_user(),
            db=db,
        )
        assert result["status"] == "running"

    @pytest.mark.asyncio
    @patch("routers.generation.celery_app")
    @patch("routers.generation.get_redis_client")
    async def test_superadmin_can_resume_others(self, mock_redis_fn, mock_celery):
        from routers.generation import resume_generation

        db = _mock_db()
        gen = _make_generation(status_val="paused", created_by="other-user")
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = project
            return mock_q

        db.query.side_effect = query_side_effect
        mock_redis_fn.return_value = None
        mock_task = Mock()
        mock_task.id = "new-celery-id"
        mock_celery.send_task.return_value = mock_task

        result = await resume_generation(
            generation_id="gen-1",
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_resume_not_found(self):
        from routers.generation import resume_generation

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await resume_generation(
                generation_id="missing",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_forbidden_non_owner(self):
        from routers.generation import resume_generation

        db = _mock_db()
        gen = _make_generation(status_val="paused", created_by="other-user")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await resume_generation(
                generation_id="gen-1",
                current_user=_make_user(is_superadmin=False),
                db=db,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_resume_invalid_status(self):
        from routers.generation import resume_generation

        db = _mock_db()
        gen = _make_generation(status_val="running")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await resume_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch("routers.generation.celery_app")
    @patch("routers.generation.get_redis_client")
    async def test_resume_project_not_found(self, mock_redis_fn, mock_celery):
        from routers.generation import resume_generation

        db = _mock_db()
        gen = _make_generation(status_val="paused")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = query_side_effect
        mock_redis_fn.return_value = None

        with pytest.raises(HTTPException) as exc:
            await resume_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_generic_exception(self):
        from routers.generation import resume_generation

        db = _mock_db()
        db.query.side_effect = RuntimeError("DB down")

        with pytest.raises(HTTPException) as exc:
            await resume_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# retry_generation
# ---------------------------------------------------------------------------


class TestRetryGeneration:
    @pytest.mark.asyncio
    @patch("routers.generation.celery_app")
    async def test_retry_success(self, mock_celery):
        from routers.generation import retry_generation

        db = _mock_db()
        gen = _make_generation(status_val="failed")
        gen.retry_count = 2
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = project
            return mock_q

        db.query.side_effect = query_side_effect

        mock_task = Mock()
        mock_task.id = "new-celery-id"
        mock_celery.send_task.return_value = mock_task

        result = await retry_generation(
            generation_id="gen-1",
            current_user=_make_user(),
            db=db,
        )
        assert result["status"] == "pending"
        assert result["retry_count"] == 3

    @pytest.mark.asyncio
    @patch("routers.generation.celery_app")
    async def test_retry_stopped_generation(self, mock_celery):
        from routers.generation import retry_generation

        db = _mock_db()
        gen = _make_generation(status_val="stopped")
        gen.retry_count = 0
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {}

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = project
            return mock_q

        db.query.side_effect = query_side_effect

        mock_task = Mock()
        mock_task.id = "new-celery-id"
        mock_celery.send_task.return_value = mock_task

        result = await retry_generation(
            generation_id="gen-1",
            current_user=_make_user(),
            db=db,
        )
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_retry_not_found(self):
        from routers.generation import retry_generation

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await retry_generation(
                generation_id="missing",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_forbidden_non_owner(self):
        from routers.generation import retry_generation

        db = _mock_db()
        gen = _make_generation(status_val="failed", created_by="other-user")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await retry_generation(
                generation_id="gen-1",
                current_user=_make_user(is_superadmin=False),
                db=db,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_retry_invalid_status(self):
        from routers.generation import retry_generation

        db = _mock_db()
        gen = _make_generation(status_val="running")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await retry_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_retry_generic_exception(self):
        from routers.generation import retry_generation

        db = _mock_db()
        db.query.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            await retry_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# delete_generation
# ---------------------------------------------------------------------------


class TestDeleteGeneration:
    @pytest.mark.asyncio
    async def test_delete_success(self):
        from routers.generation import delete_generation

        db = _mock_db()
        gen = _make_generation(status_val="completed")
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_q.delete.return_value = 3
        db.query.return_value = mock_q

        result = await delete_generation(
            generation_id="gen-1",
            current_user=_make_user(),
            db=db,
        )
        assert result["deleted_responses"] == 3
        db.delete.assert_called_once_with(gen)

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        from routers.generation import delete_generation

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await delete_generation(
                generation_id="missing",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_forbidden_non_owner(self):
        from routers.generation import delete_generation

        db = _mock_db()
        gen = _make_generation(status_val="completed", created_by="other-user")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await delete_generation(
                generation_id="gen-1",
                current_user=_make_user(is_superadmin=False),
                db=db,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_running_generation(self):
        from routers.generation import delete_generation

        db = _mock_db()
        gen = _make_generation(status_val="running")
        db.query.return_value.filter.return_value.first.return_value = gen

        with pytest.raises(HTTPException) as exc:
            await delete_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_generic_exception(self):
        from routers.generation import delete_generation

        db = _mock_db()
        db.query.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            await delete_generation(
                generation_id="gen-1",
                current_user=_make_user(),
                db=db,
            )
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# get_parse_metrics
# ---------------------------------------------------------------------------


class TestParseMetrics:
    @pytest.mark.asyncio
    @patch("routers.generation.check_project_accessible", return_value=True)
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_with_data_and_model_filter(self, mock_org, mock_access):
        from routers.generation import get_parse_metrics

        db = _mock_db()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q

        count_calls = {"n": 0}

        def count_side_effect():
            count_calls["n"] += 1
            return {1: 10, 2: 7, 3: 2, 4: 1, 5: 0}.get(count_calls["n"], 0)

        mock_q.count.side_effect = count_side_effect

        success_gen = Mock()
        success_gen.parse_metadata = {"retry_count": 2}
        success_gen2 = Mock()
        success_gen2.parse_metadata = None

        failed_gen = Mock()
        failed_gen.parse_error = "JSON decode error"
        failed_gen2 = Mock()
        failed_gen2.parse_error = "JSON decode error"
        failed_gen3 = Mock()
        failed_gen3.parse_error = None

        all_calls = {"n": 0}

        def all_side_effect():
            all_calls["n"] += 1
            if all_calls["n"] == 1:
                return [success_gen, success_gen2]
            elif all_calls["n"] == 2:
                return [failed_gen, failed_gen2, failed_gen3]
            return []

        mock_q.all.side_effect = all_side_effect
        db.query.return_value = mock_q

        result = await get_parse_metrics(
            request=_mock_request(),
            project_id="proj-1",
            model_id="gpt-4",
            db=db,
            current_user=_make_user(is_superadmin=True),
        )
        assert result["total_generations"] == 10
        assert result["parse_success"] == 7
        assert result["parse_failed"] == 2
        assert result["parse_success_rate"] == 0.7
        assert result["avg_retries_until_success"] > 0
        assert len(result["common_parse_errors"]) > 0

    @pytest.mark.asyncio
    @patch("routers.generation.check_project_accessible", return_value=True)
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_total_zero(self, mock_org, mock_access):
        from routers.generation import get_parse_metrics

        db = _mock_db()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.count.return_value = 0
        db.query.return_value = mock_q

        result = await get_parse_metrics(
            request=_mock_request(),
            project_id="proj-1",
            model_id=None,
            db=db,
            current_user=_make_user(),
        )
        assert result["total_generations"] == 0

    @pytest.mark.asyncio
    @patch("routers.generation.get_accessible_project_ids", return_value=["proj-1", "proj-2"])
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_no_project_id_with_accessible_projects(self, mock_org, mock_accessible):
        from routers.generation import get_parse_metrics

        db = _mock_db()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.count.return_value = 0
        db.query.return_value = mock_q

        result = await get_parse_metrics(
            request=_mock_request(),
            project_id=None,
            model_id=None,
            db=db,
            current_user=_make_user(is_superadmin=False),
        )
        assert result["total_generations"] == 0

    @pytest.mark.asyncio
    @patch("routers.generation.get_accessible_project_ids", return_value=[])
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_no_project_id_empty_accessible(self, mock_org, mock_accessible):
        """Cover: get_accessible_project_ids returns empty list -> early return."""
        from routers.generation import get_parse_metrics

        db = _mock_db()

        result = await get_parse_metrics(
            request=_mock_request(),
            project_id=None,
            model_id=None,
            db=db,
            current_user=_make_user(is_superadmin=False),
        )
        assert result["total_generations"] == 0

    @pytest.mark.asyncio
    @patch("routers.generation.get_accessible_project_ids", return_value=None)
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_no_project_id_none_accessible(self, mock_org, mock_accessible):
        """Cover: get_accessible_project_ids returns None (superadmin)."""
        from routers.generation import get_parse_metrics

        db = _mock_db()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.count.return_value = 0
        db.query.return_value = mock_q

        result = await get_parse_metrics(
            request=_mock_request(),
            project_id=None,
            model_id=None,
            db=db,
            current_user=_make_user(is_superadmin=True),
        )
        assert result["total_generations"] == 0

    @pytest.mark.asyncio
    @patch("routers.generation.check_project_accessible", return_value=False)
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_project_access_denied(self, mock_org, mock_access):
        from routers.generation import get_parse_metrics

        db = _mock_db()

        with pytest.raises(HTTPException) as exc:
            await get_parse_metrics(
                request=_mock_request(),
                project_id="proj-1",
                model_id=None,
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("routers.generation.check_project_accessible", return_value=True)
    @patch("routers.generation.get_org_context_from_request", return_value="private")
    async def test_parse_metrics_generic_exception(self, mock_org, mock_access):
        from routers.generation import get_parse_metrics

        db = _mock_db()
        db.query.side_effect = RuntimeError("boom")

        with pytest.raises(HTTPException) as exc:
            await get_parse_metrics(
                request=_mock_request(),
                project_id="proj-1",
                model_id=None,
                db=db,
                current_user=_make_user(),
            )
        assert exc.value.status_code == 500
