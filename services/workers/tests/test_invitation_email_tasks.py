"""
Tests for invitation email Celery tasks
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import tasks  # noqa: E402
from tasks import send_bulk_invitations_task, send_invitation_email_task  # noqa: E402


def _mock_sendgrid_success():
    """Create a mock SendGridClient that returns success."""
    mock_client = MagicMock()
    mock_client.send_message.return_value = {
        "status": "success",
        "message_id": "mock-msg-id-123",
    }
    mock_class = MagicMock(return_value=mock_client)
    return mock_class, mock_client


class TestInvitationEmailTask:
    """Test suite for invitation email Celery task"""

    def test_send_invitation_email_success(self):
        """Test successful invitation email sending"""
        invitation_id = "test-inv-123"
        to_email = "test@example.com"
        inviter_name = "John Doe"
        organization_name = "Test Org"
        invitation_url = "http://localhost:3000/accept-invitation/token123"
        role = "member"

        mock_class, mock_client = _mock_sendgrid_success()

        with patch('sendgrid_client.SendGridClient', mock_class):
            result = send_invitation_email_task(
                invitation_id, to_email, inviter_name, organization_name, invitation_url, role
            )

        assert result["status"] == "success"
        assert result["invitation_id"] == invitation_id
        assert result["recipient_hint"] == "te…@example.com"
        assert result["organization"] == organization_name
        mock_client.send_message.assert_called_once()

    def test_invitation_email_body_is_substituted(self):
        """Regression: the body was once a plain (non-f) string, so the
        literal tokens {organization_name}, {invitation_url}, etc. shipped to
        recipients and the accept link was dead. The body is now rendered from
        the invitation_recipient.html Jinja2 template — assert the real values
        are present and no unrendered token of either style leaks through."""
        mock_class, mock_client = _mock_sendgrid_success()

        with patch('sendgrid_client.SendGridClient', mock_class):
            send_invitation_email_task(
                "inv-sub",
                "user@example.com",
                "Jane Admin",
                "Göttingen",
                "https://what-a-benger.net/accept-invitation/tok123",
                "ANNOTATOR",
            )

        body = mock_client.send_message.call_args.kwargs["html_body"]
        subject = mock_client.send_message.call_args.kwargs["subject"]

        # Real values rendered into both subject and body
        assert "Göttingen" in subject
        assert "Göttingen" in body
        assert "Jane Admin" in body
        assert "ANNOTATOR" in body
        assert "https://what-a-benger.net/accept-invitation/tok123" in body

        # No unrendered placeholders of either templating style
        for token in (
            "{organization_name}",
            "{inviter_name}",
            "{role}",
            "{invitation_url}",
            "{{ organization_name }}",
            "{{ inviter_name }}",
            "{{ role }}",
            "{{ invitation_url }}",
        ):
            assert token not in body
            assert token not in subject

    def test_send_invitation_email_sendgrid_error(self):
        """Test that SendGrid errors raise RuntimeError"""
        mock_client = MagicMock()
        mock_client.send_message.return_value = {
            "status": "error",
            "error": "Invalid API key",
        }
        mock_class = MagicMock(return_value=mock_client)

        with patch('sendgrid_client.SendGridClient', mock_class):
            with pytest.raises(RuntimeError, match="SendGrid error: Invalid API key"):
                send_invitation_email_task(
                    "inv-1", "fail@example.com", "Jane", "Org", "http://example.com/invite", "member"
                )

    def test_send_invitation_email_exception(self):
        """Test that exceptions propagate for Celery retry"""
        mock_client = MagicMock()
        mock_client.send_message.side_effect = ConnectionError("Network failure")
        mock_class = MagicMock(return_value=mock_client)

        with patch('sendgrid_client.SendGridClient', mock_class):
            with pytest.raises(ConnectionError, match="Network failure"):
                send_invitation_email_task(
                    "inv-2", "fail@example.com", "Jane", "Org", "http://example.com/invite", "member"
                )

    def test_permanent_4xx_returns_failed_without_raising(self):
        """Regression: a SendGrid 400/401/403 used to burn 3 full retries
        because autoretry_for=(Exception,) swept up the RuntimeError
        raised for every non-success status. Now 4xx (except 429) is
        treated as permanent — return failed_permanent and let the task
        complete so the rate-limited emails queue keeps moving."""
        mock_client = MagicMock()
        mock_client.send_message.return_value = {
            "status": "error",
            "status_code": 400,
            "error": "SendGrid API error: 400",
            "details": "malformed recipient",
        }
        mock_class = MagicMock(return_value=mock_client)

        with patch('sendgrid_client.SendGridClient', mock_class):
            result = send_invitation_email_task(
                "inv-4xx", "bad@", "Jane", "Org", "http://example.com/invite", "member"
            )

        assert result["status"] == "failed_permanent"
        assert result["status_code"] == 400
        # Only ONE send attempt — no retry.
        assert mock_client.send_message.call_count == 1

    def test_429_rate_limit_still_retries(self):
        """429 means SendGrid is throttling us — we MUST retry with the
        countdown=60 backoff. Don't classify 429 as permanent."""
        mock_client = MagicMock()
        mock_client.send_message.return_value = {
            "status": "error",
            "status_code": 429,
            "error": "SendGrid API error: 429",
        }
        mock_class = MagicMock(return_value=mock_client)

        with patch('sendgrid_client.SendGridClient', mock_class):
            with pytest.raises(RuntimeError, match="SendGrid error"):
                send_invitation_email_task(
                    "inv-429", "x@example.com", "Jane", "Org", "http://example.com/invite", "member"
                )

    def test_5xx_still_retries(self):
        """Server errors are transient — they MUST keep retrying."""
        mock_client = MagicMock()
        mock_client.send_message.return_value = {
            "status": "error",
            "status_code": 503,
            "error": "SendGrid API error: 503",
        }
        mock_class = MagicMock(return_value=mock_client)

        with patch('sendgrid_client.SendGridClient', mock_class):
            with pytest.raises(RuntimeError, match="SendGrid error"):
                send_invitation_email_task(
                    "inv-5xx", "x@example.com", "Jane", "Org", "http://example.com/invite", "member"
                )

    def test_network_failure_still_retries(self):
        """Network/transport errors arrive with status_code=None and
        should remain retryable (so autoretry_for picks them up)."""
        mock_client = MagicMock()
        mock_client.send_message.return_value = {
            "status": "error",
            "status_code": None,
            "error": "Connection refused",
        }
        mock_class = MagicMock(return_value=mock_client)

        with patch('sendgrid_client.SendGridClient', mock_class):
            with pytest.raises(RuntimeError, match="SendGrid error"):
                send_invitation_email_task(
                    "inv-net", "x@example.com", "Jane", "Org", "http://example.com/invite", "member"
                )

    def test_send_invitation_email_logs_correctly(self):
        """Test that invitation email task logs correctly"""
        invitation_id = "test-inv-789"
        to_email = "log@example.com"
        inviter_name = "Logger Test"
        organization_name = "Log Org"
        invitation_url = "http://localhost:3000/accept-invitation/token789"
        role = "viewer"

        mock_class, mock_client = _mock_sendgrid_success()

        with patch('sendgrid_client.SendGridClient', mock_class), \
             patch('tasks.logger') as mock_logger:
            result = send_invitation_email_task(
                invitation_id, to_email, inviter_name, organization_name, invitation_url, role
            )

            assert mock_logger.info.called
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any('Sending invitation email' in str(call) for call in info_calls)
            assert any('successfully' in str(call) for call in info_calls)
            # The invitation id identifies the mail; the address stays out.
            assert all(invitation_id in call for call in info_calls)
            assert not any(to_email in call for call in info_calls)

        assert result["status"] == "success"


