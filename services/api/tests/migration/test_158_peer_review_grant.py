"""Migration 158: the peer review switch, the peer run index, the notice type.

``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block, so the
migration issues its own ``COMMIT`` before it. The upgrade test runs the
migration for real on an autocommit connection of the test engine (not the
rolled-back test session), twice, and reads the column, the index and the
enum label back from the catalog. The downgrade test runs inside a
transaction that it rolls back, so the shared test database keeps its schema.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager

from sqlalchemy import text

from models import NotificationType

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "158_peer_review_grant.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_158", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    """Install the alembic ``op`` proxy bound to the given connection."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


class TestMigration158:
    def test_revision_chains_after_157(self):
        mig = _load_migration()
        assert mig.revision == "158_peer_review_grant"
        assert mig.down_revision == "157_upload_batches_and_grading_files"

    def test_upgrade_adds_everything_and_is_idempotent(self, test_db):
        from tests.fixtures.database import _get_engine

        engine, _ = _get_engine()
        mig = _load_migration()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            with _op_context(conn):
                mig.upgrade()
                mig.upgrade()
            column = conn.execute(
                text(
                    "SELECT is_nullable, column_default FROM information_schema.columns "
                    "WHERE table_name = 'projects' AND column_name = 'peer_review_enabled'"
                )
            ).one()
            index = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'uq_human_eval_run_per_project_metric_peer'"
                )
            ).scalar_one()
            labels = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'notificationtype'"
                    )
                )
            }
        assert column[0] == "NO"
        assert "false" in str(column[1])
        assert "UNIQUE" in index and "korrektur_peer" in index
        assert NotificationType.PEER_FEEDBACK_RECEIVED.value in labels

    def test_downgrade_drops_the_index_and_the_column_but_keeps_the_enum(self, test_db):
        from tests.fixtures.database import _get_engine

        engine, _ = _get_engine()
        mig = _load_migration()
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                with _op_context(conn):
                    mig.downgrade()
                during = _catalog_state(conn)
            finally:
                trans.rollback()
            after = _catalog_state(conn)
        assert during == (False, False, True)
        assert after == (True, True, True)


def _catalog_state(conn) -> tuple[bool, bool, bool]:
    column = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'projects' AND column_name = 'peer_review_enabled'"
        )
    ).first()
    index = conn.execute(
        text(
            "SELECT 1 FROM pg_indexes "
            "WHERE indexname = 'uq_human_eval_run_per_project_metric_peer'"
        )
    ).first()
    label = conn.execute(
        text(
            "SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'notificationtype' AND e.enumlabel = 'peer_feedback_received'"
        )
    ).first()
    return column is not None, index is not None, label is not None
