"""Shape tests for migration 147: import provenance on import_jobs.

The shared test DB already carries the four columns, the self-referencing
key and the two indexes (built from the models), so ``upgrade()`` must be a
no-op through its guards, twice. ``downgrade()`` removes all of it, and a
re-run ``upgrade()`` rebuilds the shape of the models. Deleting a job a
no-op repeated clears the no-op's ``duplicate_of_job_id``.
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
NAME = "147_import_provenance"
COLUMNS = {
    "payload_sha256",
    "source_manifest",
    "idempotency_key",
    "duplicate_of_job_id",
}
INDEXES = {"ix_import_jobs_payload_sha256", "ix_import_jobs_idempotency_key"}


def _load():
    spec = importlib.util.spec_from_file_location(
        f"mig_{NAME}", os.path.join(VERSIONS, f"{NAME}.py")
    )
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


def _assert_shape(conn):
    from models import ImportJob

    insp = inspect(conn)
    columns = {c["name"]: c for c in insp.get_columns("import_jobs")}
    assert set(columns) == {c.name for c in ImportJob.__table__.columns}
    assert COLUMNS <= set(columns)
    assert all(columns[name]["nullable"] for name in COLUMNS)
    assert "JSONB" in str(columns["source_manifest"]["type"]).upper()
    assert INDEXES <= {i["name"] for i in insp.get_indexes("import_jobs")}
    (fk,) = [
        fk
        for fk in insp.get_foreign_keys("import_jobs")
        if fk["constrained_columns"] == ["duplicate_of_job_id"]
    ]
    assert fk["referred_table"] == "import_jobs"
    assert fk["referred_columns"] == ["id"]
    assert fk["options"].get("ondelete") == "SET NULL"


class TestMigration147:
    def test_revision_chains_after_the_previous_head(self):
        mig = _load()
        assert mig.revision == NAME
        assert mig.down_revision == "146_analysis_runs"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        _assert_shape(conn)

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        insp = inspect(conn)
        assert not COLUMNS & {c["name"] for c in insp.get_columns("import_jobs")}
        assert not INDEXES & {i["name"] for i in insp.get_indexes("import_jobs")}
        with _op_context(conn):
            mig.upgrade()
        _assert_shape(conn)

    def test_deleting_the_repeated_job_clears_the_reference(self, test_db: Session):
        from models import User

        user, first, repeat = (str(uuid.uuid4()) for _ in range(3))
        test_db.add(
            User(
                id=user,
                username=f"mig147-{user[:8]}",
                email=f"{user[:8]}@example.com",
                name="Mig 147",
                hashed_password="x",
            )
        )
        test_db.flush()
        conn = test_db.connection()
        for job_id, duplicate_of in ((first, None), (repeat, first)):
            conn.execute(
                text(
                    "INSERT INTO import_jobs (id, requested_by, status, object_key, "
                    "progress, payload_sha256, idempotency_key, duplicate_of_job_id) "
                    "VALUES (:id, :u, 'completed', 'imports/k', 100, :h, :k, :d)"
                ),
                {
                    "id": job_id,
                    "u": user,
                    "h": "a" * 64,
                    "k": "b" * 64,
                    "d": duplicate_of,
                },
            )
        conn.execute(text("DELETE FROM import_jobs WHERE id = :id"), {"id": first})
        assert (
            conn.execute(
                text("SELECT duplicate_of_job_id FROM import_jobs WHERE id = :id"),
                {"id": repeat},
            ).scalar_one()
            is None
        )
