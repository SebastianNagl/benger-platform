"""Shape tests for migration 127: exam tools and tool providers.

The shared test DB already carries the column and tables (created from the
models by ``Base.metadata.create_all``), so ``upgrade()`` must be a clean
no-op through its guards, twice. ``downgrade()`` removes everything; a
re-run ``upgrade()`` rebuilds it, incl. the full-text search index.
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
        "127_exam_tools.py",
    )
)

TABLES = (
    "tool_providers",
    "org_tool_provider_connections",
    "law_text_norms",
    "exam_tool_notes",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_127", MIGRATION_PATH)
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


def _exam_tools_column(conn):
    return next(
        (c for c in inspect(conn).get_columns("projects") if c["name"] == "exam_tools"),
        None,
    )


class TestMigration127Shape:
    def test_revision_chains_after_126(self):
        mig = _load_migration()
        assert mig.revision == "127_exam_tools"
        assert mig.down_revision == "126_pending_submission_uploads"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        column = _exam_tools_column(conn)
        assert column is not None and column["nullable"] is True
        insp = inspect(conn)
        for table in TABLES:
            assert insp.has_table(table)

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        insp = inspect(conn)
        assert _exam_tools_column(conn) is None
        for table in TABLES:
            assert not insp.has_table(table)

        with _op_context(conn):
            mig.upgrade()
        insp = inspect(conn)
        assert _exam_tools_column(conn) is not None
        for table in TABLES:
            assert insp.has_table(table)
        index_names = {i["name"] for i in insp.get_indexes("law_text_norms")}
        assert "ix_law_text_norms_search" in index_names
        assert "ix_law_text_norms_code_order" in index_names

    def test_external_provider_needs_base_url(self, test_db: Session):
        conn = test_db.get_bind()
        conn.execute(
            text(
                "INSERT INTO tool_providers (id, slug, name, is_builtin) "
                "VALUES (:id, :slug, 'Built-in', true)"
            ),
            {"id": str(uuid.uuid4()), "slug": f"builtin-{uuid.uuid4().hex[:6]}"},
        )
        savepoint = conn.begin_nested()
        try:
            conn.execute(
                text(
                    "INSERT INTO tool_providers (id, slug, name, is_builtin) "
                    "VALUES (:id, :slug, 'External', false)"
                ),
                {"id": str(uuid.uuid4()), "slug": f"ext-{uuid.uuid4().hex[:6]}"},
            )
            raised = False
        except Exception:
            raised = True
        finally:
            savepoint.rollback()
        assert raised, "an external provider without base_url must be refused"
