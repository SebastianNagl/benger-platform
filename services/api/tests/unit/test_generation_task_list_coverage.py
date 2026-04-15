"""
Unit tests for routers/generation_task_list.py to increase branch coverage.
Direct handler invocation (no TestClient) so pytest-cov tracks coverage.

Covers: get_project_with_permissions, get_single_task_generation_status,
get_task_generation_status, start_generation, get_generation_result.
"""

import json
import uuid
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


# ---------------------------------------------------------------------------
# get_project_with_permissions (helper function)
# ---------------------------------------------------------------------------


class TestGetProjectWithPermissions:
    def test_project_not_found(self):
        from routers.generation_task_list import get_project_with_permissions

        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        user = _make_user(is_superadmin=False)

        with pytest.raises(HTTPException) as exc:
            get_project_with_permissions("proj-1", user, db)
        assert exc.value.status_code == 404

    def test_superadmin_bypasses_checks(self):
        from routers.generation_task_list import get_project_with_permissions

        db = Mock()
        project = Mock()
        project.id = "proj-1"
        db.query.return_value.filter.return_value.first.return_value = project
        user = _make_user(is_superadmin=True)

        result = get_project_with_permissions("proj-1", user, db)
        assert result.id == "proj-1"

    def test_private_project_owner_access(self):
        from routers.generation_task_list import get_project_with_permissions

        db = Mock()
        project = Mock()
        project.id = "proj-1"
        project.is_private = True
        project.created_by = "user-123"
        db.query.return_value.filter.return_value.first.return_value = project
        user = _make_user(is_superadmin=False, user_id="user-123")

        result = get_project_with_permissions("proj-1", user, db)
        assert result.id == "proj-1"

    def test_private_project_non_owner_denied(self):
        from routers.generation_task_list import get_project_with_permissions

        db = Mock()
        project = Mock()
        project.id = "proj-1"
        project.is_private = True
        project.created_by = "other-user"
        db.query.return_value.filter.return_value.first.return_value = project
        user = _make_user(is_superadmin=False, user_id="user-123")

        with pytest.raises(HTTPException) as exc:
            get_project_with_permissions("proj-1", user, db)
        assert exc.value.status_code == 403

    @patch("routers.generation_task_list.check_project_accessible", return_value=True)
    def test_org_project_member_access(self, mock_check):
        from routers.generation_task_list import get_project_with_permissions

        db = Mock()
        project = Mock()
        project.id = "proj-1"
        project.is_private = False
        db.query.return_value.filter.return_value.first.return_value = project
        user = _make_user(is_superadmin=False)

        result = get_project_with_permissions("proj-1", user, db)
        assert result.id == "proj-1"
        mock_check.assert_called_once()

    @patch("routers.generation_task_list.check_project_accessible", return_value=False)
    def test_org_project_non_member_denied(self, mock_check):
        from routers.generation_task_list import get_project_with_permissions

        db = Mock()
        project = Mock()
        project.id = "proj-1"
        project.is_private = False
        db.query.return_value.filter.return_value.first.return_value = project
        user = _make_user(is_superadmin=False)

        with pytest.raises(HTTPException) as exc:
            get_project_with_permissions("proj-1", user, db)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# get_single_task_generation_status (helper function)
# ---------------------------------------------------------------------------


