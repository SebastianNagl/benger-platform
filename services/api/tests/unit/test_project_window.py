"""Unit tests for the pure project access-window predicates.

``project_window_state`` / ``project_reads_allowed`` / ``project_writes_allowed``
(services/shared/project_window.py) are pure functions of the two window columns
+ ``now`` — no DB, no raise. This is the full truth table, including the
one-sided-window cases (only a start, or only an end).
"""

from datetime import datetime, timedelta, timezone

from project_window import (
    project_reads_allowed,
    project_window_state,
    project_writes_allowed,
)


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


class _P:
    def __init__(self, start=None, end=None):
        self.window_start_at = start
        self.window_end_at = end


def test_no_window_is_always_open():
    p = _P()
    assert project_window_state(p, NOW) == "none"
    assert project_reads_allowed(p, NOW) is True
    assert project_writes_allowed(p, NOW) is True


def test_upcoming_hides_data_and_blocks_writes():
    p = _P(NOW + timedelta(hours=1), NOW + timedelta(hours=3))
    assert project_window_state(p, NOW) == "upcoming"
    assert project_reads_allowed(p, NOW) is False
    assert project_writes_allowed(p, NOW) is False


def test_open_allows_reads_and_writes():
    p = _P(NOW - timedelta(hours=1), NOW + timedelta(hours=1))
    assert project_window_state(p, NOW) == "open"
    assert project_reads_allowed(p, NOW) is True
    assert project_writes_allowed(p, NOW) is True


def test_closed_is_viewable_but_immutable():
    p = _P(NOW - timedelta(hours=3), NOW - timedelta(hours=1))
    assert project_window_state(p, NOW) == "closed"
    assert project_reads_allowed(p, NOW) is True  # review after close
    assert project_writes_allowed(p, NOW) is False  # immutable after close


def test_start_only_never_closes():
    assert project_window_state(_P(NOW + timedelta(hours=1), None), NOW) == "upcoming"
    assert project_window_state(_P(NOW - timedelta(hours=1), None), NOW) == "open"


def test_end_only_opens_immediately_then_closes():
    assert project_window_state(_P(None, NOW + timedelta(hours=1)), NOW) == "open"
    assert project_window_state(_P(None, NOW - timedelta(hours=1)), NOW) == "closed"


def test_boundaries_inclusive():
    # exactly at start ⇒ open (not upcoming); exactly at end ⇒ open (not closed)
    assert project_window_state(_P(NOW, NOW + timedelta(hours=1)), NOW) == "open"
    assert project_window_state(_P(NOW - timedelta(hours=1), NOW), NOW) == "open"


def test_defaults_to_now_when_not_passed():
    # A far-future start is always 'upcoming' regardless of the real clock.
    far = datetime(2999, 1, 1, tzinfo=timezone.utc)
    assert project_window_state(_P(far, None)) == "upcoming"
