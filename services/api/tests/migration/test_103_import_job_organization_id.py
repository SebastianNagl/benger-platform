"""Shape tests for migration 103: ``import_jobs.organization_id``.

The shared test DB already carries the column (created from the model by
``Base.metadata.create_all``), so ``upgrade()`` must be a no-op through its
guard, twice. ``downgrade()`` must drop the column; a re-run ``upgrade()`` must
add it back as a nullable FK to ``organizations`` with ON DELETE SET NULL.
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
        "103_import_job_organization_id.py",
    )
)

TABLE = "import_jobs"
COLUMN = "organization_id"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_103", MIGRATION_PATH)
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


class TestMigration103Shape:
    def test_revision_chains_after_102(self):
        mig = _load_migration()
        assert mig.revision == "103_import_job_organization_id"
        assert mig.down_revision == "102_korrektur_custom_graded_field"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert COLUMN in _columns(conn)

    def test_downgrade_then_upgrade_rebuilds_the_column(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        assert COLUMN not in _columns(conn)

        with _op_context(conn):
            mig.upgrade()
        column = _columns(conn)[COLUMN]
        assert column["nullable"] is True

        fks = [
            fk
            for fk in inspect(conn).get_foreign_keys(TABLE)
            if fk["constrained_columns"] == [COLUMN]
        ]
        assert len(fks) == 1
        assert fks[0]["referred_table"] == "organizations"
        assert fks[0]["referred_columns"] == ["id"]
        assert (fks[0].get("options") or {}).get("ondelete") == "SET NULL"
