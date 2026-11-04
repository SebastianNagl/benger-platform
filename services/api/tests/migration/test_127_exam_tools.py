"""Shape tests for migration 127: exam tools, tool providers, synced
bundles, student links and pins.

The shared test DB already carries the schema (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its guards, twice, and still create the expression indexes the models don't
declare. ``downgrade()`` removes everything; a re-run ``upgrade()`` rebuilds
it.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions", "127_exam_tools.py")
)

TABLES = (
    "tool_providers",
    "org_tool_provider_connections",
    "user_tool_provider_links",
    "tool_bundles",
    "tool_bundle_items",
    "tool_entitlements",
    "exam_tool_pins",
    "exam_tool_notes",
)
PROVIDER_COLUMNS = (
    "oauth_client_id",
    "encrypted_oauth_client_secret",
    "oauth_authorize_url",
    "oauth_token_url",
    "oauth_revoke_url",
    "oauth_scopes",
    "supports_student_links",
)
SYNC_COLUMNS = (
    "last_sync_started_at",
    "last_sync_finished_at",
    "last_sync_status",
    "last_sync_error",
    "last_success_at",
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


def _columns(conn, table):
    return {c["name"] for c in inspect(conn).get_columns(table)}


def _assert_full_schema(conn):
    insp = inspect(conn)
    for table in TABLES:
        assert insp.has_table(table), table
    assert "exam_tools" in _columns(conn, "projects")
    assert set(PROVIDER_COLUMNS) <= _columns(conn, "tool_providers")
    assert "api_version" not in _columns(conn, "tool_providers")
    assert set(SYNC_COLUMNS) <= _columns(conn, "org_tool_provider_connections")
    assert set(SYNC_COLUMNS) <= _columns(conn, "user_tool_provider_links")
    index_names = {i["name"] for i in insp.get_indexes("tool_bundle_items")}
    assert "ix_tool_bundle_items_search" in index_names
    assert "ix_tool_bundle_items_order" in index_names


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
        _assert_full_schema(conn)

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        insp = inspect(conn)
        for table in TABLES:
            assert not insp.has_table(table)
        assert "exam_tools" not in _columns(conn, "projects")
        with _op_context(conn):
            mig.upgrade()
        _assert_full_schema(conn)

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

    def test_entitlement_needs_exactly_one_owner(self, test_db: Session):
        conn = test_db.get_bind()
        bundle_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO tool_bundles (id, provider_slug, kind, code, content_hash) "
                "VALUES (:id, 'gii', 'law_texts', 'BGB', :hash)"
            ),
            {"id": bundle_id, "hash": uuid.uuid4().hex},
        )
        conn.execute(
            text(
                "INSERT INTO tool_entitlements (id, builtin_provider_slug, kind, code, bundle_id) "
                "VALUES (:id, 'gii', 'law_texts', 'BGB', :bundle)"
            ),
            {"id": str(uuid.uuid4()), "bundle": bundle_id},
        )
        savepoint = conn.begin_nested()
        try:
            conn.execute(
                text(
                    "INSERT INTO tool_entitlements (id, kind, code, bundle_id) "
                    "VALUES (:id, 'law_texts', 'StGB', :bundle)"
                ),
                {"id": str(uuid.uuid4()), "bundle": bundle_id},
            )
            raised = False
        except Exception:
            raised = True
        finally:
            savepoint.rollback()
        assert raised, "an entitlement without an owner must be refused"
