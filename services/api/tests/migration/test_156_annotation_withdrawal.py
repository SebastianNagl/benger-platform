"""Migration 156: the withdrawal record on ``annotations`` and ``submission_returned``.

The shared test DB is built by ``Base.metadata.create_all``, so it already has
the three columns, their users FK and (through the fixture's label loop) the
enum value. On it ``upgrade()`` must be a no-op that stays inside the caller's
transaction: the ``COMMIT`` before ``ALTER TYPE ... ADD VALUE`` only runs when
the value is missing, which lets the test DB fixture replay the migration.
The tests that need a deployed database drop the columns first, the way
production has the table before this release. Every test runs inside the
``test_db`` transaction, which rolls back.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "156_annotation_withdrawal.py",
    )
)

COLUMNS = ("withdrawn_at", "withdrawn_by", "withdrawal_reason")


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_156", MIGRATION_PATH)
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


def _withdrawn_by_fks(conn) -> list:
    return [
        fk
        for fk in inspect(conn).get_foreign_keys("annotations")
        if fk["constrained_columns"] == ["withdrawn_by"]
    ]


def _transaction_id(conn):
    return conn.execute(text("SELECT txid_current_if_assigned()")).scalar()


def _drop_withdrawal_columns(conn) -> None:
    for column in COLUMNS:
        conn.execute(text(f"ALTER TABLE annotations DROP COLUMN IF EXISTS {column}"))


class TestMigration156:
    def test_revision_chains_after_155(self):
        mig = _load_migration()
        assert mig.revision == "156_annotation_withdrawal"
        assert mig.down_revision == "155_add_evaluation_released_notification_type"

    def test_upgrade_is_a_noop_on_a_current_schema_and_never_commits(
        self, test_db: Session
    ):
        conn = test_db.get_bind()
        # Take a transaction id, so a COMMIT inside upgrade() would show as a
        # different (or no) id afterwards.
        conn.execute(text("SELECT txid_current()"))
        before = _transaction_id(conn)
        assert before is not None
        assert set(COLUMNS) <= set(_columns(conn))

        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()

        assert _transaction_id(conn) == before
        assert len(_withdrawn_by_fks(conn)) == 1

    def test_upgrade_adds_the_record_to_a_deployed_table(self, test_db: Session):
        conn = test_db.get_bind()
        _drop_withdrawal_columns(conn)
        assert not set(COLUMNS) & set(_columns(conn))

        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()  # idempotent

        columns = _columns(conn)
        for name in COLUMNS:
            assert columns[name]["nullable"] is True
            assert columns[name]["default"] is None
        fks = _withdrawn_by_fks(conn)
        assert len(fks) == 1
        assert fks[0]["referred_table"] == "users"
        assert fks[0]["referred_columns"] == ["id"]
        assert fks[0]["options"].get("ondelete") == "SET NULL"

    def test_downgrade_removes_the_record_and_upgrade_restores_it(
        self, test_db: Session
    ):
        conn = test_db.get_bind()
        _drop_withdrawal_columns(conn)
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.downgrade()
            mig.downgrade()  # idempotent
            assert not set(COLUMNS) & set(_columns(conn))
            mig.upgrade()
        assert set(COLUMNS) <= set(_columns(conn))
        assert len(_withdrawn_by_fks(conn)) == 1

    def test_notification_type_is_registered(self, test_db: Session):
        labels = test_db.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'notificationtype'"
            )
        ).scalars()
        assert "submission_returned" in set(labels)
