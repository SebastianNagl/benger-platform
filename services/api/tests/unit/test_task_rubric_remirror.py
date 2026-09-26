"""Re-mirroring the grading sheets after the exam's Notenschlüssel changed.

``task.data["bewertungsbogen"]`` mirrors the active sheet WITH the key that
grades the exam (``resolve_grade_scale``: the exam's key, else the sheet's,
else the standard key). The mirror used to refresh only when a sheet was
activated or edited, so a key change left every mirror of the project
stale. ``task_rubric_service.remirror_project_rubrics`` (async) and its sync
twin re-render them; the writers of the key call them on a change.

Pure tests (no database): the row pass, the SQL builder, and that each entry
point costs ONE query for the whole project. The Postgres round trip and
the writers are covered in
``tests/integration/test_rubric_mirror_grade_key.py``.
"""

from __future__ import annotations

from collections import namedtuple

import pytest
from sqlalchemy.dialects import postgresql

from project_models import Project, Task
from rubric_structure import (
    GRADE_SCALE_PRESETS,
    effective_grade_scale,
    normalize_structure,
    render_grade_scale_text,
    rubric_prompt_text,
)
from task_rubric_service import (
    _remirror_rows,
    _select_active_rubrics_of_project,
    remirror_project_rubrics,
    remirror_project_rubrics_sync,
)

STRUCTURE = normalize_structure(
    {
        "version": 1,
        "nodes": [
            {"id": "a", "level": 0, "kind": "section", "label": "A.", "title": "Zulässigkeit"},
            {"id": "b", "level": 1, "kind": "step", "label": "I.", "title": "Rechtsweg", "max_score": 40},
            {"id": "c", "level": 1, "kind": "step", "label": "II.", "title": "Klageart", "max_score": 60},
        ],
    }
)
EXAM_KEY = {
    "unit": "percent",
    "preset": "uebungsklausur",
    "thresholds": list(GRADE_SCALE_PRESETS["uebungsklausur"]),
    "rounding": "floor",
    "pass_grade": 4,
}
SHEET_KEY = {
    "unit": "BE",
    "thresholds": [5 * i for i in range(1, 19)],
    "rounding": "floor",
    "pass_grade": 4,
}

Row = namedtuple(
    "Row", "task title structure criteria total_points grade_scale rendered_text"
)


def _key_block(scale):
    return render_grade_scale_text(effective_grade_scale(scale, 100.0))


def _task(mirror=None):
    data = {"sachverhalt": "SV"}
    if mirror is not None:
        data["bewertungsbogen"] = mirror
    return Task(id="t1", project_id="p1", inner_id=1, data=data)


def _row(task, *, grade_scale=None, rendered_text=None):
    return Row(task, "Bogen", STRUCTURE, {}, 100.0, grade_scale, rendered_text)


def _mirror_for(row, config):
    return rubric_prompt_text(row, include_grade_scale=True, project_config=config)


