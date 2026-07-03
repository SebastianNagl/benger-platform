"""Unit tests for the SRS daily-limit primitives (issue #35 caps).

Pure functions only (no DB): the 04:00 Europe/Berlin day-rollover window and the
cap-resolution fallback. The rollover is the subtle bit — a review just after
midnight must count toward the *previous* study day, and the boundary must stay
at 04:00 local across the CET/CEST DST switch — so it's pinned here rather than
left to a hard-to-reproduce live test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from routers.projects.srs import (
    NEW_PER_DAY_DEFAULT,
    REVIEW_PER_DAY_DEFAULT,
    _caps_from_row,
    _srs_day_window,
)

_BERLIN = ZoneInfo("Europe/Berlin")


def _berlin(dt):
    return dt.astimezone(_BERLIN)


def test_window_is_24h_starting_4am_berlin_winter():
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # CET (UTC+1)
    start, end = _srs_day_window(now)
    assert start <= now < end
    assert _berlin(start).hour == 4
    assert _berlin(end).hour == 4
    assert _berlin(start).day == 15


def test_window_starts_4am_berlin_in_summer_dst():
    # July → CEST (UTC+2); the boundary must still be 04:00 *local*, proving the
    # window is DST-aware (not a fixed UTC offset).
    now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    start, end = _srs_day_window(now)
    assert start <= now < end
    assert _berlin(start).hour == 4
    assert _berlin(end).hour == 4


def test_before_4am_local_counts_as_previous_day():
    # 02:00 Berlin (= 01:00 UTC in winter) is still "yesterday" for study counts.
    now = datetime(2026, 1, 15, 1, 0, tzinfo=timezone.utc)
    start, _ = _srs_day_window(now)
    s = _berlin(start)
    assert s.hour == 4 and s.day == 14


def test_after_4am_local_counts_as_same_day():
    now = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)  # 10:00 Berlin
    start, _ = _srs_day_window(now)
    s = _berlin(start)
    assert s.hour == 4 and s.day == 15


def test_caps_from_row_falls_back_to_defaults():
    assert _caps_from_row(None) == (NEW_PER_DAY_DEFAULT, REVIEW_PER_DAY_DEFAULT)


def test_caps_from_row_uses_overrides_and_per_field_fallback():
    class _Row:
        new_per_day = 5
        review_per_day = None

    assert _caps_from_row(_Row()) == (5, REVIEW_PER_DAY_DEFAULT)

    class _Row2:
        new_per_day = None
        review_per_day = 7

    assert _caps_from_row(_Row2()) == (NEW_PER_DAY_DEFAULT, 7)

    class _Row3:
        new_per_day = 0
        review_per_day = 0

    # 0 is a real override ("study none today"), NOT a fall-through to default.
    assert _caps_from_row(_Row3()) == (0, 0)