class TestBulkInvitationEmailTask:
    """Test suite for bulk invitation email Celery task"""

    def test_send_bulk_invitations_success(self):
        """Test successful bulk invitation email sending"""
        invitations_data = [
            {
                "invitation_id": "bulk-inv-1",
                "to_email": "user1@example.com",
                "inviter_name": "Admin",
                "organization_name": "Bulk Org",
                "invitation_url": "http://localhost:3000/accept-invitation/bulk1",
                "role": "member",
            },
            {
                "invitation_id": "bulk-inv-2",
                "to_email": "user2@example.com",
                "inviter_name": "Admin",
                "organization_name": "Bulk Org",
                "invitation_url": "http://localhost:3000/accept-invitation/bulk2",
                "role": "member",
            },
            {
                "invitation_id": "bulk-inv-3",
                "to_email": "user3@example.com",
                "inviter_name": "Admin",
                "organization_name": "Bulk Org",
                "invitation_url": "http://localhost:3000/accept-invitation/bulk3",
                "role": "admin",
            },
        ]

        with patch.object(
            send_invitation_email_task, 'apply_async', return_value=MagicMock()
        ) as mock_apply:
            result = send_bulk_invitations_task(invitations_data)

        assert result["sent"] == 3
        assert result["failed"] == 0
        assert result["total"] == 3
        assert mock_apply.call_count == 3

        for i, call_args in enumerate(mock_apply.call_args_list):
            expected_delay = i * tasks.INVITATION_FANOUT_SPACING_SECONDS
            assert call_args[1]['countdown'] == expected_delay

    def test_send_bulk_invitations_partial_failure(self):
        """Test bulk invitation with some failures"""
        invitations_data = [
            {
                "invitation_id": "bulk-inv-1",
                "to_email": "success@example.com",
                "inviter_name": "Admin",
                "organization_name": "Bulk Org",
                "invitation_url": "http://localhost:3000/accept-invitation/bulk1",
                "role": "member",
            },
            {
                "invitation_id": "bulk-inv-2",
                "to_email": "fail@example.com",
                "inviter_name": "Admin",
                "organization_name": "Bulk Org",
                "invitation_url": "http://localhost:3000/accept-invitation/bulk2",
                "role": "member",
            },
        ]

        def apply_async_side_effect(*args, **kwargs):
            # Fail the second address. Keyed on the recipient, not on the
            # fan-out spacing, which is a tuning value.
            if args and "fail@example.com" in args[0]:
                raise Exception("Queue full")
            if kwargs.get("args") and "fail@example.com" in kwargs["args"]:
                raise Exception("Queue full")
            return MagicMock()

        with patch.object(
            send_invitation_email_task, 'apply_async', side_effect=apply_async_side_effect
        ):
            result = send_bulk_invitations_task(invitations_data)

        assert result["sent"] == 1
        assert result["failed"] == 1
        assert result["total"] == 2

    def test_send_bulk_invitations_empty_list(self):
        """Test bulk invitation with empty list"""
        result = send_bulk_invitations_task([])

        assert result["sent"] == 0
        assert result["failed"] == 0
        assert result["total"] == 0


