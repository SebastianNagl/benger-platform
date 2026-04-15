"""
Extended unit tests for email_service to cover uncovered lines.

Covers:
- _is_mail_enabled exception branch (lines 58-60)
- _init_template_environment when directory creation fails with OSError (lines 70-71)
- _render_template exception fallback (lines 128-132)
- is_available when mail_enabled=True and api_key exists (line 142)
- send_notification_email: disabled mail (lines 162-163), successful send (lines 201-206),
  exception (lines 225-275)
- send_digest_email: disabled mail (lines 225-275), empty notifications (line 232-233),
  successful send, failed send, exception
- send_test_email: disabled mail (lines 288-322), successful send, failed send, exception
- send_invitation_email: exception (lines 381-386)
- send_verification_email: German language (lines 414-415), exception (lines 466-468)
- send_password_reset_email: disabled mail (lines 490-491), German language (lines 496-497),
  exception (lines 545-550), failed send (lines 545-550)
- Convenience functions: send_notification_email, send_digest_email, test_email_service (lines 564, 571, 576)
"""

import os
from unittest.mock import MagicMock, AsyncMock, patch, Mock

import pytest

from models import NotificationType


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def email_svc():
    """Create an EmailService instance with mocked dependencies."""
    with patch("services.email.email_service.SendGridClient") as mock_sg:
        with patch("database.SessionLocal"):
            from email_service import EmailService

            svc = EmailService()
            svc.mail_client = mock_sg.return_value
            svc.mail_enabled = True
            return svc


@pytest.fixture
def mock_notification():
    """Create a mock Notification object."""
    n = MagicMock()
    n.type = NotificationType.PROJECT_UPDATED
    n.title = "Project Updated"
    n.message = "Your project has been updated"
    return n


# ─────────────────────────────────────────────
# _is_mail_enabled
# ─────────────────────────────────────────────

class TestIsMailEnabled:

    def test_exception_returns_true(self):
        """When the DB check throws, default to True (lines 58-60)."""
        with patch("database.SessionLocal", side_effect=Exception("no DB")):
            from email_service import EmailService

            with patch("services.email.email_service.SendGridClient"):
                svc = EmailService()
                # Should default to enabled on error
                assert svc.mail_enabled is True


# ─────────────────────────────────────────────
# _init_template_environment
# ─────────────────────────────────────────────

class TestInitTemplateEnvironment:

    def test_oserror_on_mkdir(self):
        """OSError during directory creation is caught (lines 70-71)."""
        with patch("services.email.email_service.SendGridClient"):
            with patch("database.SessionLocal"):
                with patch("services.email.email_service.Path.exists", return_value=False):
                    with patch(
                        "services.email.email_service.Path.mkdir",
                        side_effect=OSError("read-only"),
                    ):
                        from email_service import EmailService

                        svc = EmailService()
                        # Should still create the env despite mkdir failure
                        assert svc.template_env is not None


# ─────────────────────────────────────────────
# _render_template
# ─────────────────────────────────────────────

class TestRenderTemplate:

    def test_exception_returns_fallback(self, email_svc):
        """Template rendering exception returns fallback (lines 128-132)."""
        email_svc.template_env.get_template = MagicMock(
            side_effect=Exception("template not found")
        )

        subject, body = email_svc._render_template(
            "missing.html", {"message": "Hello world"}
        )
        assert subject == "BenGER Notification"
        assert "Hello world" in body

    def test_exception_fallback_no_message_key(self, email_svc):
        """Fallback uses default when context has no 'message' key."""
        email_svc.template_env.get_template = MagicMock(
            side_effect=Exception("template not found")
        )

        subject, body = email_svc._render_template("missing.html", {})
        assert subject == "BenGER Notification"
        assert "Notification from BenGER" in body


# ─────────────────────────────────────────────
# test_connection
# ─────────────────────────────────────────────

class TestTestConnection:

    @pytest.mark.asyncio
    async def test_connection_success(self, email_svc):
        """Successful connection test (lines 128-132)."""
        email_svc.mail_client.test_connection = AsyncMock(return_value=True)
        result = await email_svc.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_failure(self, email_svc):
        """Failed connection test returns False (lines 128-132)."""
        email_svc.mail_client.test_connection = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        result = await email_svc.test_connection()
        assert result is False


