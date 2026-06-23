"""Tests for notification_service.py — notification helpers and NotificationService.

As of the mailer consolidation, the worker's ``notification_service`` is a thin
re-export shim over the canonical ORM implementation in
``services/shared/mailer/notification_service.py``. The worker's former 198-line
raw-SQL stub (``db.execute(text("INSERT ... CAST(:type AS notificationtype)"))``
returning ``[{"id": ..., "user_id": ...}]`` dicts, with **no** in_app preference
gating) is gone. These tests therefore assert the **ORM** behavior:

* ``create_notification`` builds ``Notification`` ORM objects and ``db.add``s
  them (it no longer calls ``db.execute`` with raw SQL),
* it now **respects the in_app preference** — recipients are gated through
  ``NotificationService._user_wants_channel(db, user_id, type, "in_app")``,
* it returns the list of created ``Notification`` ORM objects,
* it coerces / validates the type via ``NotificationType(...)`` (invalid strings
  and non-str/non-enum types return ``[]``),
* it dispatches the email batch via
  ``mailer.notification_service.get_celery_app().send_task(...)`` after commit.

The worker-only logging helpers (``notify_task_completed`` etc.) remain defined
on the worker shim and are covered unchanged.
"""

import logging
from unittest.mock import MagicMock, Mock, patch

from models import NotificationType
from notification_service import (
    NotificationService,
    notify_llm_generation_failed,
    notify_model_api_key_invalid,
    notify_task_completed,
)


# ---------------------------------------------------------------------------
# Logging helpers (worker-only, defined on the shim)
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
# NotificationService.create_notification (ORM behavior)
# ---------------------------------------------------------------------------
#
# The canonical create_notification:
#   1. validates/coerces notification_type (str -> NotificationType, else [])
#   2. for each user, gates on _user_wants_channel(db, uid, type, "in_app")
#   3. builds Notification(...) ORM objects and db.add()s them
#   4. db.commit() (rollback + [] on failure)
#   5. dispatches the email batch via get_celery_app().send_task(...)
#
# We use a MagicMock db. By default a MagicMock _user_wants_channel returns a
# truthy MagicMock, but to keep the assertions explicit (and to exercise the
# gating) we patch _user_wants_channel and get_celery_app per test.


def _mock_db(commit_side_effect=None):
    db = MagicMock()
    db.add = Mock()
    if commit_side_effect is not None:
        db.commit = Mock(side_effect=commit_side_effect)
    else:
        db.commit = Mock()
    db.rollback = Mock()
    return db


