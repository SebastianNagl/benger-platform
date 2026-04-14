"""Extended tests for sendgrid_client.py - payload building and edge cases.

Covers:
- Payload construction with all parameters
- No API key handling
- CC/BCC recipients
- Reply-to
- Custom headers
- Disable tracking
- Plain body + HTML body
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from sendgrid_client import SendGridClient


class TestSendGridClientPayload:

    @patch.dict(os.environ, {"SENDGRID_API_KEY": "test-key"})
    def setup_method(self, method=None):
        self.client = SendGridClient()

    def test_no_api_key_returns_error(self):
        client = SendGridClient()
        client.api_key = ""
        result = client.send_message(to=["test@example.com"], subject="Test")
        assert result["status"] == "error"
        assert "not configured" in result["error"]

    @patch("sendgrid_client.requests.post")
    def test_basic_send_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "msg-123"}
        mock_post.return_value = mock_response

        result = self.client.send_message(
            to=["user@example.com"],
            subject="Test Subject",
            html_body="<p>Hello</p>",
        )
        assert result["status"] == "success"
        assert result["message_id"] == "msg-123"
        assert "user@example.com" in result["recipients"]

    @patch("sendgrid_client.requests.post")
    def test_payload_has_correct_structure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client.send_message(
            to=["a@b.com"],
            subject="Subj",
            html_body="<p>body</p>",
        )

        # Verify the JSON payload
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs.kwargs["json"]
        assert payload["subject"] == "Subj"
        assert payload["personalizations"][0]["to"][0]["email"] == "a@b.com"
        assert any(c["type"] == "text/html" for c in payload["content"])

    @patch("sendgrid_client.requests.post")
    def test_cc_and_bcc(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client.send_message(
            to=["to@b.com"],
            subject="S",
            html_body="<p>b</p>",
            cc=["cc@b.com"],
            bcc=["bcc@b.com"],
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["personalizations"][0]["cc"][0]["email"] == "cc@b.com"
        assert payload["personalizations"][0]["bcc"][0]["email"] == "bcc@b.com"

    @patch("sendgrid_client.requests.post")
    def test_reply_to(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client.send_message(
            to=["to@b.com"],
            subject="S",
            html_body="<p>b</p>",
            reply_to="reply@b.com",
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["reply_to"]["email"] == "reply@b.com"

    @patch("sendgrid_client.requests.post")
    def test_custom_headers(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client.send_message(
            to=["to@b.com"],
            subject="S",
            html_body="<p>b</p>",
            headers={"X-Custom": "value"},
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["headers"]["X-Custom"] == "value"

    @patch("sendgrid_client.requests.post")
    def test_disable_tracking(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client.send_message(
            to=["to@b.com"],
            subject="S",
            html_body="<p>b</p>",
            disable_tracking=True,
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["tracking_settings"]["click_tracking"]["enable"] is False
        assert payload["tracking_settings"]["open_tracking"]["enable"] is False

    @patch("sendgrid_client.requests.post")
    def test_plain_and_html_body(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client.send_message(
            to=["to@b.com"],
            subject="S",
            plain_body="Plain text",
            html_body="<p>HTML</p>",
        )

        payload = mock_post.call_args[1]["json"]
        types = [c["type"] for c in payload["content"]]
        assert "text/plain" in types
        assert "text/html" in types

    @patch("sendgrid_client.requests.post")
    def test_api_error_status(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        result = self.client.send_message(
            to=["to@b.com"],
            subject="S",
            html_body="<p>b</p>",
        )
        assert result["status"] == "error"
        assert "400" in result["error"]

    @patch("sendgrid_client.requests.post")
    def test_network_exception(self, mock_post):
        mock_post.side_effect = ConnectionError("Network error")

        result = self.client.send_message(
            to=["to@b.com"],
            subject="S",
            html_body="<p>b</p>",
        )
        assert result["status"] == "error"
        assert "Network error" in result["error"]

    @patch("sendgrid_client.requests.post")
    def test_custom_from_address(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client.send_message(
            to=["to@b.com"],
            subject="S",
            html_body="<p>b</p>",
            from_address="custom@domain.com",
            from_name="Custom Name",
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["from"]["email"] == "custom@domain.com"
        assert payload["from"]["name"] == "Custom Name"

    @patch("sendgrid_client.requests.post")
    def test_multiple_recipients(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {}
        mock_post.return_value = mock_response

        self.client.send_message(
            to=["a@b.com", "c@d.com", "e@f.com"],
            subject="S",
            html_body="<p>b</p>",
        )

        payload = mock_post.call_args[1]["json"]
        assert len(payload["personalizations"][0]["to"]) == 3
