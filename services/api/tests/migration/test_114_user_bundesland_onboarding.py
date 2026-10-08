"""Shape tests for migration 114: users.exam_bundesland + users.onboarding_state.

The shared test DB already carries both columns (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guard, twice. ``downgrade()`` removes both; a re-run
``upgrade()`` rebuilds them.
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
        "114_user_bundesland_onboarding.py",
    )
)

TABLE = "users"
COLUMNS = {"exam_bundesland", "onboarding_state"}


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_114", MIGRATION_PATH)
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




def _columns(conn) -> set:
    return {c["name"] for c in inspect(conn).get_columns(TABLE)}


class TestMigration114Shape:
    def test_revision_chains_after_113(self):
        mig = _load_migration()
        assert mig.revision == "114_user_bundesland_onboarding"
        assert mig.down_revision == "113_submission_files"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert COLUMNS <= _columns(conn)

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        assert not (COLUMNS & _columns(conn))

        with _op_context(conn):
            mig.upgrade()
        assert COLUMNS <= _columns(conn)

    def test_columns_round_trip(self, test_db: Session):
        from models import User

        state = {"setup_skipped": True, "tours": {"student": 1}}
        user = User(
            id=str(uuid.uuid4()),
            username=f"mig114-{uuid.uuid4().hex[:8]}",
            email=f"mig114-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="x",
            name="Mig 114",
            exam_bundesland="HH",
            onboarding_state=state,
        )
        test_db.add(user)
        test_db.flush()
        test_db.refresh(user)
        assert user.exam_bundesland == "HH"
        assert user.onboarding_state == state
