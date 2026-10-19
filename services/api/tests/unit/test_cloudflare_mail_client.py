"""
Unit tests for the Cloudflare Email Sending client and the EMAIL_PROVIDER switch.

The Cloudflare client keeps SendGridClient's result contract (the workers'
retry rule reads ``status_code``), and the switch routes the BenGER sender
domain to Cloudflare while other brands (vertretbar.net) stay on SendGrid.
"""

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from mailer.cloudflare_client import CloudflareEmailClient, html_to_text
from mailer.mail_client import (
    RoutedMailClient,
    build_mail_client,
    cloudflare_domains,
    mail_provider_name,
)
from mailer.sendgrid_client import SendGridClient

CF_ENV = {
    "CLOUDFLARE_EMAIL_API_TOKEN": "cf-token",
    "CLOUDFLARE_ACCOUNT_ID": "acc123",
    "EMAIL_FROM_ADDRESS": "noreply@what-a-benger.net",
    "EMAIL_FROM_NAME": "BenGER Platform",
}


def _response(status_code, body):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body
    response.text = str(body)
    return response


def _ok(**result):
    return _response(
        200,
        {
            "success": True,
            "errors": [],
            "result": {"message_id": "<m1@what-a-benger.net>", "delivered": [], **result},
        },
    )


@pytest.fixture
def cf_client():
    with patch.dict(os.environ, CF_ENV, clear=True):
        return CloudflareEmailClient()


