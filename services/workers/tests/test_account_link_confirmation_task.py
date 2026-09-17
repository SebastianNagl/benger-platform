"""Tests for ``emails.send_account_link_confirmation``.

The extended LMS flow queues this task when someone chooses the email proof
to link an LMS sign-in to the existing account at the LMS address (owner
decision D6). The task delivers a link that holds the proof token, so the
tests pin:

- it mails only accounts that may be linked (never a superadmin, never an
  unproven, unroutable, inactive or anonymized address), checked when the
  task runs, not only when it was queued;
- the link, the connection and the organization reach the rendered mail,
  and the mail follows the user's language (German by default);
- the token and the full address never reach the log or the task result
  (Celery logs the result);
- SendGrid 4xx is permanent, 429/5xx/transport errors retry.

Idioms mirror test_account_activation_email_task.py: patch
``sendgrid_client.SendGridClient`` and the session, drive the real task.
"""

import logging
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tasks as tasks_module  # noqa: E402
from mailer.branding import resolve_email_brand as _real_resolve_email_brand  # noqa: E402
from tasks import send_account_link_confirmation_task  # noqa: E402

TOKEN = "tok-SECRET-4711"


def _sendgrid(result):
    client = MagicMock()
    client.send_message.return_value = result
    return MagicMock(return_value=client), client


def _fake_db(user):
    db = MagicMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = user
    db.execute.return_value = res
    return db


def _user(**over):
    base = dict(
        id="u-1",
        email="owner@uni.example",
        email_verified=True,
        email_verification_method="self",
        is_active=True,
        is_superadmin=False,
        anonymized_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _brand(host=None):
    """The real brand resolver, pinned to deterministic env values."""
    env = {
        "FRONTEND_URL": "https://what-a-benger.net",
        "VERTRETBAR_FRONTEND_URL": "https://student.example",
    }
    with patch.dict(os.environ, env):
        return _real_resolve_email_brand(host)


def _run(db, *, sendgrid_class, host="what-a-benger.net", **kwargs):
    """Drive the task with the real templates and brand resolver."""
    kwargs.setdefault("user_id", "u-1")
    kwargs.setdefault("token", TOKEN)
    kwargs.setdefault("connection_name", "Moodle Uni X")
    kwargs.setdefault("organization_name", "Uni X")
    with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), \
         patch("mailer.branding.resolve_email_brand", side_effect=_brand), \
         patch("sendgrid_client.SendGridClient", sendgrid_class):
        return send_account_link_confirmation_task.run(host=host, **kwargs)


class TestEligibility:
    def test_missing_token_is_skipped_without_a_db_read(self):
        cls, client = _sendgrid({"status": "success"})
        db = _fake_db(_user())

        result = _run(db, sendgrid_class=cls, token="")

        assert result == {"status": "skipped", "reason": "missing_token"}
        db.execute.assert_not_called()
        client.send_message.assert_not_called()

    def test_missing_user_is_skipped(self):
        cls, client = _sendgrid({"status": "success"})

        result = _run(_fake_db(None), sendgrid_class=cls)

        assert result == {"status": "skipped", "reason": "user_not_found"}
        client.send_message.assert_not_called()

    @pytest.mark.parametrize(
        "overrides,reason",
        [
            ({"is_superadmin": True}, "not_linkable"),
            ({"is_active": False}, "user_inactive"),
            ({"anonymized_at": "2026-09-16"}, "user_anonymized"),
            ({"email": "lti-x@lti.invalid"}, "email_not_routable"),
            ({"email_verified": False}, "email_not_proven"),
            ({"email_verification_method": "lti_claim"}, "email_not_proven"),
            ({"email_verification_method": "admin"}, "email_not_proven"),
            ({"email_verification_method": "system"}, "email_not_proven"),
        ],
    )
    def test_ineligible_accounts_get_no_mail(self, overrides, reason):
        """Checked again when the task runs: the account may have changed
        since the proof was requested."""
        cls, client = _sendgrid({"status": "success"})
        db = _fake_db(_user(**overrides))

        result = _run(db, sendgrid_class=cls)

        assert result == {"status": "skipped", "reason": reason}
        client.send_message.assert_not_called()
        db.close.assert_called_once()

    def test_the_task_writes_nothing(self):
        cls, _ = _sendgrid({"status": "success", "message_id": "m"})
        db = _fake_db(_user())

        _run(db, sendgrid_class=cls)

        db.commit.assert_not_called()
        db.close.assert_called_once()


