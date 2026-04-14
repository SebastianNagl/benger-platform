"""
Comprehensive tests for the notifications router endpoints.
Tests the router architecture for notification management.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth_module.models import User
from main import app


class TestNotificationsRouter:
    """Test notifications router endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        """Create mock user for testing"""
        return User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_notifications(self):
        """Create mock notifications list"""
        from models import Notification, NotificationType

        notif1 = Mock(spec=Notification)
        notif1.id = "notif-1"
        notif1.user_id = "test-user-123"
        notif1.type = NotificationType.TASK_ASSIGNED
        notif1.title = "Task Completed"
        notif1.message = "Your annotation task has been completed"
        notif1.data = {}
        notif1.is_read = False
        notif1.created_at = datetime(2025, 1, 20, 10, 0, 0, tzinfo=timezone.utc)
        notif1.organization_id = None

        notif2 = Mock(spec=Notification)
        notif2.id = "notif-2"
        notif2.user_id = "test-user-123"
        notif2.type = NotificationType.PROJECT_UPDATED
        notif2.title = "Project Updated"
        notif2.message = "Project settings have been updated"
        notif2.data = {}
        notif2.is_read = True
        notif2.created_at = datetime(2025, 1, 19, 15, 30, 0, tzinfo=timezone.utc)
        notif2.organization_id = None

        return [notif1, notif2]

    def test_get_user_notifications_success(self, client, mock_user, mock_notifications):
        """Test getting user notifications"""
        from database import get_db
        from main import app
        from routers.notifications import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch(
            "notification_service.NotificationService.get_user_notifications"
        ) as mock_get_notifications:
            mock_get_notifications.return_value = mock_notifications

            # Override dependencies
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/api/notifications")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert isinstance(data, list)
                assert len(data) == 2
                assert data[0]["id"] == "notif-1"
                assert data[0]["is_read"] is False  # API returns 'is_read', not 'read'
                assert data[0]["type"] == "task_assigned"  # Enum value is lowercase
            finally:
                app.dependency_overrides.clear()

    def test_mark_notification_read_success(self, client, mock_user):
        """Test marking notification as read"""
        from database import get_db
        from main import app
        from routers.notifications import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch(
            "notification_service.NotificationService.mark_notification_read"
        ) as mock_mark_read:
            mock_mark_read.return_value = True

            # Override dependencies
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.post("/api/notifications/mark-read/notif-1")

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "message" in data
                assert data["message"] == "Notification marked as read"
            finally:
                app.dependency_overrides.clear()

    def test_mark_all_notifications_read_success(self, client, mock_user):
        """Test marking all notifications as read"""
        from database import get_db
        from main import app
        from routers.notifications import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("notification_service.NotificationService.mark_all_read") as mock_mark_all:
            mock_mark_all.return_value = 3  # Number of notifications marked

            # Override dependencies
            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.post("/api/notifications/mark-all-read")  # It's a POST, not PATCH

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "message" in data
                assert "3 notifications" in data["message"]
            finally:
                app.dependency_overrides.clear()

    # Delete endpoint doesn't exist in the notifications router - removing this test

    def test_get_notifications_unauthorized(self, client):
        """Test getting notifications without authentication"""
        response = client.get("/api/notifications")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.integration
class TestNotificationsRouterIntegration:
    """Integration tests for notifications router"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_notifications_endpoints_require_valid_request_format(self, client):
        """Test that notification endpoints properly validate request formats"""
        # Test with invalid notification ID format
        response = client.patch("/api/notifications/invalid-id-format/read")
        assert response.status_code in [400, 401, 404, 422]

    # test_notifications_endpoints_handle_missing_dependencies removed:
    # Accepted every status code including 500/503, testing nothing meaningful.
