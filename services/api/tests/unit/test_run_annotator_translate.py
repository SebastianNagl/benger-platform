"""Unit tests for `_translate_annotator_model_ids` — the results-grid annotator
re-eval fix.

The per-cell "Neuevaluierung" button forwards the grid's synthetic
`annotator:<display>` model id in `model_ids`. The helper resolves each display
back to the annotator's user id (matching results/by_task_model.py's pseudonym
logic) and folds it into `annotator_user_ids`, so the endpoint's model_ids scope
check no longer 400s human-annotator cells.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routers.evaluations.multi_field.run import _translate_annotator_model_ids


def _db_returning(rows):
    """A mock db whose annotator-resolution query yields `rows`."""
    db = MagicMock()
    (
        db.query.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value
    ) = rows
    return db


def _row(uid, username, name, pseudonym, use_pseudonym):
    return SimpleNamespace(
        id=uid, username=username, name=name, pseudonym=pseudonym, use_pseudonym=use_pseudonym
    )


class TestTranslateAnnotatorModelIds:
    def test_passthrough_and_no_db_hit_when_no_annotator_ids(self):
        db = MagicMock()
        model_ids, annotator_ids = _translate_annotator_model_ids(
            db, "p1", ["gpt-4", "claude"], None
        )
        assert model_ids == ["gpt-4", "claude"]
        assert annotator_ids is None
        db.query.assert_not_called()

    def test_resolves_pseudonym_display_to_user_id(self):
        rows = [
            _row("u1", "alice", "Alice", "anon_1", True),
            _row("u2", "bob", "Bob", "anon_2", True),
        ]
        model_ids, annotator_ids = _translate_annotator_model_ids(
            _db_returning(rows), "p1", ["annotator:anon_1"], None
        )
        assert model_ids is None  # only the synthetic annotator id was supplied
        assert annotator_ids == ["u1"]

    def test_resolves_name_display_when_not_pseudonymous(self):
        rows = [_row("u3", "carol_u", "Carol", None, False)]
        _, annotator_ids = _translate_annotator_model_ids(
            _db_returning(rows), "p1", ["annotator:Carol"], None
        )
        assert annotator_ids == ["u3"]

    def test_keeps_real_model_ids_and_merges_existing_annotators(self):
        rows = [_row("u1", "alice", "Alice", "anon_1", True)]
        model_ids, annotator_ids = _translate_annotator_model_ids(
            _db_returning(rows), "p1", ["gpt-4", "annotator:anon_1"], ["u9"]
        )
        assert model_ids == ["gpt-4"]
        assert set(annotator_ids) == {"u1", "u9"}

    def test_400_when_display_matches_no_annotator(self):
        db = _db_returning([_row("u1", "a", "A", "anon_1", True)])
        with pytest.raises(HTTPException) as exc:
            _translate_annotator_model_ids(db, "p1", ["annotator:ghost"], None)
        assert exc.value.status_code == 400
        assert "not found" in exc.value.detail