class TestSend:
    def test_success_mails_the_account_address_with_the_link(self):
        cls, client = _sendgrid({"status": "success", "message_id": "msg-1"})

        result = _run(_fake_db(_user()), sendgrid_class=cls)

        assert result == {
            "status": "success",
            "user_id": "u-1",
            "recipient_hint": "ow…@uni.example",
            "message_id": "msg-1",
        }
        kwargs = client.send_message.call_args.kwargs
        assert kwargs["to"] == ["owner@uni.example"]
        # Tracking off: SendGrid must not rewrite the proof link.
        assert kwargs["disable_tracking"] is True
        body = kwargs["html_body"]
        assert f"https://what-a-benger.net/lti/link-confirm/{TOKEN}" in body
        assert "„Moodle Uni X“" in body
        assert "der Organisation Uni X" in body
        assert "Wenn du das nicht warst" in body
        assert "24 Stunden" in body
        # German by default, also on the BenGER host.
        assert kwargs["subject"] == "Bestätige die Verknüpfung mit deinem BenGER-Konto"

    def test_user_language_preference_wins(self):
        cls, client = _sendgrid({"status": "success", "message_id": "m"})

        _run(_fake_db(_user(language_preference="en")), sendgrid_class=cls)

        kwargs = client.send_message.call_args.kwargs
        assert kwargs["subject"] == "Confirm the link to your BenGER account"
        assert "If this wasn’t you, ignore this email." in kwargs["html_body"]

    def test_student_host_brands_sender_and_link(self):
        cls, client = _sendgrid({"status": "success", "message_id": "m"})

        _run(_fake_db(_user()), sendgrid_class=cls, host="vertretbar.net")

        brand = _brand("vertretbar.net")
        kwargs = client.send_message.call_args.kwargs
        assert kwargs["from_address"] == brand.from_address
        assert kwargs["from_name"] == brand.from_name
        assert f"https://student.example/lti/link-confirm/{TOKEN}" in kwargs["html_body"]
        assert f"{brand.name}-Konto" in kwargs["subject"]

    def test_free_text_names_are_cleaned_and_escaped(self):
        cls, client = _sendgrid({"status": "success", "message_id": "m"})

        _run(
            _fake_db(_user()),
            sendgrid_class=cls,
            connection_name="Kurs\n\n<b>Jetzt klicken</b>",
            organization_name=None,
        )

        kwargs = client.send_message.call_args.kwargs
        body = kwargs["html_body"]
        assert "„Kurs &lt;b&gt;Jetzt klicken&lt;/b&gt;“" in body
        assert "<b>Jetzt" not in body
        assert "der Organisation" not in body
        assert "Jetzt" not in kwargs["subject"]

    def test_token_and_address_never_logged(self, caplog):
        cls, _ = _sendgrid({"status": "success", "message_id": "m"})

        with caplog.at_level(logging.DEBUG):
            result = _run(_fake_db(_user()), sendgrid_class=cls)

        assert TOKEN not in caplog.text
        assert "owner@uni.example" not in caplog.text
        assert TOKEN not in repr(result)
        assert "owner@uni.example" not in repr(result)


class TestFailureClassification:
    def test_permanent_4xx_returns_without_raising(self):
        cls, client = _sendgrid(
            {"status": "error", "status_code": 400, "error": "bad address"}
        )

        result = _run(_fake_db(_user()), sendgrid_class=cls)

        assert result["status"] == "failed_permanent"
        assert result["status_code"] == 400
        assert result["recipient_hint"] == "ow…@uni.example"
        assert client.send_message.call_count == 1

    @pytest.mark.parametrize("status_code", [429, 500, 503, None])
    def test_retryable_failures_raise(self, status_code):
        cls, _ = _sendgrid(
            {"status": "error", "status_code": status_code, "error": "boom"}
        )

        with pytest.raises(RuntimeError, match="SendGrid error"):
            _run(_fake_db(_user()), sendgrid_class=cls)

    def test_unexpected_exception_propagates_for_retry_without_the_token(self, caplog):
        cls, client = _sendgrid({"status": "success"})
        client.send_message.side_effect = ValueError(f"socket exploded {TOKEN}")

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ValueError, match="socket exploded"):
                _run(_fake_db(_user()), sendgrid_class=cls)

        assert TOKEN not in caplog.text

    def test_template_failure_retries_instead_of_mailing_a_linkless_body(self):
        cls, client = _sendgrid({"status": "success"})
        email_service = MagicMock()
        email_service.build_account_link_confirmation_email.side_effect = (
            RuntimeError("template missing")
        )

        with patch("email_service.email_service", email_service):
            with pytest.raises(RuntimeError, match="template missing"):
                _run(_fake_db(_user()), sendgrid_class=cls)

        client.send_message.assert_not_called()


def test_task_is_registered_with_retries():
    task = tasks_module.app.tasks["emails.send_account_link_confirmation"]
    assert task.max_retries == 3
    assert task.autoretry_for == (Exception,)
