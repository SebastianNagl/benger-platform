"""Branch-coverage tests for NotificationService._user_wants_channel.

After the mailer consolidation, the worker's ``NotificationService`` is the
canonical ORM implementation (``services/shared/mailer/notification_service.py``),
re-exported through the worker's ``notification_service`` shim. The method now
reads preferences via the ORM —
``db.query(UserNotificationPreference).filter(...).first()`` returning a
preference object with ``.in_app_enabled`` / ``.email_enabled`` attributes —
rather than the worker's former raw-SQL ``db.execute(text(...)).first()``
returning a ``(in_app_enabled, email_enabled)`` tuple.

Behavior (unchanged across the rewrite):

  * notification_type with a ``.value`` attribute (enum) -> uses ``.value``,
  * plain-string notification_type -> uses it directly,
  * non-string / non-enum notification_type -> early return False,
  * no preference row -> default (in_app on, email off),
  * row present: in_app channel -> bool(pref.in_app_enabled);
    email channel -> bool(pref.email_enabled); any other channel -> False.

All driven with a MagicMock db whose ``.query(...).filter(...).first()`` return
is crafted per branch. No real Postgres.
"""

from unittest.mock import MagicMock

from models import NotificationType
from notification_service import NotificationService


def _db_returning_preference(pref):
    """A MagicMock db whose query(...).filter(...).first() yields ``pref``."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = pref
    return db


def _pref(in_app, email):
    """A stand-in UserNotificationPreference row."""
    p = MagicMock()
    p.in_app_enabled = in_app
    p.email_enabled = email
    return p


# ============================================================================
# notification_type coercion branches
# ============================================================================


class TestNotificationTypeCoercion:
    def test_enum_uses_value_in_query(self):
        """A NotificationType enum -> filters by its .value, default-on for in_app."""
        db = _db_returning_preference(None)  # no pref row -> default
        result = NotificationService._user_wants_channel(
            db, "u1", NotificationType.EVALUATION_COMPLETED, "in_app"
        )
        # Default-when-missing: in_app enabled
        assert result is True

    def test_plain_string_used_directly(self):
        db = _db_returning_preference(None)
        result = NotificationService._user_wants_channel(
            db, "u2", "evaluation_failed", "in_app"
        )
        assert result is True

    def test_non_string_non_enum_returns_false_without_query(self):
        """An int (no .value, not a str) -> early return False, DB never hit."""
        db = MagicMock()
        result = NotificationService._user_wants_channel(db, "u3", 12345, "in_app")
        assert result is False
        assert not db.query.called


# ============================================================================
# no preference row -> defaults (in_app on, email off)
# ============================================================================


class TestNoPreferenceRow:
    def test_missing_row_in_app_default_on(self):
        db = _db_returning_preference(None)
        assert (
            NotificationService._user_wants_channel(db, "u", "evaluation_completed", "in_app")
            is True
        )

    def test_missing_row_email_default_off(self):
        db = _db_returning_preference(None)
        assert (
            NotificationService._user_wants_channel(db, "u", "evaluation_completed", "email")
            is False
        )


# ============================================================================
# preference row present -> read per channel
# ============================================================================


class TestPreferenceRowPresent:
    def test_in_app_reads_in_app_enabled_true(self):
        db = _db_returning_preference(_pref(in_app=True, email=False))
        assert (
            NotificationService._user_wants_channel(db, "u", "evaluation_completed", "in_app")
            is True
        )

    def test_in_app_disabled_when_in_app_enabled_false(self):
        db = _db_returning_preference(_pref(in_app=False, email=True))
        assert (
            NotificationService._user_wants_channel(db, "u", "evaluation_completed", "in_app")
            is False
        )

    def test_email_reads_email_enabled_true(self):
        db = _db_returning_preference(_pref(in_app=False, email=True))
        assert (
            NotificationService._user_wants_channel(db, "u", "evaluation_completed", "email")
            is True
        )

    def test_email_disabled_when_email_enabled_false(self):
        db = _db_returning_preference(_pref(in_app=True, email=False))
        assert (
            NotificationService._user_wants_channel(db, "u", "evaluation_completed", "email")
            is False
        )

    def test_unknown_channel_returns_false(self):
        """A row exists but the requested channel is neither in_app nor email."""
        db = _db_returning_preference(_pref(in_app=True, email=True))
        assert (
            NotificationService._user_wants_channel(db, "u", "evaluation_completed", "sms")
            is False
        )