class TestGetSingleTaskGenerationStatus:
    def test_no_generation_returns_none_status(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = None
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", None, db)
        assert result.status is None
        assert result.task_id == "task-1"

    def test_completed_with_dict_result(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        gen = Mock()
        gen.id = "gen-1"
        gen.status = "completed"
        gen.result = {"text": "a" * 200}
        gen.completed_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = None
        gen.structure_key = "default"

        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = gen
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", "default", db)
        assert result.status == "completed"
        assert result.result_preview is not None
        assert result.result_preview.endswith("...")

    def test_completed_with_string_result(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        gen = Mock()
        gen.id = "gen-1"
        gen.status = "completed"
        gen.result = "short text"
        gen.completed_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = None
        gen.structure_key = None

        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = gen
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", None, db)
        assert result.status == "completed"
        assert result.result_preview == "short text"

    def test_failed_with_error_message(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        gen = Mock()
        gen.id = "gen-1"
        gen.status = "failed"
        gen.result = None
        gen.completed_at = None
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = "API timeout"
        gen.structure_key = None

        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = gen
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", None, db)
        assert result.status == "failed"
        assert result.error_message == "API timeout"

    def test_with_structure_key_none_filter(self):
        from routers.generation_task_list import get_single_task_generation_status

        db = Mock()
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = None
        db.query.return_value = mock_q

        result = get_single_task_generation_status("task-1", "gpt-4", None, db)
        assert result.status is None


# ---------------------------------------------------------------------------
# get_task_generation_status (endpoint)
# ---------------------------------------------------------------------------


class TestGetTaskGenerationStatusEndpoint:
    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_no_models_configured(self, mock_perms):
        from routers.generation_task_list import get_task_generation_status

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {"selected_configuration": {"models": []}}
        mock_perms.return_value = project

        result = await get_task_generation_status(
            project_id="proj-1",
            request=_mock_request(),
            page=1,
            page_size=50,
            search=None,
            status_filter=None,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.total == 0
        assert result.models == []

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    @patch("routers.generation_task_list.get_single_task_generation_status")
    async def test_with_tasks_and_models(self, mock_gen_status, mock_perms):
        from routers.generation_task_list import get_task_generation_status, TaskGenerationStatus

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {
            "selected_configuration": {"models": ["gpt-4"]},
            "prompt_structures": {},
        }
        mock_perms.return_value = project

        task = Mock()
        task.id = "task-1"
        task.data = {"text": "hello"}
        task.meta = None
        task.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.count.return_value = 1
        mock_q.all.return_value = [task]
        db.query.return_value = mock_q

        mock_gen_status.return_value = TaskGenerationStatus(
            task_id="task-1", model_id="gpt-4", structure_key=None, status=None
        )

        result = await get_task_generation_status(
            project_id="proj-1",
            request=_mock_request(),
            page=1,
            page_size=50,
            search=None,
            status_filter=None,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.total == 1
        assert len(result.tasks) == 1

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_with_prompt_structures(self, mock_perms):
        from routers.generation_task_list import get_task_generation_status

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {
            "selected_configuration": {"models": ["gpt-4"]},
            "prompt_structures": {"default": {}, "detailed": {}},
        }
        mock_perms.return_value = project

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.count.return_value = 0
        mock_q.all.return_value = []
        db.query.return_value = mock_q

        result = await get_task_generation_status(
            project_id="proj-1",
            request=_mock_request(),
            page=1,
            page_size=50,
            search=None,
            status_filter=None,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert set(result.structures) == {"default", "detailed"}

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    @patch("routers.generation_task_list.get_single_task_generation_status")
    async def test_status_filter_excludes_non_matching(self, mock_gen_status, mock_perms):
        from routers.generation_task_list import get_task_generation_status, TaskGenerationStatus

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {
            "selected_configuration": {"models": ["gpt-4"]},
            "prompt_structures": {},
        }
        mock_perms.return_value = project

        task = Mock()
        task.id = "task-1"
        task.data = {"text": "hello"}
        task.meta = None
        task.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.count.return_value = 1
        mock_q.all.return_value = [task]
        db.query.return_value = mock_q

        mock_gen_status.return_value = TaskGenerationStatus(
            task_id="task-1", model_id="gpt-4", structure_key=None, status=None
        )

        result = await get_task_generation_status(
            project_id="proj-1",
            request=_mock_request(),
            page=1,
            page_size=50,
            search=None,
            status_filter="completed",
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert len(result.tasks) == 0

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    @patch("routers.generation_task_list.get_single_task_generation_status")
    async def test_with_search_filter(self, mock_gen_status, mock_perms):
        from routers.generation_task_list import get_task_generation_status, TaskGenerationStatus

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {
            "selected_configuration": {"models": ["gpt-4"]},
            "prompt_structures": {},
        }
        mock_perms.return_value = project

        task = Mock()
        task.id = "task-1"
        task.data = {"text": "hello"}
        task.meta = None
        task.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.count.return_value = 1
        mock_q.all.return_value = [task]
        db.query.return_value = mock_q

        mock_gen_status.return_value = TaskGenerationStatus(
            task_id="task-1", model_id="gpt-4", structure_key=None, status=None
        )

        result = await get_task_generation_status(
            project_id="proj-1",
            request=_mock_request(),
            page=1,
            page_size=50,
            search="hello",
            status_filter=None,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.total == 1


# ---------------------------------------------------------------------------
# start_generation (endpoint)
# ---------------------------------------------------------------------------


class TestStartGeneration:
    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_no_models_configured_error(self, mock_perms):
        from routers.generation_task_list import start_generation, GenerationRequest

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {"selected_configuration": {"models": []}}
        mock_perms.return_value = project

        with pytest.raises(HTTPException) as exc:
            await start_generation(
                project_id="proj-1",
                request=GenerationRequest(mode="all"),
                raw_request=_mock_request(),
                current_user=_make_user(is_superadmin=True),
                db=db,
            )
        assert exc.value.status_code == 400
        assert "No models" in exc.value.detail

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_no_tasks_error(self, mock_perms):
        from routers.generation_task_list import start_generation, GenerationRequest

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {"selected_configuration": {"models": ["gpt-4"]}}
        mock_perms.return_value = project

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = []
        db.query.return_value = mock_q

        with pytest.raises(HTTPException) as exc:
            await start_generation(
                project_id="proj-1",
                request=GenerationRequest(mode="all"),
                raw_request=_mock_request(),
                current_user=_make_user(is_superadmin=True),
                db=db,
            )
        assert exc.value.status_code == 400
        assert "No tasks" in exc.value.detail

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.celery_app")
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_all_mode_with_cancellation_and_dispatch(self, mock_perms, mock_celery):
        from routers.generation_task_list import start_generation, GenerationRequest, GenerationParameters

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {
            "selected_configuration": {"models": ["gpt-4"], "parameters": {}}
        }
        mock_perms.return_value = project

        task = Mock()
        task.id = "task-1"

        pending_gen = Mock()
        pending_gen.id = "old-gen-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.all.return_value = [task]
            elif call_count["n"] == 2:
                mock_q.all.return_value = [pending_gen]
            elif call_count["n"] == 3:
                mock_q.update.return_value = 1
            else:
                mock_q.first.return_value = None
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect
        mock_celery.control.revoke = Mock()
        mock_celery.send_task = Mock()

        result = await start_generation(
            project_id="proj-1",
            request=GenerationRequest(
                mode="all",
                parameters=GenerationParameters(temperature=0.5, max_tokens=2000),
                model_configs={"gpt-4": {"max_tokens": 4000}},
            ),
            raw_request=_mock_request(),
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.mode == "all"
        assert result.tasks_queued >= 1

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.celery_app")
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_missing_mode_skips_completed(self, mock_perms, mock_celery):
        from routers.generation_task_list import start_generation, GenerationRequest

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {
            "selected_configuration": {"models": ["gpt-4"]}
        }
        mock_perms.return_value = project

        task1 = Mock()
        task1.id = "task-1"
        task2 = Mock()
        task2.id = "task-2"

        completed_gen = Mock()
        completed_gen.status = "completed"

        failed_gen = Mock()
        failed_gen.status = "failed"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.all.return_value = [task1, task2]
            elif call_count["n"] == 2:
                mock_q.first.return_value = completed_gen
            elif call_count["n"] == 3:
                mock_q.first.return_value = failed_gen
            else:
                mock_q.first.return_value = None
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect
        mock_celery.send_task = Mock()

        result = await start_generation(
            project_id="proj-1",
            request=GenerationRequest(mode="missing"),
            raw_request=_mock_request(),
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.mode == "missing"
        assert result.tasks_queued == 1

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.celery_app")
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_with_specific_task_ids_and_model_ids(self, mock_perms, mock_celery):
        from routers.generation_task_list import start_generation, GenerationRequest

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {"selected_configuration": {"models": ["gpt-4", "claude-3"]}}
        mock_perms.return_value = project

        task = Mock()
        task.id = "task-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.all.return_value = [task]
            else:
                mock_q.first.return_value = None
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect
        mock_celery.send_task = Mock()

        result = await start_generation(
            project_id="proj-1",
            request=GenerationRequest(
                mode="all",
                model_ids=["gpt-4"],
                task_ids=["task-1"],
                structure_keys=["default"],
            ),
            raw_request=_mock_request(),
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.tasks_queued == 1

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.celery_app")
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_with_structure_keys_from_config(self, mock_perms, mock_celery):
        from routers.generation_task_list import start_generation, GenerationRequest

        db = _mock_db()
        project = Mock()
        project.id = "proj-1"
        project.generation_config = {
            "selected_configuration": {
                "models": ["gpt-4"],
            },
            "prompt_structures": {
                "default": {"name": "Default"},
                "detailed": {"name": "Detailed"},
            },
        }
        mock_perms.return_value = project

        task = Mock()
        task.id = "task-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.all.return_value = [task]
            else:
                mock_q.first.return_value = None
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect
        mock_celery.send_task = Mock()

        result = await start_generation(
            project_id="proj-1",
            request=GenerationRequest(mode="all"),
            raw_request=_mock_request(),
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.tasks_queued == 2


# ---------------------------------------------------------------------------
# get_generation_result (endpoint)
# ---------------------------------------------------------------------------


class TestGetGenerationResult:
    @pytest.mark.asyncio
    async def test_task_not_found(self):
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_generation_result(
                request=_mock_request(),
                task_id="t1",
                model_id="gpt-4",
                structure_key=None,
                current_user=_make_user(is_superadmin=True),
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_no_generations_found(self, mock_perms):
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"

        project = Mock()
        project.id = "proj-1"
        mock_perms.return_value = project

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key=None,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.task_id == "task-1"
        assert result.model_id == "gpt-4"
        assert result.results == []

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_completed_with_single_individual_generation(self, mock_perms):
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"

        project = Mock()
        project.id = "proj-1"
        mock_perms.return_value = project

        gen = Mock()
        gen.id = "gen-1"
        gen.status = "completed"
        gen.result = None
        gen.completed_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = None
        gen.structure_key = None
        gen.prompt_used = "Translate the following text"
        gen.parameters = {"temperature": 0.0}
        gen.created_by = "user-123"

        ind_gen = Mock()
        ind_gen.response_content = "Hello world"
        ind_gen.created_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
        ind_gen.usage_stats = {"tokens": 100}
        ind_gen.generation_id = "gen-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen]
            elif call_count["n"] == 3:
                mock_q.all.return_value = [ind_gen]
            elif call_count["n"] == 4:
                mock_q.all.return_value = []  # DBUser batch query
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key=None,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.task_id == "task-1"
        assert len(result.results) == 1
        assert result.results[0].status == "completed"
        assert result.results[0].result["generated_text"] == "Hello world"
        assert result.results[0].generation_time_seconds is not None

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_completed_with_multiple_individual_generations(self, mock_perms):
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"

        project = Mock()
        project.id = "proj-1"
        mock_perms.return_value = project

        gen = Mock()
        gen.id = "gen-1"
        gen.status = "completed"
        gen.result = None
        gen.completed_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = None
        gen.structure_key = None
        gen.prompt_used = None
        gen.parameters = None
        gen.created_by = "user-123"

        ind_gen1 = Mock()
        ind_gen1.response_content = "First response"
        ind_gen1.created_at = datetime(2025, 6, 2, 0, 0, 0, tzinfo=timezone.utc)
        ind_gen1.usage_stats = {"tokens": 50}
        ind_gen1.generation_id = "gen-1"

        ind_gen2 = Mock()
        ind_gen2.response_content = "Second response"
        ind_gen2.created_at = datetime(2025, 6, 2, 1, 0, 0, tzinfo=timezone.utc)
        ind_gen2.usage_stats = {"tokens": 60}
        ind_gen2.generation_id = "gen-1"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen]
            elif call_count["n"] == 3:
                mock_q.all.return_value = [ind_gen1, ind_gen2]
            elif call_count["n"] == 4:
                mock_q.all.return_value = []  # DBUser batch query
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key=None,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert "generations" in result.results[0].result
        assert len(result.results[0].result["generations"]) == 2

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_failed_generation(self, mock_perms):
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"

        project = Mock()
        project.id = "proj-1"
        mock_perms.return_value = project

        gen = Mock()
        gen.id = "gen-1"
        gen.status = "failed"
        gen.result = None
        gen.completed_at = None
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = "API rate limit exceeded"
        gen.structure_key = None
        gen.prompt_used = None
        gen.parameters = None
        gen.created_by = "user-123"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen]
            else:
                mock_q.all.return_value = []  # DBUser batch query (no completed gens to batch)

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key=None,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.results[0].status == "failed"
        assert result.results[0].error_message == "API rate limit exceeded"

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_with_structure_key_filter(self, mock_perms):
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"

        project = Mock()
        project.id = "proj-1"
        mock_perms.return_value = project

        gen = Mock()
        gen.id = "gen-1"
        gen.status = "completed"
        gen.result = {"text": "test"}
        gen.completed_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
        gen.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen.error_message = None
        gen.structure_key = "default"
        gen.prompt_used = None
        gen.parameters = None
        gen.created_by = "user-123"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen]
            elif call_count["n"] == 3:
                mock_q.all.return_value = []  # batch DBGeneration
            elif call_count["n"] == 4:
                mock_q.all.return_value = []  # DBUser batch query
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key="default",
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.results[0].structure_key == "default"

    # ---- Issue #1372: Generation history tests ----

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_default_deduplication_unchanged(self, mock_perms):
        """Two generations for the same structure_key: default mode returns only the most recent."""
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"
        mock_perms.return_value = Mock(id="proj-1")

        # Two gens for same structure_key, ordered newest-first
        gen_new = Mock()
        gen_new.id = "gen-new"
        gen_new.status = "completed"
        gen_new.result = None
        gen_new.completed_at = datetime(2025, 7, 2, tzinfo=timezone.utc)
        gen_new.created_at = datetime(2025, 7, 1, tzinfo=timezone.utc)
        gen_new.error_message = None
        gen_new.structure_key = "default"
        gen_new.prompt_used = None
        gen_new.parameters = None
        gen_new.created_by = "user-1"

        gen_old = Mock()
        gen_old.id = "gen-old"
        gen_old.status = "completed"
        gen_old.result = None
        gen_old.completed_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
        gen_old.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gen_old.error_message = None
        gen_old.structure_key = "default"
        gen_old.prompt_used = None
        gen_old.parameters = None
        gen_old.created_by = "user-1"

        ind_gen = Mock()
        ind_gen.response_content = "New response"
        ind_gen.created_at = datetime(2025, 7, 2, tzinfo=timezone.utc)
        ind_gen.usage_stats = {"tokens": 100}
        ind_gen.generation_id = "gen-new"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen_new, gen_old]  # newest first
            elif call_count["n"] == 3:
                mock_q.all.return_value = [ind_gen]  # batch DBGeneration
            elif call_count["n"] == 4:
                mock_q.all.return_value = []  # batch DBUser
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key=None,
            include_history=False,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        # Default mode: dedup keeps only newest per structure_key
        assert len(result.results) == 1
        assert result.results[0].generation_id == "gen-new"

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_include_history_returns_all(self, mock_perms):
        """include_history=True returns all generations across structures."""
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"
        mock_perms.return_value = Mock(id="proj-1")

        def make_gen(gen_id, structure_key, status, created_at, completed_at=None, created_by="user-1"):
            g = Mock()
            g.id = gen_id
            g.status = status
            g.result = None
            g.completed_at = completed_at
            g.created_at = created_at
            g.error_message = None
            g.structure_key = structure_key
            g.prompt_used = None
            g.parameters = None
            g.created_by = created_by
            return g

        gen1 = make_gen("gen-1", "default", "completed", datetime(2025, 7, 1, tzinfo=timezone.utc), datetime(2025, 7, 1, 1, tzinfo=timezone.utc))
        gen2 = make_gen("gen-2", "default", "completed", datetime(2025, 6, 1, tzinfo=timezone.utc), datetime(2025, 6, 1, 1, tzinfo=timezone.utc))
        gen3 = make_gen("gen-3", "custom", "completed", datetime(2025, 7, 1, tzinfo=timezone.utc), datetime(2025, 7, 1, 1, tzinfo=timezone.utc))

        ind_gen1 = Mock(response_content="Resp 1", created_at=datetime(2025, 7, 1, tzinfo=timezone.utc), usage_stats={}, generation_id="gen-1")
        ind_gen2 = Mock(response_content="Resp 2", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc), usage_stats={}, generation_id="gen-2")
        ind_gen3 = Mock(response_content="Resp 3", created_at=datetime(2025, 7, 1, tzinfo=timezone.utc), usage_stats={}, generation_id="gen-3")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen1, gen2, gen3]
            elif call_count["n"] == 3:
                mock_q.all.return_value = [ind_gen1, ind_gen2, ind_gen3]  # batch DBGeneration
            elif call_count["n"] == 4:
                mock_q.all.return_value = []  # batch DBUser
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key=None,
            include_history=True,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        # History mode: all 3 generations returned
        assert len(result.results) == 3
        gen_ids = [r.generation_id for r in result.results]
        assert "gen-1" in gen_ids
        assert "gen-2" in gen_ids
        assert "gen-3" in gen_ids

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_include_history_with_structure_filter(self, mock_perms):
        """include_history=True combined with structure_key filter."""
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"
        mock_perms.return_value = Mock(id="proj-1")

        # Only "default" structure generations (pre-filtered by SQL WHERE)
        gen1 = Mock(id="gen-1", status="completed", result=None,
                    completed_at=datetime(2025, 7, 1, 1, tzinfo=timezone.utc),
                    created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
                    error_message=None, structure_key="default", prompt_used=None,
                    parameters=None, created_by="user-1")
        gen2 = Mock(id="gen-2", status="failed", result=None,
                    completed_at=None,
                    created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
                    error_message="Rate limit", structure_key="default", prompt_used=None,
                    parameters=None, created_by="user-1")

        ind_gen = Mock(response_content="Result", created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
                       usage_stats={}, generation_id="gen-1")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen1, gen2]
            elif call_count["n"] == 3:
                mock_q.all.return_value = [ind_gen]  # batch DBGeneration (only gen1 is completed)
            elif call_count["n"] == 4:
                mock_q.all.return_value = []  # batch DBUser
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key="default",
            include_history=True,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert len(result.results) == 2
        assert result.results[0].generation_id == "gen-1"
        assert result.results[1].generation_id == "gen-2"
        assert result.results[1].status == "failed"

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_created_by_name_populated(self, mock_perms):
        """created_by and created_by_name are populated when user exists."""
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"
        mock_perms.return_value = Mock(id="proj-1")

        gen = Mock(id="gen-1", status="failed", result=None,
                   completed_at=None,
                   created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
                   error_message="Error", structure_key=None, prompt_used=None,
                   parameters=None, created_by="user-42")

        mock_user = Mock()
        mock_user.id = "user-42"
        mock_user.name = "Alice Smith"

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen]
            elif call_count["n"] == 3:
                # No completed gens → this is the DBUser batch query
                mock_q.all.return_value = [mock_user]
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key=None,
            include_history=False,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.results[0].created_by == "user-42"
        assert result.results[0].created_by_name == "Alice Smith"

    @pytest.mark.asyncio
    @patch("routers.generation_task_list.get_project_with_permissions")
    async def test_created_by_name_missing_user(self, mock_perms):
        """created_by_name is None when user no longer exists in DB."""
        from routers.generation_task_list import get_generation_result

        db = _mock_db()
        task = Mock()
        task.id = "task-1"
        task.project_id = "proj-1"
        mock_perms.return_value = Mock(id="proj-1")

        gen = Mock(id="gen-1", status="failed", result=None,
                   completed_at=None,
                   created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
                   error_message="Error", structure_key=None, prompt_used=None,
                   parameters=None, created_by="deleted-user-99")

        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q

            if call_count["n"] == 1:
                mock_q.first.return_value = task
            elif call_count["n"] == 2:
                mock_q.all.return_value = [gen]
            elif call_count["n"] == 3:
                # DBUser query returns empty — user deleted
                mock_q.all.return_value = []
            else:
                mock_q.all.return_value = []

            return mock_q

        db.query.side_effect = query_side_effect

        result = await get_generation_result(
            request=_mock_request(),
            task_id="task-1",
            model_id="gpt-4",
            structure_key=None,
            include_history=False,
            current_user=_make_user(is_superadmin=True),
            db=db,
        )
        assert result.results[0].created_by == "deleted-user-99"
        assert result.results[0].created_by_name is None
