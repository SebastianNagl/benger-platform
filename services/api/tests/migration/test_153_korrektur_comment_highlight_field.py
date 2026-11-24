"""Shape tests for migration 153: korrektur_comments.highlight_field.

The shared test DB already carries the column (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guard, twice. ``downgrade()`` removes it; a re-run
``upgrade()`` adds it back nullable, so comments written before it read NULL.
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
        "153_korrektur_comment_highlight_field.py",
    )
)

TABLE = "korrektur_comments"
COLUMN = "highlight_field"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_153", MIGRATION_PATH)
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


def _column(conn):
    return next(
        (c for c in inspect(conn).get_columns(TABLE) if c["name"] == COLUMN), None
    )


class TestMigration153Shape:
    def test_revision_chains_after_152(self):
        mig = _load_migration()
        assert mig.revision == "153_korrektur_comment_highlight_field"
        assert mig.down_revision == "152_platform_flags_tum_rollout"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        column = _column(conn)
        assert column is not None and column["nullable"] is True

    def test_downgrade_then_upgrade_restores_a_nullable_column(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        assert _column(conn) is None
        with _op_context(conn):
            mig.upgrade()
        column = _column(conn)
        assert column is not None and column["nullable"] is True
