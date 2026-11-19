"""Versioned lookup tables for analyses, and the inputs a run resolved

- ``analysis_lookup_tables``: a named, versioned table of a project that
  analysis specs join onto their frames (``lookups`` in the spec, for
  example a coding of system x offence x group). Every upload of a name is
  the next version; versions are immutable. Columns: ``id``, ``project_id``
  (cascades with the project), ``name``, ``version`` (from 1), an optional
  ``description``, the column names (``columns``, JSONB list) and the rows
  (``rows``, JSONB list of lists in column order), ``row_count``, the content
  hash (SHA-256 of the canonical JSON of columns and rows), ``created_by``
  (``SET NULL``) and ``created_at``. ``(project_id, name, version)`` is
  unique.
- ``analysis_runs.resolved_inputs`` (JSONB): what a run read besides its own
  project, as resolved by the worker: the further projects of a
  cross-project frame and every stored lookup table with its project, name,
  version and content hash.

Idempotent: every step is guarded, so a database built from the models (the
test DB) runs it as a no-op.

Revision ID: 148_analysis_lookup_tables
Revises: 147_import_provenance
Create Date: 2026-11-19
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "148_analysis_lookup_tables"
down_revision = "147_import_provenance"
branch_labels = None
depends_on = None

_TABLE = "analysis_lookup_tables"
_RUNS = "analysis_runs"


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _insp().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    jsonb = postgresql.JSONB()

    if not _has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id", sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("columns", jsonb, nullable=False),
            sa.Column("rows", jsonb, nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.CheckConstraint("version >= 1", name="ck_analysis_lookup_tables_version"),
            sa.UniqueConstraint(
                "project_id", "name", "version", name="uq_analysis_lookup_tables_version"
            ),
        )
    if not _has_index(_TABLE, "ix_analysis_lookup_tables_project_name"):
        op.create_index(
            "ix_analysis_lookup_tables_project_name", _TABLE, ["project_id", "name"]
        )
    if _has_table(_RUNS) and not _has_column(_RUNS, "resolved_inputs"):
        op.add_column(_RUNS, sa.Column("resolved_inputs", jsonb, nullable=True))


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_table(_RUNS) and _has_column(_RUNS, "resolved_inputs"):
        op.drop_column(_RUNS, "resolved_inputs")
    if _has_table(_TABLE):
        op.drop_table(_TABLE)
