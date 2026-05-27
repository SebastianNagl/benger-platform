"""Tests for notification_service.py - notification helpers and NotificationService.

Covers:
- notify_task_completed logging
- notify_llm_generation_failed logging
- notify_model_api_key_invalid logging
- NotificationService.create_notification with mocked DB
- Notification type conversion (enum, string, other)
- DB commit failure handling
"""

import json
import logging
from unittest.mock import MagicMock, patch


from notification_service import (
    NotificationService,
    notify_llm_generation_failed,
    notify_model_api_key_invalid,
    notify_task_completed,
)


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

class TestNotifyTaskCompleted:

    def test_logs_info(self, caplog):
        with caplog.at_level(logging.INFO, logger="notification_service"):
            notify_task_completed(task_id="t1", task_name="My Task", user_id="u1")
        assert "Task completed" in caplog.text
        assert "My Task" in caplog.text
        assert "u1" in caplog.text

    def test_accepts_kwargs(self):
        # Should not raise even with extra keyword arguments
        notify_task_completed(task_id="t1", task_name="T", user_id="u1", extra="ignored")


class TestNotifyLLMGenerationFailed:

    def test_logs_error(self, caplog):
        with caplog.at_level(logging.ERROR, logger="notification_service"):
            notify_llm_generation_failed(task_id="t1", error_message="timeout")
        assert "timeout" in caplog.text

    def test_accepts_kwargs(self):
        notify_llm_generation_failed(task_id="t1", error_message="err", foo="bar")


class TestNotifyModelApiKeyInvalid:

    def test_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="notification_service"):
            notify_model_api_key_invalid(model_id="gpt-4", user_id="u1")
        assert "Invalid API key" in caplog.text
        assert "gpt-4" in caplog.text

    def test_accepts_kwargs(self):
        notify_model_api_key_invalid(model_id="m", user_id="u", extra=True)


# ---------------------------------------------------------------------------
# NotificationService.create_notification
# ---------------------------------------------------------------------------

class TestCreateNotification:

    def _make_mock_db(self, commit_side_effect=None):
        db = MagicMock()
        if commit_side_effect:
            db.commit.side_effect = commit_side_effect
        return db

    def test_single_user(self):
        db = self._make_mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["user-1"],
            notification_type="info",
            title="Test",
            message="Hello",
        )
        assert len(result) == 1
        assert result[0]["user_id"] == "user-1"
        assert "id" in result[0]
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    def test_multiple_users(self):
        db = self._make_mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1", "u2", "u3"],
            notification_type="alert",
            title="Alert",
            message="Something happened",
        )
        assert len(result) == 3
        assert db.execute.call_count == 3

    def test_enum_type_converted(self):
        """notification_type with a .value attribute should use its value."""
        db = self._make_mock_db()
        enum_type = MagicMock()
        enum_type.value = "evaluation_completed"
        NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=enum_type,
            title="Done",
            message="Eval done",
        )
        # Verify the SQL params use the .value string
        call_args = db.execute.call_args
        params = call_args[0][1]
        assert params["type"] == "evaluation_completed"

    def test_string_type_lowered(self):
        db = self._make_mock_db()
        NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type="ALERT",
            title="T",
            message="M",
        )
        params = db.execute.call_args[0][1]
        assert params["type"] == "alert"

    def test_other_type_stringified(self):
        db = self._make_mock_db()
        NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=42,
            title="T",
            message="M",
        )
        params = db.execute.call_args[0][1]
        assert params["type"] == "42"

    def test_data_serialized_as_json(self):
        db = self._make_mock_db()
        data = {"project_id": "p1", "model": "gpt-4"}
        NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type="info",
            title="T",
            message="M",
            data=data,
        )
        params = db.execute.call_args[0][1]
        assert json.loads(params["data"]) == data

    def test_none_data_serialized_as_empty_dict(self):
        db = self._make_mock_db()
        NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type="info",
            title="T",
            message="M",
            data=None,
        )
        params = db.execute.call_args[0][1]
        assert json.loads(params["data"]) == {}

    def test_organization_id_passed(self):
        db = self._make_mock_db()
        NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type="info",
            title="T",
            message="M",
            organization_id="org-1",
        )
        params = db.execute.call_args[0][1]
        assert params["organization_id"] == "org-1"

    def test_commit_failure_returns_empty(self):
        db = self._make_mock_db(commit_side_effect=Exception("DB down"))
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type="info",
            title="T",
            message="M",
        )
        assert result == []
        db.rollback.assert_called_once()

    def test_empty_user_ids(self):
        db = self._make_mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=[],
            notification_type="info",
            title="T",
            message="M",
        )
        assert result == []
        db.execute.assert_not_called()

    def test_dispatches_email_batch_after_commit(self):
        """Regression: the worker-side NotificationService used to commit
        the in-app row and then return — silently skipping the email send.
        Users with email_enabled=True saw the bell light up but never got
        an email for any worker-triggered notification (evaluation
        completed/failed, llm generation completed). Mirrors the API-side
        dispatch added 2026-05-18.
        """
        db = self._make_mock_db()
        with patch("celery.current_app") as mock_app:
            NotificationService.create_notification(
                db=db,
                user_ids=["u1", "u2"],
                notification_type="evaluation_completed",
                title="Done",
                message="x",
                data={"project_id": "p1"},
            )
        mock_app.send_task.assert_called_once()
        args, kwargs = mock_app.send_task.call_args
        assert args[0] == "emails.send_notification_batch"
        assert kwargs["queue"] == "emails"
        # Each recipient gets a payload entry
        payload = kwargs["args"][0]
        assert len(payload) == 2
        assert {p["user_id"] for p in payload} == {"u1", "u2"}
        assert payload[0]["type"] == "evaluation_completed"
        assert payload[0]["title"] == "Done"

    def test_email_dispatch_failure_does_not_break_notification(self):
        """A failing send_task must not roll back the in-app commit."""
        db = self._make_mock_db()
        with patch("celery.current_app") as mock_app:
            mock_app.send_task.side_effect = Exception("Redis down")
            result = NotificationService.create_notification(
                db=db,
                user_ids=["u1"],
                notification_type="info",
                title="T",
                message="M",
            )
        # The commit still happened and the function returned the recipients
        assert len(result) == 1
        db.rollback.assert_not_called()

    def test_no_email_dispatch_when_commit_failed(self):
        """If the in-app commit raises, we must not enqueue an email for
        a notification the user can't see — return [] without dispatch."""
        db = self._make_mock_db(commit_side_effect=Exception("DB down"))
        with patch("celery.current_app") as mock_app:
            result = NotificationService.create_notification(
                db=db,
                user_ids=["u1"],
                notification_type="info",
                title="T",
                message="M",
            )
        assert result == []
        mock_app.send_task.assert_not_called()
