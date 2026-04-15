"""
Integration tests for Workers email service
Tests end-to-end email workflows and integration with external services
Coverage target: Critical integration paths for Phase 1 Week 3
"""

from unittest.mock import Mock, patch

import pytest

from email_service import EmailService
from models import Notification, NotificationType
from sendgrid_client import SendGridClient


@pytest.fixture
def email_service_integration():
    """Create EmailService with real dependencies mocked at integration points"""
    with patch('email_service.SendGridClient') as mock_sg_class:
        mock_sg_client = Mock()
        mock_sg_client.api_key = "test_api_key"
        mock_sg_class.return_value = mock_sg_client

        service = EmailService()
        service.mail_enabled = True
        service.mail_client = mock_sg_client
        return service


@pytest.fixture
def mock_sendgrid_response():
    """Create mock SendGrid API response"""
    response = Mock()
    response.status_code = 202
    response.headers = {'X-Message-Id': 'msg_123456'}
    response.text = 'Accepted'
    return response


class TestEmailServiceIntegration:
    """Integration tests for email service workflows"""

    @pytest.mark.asyncio
    async def test_verification_email_end_to_end(
        self, email_service_integration, mock_sendgrid_response
    ):
        """Test complete verification email workflow"""
        email_service_integration.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service_integration.send_verification_email(
            to_email="newuser@example.com",
            user_name="Test User",
            verification_link="https://example.com/verify/abc123",
            language="en",
        )

        assert result is True
        email_service_integration.mail_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_invitation_email_end_to_end(
        self, email_service_integration, mock_sendgrid_response
    ):
        """Test complete invitation email workflow"""
        email_service_integration.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service_integration.send_invitation_email(
            to_email="invitee@example.com",
            inviter_name="Admin User",
            organization_name="Test Org",
            invitation_url="https://example.com/invite/xyz789",
            role="member",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_password_reset_email_end_to_end(
        self, email_service_integration, mock_sendgrid_response
    ):
        """Test complete password reset email workflow"""
        email_service_integration.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service_integration.send_password_reset_email(
            to_email="user@example.com",
            user_name="Existing User",
            reset_link="https://example.com/reset/reset123",
            language="de",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_notification_email_with_template_rendering(
        self, email_service_integration, mock_sendgrid_response
    ):
        """Test notification email with template rendering"""
        notification = Mock(spec=Notification)
        notification.type = NotificationType.TASK_COMPLETED
        notification.id = "notif_integration_test"
        notification.message = "Your task has been completed"

        # Mock template rendering
        mock_template = Mock()
        mock_template.render.return_value = (
            "Subject: Task Completed\n<html>Your task is done!</html>"
        )

        with patch.object(
            email_service_integration.template_env, 'get_template', return_value=mock_template
        ):
            email_service_integration.mail_client.send_message.return_value = {"status": "success"}

            result = await email_service_integration.send_notification_email(
                user_email="user@example.com", notification=notification
            )

            assert result is True
            email_service_integration.template_env.get_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_service_with_sendgrid_failure(self, email_service_integration):
        """Test email service handles SendGrid API failures gracefully"""
        email_service_integration.mail_client.send_message.return_value = {
            "status": "error",
            "error": "SendGrid API error",
        }

        result = await email_service_integration.send_test_email("user@example.com", "Test User")

        assert result is False

    @pytest.mark.asyncio
    async def test_email_service_with_network_timeout(self, email_service_integration):
        """Test email service handles network timeouts"""
        email_service_integration.mail_client.send_message.side_effect = Exception(
            "Connection timeout"
        )

        result = await email_service_integration.send_test_email("user@example.com", "Test User")

        assert result is False


class TestSendGridClientIntegration:
    """Integration tests for SendGrid client"""

    def test_sendgrid_client_initialization_with_env(self):
        """Test SendGrid client reads API key from environment"""
        import os

        with patch.dict(os.environ, {'SENDGRID_API_KEY': 'test_api_key_123'}):
            client = SendGridClient()
            assert client.api_key == 'test_api_key_123'

    def test_sendgrid_client_request_formation(self, mock_sendgrid_response):
        """Test that SendGrid client forms correct API requests"""

        client = SendGridClient()
        client.api_key = "test_key"

        with patch('requests.post', return_value=mock_sendgrid_response) as mock_post:
            result = client.send_message(
                to=["recipient@example.com"], subject="Test Email", html_body="<p>Test content</p>"
            )

            # Verify request was made correctly
            mock_post.assert_called_once()
            call_args = mock_post.call_args

            # Check URL
            assert call_args[0][0] == "https://api.sendgrid.com/v3/mail/send"

            # Check headers
            headers = call_args[1]['headers']
            assert 'Authorization' in headers
            assert headers['Content-Type'] == 'application/json'

            assert result['status'] == 'success'

    def test_sendgrid_client_retry_logic_on_429(self):
        """Test SendGrid client handles rate limiting"""
        client = SendGridClient()
        client.api_key = "test_key"

        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_response.text = "Rate limit exceeded"

        with patch('requests.post', return_value=rate_limit_response):
            result = client.send_message(to=["test@example.com"], subject="Test", html_body="Test")

            assert result['status'] == 'error'
            assert '429' in result['error']


class TestMultiLanguageSupport:
    """Integration tests for multi-language email support"""

    @pytest.mark.asyncio
    async def test_german_verification_email(
        self, email_service_integration, mock_sendgrid_response
    ):
        """Test German language verification email"""
        email_service_integration.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service_integration.send_verification_email(
            to_email="benutzer@beispiel.de",
            user_name="Hans Müller",
            verification_link="https://example.com/verify/test",
            language="de",
        )

        # Verify email was sent
        assert result is True
        email_service_integration.mail_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_german_password_reset_email(
        self, email_service_integration, mock_sendgrid_response
    ):
        """Test German language password reset email"""
        email_service_integration.mail_client.send_message.return_value = {"status": "success"}

        result = await email_service_integration.send_password_reset_email(
            to_email="benutzer@beispiel.de",
            user_name="Hans Müller",
            reset_link="https://example.com/reset/test",
            language="de",
        )

        assert result is True
        email_service_integration.mail_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_to_english(self, email_service_integration, mock_sendgrid_response):
        """Test fallback to English for unsupported languages"""
        email_service_integration.mail_client.send_message.return_value = {"status": "success"}

        # Use default language (should be English)
        result = await email_service_integration.send_verification_email(
            to_email="user@example.com",
            user_name="User",
            verification_link="https://example.com/verify/test",
        )

        assert result is True


class TestEmailServiceResilience:
    """Integration tests for email service error handling and resilience"""

    @pytest.mark.asyncio
    async def test_graceful_degradation_with_template_errors(
        self, email_service_integration, mock_sendgrid_response
    ):
        """Test email service continues with fallback when templates fail"""
        notification = Mock(spec=Notification)
        notification.type = NotificationType.TASK_COMPLETED
        notification.id = "test_notif"

        # Simulate template error
        with patch.object(
            email_service_integration.template_env,
            'get_template',
            side_effect=Exception("Template not found"),
        ):
            email_service_integration.mail_client.send_message.return_value = {"status": "success"}

            result = await email_service_integration.send_notification_email(
                user_email="user@example.com", notification=notification
            )

            # Should succeed with fallback template
            assert result is True

    @pytest.mark.asyncio
    async def test_feature_flag_disabled_scenario(self):
        """Test email service behavior when mail is disabled"""
        service = EmailService()
        service.mail_enabled = False

        result = await service.send_test_email("user@example.com")

        # Should return False when disabled
        assert result is False

    @pytest.mark.asyncio
    async def test_concurrent_email_sending(
        self, email_service_integration, mock_sendgrid_response
    ):
        """Test email service handles concurrent requests"""
        import asyncio

        email_service_integration.mail_client.send_message.return_value = {"status": "success"}

        # Send multiple emails concurrently
        tasks = [
            email_service_integration.send_test_email(f"user{i}@example.com", f"User {i}")
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(results)
        assert len(results) == 10


class TestEmailServiceConfiguration:
    """Integration tests for email service configuration"""

    def test_email_service_reads_environment_config(self):
        """Test email service reads configuration from environment"""
        import os

        env_vars = {
            'MAIL_SMTP_HOST': 'smtp.custom.com',
            'MAIL_SMTP_PORT': '587',
            'MAIL_FROM_EMAIL': 'custom@example.com',
            'MAIL_FROM_NAME': 'Custom Name',
        }

        with patch.dict(os.environ, env_vars):
            service = EmailService()

            assert service.smtp_host == 'smtp.custom.com'
            assert service.smtp_port == 587
            assert service.from_email == 'custom@example.com'
            assert service.from_name == 'Custom Name'

    def test_email_service_default_configuration(self):
        """Test email service uses correct defaults"""
        service = EmailService()

        assert service.smtp_host == 'mail'
        assert service.smtp_port == 25
        assert service.from_email == 'noreply@what-a-benger.net'
        assert service.from_name == 'BenGER Platform'
