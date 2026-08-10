"""Shape tests for migration 091: users.exam_layout_prefs.

The shared test DB already carries the column (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guard — twice. ``downgrade()`` must remove the column; a re-run
``upgrade()`` must rebuild it. The column stores the complete exam-interface
layout object as JSON (see ExamLayoutPrefs in auth_schemas.py).
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
        "091_add_user_exam_layout_prefs.py",
    )
)

TABLE = "users"
COLUMN = "exam_layout_prefs"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_091", MIGRATION_PATH)
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


class TestMigration091Shape:
    def test_revision_chains_after_090(self):
        # Authored against the committed head 090. If the parallel task-rubrics
        # stream lands 088 (also chained on 090) first, re-point this
        # down_revision at 088 — test_single_alembic_head fails the collision.
        mig = _load_migration()
        assert mig.revision == "091_add_user_exam_layout_prefs"
        assert mig.down_revision == "090_exam_unlimited_annotations"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            # Second run — the column guard must make this a no-op.
            mig.upgrade()
        assert COLUMN in _columns(conn)

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        assert COLUMN not in _columns(conn)

        with _op_context(conn):
            mig.upgrade()
        assert COLUMN in _columns(conn)

    def test_column_round_trips_the_canonical_object(self, test_db: Session):
        from models import User

        prefs = {
            "mode": "modern",
            "case_position": "left",
            "notes_position": "right",
            "outline_position": "none",
        }
        user = User(
            id=str(uuid.uuid4()),
            username=f"mig091-{uuid.uuid4().hex[:8]}",
            email=f"mig091-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="x",
            name="Mig 091",
            exam_layout_prefs=prefs,
        )
        test_db.add(user)
        test_db.flush()
        test_db.refresh(user)
        assert user.exam_layout_prefs == prefs