class TestCloudflareEmailClient:
    def test_endpoint_uses_the_account_id(self, cf_client):
        assert cf_client.api_url == (
            "https://api.cloudflare.com/client/v4/accounts/acc123/email/sending/send"
        )
        assert cf_client.provider == "cloudflare"

    @patch("mailer.cloudflare_client.requests.post")
    def test_send_success_payload_and_result(self, mock_post, cf_client):
        mock_post.return_value = _ok(queued=["a@uni-potsdam.de"])

        result = cf_client.send_message(
            to=["a@uni-potsdam.de"],
            subject="Invitation",
            html_body='<p>Hi</p><a href="https://x.test/accept/1">Accept</a>',
            disable_tracking=True,
        )

        assert result == {
            "status": "success",
            "message_id": "<m1@what-a-benger.net>",
            "recipients": ["a@uni-potsdam.de"],
            "status_code": 200,
        }
        kwargs = mock_post.call_args.kwargs
        assert kwargs["headers"]["Authorization"] == "Bearer cf-token"
        assert kwargs["timeout"] == (5, 15)
        payload = kwargs["json"]
        assert payload["from"] == "BenGER Platform <noreply@what-a-benger.net>"
        assert payload["to"] == ["a@uni-potsdam.de"]
        assert payload["subject"] == "Invitation"
        assert "Accept (https://x.test/accept/1)" in payload["text"]

    @patch("mailer.cloudflare_client.requests.post")
    def test_optional_fields_and_explicit_sender(self, mock_post, cf_client):
        mock_post.return_value = _ok()

        cf_client.send_message(
            to=["a@x.de"],
            subject="S",
            plain_body="plain",
            from_address="team@what-a-benger.net",
            from_name="Team, BenGER",
            reply_to="help@what-a-benger.net",
            cc=["c@x.de"],
            bcc=["b@x.de"],
            headers={"X-Test": "1"},
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["from"] == '"Team, BenGER" <team@what-a-benger.net>'
        assert payload["text"] == "plain"
        assert "html" not in payload
        assert payload["reply_to"] == "help@what-a-benger.net"
        assert payload["cc"] == ["c@x.de"]
        assert payload["bcc"] == ["b@x.de"]
        assert payload["headers"] == {"X-Test": "1"}

    @patch("mailer.cloudflare_client.requests.post")
    def test_invalid_placeholder_is_never_mailed(self, mock_post, cf_client):
        result = cf_client.send_message(to=["lms-123@users.benger.invalid"], subject="S")

        mock_post.assert_not_called()
        assert result["status"] == "error"
        assert result["status_code"] == 400
        assert "provider_rejected" not in result

    @patch("mailer.cloudflare_client.requests.post")
    def test_api_rejection_is_marked_and_masked(self, mock_post, cf_client):
        mock_post.return_value = _response(
            403,
            {
                "success": False,
                "errors": [
                    {"code": 10203, "message": "sending disabled for someone@uni-hamburg.de"}
                ],
            },
        )

        result = cf_client.send_message(to=["someone@uni-hamburg.de"], subject="S")

        assert result["status"] == "error"
        assert result["status_code"] == 403
        assert result["provider_rejected"] is True
        assert "10203" in result["details"]
        assert "someone@uni-hamburg.de" not in result["details"]

    @patch("mailer.cloudflare_client.requests.post")
    def test_throttling_keeps_status_429_for_the_retry_rule(self, mock_post, cf_client):
        mock_post.return_value = _response(
            429, {"success": False, "errors": [{"code": 10004, "message": "throttled"}]}
        )

        result = cf_client.send_message(to=["a@x.de"], subject="S")

        assert result["status_code"] == 429

    @patch("mailer.cloudflare_client.requests.post")
    def test_transport_failure_is_retryable_and_not_rejected(self, mock_post, cf_client):
        mock_post.side_effect = requests.exceptions.ConnectionError("down")

        result = cf_client.send_message(to=["a@x.de"], subject="S")

        assert result["status"] == "error"
        assert result["status_code"] is None
        assert "provider_rejected" not in result

    @patch("mailer.cloudflare_client.requests.post")
    def test_every_recipient_bounced_is_permanent(self, mock_post, cf_client):
        mock_post.return_value = _ok(permanent_bounces=["gone@x.de"])

        result = cf_client.send_message(to=["gone@x.de"], subject="S")

        assert result["status"] == "error"
        assert result["status_code"] == 422
        assert "provider_rejected" not in result

    @patch("mailer.cloudflare_client.requests.post")
    def test_partial_bounce_still_counts_as_sent(self, mock_post, cf_client):
        mock_post.return_value = _ok(permanent_bounces=["gone@x.de"], delivered=["ok@x.de"])

        result = cf_client.send_message(to=["gone@x.de", "ok@x.de"], subject="S")

        assert result["status"] == "success"

    def test_unconfigured_client_rejects_without_calling(self):
        with patch.dict(os.environ, {}, clear=True):
            client = CloudflareEmailClient()
        with patch("mailer.cloudflare_client.requests.post") as mock_post:
            result = client.send_message(to=["a@x.de"], subject="S")
        mock_post.assert_not_called()
        assert result["status"] == "error"
        assert result["provider_rejected"] is True

    @patch("mailer.cloudflare_client.requests.get")
    def test_connection_falls_back_to_the_account_token_path(self, mock_get, cf_client):
        mock_get.side_effect = [
            _response(401, {"success": False}),
            _response(200, {"success": True, "result": {"status": "active"}}),
        ]

        assert asyncio.run(cf_client.test_connection()) is True
        assert mock_get.call_args.args[0].endswith("/accounts/acc123/tokens/verify")


class TestHtmlToText:
    def test_link_labels_keep_their_target_and_bare_urls_stay(self):
        text = html_to_text(
            "<h2>Hello &amp; welcome</h2><p>Click "
            '<a href="https://a.test/x">here</a></p>'
            '<p><a href="https://a.test/y">https://a.test/y</a></p>'
            "<style>p{color:red}</style>"
        )
        assert "Hello & welcome" in text
        assert "here (https://a.test/x)" in text
        assert "https://a.test/y (https://a.test/y)" not in text
        assert "color" not in text


class TestProviderSwitch:
    def test_default_is_sendgrid(self):
        with patch.dict(os.environ, {}, clear=True):
            assert mail_provider_name() == "sendgrid"
            sendgrid_class = MagicMock()
            assert build_mail_client(sendgrid_class) is sendgrid_class.return_value

    def test_unknown_provider_falls_back_to_sendgrid(self):
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "pigeon"}, clear=True):
            assert mail_provider_name() == "sendgrid"

    def test_cloudflare_builds_a_router(self):
        with patch.dict(os.environ, {**CF_ENV, "EMAIL_PROVIDER": "Cloudflare"}, clear=True):
            client = build_mail_client(MagicMock())
        assert isinstance(client, RoutedMailClient)
        assert client.provider == "cloudflare"
        assert client.primary_domains == {"what-a-benger.net"}

    def test_domains_override(self):
        with patch.dict(
            os.environ, {"CLOUDFLARE_EMAIL_DOMAINS": "what-a-benger.net, Vertretbar.net"}
        ):
            assert cloudflare_domains() == {"what-a-benger.net", "vertretbar.net"}