class TestEmailTaskIntegration:
    """Integration tests for email task configuration"""

    def test_invitation_email_with_retry_mechanism(self):
        """Test that invitation email task has retry configuration"""
        from tasks import app

        task = app.tasks.get('emails.send_invitation')
        assert task is not None

        assert hasattr(task, 'autoretry_for')
        assert task.retry_kwargs['max_retries'] == 3
        assert task.retry_kwargs['countdown'] == 60

    def test_email_queue_routing(self):
        """Test that email tasks are routed to the correct queue.

        Routing moved from the `emails.*` glob to the shared table in
        services/shared/celery_queues.py, so assert against that instead. The
        destination is unchanged: mail still goes to `emails`, now served by its
        own worker pool so a rate-limited bulk invite can't hold interactive
        slots.
        """
        import celery_queues

        from tasks import app

        assert celery_queues.route_task in tuple(app.conf.task_routes)
        for name in (
            'emails.send_invitation',
            'emails.send_bulk_invitations',
            'emails.send_notification_batch',
        ):
            assert celery_queues.queue_for(name) == 'emails'

        assert 'emails.send_invitation' in app.conf.task_annotations
        assert app.conf.task_annotations['emails.send_invitation']['rate_limit'] == '120/m'

        assert 'emails.send_bulk_invitations' in app.conf.task_annotations
        assert app.conf.task_annotations['emails.send_bulk_invitations']['rate_limit'] == '5/m'


# ---------------------------------------------------------------------------
# Delivery bookkeeping on the invitation row
#
# The mail worker used to leave no durable trace of a send: the log line
# scrolled away and the Celery result expired after a day. An OOM-killed
# worker was indistinguishable from a delivered invitation, and the admin UI
# said "invite sent" as soon as the task was queued. The task now stamps the
# outcome onto `invitations`.
# ---------------------------------------------------------------------------


class _FakeInvitation:
    """Stand-in for the ORM row, with the four bookkeeping columns."""

    def __init__(self, invitation_id="inv-book"):
        self.id = invitation_id
        self.email_sent_at = None
        self.email_last_attempt_at = None
        self.email_attempts = 0
        self.email_last_error = None