class TestRowPass:
    def test_a_new_exam_key_rewrites_the_stale_mirror(self):
        task = _task()
        row = _row(task)
        # The mirror as activation wrote it, before the exam had a key.
        task.data = {**task.data, "bewertungsbogen": _mirror_for(row, {})}
        assert task.data["bewertungsbogen"].endswith(_key_block(None))

        assert _remirror_rows([row], {"grade_scale": EXAM_KEY}) == 1
        assert task.data["bewertungsbogen"].endswith(_key_block(EXAM_KEY))
        assert task.data["sachverhalt"] == "SV"

    def test_an_up_to_date_mirror_is_not_rewritten(self):
        config = {"grade_scale": EXAM_KEY}
        task = _task()
        row = _row(task)
        task.data = {**task.data, "bewertungsbogen": _mirror_for(row, config)}
        before = task.data

        assert _remirror_rows([row], config) == 0
        # Not even reassigned: no UPDATE for this row at flush.
        assert task.data is before

    def test_the_exam_key_wins_over_the_sheet_key(self):
        task = _task("alt")
        _remirror_rows([_row(task, grade_scale=SHEET_KEY)], {"grade_scale": EXAM_KEY})
        assert task.data["bewertungsbogen"].endswith(_key_block(EXAM_KEY))

    def test_a_cleared_exam_key_falls_back_to_the_sheet_key(self):
        task = _task(_mirror_for(_row(None, grade_scale=SHEET_KEY), {"grade_scale": EXAM_KEY}))
        assert _remirror_rows([_row(task, grade_scale=SHEET_KEY)], {"runs_per_task": 1}) == 1
        assert task.data["bewertungsbogen"].endswith(_key_block(SHEET_KEY))

    def test_a_cleared_exam_key_falls_back_to_the_standard_key(self):
        task = _task(_mirror_for(_row(None), {"grade_scale": EXAM_KEY}))
        assert _remirror_rows([_row(task)], {}) == 1
        assert task.data["bewertungsbogen"].endswith(_key_block(None))

    def test_no_config_never_falls_back_to_a_loaded_project(self):
        """``None`` means the project has no config. The mirror function
        would otherwise read ``task.project``, which the session may still
        hold with the OLD key."""
        task = _task("alt")
        task.project = Project(id="p1", title="P", evaluation_config={"grade_scale": EXAM_KEY})
        _remirror_rows([_row(task)], None)
        assert task.data["bewertungsbogen"].endswith(_key_block(None))

    def test_a_generated_sheet_mirrors_its_rendered_text(self):
        task = _task("alt")
        row = _row(task, rendered_text="BEWERTUNGSBOGEN (generiert)\n…")
        assert _remirror_rows([row], {"grade_scale": EXAM_KEY}) == 1
        assert task.data["bewertungsbogen"] == "BEWERTUNGSBOGEN (generiert)\n…"
        # A second pass finds it current.
        assert _remirror_rows([row], {"grade_scale": EXAM_KEY}) == 0

    def test_counts_only_the_rows_it_rewrote(self):
        config = {"grade_scale": EXAM_KEY}
        fresh = _task()
        fresh_row = _row(fresh)
        fresh.data = {**fresh.data, "bewertungsbogen": _mirror_for(fresh_row, config)}
        stale = [_task("alt") for _ in range(3)]
        assert _remirror_rows([fresh_row] + [_row(t) for t in stale], config) == 3


class TestSelect:
    def _sql(self):
        return str(
            _select_active_rubrics_of_project("p1").compile(dialect=postgresql.dialect())
        )

    def test_one_statement_joins_the_active_sheet_of_each_task(self):
        sql = self._sql()
        assert "FROM tasks JOIN task_rubrics ON task_rubrics.task_id = tasks.id" in sql
        assert "task_rubrics.status = " in sql
        assert "WHERE tasks.project_id = " in sql

    def test_reads_only_rendered_text_of_the_generation_metadata(self):
        """A generated sheet's metadata also carries the full generator
        documents; a re-render only needs the rendered text."""
        sql = self._sql()
        assert "task_rubrics.generation_metadata[" in sql
        assert "task_rubrics.generation_metadata," not in sql
        assert "task_rubrics.generation_metadata " not in sql.split("FROM")[0]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _SyncSession:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []
        self.flushes = 0

    def execute(self, statement):
        self.executed.append(statement)
        return _Result(self.rows)

    def flush(self):
        self.flushes += 1


class _AsyncSession(_SyncSession):
    async def execute(self, statement):
        return _SyncSession.execute(self, statement)

    async def flush(self):
        _SyncSession.flush(self)


class TestEntryPoints:
    """Both lanes: one query for the whole project, a flush only when a
    mirror changed."""

    def _rows(self, n):
        return [_row(_task("alt")) for _ in range(n)]

    def test_sync_twin(self):
        db = _SyncSession(self._rows(25))
        assert remirror_project_rubrics_sync(db, "p1", {"grade_scale": EXAM_KEY}) == 25
        assert len(db.executed) == 1
        assert db.flushes == 1
        # Nothing left to do: no flush.
        assert remirror_project_rubrics_sync(db, "p1", {"grade_scale": EXAM_KEY}) == 0
        assert db.flushes == 1

    @pytest.mark.asyncio
    async def test_async_entry(self):
        db = _AsyncSession(self._rows(25))
        assert await remirror_project_rubrics(db, "p1", {"grade_scale": EXAM_KEY}) == 25
        assert len(db.executed) == 1
        assert db.flushes == 1
        assert await remirror_project_rubrics(db, "p1", {"grade_scale": EXAM_KEY}) == 0
        assert db.flushes == 1

    @pytest.mark.asyncio
    async def test_a_project_without_active_sheets(self):
        db = _AsyncSession([])
        assert await remirror_project_rubrics(db, "p1", {"grade_scale": EXAM_KEY}) == 0
        assert db.flushes == 0
