"""Migration 153: server default FALSE on the unused ``projects.is_published``.

The model no longer maps the column, so the shared test DB (built by
``Base.metadata.create_all``) lacks it. The tests that need it add it the
way production has it (NOT NULL, no server default, as created by the
baseline migration), so they check what the release does to a deployed
database: ``upgrade()`` sets the default FALSE (twice, idempotent), a row
inserted through the model (which no longer names the column) reads
FALSE, and ``downgrade()`` removes
the default again. Without the column both directions are no-ops. The report
publication flag (``project_reports.is_published``) is untouched. Every test
runs inside the ``test_db`` transaction, which rolls back.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "153_project_is_published_server_default.py",
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


def _drop_column(conn) -> None:
    """A test DB bootstrapped before this release still has the column (the
    fixture keeps long-lived DBs); start every test from the model's schema."""
    conn.execute(text("ALTER TABLE projects DROP COLUMN IF EXISTS is_published"))


def _add_deployed_column(conn) -> None:
    _drop_column(conn)
    conn.execute(text("ALTER TABLE projects ADD COLUMN is_published BOOLEAN NOT NULL"))


def _owner(test_db: Session) -> str:
    from models import User

    user = User(
        id=_uid("usr"),
        username=_uid("un"),
        email=f"{_uid('m')}@example.com",
        name="Owner",
    )
    test_db.add(user)
    test_db.flush()
    return user.id


def _insert_from_model(test_db: Session, owner_id: str) -> str:
    """Insert a project through the model, which no longer names the column."""
    from project_models import Project

    project = Project(id=_uid("prj"), title="P", created_by=owner_id)
    test_db.add(project)
    test_db.flush()
    return project.id


class TestMigration153:
    def test_revision_chains_after_152(self):
        mig = _load_migration()
        assert mig.revision == "153_project_is_published_server_default"
        assert mig.down_revision == "152_platform_flags_tum_rollout"

    def test_model_and_api_no_longer_carry_the_flag(self):
        from project_models import Project

        from project_schemas import ProjectResponse, ProjectUpdate

        assert "is_published" not in Project.__table__.columns
        assert "is_published" not in ProjectResponse.model_fields
        assert "is_published" not in ProjectUpdate.model_fields

    def test_report_publication_flag_stays(self, test_db: Session):
        conn = test_db.get_bind()
        before = _columns(conn, "project_reports")["is_published"]
        _add_deployed_column(conn)
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.downgrade()
        after = _columns(conn, "project_reports")["is_published"]
        assert after["nullable"] == before["nullable"]
        assert str(after["default"]) == str(before["default"])

    def test_both_directions_are_noops_without_the_column(self, test_db: Session):
        conn = test_db.get_bind()
        _drop_column(conn)
        assert "is_published" not in _columns(conn, "projects")
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
            mig.downgrade()
        assert "is_published" not in _columns(conn, "projects")

    def test_upgrade_sets_default_false_and_keeps_the_column(self, test_db: Session):
        conn = test_db.get_bind()
        owner_id = _owner(test_db)
        _add_deployed_column(conn)
        assert _columns(conn, "projects")["is_published"]["default"] is None

        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()  # idempotent

        column = _columns(conn, "projects")["is_published"]
        assert column["nullable"] is False
        assert "false" in str(column["default"]).lower()
        project_id = _insert_from_model(test_db, owner_id)
        stored = conn.execute(
            text("SELECT is_published FROM projects WHERE id = :id"),
            {"id": project_id},
        ).scalar()
        assert stored is False

    def test_downgrade_removes_the_default(self, test_db: Session):
        conn = test_db.get_bind()
        owner_id = _owner(test_db)
        _add_deployed_column(conn)
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.downgrade()

        column = _columns(conn, "projects")["is_published"]
        assert column["nullable"] is False
        assert column["default"] is None
        with pytest.raises(IntegrityError), test_db.begin_nested():
            _insert_from_model(test_db, owner_id)
