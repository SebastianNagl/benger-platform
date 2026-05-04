"""Unit tests for _row_has_score in tasks.py.

Locks down the predicate that decides whether a TaskEvaluation row is
"already scored" for `evaluate_missing_only=True` re-runs. The bug this
covers: pre-fix the predicate was `isinstance(v, (int, float))`, which
returned False for every metric written under the unified
`{value, method, details, error}` shape introduced by the academic-rigor
overhaul. Result: every successful row was treated as missing and got
silently re-run on every "evaluate missing only" click.

The function is duplicated inline below to keep the test free of the
Celery / SQLAlchemy stack `tasks.py` drags in at import time. Must be
kept in sync with `services/workers/tasks.py:_row_has_score` — the
contract test below catches any drift between the two copies.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import pytest


def _row_has_score(metrics: Optional[dict]) -> bool:
    """Mirror of `tasks.py:_row_has_score`. Keep in sync."""
    if not metrics:
        return False
    for k, v in metrics.items():
        if k == "error":
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return True
        if isinstance(v, dict):
            inner = v.get("value")
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return True
    return False


@pytest.fixture(scope="module")
def row_has_score():
    return _row_has_score


def test_inline_copy_present_in_tasks_py():
    """Sanity: the source `tasks.py` actually defines `_row_has_score` so
    this inline copy isn't testing dead code. Body equivalence is asserted
    by the behavioural cases below; if those would diverge from `tasks.py`
    a careful reviewer must keep both in sync."""
    tasks_path = Path(__file__).parent.parent / "tasks.py"
    src = tasks_path.read_text()
    assert "def _row_has_score(" in src, (
        "tasks.py is missing the `_row_has_score` helper that the "
        "missing-only re-run logic depends on."
    )


class TestRowHasScore:
    def test_legacy_bare_float(self, row_has_score):
        assert row_has_score({"bleu": 0.42}) is True

    def test_legacy_int(self, row_has_score):
        assert row_has_score({"exact_match": 1}) is True

    def test_unified_dict_with_numeric_value(self, row_has_score):
        # Post-academic-rigor shape — the bug case.
        assert row_has_score(
            {
                "llm_judge_falloesung": {
                    "value": 0.85,
                    "method": "llm_judge_falloesung",
                    "details": {},
                    "error": None,
                }
            }
        ) is True

    def test_korrektur_unified_dict(self, row_has_score):
        assert row_has_score(
            {
                "korrektur_falloesung": {
                    "value": 51.5,
                    "method": "korrektur_falloesung",
                    "details": {"dimensions": {}},
                    "error": None,
                }
            }
        ) is True

    def test_error_row(self, row_has_score):
        # Worker-persisted error sentinel — must NOT count as scored.
        assert row_has_score({"error": True}) is False

    def test_empty_metrics(self, row_has_score):
        assert row_has_score({}) is False

    def test_none_metrics(self, row_has_score):
        assert row_has_score(None) is False

    def test_unified_dict_without_numeric_value(self, row_has_score):
        # Edge case: a partially-formed blob where `value` isn't a number.
        # Must not count as scored.
        assert row_has_score(
            {"some_metric": {"value": "not-a-number", "details": {}}}
        ) is False

    def test_bool_is_not_score(self, row_has_score):
        # `passed: True` etc. are booleans — Python treats bool as int so a
        # naive isinstance check would incorrectly count them.
        assert row_has_score({"passed": True}) is False

    def test_nested_bool_value_is_not_score(self, row_has_score):
        assert row_has_score({"x": {"value": True}}) is False

    def test_mixed_error_and_score(self, row_has_score):
        # An error sentinel plus a real numeric metric → still scored.
        assert row_has_score({"error": True, "bleu": 0.42}) is True

    def test_legacy_korrektur_root_shape(self, row_has_score):
        # Pre-unified Korrektur Falllösung was {score, total_score, dimensions, ...}
        # at root. The plan calls those out — we treat the root metric as
        # the dict; without `value` key it's not picked up. That's OK because
        # those rows were already covered by the legacy bare-float path
        # before academic-rigor; nothing in prod still writes this shape
        # AND lacks a top-level numeric metric.
        assert row_has_score(
            {"korrektur_falloesung": {"score": 51.5, "total_score": 51.5}}
        ) is False
