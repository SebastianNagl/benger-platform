"""
Comprehensive tests for SendGrid client
Tests email delivery, API error handling, retry logic, validation
Coverage target: 100% of sendgrid_client.py
"""

import os
from unittest.mock import Mock, patch

import pytest
import requests

from sendgrid_client import SendGridClient


@pytest.fixture
def sendgrid_client():
    """Create a SendGrid client for testing"""
    with patch.dict(
        os.environ,
        {
            "SENDGRID_API_KEY": "test_api_key_123",
            "EMAIL_FROM_ADDRESS": "test@example.com",
            "EMAIL_FROM_NAME": "Test Service",
        },
    ):
        return SendGridClient()


@pytest.fixture
def sendgrid_client_no_key():
    """Create a SendGrid client without API key"""
    with patch.dict(
        os.environ,
        {
            "SENDGRID_API_KEY": "",
            "EMAIL_FROM_ADDRESS": "test@example.com",
            "EMAIL_FROM_NAME": "Test Service",
        },
    ):
        return SendGridClient()


class TestSendGridClientInitialization:
    """Test SendGrid client initialization"""

    def test_init_with_api_key(self, sendgrid_client):
        """Test initialization with API key"""
        assert sendgrid_client.api_key == "test_api_key_123"
        assert sendgrid_client.from_email == "test@example.com"
        assert sendgrid_client.from_name == "Test Service"
        assert sendgrid_client.api_url == "https://api.sendgrid.com/v3/mail/send"

    def test_init_without_api_key(self, sendgrid_client_no_key):
        """Test initialization without API key logs warning"""
        assert sendgrid_client_no_key.api_key == ""
        assert sendgrid_client_no_key.from_email == "test@example.com"

    def test_init_with_default_values(self):
        """Test initialization with default environment values"""
        with patch.dict(os.environ, {}, clear=True):
            client = SendGridClient()
            assert client.api_key == ""
            assert client.from_email == "noreply@what-a-benger.net"
            assert client.from_name == "BenGER Platform"


