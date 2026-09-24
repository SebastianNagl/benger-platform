"""Shape tests for migration 108: drop the legacy ``project_members`` table.

The model is gone, so the shared test DB (built by ``Base.metadata.create_all``)
has no ``project_members`` table: ``upgrade()`` must be a no-op there, twice.
``downgrade()`` recreates the table exactly as ``001_complete_baseline`` did
(columns, FKs, unique constraint, three indexes), and a following
``upgrade()`` drops it again together with its indexes, even when it holds
rows. Every test runs inside the ``test_db`` transaction, which rolls back.
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
        "108_drop_project_members.py",
    )
)

TABLE = "project_members"
INDEXES = {
    "ix_project_members_id",
    "ix_project_members_project_id",
    "ix_project_members_user_id",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_108", MIGRATION_PATH)
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


def _exists(conn) -> bool:
    return TABLE in inspect(conn).get_table_names()


def _uid(prefix="x") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class TestMigration108:
    def test_revision_chains_after_107(self):
        mig = _load_migration()
        assert mig.revision == "108_drop_project_members"
        assert mig.down_revision == "107_invitation_email_state"

    def test_model_is_gone(self):
        import project_models
        from models import Base

        assert not hasattr(project_models, "ProjectMember")
        assert TABLE not in Base.metadata.tables

    def test_upgrade_is_a_noop_without_the_table(self, test_db: Session):
        conn = test_db.get_bind()
        assert not _exists(conn)
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert not _exists(conn)

    def test_downgrade_recreates_the_baseline_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            mig.downgrade()  # idempotent

        insp = inspect(conn)
        cols = {c["name"]: c for c in insp.get_columns(TABLE)}
        assert set(cols) == {
            "id",
            "project_id",
            "user_id",
            "role",
            "assigned_by",
            "is_active",
            "created_at",
            "updated_at",
        }
        for name in ("id", "project_id", "user_id", "role", "is_active", "created_at"):
            assert cols[name]["nullable"] is False, name
        for name in ("assigned_by", "updated_at"):
            assert cols[name]["nullable"] is True, name
        assert "now()" in str(cols["created_at"]["default"])

        fks = {
            fk["constrained_columns"][0]: (
                fk["referred_table"],
                (fk.get("options") or {}).get("ondelete"),
            )
            for fk in insp.get_foreign_keys(TABLE)
        }
        assert fks == {
            "assigned_by": ("users", "SET NULL"),
            "project_id": ("projects", "CASCADE"),
            "user_id": ("users", "CASCADE"),
        }
        uniques = {u["name"]: u["column_names"] for u in insp.get_unique_constraints(TABLE)}
        assert uniques == {"unique_project_member": ["project_id", "user_id"]}
        # PostgreSQL reports the unique constraint's backing index too.
        plain = {
            ix["name"]
            for ix in insp.get_indexes(TABLE)
            if not ix.get("duplicates_constraint")
        }
        assert plain == INDEXES

    def test_upgrade_drops_a_populated_table_and_its_indexes(self, test_db: Session):
        """The production path: the table exists and holds rows."""
        from models import User
        from project_models import Project

        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()

        user = User(
            id=_uid("usr"),
            username=_uid("un"),
            email=f"{_uid('m')}@example.com",
            name="Member",
        )
        test_db.add(user)
        test_db.flush()
        project = Project(id=_uid("prj"), title="P", created_by=user.id)
        test_db.add(project)
        test_db.flush()
        conn.exec_driver_sql(
            f"INSERT INTO {TABLE} (id, project_id, user_id, role, is_active) "
            f"VALUES ('{_uid('pm')}', '{project.id}', '{user.id}', 'CONTRIBUTOR', true)"
        )

        with _op_context(conn):
            mig.upgrade()
        assert not _exists(conn)
        leftover = conn.execute(
            text("SELECT count(*) FROM pg_class WHERE relname = ANY(:names)"),
            {"names": sorted(INDEXES)},
        ).scalar()
        assert leftover == 0
