"""``_resolve_task_rubric`` — Bewertungsbogen row selection for judge cells.

Selection semantics under test (they guard the study design): the default
is the task's single ``status='active'`` rubric; a
``metric_parameters.rubric_selector.generator_model_id`` overrides to that
generator's NEWEST non-archived candidate (the crossed rubric-source ×
judge lever, RQ4); rows whose criteria carry no ``max_score`` anywhere are
unusable for multi-dim grading and resolve to None.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from evaluation.cell_evaluator import _resolve_task_rubric

TASK = SimpleNamespace(id="task-1")

GOOD_CRITERIA = {"s01_x": {"name": "X", "rubric": "r", "max_score": 100}}
SCORELESS_CRITERIA = {"s01_x": {"name": "X", "rubric": "r"}}


def _db_returning(row, *, via_order_by):
    """Mock the sync query chain; both selector shapes end in .first()."""
    db = MagicMock()
    q = db.query.return_value.filter.return_value
    if via_order_by:
        q.filter.return_value.order_by.return_value.first.return_value = row
    else:
        q.filter.return_value.first.return_value = row
    return db


def _row(criteria=GOOD_CRITERIA, **kw):
    return SimpleNamespace(criteria=criteria, **kw)


def test_default_resolves_active_rubric():
    row = _row()
    db = _db_returning(row, via_order_by=False)
    assert _resolve_task_rubric(db, TASK, {}) is row


def test_none_metric_parameters_treated_as_default():
    row = _row()
    db = _db_returning(row, via_order_by=False)
    assert _resolve_task_rubric(db, TASK, None) is row


def test_generator_selector_takes_order_by_path():
    row = _row()
    db = _db_returning(row, via_order_by=True)
    result = _resolve_task_rubric(
        db, TASK, {"rubric_selector": {"generator_model_id": "gpt-5.4"}}
    )
    assert result is row
    # newest-first ordering was applied on the selector path
    chain = db.query.return_value.filter.return_value.filter.return_value
    assert chain.order_by.called


def test_no_active_rubric_resolves_none():
    db = _db_returning(None, via_order_by=False)
    assert _resolve_task_rubric(db, TASK, {}) is None


def test_non_dict_criteria_resolves_none():
    db = _db_returning(_row(criteria=None), via_order_by=False)
    assert _resolve_task_rubric(db, TASK, {}) is None


def test_scoreless_criteria_resolves_none():
    # A rubric without any max_score cannot drive multi-dim mode.
    db = _db_returning(_row(criteria=SCORELESS_CRITERIA), via_order_by=False)
    assert _resolve_task_rubric(db, TASK, {}) is None


def test_empty_selector_dict_uses_active_path():
    row = _row()
    db = _db_returning(row, via_order_by=False)
    assert _resolve_task_rubric(db, TASK, {"rubric_selector": {}}) is row
