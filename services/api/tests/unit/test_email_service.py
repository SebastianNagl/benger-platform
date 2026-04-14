"""
Unit tests for Email Service
Tests the email service functionality including SendGrid integration
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from email_service import EmailService
from models import NotificationType


class TestEmailService:
    """Test email service functionality"""

    @pytest.fixture
    def email_service(self):
        """Create an email service instance for testing"""
        with patch('services.email.email_service.SendGridClient') as mock_client:
            with patch('database.SessionLocal'):
                service = EmailService()
                service.mail_client = mock_client.return_value
                return service

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        with patch('database.SessionLocal') as mock_session:
            session = MagicMock()
            mock_session.return_value = session
            yield session

    def test_initialization(self, email_service):
        """Test email service initialization"""
        assert email_service.smtp_host == 'mail'  # Default
        assert email_service.smtp_port == 25  # Default
        assert email_service.from_email == 'noreply@what-a-benger.net'  # Default
        assert email_service.from_name == 'BenGER Platform'  # Default
        assert email_service.mail_client is not None

    def test_feature_flag_check(self, mock_db_session):
        """Test email service feature flag checking"""
        # Test with feature flag enabled
        mock_flag = MagicMock()
        mock_flag.is_enabled = True
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_flag

        with patch('database.SessionLocal', return_value=mock_db_session):
            service = EmailService()
            assert service.mail_enabled == True

        # Test with feature flag disabled
        mock_flag.is_enabled = False
        with patch('database.SessionLocal', return_value=mock_db_session):
            service = EmailService()
            assert service.mail_enabled == False

        # Test with no feature flag (default to enabled)
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        with patch('database.SessionLocal', return_value=mock_db_session):
            service = EmailService()
            assert service.mail_enabled == True

    def test_template_environment_initialization(self, email_service):
        """Test Jinja2 template environment initialization"""
        assert email_service.template_env is not None
        assert email_service.template_env.autoescape == True
        assert 'format_date' in email_service.template_env.filters

    @patch('services.email.email_service.Path.exists')
    def test_template_directory_creation(self, mock_exists):
        """Test template directory creation if not exists"""
        mock_exists.return_value = False

        with patch('services.email.email_service.Path.mkdir') as mock_mkdir:
            with patch('services.email.email_service.SendGridClient'):
                with patch('database.SessionLocal'):
                    EmailService()
                    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_render_template(self, email_service):
        """Test email template rendering"""
        # Mock template
        mock_template = MagicMock()
        mock_template.render.return_value = "Subject: Test Subject\n\nTest Body Content"
        email_service.template_env.get_template = MagicMock(return_value=mock_template)

        subject, body = email_service._render_template(
            'test_template.html', {'name': 'John', 'organization': 'BenGER'}
        )

        assert subject == 'Test Subject'
        assert body == 'Test Body Content'
        mock_template.render.assert_called_once_with(name='John', organization='BenGER')

    def test_render_template_without_subject(self, email_service):
        """Test template rendering without subject line"""
        mock_template = MagicMock()
        mock_template.render.return_value = "Just body content without subject"
        email_service.template_env.get_template = MagicMock(return_value=mock_template)

        subject, body = email_service._render_template('no_subject.html', {'content': 'test'})

        assert subject == 'BenGER Notification'  # Default subject
        assert body == 'Just body content without subject'

    @pytest.mark.asyncio
    async def test_send_invitation_email(self, email_service):
        """Test sending invitation emails"""
        email_service.mail_client.send_message = MagicMock(
            return_value={'status': 'success', 'message_id': 'msg_123'}
        )

        result = await email_service.send_invitation_email(
            'newuser@example.com',
            'org_admin',
            'TUM Research Group',
            'https://what-a-benger.net/invite/token123',
            'Welcome to our research group!',
        )

        assert result == True
        email_service.mail_client.send_message.assert_called_once()

        call_args = email_service.mail_client.send_message.call_args
        assert call_args[1]['to'] == ['newuser@example.com']
        assert 'Invitation' in call_args[1]['subject']
        assert 'TUM Research Group' in call_args[1]['html_body']
        assert 'org_admin' in call_args[1]['html_body']
        assert 'https://what-a-benger.net/invite/token123' in call_args[1]['html_body']

    @pytest.mark.asyncio
    async def test_send_invitation_email_disabled(self, email_service):
        """Test invitation email when mail is disabled"""
        email_service.mail_enabled = False

        result = await email_service.send_invitation_email(
            'newuser@example.com', 'user', 'Test Org', 'https://test.com/invite', 'Welcome'
        )

        assert result == False
        email_service.mail_client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_password_reset_email(self, email_service):
        """Test sending password reset emails"""
        email_service.mail_client.send_message = MagicMock(
            return_value={'status': 'success', 'message_id': 'msg_reset'}
        )

        result = await email_service.send_password_reset_email(
            'user@example.com', 'Test User', 'https://what-a-benger.net/reset/token456'
        )

        assert result == True
        email_service.mail_client.send_message.assert_called_once()

        call_args = email_service.mail_client.send_message.call_args
        assert call_args[1]['to'] == ['user@example.com']
        assert (
            'password' in call_args[1]['subject'].lower()
            or 'reset' in call_args[1]['subject'].lower()
        )
        assert 'https://what-a-benger.net/reset/token456' in call_args[1]['html_body']

    @pytest.mark.asyncio
    async def test_send_verification_email(self, email_service):
        """Test sending verification emails"""
        email_service.mail_client.send_message = MagicMock(
            return_value={'status': 'success', 'message_id': 'msg_verify'}
        )

        result = await email_service.send_verification_email(
            'newuser@example.com', 'New User', 'https://what-a-benger.net/verify/token789'
        )

        assert result == True
        email_service.mail_client.send_message.assert_called_once()

        call_args = email_service.mail_client.send_message.call_args
        assert call_args[1]['to'] == ['newuser@example.com']
        assert 'Verify' in call_args[1]['subject'] or 'Confirmation' in call_args[1]['subject']
        assert 'https://what-a-benger.net/verify/token789' in call_args[1]['html_body']

    @pytest.mark.asyncio
    async def test_send_notification_email(self, email_service):
        """Test sending notification emails"""
        email_service.mail_client.send_message = MagicMock(
            return_value={'status': 'success', 'message_id': 'msg_notify'}
        )

        notification = MagicMock()
        notification.type = NotificationType.PROJECT_UPDATED
        notification.title = 'Project Updated'
        notification.message = 'Your project has been updated'
        notification.metadata = {'project_name': 'Research Project'}

        result = await email_service.send_notification_email('user@example.com', notification)

        assert result == True
        email_service.mail_client.send_message.assert_called_once()

        call_args = email_service.mail_client.send_message.call_args
        assert call_args[1]['to'] == ['user@example.com']
        assert 'Notification' in call_args[1]['subject'] or 'Project' in call_args[1]['subject']
        assert call_args[1]['html_body'] is not None  # Just check that html_body exists

    @pytest.mark.asyncio
    async def test_handle_sendgrid_error(self, email_service):
        """Test handling SendGrid API errors"""
        email_service.mail_client.send_message = MagicMock(
            return_value={'status': 'error', 'error': 'Rate limit exceeded'}
        )

        result = await email_service.send_verification_email(
            'user@example.com', 'Test User', 'https://test.com/verify'
        )

        assert result == False

    # Removed test_send_bulk_emails - method doesn't exist
    # Removed test_send_bulk_emails_with_failures - method doesn't exist
    # Removed test_send_email_with_template - method doesn't exist
    # Removed test_email_with_attachments - method doesn't exist

    def test_environment_specific_sender(self):
        """Test environment-specific sender configuration"""
        # Test production
        with patch.dict(
            os.environ,
            {
                'ENVIRONMENT': 'production',
                'MAIL_FROM_EMAIL': 'noreply@what-a-benger.net',
                'MAIL_FROM_NAME': 'BenGER Platform',
            },
        ):
            with patch('services.email.email_service.SendGridClient'):
                with patch('database.SessionLocal'):
                    service = EmailService()
                    assert service.from_email == 'noreply@what-a-benger.net'
                    assert service.from_name == 'BenGER Platform'

        # Test staging (same sender address, different name)
        with patch.dict(
            os.environ,
            {
                'ENVIRONMENT': 'staging',
                'MAIL_FROM_EMAIL': 'noreply@what-a-benger.net',  # Same verified domain
                'MAIL_FROM_NAME': 'BenGER Staging',  # Different name to identify staging
            },
        ):
            with patch('services.email.email_service.SendGridClient'):
                with patch('database.SessionLocal'):
                    service = EmailService()
                    assert service.from_email == 'noreply@what-a-benger.net'
                    assert service.from_name == 'BenGER Staging'

    # Removed test_retry_on_failure - send_with_retry method doesn't exist
    # Removed test_email_queue_integration - queue_email method doesn't exist
    # Removed test_track_email_delivery - track_delivery method doesn't exist
