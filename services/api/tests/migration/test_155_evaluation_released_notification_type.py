"""Migration 155: the evaluation_released notification type.

``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block, so the
migration issues its own ``COMMIT`` first. The upgrade test runs it for real
on an autocommit connection of the test engine (not the rolled-back test
session), twice, and reads the labels back from ``pg_enum``.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import text

from models import NotificationType

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "155_add_evaluation_released_notification_type.py",
    )
)

NEW_VALUES = {NotificationType.EVALUATION_RELEASED.value}


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_155", MIGRATION_PATH)
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


class TestMigration155:
    def test_revision_chains_after_154(self):
        mig = _load_migration()
        assert mig.revision == "155_add_evaluation_released_notification_type"
        assert mig.down_revision == "154_korrektur_comment_highlight_field"

    def test_upgrade_adds_the_values_and_is_idempotent(self, test_db):
        # test_db only makes sure the schema (and the enum) exists; the
        # migration needs a connection outside its transaction.
        from tests.fixtures.database import _get_engine

        engine, _ = _get_engine()
        mig = _load_migration()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            with _op_context(conn):
                mig.upgrade()
                mig.upgrade()
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
        assert NEW_VALUES <= labels

    def test_downgrade_is_a_no_op(self):
        mig = _load_migration()
        with patch.object(mig, "op") as op:
            mig.downgrade()
        op.execute.assert_not_called()
