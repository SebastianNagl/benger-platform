"""Shape tests for migration 076: the five LTI 1.3 tables.

The shared test DB already carries the ``lti_*`` tables (created from the
models by ``Base.metadata.create_all``), so ``upgrade()`` must be a clean
no-op through its inspector guards — twice. After ``downgrade()`` a re-run
``upgrade()`` must rebuild the full shape: tables, the named unique
constraints, and the named indices. Everything runs on the fixture's outer
transaction (Postgres DDL is transactional), so the shared test DB is
untouched after rollback.

Binds the alembic ``op`` proxy via ``Operations.context`` — the same
mechanism ``MigrationContext.run_migrations`` uses — because 076 issues real
DDL (``op.create_table``), unlike the data-only migrations tested elsewhere
in this directory that only need ``op.get_bind()`` patched.
"""

from __future__ import annotations

import importlib.util
import os
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
        "079_add_lti_tables.py",
    )
)

LTI_TABLES = [
    "lti_platform_registrations",
    "lti_deployments",
    "lti_resource_links",
    "lti_user_links",
    "lti_grade_syncs",
]

EXPECTED_UNIQUES = {
    "lti_platform_registrations": "uq_lti_registration_issuer_client",
    "lti_deployments": "uq_lti_deployment",
    "lti_resource_links": "uq_lti_resource_link",
    "lti_user_links": "uq_lti_user_link",
    "lti_grade_syncs": "uq_lti_grade_sync",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_076", MIGRATION_PATH)
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


class TestMigration079Shape:
    def test_revision_chains_after_075(self):
        mig = _load_migration()
        assert mig.revision == "079_add_lti_tables"
        assert mig.down_revision == "078_evaluation_lifecycle_columns"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            # Second run — the table/index guards must make this a no-op.
            mig.upgrade()
        tables = set(inspect(conn).get_table_names())
        assert set(LTI_TABLES) <= tables

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()

        with _op_context(conn):
            mig.downgrade()
        remaining = set(inspect(conn).get_table_names())
        assert not set(LTI_TABLES) & remaining

        with _op_context(conn):
            mig.upgrade()
        insp = inspect(conn)
        assert set(LTI_TABLES) <= set(insp.get_table_names())

        for table, uq_name in EXPECTED_UNIQUES.items():
            uq_names = {c["name"] for c in insp.get_unique_constraints(table)}
            assert uq_name in uq_names, f"{table} missing {uq_name}"

        grade_sync_indexes = {ix["name"] for ix in insp.get_indexes("lti_grade_syncs")}
        assert "ix_lti_grade_syncs_due" in grade_sync_indexes
        resource_link_indexes = {
            ix["name"] for ix in insp.get_indexes("lti_resource_links")
        }
        assert "ix_lti_resource_links_project" in resource_link_indexes

        # Spot-check the outbox columns the extended sync worker relies on.
        grade_sync_columns = {c["name"] for c in insp.get_columns("lti_grade_syncs")}
        assert {
            "status",
            "attempts",
            "next_retry_at",
            "last_synced_score",
            "last_synced_hash",
            "source_task_evaluation_id",
            "last_error",
        } <= grade_sync_columns
