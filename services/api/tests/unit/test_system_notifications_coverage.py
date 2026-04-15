"""
Unit tests for services/email/system_notifications.py — targets 0% coverage (lines 8-239).
Covers all convenience functions: send_maintenance_notification, send_performance_alert,
send_security_alert, send_quota_warning, schedule_system_maintenance,
emergency_maintenance, suspicious_login_attempt, password_breach_notification,
database_performance_alert, api_rate_limit_alert.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestSendMaintenanceNotification:

    @patch("services.email.system_notifications.notify_system_maintenance")
    def test_success(self, mock_notify):
        from services.email.system_notifications import send_maintenance_notification
        db = MagicMock()
        send_maintenance_notification(
            db=db,
            title="Test Maintenance",
            message="System will be down",
            maintenance_start="2024-01-01T00:00:00",
            maintenance_end="2024-01-01T02:00:00",
            affected_services=["api", "frontend"],
        )
        mock_notify.assert_called_once()

    @patch("services.email.system_notifications.notify_system_maintenance", side_effect=Exception("fail"))
    def test_error_logged(self, mock_notify):
        from services.email.system_notifications import send_maintenance_notification
        db = MagicMock()
        # Should not raise
        send_maintenance_notification(db=db, title="Test", message="msg")


class TestSendPerformanceAlert:

    @patch("services.email.system_notifications.notify_performance_alert")
    def test_success(self, mock_notify):
        from services.email.system_notifications import send_performance_alert
        db = MagicMock()
        send_performance_alert(
            db=db,
            service_name="Database",
            alert_message="Slow query",
            severity="high",
            estimated_resolution="1 hour",
        )
        mock_notify.assert_called_once()

    @patch("services.email.system_notifications.notify_performance_alert", side_effect=Exception("fail"))
    def test_error_logged(self, mock_notify):
        from services.email.system_notifications import send_performance_alert
        db = MagicMock()
        send_performance_alert(db=db, service_name="API", alert_message="err")


class TestSendSecurityAlert:

    @patch("services.email.system_notifications.notify_security_alert")
    def test_success(self, mock_notify):
        from services.email.system_notifications import send_security_alert
        db = MagicMock()
        send_security_alert(
            db=db,
            user_id="u1",
            alert_type="login_failure",
            message="Failed login",
            severity="high",
            action_required="Change password",
            additional_context={"ip": "1.2.3.4"},
        )
        mock_notify.assert_called_once()

    @patch("services.email.system_notifications.notify_security_alert", side_effect=Exception("fail"))
    def test_error_logged(self, mock_notify):
        from services.email.system_notifications import send_security_alert
        db = MagicMock()
        send_security_alert(db=db, user_id="u1", alert_type="test", message="msg")


class TestSendQuotaWarning:

    @patch("services.email.system_notifications.notify_api_quota_warning")
    def test_success(self, mock_notify):
        from services.email.system_notifications import send_quota_warning
        db = MagicMock()
        send_quota_warning(
            db=db,
            user_id="u1",
            provider="OpenAI",
            usage_percentage=85,
            quota_limit="1000",
            current_usage="850",
        )
        mock_notify.assert_called_once()

    @patch("services.email.system_notifications.notify_api_quota_warning", side_effect=Exception("fail"))
    def test_error_logged(self, mock_notify):
        from services.email.system_notifications import send_quota_warning
        db = MagicMock()
        send_quota_warning(
            db=db, user_id="u1", provider="OpenAI",
            usage_percentage=90, quota_limit="100", current_usage="90",
        )


class TestScheduleSystemMaintenance:

    @patch("services.email.system_notifications.send_maintenance_notification")
    def test_success(self, mock_send):
        from services.email.system_notifications import schedule_system_maintenance
        db = MagicMock()
        schedule_system_maintenance(
            db=db,
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-01T02:00:00",
            affected_services=["api"],
            description="Monthly update",
        )
        mock_send.assert_called_once()
        args = mock_send.call_args
        assert "Scheduled System Maintenance" in args.kwargs.get("title", args[1] if len(args) > 1 else "")


class TestEmergencyMaintenance:

    @patch("services.email.system_notifications.send_maintenance_notification")
    def test_success(self, mock_send):
        from services.email.system_notifications import emergency_maintenance
        db = MagicMock()
        emergency_maintenance(
            db=db,
            reason="Database outage",
            affected_services=["database"],
            estimated_duration="2 hours",
        )
        mock_send.assert_called_once()


class TestSuspiciousLoginAttempt:

    @patch("services.email.system_notifications.send_security_alert")
    def test_with_location(self, mock_send):
        from services.email.system_notifications import suspicious_login_attempt
        db = MagicMock()
        suspicious_login_attempt(
            db=db,
            user_id="u1",
            ip_address="1.2.3.4",
            location="Berlin, Germany",
        )
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert "1.2.3.4" in call_kwargs.get("message", "")

    @patch("services.email.system_notifications.send_security_alert")
    def test_without_location(self, mock_send):
        from services.email.system_notifications import suspicious_login_attempt
        db = MagicMock()
        suspicious_login_attempt(db=db, user_id="u1", ip_address="5.6.7.8")
        mock_send.assert_called_once()


class TestPasswordBreachNotification:

    @patch("services.email.system_notifications.send_security_alert")
    def test_success(self, mock_send):
        from services.email.system_notifications import password_breach_notification
        db = MagicMock()
        password_breach_notification(db=db, user_id="u1", breach_source="ExampleCorp")
        mock_send.assert_called_once()


class TestDatabasePerformanceAlert:

    @patch("services.email.system_notifications.send_performance_alert")
    def test_high_severity(self, mock_send):
        from services.email.system_notifications import database_performance_alert
        db = MagicMock()
        database_performance_alert(db=db, response_time_ms=2500, threshold_ms=1000)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("severity", "") == "high"

    @patch("services.email.system_notifications.send_performance_alert")
    def test_medium_severity(self, mock_send):
        from services.email.system_notifications import database_performance_alert
        db = MagicMock()
        database_performance_alert(db=db, response_time_ms=1200, threshold_ms=1000)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("severity", "") == "medium"


class TestApiRateLimitAlert:

    @patch("services.email.system_notifications.send_performance_alert")
    def test_high_severity(self, mock_send):
        from services.email.system_notifications import api_rate_limit_alert
        db = MagicMock()
        api_rate_limit_alert(db=db, service_name="OpenAI", current_rate=95, limit=100)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("severity", "") == "high"

    @patch("services.email.system_notifications.send_performance_alert")
    def test_medium_severity(self, mock_send):
        from services.email.system_notifications import api_rate_limit_alert
        db = MagicMock()
        api_rate_limit_alert(db=db, service_name="OpenAI", current_rate=75, limit=100)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs.get("severity", "") == "medium"
