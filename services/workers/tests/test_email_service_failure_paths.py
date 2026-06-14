"""Failure- and exception-path coverage for email_service.py (workers).

The existing test_email_service.py covers the happy paths and the
mail-disabled guards for every EmailService method, plus the notification
sendgrid-failure / exception branches. It does NOT cover:

  * the sendgrid "status != success" failure return for send_digest_email,
    send_invitation_email, send_verification_email, send_password_reset_email
    (each has an `else: logger.error(...); return False` arm),
  * the outer `except Exception -> return False` arm for those same methods
    AND for send_notification_email (the existing exception test only trips
    the template render which is swallowed inside _render_template, so the
    outer except is never reached — we make send_message itself raise),
  * the read-only-filesystem `OSError` arm of _init_template_environment,
  * the three module-level async convenience wrappers
    (send_notification_email / send_digest_email / test_email_service).

Every test drives the same MagicMock-SendGrid idiom used by the
`email_service` fixture in test_email_service.py: the client's send_message
return value (or side effect) is crafted per branch and the boolean result
is asserted. No real SendGrid, no real template directory.
"""

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from jinja2 import Environment

from email_service import EmailService
from models import Notification, NotificationType


@pytest.fixture
def mock_sendgrid_client():
    client = Mock()
    client.send_message = Mock(return_value={"status": "success"})
    client.test_connection = AsyncMock(return_value=True)
    return client


@pytest.fixture
def email_service(mock_sendgrid_client):
    with patch("email_service.SendGridClient", return_value=mock_sendgrid_client):
        with patch.object(EmailService, "_init_template_environment") as mock_env:
            mock_template_env = Mock(spec=Environment)
            mock_env.return_value = mock_template_env
            service = EmailService()
            service.mail_enabled = True
            service.template_env = mock_template_env
            return service


@pytest.fixture
def notification():
    notif = Mock(spec=Notification)
    notif.type = NotificationType.TASK_ASSIGNED
    notif.id = "notif_123"
    notif.message = "A new task has been created"
    return notif


def _good_template(email_service):
    """Wire the mocked template env to render a usable subject+body."""
    mock_template = Mock()
    mock_template.render.return_value = "Subject: S\n<html>Body</html>"
    email_service.template_env.get_template.return_value = mock_template


# ============================================================================
# send_notification_email outer-except (send_message raises)
# ============================================================================


class TestSendNotificationEmailOuterExcept:
    @pytest.mark.asyncio
    async def test_send_message_raises_returns_false(self, email_service, notification):
        """The render is fine, but the transport itself raises -> the outer
        `except Exception -> return False` arm (lines 174-176) executes."""
        _good_template(email_service)
        email_service.mail_client.send_message.side_effect = RuntimeError("socket dead")
        result = await email_service.send_notification_email("u@example.com", notification)
        assert result is False


# ============================================================================
# send_digest_email failure + exception
# ============================================================================