def _fake_invitation_db(invitation):
    """A MagicMock session whose query(...).filter(...).first() yields the row."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = invitation
    return db


def _run_with_bookkeeping(sendgrid_result, invitation, *, invitation_id=None):
    """Drive the task with the mail provider stubbed and the DB faked."""
    import tasks as tasks_module

    mock_client = MagicMock()
    mock_client.send_message.return_value = sendgrid_result
    mock_class = MagicMock(return_value=mock_client)
    db = _fake_invitation_db(invitation)

    with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), \
         patch.object(tasks_module, "HAS_DATABASE", True), \
         patch('sendgrid_client.SendGridClient', mock_class):
        try:
            result = send_invitation_email_task(
                invitation_id or invitation.id,
                "book@example.com",
                "Jane Admin",
                "Book Org",
                "http://localhost:3000/accept-invitation/booktok",
                "ANNOTATOR",
            )
        except RuntimeError as e:
            return None, db, e
    return result, db, None


class TestInvitationEmailBookkeeping:
    """The delivery state the admin UI and the resend guard read."""

    def test_success_stamps_sent_and_counts_the_attempt(self):
        inv = _FakeInvitation()

        result, db, raised = _run_with_bookkeeping(
            {"status": "success", "message_id": "m-1"}, inv
        )

        assert raised is None
        assert result["status"] == "success"
        assert inv.email_attempts == 1
        assert inv.email_last_attempt_at is not None
        assert inv.email_sent_at is not None
        assert inv.email_last_error is None
        assert db.commit.called

    def test_success_clears_a_previous_error(self):
        """A retry that finally lands must not leave the old failure on screen."""
        inv = _FakeInvitation()
        inv.email_attempts = 2
        inv.email_last_error = "SendGrid 503: upstream down (retrying)"

        _run_with_bookkeeping({"status": "success", "message_id": "m-2"}, inv)

        assert inv.email_sent_at is not None
        assert inv.email_last_error is None
        assert inv.email_attempts == 3

    def test_permanent_failure_records_the_reason_and_no_sent_at(self):
        inv = _FakeInvitation()

        result, _db, raised = _run_with_bookkeeping(
            {
                "status": "error",
                "status_code": 400,
                "error": "Does not contain a valid address",
            },
            inv,
        )

        assert raised is None
        assert result["status"] == "failed_permanent"
        assert inv.email_sent_at is None
        assert inv.email_attempts == 1
        assert "400" in inv.email_last_error
        assert "valid address" in inv.email_last_error

    def test_retryable_failure_records_the_reason_and_still_raises(self):
        """The error has to be durable BEFORE the retry, otherwise a worker
        that dies during the 60 s countdown leaves nothing behind."""
        inv = _FakeInvitation()

        _result, _db, raised = _run_with_bookkeeping(
            {"status": "error", "status_code": 503, "error": "upstream down"}, inv
        )

        assert isinstance(raised, RuntimeError)
        assert inv.email_sent_at is None
        assert inv.email_attempts == 1
        assert "503" in inv.email_last_error
        assert "retrying" in inv.email_last_error

    def test_each_attempt_bumps_the_counter(self):
        """Celery re-invokes the same task on retry, so the count is the only
        record of how hard we tried."""
        inv = _FakeInvitation()

        for _ in range(3):
            _run_with_bookkeeping(
                {"status": "error", "status_code": 503, "error": "upstream down"}, inv
            )

        assert inv.email_attempts == 3

    def test_unexpected_exception_records_the_reason_and_propagates(self):
        import tasks as tasks_module

        inv = _FakeInvitation()
        db = _fake_invitation_db(inv)
        boom = MagicMock(side_effect=ValueError("sendgrid client exploded"))

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), \
             patch.object(tasks_module, "HAS_DATABASE", True), \
             patch('sendgrid_client.SendGridClient', boom):
            with pytest.raises(ValueError, match="exploded"):
                send_invitation_email_task(
                    inv.id, "x@example.com", "Jane", "Org", "http://x/i", "member"
                )

        assert inv.email_sent_at is None
        assert "ValueError" in inv.email_last_error

    def test_bookkeeping_failure_does_not_swallow_a_successful_send(self):
        """A broken DB must never turn an accepted message into a retry: the
        task's autoretry_for=(Exception,) would resend mail SendGrid took."""
        import tasks as tasks_module

        mock_client = MagicMock()
        mock_client.send_message.return_value = {
            "status": "success",
            "message_id": "m-3",
        }

        with patch.object(
            tasks_module,
            "SessionLocal",
            MagicMock(side_effect=RuntimeError("no database")),
        ), patch.object(tasks_module, "HAS_DATABASE", True), patch(
            'sendgrid_client.SendGridClient', MagicMock(return_value=mock_client)
        ):
            result = send_invitation_email_task(
                "inv-nodb", "x@example.com", "Jane", "Org", "http://x/i", "member"
            )

        assert result["status"] == "success"
        mock_client.send_message.assert_called_once()

    def test_missing_invitation_row_is_skipped_not_fatal(self):
        """A cancelled invitation still has a task in flight. Bookkeeping has
        nothing to write, and the send must not be retried over it."""
        import tasks as tasks_module

        mock_client = MagicMock()
        mock_client.send_message.return_value = {
            "status": "success",
            "message_id": "m-4",
        }
        db = _fake_invitation_db(None)

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), \
             patch.object(tasks_module, "HAS_DATABASE", True), \
             patch('sendgrid_client.SendGridClient', MagicMock(return_value=mock_client)):
            result = send_invitation_email_task(
                "inv-gone", "x@example.com", "Jane", "Org", "http://x/i", "member"
            )

        assert result["status"] == "success"
        db.commit.assert_not_called()

    def test_no_database_skips_bookkeeping_entirely(self):
        import tasks as tasks_module

        inv = _FakeInvitation()
        db = _fake_invitation_db(inv)
        mock_client = MagicMock()
        mock_client.send_message.return_value = {
            "status": "success",
            "message_id": "m-5",
        }

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), \
             patch.object(tasks_module, "HAS_DATABASE", False), \
             patch('sendgrid_client.SendGridClient', MagicMock(return_value=mock_client)):
            result = send_invitation_email_task(
                inv.id, "x@example.com", "Jane", "Org", "http://x/i", "member"
            )

        assert result["status"] == "success"
        assert inv.email_attempts == 0
        db.query.assert_not_called()

    def test_error_text_is_truncated(self):
        from tasks import INVITATION_ERROR_MAX_CHARS

        inv = _FakeInvitation()
        _run_with_bookkeeping(
            {"status": "error", "status_code": 400, "error": "x" * 5000}, inv
        )

        assert len(inv.email_last_error) == INVITATION_ERROR_MAX_CHARS


