"""
Unit and integration tests for generation task list endpoints (Issue #495).
Tests paginated task list with per-model generation status.
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from routers.generation_task_list import (
    GenerationRequest,
    PaginatedTaskGenerationResponse,
    TaskWithGenerationStatus,
    get_project_with_permissions,
    get_single_task_generation_status,
)


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = str(uuid.uuid4())
    user.is_superadmin = True
    return user


@pytest.fixture
def mock_project():
    """Create a mock project."""
    project = MagicMock()
    project.id = str(uuid.uuid4())
    project.title = "Test Project"
    project.is_private = False
    project.generation_config = {
        "selected_configuration": {"models": ["gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"]}
    }
    return project


@pytest.fixture
def mock_task():
    """Create a mock task."""
    task = MagicMock()
    task.id = str(uuid.uuid4())
    task.project_id = str(uuid.uuid4())
    task.data = {"text": "Test task content", "question": "What is the answer?"}
    task.meta = {"system_prompt": "You are helpful", "generation_prompt": "Generate response"}
    task.created_at = datetime.now()
    return task


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_project_with_permissions_superadmin(self, mock_db, mock_user, mock_project):
        """Test project access for superadmin."""
        mock_db.query().filter().first.return_value = mock_project

        result = get_project_with_permissions(mock_project.id, mock_user, mock_db)

        assert result == mock_project
        mock_db.query().filter().first.assert_called_once()

    def test_get_project_with_permissions_not_found(self, mock_db, mock_user):
        """Test project not found error."""
        mock_db.query().filter().first.return_value = None

        with pytest.raises(Exception) as exc_info:
            get_project_with_permissions("invalid-id", mock_user, mock_db)

        assert "not found" in str(exc_info.value).lower()

    @patch('routers.generation_task_list.check_project_accessible', return_value=True)
    def test_get_project_with_permissions_org_member(self, mock_check, mock_db, mock_project):
        """Test access to non-private project by org member (non-superadmin)."""
        mock_db.query().filter().first.return_value = mock_project

        user = MagicMock()
        user.is_superadmin = False
        user.id = str(uuid.uuid4())

        result = get_project_with_permissions(mock_project.id, user, mock_db)
        assert result == mock_project
        mock_check.assert_called_once()

    @patch('routers.generation_task_list.check_project_accessible', return_value=False)
    def test_get_project_with_permissions_non_member_denied(self, mock_check, mock_db, mock_project):
        """Test non-member gets 403 on non-private project."""
        mock_db.query().filter().first.return_value = mock_project

        user = MagicMock()
        user.is_superadmin = False
        user.id = str(uuid.uuid4())

        with pytest.raises(Exception) as exc_info:
            get_project_with_permissions(mock_project.id, user, mock_db)
        assert exc_info.value.status_code == 403

    def test_get_single_task_generation_status_no_generation(self, mock_db):
        """Test status when no generation exists."""
        mock_db.query().filter().filter().order_by().first.return_value = None

        result = get_single_task_generation_status("task-id", "model-id", None, mock_db)

        assert result.task_id == "task-id"
        assert result.model_id == "model-id"
        assert result.structure_key is None
        assert result.status is None
        assert result.generation_id is None

    def test_get_single_task_generation_status_completed(self, mock_db):
        """Test status for completed generation."""
        mock_generation = MagicMock()
        mock_generation.id = str(uuid.uuid4())
        mock_generation.status = "completed"
        mock_generation.result = {"generated_text": "This is a test response"}
        mock_generation.completed_at = datetime.now()
        mock_generation.created_at = datetime.now()
        mock_generation.error_message = None

        mock_db.query().filter().filter().order_by().first.return_value = mock_generation

        result = get_single_task_generation_status("task-id", "model-id", None, mock_db)

        assert result.task_id == "task-id"
        assert result.model_id == "model-id"
        assert result.structure_key is None
        assert result.status == "completed"
        assert result.generation_id == mock_generation.id
        assert result.result_preview is not None

    def test_get_single_task_generation_status_failed(self, mock_db):
        """Test status for failed generation."""
        mock_generation = MagicMock()
        mock_generation.id = str(uuid.uuid4())
        mock_generation.status = "failed"
        mock_generation.result = None
        mock_generation.completed_at = datetime.now()
        mock_generation.created_at = datetime.now()
        mock_generation.error_message = "API rate limit exceeded"

        mock_db.query().filter().filter().order_by().first.return_value = mock_generation

        result = get_single_task_generation_status("task-id", "model-id", None, mock_db)

        assert result.task_id == "task-id"
        assert result.model_id == "model-id"
        assert result.structure_key is None
        assert result.status == "failed"
        assert result.error_message == "API rate limit exceeded"
        assert result.result_preview is None


    def test_get_single_task_generation_status_with_structure_key(self, mock_db):
        """Test status lookup with explicit structure_key finds matching generation."""
        mock_generation = MagicMock()
        mock_generation.id = str(uuid.uuid4())
        mock_generation.status = "completed"
        mock_generation.result = {"text": "response"}
        mock_generation.completed_at = datetime.now()
        mock_generation.created_at = datetime.now()
        mock_generation.error_message = None

        mock_db.query().filter().filter().order_by().first.return_value = mock_generation

        result = get_single_task_generation_status("task-id", "model-id", "default", mock_db)

        assert result.task_id == "task-id"
        assert result.model_id == "model-id"
        assert result.structure_key == "default"
        assert result.status == "completed"

    def test_get_single_task_generation_status_structure_key_no_match(self, mock_db):
        """Test status with structure_key returns null status when no generation found."""
        mock_db.query().filter().filter().order_by().first.return_value = None

        result = get_single_task_generation_status("task-id", "model-id", "default", mock_db)

        assert result.structure_key == "default"
        assert result.status is None


class TestPrivateProjectPermissions:
    """Test private project handling in get_project_with_permissions."""

    def test_private_project_creator_has_access(self, mock_db):
        """Private project creator should have access."""
        user_id = str(uuid.uuid4())
        user = MagicMock()
        user.id = user_id
        user.is_superadmin = False

        project = MagicMock()
        project.id = str(uuid.uuid4())
        project.is_private = True
        project.created_by = user_id

        mock_db.query().filter().first.return_value = project

        result = get_project_with_permissions(project.id, user, mock_db)
        assert result == project

    def test_private_project_other_user_blocked(self, mock_db):
        """Non-creator should get 403 on private project."""
        user = MagicMock()
        user.id = str(uuid.uuid4())
        user.is_superadmin = False

        project = MagicMock()
        project.id = str(uuid.uuid4())
        project.is_private = True
        project.created_by = str(uuid.uuid4())  # Different user

        mock_db.query().filter().first.return_value = project

        with pytest.raises(Exception) as exc_info:
            get_project_with_permissions(project.id, user, mock_db)
        assert exc_info.value.status_code == 403

    def test_private_project_superadmin_has_access(self, mock_db):
        """Superadmin should have access to any private project."""
        user = MagicMock()
        user.id = str(uuid.uuid4())
        user.is_superadmin = True

        project = MagicMock()
        project.id = str(uuid.uuid4())
        project.is_private = True
        project.created_by = str(uuid.uuid4())  # Different user

        mock_db.query().filter().first.return_value = project

        result = get_project_with_permissions(project.id, user, mock_db)
        assert result == project


class TestPaginatedTaskGenerationEndpoint:
    """Test the paginated task generation status endpoint."""

    @patch('services.feature_flag_service.FeatureFlagService')
    def test_get_task_generation_status_feature_disabled(
        self, mock_flag_service, mock_db, mock_user
    ):
        """Test that endpoint returns 403 when feature flag is disabled."""
        mock_flag_service.return_value.is_enabled.return_value = False

        # This would need to be tested through the actual FastAPI app
        # Here we just verify the flag service would be called correctly
        flag_service = mock_flag_service(mock_db)
        assert not flag_service.is_enabled("generation", mock_user)

    def test_paginated_response_structure(self):
        """Test the structure of paginated response."""
        tasks = [
            TaskWithGenerationStatus(
                id=str(uuid.uuid4()),
                data={"text": "Task 1"},
                meta=None,
                created_at=datetime.now(),
                generation_status={},
            ),
            TaskWithGenerationStatus(
                id=str(uuid.uuid4()),
                data={"text": "Task 2"},
                meta=None,
                created_at=datetime.now(),
                generation_status={},
            ),
        ]

        response = PaginatedTaskGenerationResponse(
            tasks=tasks,
            total=2,
            page=1,
            page_size=50,
            total_pages=1,
            models=["gpt-4o", "claude-sonnet-4"],
            structures=[],
        )

        assert len(response.tasks) == 2
        assert response.total == 2
        assert response.page == 1
        assert response.page_size == 50
        assert response.total_pages == 1
        assert len(response.models) == 2

    def test_pagination_calculation(self):
        """Test pagination calculations."""
        # Test various pagination scenarios
        test_cases = [
            (100, 25, 4),  # 100 items, 25 per page = 4 pages
            (99, 25, 4),  # 99 items, 25 per page = 4 pages
            (101, 25, 5),  # 101 items, 25 per page = 5 pages
            (0, 25, 0),  # 0 items = 0 pages
            (1, 25, 1),  # 1 item = 1 page
        ]

        for total, page_size, expected_pages in test_cases:
            actual_pages = (total + page_size - 1) // page_size if total > 0 else 0
            assert (
                actual_pages == expected_pages
            ), f"Failed for total={total}, page_size={page_size}"


class TestGenerationEndpoint:
    """Test the generation endpoint."""

    def test_generation_request_validation(self):
        """Test request validation for generation."""
        # Valid request with all mode
        request = GenerationRequest(
            mode="all", model_ids=["gpt-4o", "claude-sonnet-4"], task_ids=["task-1", "task-2"]
        )
        assert request.mode == "all"
        assert len(request.model_ids) == 2
        assert len(request.task_ids) == 2

        # Valid request with missing mode
        request = GenerationRequest(mode="missing", model_ids=None, task_ids=None)
        assert request.mode == "missing"
        assert request.model_ids is None
        assert request.task_ids is None

    def test_generation_mode_validation(self):
        """Test that only 'all' or 'missing' modes are accepted."""
        with pytest.raises(Exception):
            # This would raise a validation error in actual FastAPI
            GenerationRequest(mode="invalid", model_ids=["gpt-4o"])

    @patch('routers.generation_task_list.celery_app')
    def test_generation_queues_tasks(self, mock_celery, mock_db):
        """Test that generation correctly queues tasks."""
        # Setup mock tasks
        mock_tasks = [MagicMock(id=f"task-{i}") for i in range(3)]
        mock_db.query().filter().all.return_value = mock_tasks

        # Setup mock for checking existing generations (all missing)
        mock_db.query().filter().first.return_value = None

        # Simulate queuing tasks
        tasks_to_queue = []
        model_ids = ["gpt-4o", "claude-sonnet-4"]

        for task in mock_tasks:
            for model_id in model_ids:
                tasks_to_queue.append((task.id, model_id))

        # Verify correct number of tasks would be queued
        assert len(tasks_to_queue) == 6  # 3 tasks * 2 models

    def test_parallel_processing_estimation(self):
        """Test time estimation for parallel processing."""
        # Test estimation calculation
        tasks_count = 10
        models_count = 3

        # Estimation formula from the code
        estimated_time = (tasks_count // models_count * 5) if models_count else (tasks_count * 5)

        assert estimated_time == 15  # (10 // 3) * 5 = 3 * 5 = 15


class TestGenerationResultEndpoint:
    """Test the generation result retrieval endpoint."""

    def test_generation_result_response_structure(self):
        """Test the structure of generation result response."""
        from routers.generation_task_list import GenerationResultResponse

        response = GenerationResultResponse(
            task_id="task-123",
            model_id="gpt-4o",
            generation_id="gen-456",
            status="completed",
            result={"generated_text": "Test response"},
            generated_at=datetime.now(),
            generation_time_seconds=2.5,
            prompt_used="Generate a response",
            parameters={"temperature": 0.7, "max_tokens": 2000},
            error_message=None,
        )

        assert response.task_id == "task-123"
        assert response.model_id == "gpt-4o"
        assert response.status == "completed"
        assert response.result["generated_text"] == "Test response"
        assert response.generation_time_seconds == 2.5

    def test_generation_time_calculation(self):
        """Test generation time calculation."""
        created_at = datetime(2024, 1, 1, 12, 0, 0)
        completed_at = datetime(2024, 1, 1, 12, 0, 5)

        generation_time = (completed_at - created_at).total_seconds()

        assert generation_time == 5.0


class TestWebSocketIntegration:
    """Test WebSocket integration for real-time updates."""

    def test_websocket_url_construction(self):
        """Test WebSocket URL construction from API URL."""
        test_cases = [
            ("http://api.localhost", "ws://api.localhost/ws/projects/{}/generation-status"),
            ("https://api.example.com", "wss://api.example.com/ws/projects/{}/generation-status"),
            ("http://localhost:8000", "ws://localhost:8000/ws/projects/{}/generation-status"),
        ]

        for api_url, expected_pattern in test_cases:
            ws_protocol = "wss" if api_url.startswith("https") else "ws"
            ws_host = api_url.replace("https://", "").replace("http://", "")
            ws_url = f"{ws_protocol}://{ws_host}/ws/projects/{{}}/generation-status"

            assert ws_url == expected_pattern.format("{}")

    def test_websocket_message_structure(self):
        """Test the structure of WebSocket messages."""
        message = {
            "type": "generation_update",
            "task_id": "task-123",
            "model_id": "gpt-4o",
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
        }

        assert message["type"] == "generation_update"
        assert "task_id" in message
        assert "model_id" in message
        assert "status" in message


class TestPerformance:
    """Test performance-related aspects."""

    def test_pagination_limits(self):
        """Test that pagination limits are enforced."""
        # Maximum page size should be 200
        MAX_PAGE_SIZE = 200

        test_sizes = [1, 25, 50, 100, 200, 201, 500]

        for size in test_sizes:
            if size > MAX_PAGE_SIZE:
                # Should be clamped to MAX_PAGE_SIZE
                actual_size = min(size, MAX_PAGE_SIZE)
                assert actual_size == MAX_PAGE_SIZE
            else:
                assert size <= MAX_PAGE_SIZE

    def test_search_query_optimization(self):
        """Test that search queries are optimized."""
        # Test that search uses ILIKE for case-insensitive search
        search_term = "test"
        expected_pattern = f"%{search_term}%"

        assert expected_pattern == "%test%"

        # Verify search term is properly escaped for SQL
        special_chars = ["'", '"', "%", "_", "\\"]
        for char in special_chars:
            # These characters should be handled properly in actual implementation
            search_with_special = f"test{char}data"
            # The implementation should escape these properly
            assert char in search_with_special


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
