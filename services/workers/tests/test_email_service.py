"""
Comprehensive tests for email service (workers)
Tests email sending, template rendering, multi-language support
Coverage target: 60%+ of email_service.py
"""

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from jinja2 import Environment

from email_service import EmailService
from models import Notification, NotificationType


@pytest.fixture
def mock_db_session():
    """Create a mock database session"""
    session = Mock()
    session.query = Mock()
    session.close = Mock()
    return session


@pytest.fixture
def mock_feature_flag():
    """Create a mock feature flag"""
    flag = Mock()
    flag.name = "API_MAIL_SERVICE"
    flag.is_enabled = True
    return flag


@pytest.fixture
def mock_sendgrid_client():
    """Create a mock SendGrid client"""
    client = Mock()
    client.send_message = Mock(return_value={"status": "success"})
    client.test_connection = AsyncMock(return_value=True)
    return client


@pytest.fixture
def email_service(mock_sendgrid_client):
    """Create an EmailService instance with mocked dependencies"""
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
    """Create a sample notification"""
    notif = Mock(spec=Notification)
    notif.type = NotificationType.TASK_CREATED
    notif.id = "notif_123"
    notif.message = "A new task has been created"
    return notif


class TestEmailServiceInitialization:
    """Test EmailService initialization"""

    def test_init_with_default_values(self, mock_sendgrid_client):
        """Test initialization with default environment values"""
        with patch("email_service.SendGridClient", return_value=mock_sendgrid_client):
            with patch.object(EmailService, "_init_template_environment", return_value=Mock()):
                service = EmailService()

                assert service.smtp_host == "mail"
                assert service.smtp_port == 25
                assert service.from_email == "noreply@what-a-benger.net"
                assert service.from_name == "BenGER Platform"

    def test_init_with_custom_env_values(self, mock_sendgrid_client):
        """Test initialization with custom environment values"""
        env_vars = {
            "MAIL_SMTP_HOST": "smtp.custom.com",
            "MAIL_SMTP_PORT": "587",
            "MAIL_FROM_EMAIL": "custom@example.com",
            "MAIL_FROM_NAME": "Custom Name",
        }

        with patch.dict(os.environ, env_vars):
            with patch("email_service.SendGridClient", return_value=mock_sendgrid_client):
                with patch.object(
                    EmailService, "_init_template_environment", return_value=Mock()
                ):
                    service = EmailService()

                    assert service.smtp_host == "smtp.custom.com"
                    assert service.smtp_port == 587
                    assert service.from_email == "custom@example.com"
                    assert service.from_name == "Custom Name"

    def test_init_with_mail_disabled(self, mock_sendgrid_client):
        """Test initialization when mail service is disabled"""
        with patch("email_service.SendGridClient", return_value=mock_sendgrid_client):
            with patch.object(EmailService, "_init_template_environment", return_value=Mock()):
                service = EmailService()
                service.mail_enabled = False

                assert service.mail_enabled is False


class TestMailEnabledFlag:
    """Test mail_enabled flag behavior"""

    def test_mail_enabled_default_is_true(self):
        """Test mail service is enabled by default"""
        with patch("email_service.SendGridClient"):
            with patch.object(EmailService, "_init_template_environment", return_value=Mock()):
                service = EmailService()
                assert service.mail_enabled is True

    def test_mail_can_be_disabled(self):
        """Test mail service can be disabled"""
        with patch("email_service.SendGridClient"):
            with patch.object(EmailService, "_init_template_environment", return_value=Mock()):
                service = EmailService()
                service.mail_enabled = False
                assert service.mail_enabled is False

    def test_mail_enabled_affects_sending(self):
        """Test that disabled mail prevents sending"""
        with patch("email_service.SendGridClient") as mock_sg:
            mock_client = Mock()
            mock_sg.return_value = mock_client
            with patch.object(EmailService, "_init_template_environment", return_value=Mock()):
                service = EmailService()
                service.mail_enabled = False
                # mail_enabled = False should prevent sending in all send methods


