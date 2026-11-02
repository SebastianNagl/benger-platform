"""Shape tests for migration 123: projects.allow_external_paste.

The shared test DB already carries the column (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guard, twice. ``downgrade()`` removes it; a re-run
``upgrade()`` rebuilds it NOT NULL with a TRUE server default, so existing
projects keep allowing pastes.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
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
        "123_project_allow_external_paste.py",
    )
)

TABLE = "projects"
COLUMN = "allow_external_paste"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_123", MIGRATION_PATH)
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


def _owner(test_db: Session):
    from models import User

    owner = User(
        id=str(uuid.uuid4()),
        username=f"mig123-{uuid.uuid4().hex[:8]}",
        email=f"mig123-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Mig 123",
    )
    test_db.add(owner)
    test_db.flush()
    return owner


class TestMigration123Shape:
    def test_revision_chains_after_122(self):
        mig = _load_migration()
        assert mig.revision == "123_project_allow_external_paste"
        assert mig.down_revision == "122_korrektur_feedback_human_run_singleton"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        column = _column(conn)
        assert column is not None and column["nullable"] is False

    def test_downgrade_then_upgrade_backfills_true(self, test_db: Session):
        from project_models import Project

        owner = _owner(test_db)
        project_id = str(uuid.uuid4())
        test_db.add(Project(id=project_id, title="mig123", created_by=owner.id))
        test_db.flush()

        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        assert _column(conn) is None

        with _op_context(conn):
            mig.upgrade()
        column = _column(conn)
        assert column is not None and column["nullable"] is False
        value = conn.execute(
            text("SELECT allow_external_paste FROM projects WHERE id = :id"),
            {"id": project_id},
        ).scalar_one()
        assert value is True

    def test_new_projects_allow_pasting(self, test_db: Session):
        from project_models import Project

        owner = _owner(test_db)
        project = Project(id=str(uuid.uuid4()), title="mig123", created_by=owner.id)
        test_db.add(project)
        test_db.flush()
        test_db.refresh(project)
        assert project.allow_external_paste is True
