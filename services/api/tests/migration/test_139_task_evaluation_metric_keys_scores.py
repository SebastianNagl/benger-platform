"""Shape tests for migration 139: task, field, creation time and lite
metrics in the ``task_evaluation_metric_keys`` mirror.

The shared test DB already carries the columns, the function and the
trigger (``create_all``, its metadata listener and
``backfill_task_evaluation_metric_keys``), so ``upgrade()`` must return
through its guard. The trigger keeps the new columns in step with
``task_evaluations``; the stored ``metrics_lite`` equals the read-time
projection; the fill completes a mirror from before the migration across
batch boundaries; ``downgrade()`` restores migration 138's mirror.
"""
from __future__ import annotations

import importlib.util
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)

NEW_COLUMNS = {"task_id", "field_name", "created_at", "metrics_lite"}


def _load(name: str = "139_task_evaluation_metric_keys_scores"):
    spec = importlib.util.spec_from_file_location(f"mig_{name}", os.path.join(VERSIONS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


# Metrics shapes the projection has to handle: unified values with heavy
# nested fields, bare numerics, metadata keys, error values, JSON non-objects.
METRICS = [
    {
        "llm_judge_falloesung": {
            "value": 0.8,
            "details": {"rubric": "x" * 500},
            "justification": "long",
            "method": "llm_judge",
            "raw": {"tokens": 3},
            "grade": "gut",
        },
        "llm_judge_falloesung_passed": 1,
    },
    {"bleu": 0.42},
    {"llm_judge_lexam": {"value": None, "error": True}, "llm_judge_lexam_response": "text"},
    {"score": 0.5, "overall_score": {"value": 0.6, "details": [1, 2]}},
    {},
    [1, 2],
    None,
]


def _seed_rows(test_db: Session, metrics_list):
    """Task evaluations with the given metrics, returned as their ids."""
    from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation, User
    from project_models import Project, Task

    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()), username=f"mig139-{suffix}", email=f"mig139-{suffix}@example.com",
        hashed_password="x", name="Mig 139",
    )
    test_db.add(user)
    test_db.flush()
    project = Project(id=str(uuid.uuid4()), title="mig139", created_by=user.id)
    test_db.add(project)
    test_db.flush()
    task = Task(id=str(uuid.uuid4()), project_id=project.id, data={"text": "x"}, inner_id=1)
    run = EvaluationRun(
        id=str(uuid.uuid4()), project_id=project.id, model_id="m", evaluation_type_ids=["x"],
        metrics={}, eval_metadata={}, status="completed", created_by=user.id,
    )
    test_db.add_all([task, run])
    test_db.flush()
    judge = EvaluationJudgeRun(
        id=str(uuid.uuid4()), evaluation_id=run.id, judge_model_id=None, run_index=0,
        status="completed",
    )
    test_db.add(judge)
    test_db.flush()
    base = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    ids = []
    for i, metrics in enumerate(metrics_list):
        row = TaskEvaluation(
            id=f"mig139-{suffix}-{i:03d}", evaluation_id=run.id, judge_run_id=judge.id,
            task_id=task.id, field_name=f"f{i}", answer_type="text", ground_truth="x",
            prediction="x", metrics=metrics, passed=True, created_at=base + timedelta(minutes=i),
        )
        test_db.add(row)
        ids.append(row.id)
    test_db.flush()
    return ids


def _mirror(conn, ids):
    rows = conn.execute(
        text(
            "SELECT task_evaluation_id, task_id, field_name, created_at, metrics_lite "
            "FROM task_evaluation_metric_keys WHERE task_evaluation_id = ANY(:ids)"
        ),
        {"ids": ids},
    ).all()
    return {r.task_evaluation_id: tuple(r[1:]) for r in rows}


def _source(conn, ids):
    """What the mirror must hold: the row's own columns and the read-time
    lite projection of ``routers/evaluations/metrics_lite.py``."""
    from models import TaskEvaluation
    from routers.evaluations.metrics_lite import metrics_lite_expr

    rows = conn.execute(
        select(
            TaskEvaluation.id,
            TaskEvaluation.task_id,
            TaskEvaluation.field_name,
            TaskEvaluation.created_at,
            metrics_lite_expr(),
        ).where(TaskEvaluation.id.in_(ids))
    ).all()
    return {r[0]: tuple(r[1:]) for r in rows}


def _new_columns(conn):
    return {
        c["name"]: c
        for c in inspect(conn).get_columns("task_evaluation_metric_keys")
        if c["name"] in NEW_COLUMNS
    }


