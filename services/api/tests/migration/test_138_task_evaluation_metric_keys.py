"""Shape tests for migration 138: the ``task_evaluation_metric_keys`` mirror.

The shared test DB already carries the table, its index, the function and
the triggers (``create_all`` and its metadata listener), so ``upgrade()``
must return through its guards. The fill mirrors exactly the missing rows
across batch boundaries and drops orphans; ``downgrade()`` removes all of it
and ``add_schema()`` rebuilds table, function and triggers.
"""
from __future__ import annotations

import importlib.util
import json
import os
import uuid
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)


def _load(name: str = "138_task_evaluation_metric_keys"):
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


def _has_trigger(conn) -> bool:
    return conn.execute(
        text(
            "SELECT 1 FROM pg_trigger WHERE tgname = "
            "'trg_task_evaluation_metric_keys' AND NOT tgisinternal"
        )
    ).first() is not None


def _seed_rows(test_db: Session, metrics_list):
    """Task evaluations with the given metrics, returned as their ids."""
    from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation, User
    from project_models import Project, Task

    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()), username=f"mig138-{suffix}", email=f"mig138-{suffix}@example.com",
        hashed_password="x", name="Mig 138",
    )
    test_db.add(user)
    test_db.flush()
    project = Project(id=str(uuid.uuid4()), title="mig138", created_by=user.id)
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
    ids = []
    for i, metrics in enumerate(metrics_list):
        row = TaskEvaluation(
            id=f"mig138-{suffix}-{i:03d}", evaluation_id=run.id, judge_run_id=judge.id,
            task_id=task.id, field_name=f"f{i}", answer_type="text", ground_truth="x",
            prediction="x", metrics=metrics, passed=True,
        )
        test_db.add(row)
        ids.append(row.id)
    test_db.flush()
    return ids


def _keys(conn, ids):
    rows = conn.execute(
        text(
            "SELECT task_evaluation_id, metric_keys FROM task_evaluation_metric_keys "
            "WHERE task_evaluation_id = ANY(:ids)"
        ),
        {"ids": ids},
    ).all()
    return {r.task_evaluation_id: r.metric_keys for r in rows}


class TestMigration138Shape:
    def test_revision_chains_after_137(self):
        mig = _load()
        assert mig.revision == "138_task_evaluation_metric_keys"
        assert mig.down_revision == "137_task_rubric_review"

    def test_upgrade_is_a_no_op_on_the_finished_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert "task_evaluation_metric_keys" in inspect(conn).get_table_names()
        assert _has_trigger(conn)
        assert mig._index_state(conn) is True

    def test_rebuilt_triggers_keep_the_mirror(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
            mig.add_schema()

        def mirror(row_id):
            return conn.execute(
                text(
                    "SELECT evaluation_id, evaluation_config_id, metric_keys "
                    "FROM task_evaluation_metric_keys WHERE task_evaluation_id = :id"
                ),
                {"id": row_id},
            ).first()

        first, second = _seed_rows(test_db, [{"rouge": 1, "bleu": 2}, {"chrf": 1}])
        evaluation_id = mirror(first).evaluation_id
        assert tuple(mirror(first)) == (evaluation_id, None, ["bleu", "rouge"])
        assert tuple(mirror(second)) == (evaluation_id, None, ["chrf"])

        conn.execute(
            text(
                "UPDATE task_evaluations SET metrics = CAST(:m AS jsonb), "
                "evaluation_config_id = 'cfg-x' WHERE id = :id"
            ),
            {"m": json.dumps({"exact_match": 1}), "id": first},
        )
        assert tuple(mirror(first)) == (evaluation_id, "cfg-x", ["exact_match"])

        conn.execute(text("DELETE FROM task_evaluations WHERE id = :id"), {"id": first})
        assert mirror(first) is None
        assert mirror(second) is not None

        conn.execute(text("TRUNCATE task_evaluations CASCADE"))
        assert conn.execute(text("SELECT count(*) FROM task_evaluation_metric_keys")).scalar() == 0

    def test_table_matches_the_model(self, test_db: Session):
        from models import TaskEvaluationMetricKeys

        conn = test_db.get_bind()
        columns = {c["name"]: c for c in inspect(conn).get_columns("task_evaluation_metric_keys")}
        assert set(columns) == {c.name for c in TaskEvaluationMetricKeys.__table__.columns}
        for column in TaskEvaluationMetricKeys.__table__.columns:
            assert columns[column.name]["nullable"] == column.nullable

    def test_function(self, test_db: Session):
        conn = test_db.get_bind()
        for value, expected in (
            ({"b": 1, "a": {"x": 1}}, ["a", "b"]),
            ({}, []),
            ([1, 2], []),
            ("s", []),
        ):
            got = conn.execute(
                text("SELECT task_evaluation_metric_keys(CAST(:m AS jsonb))"),
                {"m": json.dumps(value)},
            ).scalar()
            assert got == expected

    def test_fill_mirrors_missing_rows_and_drops_orphans(self, test_db: Session):
        conn = test_db.get_bind()
        ids = _seed_rows(
            test_db,
            [{"bleu": 1, "rouge": 2}, {"exact_match": 1}, [1], {"chrf": 1}, {"z": 1, "a": 2}],
        )
        # A database from before the migration: the seeded rows have no
        # mirror yet, and one mirror row has lost its task evaluation.
        conn.execute(
            text("DELETE FROM task_evaluation_metric_keys WHERE task_evaluation_id = ANY(:ids)"),
            {"ids": ids},
        )
        conn.execute(
            text(
                "INSERT INTO task_evaluation_metric_keys (task_evaluation_id, evaluation_id, "
                "metric_keys) VALUES ('mig138-orphan', 'gone', '[]')"
            )
        )
        mig = _load()
        assert mig.fill(conn, blocks=1) == len(ids)
        assert _keys(conn, ids) == {
            ids[0]: ["bleu", "rouge"],
            ids[1]: ["exact_match"],
            ids[2]: [],
            ids[3]: ["chrf"],
            ids[4]: ["a", "z"],
        }
        assert _keys(conn, ["mig138-orphan"]) == {}
        assert mig.fill(conn, blocks=1) == 0
        mig.build_index(conn)
        assert mig._index_state(conn) is True

    def test_downgrade_then_add_schema_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert "task_evaluation_metric_keys" not in inspect(conn).get_table_names()
        assert not _has_trigger(conn)
        assert conn.execute(
            text("SELECT 1 FROM pg_proc WHERE proname = 'task_evaluation_metric_keys'")
        ).first() is None
        with _op_context(conn):
            mig.add_schema()
        assert "task_evaluation_metric_keys" in inspect(conn).get_table_names()
        assert _has_trigger(conn)
