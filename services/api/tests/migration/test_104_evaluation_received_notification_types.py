"""Shape tests for migration 104: the evaluation_received_* notification types.

``ALTER TYPE ... ADD VALUE`` needs its own ``COMMIT``, which would end the test
session's transaction, so ``upgrade()`` runs against a stubbed ``op`` here. The
shared test DB is built from the models, so its enum must already carry the
three values; the startup drift check confirms that.
"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch

from sqlalchemy.orm import Session

from models import NotificationType

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "104_add_evaluation_received_notification_types.py",
    )
)

NEW_VALUES = {
    NotificationType.EVALUATION_RECEIVED_HUMAN.value,
    NotificationType.EVALUATION_RECEIVED_IMMEDIATE.value,
    NotificationType.EVALUATION_RECEIVED_BATCH.value,
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_104", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class TestMigration104Shape:
    def test_revision_chains_after_103(self):
        mig = _load_migration()
        assert mig.revision == "104_add_evaluation_received_notification_types"
        assert mig.down_revision == "103_import_job_organization_id"

    def test_values_match_the_python_enum(self):
        assert set(_load_migration().NEW_VALUES) == NEW_VALUES

    def test_upgrade_commits_then_adds_each_value(self):
        mig = _load_migration()
        with patch.object(mig, "op") as op:
            mig.upgrade()
        statements = [c.args[0] for c in op.execute.call_args_list]
        assert statements[0] == "COMMIT"
        assert sorted(statements[1:]) == sorted(
            f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{value}'"
            for value in NEW_VALUES
        )

    def test_downgrade_is_a_no_op(self):
        mig = _load_migration()
        with patch.object(mig, "op") as op:
            mig.downgrade()
        op.execute.assert_not_called()

    def test_test_db_enum_has_no_drift(self, test_db: Session):
        from mailer.notification_service import check_notification_type_enum_drift

        assert check_notification_type_enum_drift(test_db) == []
