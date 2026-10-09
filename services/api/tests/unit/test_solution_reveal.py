"""``services/shared/solution_reveal.py``: the reference and step-detail
reveal rules (migration 116)."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from solution_reveal import reference_revealed, step_detail_revealed  # noqa: E402


def _project(full, steps):
    return SimpleNamespace(
        annotator_full_visibility_after_submit=full,
        annotator_step_detail_after_submit=steps,
    )


@pytest.mark.parametrize("full", [True, False])
def test_null_follows_the_reference_switch(full):
    assert step_detail_revealed(_project(full, None)) is full
    assert reference_revealed(_project(full, None)) is full


@pytest.mark.parametrize("full", [True, False])
@pytest.mark.parametrize("steps", [True, False])
def test_explicit_value_wins_and_leaves_the_reference_alone(full, steps):
    project = _project(full, steps)
    assert step_detail_revealed(project) is steps
    assert reference_revealed(project) is full


def test_objects_without_the_columns_reveal_nothing():
    assert step_detail_revealed(SimpleNamespace()) is False
    assert reference_revealed(SimpleNamespace()) is False
