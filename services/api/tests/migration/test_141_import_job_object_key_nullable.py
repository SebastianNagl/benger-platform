"""Migration 141: ``import_jobs.object_key`` may be NULL.

The daily file cleanup clears the key of an import job whose upload it
deleted. ``upgrade()`` drops NOT NULL (and is idempotent, because the test DB
built from the models has it nullable already); ``downgrade()`` fills the
cleared keys with ``''`` and restores NOT NULL. Rolled back with the test
transaction.
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
NAME = "141_import_job_object_key_nullable"


def _load():
    spec = importlib.util.spec_from_file_location(f"mig_{NAME}", os.path.join(VERSIONS, f"{NAME}.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with Operations.context(MigrationContext.configure(connection)):
        yield


def _nullable(conn) -> bool:
    column = next(c for c in inspect(conn).get_columns("import_jobs") if c["name"] == "object_key")
    return column["nullable"]


def _swept_import_job(test_db: Session) -> str:
    from models import ImportJob, User

    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()), username=f"mig141-{suffix}", email=f"mig141-{suffix}@example.com",
        hashed_password="x", name="Mig 141",
    )
    test_db.add(user)
    test_db.flush()
    job = ImportJob(
        id=str(uuid.uuid4()), requested_by=user.id, status="completed", object_key=None,
    )
    test_db.add(job)
    test_db.flush()
    return job.id


class TestMigration141:
    def test_revision_chains_after_140(self):
        mig = _load()
        assert mig.revision == NAME
        assert mig.down_revision == "140_generation_cascades_and_purge_jobs"

    def test_upgrade_makes_the_key_nullable_and_is_idempotent(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert _nullable(conn)

    def test_downgrade_fills_cleared_keys_and_restores_not_null(self, test_db: Session):
        job_id = _swept_import_job(test_db)
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert not _nullable(conn)
        key = conn.execute(
            text("SELECT object_key FROM import_jobs WHERE id = :id"), {"id": job_id}
        ).scalar_one()
        assert key == ""
        with _op_context(conn):
            mig.upgrade()
        assert _nullable(conn)
