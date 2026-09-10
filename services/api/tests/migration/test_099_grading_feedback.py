"""Shape tests for migration 099: the ``grading_feedback`` table.

The shared test DB already carries the table (created from the model by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guards — twice. ``downgrade()`` must drop the table; a re-run
``upgrade()`` must rebuild it with the unique index the extended upsert relies
on and the three CHECK constraints.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager

from sqlalchemy import inspect
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "099_add_grading_feedback.py",
    )
)

TABLE = "grading_feedback"
UNIQUE_INDEX = "uq_grading_feedback_user_annotation_source"
CHECKS = {
    "ck_grading_feedback_source",
    "ck_grading_feedback_rating",
    "ck_grading_feedback_not_empty",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_099", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    """Install the alembic ``op`` proxy bound to the test connection."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _tables(conn) -> set:
    return set(inspect(conn).get_table_names())


def _indexes(conn) -> dict:
    return {ix["name"]: ix for ix in inspect(conn).get_indexes(TABLE)}


class TestMigration099Shape:
    def test_revision_chains_after_098(self):
        mig = _load_migration()
        assert mig.revision == "099_add_grading_feedback"
        assert mig.down_revision == "098_project_report_public"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            # Second run — the table/index guards must make this a no-op.
            mig.upgrade()
        assert TABLE in _tables(conn)
        assert UNIQUE_INDEX in _indexes(conn)

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        assert TABLE not in _tables(conn)

        with _op_context(conn):
            mig.upgrade()
        assert TABLE in _tables(conn)

        indexes = _indexes(conn)
        assert indexes[UNIQUE_INDEX]["unique"] is True
        assert indexes[UNIQUE_INDEX]["column_names"] == [
            "user_id",
            "annotation_id",
            "grading_source",
        ]
        assert "ix_grading_feedback_project_created" in indexes
        assert "ix_grading_feedback_evaluation_run" in indexes

        columns = {c["name"] for c in inspect(conn).get_columns(TABLE)}
        assert {
            "id", "project_id", "task_id", "annotation_id", "user_id",
            "grading_source", "evaluation_run_id", "judge_model_id",
            "grade_points", "passed", "rating", "comment", "context",
            "created_at", "updated_at",
        } <= columns

        checks = {c["name"] for c in inspect(conn).get_check_constraints(TABLE)}
        assert CHECKS <= checks
