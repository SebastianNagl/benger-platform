"""Migration 159: ``annotations.original_result``.

The shared test DB is built by ``Base.metadata.create_all``, so it already has
the column; on it ``upgrade()`` must be a no-op. The tests that need a
deployed database drop the column first, the way production has the table
before this release. Every test runs inside the ``test_db`` transaction,
which rolls back.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "159_annotation_original_result.py",
    )
)

COLUMN = "original_result"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_159", MIGRATION_PATH)
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
    return {c["name"]: c for c in inspect(conn).get_columns("annotations")}


def _drop_column(conn) -> None:
    conn.execute(text(f"ALTER TABLE annotations DROP COLUMN IF EXISTS {COLUMN}"))


class TestMigration159:
    def test_revision_chains_after_158(self):
        mig = _load_migration()
        assert mig.revision == "159_annotation_original_result"
        assert mig.down_revision == "158_peer_review_grant"

    def test_upgrade_is_a_noop_on_a_current_schema(self, test_db: Session):
        conn = test_db.get_bind()
        assert COLUMN in _columns(conn)
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert COLUMN in _columns(conn)

    def test_upgrade_adds_a_nullable_jsonb_column(self, test_db: Session):
        conn = test_db.get_bind()
        _drop_column(conn)
        assert COLUMN not in _columns(conn)

        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()  # idempotent

        column = _columns(conn)[COLUMN]
        assert column["nullable"] is True
        assert column["default"] is None
        assert isinstance(column["type"], JSONB)

    def test_downgrade_removes_the_column_and_upgrade_restores_it(
        self, test_db: Session
    ):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            mig.downgrade()  # idempotent
            assert COLUMN not in _columns(conn)
            mig.upgrade()
        assert COLUMN in _columns(conn)