class TestSendDigestEmailFailurePaths:
    @pytest.mark.asyncio
    async def test_sendgrid_failure_returns_false(self, email_service, notification):
        _good_template(email_service)
        email_service.mail_client.send_message.return_value = {
            "status": "error",
            "error": "rate limited",
        }
        result = await email_service.send_digest_email(
            "u@example.com", [notification], "daily"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_raises_returns_false(self, email_service, notification):
        _good_template(email_service)
        email_service.mail_client.send_message.side_effect = RuntimeError("boom")
        result = await email_service.send_digest_email(
            "u@example.com", [notification], "weekly"
        )
        assert result is False


# ============================================================================
# send_invitation_email failure + exception
# ============================================================================


class TestSendInvitationEmailFailurePaths:
    @pytest.mark.asyncio
    async def test_sendgrid_failure_returns_false(self, email_service):
        _good_template(email_service)
        email_service.mail_client.send_message.return_value = {
            "status": "error",
            "error": "bad address",
        }
        result = await email_service.send_invitation_email(
            to_email="u@example.com",
            inviter_name="Alice",
            organization_name="Acme",
            invitation_url="https://x/invite",
            role="member",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_raises_returns_false(self, email_service):
        _good_template(email_service)
        email_service.mail_client.send_message.side_effect = RuntimeError("boom")
        result = await email_service.send_invitation_email(
            to_email="u@example.com",
            inviter_name="Alice",
            organization_name="Acme",
            invitation_url="https://x/invite",
        )
        assert result is False


# ============================================================================
# send_verification_email failure + exception (both EN and DE language arms)
# ============================================================================


class TestSendVerificationEmailFailurePaths:
    @pytest.mark.asyncio
    async def test_sendgrid_failure_returns_false_english(self, email_service):
        email_service.mail_client.send_message.return_value = {
            "status": "error",
            "error": "nope",
        }
        result = await email_service.send_verification_email(
            "u@example.com", "Bob", "https://x/verify", language="en"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_raises_returns_false_german(self, email_service):
        email_service.mail_client.send_message.side_effect = RuntimeError("boom")
        result = await email_service.send_verification_email(
            "u@example.com", "Bob", "https://x/verify", language="de"
        )
        assert result is False


# ============================================================================
# send_password_reset_email failure + exception
# ============================================================================


class TestSendPasswordResetEmailFailurePaths:
    @pytest.mark.asyncio
    async def test_sendgrid_failure_returns_false(self, email_service):
        email_service.mail_client.send_message.return_value = {
            "status": "error",
            "error": "nope",
        }
        result = await email_service.send_password_reset_email(
            "u@example.com", "Bob", "https://x/reset", language="en"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_raises_returns_false(self, email_service):
        email_service.mail_client.send_message.side_effect = RuntimeError("boom")
        result = await email_service.send_password_reset_email(
            "u@example.com", "Bob", "https://x/reset", language="de"
        )
        assert result is False


# ============================================================================
# send_test_email exception (outer except)
# ============================================================================


class TestSendTestEmailException:
    @pytest.mark.asyncio
    async def test_send_message_raises_returns_false(self, email_service):
        email_service.mail_client.send_message.side_effect = RuntimeError("boom")
        result = await email_service.send_test_email("u@example.com", "Test")
        assert result is False


# ============================================================================
# _init_template_environment read-only-filesystem OSError arm
# ============================================================================


class TestInitTemplateEnvironmentReadOnly:
    def test_mkdir_oserror_is_swallowed(self, mock_sendgrid_client):
        """When the template dir is missing AND mkdir raises OSError (read-only
        rootfs), the warning arm (lines 53-54) runs and an Environment is still
        returned — initialization must not crash."""
        with patch("email_service.SendGridClient", return_value=mock_sendgrid_client):
            service = EmailService.__new__(EmailService)
            # Point at a path that "doesn't exist", and make mkdir fail.
            with patch.dict(
                os.environ, {"EMAIL_TEMPLATE_DIR": "/nonexistent/ro/templates"}
            ):
                with patch("pathlib.Path.exists", return_value=False), patch(
                    "pathlib.Path.mkdir", side_effect=OSError("read-only file system")
                ):
                    env = service._init_template_environment()
        assert isinstance(env, Environment)


# ============================================================================
# Module-level async convenience wrappers
# ============================================================================


class TestConvenienceWrappers:
    @pytest.mark.asyncio
    async def test_send_notification_email_wrapper_delegates(self, notification):
        """The module-level send_notification_email forwards to the global
        email_service instance (line 534)."""
        import email_service as es

        with patch.object(
            es.email_service, "send_notification_email", new=AsyncMock(return_value=True)
        ) as m:
            out = await es.send_notification_email("u@example.com", notification, {"k": "v"})
        assert out is True
        m.assert_awaited_once_with("u@example.com", notification, {"k": "v"})

    @pytest.mark.asyncio
    async def test_send_digest_email_wrapper_delegates(self, notification):
        """Line 541."""
        import email_service as es

        with patch.object(
            es.email_service, "send_digest_email", new=AsyncMock(return_value=True)
        ) as m:
            out = await es.send_digest_email("u@example.com", [notification], "weekly")
        assert out is True
        m.assert_awaited_once_with("u@example.com", [notification], "weekly")

    @pytest.mark.asyncio
    async def test_test_email_service_wrapper_delegates(self):
        """Line 546."""
        import email_service as es

        with patch.object(
            es.email_service, "test_connection", new=AsyncMock(return_value=True)
        ) as m:
            out = await es.test_email_service()
        assert out is True
        m.assert_awaited_once()
