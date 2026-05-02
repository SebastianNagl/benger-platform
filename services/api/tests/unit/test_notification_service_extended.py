"""
Unit tests for services/email/notification_service.py — 61.38% coverage (154 uncovered lines).

Tests _user_wants_notification, get_user_notifications, get_unread_count,
mark_notification_read, mark_all_read, get_user_preferences,
update_user_preferences, cleanup, bulk operations.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestUserWantsNotification:
    """Test _user_wants_notification static method."""

    def test_no_preference_defaults_to_true(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = NotificationService._user_wants_notification(db, "user-1", "project_created")
        assert result is True

    def test_preference_enabled(self):
        from services.email.notification_service import NotificationService
        pref = MagicMock()
        pref.email_enabled = True
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = pref
        result = NotificationService._user_wants_notification(db, "user-1", "project_created")
        assert result is True

    def test_preference_disabled(self):
        from services.email.notification_service import NotificationService
        pref = MagicMock()
        pref.in_app_enabled = False
        pref.email_enabled = False
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = pref
        result = NotificationService._user_wants_notification(db, "user-1", "project_created")
        assert result is False

    def test_enum_type_converted(self):
        from models import NotificationType
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = NotificationService._user_wants_notification(
            db, "user-1", NotificationType.PROJECT_CREATED
        )
        assert result is True

    def test_invalid_type_returns_false(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        result = NotificationService._user_wants_notification(db, "user-1", 12345)
        assert result is False


class TestCreateNotification:
    """Test NotificationService.create_notification (patching async parts)."""

    def test_invalid_type_returns_empty(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        result = NotificationService.create_notification(
            db=db, user_ids=["user-1"],
            notification_type="completely_invalid_type_xyz",
            title="Test", message="Test",
        )
        assert result == []

    def test_invalid_type_object_returns_empty(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        result = NotificationService.create_notification(
            db=db, user_ids=["user-1"],
            notification_type=12345,
            title="Test", message="Test",
        )
        assert result == []

    def test_empty_user_ids_commits_nothing(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        with patch("services.email.notification_service.asyncio", MagicMock()):
            result = NotificationService.create_notification(
                db=db, user_ids=[],
                notification_type="project_created",
                title="Test", message="Test",
            )
        assert isinstance(result, list)

    def test_commit_failure_rollback(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.commit.side_effect = Exception("DB error")

        result = NotificationService.create_notification(
            db=db, user_ids=["user-1"],
            notification_type="project_created",
            title="Test", message="Test",
        )
        assert db.rollback.called
        assert result == []

    def test_user_with_disabled_preference_skipped(self):
        from services.email.notification_service import NotificationService
        pref = MagicMock()
        pref.email_enabled = False
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = pref
        with patch("services.email.notification_service.asyncio", MagicMock()):
            result = NotificationService.create_notification(
                db=db, user_ids=["user-1"],
                notification_type="project_created",
                title="Test", message="Test",
            )
        # User skipped, no notifications created, commit is empty
        assert isinstance(result, list)


class TestGetUserNotifications:
    """Test get_user_notifications."""

    def test_basic_query(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.offset.return_value = q
        q.limit.return_value = q
        q.all.return_value = []
        assert NotificationService.get_user_notifications(db, "user-1") == []

    def test_unread_only(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.offset.return_value = q
        q.limit.return_value = q
        q.all.return_value = []
        assert NotificationService.get_user_notifications(db, "user-1", unread_only=True) == []

    def test_with_pagination(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.offset.return_value = q
        q.limit.return_value = q
        q.all.return_value = ["n1", "n2"]
        result = NotificationService.get_user_notifications(db, "user-1", limit=10, offset=5)
        assert len(result) == 2


class TestGetUnreadCount:
    """Test get_unread_count."""

    def test_count(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.count.return_value = 5
        assert NotificationService.get_unread_count(db, "user-1") == 5

    def test_zero_count(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.count.return_value = 0
        assert NotificationService.get_unread_count(db, "user-1") == 0


class TestMarkNotificationRead:
    """Test mark_notification_read."""

    def test_existing_notification(self):
        from services.email.notification_service import NotificationService
        notification = MagicMock()
        notification.is_read = False
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = notification
        result = NotificationService.mark_notification_read(db, "notif-1", "user-1")
        assert result is True
        assert notification.is_read is True

    def test_nonexistent_notification(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = NotificationService.mark_notification_read(db, "notif-1", "user-1")
        assert result is False


class TestMarkAllRead:
    """Test mark_all_read."""

    def test_marks_all(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.update.return_value = 3
        result = NotificationService.mark_all_read(db, "user-1")
        assert result == 3
        assert db.commit.called


class TestGetUserPreferences:
    """Test get_user_preferences."""

    def test_returns_defaults_when_no_prefs(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        result = NotificationService.get_user_preferences(db, "user-1")
        # Returns defaults for all notification types: per-channel shape, all on
        assert isinstance(result, dict)
        assert len(result) > 0
        assert all(
            v == {"enabled": True, "in_app": True, "email": True}
            for v in result.values()
        )

    def test_returns_overridden_prefs(self):
        from services.email.notification_service import NotificationService
        pref1 = MagicMock()
        pref1.notification_type = "project_created"
        pref1.in_app_enabled = False
        pref1.email_enabled = False
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [pref1]
        result = NotificationService.get_user_preferences(db, "user-1")
        assert result["project_created"] == {
            "enabled": False,
            "in_app": False,
            "email": False,
        }


class TestUpdateUserPreferences:
    """Test update_user_preferences."""

    def test_update_existing(self):
        from services.email.notification_service import NotificationService
        existing_pref = MagicMock()
        existing_pref.email_enabled = True
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing_pref
        result = NotificationService.update_user_preferences(
            db, "user-1", {"project_created": False}
        )
        assert result is True

    def test_create_new_preference(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = NotificationService.update_user_preferences(
            db, "user-1", {"project_created": True}
        )
        assert result is True
        assert db.add.called


class TestCleanupNotifications:
    """Test cleanup_notifications."""

    def test_cleanup_deletes_old(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 10
        result = NotificationService.cleanup_notifications(db, older_than_days=30)
        assert result == 10
        assert db.commit.called

    def test_cleanup_custom_days(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 5
        result = NotificationService.cleanup_notifications(db, older_than_days=7)
        assert result == 5


class TestMarkNotificationsReadBulk:
    """Test mark_notifications_read_bulk."""

    def test_bulk_mark(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.update.return_value = 3
        result = NotificationService.mark_notifications_read_bulk(
            db, "user-1", ["n1", "n2", "n3"]
        )
        assert result == 3
        assert db.commit.called


class TestDeleteNotificationsBulk:
    """Test delete_notifications_bulk."""

    def test_bulk_delete(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 2
        result = NotificationService.delete_notifications_bulk(
            db, "user-1", ["n1", "n2"]
        )
        assert result == 2


class TestGetNotificationSummary:
    """Test get_notification_summary."""

    def test_summary_structure(self):
        from services.email.notification_service import NotificationService
        db = MagicMock()
        db.query.return_value.filter.return_value.count.return_value = 10
        db.query.return_value.filter.return_value.all.return_value = []
        result = NotificationService.get_notification_summary(db, "user-1", days=7)
        assert isinstance(result, dict)
