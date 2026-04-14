"""Tests for post-annotation questionnaire endpoints (Issue #1208)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app

# Patch access checks for all questionnaire tests — these test questionnaire logic, not access control
_patch_access = patch(
    'routers.projects.questionnaire.check_project_accessible', return_value=True
)
_patch_assignment = patch(
    'routers.projects.questionnaire.check_task_assigned_to_user', return_value=True
)
_patch_edit = patch(
    'routers.projects.questionnaire.check_user_can_edit_project', return_value=True
)


class TestQuestionnaireEndpoints:
    """Test questionnaire endpoints at /api/projects/{pid}/tasks/{tid}/questionnaire-response"""

    @pytest.fixture(autouse=True)
    def patch_access_check(self):
        with _patch_access, _patch_assignment, _patch_edit:
            yield

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        user = Mock()
        user.id = "user-123"
        user.username = "annotator"
        user.email = "annotator@example.com"
        user.is_superadmin = False
        user.is_active = True
        user.email_verified = True
        return user

    @pytest.fixture
    def mock_superadmin(self):
        user = Mock()
        user.id = "admin-123"
        user.username = "admin"
        user.email = "admin@example.com"
        user.is_superadmin = True
        user.is_active = True
        user.email_verified = True
        return user

    @pytest.fixture
    def mock_project(self):
        project = Mock()
        project.id = "project-1"
        project.questionnaire_enabled = True
        project.created_by = "admin-123"
        return project

    @pytest.fixture
    def mock_project_no_questionnaire(self):
        project = Mock()
        project.id = "project-2"
        project.questionnaire_enabled = False
        project.created_by = "admin-123"
        return project

    @pytest.fixture
    def mock_task(self):
        task = Mock()
        task.id = "task-1"
        task.project_id = "project-1"
        return task

    @pytest.fixture
    def mock_annotation(self):
        annotation = Mock()
        annotation.id = "annotation-1"
        annotation.task_id = "task-1"
        annotation.completed_by = "user-123"
        return annotation

    def test_submit_questionnaire_success(self, client, mock_user, mock_project, mock_task, mock_annotation):
        """Submit succeeds with valid data."""
        from auth_module import require_user
        from database import get_db

        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        project_filter = MagicMock()
        project_filter.first.return_value = mock_project
        task_filter = MagicMock()
        task_filter.first.return_value = mock_task
        annotation_filter = MagicMock()
        annotation_filter.first.return_value = mock_annotation
        existing_filter = MagicMock()
        existing_filter.first.return_value = None  # No duplicate

        mock_query.filter.side_effect = [project_filter, task_filter, annotation_filter, existing_filter]

        # Mock refresh to set required fields on the saved object
        def mock_refresh(obj):
            obj.id = "response-1"
            obj.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = mock_refresh

        def override_get_db():
            yield mock_db

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.post(
                "/api/projects/project-1/tasks/task-1/questionnaire-response",
                json={
                    "annotation_id": "annotation-1",
                    "result": [{"from_name": "q1", "to_name": "q1", "type": "choices", "value": {"choices": ["yes"]}}],
                },
            )
            assert response.status_code == status.HTTP_200_OK
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    def test_submit_duplicate_rejected(self, client, mock_user, mock_project, mock_task, mock_annotation):
        """Duplicate responses rejected (400)."""
        from auth_module import require_user
        from database import get_db

        existing_response = Mock()
        existing_response.id = "existing-resp"

        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        project_filter = MagicMock()
        project_filter.first.return_value = mock_project
        task_filter = MagicMock()
        task_filter.first.return_value = mock_task
        annotation_filter = MagicMock()
        annotation_filter.first.return_value = mock_annotation
        existing_filter = MagicMock()
        existing_filter.first.return_value = existing_response  # Duplicate exists

        mock_query.filter.side_effect = [project_filter, task_filter, annotation_filter, existing_filter]

        def override_get_db():
            yield mock_db

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.post(
                "/api/projects/project-1/tasks/task-1/questionnaire-response",
                json={
                    "annotation_id": "annotation-1",
                    "result": [{"from_name": "q1", "to_name": "q1", "type": "choices", "value": {"choices": ["yes"]}}],
                },
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "already submitted" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_submit_disabled_questionnaire_rejected(
        self, client, mock_user, mock_project_no_questionnaire, mock_task
    ):
        """Disabled questionnaire rejected (400)."""
        from auth_module import require_user
        from database import get_db

        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        project_filter = MagicMock()
        project_filter.first.return_value = mock_project_no_questionnaire

        mock_query.filter.return_value = project_filter

        def override_get_db():
            yield mock_db

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.post(
                "/api/projects/project-2/tasks/task-1/questionnaire-response",
                json={
                    "annotation_id": "annotation-1",
                    "result": [{"from_name": "q1", "to_name": "q1", "type": "choices", "value": {"choices": ["yes"]}}],
                },
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "not enabled" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_submit_nonexistent_annotation_rejected(self, client, mock_user, mock_project, mock_task):
        """Non-existent annotation rejected (404)."""
        from auth_module import require_user
        from database import get_db

        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        project_filter = MagicMock()
        project_filter.first.return_value = mock_project
        task_filter = MagicMock()
        task_filter.first.return_value = mock_task
        annotation_filter = MagicMock()
        annotation_filter.first.return_value = None  # Not found

        mock_query.filter.side_effect = [project_filter, task_filter, annotation_filter]

        def override_get_db():
            yield mock_db

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.post(
                "/api/projects/project-1/tasks/task-1/questionnaire-response",
                json={
                    "annotation_id": "nonexistent",
                    "result": [{"from_name": "q1", "to_name": "q1", "type": "choices", "value": {"choices": ["yes"]}}],
                },
            )
            assert response.status_code == status.HTTP_404_NOT_FOUND
        finally:
            app.dependency_overrides.clear()

    def test_list_responses_permission_creator(self, client, mock_project):
        """Project creator can list questionnaire responses."""
        from auth_module import require_user
        from database import get_db

        creator = Mock()
        creator.id = "admin-123"  # Same as project.created_by
        creator.is_superadmin = False

        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        project_filter = MagicMock()
        project_filter.first.return_value = mock_project

        responses_query = MagicMock()
        responses_query.order_by.return_value = responses_query
        responses_query.all.return_value = []

        mock_query.filter.side_effect = [project_filter, responses_query]

        def override_get_db():
            yield mock_db

        app.dependency_overrides[require_user] = lambda: creator
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/projects/project-1/questionnaire-responses")
            assert response.status_code == status.HTTP_200_OK
        finally:
            app.dependency_overrides.clear()

    def test_list_responses_permission_superadmin(self, client, mock_project, mock_superadmin):
        """Superadmin can list questionnaire responses."""
        from auth_module import require_user
        from database import get_db

        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        project_filter = MagicMock()
        project_filter.first.return_value = mock_project

        responses_query = MagicMock()
        responses_query.order_by.return_value = responses_query
        responses_query.all.return_value = []

        mock_query.filter.side_effect = [project_filter, responses_query]

        def override_get_db():
            yield mock_db

        app.dependency_overrides[require_user] = lambda: mock_superadmin
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/api/projects/project-1/questionnaire-responses")
            assert response.status_code == status.HTTP_200_OK
        finally:
            app.dependency_overrides.clear()

    def test_list_responses_permission_denied(self, client, mock_user, mock_project):
        """Non-creator, non-superadmin, non-contributor gets 403."""
        from auth_module import require_user
        from database import get_db

        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        project_filter = MagicMock()
        project_filter.first.return_value = mock_project

        mock_query.filter.return_value = project_filter

        def override_get_db():
            yield mock_db

        # mock_user.id is "user-123", project.created_by is "admin-123" → denied
        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Override the edit check to deny (this user has no org role)
            with patch('routers.projects.questionnaire.check_user_can_edit_project', return_value=False):
                response = client.get("/api/projects/project-1/questionnaire-responses")
                assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()
