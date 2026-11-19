"""Import provenance and idempotent re-import on import jobs.

- ``import_jobs.payload_sha256`` (String(64), nullable, indexed): SHA-256 of
  the payload bytes the worker downloaded, so every import of one file can
  be found.
- ``import_jobs.source_manifest`` (JSONB, nullable): where the payload came
  from and what it was imported as (``shared/import_provenance.py``).
- ``import_jobs.idempotency_key`` (String(64), nullable, indexed): SHA-256
  over payload hash, target and the options that shape the result. A new
  import whose key equals that of a completed import is a no-op.
- ``import_jobs.duplicate_of_job_id`` (String, nullable, FK import_jobs.id
  ON DELETE SET NULL): the completed import a no-op job repeated.

Rows written before this migration keep NULL in all four, so they are never
matched: the first import of a file after the upgrade runs as before.

Pure additive and idempotent: each step is guarded by an inspector check,
so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 147_import_provenance
Revises: 146_analysis_runs
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "147_import_provenance"
down_revision = "146_analysis_runs"
branch_labels = None
depends_on = None

_TABLE = "import_jobs"
_FK = "fk_import_jobs_duplicate_of_job_id"
_INDEXES = {
    "ix_import_jobs_payload_sha256": "payload_sha256",
    "ix_import_jobs_idempotency_key": "idempotency_key",
}


def _inspector():
    return inspect(op.get_bind())


def _columns() -> set:
    insp = _inspector()
    if _TABLE not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(_TABLE)}


def _indexes() -> set:
    insp = _inspector()
    if _TABLE not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes(_TABLE)}


def _duplicate_fks() -> set:
    """Names of the foreign keys on duplicate_of_job_id, whatever they are
    called (create_all names them after the convention of the models)."""
    insp = _inspector()
    if _TABLE not in insp.get_table_names():
        return set()
    return {
        fk["name"]
        for fk in insp.get_foreign_keys(_TABLE)
        if fk["constrained_columns"] == ["duplicate_of_job_id"]
    }


def upgrade() -> None:
    existing = _columns()
    if "payload_sha256" not in existing:
        op.add_column(_TABLE, sa.Column("payload_sha256", sa.String(64), nullable=True))
    if "source_manifest" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "source_manifest",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
    if "idempotency_key" not in existing:
        op.add_column(
            _TABLE, sa.Column("idempotency_key", sa.String(64), nullable=True)
        )
    if "duplicate_of_job_id" not in existing:
        op.add_column(
            _TABLE, sa.Column("duplicate_of_job_id", sa.String(), nullable=True)
        )
    if not _duplicate_fks():
        op.create_foreign_key(
            _FK,
            _TABLE,
            _TABLE,
            ["duplicate_of_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
    present = _indexes()
    for name, column in _INDEXES.items():
        if name not in present:
            op.create_index(name, _TABLE, [column])


def downgrade() -> None:
    present = _indexes()
    for name in _INDEXES:
        if name in present:
            op.drop_index(name, table_name=_TABLE)
    for name in _duplicate_fks():
        op.drop_constraint(name, _TABLE, type_="foreignkey")
    existing = _columns()
    for column in (
        "duplicate_of_job_id",
        "idempotency_key",
        "source_manifest",
        "payload_sha256",
    ):
        if column in existing:
            op.drop_column(_TABLE, column)
