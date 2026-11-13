"""Shape tests for migration 130: ``tasks.source_task_id``.

The shared test DB is built from the models, so the column already exists and
``upgrade()`` must be a clean no-op twice; a downgrade drops it and a re-run
upgrade adds it back (inside the test transaction, rolled back afterwards).
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
        "130_task_source_task_id.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_130", MIGRATION_PATH)
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


def _task_columns(conn) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns("tasks")}


class TestMigration130Shape:
    def test_revision_chains_after_129(self):
        mig = _load_migration()
        assert mig.revision == "130_task_source_task_id"
        assert mig.down_revision == "129_lti_openolat_and_nrps"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert _task_columns(conn)["source_task_id"]["nullable"] is True

    def test_downgrade_then_upgrade(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        assert "source_task_id" not in _task_columns(conn)
        with _op_context(conn):
            mig.upgrade()
        assert "source_task_id" in _task_columns(conn)
