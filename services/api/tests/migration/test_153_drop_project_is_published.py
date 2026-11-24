"""Migration 153: drop the unused ``projects.is_published`` column.

The model no longer has the column, so the shared test DB (built by
``Base.metadata.create_all``) lacks it and ``upgrade()`` is a no-op there,
twice. ``downgrade()`` adds it back as NOT NULL with the default FALSE, so
existing rows read FALSE, and a following ``upgrade()`` drops it again from
a table that holds rows. The report
publication flag (``project_reports.is_published``) is untouched. Every test
runs inside the ``test_db`` transaction, which rolls back.
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
        "153_drop_project_is_published.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_153", MIGRATION_PATH)
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


def _columns(conn, table: str) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _uid(prefix="x") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class TestMigration153:
    def test_revision_chains_after_152(self):
        mig = _load_migration()
        assert mig.revision == "153_drop_project_is_published"
        assert mig.down_revision == "152_platform_flags_tum_rollout"

    def test_model_and_api_no_longer_carry_the_flag(self):
        from project_models import Project
        from project_schemas import ProjectResponse, ProjectUpdate

        assert "is_published" not in Project.__table__.columns
        assert "is_published" not in ProjectResponse.model_fields
        assert "is_published" not in ProjectUpdate.model_fields

    def test_report_publication_flag_stays(self, test_db: Session):
        assert "is_published" in _columns(test_db.get_bind(), "project_reports")

    def test_upgrade_is_a_noop_without_the_column(self, test_db: Session):
        conn = test_db.get_bind()
        assert "is_published" not in _columns(conn, "projects")
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert "is_published" not in _columns(conn, "projects")

    def test_downgrade_restores_a_not_null_false_default(self, test_db: Session):
        from models import User
        from project_models import Project

        conn = test_db.get_bind()
        user = User(
            id=_uid("usr"),
            username=_uid("un"),
            email=f"{_uid('m')}@example.com",
            name="Owner",
        )
        test_db.add(user)
        test_db.flush()
        project = Project(id=_uid("prj"), title="P", created_by=user.id)
        test_db.add(project)
        test_db.flush()

        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            mig.downgrade()  # idempotent

        column = _columns(conn, "projects")["is_published"]
        assert column["nullable"] is False
        assert "false" in str(column["default"]).lower()
        stored = conn.execute(
            text("SELECT is_published FROM projects WHERE id = :id"), {"id": project.id}
        ).scalar()
        assert stored is False

        with _op_context(conn):
            mig.upgrade()
        assert "is_published" not in _columns(conn, "projects")
        assert conn.execute(
            text("SELECT count(*) FROM projects WHERE id = :id"), {"id": project.id}
        ).scalar() == 1
