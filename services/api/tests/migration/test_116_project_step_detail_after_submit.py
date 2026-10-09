"""Shape tests for migration 116: projects.annotator_step_detail_after_submit.

The shared test DB already carries the column (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guard, twice. ``downgrade()`` removes it; a re-run
``upgrade()`` rebuilds it, nullable, so existing projects keep following the
reference switch.
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
        "116_project_step_detail_after_submit.py",
    )
)

TABLE = "projects"
COLUMN = "annotator_step_detail_after_submit"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_116", MIGRATION_PATH)
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


class TestMigration116Shape:
    def test_revision_chains_after_115(self):
        mig = _load_migration()
        assert mig.revision == "116_project_step_detail_after_submit"
        assert mig.down_revision == "115_group_require_private_keys"

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

    def test_new_projects_follow_the_reference_switch(self, test_db: Session):
        from models import User
        from project_models import Project
        from solution_reveal import step_detail_revealed

        owner = User(
            id=str(uuid.uuid4()),
            username=f"mig116-{uuid.uuid4().hex[:8]}",
            email=f"mig116-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="x",
            name="Mig 116",
        )
        test_db.add(owner)
        test_db.flush()
        project = Project(id=str(uuid.uuid4()), title="mig116", created_by=owner.id)
        test_db.add(project)
        test_db.flush()
        test_db.refresh(project)
        assert project.annotator_step_detail_after_submit is None
        assert step_detail_revealed(project) is False
        project.annotator_full_visibility_after_submit = True
        assert step_detail_revealed(project) is True