# ─────────────────────────────────────────────
# is_available
# ─────────────────────────────────────────────

class TestIsAvailable:

    def test_available_when_enabled_and_key_exists(self, email_svc):
        """Returns True when both mail_enabled and api_key are set (line 142)."""
        email_svc.mail_enabled = True
        email_svc.mail_client.api_key = "sg-some-key"
        assert email_svc.is_available() is True

    def test_not_available_when_disabled(self, email_svc):
        """Returns False when mail_enabled is False."""
        email_svc.mail_enabled = False
        email_svc.mail_client.api_key = "sg-some-key"
        assert email_svc.is_available() is False

    def test_not_available_when_no_key(self, email_svc):
        """Returns False when api_key is empty."""
        email_svc.mail_enabled = True
        email_svc.mail_client.api_key = ""
        assert email_svc.is_available() is False


# ─────────────────────────────────────────────
# send_notification_email
# ─────────────────────────────────────────────

class TestSendNotificationEmail:

    @pytest.mark.asyncio
    async def test_disabled_mail(self, email_svc, mock_notification):
        """Returns False when mail is disabled (lines 162-163)."""
        email_svc.mail_enabled = False
        result = await email_svc.send_notification_email(
            "user@example.com", mock_notification
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_send(self, email_svc, mock_notification):
        """Successful notification email send (lines 197-199)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "success"}
        )
        # Mock template rendering
        email_svc._render_template = MagicMock(return_value=("Subject", "<p>Body</p>"))

        result = await email_svc.send_notification_email(
            "user@example.com", mock_notification
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_failed_send(self, email_svc, mock_notification):
        """Failed notification email returns False (lines 201-202)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "error", "error": "rate limited"}
        )
        email_svc._render_template = MagicMock(return_value=("Subject", "<p>Body</p>"))

        result = await email_svc.send_notification_email(
            "user@example.com", mock_notification
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_during_send(self, email_svc, mock_notification):
        """Exception during send returns False (lines 204-206)."""
        email_svc._render_template = MagicMock(side_effect=Exception("render failed"))

        result = await email_svc.send_notification_email(
            "user@example.com", mock_notification
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_notification_type_none(self, email_svc):
        """Notification with type=None uses default template (line 186)."""
        n = MagicMock()
        n.type = None

        email_svc._render_template = MagicMock(return_value=("Subject", "<p>Body</p>"))
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "success"}
        )

        result = await email_svc.send_notification_email("user@example.com", n)
        assert result is True
        # Should use "default_notification.html"
        email_svc._render_template.assert_called_once()
        template_name = email_svc._render_template.call_args[0][0]
        assert template_name == "default_notification.html"


# ─────────────────────────────────────────────
# send_digest_email
# ─────────────────────────────────────────────

class TestSendDigestEmail:

    @pytest.mark.asyncio
    async def test_disabled_mail(self, email_svc):
        """Returns False when mail is disabled (lines 225-227)."""
        email_svc.mail_enabled = False
        result = await email_svc.send_digest_email("user@example.com", [])
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_notifications(self, email_svc):
        """Empty notification list returns True (lines 231-233)."""
        result = await email_svc.send_digest_email("user@example.com", [])
        assert result is True

    @pytest.mark.asyncio
    async def test_successful_send(self, email_svc):
        """Successful digest email send (lines 266-268)."""
        notifications = [MagicMock(type=NotificationType.PROJECT_CREATED)]
        email_svc._render_template = MagicMock(return_value=("Subject", "<p>Digest</p>"))
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "success"}
        )

        result = await email_svc.send_digest_email(
            "user@example.com", notifications, "daily"
        )
        assert result is True
        # Verify the subject was overridden
        call_args = email_svc.mail_client.send_message.call_args
        assert "Daily" in call_args[1]["subject"]

    @pytest.mark.asyncio
    async def test_failed_send(self, email_svc):
        """Failed digest email returns False (lines 270-271)."""
        notifications = [MagicMock(type=NotificationType.PROJECT_CREATED)]
        email_svc._render_template = MagicMock(return_value=("Subject", "<p>Digest</p>"))
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "error", "error": "timeout"}
        )

        result = await email_svc.send_digest_email(
            "user@example.com", notifications, "weekly"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_during_send(self, email_svc):
        """Exception during digest email returns False (lines 273-275)."""
        notifications = [MagicMock(type=NotificationType.PROJECT_CREATED)]
        email_svc._render_template = MagicMock(side_effect=Exception("render error"))

        result = await email_svc.send_digest_email(
            "user@example.com", notifications
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_notification_with_no_type(self, email_svc):
        """Notification with type=None uses 'other' grouping (line 238)."""
        n = MagicMock()
        n.type = None
        email_svc._render_template = MagicMock(return_value=("Subject", "<p>D</p>"))
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "success"}
        )

        result = await email_svc.send_digest_email("user@example.com", [n])
        assert result is True


