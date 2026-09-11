"""Shape tests for migration 100: ``task_rubrics.structure`` / ``grade_scale``
and the Integer → Float change of ``total_points``.

The shared test DB already carries the new shape (created from the model by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guards — twice. ``downgrade()`` must drop the two JSONB columns
and turn ``total_points`` back into an integer; a re-run ``upgrade()`` must
rebuild the shape.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "100_task_rubrics_structure.py",
    )
)

TABLE = "task_rubrics"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_100", MIGRATION_PATH)
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


def _columns(conn) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns(TABLE)}


class TestMigration100Shape:
    def test_revision_chains_after_099(self):
        mig = _load_migration()
        assert mig.revision == "100_task_rubrics_structure"
        assert mig.down_revision == "099_add_grading_feedback"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            # Second run — the column/type guards must make this a no-op.
            mig.upgrade()
        columns = _columns(conn)
        assert "structure" in columns and "grade_scale" in columns
        assert isinstance(columns["total_points"]["type"], (sa.Float, sa.Numeric))

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        columns = _columns(conn)
        assert "structure" not in columns and "grade_scale" not in columns
        assert isinstance(columns["total_points"]["type"], sa.Integer)

        with _op_context(conn):
            mig.upgrade()
        columns = _columns(conn)
        assert columns["structure"]["nullable"] is True
        assert columns["grade_scale"]["nullable"] is True
        assert isinstance(columns["total_points"]["type"], (sa.Float, sa.Numeric))
        assert columns["total_points"]["nullable"] is False
