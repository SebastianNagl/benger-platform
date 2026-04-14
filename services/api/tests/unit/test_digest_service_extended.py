"""
Unit tests for services/email/digest_service.py — 23.61% coverage (121 uncovered lines).

Tests DigestService.should_send_digest, get_digest_period, generate_digest_data,
and related helper methods.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestShouldSendDigest:
    """Test DigestService.should_send_digest."""

    def test_digest_disabled_returns_false(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            enable_email_digest=False,
            digest_frequency="daily",
            digest_time="09:00",
        )
        assert DigestService.should_send_digest(user) is False

    def test_no_frequency_returns_false(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            enable_email_digest=True,
            digest_frequency=None,
            digest_time="09:00",
        )
        assert DigestService.should_send_digest(user) is False

    def test_no_time_returns_false(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            enable_email_digest=True,
            digest_frequency="daily",
            digest_time=None,
        )
        assert DigestService.should_send_digest(user) is False

    def test_email_service_not_available(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            enable_email_digest=True,
            digest_frequency="daily",
            digest_time="09:00",
        )
        # EMAIL_SERVICE_AVAILABLE is False by default in test env
        assert DigestService.should_send_digest(user) is False

    def test_never_sent_before_returns_true_when_available(self):
        from services.email.digest_service import DigestService
        import services.email.digest_service as ds
        original = ds.EMAIL_SERVICE_AVAILABLE
        try:
            ds.EMAIL_SERVICE_AVAILABLE = True
            user = SimpleNamespace(
                id="u1",
                enable_email_digest=True,
                digest_frequency="daily",
                digest_time="00:00",
                timezone="UTC",
                last_digest_sent=None,
            )
            result = DigestService.should_send_digest(user)
            assert result is True
        finally:
            ds.EMAIL_SERVICE_AVAILABLE = original

    def test_daily_sent_today_returns_false(self):
        from services.email.digest_service import DigestService
        import pytz
        import services.email.digest_service as ds
        original = ds.EMAIL_SERVICE_AVAILABLE
        try:
            ds.EMAIL_SERVICE_AVAILABLE = True
            now = datetime.now(pytz.timezone("UTC"))
            user = SimpleNamespace(
                id="u1",
                enable_email_digest=True,
                digest_frequency="daily",
                digest_time="00:00",
                timezone="UTC",
                last_digest_sent=now,
            )
            result = DigestService.should_send_digest(user)
            assert result is False
        finally:
            ds.EMAIL_SERVICE_AVAILABLE = original

    def test_daily_sent_yesterday_returns_true(self):
        from services.email.digest_service import DigestService
        import pytz
        import services.email.digest_service as ds
        original = ds.EMAIL_SERVICE_AVAILABLE
        try:
            ds.EMAIL_SERVICE_AVAILABLE = True
            now = datetime.now(pytz.timezone("UTC"))
            yesterday = now - timedelta(days=1, hours=2)
            user = SimpleNamespace(
                id="u1",
                enable_email_digest=True,
                digest_frequency="daily",
                digest_time="00:00",
                timezone="UTC",
                last_digest_sent=yesterday,
            )
            result = DigestService.should_send_digest(user)
            assert result is True
        finally:
            ds.EMAIL_SERVICE_AVAILABLE = original

    def test_weekly_wrong_day_returns_false(self):
        from services.email.digest_service import DigestService
        import pytz
        import services.email.digest_service as ds
        original = ds.EMAIL_SERVICE_AVAILABLE
        try:
            ds.EMAIL_SERVICE_AVAILABLE = True
            now = datetime.now(pytz.timezone("UTC"))
            current_weekday = now.weekday()
            wrong_day = (current_weekday + 1) % 7
            user = SimpleNamespace(
                id="u1",
                enable_email_digest=True,
                digest_frequency="weekly",
                digest_time="00:00",
                timezone="UTC",
                last_digest_sent=now - timedelta(days=8),
                digest_days=json.dumps([wrong_day]),
            )
            result = DigestService.should_send_digest(user)
            assert result is False
        finally:
            ds.EMAIL_SERVICE_AVAILABLE = original

    def test_bi_weekly_recent_returns_false(self):
        from services.email.digest_service import DigestService
        import pytz
        import services.email.digest_service as ds
        original = ds.EMAIL_SERVICE_AVAILABLE
        try:
            ds.EMAIL_SERVICE_AVAILABLE = True
            now = datetime.now(pytz.timezone("UTC"))
            user = SimpleNamespace(
                id="u1",
                enable_email_digest=True,
                digest_frequency="bi-weekly",
                digest_time="00:00",
                timezone="UTC",
                last_digest_sent=now - timedelta(days=5),
            )
            result = DigestService.should_send_digest(user)
            assert result is False
        finally:
            ds.EMAIL_SERVICE_AVAILABLE = original

    def test_before_digest_time_returns_false(self):
        from services.email.digest_service import DigestService
        import pytz
        import services.email.digest_service as ds
        original = ds.EMAIL_SERVICE_AVAILABLE
        try:
            ds.EMAIL_SERVICE_AVAILABLE = True
            # Set digest time far in the future (23:59) so it's never "due" now
            user = SimpleNamespace(
                id="u1",
                enable_email_digest=True,
                digest_frequency="daily",
                digest_time="23:59",
                timezone="UTC",
                last_digest_sent=datetime.now(pytz.UTC),  # Already sent today
            )
            result = DigestService.should_send_digest(user)
            assert result is False
        finally:
            ds.EMAIL_SERVICE_AVAILABLE = original


class TestGetDigestPeriod:
    """Test DigestService.get_digest_period."""

    def test_daily_period(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            digest_frequency="daily",
            timezone="UTC",
        )
        period = DigestService.get_digest_period(user)
        assert "start" in period
        assert "end" in period
        delta = period["end"] - period["start"]
        assert abs(delta.total_seconds() - 86400) < 60  # ~1 day

    def test_weekly_period(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            digest_frequency="weekly",
            timezone="UTC",
        )
        period = DigestService.get_digest_period(user)
        delta = period["end"] - period["start"]
        assert abs(delta.total_seconds() - 7 * 86400) < 60

    def test_bi_weekly_period(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            digest_frequency="bi-weekly",
            timezone="UTC",
        )
        period = DigestService.get_digest_period(user)
        delta = period["end"] - period["start"]
        assert abs(delta.total_seconds() - 14 * 86400) < 60

    def test_unknown_frequency_defaults_to_daily(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            digest_frequency="unknown",
            timezone="UTC",
        )
        period = DigestService.get_digest_period(user)
        delta = period["end"] - period["start"]
        assert abs(delta.total_seconds() - 86400) < 60

    def test_none_timezone_defaults_to_utc(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            digest_frequency="daily",
            timezone=None,
        )
        period = DigestService.get_digest_period(user)
        assert "start" in period
        assert "end" in period

    def test_invalid_timezone_fallback(self):
        from services.email.digest_service import DigestService
        user = SimpleNamespace(
            id="u1",
            digest_frequency="daily",
            timezone="Invalid/Timezone",
        )
        period = DigestService.get_digest_period(user)
        # Should fall back to UTC-based period
        assert "start" in period


class TestGenerateDigestData:
    """Test DigestService.generate_digest_data."""

    def _make_notification(self, id, type_value, title, message, is_read=False):
        import pytz
        return SimpleNamespace(
            id=id,
            type=SimpleNamespace(value=type_value),
            title=title,
            message=message,
            is_read=is_read,
            created_at=datetime.now(pytz.UTC),
        )

    def test_empty_notifications(self):
        from services.email.digest_service import DigestService
        result = DigestService.generate_digest_data([])
        assert result["total_count"] == 0
        assert result["by_type"] == {}
        assert result["summary"] == "No new notifications"

    def test_single_notification(self):
        from services.email.digest_service import DigestService
        notif = self._make_notification("n1", "info", "Title", "Message")
        result = DigestService.generate_digest_data([notif])
        assert result["total_count"] == 1
        assert "1 new notification" in result["summary"]
        assert "info" in result["by_type"]

    def test_multiple_notifications(self):
        from services.email.digest_service import DigestService
        notifs = [
            self._make_notification("n1", "info", "Info 1", "Msg 1"),
            self._make_notification("n2", "warning", "Warn 1", "Msg 2"),
            self._make_notification("n3", "info", "Info 2", "Msg 3"),
        ]
        result = DigestService.generate_digest_data(notifs)
        assert result["total_count"] == 3
        assert "3 new notifications" in result["summary"]
        assert len(result["by_type"]["info"]) == 2
        assert len(result["by_type"]["warning"]) == 1

    def test_unread_count(self):
        from services.email.digest_service import DigestService
        notifs = [
            self._make_notification("n1", "info", "T1", "M1", is_read=False),
            self._make_notification("n2", "info", "T2", "M2", is_read=True),
            self._make_notification("n3", "info", "T3", "M3", is_read=False),
        ]
        result = DigestService.generate_digest_data(notifs)
        assert result["unread_count"] == 2
        assert "2 unread" in result["summary"]

    def test_recent_notifications_limited_to_10(self):
        from services.email.digest_service import DigestService
        notifs = [
            self._make_notification(f"n{i}", "info", f"T{i}", f"M{i}")
            for i in range(15)
        ]
        result = DigestService.generate_digest_data(notifs)
        assert len(result["recent_notifications"]) == 10

    def test_type_counts(self):
        from services.email.digest_service import DigestService
        notifs = [
            self._make_notification("n1", "info", "T1", "M1"),
            self._make_notification("n2", "error", "T2", "M2"),
            self._make_notification("n3", "info", "T3", "M3"),
        ]
        result = DigestService.generate_digest_data(notifs)
        assert result["type_counts"]["info"] == 2
        assert result["type_counts"]["error"] == 1

    def test_notification_data_structure(self):
        from services.email.digest_service import DigestService
        notif = self._make_notification("n1", "info", "Title", "Message")
        result = DigestService.generate_digest_data([notif])
        recent = result["recent_notifications"][0]
        assert "id" in recent
        assert "type" in recent
        assert "title" in recent
        assert "message" in recent
        assert "created_at" in recent
        assert "is_read" in recent
