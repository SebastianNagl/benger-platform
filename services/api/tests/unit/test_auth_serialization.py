"""Unit tests for auth_module.serialization — the defensive DB-value ->
wire-format converters shared by db_user_to_user and the /auth/me extras.

The isinstance guards are load-bearing: several auth unit tests build DB users
as Mocks, whose attributes are truthy child Mocks. The converters must map
those (and any other non-datetime/non-dict junk) to None instead of letting a
Mock reach Pydantic validation.
"""

from datetime import datetime, timezone
from unittest.mock import Mock

from auth_module.serialization import ensure_dict, iso_or_none


class TestIsoOrNone:
    def test_tz_aware_datetime(self):
        assert (
            iso_or_none(datetime(2026, 1, 1, tzinfo=timezone.utc))
            == "2026-01-01T00:00:00+00:00"
        )

    def test_naive_datetime(self):
        # SQLite test DBs can yield naive datetimes — offset-less ISO is fine
        assert iso_or_none(datetime(2026, 1, 1, 12, 30)) == "2026-01-01T12:30:00"

    def test_none(self):
        assert iso_or_none(None) is None

    def test_mock(self):
        assert iso_or_none(Mock()) is None

    def test_string_passthrough_rejected(self):
        # Already-serialized values are not double-converted; callers hand in
        # the raw column value or nothing.
        assert iso_or_none("2026-01-01T00:00:00+00:00") is None


class TestLeanUserCoercion:
    """The lean auth User coerces the pref fields at the schema boundary —
    endpoints like signup and PATCH /users/{id}/verify-email put raw ORM rows
    through response_model=User, so datetime columns (and Mock rows in unit
    tests) must not fail Optional[str]/Optional[dict] validation."""

    def _kwargs(self, **overrides):
        base = dict(
            id="u1",
            username="u",
            email="u@example.com",
            name="U",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        base.update(overrides)
        return base

    def test_datetime_column_becomes_iso_string(self):
        from auth_module.models import User

        user = User(
            **self._kwargs(
                vertretbar_onboarding_completed_at=datetime(
                    2026, 1, 1, tzinfo=timezone.utc
                )
            )
        )
        assert user.vertretbar_onboarding_completed_at == "2026-01-01T00:00:00+00:00"

    def test_string_and_none_pass_through(self):
        from auth_module.models import User

        assert (
            User(**self._kwargs(vertretbar_onboarding_completed_at="2026-01-01T00:00:00+00:00"))
            .vertretbar_onboarding_completed_at
            == "2026-01-01T00:00:00+00:00"
        )
        assert User(**self._kwargs()).vertretbar_onboarding_completed_at is None

    def test_mock_row_degrades_to_none(self):
        from auth_module.models import User

        user = User(
            **self._kwargs(
                vertretbar_onboarding_completed_at=Mock(), exam_layout_prefs=Mock()
            )
        )
        assert user.vertretbar_onboarding_completed_at is None
        assert user.exam_layout_prefs is None

    def test_exam_layout_json_string_parses(self):
        from auth_module.models import User

        user = User(**self._kwargs(exam_layout_prefs='{"mode": "modern"}'))
        assert user.exam_layout_prefs == {"mode": "modern"}


class TestEnsureDict:
    def test_dict(self):
        d = {"mode": "modern"}
        assert ensure_dict(d) is d

    def test_json_string(self):
        assert ensure_dict('{"a": 1}') == {"a": 1}

    def test_invalid_json(self):
        assert ensure_dict("not json") is None

    def test_json_list(self):
        assert ensure_dict("[1, 2, 3]") is None

    def test_none(self):
        assert ensure_dict(None) is None

    def test_mock(self):
        assert ensure_dict(Mock()) is None

    def test_int(self):
        assert ensure_dict(42) is None
