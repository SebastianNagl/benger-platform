"""Tests for ``emails.send_account_activation``.

This task shipped without worker-side coverage (it dropped the workers gate from
90.40% to 89.87%), which matters more than the number: it is the single writer
for activation-token minting. Both the auto path (first LTI provisioning) and
the fallback path (a sub-only account supplying an address) enqueue it, so its
guards are what stop a double-fire from re-minting a token, an already-activated
account from being reset, and an address that belongs to somebody else from
being adopted.

Idioms mirror test_invitation_email_tasks.py: patch ``sendgrid_client.SendGridClient``
and drive the real task function.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tasks as tasks_module  # noqa: E402
from tasks import send_account_activation_task  # noqa: E402


def _sendgrid(result):
    client = MagicMock()
    client.send_message.return_value = result
    return MagicMock(return_value=client), client


def _fake_db(user, *, email_taken=False):
    """Session double for the two ``db.execute(select(...))`` lookups the task
    makes: the FOR UPDATE user fetch, then (only when target_email is given)
    the address-collision probe."""
    db = MagicMock()
    calls = {"n": 0}

    def _execute(_stmt):
        calls["n"] += 1
        res = MagicMock()
        if calls["n"] == 1:
            res.scalar_one_or_none.return_value = user
        else:
            res.first.return_value = ("other-user",) if email_taken else None
        return res

    db.execute.side_effect = _execute
    return db


def _user(**over):
    u = MagicMock()
    u.id = over.get("id", "u-1")
    u.email = over.get("email", "student@uni.example")
    return u


def _brand():
    brand = MagicMock()
    brand.name = "Vertretbar"
    brand.frontend_url = "https://vertretbar.net"
    brand.default_language = "de"
    brand.from_address = "noreply@vertretbar.net"
    brand.from_name = "Vertretbar"
    return brand


def _run(db, *, sendgrid_class, eligibility=None, token="tok-abc", **kwargs):
    """Drive the task with all of its lazily-imported collaborators stubbed."""
    email_service = MagicMock()
    email_service.build_account_activation_email.return_value = ("Betreff", "<p>hi</p>")

    with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), \
         patch("account_activation.activation_eligibility", return_value=eligibility), \
         patch("account_activation.current_or_new_activation_token", return_value=token), \
         patch("account_activation.build_activation_link", return_value=f"https://x/activate/{token}"), \
         patch("mailer.branding.resolve_email_brand", return_value=_brand()), \
         patch("email_service.email_service", email_service), \
         patch("sendgrid_client.SendGridClient", sendgrid_class):
        return send_account_activation_task.run(**kwargs), email_service


class TestActivationEmailGuards:
    def test_missing_user_is_skipped(self):
        cls, client = _sendgrid({"status": "success"})
        result, _ = _run(_fake_db(None), sendgrid_class=cls, user_id="gone")

        assert result == {"status": "skipped", "reason": "user_not_found"}
        client.send_message.assert_not_called()

    @pytest.mark.parametrize("reason", ["already_activated", "no_routable_email"])
    def test_ineligible_account_is_skipped_without_minting_a_token(self, reason):
        """The eligibility guard is what makes a double-fire a no-op. If this
        regressed, a second dispatch would re-mint a token and silently
        invalidate the link already sitting in the student's inbox."""
        cls, client = _sendgrid({"status": "success"})
        db = _fake_db(_user())

        result, _ = _run(db, sendgrid_class=cls, eligibility=reason, user_id="u-1")

        assert result == {"status": "skipped", "reason": reason}
        client.send_message.assert_not_called()
        db.commit.assert_not_called()

    def test_target_email_belonging_to_another_user_aborts(self):
        """The fallback path lets a sub-only account type in an address. If it
        is already taken, adopting it would hand one account's mail to another."""
        cls, client = _sendgrid({"status": "success"})
        db = _fake_db(_user(), email_taken=True)

        result, _ = _run(
            db,
            sendgrid_class=cls,
            user_id="u-1",
            target_email="taken@uni.example",
        )

        assert result == {"status": "skipped", "reason": "email_taken"}
        client.send_message.assert_not_called()
        db.commit.assert_not_called()


class TestActivationEmailSend:
    def test_success_commits_the_token_before_sending(self):
        """A link that reaches a mailbox must resolve, so the token commit has
        to happen BEFORE the send — not after."""
        cls, client = _sendgrid({"status": "success", "message_id": "msg-1"})
        db = _fake_db(_user())
        order = []
        db.commit.side_effect = lambda: order.append("commit")
        client.send_message.side_effect = lambda **kw: (
            order.append("send"),
            {"status": "success", "message_id": "msg-1"},
        )[1]

        result, email_service = _run(db, sendgrid_class=cls, user_id="u-1")

        assert result["status"] == "success"
        assert result["user_id"] == "u-1"
        assert result["recipient"] == "student@uni.example"
        assert result["message_id"] == "msg-1"
        assert order == ["commit", "send"], "token must be committed before the send"
        # Tracking off: activation links must not be rewritten by SendGrid.
        assert client.send_message.call_args.kwargs["disable_tracking"] is True

    def test_target_email_wins_over_the_account_address(self):
        cls, client = _sendgrid({"status": "success", "message_id": "m"})
        db = _fake_db(_user(email="old@uni.example"))

        result, _ = _run(
            db, sendgrid_class=cls, user_id="u-1", target_email="new@uni.example"
        )

        assert result["recipient"] == "new@uni.example"
        assert client.send_message.call_args.kwargs["to"] == ["new@uni.example"]

    def test_expiry_days_travel_into_the_template(self):
        cls, _ = _sendgrid({"status": "success", "message_id": "m"})
        result, email_service = _run(_fake_db(_user()), sendgrid_class=cls, user_id="u-1")

        assert result["status"] == "success"
        kwargs = email_service.build_account_activation_email.call_args.kwargs
        assert kwargs["expiry_days"] == 7  # ACTIVATION_TOKEN_EXPIRY
        assert kwargs["brand_name"] == "Vertretbar"
        assert kwargs["frontend_host"] == "vertretbar.net"


class TestActivationEmailFailureClassification:
    def test_permanent_4xx_returns_without_raising(self):
        """Same split as the invitation task: a 4xx must not burn three
        retries on the rate-limited emails queue."""
        cls, client = _sendgrid(
            {"status": "error", "status_code": 400, "error": "bad address"}
        )

        result, _ = _run(_fake_db(_user()), sendgrid_class=cls, user_id="u-1")

        assert result["status"] == "failed_permanent"
        assert result["status_code"] == 400
        assert client.send_message.call_count == 1

    @pytest.mark.parametrize("status_code", [429, 500, 503, None])
    def test_retryable_failures_raise(self, status_code):
        """429 (throttled) and 5xx must raise so autoretry_for backs off."""
        cls, _ = _sendgrid(
            {"status": "error", "status_code": status_code, "error": "boom"}
        )

        with pytest.raises(RuntimeError, match="SendGrid error"):
            _run(_fake_db(_user()), sendgrid_class=cls, user_id="u-1")

    def test_unexpected_exception_propagates_for_retry(self):
        cls, client = _sendgrid({"status": "success"})
        client.send_message.side_effect = ValueError("socket exploded")

        with pytest.raises(Exception, match="socket exploded"):
            _run(_fake_db(_user()), sendgrid_class=cls, user_id="u-1")
