"""Data tests for migration 102: re-file human rubric gradings.

`korrektur_custom` rows were written under a hardcoded `field_name = "answer"`
while the `llm_judge_rubric` row of the SAME submission carried the real field.
The pure `_field_for_project` helper decides what the row should say; the
migration is then run against the DB to prove it rewrites only the rows that
still say "answer" AND carry a `korrektur_custom` metric -- the many legitimate
rows of projects whose annotation field really is called "answer" must be left
alone.
"""

from __future__ import annotations

import importlib.util
import json
import os
import uuid
from contextlib import contextmanager

import sqlalchemy as sa

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "alembic", "versions",
        "102_korrektur_custom_graded_field.py",
    )
)


def _load():
    spec = importlib.util.spec_from_file_location("mig_102", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


mig = _load()


def _entry(metric, fields=None):
    out = {"metric": metric}
    if fields is not None:
        out["prediction_fields"] = fields
    return out


class TestFieldForProject:
    def test_the_human_lane_own_configuration_wins(self):
        config = {
            "evaluation_configs": [
                _entry("llm_judge_rubric", ["loesung"]),
                _entry("korrektur_custom", ["gliederung"]),
            ]
        }
        assert mig._field_for_project(config) == "gliederung"

    def test_it_falls_back_to_the_judge_peer(self):
        config = {"evaluation_configs": [_entry("llm_judge_rubric", ["loesung"])]}
        assert mig._field_for_project(config) == "loesung"

    def test_the_legacy_custom_judge_counts_as_a_peer(self):
        config = {"evaluation_configs": [_entry("llm_judge_custom", ["antwort"])]}
        assert mig._field_for_project(config) == "antwort"

    def test_a_json_string_column_is_parsed(self):
        config = json.dumps(
            {"evaluation_configs": [_entry("korrektur_custom", ["loesung"])]}
        )
        assert mig._field_for_project(config) == "loesung"

    def test_nothing_usable_yields_none(self):
        assert mig._field_for_project(None) is None
        assert mig._field_for_project("not json") is None
        assert mig._field_for_project({}) is None
        assert mig._field_for_project({"evaluation_configs": [_entry("x")]}) is None


class TestAgainstTheDatabase:
    def _seed(self, db, owner_id, *, configs, field_name, metrics):
        from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation
        from project_models import Project, Task

        project = Project(
            id=str(uuid.uuid4()), title="mig102", created_by=owner_id,
            evaluation_config={"evaluation_configs": configs},
        )
        db.add(project)
        db.flush()
        task = Task(
            id=str(uuid.uuid4()), project_id=project.id, inner_id=1, data={}
        )
        db.add(task)
        db.flush()
        run = EvaluationRun(
            id=str(uuid.uuid4()), project_id=project.id, model_id="mig102",
            evaluation_type_ids=["korrektur_custom"], metrics={},
            status="completed", created_by=owner_id,
        )
        db.add(run)
        db.flush()
        judge_run = EvaluationJudgeRun(
            id=str(uuid.uuid4()), evaluation_id=run.id,
            judge_model_id="human", run_index=0, status="completed",
        )
        db.add(judge_run)
        db.flush()
        row = TaskEvaluation(
            id=str(uuid.uuid4()), task_id=task.id, evaluation_id=run.id,
            judge_run_id=judge_run.id, answer_type="long_text",
            ground_truth="", prediction="", passed=False,
            field_name=field_name, metrics=metrics,
        )
        db.add(row)
        db.commit()
        return project, task, row

    def test_it_refiles_the_rubric_row_and_spares_the_rest(self, test_db, test_user):
        from models import TaskEvaluation

        _p1, _t1, target = self._seed(
            test_db, test_user.id,
            configs=[_entry("llm_judge_rubric", ["loesung"]),
                     _entry("korrektur_custom", ["loesung"])],
            field_name="answer",
            metrics={"korrektur_custom": {"value": 0.5, "details": {}}},
        )
        # A project whose annotation field genuinely IS "answer", graded by a
        # different metric. Must not be touched.
        _p2, _t2, bystander = self._seed(
            test_db, test_user.id,
            configs=[_entry("llm_judge_custom", ["answer"])],
            field_name="answer",
            metrics={"llm_judge_custom": {"value": 0.9, "details": {}}},
        )
        try:
            with _bound(test_db):
                mig.upgrade()
            test_db.expire_all()
            assert test_db.get(TaskEvaluation, target.id).field_name == "loesung"
            assert test_db.get(TaskEvaluation, bystander.id).field_name == "answer"

            # Idempotent: nothing left saying "answer" for that metric.
            with _bound(test_db):
                mig.upgrade()
            test_db.expire_all()
            assert test_db.get(TaskEvaluation, target.id).field_name == "loesung"
        finally:
            for row in (target, bystander):
                test_db.query(TaskEvaluation).filter(
                    TaskEvaluation.id == row.id
                ).delete()
            test_db.commit()

    def test_a_project_without_configuration_is_left_alone(self, test_db, test_user):
        from models import TaskEvaluation

        _p, _t, row = self._seed(
            test_db, test_user.id, configs=[], field_name="answer",
            metrics={"korrektur_custom": {"value": 0.5, "details": {}}},
        )
        try:
            with _bound(test_db):
                mig.upgrade()
            test_db.expire_all()
            # No config, no sibling rows to learn from -> untouched, not guessed.
            assert test_db.get(TaskEvaluation, row.id).field_name == "answer"
        finally:
            test_db.query(TaskEvaluation).filter(
                TaskEvaluation.id == row.id
            ).delete()
            test_db.commit()


@contextmanager
def _bound(db):
    """Point the migration's `op.get_bind()` at the test transaction."""
    original = mig.op.get_bind
    mig.op.get_bind = lambda: db.connection()  # type: ignore[assignment]
    try:
        yield
    finally:
        mig.op.get_bind = original  # type: ignore[assignment]