# ─────────────────────────────────────────────
# send_test_email
# ─────────────────────────────────────────────

class TestSendTestEmail:

    @pytest.mark.asyncio
    async def test_disabled_mail(self, email_svc):
        """Returns False when mail is disabled (lines 288-290)."""
        email_svc.mail_enabled = False
        result = await email_svc.send_test_email("user@example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_send(self, email_svc):
        """Successful test email (lines 313-314)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "success"}
        )
        result = await email_svc.send_test_email("user@example.com", "Alice")
        assert result is True

    @pytest.mark.asyncio
    async def test_failed_send(self, email_svc):
        """Failed test email returns False (lines 317-318)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "error", "error": "bad request"}
        )
        result = await email_svc.send_test_email("user@example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_during_send(self, email_svc):
        """Exception during test email returns False (lines 320-322)."""
        email_svc.mail_client.send_message = MagicMock(
            side_effect=Exception("connection failed")
        )
        result = await email_svc.send_test_email("user@example.com")
        assert result is False


# ─────────────────────────────────────────────
# send_invitation_email
# ─────────────────────────────────────────────

class TestSendInvitationEmail:

    @pytest.mark.asyncio
    async def test_exception_during_send(self, email_svc):
        """Exception returns False (lines 384-386)."""
        email_svc.mail_client.send_message = MagicMock(
            side_effect=Exception("timeout")
        )
        result = await email_svc.send_invitation_email(
            "to@example.com", "Alice", "TUM", "https://invite.link"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_failed_send(self, email_svc):
        """Failed send returns False (lines 381-382)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "error", "error": "invalid recipient"}
        )
        result = await email_svc.send_invitation_email(
            "to@example.com", "Alice", "TUM", "https://invite.link"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_send(self, email_svc):
        """Successful invitation send (lines 377-378)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "success"}
        )
        result = await email_svc.send_invitation_email(
            "to@example.com", "Alice", "TUM", "https://invite.link"
        )
        assert result is True
        call_args = email_svc.mail_client.send_message.call_args[1]
        assert call_args["disable_tracking"] is True


# ─────────────────────────────────────────────
# send_verification_email
# ─────────────────────────────────────────────

class TestSendVerificationEmail:

    @pytest.mark.asyncio
    async def test_disabled_mail(self, email_svc):
        """Returns False when disabled (lines 407-409)."""
        email_svc.mail_enabled = False
        result = await email_svc.send_verification_email(
            "user@example.com", "User", "https://verify.link"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_german_language(self, email_svc):
        """German language email (lines 414-432)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "success"}
        )
        result = await email_svc.send_verification_email(
            "user@example.com", "Hans", "https://verify.link", language="de"
        )
        assert result is True
        call_args = email_svc.mail_client.send_message.call_args[1]
        assert "Bestätigen" in call_args["subject"]

    @pytest.mark.asyncio
    async def test_exception_during_send(self, email_svc):
        """Exception returns False (lines 466-468)."""
        email_svc.mail_client.send_message = MagicMock(
            side_effect=Exception("boom")
        )
        result = await email_svc.send_verification_email(
            "user@example.com", "User", "https://verify.link"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_failed_send(self, email_svc):
        """Failed verification email returns False (lines 463-464)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "error", "error": "nope"}
        )
        result = await email_svc.send_verification_email(
            "user@example.com", "User", "https://verify.link"
        )
        assert result is False


