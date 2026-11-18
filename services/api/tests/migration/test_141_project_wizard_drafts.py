"""Shape tests for migration 141: creation-wizard drafts.

The shared test DB already carries the column, the index and the table (built
from the models), so ``upgrade()`` must be a no-op through its guards, twice.
``downgrade()`` removes all of it and a re-run ``upgrade()`` rebuilds it with
the columns of the model. Existing projects keep ``is_wizard_draft = false``.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)
NAME = "141_project_wizard_drafts"


def _load():
    spec = importlib.util.spec_from_file_location(f"mig_{NAME}", os.path.join(VERSIONS, f"{NAME}.py"))
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


def _columns(conn, table):
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _indexes(conn, table):
    return {i["name"]: i for i in inspect(conn).get_indexes(table)}


def _assert_shape(conn):
    from project_models import ProjectWizardDraft

    flag = _columns(conn, "projects")["is_wizard_draft"]
    assert flag["nullable"] is False
    assert "false" in str(flag["default"]).lower()
    index = _indexes(conn, "projects")["ix_projects_wizard_draft"]
    assert index["column_names"] == ["created_by"]
    assert "is_wizard_draft" in str(index.get("dialect_options", {}).get("postgresql_where"))
    assert set(_columns(conn, "project_wizard_drafts")) == {
        c.name for c in ProjectWizardDraft.__table__.columns
    }
    assert "ix_project_wizard_drafts_touched_at" in _indexes(conn, "project_wizard_drafts")
    uniques = {
        u["name"]: u["column_names"]
        for u in inspect(conn).get_unique_constraints("project_wizard_drafts")
    }
    assert uniques["uq_project_wizard_drafts_client_key"] == ["created_by", "client_key"]
    deletes = {
        fk["referred_table"]: fk["options"].get("ondelete")
        for fk in inspect(conn).get_foreign_keys("project_wizard_drafts")
    }
    assert deletes == {
        "projects": "CASCADE",
        "users": "CASCADE",
        "organizations": "SET NULL",
        "organization_groups": "SET NULL",
    }


class TestMigration141:
    def test_revision_chains_after_140(self):
        mig = _load()
        assert mig.revision == NAME
        assert mig.down_revision == "140_generation_cascades_and_purge_jobs"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        _assert_shape(conn)

    def test_new_projects_are_not_drafts(self, test_db: Session):
        from models import User
        from project_models import Project

        suffix = uuid.uuid4().hex[:8]
        owner = User(
            id=str(uuid.uuid4()), username=f"mig141-{suffix}",
            email=f"mig141-{suffix}@example.com", hashed_password="x", name="Mig 141",
        )
        test_db.add(owner)
        test_db.flush()
        project = Project(id=str(uuid.uuid4()), title="p", created_by=owner.id)
        test_db.add(project)
        test_db.flush()
        value = test_db.get_bind().execute(
            text("SELECT is_wizard_draft FROM projects WHERE id = :id"), {"id": project.id}
        ).scalar_one()
        assert value is False

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert "project_wizard_drafts" not in inspect(conn).get_table_names()
        assert "is_wizard_draft" not in _columns(conn, "projects")
        assert "ix_projects_wizard_draft" not in _indexes(conn, "projects")
        with _op_context(conn):
            mig.upgrade()
        _assert_shape(conn)
