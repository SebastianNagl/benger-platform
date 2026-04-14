"""Coverage tests for sendgrid_client.py payload building.

Tests the send_message method's payload construction and error handling
without making actual API calls.
"""

import sys
import os
from unittest.mock import patch, MagicMock

workers_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, workers_root)


class TestSendGridClientInit:
    def test_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            from sendgrid_client import SendGridClient
            client = SendGridClient()
            assert client.api_key == ""

    def test_with_api_key(self):
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "test-key"}):
            from sendgrid_client import SendGridClient
            client = SendGridClient()
            assert client.api_key == "test-key"


class TestSendMessage:
    def _make_client(self):
        from sendgrid_client import SendGridClient
        client = SendGridClient()
        client.api_key = "test-key"
        return client

    @patch("sendgrid_client.requests.post")
    def test_basic_send(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.headers = {"X-Message-Id": "msg-123"}
        mock_post.return_value = mock_resp

        client = self._make_client()
        result = client.send_message(
            to=["test@example.com"],
            subject="Test Subject",
            html_body="<p>Hello</p>",
        )
        assert result["status"] == "success"
        assert result["message_id"] == "msg-123"

    @patch("sendgrid_client.requests.post")
    def test_with_cc_bcc(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        client = self._make_client()
        result = client.send_message(
            to=["to@test.com"],
            subject="Test",
            html_body="<p>Hi</p>",
            cc=["cc@test.com"],
            bcc=["bcc@test.com"],
        )
        assert result["status"] == "success"
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert len(payload["personalizations"][0]["cc"]) == 1
        assert len(payload["personalizations"][0]["bcc"]) == 1

    @patch("sendgrid_client.requests.post")
    def test_with_reply_to(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        client = self._make_client()
        client.send_message(
            to=["to@test.com"],
            subject="Test",
            html_body="<p>Hi</p>",
            reply_to="reply@test.com",
        )
        payload = mock_post.call_args[1]["json"]
        assert payload["reply_to"]["email"] == "reply@test.com"

    @patch("sendgrid_client.requests.post")
    def test_with_custom_headers(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        client = self._make_client()
        client.send_message(
            to=["to@test.com"],
            subject="Test",
            html_body="<p>Hi</p>",
            headers={"X-Custom": "value"},
        )
        payload = mock_post.call_args[1]["json"]
        assert payload["headers"]["X-Custom"] == "value"

    @patch("sendgrid_client.requests.post")
    def test_disable_tracking(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        client = self._make_client()
        client.send_message(
            to=["to@test.com"],
            subject="Test",
            html_body="<p>Hi</p>",
            disable_tracking=True,
        )
        payload = mock_post.call_args[1]["json"]
        assert payload["tracking_settings"]["click_tracking"]["enable"] is False

    @patch("sendgrid_client.requests.post")
    def test_plain_body(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        client = self._make_client()
        client.send_message(
            to=["to@test.com"],
            subject="Test",
            plain_body="Hello plain",
        )
        payload = mock_post.call_args[1]["json"]
        assert any(c["type"] == "text/plain" for c in payload["content"])

    @patch("sendgrid_client.requests.post")
    def test_api_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_post.return_value = mock_resp

        client = self._make_client()
        result = client.send_message(
            to=["to@test.com"],
            subject="Test",
            html_body="<p>Hi</p>",
        )
        assert result["status"] == "error"

    @patch("sendgrid_client.requests.post")
    def test_exception(self, mock_post):
        mock_post.side_effect = Exception("Connection error")

        client = self._make_client()
        result = client.send_message(
            to=["to@test.com"],
            subject="Test",
            html_body="<p>Hi</p>",
        )
        assert result["status"] == "error"
        assert "Connection error" in result["error"]

    def test_no_api_key_returns_error(self):
        from sendgrid_client import SendGridClient
        client = SendGridClient()
        client.api_key = ""
        result = client.send_message(
            to=["to@test.com"],
            subject="Test",
            html_body="<p>Hi</p>",
        )
        assert result["status"] == "error"
        assert "not configured" in result["error"]

    @patch("sendgrid_client.requests.post")
    def test_custom_from(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        client = self._make_client()
        client.send_message(
            to=["to@test.com"],
            subject="Test",
            html_body="<p>Hi</p>",
            from_address="custom@test.com",
            from_name="Custom Sender",
        )
        payload = mock_post.call_args[1]["json"]
        assert payload["from"]["email"] == "custom@test.com"
        assert payload["from"]["name"] == "Custom Sender"
