"""Shape tests for migration 115: organization_groups.require_private_keys.

The shared test DB already carries the column (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guard, twice. ``downgrade()`` removes it; a re-run
``upgrade()`` rebuilds it, nullable, so existing groups follow their org.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
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
        "115_group_require_private_keys.py",
    )
)

TABLE = "organization_groups"
COLUMN = "require_private_keys"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_115", MIGRATION_PATH)
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


class TestMigration115Shape:
    def test_revision_chains_after_114(self):
        mig = _load_migration()
        assert mig.revision == "115_group_require_private_keys"
        assert mig.down_revision == "114_user_bundesland_onboarding"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        column = _column(conn)
        assert column is not None and column["nullable"] is True

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        assert _column(conn) is None

        with _op_context(conn):
            mig.upgrade()
        assert _column(conn) is not None

    def test_new_groups_follow_their_org(self, test_db: Session):
        from models import Organization, OrganizationGroup

        org = Organization(
            id=str(uuid.uuid4()),
            name=f"mig115-{uuid.uuid4().hex[:8]}",
            display_name="Mig 115",
            slug=f"mig115-{uuid.uuid4().hex[:8]}",
        )
        test_db.add(org)
        test_db.flush()
        group = OrganizationGroup(
            id=str(uuid.uuid4()), organization_id=org.id, name="LS", is_active=True
        )
        test_db.add(group)
        test_db.flush()
        test_db.refresh(group)
        assert group.require_private_keys is None