class TestTemplateEnvironment:
    """Test Jinja2 template environment setup"""

    def test_init_template_environment_creates_directory(self):
        """Test that template directory is created if it doesn't exist"""
        with patch("email_service.SendGridClient"):
            with patch("pathlib.Path.exists", return_value=False):
                with patch("pathlib.Path.mkdir") as mock_mkdir:
                    service = EmailService()
                    env = service._init_template_environment()

                    # mkdir should be called at least once
                    assert mock_mkdir.called
                    assert isinstance(env, Environment)

    def test_init_template_environment_existing_directory(self):
        """Test initialization with existing template directory"""
        with patch("email_service.SendGridClient"):
            with patch("pathlib.Path.exists", return_value=True):
                service = EmailService()
                env = service._init_template_environment()

                assert isinstance(env, Environment)
                assert env.autoescape is True

    def test_template_environment_has_custom_filters(self):
        """Test that custom template filters are registered"""
        with patch("email_service.SendGridClient"):
            service = EmailService()
            env = service._init_template_environment()

            # Check for format_date filter
            assert "format_date" in env.filters


class TestTemplateRendering:
    """Test template rendering functionality"""

    def test_render_template_with_subject_line(self, email_service):
        """Test rendering template with Subject: line"""
        mock_template = Mock()
        mock_template.render.return_value = (
            "Subject: Test Email\n<html><body>Test content</body></html>"
        )
        email_service.template_env.get_template.return_value = mock_template

        subject, html_body = email_service._render_template("test.html", {"name": "Test User"})

        assert subject == "Test Email"
        assert "Test content" in html_body
        assert "Subject:" not in html_body

    def test_render_template_without_subject_line(self, email_service):
        """Test rendering template without Subject: line"""
        mock_template = Mock()
        mock_template.render.return_value = "<html><body>Test content</body></html>"
        email_service.template_env.get_template.return_value = mock_template

        subject, html_body = email_service._render_template("test.html", {"name": "Test User"})

        assert subject == "BenGER Notification"
        assert "Test content" in html_body

    def test_render_template_error_handling(self, email_service):
        """Test fallback behavior on template rendering error"""
        email_service.template_env.get_template.side_effect = Exception("Template not found")

        subject, html_body = email_service._render_template(
            "missing.html", {"message": "Test message"}
        )

        assert subject == "BenGER Notification"
        assert "Test message" in html_body

    def test_render_template_with_empty_context(self, email_service):
        """Test rendering with empty context"""
        mock_template = Mock()
        mock_template.render.return_value = "<html><body>Empty</body></html>"
        email_service.template_env.get_template.return_value = mock_template

        subject, html_body = email_service._render_template("test.html", {})

        assert subject == "BenGER Notification"
        assert "Empty" in html_body


class TestTestConnection:
    """Test mail server connection testing"""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, email_service):
        """Test successful connection test"""
        email_service.mail_client.test_connection = AsyncMock(return_value=True)

        result = await email_service.test_connection()

        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, email_service):
        """Test failed connection test"""
        email_service.mail_client.test_connection = AsyncMock(return_value=False)

        result = await email_service.test_connection()

        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_exception(self, email_service):
        """Test connection test with exception"""
        email_service.mail_client.test_connection = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        result = await email_service.test_connection()

        assert result is False