class TestCreateNotification:

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_single_user_adds_orm_object(self, mock_wants, mock_celery):
        mock_wants.return_value = True
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["user-1"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="Test",
            message="Hello",
        )
        assert len(result) == 1
        # ORM object, not a raw-SQL dict
        assert result[0].user_id == "user-1"
        assert result[0].type == NotificationType.PROJECT_CREATED.value
        # ORM path: db.add was used, NOT raw db.execute(INSERT ...)
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_multiple_users(self, mock_wants, mock_celery):
        mock_wants.return_value = True
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1", "u2", "u3"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="Alert",
            message="Something happened",
        )
        assert len(result) == 3
        assert db.add.call_count == 3
        assert {n.user_id for n in result} == {"u1", "u2", "u3"}

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_enum_type_stored_as_value(self, mock_wants, mock_celery):
        """A NotificationType enum is stored as its lowercase .value."""
        mock_wants.return_value = True
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=NotificationType.EVALUATION_COMPLETED,
            title="Done",
            message="Eval done",
        )
        assert result[0].type == "evaluation_completed"

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_valid_string_type_used_directly(self, mock_wants, mock_celery):
        """A valid type string is accepted and stored verbatim."""
        mock_wants.return_value = True
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type="evaluation_completed",
            title="T",
            message="M",
        )
        assert len(result) == 1
        assert result[0].type == "evaluation_completed"

    def test_invalid_string_type_returns_empty(self):
        """An unknown type string returns [] without touching the session."""
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type="totally_bogus_type",
            title="T",
            message="M",
        )
        assert result == []
        db.add.assert_not_called()

    def test_non_string_non_enum_type_returns_empty(self):
        """A non-str / non-enum type returns [] (was previously stringified by
        the raw-SQL stub; the ORM path rejects it)."""
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=42,
            title="T",
            message="M",
        )
        assert result == []
        db.add.assert_not_called()

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_data_attached_to_orm_object(self, mock_wants, mock_celery):
        mock_wants.return_value = True
        db = _mock_db()
        data = {"project_id": "p1", "model": "gpt-4"}
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
            data=data,
        )
        assert result[0].data == data

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_none_data_becomes_empty_dict(self, mock_wants, mock_celery):
        mock_wants.return_value = True
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
            data=None,
        )
        assert result[0].data == {}

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_organization_id_attached(self, mock_wants, mock_celery):
        mock_wants.return_value = True
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
            organization_id="org-1",
        )
        assert result[0].organization_id == "org-1"

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_commit_failure_rolls_back_and_returns_empty(self, mock_wants, mock_celery):
        mock_wants.return_value = True
        db = _mock_db(commit_side_effect=Exception("DB down"))
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
        )
        assert result == []
        db.rollback.assert_called_once()

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_empty_user_ids(self, mock_wants, mock_celery):
        mock_wants.return_value = True
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=[],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
        )
        assert result == []
        db.add.assert_not_called()

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_in_app_preference_gates_insert(self, mock_wants, mock_celery):
        """BEHAVIOR CHANGE: the worker path now respects the in_app preference.

        The former raw-SQL stub inserted a row for every recipient
        unconditionally. The ORM path skips recipients whose in_app channel is
        disabled — so a user who turned in-app off for this type gets no row.
        """
        # u1 wants in_app, u2 does not
        mock_wants.side_effect = lambda db, uid, ntype, channel: uid == "u1"
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1", "u2"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
        )
        assert len(result) == 1
        assert result[0].user_id == "u1"
        db.add.assert_called_once()

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_dispatches_email_batch_after_commit(self, mock_wants, mock_celery):
        """The in-app commit is followed by an emails.send_notification_batch
        dispatch (mirrors the api side; the former worker stub used
        celery.current_app directly)."""
        mock_wants.return_value = True
        mock_app = MagicMock()
        mock_celery.return_value = mock_app
        db = _mock_db()

        NotificationService.create_notification(
            db=db,
            user_ids=["u1", "u2"],
            notification_type=NotificationType.EVALUATION_COMPLETED,
            title="Done",
            message="x",
            data={"project_id": "p1"},
        )
        mock_app.send_task.assert_called_once()
        args, kwargs = mock_app.send_task.call_args
        assert args[0] == "emails.send_notification_batch"
        assert kwargs["queue"] == "emails"
        payload = kwargs["args"][0]
        assert len(payload) == 2
        assert {p["user_id"] for p in payload} == {"u1", "u2"}
        assert payload[0]["type"] == "evaluation_completed"
        assert payload[0]["title"] == "Done"

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_email_dispatch_failure_does_not_break_notification(self, mock_wants, mock_celery):
        """A failing send_task must not roll back the committed in-app rows."""
        mock_wants.return_value = True
        mock_celery.return_value.send_task.side_effect = Exception("Redis down")
        db = _mock_db()
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
        )
        assert len(result) == 1
        db.rollback.assert_not_called()

    @patch("mailer.notification_service.get_celery_app")
    @patch("mailer.notification_service.NotificationService._user_wants_channel")
    def test_no_email_dispatch_when_commit_failed(self, mock_wants, mock_celery):
        """If the in-app commit raises, we must not enqueue an email for a
        notification the user can't see — return [] without dispatch."""
        mock_wants.return_value = True
        db = _mock_db(commit_side_effect=Exception("DB down"))
        result = NotificationService.create_notification(
            db=db,
            user_ids=["u1"],
            notification_type=NotificationType.PROJECT_CREATED,
            title="T",
            message="M",
        )
        assert result == []
        mock_celery.return_value.send_task.assert_not_called()
