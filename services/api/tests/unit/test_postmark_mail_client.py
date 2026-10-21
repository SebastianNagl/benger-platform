"""
Unit tests for the Postmark client and its place in RoutedMailClient.

Postmark is the fallback for account-critical mail only: it is tried after a
Cloudflare rejection when the caller marks the mail ``essential``, it stops at
its monthly budget, and anything it rejects still reaches SendGrid.
"""

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from mailer import postmark_client
from mailer.mail_client import RoutedMailClient, build_mail_client
from mailer.postmark_client import PostmarkEmailClient

PM_ENV = {
    "POSTMARK_SERVER_TOKEN": "pm-token",
    "EMAIL_FROM_ADDRESS": "noreply@what-a-benger.net",
    "EMAIL_FROM_NAME": "BenGER Platform",
}


def _response(status_code, body):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = body
    response.text = str(body)
    return response


def _ok():
    return _response(200, {"ErrorCode": 0, "Message": "OK", "MessageID": "pm-1"})


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expiries = {}

    def incrby(self, key, amount):
        self.values[key] = self.values.get(key, 0) + amount
        return self.values[key]

    def decrby(self, key, amount):
        self.values[key] = self.values.get(key, 0) - amount
        return self.values[key]

    def expire(self, key, seconds):
        self.expiries[key] = seconds


@pytest.fixture
def fake_redis():
    redis = FakeRedis()
    with patch.object(postmark_client, "_redis", return_value=redis):
        yield redis


@pytest.fixture
def pm_client():
    with patch.dict(os.environ, PM_ENV, clear=True):
        return PostmarkEmailClient()


class TestPostmarkEmailClient:
    @patch("mailer.postmark_client.requests.post")
    def test_send_success_payload_and_result(self, mock_post, pm_client, fake_redis):
        mock_post.return_value = _ok()

        result = pm_client.send_message(
            to=["a@tum.de"],
            subject="Invitation",
            html_body='<p>Hi</p><a href="https://x.test/accept/1">Accept</a>',
            headers={"X-Test": "1"},
            essential=True,
        )

        assert result == {
            "status": "success",
            "message_id": "pm-1",
            "recipients": ["a@tum.de"],
            "status_code": 200,
        }
        kwargs = mock_post.call_args.kwargs
        assert mock_post.call_args.args[0] == "https://api.postmarkapp.com/email"
        assert kwargs["headers"]["X-Postmark-Server-Token"] == "pm-token"
        assert kwargs["timeout"] == (5, 15)
        payload = kwargs["json"]
        assert payload["From"] == "BenGER Platform <noreply@what-a-benger.net>"
        assert payload["To"] == "a@tum.de"
        assert payload["MessageStream"] == "outbound"
        assert payload["TrackOpens"] is False
        assert payload["TrackLinks"] == "None"
        assert "Accept (https://x.test/accept/1)" in payload["TextBody"]
        assert payload["Headers"] == [{"Name": "X-Test", "Value": "1"}]
        assert sum(fake_redis.values.values()) == 1
        assert list(fake_redis.expiries.values()) == [40 * 24 * 3600]

    @patch("mailer.postmark_client.requests.post")
    def test_budget_counts_every_recipient(self, mock_post, pm_client, fake_redis):
        mock_post.return_value = _ok()

        pm_client.send_message(to=["a@x.de", "b@x.de"], subject="S", cc=["c@x.de"])

        assert sum(fake_redis.values.values()) == 3
        assert mock_post.call_args.kwargs["json"]["Cc"] == "c@x.de"

    @patch("mailer.postmark_client.requests.post")
    def test_over_budget_rejects_without_calling(self, mock_post, fake_redis):
        with patch.dict(os.environ, {**PM_ENV, "POSTMARK_MONTHLY_LIMIT": "2"}, clear=True):
            client = PostmarkEmailClient()
        mock_post.return_value = _ok()

        assert client.send_message(to=["a@x.de"], subject="S")["status"] == "success"
        assert client.send_message(to=["b@x.de"], subject="S")["status"] == "success"
        result = client.send_message(to=["c@x.de"], subject="S")

        assert mock_post.call_count == 2
        assert result["status"] == "error"
        assert result["provider_rejected"] is True
        # The refused reservation is not kept.
        assert sum(fake_redis.values.values()) == 2

    @patch("mailer.postmark_client.requests.post")
    def test_api_rejection_releases_the_reservation(self, mock_post, pm_client, fake_redis):
        mock_post.return_value = _response(
            422, {"ErrorCode": 406, "Message": "Inactive recipient a@x.de"}
        )

        result = pm_client.send_message(to=["a@x.de"], subject="S")

        assert result["status"] == "error"
        assert result["status_code"] == 422
        assert result["provider_rejected"] is True
        assert "406" in result["details"]
        assert "a@x.de" not in result["details"]
        assert sum(fake_redis.values.values()) == 0

    @patch("mailer.postmark_client.requests.post")
    def test_transport_failure_is_retryable_and_keeps_the_reservation(
        self, mock_post, pm_client, fake_redis
    ):
        mock_post.side_effect = requests.exceptions.ConnectionError("down")

        result = pm_client.send_message(to=["a@x.de"], subject="S")

        assert result["status_code"] is None
        assert "provider_rejected" not in result
        assert sum(fake_redis.values.values()) == 1

    @patch("mailer.postmark_client.requests.post")
    def test_without_redis_it_still_sends(self, mock_post, pm_client):
        mock_post.return_value = _ok()
        with patch.object(postmark_client, "_redis", return_value=None):
            assert pm_client.send_message(to=["a@x.de"], subject="S")["status"] == "success"

    @patch("mailer.postmark_client.requests.post")
    def test_redis_errors_fail_open(self, mock_post, pm_client):
        mock_post.return_value = _ok()
        broken = MagicMock()
        broken.incrby.side_effect = ConnectionError("redis down")
        with patch.object(postmark_client, "_redis", return_value=broken):
            assert pm_client.send_message(to=["a@x.de"], subject="S")["status"] == "success"

    @patch("mailer.postmark_client.requests.post")
    def test_invalid_placeholder_is_never_mailed(self, mock_post, pm_client, fake_redis):
        result = pm_client.send_message(to=["lms-1@users.benger.invalid"], subject="S")

        mock_post.assert_not_called()
        assert result["status_code"] == 400
        assert fake_redis.values == {}

    def test_unconfigured_client_rejects(self):
        with patch.dict(os.environ, {}, clear=True):
            client = PostmarkEmailClient()
        assert not client.is_configured()
        assert client.send_message(to=["a@x.de"], subject="S")["provider_rejected"] is True

    def test_token_whitespace_is_stripped(self):
        # A token copied from a file keeps its newline, which breaks the header.
        with patch.dict(os.environ, {**PM_ENV, "POSTMARK_SERVER_TOKEN": "pm-token\n"}, clear=True):
            assert PostmarkEmailClient().api_key == "pm-token"

    def test_bad_limit_uses_the_default(self):
        with patch.dict(os.environ, {**PM_ENV, "POSTMARK_MONTHLY_LIMIT": "lots"}, clear=True):
            assert PostmarkEmailClient().monthly_limit == 100

    @patch("mailer.postmark_client.requests.get")
    def test_connection_checks_the_server_token(self, mock_get, pm_client):
        mock_get.return_value = _response(200, {"ID": 1})
        assert asyncio.run(pm_client.test_connection()) is True
        assert mock_get.call_args.args[0] == "https://api.postmarkapp.com/server"


