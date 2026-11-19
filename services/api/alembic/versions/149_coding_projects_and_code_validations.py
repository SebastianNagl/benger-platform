"""Codes: ``coding_projects``, ``code_validations`` and ``analysis_runs.codes``

Codes are measures read off an answer by a procedure (a versioned regex set,
a coder plugin, a judge system's coding). This migration adds what they
persist:

- ``coding_projects``: one row per project made from a sample of another
  project's answers so they can be coded, keyed by the coding project
  (cascades with it), with the source project (``SET NULL``), the answer
  source (the full response or a parsed field), the copied task data keys,
  the sample (seed, size, filters, candidate count, hash of the drawn
  generation ids), the coding format version, ``created_by`` (``SET NULL``)
  and ``created_at``.
- ``code_validations``: one row per validation of a code against the human
  codes of a coding project's control: the code as submitted and
  normalized, its kind, ref, version, identity hash and full identity record,
  options, the coding format version, the agreement metrics and per-task
  codes, kappa, observed agreement and counts, warnings, the error message
  and the Celery task id, with ``created_at``/``started_at``/``completed_at``.
  ``project_id`` cascades with the coding project, ``source_project_id`` and
  ``created_by`` are ``SET NULL``. ``status`` is checked (``pending``,
  ``running``, ``completed``, ``failed``); indexes on ``code_hash``,
  ``source_project_id`` and ``(project_id, created_at)``.
- ``analysis_runs.codes`` (JSONB, nullable): the identity record of every
  code measure a run computed, with the validation it accepted.

Idempotent: every step is guarded, so a database built from the models (the
test DB) runs it as a no-op.

Revision ID: 149_coding_projects_and_code_validations
Revises: 148_analysis_lookup_tables
Create Date: 2026-11-19
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "149_coding_projects_and_code_validations"
down_revision = "148_analysis_lookup_tables"
branch_labels = None
depends_on = None

_CODING = "coding_projects"
_VALIDATIONS = "code_validations"
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
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    if not _has_table(_CODING):
        op.create_table(
            _CODING,
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "source_project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("answer_source", jsonb, nullable=False),
            sa.Column("context_fields", jsonb, nullable=False),
            sa.Column("sample", jsonb, nullable=False),
            sa.Column("coding_version", sa.Integer(), nullable=False),
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _has_index(_CODING, "ix_coding_projects_source_project_id"):
        op.create_index(
            "ix_coding_projects_source_project_id", _CODING, ["source_project_id"]
        )

    if not _has_table(_VALIDATIONS):
        op.create_table(
            _VALIDATIONS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "source_project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("control", sa.String(200), nullable=False),
            sa.Column("code", jsonb, nullable=False),
            sa.Column("normalized_code", jsonb, nullable=False),
            sa.Column("code_kind", sa.String(20), nullable=False),
            sa.Column("code_ref", sa.String(300), nullable=True),
            sa.Column("code_version", sa.String(100), nullable=True),
            sa.Column("code_hash", sa.String(64), nullable=True),
            sa.Column("identity", jsonb, nullable=True),
            sa.Column("options", jsonb, nullable=False),
            sa.Column("coding_version", sa.Integer(), nullable=False),
            sa.Column("metrics", jsonb, nullable=True),
            sa.Column("items", jsonb, nullable=True),
            sa.Column("n_items", sa.Integer(), nullable=True),
            sa.Column("n_compared", sa.Integer(), nullable=True),
            sa.Column("kappa", sa.Float(), nullable=True),
            sa.Column("observed_agreement", sa.Float(), nullable=True),
            sa.Column("warnings", jsonb, nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("celery_task_id", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending', 'running', 'completed', 'failed')",
                name="ck_code_validations_status",
            ),
        )
    if not _has_index(_VALIDATIONS, "ix_code_validations_code_hash"):
        op.create_index("ix_code_validations_code_hash", _VALIDATIONS, ["code_hash"])
    if not _has_index(_VALIDATIONS, "ix_code_validations_source_project_id"):
        op.create_index(
            "ix_code_validations_source_project_id", _VALIDATIONS, ["source_project_id"]
        )
    if not _has_index(_VALIDATIONS, "ix_code_validations_project_created"):
        op.create_index(
            "ix_code_validations_project_created", _VALIDATIONS, ["project_id", "created_at"]
        )

    if _has_table(_RUNS) and not _has_column(_RUNS, "codes"):
        op.add_column(_RUNS, sa.Column("codes", jsonb, nullable=True))


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_table(_RUNS) and _has_column(_RUNS, "codes"):
        op.drop_column(_RUNS, "codes")
    if _has_table(_VALIDATIONS):
        op.drop_table(_VALIDATIONS)
    if _has_table(_CODING):
        op.drop_table(_CODING)
