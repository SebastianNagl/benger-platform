"""
Tests for invitation email Celery tasks
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tasks import send_bulk_invitations_task, send_invitation_email_task


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
        assert result["recipient"] == to_email
        assert result["organization"] == organization_name
        mock_client.send_message.assert_called_once()

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
            expected_delay = i * 2
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
            if kwargs.get('countdown', 0) == 2:
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
        """Test that email tasks are routed to the correct queue"""
        from tasks import app

        assert 'emails.*' in app.conf.task_routes
        assert app.conf.task_routes['emails.*']['queue'] == 'emails'

        assert 'emails.send_invitation' in app.conf.task_annotations
        assert app.conf.task_annotations['emails.send_invitation']['rate_limit'] == '30/m'

        assert 'emails.send_bulk_invitations' in app.conf.task_annotations
        assert app.conf.task_annotations['emails.send_bulk_invitations']['rate_limit'] == '5/m'
