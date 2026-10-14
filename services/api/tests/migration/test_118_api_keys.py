"""Shape tests for migration 118: access keys.

The shared test DB already carries the tables and the column (created from
the models by ``Base.metadata.create_all``), so ``upgrade()`` must be a clean
no-op through its guards, twice. ``downgrade()`` removes everything and a
re-run ``upgrade()`` rebuilds the same shape, including the owner-shape
check and the composite group FK.
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
        "118_api_keys.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_118", MIGRATION_PATH)
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


def _shape(conn):
    insp = inspect(conn)
    user_cols = {c["name"]: c for c in insp.get_columns("users")}
    return {
        "service_col": user_cols.get("is_service_account"),
        "keys": insp.has_table("api_keys"),
        "usage": insp.has_table("api_key_usage_events"),
    }


def _seed_user(db: Session):
    from models import User

    user = User(
        id=str(uuid.uuid4()),
        username=f"mig118-{uuid.uuid4().hex[:8]}",
        email=f"mig118-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Mig 118",
    )
    db.add(user)
    db.flush()
    return user


class TestMigration118Shape:
    def test_revision_chains_after_117(self):
        mig = _load_migration()
        assert mig.revision == "118_api_keys"
        assert mig.down_revision == "117_task_work_presence"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        shape = _shape(conn)
        assert shape["service_col"] is not None
        assert shape["service_col"]["nullable"] is False
        assert shape["keys"] and shape["usage"]

    def test_downgrade_then_upgrade_rebuilds_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        shape = _shape(conn)
        assert shape["service_col"] is None
        assert not shape["keys"] and not shape["usage"]

        with _op_context(conn):
            mig.upgrade()
        shape = _shape(conn)
        assert shape["service_col"] is not None
        assert shape["keys"] and shape["usage"]

        insp = inspect(conn)
        fks = {fk["name"] for fk in insp.get_foreign_keys("api_keys")}
        assert "fk_api_keys_group_scope" in fks
        checks = {c["name"] for c in insp.get_check_constraints("api_keys")}
        assert {"ck_api_keys_owner_shape", "ck_api_keys_owner_type"} <= checks
        usage_idx = {i["name"] for i in insp.get_indexes("api_key_usage_events")}
        assert "ix_api_key_usage_events_created_brin" in usage_idx

    def test_owner_shape_check_rejects_personal_key_with_org(self, test_db: Session):
        user = _seed_user(test_db)
        conn = test_db.connection()
        org_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO organizations (id, name, display_name, slug, is_active, created_at)"
                " VALUES (:id, 'o', 'o', :slug, true, now())"
            ),
            {"id": org_id, "slug": f"mig118-{org_id[:8]}"},
        )
        conn.execute(text("SAVEPOINT mig118_check"))
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO api_keys (id, name, key_prefix, key_hash, owner_type,"
                    " user_id, organization_id, created_by)"
                    " VALUES (:id, 'k', :p, :h, 'user', :u, :o, :u)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "p": f"bgr_test_{uuid.uuid4().hex[:8]}",
                    "h": "0" * 64,
                    "u": user.id,
                    "o": org_id,
                },
            )
        conn.execute(text("ROLLBACK TO SAVEPOINT mig118_check"))

    def test_service_account_defaults_to_false(self, test_db: Session):
        user = _seed_user(test_db)
        test_db.refresh(user)
        assert user.is_service_account is False