class TestMigration139Shape:
    def test_revision_chains_after_138(self):
        mig = _load()
        assert mig.revision == "139_task_evaluation_metric_keys_scores"
        assert mig.down_revision == "138_task_evaluation_metric_keys"

    def test_upgrade_is_a_no_op_on_the_finished_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        assert mig.is_complete(conn)
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert mig.is_complete(conn)

    def test_function(self, test_db: Session):
        conn = test_db.get_bind()
        for value, expected in (
            (
                {"j": {"value": 1, "details": 2, "method": 3, "raw": 4, "justification": 5, "k": 6}},
                {"j": {"value": 1, "k": 6}},
            ),
            ({"b": 0.5, "s": "x", "n": None, "l": [1]}, {"b": 0.5, "s": "x", "n": None, "l": [1]}),
            ({}, {}),
            ([1, 2], {}),
            ("s", {}),
            (None, {}),
        ):
            got = conn.execute(
                text("SELECT task_evaluation_metrics_lite(CAST(:m AS jsonb))"),
                {"m": json.dumps(value)},
            ).scalar()
            assert got == expected

    def test_trigger_keeps_columns_equal_to_the_read_time_projection(self, test_db: Session):
        conn = test_db.get_bind()
        ids = _seed_rows(test_db, METRICS)
        assert _mirror(conn, ids) == _source(conn, ids)

        later = datetime(2027, 1, 1, tzinfo=timezone.utc)
        conn.execute(
            text(
                "UPDATE task_evaluations SET metrics = CAST(:m AS jsonb), field_name = 'moved', "
                "created_at = :at WHERE id = :id"
            ),
            {"m": json.dumps({"chrf": {"value": 0.3, "details": {}}}), "at": later, "id": ids[0]},
        )
        assert _mirror(conn, [ids[0]])[ids[0]][1:] == ("moved", later, {"chrf": {"value": 0.3}})
        assert _mirror(conn, ids) == _source(conn, ids)

    def test_fill_completes_a_mirror_from_before_the_migration(self, test_db: Session):
        conn = test_db.get_bind()
        ids = _seed_rows(test_db, METRICS)
        # A mirror from before the migration: nullable, empty new columns,
        # and one task evaluation without a mirror row at all.
        conn.execute(
            text(
                "ALTER TABLE task_evaluation_metric_keys ALTER COLUMN task_id DROP NOT NULL, "
                "ALTER COLUMN field_name DROP NOT NULL, ALTER COLUMN created_at DROP NOT NULL, "
                "ALTER COLUMN metrics_lite DROP NOT NULL"
            )
        )
        conn.execute(
            text(
                "UPDATE task_evaluation_metric_keys SET task_id = NULL, field_name = NULL, "
                "created_at = NULL, metrics_lite = NULL WHERE task_evaluation_id = ANY(:ids)"
            ),
            {"ids": ids[1:]},
        )
        conn.execute(
            text("DELETE FROM task_evaluation_metric_keys WHERE task_evaluation_id = :id"),
            {"id": ids[0]},
        )
        mig = _load()
        assert not mig.is_complete(conn)

        written = mig.fill(conn, blocks=1)

        assert written >= len(ids)
        assert _mirror(conn, ids) == _source(conn, ids)
        assert conn.execute(
            text(
                "SELECT metric_keys FROM task_evaluation_metric_keys WHERE task_evaluation_id = :id"
            ),
            {"id": ids[0]},
        ).scalar() == ["llm_judge_falloesung", "llm_judge_falloesung_passed"]
        assert mig.fill(conn, blocks=1) == 0
        mig.set_not_null(conn)
        assert mig.is_complete(conn)

    def test_downgrade_restores_138_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert _new_columns(conn) == {}
        assert all(mig._index_state(conn, name) is None for name in mig._INDEXES)
        assert conn.execute(
            text("SELECT 1 FROM pg_proc WHERE proname = 'task_evaluation_metrics_lite'")
        ).first() is None
        # Migration 138's trigger still mirrors keys.
        (row_id,) = _seed_rows(test_db, [{"bleu": 1}])
        assert conn.execute(
            text(
                "SELECT metric_keys FROM task_evaluation_metric_keys WHERE task_evaluation_id = :id"
            ),
            {"id": row_id},
        ).scalar() == ["bleu"]

        with _op_context(conn):
            mig.add_schema()
        mig.fill(conn)
        mig.set_not_null(conn)
        # build_indexes() builds CONCURRENTLY, which cannot run inside the
        # test's transaction: the models' statements build the same indexes.
        from models import TASK_EVALUATION_METRIC_KEYS_INDEXES

        assert not mig.is_complete(conn)
        for statement in TASK_EVALUATION_METRIC_KEYS_INDEXES:
            conn.execute(text(statement))
        assert mig.is_complete(conn)
        assert set(_new_columns(conn)) == NEW_COLUMNS
        assert _mirror(conn, [row_id]) == _source(conn, [row_id])
