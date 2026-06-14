"""Branch-coverage tests for NotificationService._user_wants_channel.

This static method (notification_service.py:147-198) decides whether a given
notification channel ('in_app' or 'email') is enabled for a user/type. The
existing test_notification_service.py covers create_notification but never
invokes _user_wants_channel with crafted inputs; test_tasks_more_coverage.py
only patches it. So every branch here is currently unreached:

  * notification_type with a .value attribute (enum-like) -> uses .value,
  * plain-string notification_type -> uses it directly,
  * non-string / non-enum notification_type -> early return False,
  * pref-lookup exception -> warn + default (in_app on, email off),
  * no preference row -> default (in_app on, email off),
  * row present: in_app channel -> bool(row[0]); email channel -> bool(row[1]);
    any other channel -> False.

All driven with a MagicMock db whose .execute(...).first() return is crafted per
branch. No real Postgres. Mirrors the MagicMock-db idioms in
test_notification_service.py.
"""

from unittest.mock import MagicMock

from notification_service import NotificationService


class _EnumLike:
    """Stand-in for a NotificationType enum member: has a `.value`."""

    def __init__(self, value):
        self.value = value


def _db_returning_row(row):
    """A MagicMock db whose execute(...).first() yields `row`."""
    db = MagicMock()
    db.execute.return_value.first.return_value = row
    return db


# ============================================================================
# notification_type coercion branches
# ============================================================================


class TestNotificationTypeCoercion:
    def test_enum_like_uses_value_in_query_params(self):
        """A type object with .value is passed as type_value to the query."""
        db = _db_returning_row(None)  # no pref row -> default
        result = NotificationService._user_wants_channel(
            db, "u1", _EnumLike("evaluation_completed"), "in_app"
        )
        # Default-when-missing: in_app enabled
        assert result is True
        # The bound :type param was the enum's .value, not its repr
        _, params = db.execute.call_args[0]
        assert params["type"] == "evaluation_completed"
        assert params["uid"] == "u1"

    def test_plain_string_used_directly(self):
        db = _db_returning_row(None)
        result = NotificationService._user_wants_channel(
            db, "u2", "evaluation_failed", "in_app"
        )
        assert result is True
        _, params = db.execute.call_args[0]
        assert params["type"] == "evaluation_failed"

    def test_non_string_non_enum_returns_false_without_query(self):
        """An int (no .value, not a str) -> early return False, DB never hit."""
        db = MagicMock()
        result = NotificationService._user_wants_channel(db, "u3", 12345, "in_app")
        assert result is False
        assert not db.execute.called


# ============================================================================
# pref-lookup exception branch
# ============================================================================


class TestPrefLookupException:
    def test_query_exception_defaults_to_in_app(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("connection reset")
        # in_app requested -> default True even on lookup failure
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "in_app")
            is True
        )

    def test_query_exception_email_defaults_off(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("connection reset")
        # email requested -> default False (email is opt-in)
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "email")
            is False
        )


# ============================================================================
# no preference row -> defaults
# ============================================================================


class TestNoPreferenceRow:
    def test_missing_row_in_app_default_on(self):
        db = _db_returning_row(None)
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "in_app")
            is True
        )

    def test_missing_row_email_default_off(self):
        db = _db_returning_row(None)
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "email")
            is False
        )


# ============================================================================
# preference row present -> read per channel
# ============================================================================


class TestPreferenceRowPresent:
    def test_in_app_reads_first_column(self):
        # row = (in_app_enabled, email_enabled)
        db = _db_returning_row((True, False))
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "in_app")
            is True
        )

    def test_in_app_disabled_when_first_column_false(self):
        db = _db_returning_row((False, True))
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "in_app")
            is False
        )

    def test_email_reads_second_column(self):
        db = _db_returning_row((False, True))
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "email")
            is True
        )

    def test_email_disabled_when_second_column_false(self):
        db = _db_returning_row((True, False))
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "email")
            is False
        )

    def test_unknown_channel_returns_false(self):
        """A row exists but the requested channel is neither in_app nor email."""
        db = _db_returning_row((True, True))
        assert (
            NotificationService._user_wants_channel(db, "u", "t_str", "sms")
            is False
        )