class TestSendMessage:
    """Test send_message functionality"""

    def test_send_message_success(self, sendgrid_client):
        """Test successful email delivery"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_message_id_123"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"],
                subject="Test Subject",
                html_body="<p>Test HTML</p>",
                plain_body="Test plain text",
            )

            assert result["status"] == "success"
            assert result["message_id"] == "test_message_id_123"
            assert result["recipients"] == ["recipient@example.com"]

            # Verify API call
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer test_api_key_123"
            assert call_kwargs["headers"]["Content-Type"] == "application/json"

            # Verify payload structure
            payload = call_kwargs["json"]
            assert payload["subject"] == "Test Subject"
            assert payload["from"]["email"] == "test@example.com"
            assert payload["from"]["name"] == "Test Service"
            assert len(payload["personalizations"][0]["to"]) == 1
            assert payload["personalizations"][0]["to"][0]["email"] == "recipient@example.com"
            assert len(payload["content"]) == 2  # Both plain and HTML

    def test_send_message_without_api_key(self, sendgrid_client_no_key):
        """Test send_message fails gracefully without API key"""
        result = sendgrid_client_no_key.send_message(
            to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
        )

        assert result["status"] == "error"
        assert result["error"] == "SendGrid not configured"

    def test_send_message_with_custom_from(self, sendgrid_client):
        """Test email with custom from address and name"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"],
                subject="Test",
                html_body="<p>Test</p>",
                from_address="custom@example.com",
                from_name="Custom Name",
            )

            payload = mock_post.call_args[1]["json"]
            assert payload["from"]["email"] == "custom@example.com"
            assert payload["from"]["name"] == "Custom Name"
            assert result["status"] == "success"

    def test_send_message_with_cc_bcc(self, sendgrid_client):
        """Test email with CC and BCC recipients"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["to@example.com"],
                subject="Test",
                html_body="<p>Test</p>",
                cc=["cc1@example.com", "cc2@example.com"],
                bcc=["bcc@example.com"],
            )

            payload = mock_post.call_args[1]["json"]
            assert len(payload["personalizations"][0]["cc"]) == 2
            assert payload["personalizations"][0]["cc"][0]["email"] == "cc1@example.com"
            assert len(payload["personalizations"][0]["bcc"]) == 1
            assert payload["personalizations"][0]["bcc"][0]["email"] == "bcc@example.com"
            assert result["status"] == "success"

    def test_send_message_with_reply_to(self, sendgrid_client):
        """Test email with reply-to address"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"],
                subject="Test",
                html_body="<p>Test</p>",
                reply_to="reply@example.com",
            )

            payload = mock_post.call_args[1]["json"]
            assert payload["reply_to"]["email"] == "reply@example.com"
            assert result["status"] == "success"

    def test_send_message_with_custom_headers(self, sendgrid_client):
        """Test email with custom headers"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            custom_headers = {"X-Custom-Header": "custom_value", "X-Priority": "high"}

            result = sendgrid_client.send_message(
                to=["recipient@example.com"],
                subject="Test",
                html_body="<p>Test</p>",
                headers=custom_headers,
            )

            payload = mock_post.call_args[1]["json"]
            assert payload["headers"]["X-Custom-Header"] == "custom_value"
            assert payload["headers"]["X-Priority"] == "high"
            assert result["status"] == "success"

    def test_send_message_with_tracking_disabled(self, sendgrid_client):
        """Test email with tracking disabled (important for verification emails)"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"],
                subject="Test",
                html_body="<p>Test with <a href='http://example.com'>link</a></p>",
                disable_tracking=True,
            )

            payload = mock_post.call_args[1]["json"]
            assert "tracking_settings" in payload
            assert payload["tracking_settings"]["click_tracking"]["enable"] is False
            assert payload["tracking_settings"]["click_tracking"]["enable_text"] is False
            assert payload["tracking_settings"]["open_tracking"]["enable"] is False
            assert result["status"] == "success"

    def test_send_message_plain_text_only(self, sendgrid_client):
        """Test sending plain text only email"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"],
                subject="Plain text test",
                plain_body="This is plain text only",
            )

            payload = mock_post.call_args[1]["json"]
            assert len(payload["content"]) == 1
            assert payload["content"][0]["type"] == "text/plain"
            assert payload["content"][0]["value"] == "This is plain text only"
            assert result["status"] == "success"

    def test_send_message_html_only(self, sendgrid_client):
        """Test sending HTML only email"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"],
                subject="HTML test",
                html_body="<p>This is HTML only</p>",
            )

            payload = mock_post.call_args[1]["json"]
            assert len(payload["content"]) == 1
            assert payload["content"][0]["type"] == "text/html"
            assert payload["content"][0]["value"] == "<p>This is HTML only</p>"
            assert result["status"] == "success"

    def test_send_message_multiple_recipients(self, sendgrid_client):
        """Test sending to multiple recipients"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]
            result = sendgrid_client.send_message(
                to=recipients, subject="Test", html_body="<p>Test</p>"
            )

            payload = mock_post.call_args[1]["json"]
            assert len(payload["personalizations"][0]["to"]) == 3
            assert result["recipients"] == recipients
            assert result["status"] == "success"


class TestSendMessageErrorHandling:
    """Test error handling in send_message"""

    def test_sendgrid_api_400_error(self, sendgrid_client):
        """Test handling of 400 Bad Request error"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid request parameters"

        with patch('requests.post', return_value=mock_response):
            result = sendgrid_client.send_message(
                to=["invalid@@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "error"
            assert "400" in result["error"]
            assert "details" in result
            assert result["recipients"] == ["invalid@@example.com"]

    def test_sendgrid_api_429_rate_limit(self, sendgrid_client):
        """Test handling of 429 Rate Limit error"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        with patch('requests.post', return_value=mock_response):
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "error"
            assert "429" in result["error"]

    def test_sendgrid_api_500_error(self, sendgrid_client):
        """Test handling of 500 Internal Server Error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        with patch('requests.post', return_value=mock_response):
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "error"
            assert "500" in result["error"]

    def test_sendgrid_api_503_service_unavailable(self, sendgrid_client):
        """Test handling of 503 Service Unavailable"""
        mock_response = Mock()
        mock_response.status_code = 503
        mock_response.text = "Service temporarily unavailable"

        with patch('requests.post', return_value=mock_response):
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "error"
            assert "503" in result["error"]

    def test_network_exception(self, sendgrid_client):
        """Test handling of network connection errors"""
        with patch(
            'requests.post', side_effect=requests.exceptions.ConnectionError("Network error")
        ):
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "error"
            assert "Network error" in result["error"]
            assert result["recipients"] == ["recipient@example.com"]

    def test_timeout_exception(self, sendgrid_client):
        """Test handling of timeout errors"""
        with patch('requests.post', side_effect=requests.exceptions.Timeout("Request timed out")):
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "error"
            assert "timed out" in result["error"].lower()

    def test_generic_exception(self, sendgrid_client):
        """Test handling of unexpected exceptions"""
        with patch('requests.post', side_effect=Exception("Unexpected error")):
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "error"
            assert "Unexpected error" in result["error"]


class TestSendMessageResponseCodes:
    """Test different SendGrid API success response codes"""

    @pytest.mark.parametrize("status_code", [200, 201, 202])
    def test_success_status_codes(self, sendgrid_client, status_code):
        """Test that all 2xx status codes are treated as success"""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.headers = {"X-Message-Id": f"test_id_{status_code}"}

        with patch('requests.post', return_value=mock_response):
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "success"
            assert result["message_id"] == f"test_id_{status_code}"

    def test_message_id_fallback(self, sendgrid_client):
        """Test fallback when message ID is not in response headers"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {}  # No X-Message-Id header

        with patch('requests.post', return_value=mock_response):
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Test", html_body="<p>Test</p>"
            )

            assert result["status"] == "success"
            assert result["message_id"] == "unknown"


class TestVerifyWebhookSignature:
    """Test webhook signature verification"""

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_always_true(self, sendgrid_client):
        """Test that webhook verification currently returns True (placeholder)"""
        result = await sendgrid_client.verify_webhook_signature(
            signature="test_signature", payload=b"test_payload"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_with_empty_signature(self, sendgrid_client):
        """Test webhook verification with empty signature"""
        result = await sendgrid_client.verify_webhook_signature(
            signature="", payload=b"test_payload"
        )

        # Currently returns True as it's a placeholder
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_webhook_signature_with_empty_payload(self, sendgrid_client):
        """Test webhook verification with empty payload"""
        result = await sendgrid_client.verify_webhook_signature(
            signature="test_signature", payload=b""
        )

        assert result is True


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_send_message_with_very_long_subject(self, sendgrid_client):
        """Test email with very long subject line"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        long_subject = "A" * 1000  # Very long subject

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject=long_subject, html_body="<p>Test</p>"
            )

            payload = mock_post.call_args[1]["json"]
            assert payload["subject"] == long_subject
            assert result["status"] == "success"

    def test_send_message_with_special_characters_in_subject(self, sendgrid_client):
        """Test email with special characters in subject"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        special_subject = "Test with émojis 🎉 and special chars: <>&\"'"

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject=special_subject, html_body="<p>Test</p>"
            )

            payload = mock_post.call_args[1]["json"]
            assert payload["subject"] == special_subject
            assert result["status"] == "success"

    def test_send_message_with_unicode_content(self, sendgrid_client):
        """Test email with Unicode content"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        unicode_content = "<p>German: Über, French: Château, Japanese: 日本語, Emoji: 😀</p>"

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(
                to=["recipient@example.com"], subject="Unicode test", html_body=unicode_content
            )

            payload = mock_post.call_args[1]["json"]
            assert unicode_content in str(payload["content"])
            assert result["status"] == "success"

    def test_send_message_with_empty_to_list(self, sendgrid_client):
        """Test behavior with empty recipient list"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "test_id"}

        with patch('requests.post', return_value=mock_response) as mock_post:
            result = sendgrid_client.send_message(to=[], subject="Test", html_body="<p>Test</p>")

            # Should still attempt to send (SendGrid will handle validation)
            payload = mock_post.call_args[1]["json"]
            assert len(payload["personalizations"][0]["to"]) == 0
