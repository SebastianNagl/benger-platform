"""Shape tests for migration 109: Safe Exam Browser columns on ``projects``.

The shared test DB is built by ``Base.metadata.create_all``, so both columns
already exist: ``upgrade()`` must be a no-op there. ``downgrade()`` removes
them (idempotently) and a following ``upgrade()`` restores them with the
right types and defaults, keeping existing rows valid. Every test runs inside
the ``test_db`` transaction, which rolls back.
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
        "109_project_seb_settings.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_109", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _columns(conn) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns("projects")}


class TestMigration109:
    def test_revision_chains_after_108(self):
        mig = _load_migration()
        assert mig.revision == "109_project_seb_settings"
        assert mig.down_revision == "108_drop_project_members"

    def test_model_declares_both_columns(self):
        from project_models import Project

        cols = Project.__table__.columns
        assert cols["seb_required"].nullable is False
        assert cols["seb_config"].nullable is True

    def test_upgrade_is_a_noop_when_columns_exist(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
        cols = _columns(conn)
        assert "seb_required" in cols and "seb_config" in cols

    def test_downgrade_then_upgrade_restores_the_shape(self, test_db: Session):
        from models import User
        from project_models import Project

        conn = test_db.get_bind()
        user = User(
            id=str(uuid.uuid4()),
            username=f"u-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            name="U",
        )
        test_db.add(user)
        test_db.flush()
        project = Project(id=str(uuid.uuid4()), title="P", created_by=user.id)
        test_db.add(project)
        test_db.flush()

        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            mig.downgrade()  # idempotent
            assert not {"seb_required", "seb_config"} & set(_columns(conn))
            mig.upgrade()

        cols = _columns(conn)
        assert cols["seb_required"]["nullable"] is False
        assert "false" in str(cols["seb_required"]["default"]).lower()
        assert cols["seb_config"]["nullable"] is True
        assert "JSONB" in str(cols["seb_config"]["type"]).upper()
        row = conn.execute(
            text("SELECT seb_required, seb_config FROM projects WHERE id = :id"),
            {"id": project.id},
        ).one()
        assert row == (False, None)
