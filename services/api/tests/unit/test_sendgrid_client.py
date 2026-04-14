"""
Unit tests for SendGrid Email Client
Tests the SendGrid integration for BenGER email functionality
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from sendgrid_client import SendGridClient


class TestSendGridClient:
    """Test SendGrid client functionality"""

    @pytest.fixture
    def sendgrid_client(self):
        """Create a SendGrid client instance for testing"""
        with patch.dict(
            os.environ,
            {
                'SENDGRID_API_KEY': 'test_api_key_123',
                'EMAIL_FROM_ADDRESS': 'test@what-a-benger.net',
                'EMAIL_FROM_NAME': 'Test BenGER',
            },
        ):
            return SendGridClient()

    @pytest.fixture
    def sendgrid_client_no_key(self):
        """Create a SendGrid client without API key"""
        with patch.dict(os.environ, {}, clear=True):
            return SendGridClient()

    def test_initialization_with_env_vars(self, sendgrid_client):
        """Test SendGrid client initialization with environment variables"""
        assert sendgrid_client.api_key == 'test_api_key_123'
        assert sendgrid_client.from_email == 'test@what-a-benger.net'
        assert sendgrid_client.from_name == 'Test BenGER'
        assert sendgrid_client.api_url == 'https://api.sendgrid.com/v3/mail/send'

    def test_initialization_without_api_key(self, sendgrid_client_no_key):
        """Test SendGrid client initialization without API key"""
        assert sendgrid_client_no_key.api_key == ''
        assert sendgrid_client_no_key.from_email == 'noreply@what-a-benger.net'  # Default
        assert sendgrid_client_no_key.from_name == 'BenGER Platform'  # Default

    @patch('requests.post')
    def test_send_message_success(self, mock_post, sendgrid_client):
        """Test successful email sending via SendGrid"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {'X-Message-Id': 'msg_123'}
        mock_post.return_value = mock_response

        result = sendgrid_client.send_message(
            to=['recipient@example.com'],
            subject='Test Email',
            html_body='<p>Test HTML content</p>',
            plain_body='Test plain content',
        )

        assert result['status'] == 'success'
        assert result['message_id'] == 'msg_123'

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == 'https://api.sendgrid.com/v3/mail/send'

        # Verify headers
        headers = call_args[1]['headers']
        assert headers['Authorization'] == 'Bearer test_api_key_123'
        assert headers['Content-Type'] == 'application/json'

        # Verify payload
        payload = call_args[1]['json']
        assert payload['personalizations'][0]['to'][0]['email'] == 'recipient@example.com'
        assert payload['subject'] == 'Test Email'
        assert payload['from']['email'] == 'test@what-a-benger.net'
        assert payload['from']['name'] == 'Test BenGER'

    @patch('requests.post')
    def test_send_message_with_multiple_recipients(self, mock_post, sendgrid_client):
        """Test sending email to multiple recipients"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {'X-Message-Id': 'msg_456'}
        mock_post.return_value = mock_response

        result = sendgrid_client.send_message(
            to=['user1@example.com', 'user2@example.com'],
            subject='Multi-recipient Email',
            html_body='<p>Test</p>',
            cc=['cc@example.com'],
            bcc=['bcc@example.com'],
        )

        assert result['status'] == 'success'

        # Verify payload includes all recipients
        payload = mock_post.call_args[1]['json']
        personalizations = payload['personalizations'][0]
        assert len(personalizations['to']) == 2
        assert personalizations['to'][0]['email'] == 'user1@example.com'
        assert personalizations['to'][1]['email'] == 'user2@example.com'
        assert personalizations['cc'][0]['email'] == 'cc@example.com'
        assert personalizations['bcc'][0]['email'] == 'bcc@example.com'

    @patch('requests.post')
    def test_send_message_with_custom_headers(self, mock_post, sendgrid_client):
        """Test sending email with custom headers"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {'X-Message-Id': 'msg_789'}
        mock_post.return_value = mock_response

        result = sendgrid_client.send_message(
            to=['recipient@example.com'],
            subject='Test with Headers',
            plain_body='Test',
            headers={'X-Custom-Header': 'custom_value', 'X-Campaign-Id': 'campaign_123'},
        )

        assert result['status'] == 'success'

        # Verify custom headers in payload
        payload = mock_post.call_args[1]['json']
        assert payload['headers']['X-Custom-Header'] == 'custom_value'
        assert payload['headers']['X-Campaign-Id'] == 'campaign_123'

    @patch('requests.post')
    def test_send_message_with_reply_to(self, mock_post, sendgrid_client):
        """Test sending email with reply-to address"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {'X-Message-Id': 'msg_101'}
        mock_post.return_value = mock_response

        result = sendgrid_client.send_message(
            to=['recipient@example.com'],
            subject='Test Reply-To',
            plain_body='Test',
            reply_to='support@what-a-benger.net',
        )

        assert result['status'] == 'success'

        # Verify reply-to in payload
        payload = mock_post.call_args[1]['json']
        assert payload['reply_to']['email'] == 'support@what-a-benger.net'

    def test_send_message_without_api_key(self, sendgrid_client_no_key):
        """Test sending email without API key configured"""
        result = sendgrid_client_no_key.send_message(
            to=['recipient@example.com'], subject='Test Email', plain_body='Test'
        )

        assert result['status'] == 'error'
        assert result['error'] == 'SendGrid not configured'

    @patch('requests.post')
    def test_send_message_api_error(self, mock_post, sendgrid_client):
        """Test handling SendGrid API errors"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"errors": [{"message": "Invalid email address"}]}'
        mock_response.json.return_value = {'errors': [{'message': 'Invalid email address'}]}
        mock_post.return_value = mock_response

        result = sendgrid_client.send_message(
            to=['invalid-email'], subject='Test Email', plain_body='Test'
        )

        assert result['status'] == 'error'
        # The error message contains the status code
        assert '400' in result['error']
        # The detailed error should be in the 'details' field
        assert 'details' in result

    @patch('requests.post')
    def test_send_message_network_error(self, mock_post, sendgrid_client):
        """Test handling network errors"""
        mock_post.side_effect = requests.exceptions.RequestException('Network error')

        result = sendgrid_client.send_message(
            to=['recipient@example.com'], subject='Test Email', plain_body='Test'
        )

        assert result['status'] == 'error'
        assert 'Network error' in result['error']

    @patch('requests.post')
    def test_send_message_timeout(self, mock_post, sendgrid_client):
        """Test handling timeout errors"""
        mock_post.side_effect = requests.exceptions.Timeout('Request timeout')

        result = sendgrid_client.send_message(
            to=['recipient@example.com'], subject='Test Email', plain_body='Test'
        )

        assert result['status'] == 'error'
        assert 'timeout' in result['error'].lower()

    @patch('requests.post')
    def test_send_message_rate_limit(self, mock_post, sendgrid_client):
        """Test handling rate limit errors"""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {'X-RateLimit-Reset': '1234567890'}
        mock_response.text = '{"errors": [{"message": "Rate limit exceeded"}]}'
        mock_response.json.return_value = {'errors': [{'message': 'Rate limit exceeded'}]}
        mock_post.return_value = mock_response

        result = sendgrid_client.send_message(
            to=['recipient@example.com'], subject='Test Email', plain_body='Test'
        )

        assert result['status'] == 'error'
        # The error message contains the 429 status code
        assert '429' in result['error']

    def test_environment_specific_configuration(self):
        """Test environment-specific email configuration"""
        # Test production configuration
        with patch.dict(
            os.environ,
            {
                'ENVIRONMENT': 'production',
                'SENDGRID_API_KEY': 'prod_key',
                'EMAIL_FROM_ADDRESS': 'noreply@what-a-benger.net',
                'EMAIL_FROM_NAME': 'BenGER Platform',
            },
        ):
            client = SendGridClient()
            assert client.from_email == 'noreply@what-a-benger.net'
            assert client.from_name == 'BenGER Platform'

        # Test staging configuration (same sender address, different name)
        with patch.dict(
            os.environ,
            {
                'ENVIRONMENT': 'staging',
                'SENDGRID_API_KEY': 'staging_key',
                'EMAIL_FROM_ADDRESS': 'noreply@what-a-benger.net',  # Same verified domain
                'EMAIL_FROM_NAME': 'BenGER Staging',  # Different name to identify staging
            },
        ):
            client = SendGridClient()
            assert client.from_email == 'noreply@what-a-benger.net'
            assert client.from_name == 'BenGER Staging'

    @patch('requests.post')
    def test_bulk_email_sending(self, mock_post, sendgrid_client):
        """Test bulk email sending capabilities"""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {'X-Message-Id': 'msg_bulk'}
        mock_post.return_value = mock_response

        # Test sending to many recipients efficiently
        recipients = [f'user{i}@example.com' for i in range(100)]

        result = sendgrid_client.send_message(
            to=recipients, subject='Bulk Email Test', plain_body='Bulk message'
        )

        assert result['status'] == 'success'

        # Verify SendGrid personalizations are used efficiently
        payload = mock_post.call_args[1]['json']
        # SendGrid recommends max 1000 recipients per personalization
        assert len(payload['personalizations'][0]['to']) <= 1000