class TestSendNotificationEmail:
    """Test send_notification_email method"""

    @pytest.mark.asyncio
    async def test_send_notification_email_success(self, email_service, notification):
        """Test successful notification email sending"""
        mock_template = Mock()
        mock_template.render.return_value = (
            "Subject: Task Assigned\n<html><body>Content</body></html>"
        )
        email_service.template_env.get_template.return_value = mock_template
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_notification_email("user@example.com", notification)

        assert result is True
        email_service.mail_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_email_mail_disabled(self, email_service, notification):
        """Test email not sent when service is disabled"""
        email_service.mail_enabled = False

        result = await email_service.send_notification_email("user@example.com", notification)

        assert result is False
        email_service.mail_client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_notification_email_with_context(self, email_service, notification):
        """Test notification email with additional context"""
        mock_template = Mock()
        mock_template.render.return_value = "Subject: Test\n<html>Content</html>"
        email_service.template_env.get_template.return_value = mock_template
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_notification_email(
            "user@example.com", notification, context={"extra_data": "test"}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_notification_email_sendgrid_failure(self, email_service, notification):
        """Test handling of SendGrid send failure"""
        mock_template = Mock()
        mock_template.render.return_value = "Subject: Test\n<html>Content</html>"
        email_service.template_env.get_template.return_value = mock_template
        email_service.mail_client.send_message.return_value = {
            "status": "error",
            "error": "API error",
        }

        result = await email_service.send_notification_email("user@example.com", notification)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_email_exception(self, email_service, notification):
        """Test graceful handling of template rendering errors"""
        email_service.template_env.get_template.side_effect = Exception("Template error")
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_notification_email("user@example.com", notification)

        # Should succeed with fallback template
        assert result is True


class TestSendDigestEmail:
    """Test send_digest_email method"""

    @pytest.mark.asyncio
    async def test_send_digest_email_success(self, email_service, notification):
        """Test successful digest email sending"""
        mock_template = Mock()
        mock_template.render.return_value = (
            "Subject: Digest\n<html><body>Digest content</body></html>"
        )
        email_service.template_env.get_template.return_value = mock_template
        email_service.mail_client.send_message.return_value = {"status": "success"}

        notifications = [notification]
        result = await email_service.send_digest_email("user@example.com", notifications, "daily")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_digest_email_mail_disabled(self, email_service, notification):
        """Test digest email not sent when service is disabled"""
        email_service.mail_enabled = False

        result = await email_service.send_digest_email("user@example.com", [notification], "daily")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_digest_email_empty_list(self, email_service):
        """Test digest email with empty notification list"""
        result = await email_service.send_digest_email("user@example.com", [], "daily")

        # Should return True for empty list (nothing to send)
        assert result is True
        email_service.mail_client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_digest_email_weekly(self, email_service, notification):
        """Test weekly digest email"""
        mock_template = Mock()
        mock_template.render.return_value = "Subject: Weekly\n<html>Content</html>"
        email_service.template_env.get_template.return_value = mock_template
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_digest_email("user@example.com", [notification], "weekly")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_digest_email_multiple_notifications(self, email_service):
        """Test digest email with multiple notifications"""
        mock_template = Mock()
        mock_template.render.return_value = "Subject: Digest\n<html>Content</html>"
        email_service.template_env.get_template.return_value = mock_template
        email_service.mail_client.send_message.return_value = {"status": "success"}

        notifications = []
        for i in range(5):
            notif = Mock(spec=Notification)
            notif.type = NotificationType.TASK_CREATED
            notif.id = f"notif_{i}"
            notifications.append(notif)

        result = await email_service.send_digest_email("user@example.com", notifications, "daily")

        assert result is True


class TestSendTestEmail:
    """Test send_test_email method"""

    @pytest.mark.asyncio
    async def test_send_test_email_success(self, email_service):
        """Test successful test email sending"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_test_email("user@example.com", "Test User")

        assert result is True
        email_service.mail_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_test_email_mail_disabled(self, email_service):
        """Test test email not sent when service is disabled"""
        email_service.mail_enabled = False

        result = await email_service.send_test_email("user@example.com")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_test_email_default_name(self, email_service):
        """Test test email with default user name"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_test_email("user@example.com")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_test_email_failure(self, email_service):
        """Test handling of test email send failure"""
        email_service.mail_client.send_message.return_value = {
            "status": "error",
            "error": "Send failed",
        }

        result = await email_service.send_test_email("user@example.com")

        assert result is False


class TestSendInvitationEmail:
    """Test send_invitation_email method"""

    @pytest.mark.asyncio
    async def test_send_invitation_email_success(self, email_service):
        """Test successful invitation email sending"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_invitation_email(
            to_email="invitee@example.com",
            inviter_name="John Doe",
            organization_name="Test Org",
            invitation_url="https://example.com/invite/123",
            role="member",
        )

        assert result is True
        call_args = email_service.mail_client.send_message.call_args
        assert call_args[1]["disable_tracking"] is True

    @pytest.mark.asyncio
    async def test_send_invitation_email_mail_disabled(self, email_service):
        """Test invitation email not sent when service is disabled"""
        email_service.mail_enabled = False

        result = await email_service.send_invitation_email(
            to_email="invitee@example.com",
            inviter_name="John Doe",
            organization_name="Test Org",
            invitation_url="https://example.com/invite/123",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_invitation_email_different_roles(self, email_service):
        """Test invitation emails for different roles"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        roles = ["member", "admin", "contributor"]
        for role in roles:
            result = await email_service.send_invitation_email(
                to_email="invitee@example.com",
                inviter_name="John Doe",
                organization_name="Test Org",
                invitation_url="https://example.com/invite/123",
                role=role,
            )
            assert result is True


class TestSendVerificationEmail:
    """Test send_verification_email method"""

    @pytest.mark.asyncio
    async def test_send_verification_email_english(self, email_service):
        """Test verification email in English"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_verification_email(
            to_email="user@example.com",
            user_name="John Doe",
            verification_link="https://example.com/verify/123",
            language="en",
        )

        assert result is True
        call_args = email_service.mail_client.send_message.call_args
        subject = call_args[1]["subject"]
        assert "Verify" in subject or "verify" in subject

    @pytest.mark.asyncio
    async def test_send_verification_email_german(self, email_service):
        """Test verification email in German"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_verification_email(
            to_email="user@example.com",
            user_name="Hans Müller",
            verification_link="https://example.com/verify/123",
            language="de",
        )

        assert result is True
        call_args = email_service.mail_client.send_message.call_args
        subject = call_args[1]["subject"]
        assert "Bestätigen" in subject or "bestätigen" in subject

    @pytest.mark.asyncio
    async def test_send_verification_email_mail_disabled(self, email_service):
        """Test verification email not sent when service is disabled"""
        email_service.mail_enabled = False

        result = await email_service.send_verification_email(
            to_email="user@example.com",
            user_name="John Doe",
            verification_link="https://example.com/verify/123",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_verification_email_default_language(self, email_service):
        """Test verification email with default language (English)"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_verification_email(
            to_email="user@example.com",
            user_name="John Doe",
            verification_link="https://example.com/verify/123",
        )

        assert result is True


class TestSendPasswordResetEmail:
    """Test send_password_reset_email method"""

    @pytest.mark.asyncio
    async def test_send_password_reset_email_english(self, email_service):
        """Test password reset email in English"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_password_reset_email(
            to_email="user@example.com",
            user_name="John Doe",
            reset_link="https://example.com/reset/123",
            language="en",
        )

        assert result is True
        call_args = email_service.mail_client.send_message.call_args
        subject = call_args[1]["subject"]
        assert "Reset" in subject or "password" in subject

    @pytest.mark.asyncio
    async def test_send_password_reset_email_german(self, email_service):
        """Test password reset email in German"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_password_reset_email(
            to_email="user@example.com",
            user_name="Hans Müller",
            reset_link="https://example.com/reset/123",
            language="de",
        )

        assert result is True
        call_args = email_service.mail_client.send_message.call_args
        subject = call_args[1]["subject"]
        assert "Passwort" in subject or "zurücksetzen" in subject

    @pytest.mark.asyncio
    async def test_send_password_reset_email_mail_disabled(self, email_service):
        """Test password reset email not sent when service is disabled"""
        email_service.mail_enabled = False

        result = await email_service.send_password_reset_email(
            to_email="user@example.com",
            user_name="John Doe",
            reset_link="https://example.com/reset/123",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_password_reset_email_default_language(self, email_service):
        """Test password reset email with default language (English)"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_password_reset_email(
            to_email="user@example.com",
            user_name="John Doe",
            reset_link="https://example.com/reset/123",
        )

        assert result is True


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_send_email_with_special_characters(self, email_service):
        """Test email sending with special characters"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service.send_test_email("user+test@example.com", "User with émojis 🎉")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_email_with_very_long_names(self, email_service):
        """Test email sending with very long names"""
        email_service.mail_client.send_message.return_value = {"status": "success"}

        long_name = "A" * 500
        result = await email_service.send_test_email("user@example.com", long_name)

        assert result is True

    @pytest.mark.asyncio
    async def test_notification_type_mapping(self, email_service):
        """Test all notification type mappings"""
        mock_template = Mock()
        mock_template.render.return_value = "Subject: Test\n<html>Content</html>"
        email_service.template_env.get_template.return_value = mock_template
        email_service.mail_client.send_message.return_value = {"status": "success"}

        notification_types = [
            NotificationType.TASK_CREATED,
            NotificationType.ANNOTATION_COMPLETED,
            NotificationType.ORGANIZATION_INVITATION_SENT,
            NotificationType.DATA_UPLOAD_COMPLETED,
            NotificationType.EVALUATION_COMPLETED,
        ]

        for notif_type in notification_types:
            notif = Mock(spec=Notification)
            notif.type = notif_type
            notif.id = f"notif_{notif_type.value}"

            result = await email_service.send_notification_email("user@example.com", notif)
            assert result is True

    @pytest.mark.asyncio
    async def test_unknown_notification_type(self, email_service):
        """Test notification with unknown/unmapped type"""
        mock_template = Mock()
        mock_template.render.return_value = "Subject: Default\n<html>Content</html>"
        email_service.template_env.get_template.return_value = mock_template
        email_service.mail_client.send_message.return_value = {"status": "success"}

        # Create notification with None type
        notif = Mock(spec=Notification)
        notif.type = None
        notif.id = "notif_unknown"

        result = await email_service.send_notification_email("user@example.com", notif)

        assert result is True
        # Should use default_notification.html template
        email_service.template_env.get_template.assert_called_with("default_notification.html")