# ─────────────────────────────────────────────
# send_password_reset_email
# ─────────────────────────────────────────────

class TestSendPasswordResetEmail:

    @pytest.mark.asyncio
    async def test_disabled_mail(self, email_svc):
        """Returns False when disabled (lines 490-491)."""
        email_svc.mail_enabled = False
        result = await email_svc.send_password_reset_email(
            "user@example.com", "User", "https://reset.link"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_german_language(self, email_svc):
        """German language password reset (lines 496-497)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "success"}
        )
        result = await email_svc.send_password_reset_email(
            "user@example.com", "Hans", "https://reset.link", language="de"
        )
        assert result is True
        call_args = email_svc.mail_client.send_message.call_args[1]
        assert "Passwort" in call_args["subject"]

    @pytest.mark.asyncio
    async def test_failed_send(self, email_svc):
        """Failed password reset email returns False (lines 545-546)."""
        email_svc.mail_client.send_message = MagicMock(
            return_value={"status": "error", "error": "fail"}
        )
        result = await email_svc.send_password_reset_email(
            "user@example.com", "User", "https://reset.link"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_during_send(self, email_svc):
        """Exception returns False (lines 548-550)."""
        email_svc.mail_client.send_message = MagicMock(
            side_effect=Exception("network error")
        )
        result = await email_svc.send_password_reset_email(
            "user@example.com", "User", "https://reset.link"
        )
        assert result is False


# ─────────────────────────────────────────────
# Module-level convenience functions
# ─────────────────────────────────────────────

class TestConvenienceFunctions:

    @pytest.mark.asyncio
    async def test_send_notification_email_convenience(self):
        """Test module-level send_notification_email function (line 564)."""
        import sys

        # The convenience functions reference the global from services.email.email_service
        pkg_mod = sys.modules.get("services.email.email_service")
        short_mod = sys.modules.get("email_service")

        # Patch in both module copies
        mock_svc = MagicMock()
        mock_svc.send_notification_email = AsyncMock(return_value=True)

        originals = {}
        for mod in [pkg_mod, short_mod]:
            if mod:
                originals[id(mod)] = (mod, getattr(mod, "email_service", None))
                mod.email_service = mock_svc

        try:
            from email_service import send_notification_email

            notification = MagicMock()
            result = await send_notification_email("user@example.com", notification)
            assert result is True
            mock_svc.send_notification_email.assert_called_once()
        finally:
            for _, (mod, orig) in originals.items():
                mod.email_service = orig

    @pytest.mark.asyncio
    async def test_send_digest_email_convenience(self):
        """Test module-level send_digest_email function (line 571)."""
        import sys

        pkg_mod = sys.modules.get("services.email.email_service")
        short_mod = sys.modules.get("email_service")

        mock_svc = MagicMock()
        mock_svc.send_digest_email = AsyncMock(return_value=True)

        originals = {}
        for mod in [pkg_mod, short_mod]:
            if mod:
                originals[id(mod)] = (mod, getattr(mod, "email_service", None))
                mod.email_service = mock_svc

        try:
            from email_service import send_digest_email

            result = await send_digest_email("user@example.com", [], "daily")
            assert result is True
            mock_svc.send_digest_email.assert_called_once()
        finally:
            for _, (mod, orig) in originals.items():
                mod.email_service = orig

    @pytest.mark.asyncio
    async def test_test_email_service_convenience(self):
        """Test module-level test_email_service function (line 576)."""
        import sys

        pkg_mod = sys.modules.get("services.email.email_service")
        short_mod = sys.modules.get("email_service")

        mock_svc = MagicMock()
        mock_svc.test_connection = AsyncMock(return_value=True)

        originals = {}
        for mod in [pkg_mod, short_mod]:
            if mod:
                originals[id(mod)] = (mod, getattr(mod, "email_service", None))
                mod.email_service = mock_svc

        try:
            from email_service import test_email_service

            result = await test_email_service()
            assert result is True
            mock_svc.test_connection.assert_called_once()
        finally:
            for _, (mod, orig) in originals.items():
                mod.email_service = orig


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
