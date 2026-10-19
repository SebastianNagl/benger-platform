"""Shape tests for migration 119: korrektur_reservations.

The shared test DB already carries the table (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its guard, twice. ``downgrade()`` removes the table and a re-run
``upgrade()`` rebuilds the same shape, including the per-user uniqueness.
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
        "119_korrektur_reservations.py",
    )
)

TABLE = "korrektur_reservations"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_119", MIGRATION_PATH)
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


class TestMigration119Shape:
    def test_revision_chains_after_118(self):
        mig = _load_migration()
        assert mig.revision == "119_korrektur_reservations"
        assert mig.down_revision == "118_api_keys"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert inspect(conn).has_table(TABLE)

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        assert not inspect(conn).has_table(TABLE)

        with _op_context(conn):
            mig.upgrade()
        insp = inspect(conn)
        cols = {c["name"] for c in insp.get_columns(TABLE)}
        assert {
            "id", "project_id", "task_id", "user_id", "metric",
            "target_type", "target_id", "created_at", "last_seen_at",
        } <= cols
        uniques = {u["name"] for u in insp.get_unique_constraints(TABLE)}
        assert "uq_korrektur_reservation_user_target" in uniques
        indexes = {i["name"] for i in insp.get_indexes(TABLE)}
        assert {
            "ix_korrektur_reservations_project_metric",
            "ix_korrektur_reservations_task_id",
        } <= indexes

    def test_model_matches_migration_names(self):
        from project_models import KorrekturReservation

        table = KorrekturReservation.__table__
        assert table.name == TABLE
        assert "uq_korrektur_reservation_user_target" in {
            c.name for c in table.constraints
        }
