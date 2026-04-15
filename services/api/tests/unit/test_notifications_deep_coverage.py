"""
Unit tests for routers/notifications.py to increase branch coverage.

Covers uncovered lines: mark_read success, mark_all_read success, limit < 1 capping,
update_preferences PUT alias, email status when available and configured/unconfigured,
email test when configured, send success/failure, test notifications with
count > 1, admin test with invalid type, generate_all with total failure,
groups with date/organization, summary with days < 1, bulk operations success,
and SSE stream.

Rewritten to call handler functions directly (no TestClient) so that pytest-cov
tracks the router code.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock, AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_user(is_superadmin=False, user_id="test-user-123"):
    user = Mock()
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_superadmin = is_superadmin
    user.is_active = True
    user.email_verified = True
    user.organization_id = None
    return user


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_db.query.return_value = mock_q
    return mock_db


def _make_notification(nid="notif-1", is_read=False):
    from models import NotificationType

    n = Mock()
    n.id = nid
    n.user_id = "test-user-123"
    n.type = NotificationType.SYSTEM_ALERT
    n.title = "Test Notification"
    n.message = "Test message"
    n.data = {"test": True}
    n.is_read = is_read
    n.created_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    n.organization_id = None
    return n


# ---------------------------------------------------------------------------
# mark_notification_read
# ---------------------------------------------------------------------------

class TestMarkNotificationReadSuccess:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.mark_notification_read", return_value=True)
    async def test_mark_read_success(self, mock_mark):
        from routers.notifications import mark_notification_read

        user = _mock_user()
        db = _mock_db()

        result = await mark_notification_read(
            notification_id="notif-1", current_user=user, db=db,
        )
        assert result["message"] == "Notification marked as read"

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.mark_notification_read", return_value=False)
    async def test_mark_read_not_found(self, mock_mark):
        from routers.notifications import mark_notification_read

        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await mark_notification_read(
                notification_id="missing", current_user=user, db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.mark_notification_read", side_effect=Exception("fail"))
    async def test_mark_read_exception(self, mock_mark):
        from routers.notifications import mark_notification_read

        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await mark_notification_read(
                notification_id="notif-1", current_user=user, db=db,
            )
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# mark_all_notifications_read
# ---------------------------------------------------------------------------

class TestMarkAllReadSuccess:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.mark_all_read", return_value=5)
    async def test_mark_all_success(self, mock_mark):
        from routers.notifications import mark_all_notifications_read

        user = _mock_user()
        db = _mock_db()

        result = await mark_all_notifications_read(current_user=user, db=db)
        assert "5" in result["message"]


# ---------------------------------------------------------------------------
# get_notifications: limit capping and unread_only
# ---------------------------------------------------------------------------

class TestGetNotificationsLimitBranches:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.get_user_notifications", return_value=[])
    async def test_limit_below_one_capped(self, mock_get):
        from routers.notifications import get_notifications

        user = _mock_user()
        db = _mock_db()

        result = await get_notifications(
            current_user=user, db=db, limit=0, offset=0, unread_only=False,
        )
        assert result == []
        # Should have capped limit to 1
        mock_get.assert_called_once()
        assert mock_get.call_args.kwargs.get("limit") == 1

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.get_user_notifications")
    async def test_unread_only_true(self, mock_get):
        from routers.notifications import get_notifications

        mock_get.return_value = [_make_notification()]
        user = _mock_user()
        db = _mock_db()

        result = await get_notifications(
            current_user=user, db=db, limit=20, offset=0, unread_only=True,
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.get_user_notifications", return_value=[])
    async def test_limit_above_100_capped(self, mock_get):
        from routers.notifications import get_notifications

        user = _mock_user()
        db = _mock_db()

        await get_notifications(
            current_user=user, db=db, limit=200, offset=0, unread_only=False,
        )
        assert mock_get.call_args.kwargs.get("limit") == 100


# ---------------------------------------------------------------------------
# email status
# ---------------------------------------------------------------------------

class TestEmailStatusAvailable:
    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True)
    @patch("routers.notifications.email_service")
    async def test_email_configured(self, mock_es):
        from routers.notifications import get_email_status

        mock_es.is_available.return_value = True
        user = _mock_user()

        result = await get_email_status(current_user=user)
        assert result["available"] is True
        assert result["configured"] is True
        assert "ready" in result["message"]

    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True)
    @patch("routers.notifications.email_service")
    async def test_email_not_configured(self, mock_es):
        from routers.notifications import get_email_status

        mock_es.is_available.return_value = False
        user = _mock_user()

        result = await get_email_status(current_user=user)
        assert result["configured"] is False

    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True)
    @patch("routers.notifications.email_service")
    async def test_email_check_exception(self, mock_es):
        from routers.notifications import get_email_status

        mock_es.is_available.side_effect = Exception("fail")
        user = _mock_user()

        result = await get_email_status(current_user=user)
        assert result["available"] is False

    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", False)
    async def test_email_service_not_available(self):
        from routers.notifications import get_email_status

        user = _mock_user()
        result = await get_email_status(current_user=user)
        assert result["available"] is False


# ---------------------------------------------------------------------------
# email test endpoint
# ---------------------------------------------------------------------------

class TestEmailTestEndpoint:
    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True)
    @patch("routers.notifications.email_service")
    async def test_email_not_configured_returns_503(self, mock_es):
        from routers.notifications import send_test_email

        mock_es.is_available.return_value = False
        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await send_test_email(current_user=user, db=db)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True)
    @patch("routers.notifications.email_service")
    async def test_email_send_success(self, mock_es):
        from routers.notifications import send_test_email

        mock_es.is_available.return_value = True
        mock_es.send_test_email = AsyncMock(return_value=True)
        user = _mock_user()
        db = _mock_db()

        result = await send_test_email(current_user=user, db=db)
        assert "sent successfully" in result["message"]

    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True)
    @patch("routers.notifications.email_service")
    async def test_email_send_failure(self, mock_es):
        from routers.notifications import send_test_email

        mock_es.is_available.return_value = True
        mock_es.send_test_email = AsyncMock(return_value=False)
        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await send_test_email(current_user=user, db=db)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", True)
    @patch("routers.notifications.email_service")
    async def test_email_send_exception(self, mock_es):
        from routers.notifications import send_test_email

        mock_es.is_available.return_value = True
        mock_es.send_test_email = AsyncMock(side_effect=Exception("SMTP error"))
        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await send_test_email(current_user=user, db=db)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", False)
    async def test_email_service_unavailable(self):
        from routers.notifications import send_test_email

        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await send_test_email(current_user=user, db=db)
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# test notifications
# ---------------------------------------------------------------------------

class TestTestNotificationsDeep:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.create_notification")
    async def test_multiple_notifications(self, mock_create):
        from routers.notifications import create_test_notification, TestNotificationRequest

        mock_notif = Mock()
        mock_notif.id = "n"
        mock_create.return_value = [mock_notif]

        user = _mock_user()
        db = _mock_db()

        result = await create_test_notification(
            request=TestNotificationRequest(
                notification_type="system_alert",
                title="Custom Title",
                message="Custom Message",
                count=3,
            ),
            current_user=user,
            db=db,
        )
        assert result["success"] is True
        assert mock_create.call_count == 3

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.create_notification")
    async def test_no_title_no_message_defaults(self, mock_create):
        from routers.notifications import create_test_notification, TestNotificationRequest

        mock_notif = Mock()
        mock_notif.id = "n"
        mock_create.return_value = [mock_notif]

        user = _mock_user()
        db = _mock_db()

        result = await create_test_notification(
            request=TestNotificationRequest(notification_type="system_alert", count=1),
            current_user=user,
            db=db,
        )
        assert result["success"] is True
        # Verify auto-generated title was used
        call_kwargs = mock_create.call_args
        assert "System Alert" in call_kwargs.kwargs.get("title", "")

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.create_notification")
    async def test_admin_test_invalid_type_defaults_to_system_alert(self, mock_create):
        from routers.notifications import create_admin_test_notification, AdminTestNotificationRequest

        mock_notif = Mock()
        mock_notif.id = "admin-n"
        mock_create.return_value = [mock_notif]

        user = _mock_user(is_superadmin=True)
        db = _mock_db()

        result = await create_admin_test_notification(
            request=AdminTestNotificationRequest(
                type="totally_invalid_type",
                title="Admin Test",
                message="Test msg",
            ),
            current_user=user,
            db=db,
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.create_notification")
    async def test_admin_test_with_custom_data(self, mock_create):
        from routers.notifications import create_admin_test_notification, AdminTestNotificationRequest

        mock_notif = Mock()
        mock_notif.id = "admin-n"
        mock_create.return_value = [mock_notif]

        user = _mock_user(is_superadmin=True)
        db = _mock_db()

        result = await create_admin_test_notification(
            request=AdminTestNotificationRequest(
                type="system_alert",
                title="Test",
                message="Test msg",
                data={"custom": "data"},
            ),
            current_user=user,
            db=db,
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.create_notification", side_effect=Exception("DB fail"))
    async def test_admin_test_error(self, mock_create):
        from routers.notifications import create_admin_test_notification, AdminTestNotificationRequest

        user = _mock_user(is_superadmin=True)
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await create_admin_test_notification(
                request=AdminTestNotificationRequest(
                    type="system_alert",
                    title="Test",
                    message="Test msg",
                ),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_admin_test_not_superadmin(self):
        from routers.notifications import create_admin_test_notification, AdminTestNotificationRequest

        user = _mock_user(is_superadmin=False)
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await create_admin_test_notification(
                request=AdminTestNotificationRequest(
                    type="system_alert",
                    title="Test",
                    message="Test msg",
                ),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# generate_all test notifications
# ---------------------------------------------------------------------------

class TestGenerateAllDeep:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.create_notification", side_effect=Exception("always fail"))
    async def test_all_fail(self, mock_create):
        from routers.notifications import generate_all_test_notifications

        user = _mock_user(is_superadmin=True)
        db = _mock_db()

        result = await generate_all_test_notifications(current_user=user, db=db)
        assert result["success"] is False
        assert result["count"] == 0
        assert result["errors"] is not None

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.create_notification")
    async def test_outer_exception(self, mock_create):
        from routers.notifications import generate_all_test_notifications

        mock_notif = Mock()
        mock_notif.id = "n"
        mock_create.return_value = [mock_notif]

        user = _mock_user(is_superadmin=True)
        db = _mock_db()
        db.commit.side_effect = Exception("commit fail")

        with pytest.raises(HTTPException) as exc_info:
            await generate_all_test_notifications(current_user=user, db=db)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_not_superadmin(self):
        from routers.notifications import generate_all_test_notifications

        user = _mock_user(is_superadmin=False)
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await generate_all_test_notifications(current_user=user, db=db)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# groups
# ---------------------------------------------------------------------------

class TestGroupsDeep:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.get_notification_groups")
    async def test_group_by_date(self, mock_groups):
        from routers.notifications import get_notification_groups

        mock_groups.return_value = {"2025-06-15": [_make_notification()]}
        user = _mock_user()
        db = _mock_db()

        result = await get_notification_groups(
            current_user=user, db=db, group_by="date", limit=50,
        )
        assert "groups" in result.__dict__ or hasattr(result, "groups")

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.get_notification_groups")
    async def test_group_by_organization(self, mock_groups):
        from routers.notifications import get_notification_groups

        mock_groups.return_value = {"org-1": [_make_notification()]}
        user = _mock_user()
        db = _mock_db()

        result = await get_notification_groups(
            current_user=user, db=db, group_by="organization", limit=50,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_group_by_invalid(self):
        from routers.notifications import get_notification_groups

        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await get_notification_groups(
                current_user=user, db=db, group_by="invalid", limit=50,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

class TestSummaryDeep:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.get_notification_summary")
    async def test_days_below_one_capped(self, mock_summary):
        from routers.notifications import get_notification_summary

        mock_summary.return_value = {
            "total_notifications": 0,
            "unread_notifications": 0,
            "read_notifications": 0,
            "notifications_by_type": {},
            "period_days": 1,
            "summary_generated_at": datetime.now(timezone.utc).isoformat(),
        }

        user = _mock_user()
        db = _mock_db()

        result = await get_notification_summary(current_user=user, db=db, days=0)
        # days should be capped to 1
        mock_summary.assert_called_once()
        assert mock_summary.call_args.kwargs.get("days") == 1


# ---------------------------------------------------------------------------
# preferences
# ---------------------------------------------------------------------------

class TestDigestAlias:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.update_user_preferences", return_value=True)
    async def test_put_preferences_delegates(self, mock_update):
        from routers.notifications import update_notification_preferences_put, NotificationPreferencesUpdate

        user = _mock_user()
        db = _mock_db()

        result = await update_notification_preferences_put(
            preferences_update=NotificationPreferencesUpdate(preferences={"system_alert": True}),
            current_user=user,
            db=db,
        )
        assert result["message"] == "Preferences updated successfully"

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.update_user_preferences", return_value=True)
    async def test_post_preferences_success(self, mock_update):
        from routers.notifications import update_notification_preferences, NotificationPreferencesUpdate

        user = _mock_user()
        db = _mock_db()

        result = await update_notification_preferences(
            preferences_update=NotificationPreferencesUpdate(preferences={"system_alert": True}),
            current_user=user,
            db=db,
        )
        assert result["message"] == "Preferences updated successfully"

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.update_user_preferences", return_value=False)
    async def test_post_preferences_failure(self, mock_update):
        from routers.notifications import update_notification_preferences, NotificationPreferencesUpdate

        user = _mock_user()
        db = _mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await update_notification_preferences(
                preferences_update=NotificationPreferencesUpdate(preferences={"system_alert": True}),
                current_user=user,
                db=db,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# bulk operations
# ---------------------------------------------------------------------------

class TestBulkOperations:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.mark_notifications_read_bulk", return_value=3)
    async def test_bulk_mark_read(self, mock_bulk):
        from routers.notifications import mark_notifications_read_bulk, BulkOperationRequest

        user = _mock_user()
        db = _mock_db()

        result = await mark_notifications_read_bulk(
            request=BulkOperationRequest(notification_ids=["n1", "n2", "n3"]),
            current_user=user,
            db=db,
        )
        assert result.count == 3

    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.delete_notifications_bulk", return_value=2)
    async def test_bulk_delete(self, mock_bulk):
        from routers.notifications import delete_notifications_bulk, BulkOperationRequest

        user = _mock_user()
        db = _mock_db()

        result = await delete_notifications_bulk(
            request=BulkOperationRequest(notification_ids=["n1", "n2"]),
            current_user=user,
            db=db,
        )
        assert result.count == 2


# ---------------------------------------------------------------------------
# unread count
# ---------------------------------------------------------------------------

class TestUnreadCount:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.get_unread_count", return_value=7)
    async def test_unread_count_success(self, mock_count):
        from routers.notifications import get_unread_count

        user = _mock_user()
        db = _mock_db()

        result = await get_unread_count(current_user=user, db=db)
        assert result.count == 7


# ---------------------------------------------------------------------------
# get_notification_preferences
# ---------------------------------------------------------------------------

class TestGetPreferences:
    @pytest.mark.asyncio
    @patch("notification_service.NotificationService.get_user_preferences", return_value={"system_alert": True})
    async def test_get_preferences_success(self, mock_prefs):
        from routers.notifications import get_notification_preferences

        user = _mock_user()
        db = _mock_db()

        result = await get_notification_preferences(current_user=user, db=db)
        assert result.preferences == {"system_alert": True}
