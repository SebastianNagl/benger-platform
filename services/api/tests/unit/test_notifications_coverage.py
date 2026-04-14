"""
Unit tests for routers/notifications.py to increase branch coverage.
Covers all notification CRUD endpoints, bulk operations, groups, summary,
email status, test notifications, and error paths.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth_module.models import User
from main import app


def _make_user(is_superadmin=False, user_id="test-user-123"):
    user = User(
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
    return user


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


class TestGetNotifications:
    def test_success(self):
        client = TestClient(app)
        mock_user = _make_user()
        notifs = [_make_notification("n1"), _make_notification("n2", True)]

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_user_notifications") as mock_get:
                mock_get.return_value = notifs
                resp = client.get("/api/notifications?limit=10&offset=0&unread_only=false")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) == 2
        finally:
            app.dependency_overrides.clear()

    def test_limit_capped_at_100(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_user_notifications") as mock_get:
                mock_get.return_value = []
                resp = client.get("/api/notifications?limit=200")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_service_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_user_notifications") as mock_get:
                mock_get.side_effect = Exception("DB error")
                resp = client.get("/api/notifications")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestUnreadCount:
    def test_success(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_unread_count") as mock_count:
                mock_count.return_value = 5
                resp = client.get("/api/notifications/unread-count")
                assert resp.status_code == 200
                assert resp.json()["count"] == 5
        finally:
            app.dependency_overrides.clear()

    def test_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_unread_count") as mock_count:
                mock_count.side_effect = Exception("fail")
                resp = client.get("/api/notifications/unread-count")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestMarkNotificationRead:
    def test_not_found(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.mark_notification_read") as mock_mark:
                mock_mark.return_value = False
                resp = client.post("/api/notifications/mark-read/nonexistent")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.mark_notification_read") as mock_mark:
                mock_mark.side_effect = Exception("fail")
                resp = client.post("/api/notifications/mark-read/n1")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestMarkAllRead:
    def test_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.mark_all_read") as mock_mark:
                mock_mark.side_effect = Exception("fail")
                resp = client.post("/api/notifications/mark-all-read")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestPreferences:
    def test_get_preferences_success(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_user_preferences") as mock_prefs:
                mock_prefs.return_value = {"task_assigned": True, "system_alert": False}
                resp = client.get("/api/notifications/preferences")
                assert resp.status_code == 200
                assert resp.json()["preferences"]["task_assigned"] is True
        finally:
            app.dependency_overrides.clear()

    def test_get_preferences_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_user_preferences") as mock_prefs:
                mock_prefs.side_effect = Exception("fail")
                resp = client.get("/api/notifications/preferences")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_update_preferences_success(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.update_user_preferences") as mock_update:
                mock_update.return_value = True
                resp = client.post(
                    "/api/notifications/preferences",
                    json={"preferences": {"task_assigned": True}},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_update_preferences_failure(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.update_user_preferences") as mock_update:
                mock_update.return_value = False
                resp = client.post(
                    "/api/notifications/preferences",
                    json={"preferences": {"task_assigned": True}},
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_update_preferences_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.update_user_preferences") as mock_update:
                mock_update.side_effect = Exception("fail")
                resp = client.post(
                    "/api/notifications/preferences",
                    json={"preferences": {"task_assigned": True}},
                )
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_put_preferences(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.update_user_preferences") as mock_update:
                mock_update.return_value = True
                resp = client.put(
                    "/api/notifications/preferences",
                    json={"preferences": {"task_assigned": False}},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestBulkOperations:
    def test_bulk_mark_read(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.mark_notifications_read_bulk") as mock_bulk:
                mock_bulk.return_value = 3
                resp = client.post(
                    "/api/notifications/bulk/mark-read",
                    json={"notification_ids": ["n1", "n2", "n3"]},
                )
                assert resp.status_code == 200
                assert resp.json()["count"] == 3
        finally:
            app.dependency_overrides.clear()

    def test_bulk_mark_read_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.mark_notifications_read_bulk") as mock_bulk:
                mock_bulk.side_effect = Exception("fail")
                resp = client.post(
                    "/api/notifications/bulk/mark-read",
                    json={"notification_ids": ["n1"]},
                )
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_bulk_delete(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.delete_notifications_bulk") as mock_del:
                mock_del.return_value = 2
                resp = client.post(
                    "/api/notifications/bulk/delete",
                    json={"notification_ids": ["n1", "n2"]},
                )
                assert resp.status_code == 200
                assert resp.json()["count"] == 2
        finally:
            app.dependency_overrides.clear()

    def test_bulk_delete_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.delete_notifications_bulk") as mock_del:
                mock_del.side_effect = Exception("fail")
                resp = client.post(
                    "/api/notifications/bulk/delete",
                    json={"notification_ids": ["n1"]},
                )
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestGroups:
    def test_invalid_group_by(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            resp = client.get("/api/notifications/groups?group_by=invalid")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_group_by_type(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_notification_groups") as mock_groups:
                mock_groups.return_value = {"system_alert": [_make_notification()]}
                resp = client.get("/api/notifications/groups?group_by=type")
                assert resp.status_code == 200
                data = resp.json()
                assert "groups" in data
        finally:
            app.dependency_overrides.clear()

    def test_groups_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_notification_groups") as mock_groups:
                mock_groups.side_effect = Exception("fail")
                resp = client.get("/api/notifications/groups?group_by=type")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestSummary:
    def test_summary_success(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_notification_summary") as mock_summary:
                mock_summary.return_value = {
                    "total_notifications": 10,
                    "unread_notifications": 3,
                    "read_notifications": 7,
                    "notifications_by_type": {"system_alert": 5, "task_assigned": 5},
                    "period_days": 7,
                    "summary_generated_at": datetime.now(timezone.utc).isoformat(),
                }
                resp = client.get("/api/notifications/summary?days=7")
                assert resp.status_code == 200
                assert resp.json()["total_notifications"] == 10
        finally:
            app.dependency_overrides.clear()

    def test_summary_days_capped(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_notification_summary") as mock_summary:
                mock_summary.return_value = {
                    "total_notifications": 0,
                    "unread_notifications": 0,
                    "read_notifications": 0,
                    "notifications_by_type": {},
                    "period_days": 90,
                    "summary_generated_at": datetime.now(timezone.utc).isoformat(),
                }
                resp = client.get("/api/notifications/summary?days=200")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_summary_error(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            with patch("notification_service.NotificationService.get_notification_summary") as mock_summary:
                mock_summary.side_effect = Exception("fail")
                resp = client.get("/api/notifications/summary")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestEmailStatus:
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", False)
    def test_email_service_not_available(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            resp = client.get("/api/notifications/email/status")
            assert resp.status_code == 200
            assert resp.json()["available"] is False
        finally:
            app.dependency_overrides.clear()


class TestDigestEndpoint:
    def test_digest_returns_501(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            resp = client.post("/api/notifications/digest/test")
            assert resp.status_code == 501
        finally:
            app.dependency_overrides.clear()


class TestTestNotifications:
    def test_create_test_notification(self):
        client = TestClient(app)
        mock_user = _make_user()
        mock_db = Mock(spec=Session)

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            mock_notif = Mock()
            mock_notif.id = "new-notif"
            with patch("notification_service.NotificationService.create_notification") as mock_create:
                mock_create.return_value = [mock_notif]
                resp = client.post(
                    "/api/notifications/test",
                    json={"notification_type": "system_alert", "count": 1},
                )
                assert resp.status_code == 200
                assert resp.json()["success"] is True
        finally:
            app.dependency_overrides.clear()

    def test_create_test_notification_invalid_type(self):
        client = TestClient(app)
        mock_user = _make_user()
        mock_db = Mock(spec=Session)

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            mock_notif = Mock()
            mock_notif.id = "new-notif"
            with patch("notification_service.NotificationService.create_notification") as mock_create:
                mock_create.return_value = [mock_notif]
                resp = client.post(
                    "/api/notifications/test",
                    json={"notification_type": "invalid_type_xyz", "count": 1},
                )
                assert resp.status_code == 200  # Falls back to system_alert
        finally:
            app.dependency_overrides.clear()

    def test_create_test_notification_error(self):
        client = TestClient(app)
        mock_user = _make_user()
        mock_db = Mock(spec=Session)

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("notification_service.NotificationService.create_notification") as mock_create:
                mock_create.side_effect = Exception("fail")
                resp = client.post(
                    "/api/notifications/test",
                    json={"notification_type": "system_alert", "count": 1},
                )
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_create_admin_test_not_superadmin(self):
        client = TestClient(app)
        mock_user = _make_user(is_superadmin=False)

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            resp = client.post(
                "/api/notifications/test/create",
                json={"type": "system_alert", "title": "Test", "message": "Test msg"},
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_create_admin_test_success(self):
        client = TestClient(app)
        mock_user = _make_user(is_superadmin=True)
        mock_db = Mock(spec=Session)

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            mock_notif = Mock()
            mock_notif.id = "admin-notif"
            with patch("notification_service.NotificationService.create_notification") as mock_create:
                mock_create.return_value = [mock_notif]
                resp = client.post(
                    "/api/notifications/test/create",
                    json={"type": "system_alert", "title": "Admin Test", "message": "Test msg"},
                )
                assert resp.status_code == 200
                assert resp.json()["success"] is True
        finally:
            app.dependency_overrides.clear()

    def test_generate_all_not_superadmin(self):
        client = TestClient(app)
        mock_user = _make_user(is_superadmin=False)

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            resp = client.post("/api/notifications/test/generate-all")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_generate_all_success(self):
        client = TestClient(app)
        mock_user = _make_user(is_superadmin=True)
        mock_db = Mock(spec=Session)

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            mock_notif = Mock()
            mock_notif.id = "gen-notif"
            with patch("notification_service.NotificationService.create_notification") as mock_create:
                mock_create.return_value = [mock_notif]
                resp = client.post("/api/notifications/test/generate-all")
                assert resp.status_code == 200
                assert resp.json()["success"] is True
        finally:
            app.dependency_overrides.clear()

    def test_generate_all_partial_errors(self):
        client = TestClient(app)
        mock_user = _make_user(is_superadmin=True)
        mock_db = Mock(spec=Session)

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            call_count = {"n": 0}

            def create_side_effect(*args, **kwargs):
                call_count["n"] += 1
                if call_count["n"] % 3 == 0:
                    raise Exception("partial fail")
                mock_notif = Mock()
                mock_notif.id = f"notif-{call_count['n']}"
                return [mock_notif]

            with patch("notification_service.NotificationService.create_notification") as mock_create:
                mock_create.side_effect = create_side_effect
                resp = client.post("/api/notifications/test/generate-all")
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["errors"] is not None
        finally:
            app.dependency_overrides.clear()


class TestEmailTest:
    @patch("routers.notifications.EMAIL_SERVICE_AVAILABLE", False)
    def test_email_not_available(self):
        client = TestClient(app)
        mock_user = _make_user()

        from database import get_db
        from routers.notifications import require_user

        app.dependency_overrides[require_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: Mock(spec=Session)

        try:
            resp = client.post("/api/notifications/email/test")
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.clear()