REJECTED = {"status": "error", "status_code": 403, "provider_rejected": True}


class TestRoutingWithPostmark:
    @pytest.fixture
    def router(self):
        primary = MagicMock(api_key="cf", from_email="noreply@what-a-benger.net")
        fallback = MagicMock(api_key="sg")
        postmark = MagicMock()
        return RoutedMailClient(primary, fallback, {"what-a-benger.net"}, postmark)

    def test_essential_mail_goes_to_postmark_after_cloudflare_rejects(self, router):
        router.primary.send_message.return_value = dict(REJECTED)
        router.essential_fallback.send_message.return_value = {"status": "success"}

        result = router.send_message(to=["a@x.de"], subject="S", essential=True)

        assert result == {"status": "success"}
        router.essential_fallback.send_message.assert_called_once_with(
            to=["a@x.de"], subject="S"
        )
        router.fallback.send_message.assert_not_called()

    def test_other_mail_skips_postmark(self, router):
        router.primary.send_message.return_value = dict(REJECTED)
        router.fallback.send_message.return_value = {"status": "success"}

        router.send_message(to=["a@x.de"], subject="S")

        router.essential_fallback.send_message.assert_not_called()
        router.fallback.send_message.assert_called_once()

    def test_postmark_rejection_reaches_sendgrid(self, router):
        router.primary.send_message.return_value = dict(REJECTED)
        router.essential_fallback.send_message.return_value = dict(REJECTED)
        router.fallback.send_message.return_value = {"status": "success", "status_code": 202}

        result = router.send_message(to=["a@x.de"], subject="S", essential=True)

        assert result["status_code"] == 202

    def test_postmark_transport_failure_does_not_double_send(self, router):
        router.primary.send_message.return_value = dict(REJECTED)
        router.essential_fallback.send_message.return_value = {
            "status": "error",
            "status_code": None,
        }

        result = router.send_message(to=["a@x.de"], subject="S", essential=True)

        assert result["status_code"] is None
        router.fallback.send_message.assert_not_called()

    def test_cloudflare_success_never_touches_postmark(self, router):
        router.primary.send_message.return_value = {"status": "success"}

        router.send_message(to=["a@x.de"], subject="S", essential=True)

        router.essential_fallback.send_message.assert_not_called()
        assert "essential" not in router.primary.send_message.call_args.kwargs

    def test_other_brand_skips_both(self, router):
        router.fallback.send_message.return_value = {"status": "success"}

        router.send_message(
            to=["a@x.de"], subject="S", from_address="noreply@vertretbar.net", essential=True
        )

        router.primary.send_message.assert_not_called()
        router.essential_fallback.send_message.assert_not_called()


class TestBuildWithPostmark:
    def test_token_adds_postmark(self):
        env = {**PM_ENV, "EMAIL_PROVIDER": "cloudflare"}
        with patch.dict(os.environ, env, clear=True):
            client = build_mail_client(MagicMock())
        assert isinstance(client.essential_fallback, PostmarkEmailClient)

    def test_no_token_no_postmark(self):
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "cloudflare"}, clear=True):
            client = build_mail_client(MagicMock())
        assert client.essential_fallback is None

    def test_sendgrid_accepts_the_essential_hint(self):
        from mailer.sendgrid_client import SendGridClient

        with patch.dict(os.environ, {}, clear=True):
            client = SendGridClient()
        # Unconfigured, so no request; the keyword must simply be accepted.
        assert client.send_message(to=["a@x.de"], subject="S", essential=True)["status"] == "error"