class TestRoutedMailClient:
    @pytest.fixture
    def router(self):
        primary = MagicMock(api_key="cf", from_email="noreply@what-a-benger.net")
        fallback = MagicMock(api_key="sg")
        return RoutedMailClient(primary, fallback, {"what-a-benger.net"})

    def test_benger_sender_goes_through_cloudflare(self, router):
        router.primary.send_message.return_value = {"status": "success"}

        result = router.send_message(to=["a@x.de"], subject="S", html_body="<p>x</p>")

        assert result == {"status": "success"}
        router.fallback.send_message.assert_not_called()

    def test_other_brand_goes_through_sendgrid(self, router):
        router.fallback.send_message.return_value = {"status": "success"}

        router.send_message(to=["a@x.de"], subject="S", from_address="noreply@vertretbar.net")

        router.primary.send_message.assert_not_called()
        assert router.fallback.send_message.call_args.kwargs["from_address"] == (
            "noreply@vertretbar.net"
        )

    def test_cloudflare_rejection_falls_back_to_sendgrid(self, router):
        router.primary.send_message.return_value = {
            "status": "error",
            "status_code": 403,
            "provider_rejected": True,
        }
        router.fallback.send_message.return_value = {"status": "success", "status_code": 202}

        result = router.send_message(to=["a@x.de"], subject="S")

        assert result["status_code"] == 202
        router.fallback.send_message.assert_called_once_with(to=["a@x.de"], subject="S")

    def test_transport_failure_does_not_double_send(self, router):
        router.primary.send_message.return_value = {"status": "error", "status_code": None}

        result = router.send_message(to=["a@x.de"], subject="S")

        assert result["status_code"] is None
        router.fallback.send_message.assert_not_called()

    def test_bounce_is_returned_not_resent(self, router):
        router.primary.send_message.return_value = {"status": "error", "status_code": 422}

        router.send_message(to=["a@x.de"], subject="S")

        router.fallback.send_message.assert_not_called()


class TestSendGridConnection:
    def test_connection_checks_the_key(self):
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "sg"}, clear=True):
            client = SendGridClient()
        with patch("mailer.sendgrid_client.requests.get") as mock_get:
            mock_get.return_value = _response(200, {"scopes": ["mail.send"]})
            assert asyncio.run(client.test_connection()) is True
        assert mock_get.call_args.args[0] == "https://api.sendgrid.com/v3/scopes"

    def test_connection_without_key_is_false(self):
        with patch.dict(os.environ, {}, clear=True):
            client = SendGridClient()
        assert asyncio.run(client.test_connection()) is False


class TestEmailServiceUsesTheSwitch:
    def test_cloudflare_provider_reaches_email_service(self):
        from mailer.email_service import EmailService

        with patch.dict(os.environ, {**CF_ENV, "EMAIL_PROVIDER": "cloudflare"}, clear=True):
            service = EmailService()
        assert isinstance(service.mail_client, RoutedMailClient)
        assert service.is_available()
