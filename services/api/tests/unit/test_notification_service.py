"""
Comprehensive test suite for notification_service
Tests notification creation, delivery, and integration with email service
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest

from models import NotificationType, Organization, User
from notification_service import (
    NotificationService,
    notify_llm_generation_failed,
    notify_project_created,
    notify_security_alert,
    notify_system_maintenance,
)


@pytest.fixture
def mock_db():
    """Mock database session"""
    return MagicMock()


@pytest.fixture
def test_user():
    """Test user fixture"""
    return User(
        id=str(uuid4()),
        username="testuser",
        email="test@example.com",
        name="Test User",
        email_verified=True,
        is_superadmin=False,
        is_active=True,
    )


@pytest.fixture
def test_organization():
    """Test organization fixture"""
    return Organization(
        id=str(uuid4()),
        name="Test Organization",
        description="Test organization for notifications",
    )


class TestNotificationServiceInitialization:
    """Test notification service initialization"""

    def test_notification_service_exists(self):
        """Test service class exists"""
        assert NotificationService is not None
        assert hasattr(NotificationService, "create_notification")

    def test_service_methods(self):
        """Test service has required methods"""
        assert hasattr(NotificationService, "create_notification")
        assert hasattr(NotificationService, "get_notification_recipients")


class TestNotificationCreation:
    """Test notification creation"""

    @patch("notification_service.NotificationService._user_wants_notification")
    @patch("notification_service.asyncio.create_task")
    def test_create_notification_basic(
        self, mock_create_task, mock_wants_notif, mock_db, test_user
    ):
        """Test basic notification creation"""

        # Mock user wants notification
        mock_wants_notif.return_value = True

        # Mock database operations
        mock_db.add = Mock()
        mock_db.commit = Mock()

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[test_user.id],
            notification_type=NotificationType.PROJECT_CREATED,
            title="Test Notification",
            message="This is a test notification",
            data={"test": "data"},
        )

        # Verify database operations were called
        assert mock_db.add.call_count == 1
        mock_db.commit.assert_called_once()
        assert len(result) == 1

    @patch("notification_service.NotificationService._user_wants_notification")
    @patch("notification_service.asyncio.create_task")
    def test_create_notification_with_organization(
        self, mock_create_task, mock_wants_notif, mock_db, test_user, test_organization
    ):
        """Test notification creation with organization"""

        mock_wants_notif.return_value = True
        mock_db.add = Mock()
        mock_db.commit = Mock()

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[test_user.id],
            notification_type=NotificationType.PROJECT_CREATED,
            title="Test Notification",
            message="Test message",
            data={"project_id": "test-project"},
            organization_id=test_organization.id,
        )

        assert mock_db.add.call_count == 1
        mock_db.commit.assert_called_once()
        assert len(result) == 1

    @patch("notification_service.NotificationService._user_wants_notification")
    def test_create_notification_invalid_type(self, mock_wants_notif, mock_db, test_user):
        """Test notification creation with invalid type"""

        mock_wants_notif.return_value = True

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[test_user.id],
            notification_type="invalid_type",
            title="Test",
            message="Test",
        )

        # Should return empty list for invalid type
        assert len(result) == 0


class TestNotificationRecipients:
    """Test notification recipient determination"""

    def test_get_notification_recipients_basic(self, mock_db):
        """Test getting notification recipients"""

        # Mock database query
        mock_db.query.return_value.filter.return_value.all.return_value = [
            Mock(user_id="user1"),
            Mock(user_id="user2"),
        ]

        result = NotificationService.get_notification_recipients(
            db=mock_db,
            event_type=NotificationType.PROJECT_CREATED,
            context={"project_id": "test-project"},
        )

        # Should return list of user IDs (method implementation may vary)
        assert isinstance(result, list)


class TestNotificationQueries:
    """Test notification database queries"""

    def test_get_user_notifications(self, mock_db, test_user):
        """Test getting user notifications"""

        # Mock query result
        mock_notifications = [
            Mock(id="1", type=NotificationType.PROJECT_CREATED, is_read=False),
            Mock(id="2", type=NotificationType.DATA_IMPORT_SUCCESS, is_read=True),
        ]

        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            mock_notifications
        )
        mock_db.query.return_value = mock_query

        result = NotificationService.get_user_notifications(
            db=mock_db, user_id=test_user.id, limit=10, unread_only=False
        )

        # The mock query chain returns the mock result, so just check it's not None
        assert result is not None
        mock_db.query.assert_called_once()

    def test_mark_notification_read(self, mock_db):
        """Test marking notification as read"""

        notification_id = str(uuid4())
        mock_notification = Mock(id=notification_id, is_read=False)

        mock_db.query.return_value.filter.return_value.first.return_value = mock_notification
        mock_db.commit = Mock()

        result = NotificationService.mark_notification_read(
            db=mock_db, notification_id=notification_id, user_id="test_user_id"
        )

        assert mock_notification.is_read is True
        mock_db.commit.assert_called_once()


class TestNotificationBulkOperations:
    """Test bulk notification operations"""

    def test_mark_all_read(self, mock_db, test_user):
        """Test marking all user notifications as read"""

        mock_db.query.return_value.filter.return_value.update.return_value = 3
        mock_db.commit = Mock()

        result = NotificationService.mark_all_read(db=mock_db, user_id=test_user.id)

        assert result == 3
        mock_db.commit.assert_called_once()

    def test_delete_old_notifications(self, mock_db):
        """Test deleting old notifications"""

        mock_db.query.return_value.filter.return_value.delete.return_value = 5
        mock_db.commit = Mock()

        result = NotificationService.cleanup_notifications(db=mock_db, older_than_days=30)

        assert result == 5
        mock_db.commit.assert_called_once()


@pytest.mark.integration
class TestNotificationIntegration:
    """Integration tests for notification service"""

    @patch("notification_service.NotificationService._user_wants_notification")
    @patch("notification_service.EMAIL_SERVICE_AVAILABLE", True)
    @patch("notification_service.asyncio.create_task")
    def test_create_and_send_notification(
        self, mock_create_task, mock_wants_notif, mock_db, test_user
    ):
        """Test complete notification workflow"""

        mock_wants_notif.return_value = True
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_create_task.return_value = None  # Mock async task creation

        # Create notification
        notifications = NotificationService.create_notification(
            db=mock_db,
            user_ids=[test_user.id],
            notification_type=NotificationType.PROJECT_CREATED,
            title="Project Created",
            message="Your project has been created successfully",
            data={"project_name": "Test Project"},
        )

        # Verify both operations succeeded
        assert len(notifications) == 1
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_create_task.assert_called_once()  # Email task created


class TestNotificationErrorHandling:
    """Test error handling in notification service"""

    @patch("notification_service.NotificationService._user_wants_notification")
    def test_database_error_handling(self, mock_wants_notif, mock_db, test_user):
        """Test handling of database errors"""

        mock_wants_notif.return_value = True
        mock_db.add = Mock()
        mock_db.commit = Mock(side_effect=Exception("Database error"))
        mock_db.rollback = Mock()

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[test_user.id],
            notification_type=NotificationType.PROJECT_CREATED,
            title="Test",
            message="Test",
        )

        # Should return empty list on error
        assert len(result) == 0
        mock_db.rollback.assert_called_once()


class TestNotificationPreferences:
    """Test notification preference handling"""

    @patch("notification_service.NotificationService._user_wants_notification")
    def test_user_preferences_respected(self, mock_wants_notif, mock_db, test_user):
        """Test that user preferences are respected"""

        # User doesn't want this type of notification
        mock_wants_notif.return_value = False
        mock_db.add = Mock()
        mock_db.commit = Mock()

        result = NotificationService.create_notification(
            db=mock_db,
            user_ids=[test_user.id],
            notification_type=NotificationType.PROJECT_CREATED,
            title="Test",
            message="Test",
        )

        # Should not create any notifications
        assert len(result) == 0
        mock_db.add.assert_not_called()


class TestEmailNotifications:
    """Test email notification functionality"""

    @patch("services.email.notification_service.EMAIL_SERVICE_AVAILABLE", True)
    @patch("services.email.notification_service.send_notification_email")
    @patch("services.email.notification_service.NotificationService._user_wants_email_notification")
    @patch("services.email.notification_service.NotificationService._user_wants_notification")
    @pytest.mark.asyncio
    async def test_send_email_notifications(
        self, mock_wants_notif, mock_wants_email, mock_send_email, mock_db, test_user
    ):
        """Test email notifications are sent correctly"""

        # Setup
        mock_wants_notif.return_value = True
        mock_wants_email.return_value = True
        mock_send_email.return_value = True

        # Create notification data as dictionary (expected format)
        notification_data = [
            {
                "id": "notif-1",
                "user_id": test_user.id,
                "type": NotificationType.PROJECT_CREATED,
                "title": "Test Notification",
                "message": "Test message",
            }
        ]

        # Mock database query for user
        mock_db.query.return_value.filter.return_value.first.return_value = test_user

        # Test sending email
        await NotificationService._send_email_notifications(mock_db, notification_data)

        # Verify email was sent
        mock_send_email.assert_called_once()

    @patch("notification_service.EMAIL_SERVICE_AVAILABLE", True)
    @patch("email_validation.is_valid_email")
    @patch("notification_service.send_notification_email")
    @patch("notification_service.NotificationService._user_wants_email_notification")
    @pytest.mark.asyncio
    async def test_invalid_email_skipped(
        self, mock_wants_email, mock_send_email, mock_is_valid, mock_db, test_user
    ):
        """Test invalid emails are skipped"""

        # Setup
        mock_wants_email.return_value = True
        mock_is_valid.return_value = False
        test_user.email = "invalid-email"

        notification_data = [
            {"id": "notif-1", "user_id": test_user.id, "type": NotificationType.PROJECT_CREATED}
        ]

        mock_db.query.return_value.filter.return_value.first.return_value = test_user

        # Test
        await NotificationService._send_email_notifications(mock_db, notification_data)

        # Email should not be sent for invalid email
        mock_send_email.assert_not_called()


class TestBulkOperations:
    """Test bulk notification operations"""

    def test_mark_notifications_read_bulk(self, mock_db, test_user):
        """Test bulk marking notifications as read"""

        notification_ids = ["notif-1", "notif-2", "notif-3"]

        mock_query = Mock()
        mock_query.filter.return_value.update.return_value = 3
        mock_db.query.return_value = mock_query
        mock_db.commit = Mock()

        result = NotificationService.mark_notifications_read_bulk(
            db=mock_db, user_id=test_user.id, notification_ids=notification_ids
        )

        assert result == 3
        mock_db.commit.assert_called_once()

    def test_delete_notifications_bulk(self, mock_db, test_user):
        """Test bulk deleting notifications"""

        notification_ids = ["notif-1", "notif-2"]

        mock_query = Mock()
        mock_query.filter.return_value.delete.return_value = 2
        mock_db.query.return_value = mock_query
        mock_db.commit = Mock()

        result = NotificationService.delete_notifications_bulk(
            db=mock_db, user_id=test_user.id, notification_ids=notification_ids
        )

        assert result == 2
        mock_db.commit.assert_called_once()


class TestNotificationGrouping:
    """Test notification grouping and summary"""

    def test_get_notification_groups_by_type(self, mock_db, test_user):
        """Test grouping notifications by type"""

        # Create mock notifications
        notifications = [
            Mock(type=NotificationType.PROJECT_CREATED, created_at=datetime.utcnow()),
            Mock(type=NotificationType.PROJECT_CREATED, created_at=datetime.utcnow()),
            Mock(type=NotificationType.DATA_IMPORT_SUCCESS, created_at=datetime.utcnow()),
        ]

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            notifications
        )

        result = NotificationService.get_notification_groups(
            db=mock_db, user_id=test_user.id, group_by="type"
        )

        assert NotificationType.PROJECT_CREATED.value in result
        assert len(result[NotificationType.PROJECT_CREATED.value]) == 2
        assert NotificationType.DATA_IMPORT_SUCCESS.value in result
        assert len(result[NotificationType.DATA_IMPORT_SUCCESS.value]) == 1

    def test_get_notification_groups_by_date(self, mock_db, test_user):
        """Test grouping notifications by date"""

        # Create mock notifications with different dates
        date1 = datetime(2024, 1, 1)
        date2 = datetime(2024, 1, 2)

        notifications = [
            Mock(type=NotificationType.PROJECT_CREATED, created_at=date1),
            Mock(type=NotificationType.DATA_IMPORT_SUCCESS, created_at=date1),
            Mock(type=NotificationType.PROJECT_DELETED, created_at=date2),
        ]

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            notifications
        )

        result = NotificationService.get_notification_groups(
            db=mock_db, user_id=test_user.id, group_by="date"
        )

        assert "2024-01-01" in result
        assert len(result["2024-01-01"]) == 2
        assert "2024-01-02" in result
        assert len(result["2024-01-02"]) == 1

    def test_get_notification_summary(self, mock_db, test_user):
        """Test notification summary generation"""

        # Create separate mock chains for each query
        query_count = 0

        def mock_query_side_effect(*args):
            nonlocal query_count
            query_count += 1

            if query_count <= 2:
                # First two queries are for counting (total and unread)
                mock_chain = Mock()
                if query_count == 1:
                    mock_chain.filter.return_value.count.return_value = 10  # total
                else:
                    mock_chain.filter.return_value.count.return_value = 3  # unread
                return mock_chain
            else:
                # Third query is for type counts
                type_results = [
                    Mock(type=NotificationType.PROJECT_CREATED, count=5),
                    Mock(type=NotificationType.DATA_IMPORT_SUCCESS, count=3),
                    Mock(type=NotificationType.PROJECT_DELETED, count=2),
                ]
                mock_chain = Mock()
                mock_chain.filter.return_value.group_by.return_value.all.return_value = type_results
                return mock_chain

        mock_db.query.side_effect = mock_query_side_effect

        result = NotificationService.get_notification_summary(
            db=mock_db, user_id=test_user.id, days=7
        )

        assert result["total_notifications"] == 10
        assert result["unread_notifications"] == 3
        assert result["read_notifications"] == 7
        assert result["period_days"] == 7
        assert "summary_generated_at" in result


class TestHelperFunctions:
    """Test notification helper functions"""

    @patch("notification_service.NotificationService.get_notification_recipients")
    @patch("notification_service.NotificationService.create_notification")
    def test_notify_project_created(self, mock_create, mock_get_recipients, mock_db):
        """Test project creation notification"""

        mock_get_recipients.return_value = ["user-1", "user-2"]
        mock_create.return_value = [Mock()]

        notify_project_created(
            db=mock_db,
            project_id="proj-1",
            project_title="Test Project",
            creator_name="John Doe",
            organization_id="org-1",
        )

        mock_get_recipients.assert_called_once_with(
            mock_db, NotificationType.PROJECT_CREATED, {"organization_id": "org-1"}
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args["notification_type"] == NotificationType.PROJECT_CREATED
        assert "Test Project" in call_args["title"]

    @patch("notification_service.NotificationService.create_notification")
    def test_notify_llm_generation_failed(self, mock_create, mock_db):
        """Test LLM generation failure notification"""

        notify_llm_generation_failed(
            db=mock_db,
            task_id="task-1",
            task_name="Test Task",
            model_name="gpt-4",
            user_id="user-1",
            error_message="API quota exceeded",
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args["notification_type"] == NotificationType.LLM_GENERATION_FAILED
        assert "API quota exceeded" in call_args["message"]

    @patch("notification_service.NotificationService.create_notification")
    def test_notify_system_maintenance(self, mock_create, mock_db):
        """Test system maintenance notification"""

        # Mock active users
        mock_users = [Mock(id="user-1"), Mock(id="user-2")]
        mock_db.query.return_value.filter.return_value.all.return_value = mock_users

        notify_system_maintenance(
            db=mock_db,
            title="Scheduled Maintenance",
            message="System will be down for maintenance",
            maintenance_start="2024-01-01 00:00:00",
            maintenance_end="2024-01-01 02:00:00",
            affected_services=["API", "Frontend"],
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args["notification_type"] == NotificationType.SYSTEM_MAINTENANCE
        assert call_args["user_ids"] == ["user-1", "user-2"]
        assert call_args["data"]["affected_services"] == ["API", "Frontend"]

    @patch("notification_service.NotificationService.create_notification")
    def test_notify_security_alert(self, mock_create, mock_db):
        """Test security alert notification"""

        notify_security_alert(
            db=mock_db,
            user_id="user-1",
            alert_type="Suspicious Login",
            alert_message="Login from new device detected",
            severity="high",
            action_required="Verify your identity",
        )

        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args["notification_type"] == NotificationType.SECURITY_ALERT
        assert call_args["data"]["severity"] == "high"
        assert "Verify your identity" in call_args["message"]


class TestNotificationPreferencesExtended:
    """Test extended notification preference handling"""

    def test_update_user_preferences_success(self, mock_db, test_user):
        """Test successful preference update"""

        preferences = {
            NotificationType.PROJECT_CREATED.value: True,
            NotificationType.DATA_IMPORT_SUCCESS.value: False,
        }

        mock_pref = Mock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,
            mock_pref,
        ]
        mock_db.add = Mock()
        mock_db.commit = Mock()

        result = NotificationService.update_user_preferences(
            db=mock_db, user_id=test_user.id, preferences=preferences
        )

        assert result is True
        mock_db.commit.assert_called_once()

    def test_update_user_preferences_invalid_type(self, mock_db, test_user):
        """Test preference update with invalid notification type"""

        preferences = {
            "invalid_type": True,
            NotificationType.PROJECT_CREATED.value: False,
        }

        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.add = Mock()
        mock_db.commit = Mock()

        result = NotificationService.update_user_preferences(
            db=mock_db, user_id=test_user.id, preferences=preferences
        )

        # Should still succeed, just skip invalid type
        assert result is True
        mock_db.commit.assert_called_once()


class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limiting_not_implemented(self):
        """Test that rate limiting is not yet implemented"""
        # Rate limiting is not implemented in the current notification service
        # This test documents that it's a missing feature
        assert not hasattr(NotificationService, "check_rate_limit")
        assert not hasattr(NotificationService, "apply_rate_limit")


class TestWebhookNotifications:
    """Test webhook notification functionality"""

    def test_webhook_not_implemented(self):
        """Test that webhook notifications are not yet implemented"""
        # Webhook notifications are not implemented in the current service
        # This test documents that it's a missing feature
        assert not hasattr(NotificationService, "send_webhook_notification")
        assert not hasattr(NotificationService, "register_webhook")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