class TestInvitationEmailKeepsTheAddressOutOfTheLog:
    """Celery logs a task's return value at INFO ("Task ... succeeded: ..."),
    and worker logs are kept outside the database. The invitation id
    identifies the mail; the address only appears as a masked hint."""

    ADDRESS = "erika.musterfrau@uni-x.de"

    def _send(self, send_result, caplog, invitation_id="inv-log-1"):
        mock_client = MagicMock()
        mock_client.send_message.return_value = send_result
        with patch('sendgrid_client.SendGridClient', MagicMock(return_value=mock_client)), \
             caplog.at_level("DEBUG"):
            return send_invitation_email_task(
                invitation_id, self.ADDRESS, "Jane", "Org", "http://example.com/invite", "member"
            )

    def test_success_result_and_log_carry_only_the_hint(self, caplog):
        result = self._send({"status": "success", "message_id": "m-1"}, caplog)

        assert result["status"] == "success"
        assert result["recipient_hint"] == "er…@uni-x.de"
        assert "recipient" not in result
        assert self.ADDRESS not in repr(result)
        assert self.ADDRESS not in caplog.text
        assert "inv-log-1" in caplog.text

    def test_permanent_failure_result_and_log_carry_only_the_hint(self, caplog):
        result = self._send(
            {"status": "error", "status_code": 400, "error": "SendGrid API error: 400"}, caplog
        )

        assert result["status"] == "failed_permanent"
        assert result["recipient_hint"] == "er…@uni-x.de"
        assert self.ADDRESS not in repr(result)
        assert self.ADDRESS not in caplog.text
        assert "Permanent SendGrid 400 for invitation inv-log-1" in caplog.text

    def test_retryable_failure_log_names_the_invitation(self, caplog):
        with pytest.raises(RuntimeError, match="SendGrid error"):
            self._send(
                {"status": "error", "status_code": 503, "error": "SendGrid API error: 503"}, caplog
            )

        assert self.ADDRESS not in caplog.text
        assert "Retryable SendGrid failure for invitation inv-log-1" in caplog.text

    def test_bulk_fan_out_result_and_log_name_invitations_only(self, caplog):
        queued = MagicMock()
        queued.id = "task-1"
        with patch.object(
            tasks.send_invitation_email_task, "apply_async", return_value=queued
        ), caplog.at_level("DEBUG"):
            result = send_bulk_invitations_task(
                [{"invitation_id": "inv-b1", "to_email": self.ADDRESS, "inviter_name": "Jane"}]
            )

        assert result["results"] == [
            {"invitation_id": "inv-b1", "task_id": "task-1", "status": "queued"}
        ]
        assert self.ADDRESS not in repr(result)
        assert self.ADDRESS not in caplog.text
        assert "inv-b1" in caplog.text
