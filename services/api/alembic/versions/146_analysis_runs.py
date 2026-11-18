"""Analysis runs and their estimates: ``analysis_runs``, ``analysis_estimates``

The analysis engine (``services/shared/analysis``) runs a declared spec over a
project's generations on the ``analysis`` worker queue and records:

- ``analysis_runs``: one row per run with the submitted and the normalized
  spec (JSONB), the spec hash and spec format version, the engine version,
  the frame snapshot (content hash, object key under ``analysis/``, its
  SHA-256, size and row count, the frame counts), the numeric library
  versions and the workers' lockfile hash, a reserved seed, the per-fit
  summaries, warnings and timings, the estimate count, the error message and
  the Celery task id, with ``created_at``/``started_at``/``completed_at``.
  ``project_id`` cascades with the project; ``created_by`` is ``SET NULL``.
  ``status`` is checked (``pending``, ``running``, ``completed``, ``failed``);
  indexes on ``spec_hash`` and ``(project_id, created_at)``.
- ``analysis_estimates``: one row per estimate (estimand, contrast, scope)
  with estimate, standard error, statistic, degrees of freedom, p-value,
  null, interval, equivalence (the first bound set as a boolean, all sets in
  ``tost``), minimum detectable effect, ratio parts, family with adjusted
  p-value and every membership in ``adjustments``, observation and cluster
  counts and the conventions used. Cascades with its run; ``(run_id,
  position)`` is unique and ``(run_id, estimand_id)`` indexed.

Idempotent: every step is guarded, so a database built from the models (the
test DB) runs it as a no-op.

Revision ID: 146_analysis_runs
Revises: 145_compliance_findings
Create Date: 2026-11-18
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "146_analysis_runs"
down_revision = "145_compliance_findings"
branch_labels = None
depends_on = None

_RUNS = "analysis_runs"
_ESTIMATES = "analysis_estimates"


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    jsonb = postgresql.JSONB()

    if not _has_table(_RUNS):
        op.create_table(
            _RUNS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id", sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("spec", jsonb, nullable=False),
            sa.Column("normalized_spec", jsonb, nullable=False),
            sa.Column("spec_hash", sa.String(64), nullable=False),
            sa.Column("spec_version", sa.Integer(), nullable=False),
            sa.Column("engine_version", sa.String(32), nullable=False),
            sa.Column("frame_hash", sa.String(64), nullable=True),
            sa.Column("frame_object_key", sa.String(), nullable=True),
            sa.Column("frame_sha256", sa.String(64), nullable=True),
            sa.Column("frame_bytes", sa.BigInteger(), nullable=True),
            sa.Column("frame_rows", sa.Integer(), nullable=True),
            sa.Column("frame_counts", jsonb, nullable=True),
            sa.Column("library_versions", jsonb, nullable=True),
            sa.Column("lockfile_sha256", sa.String(64), nullable=True),
            sa.Column("seed", sa.BigInteger(), nullable=True),
            sa.Column("fits", jsonb, nullable=True),
            sa.Column("warnings", jsonb, nullable=True),
            sa.Column("timings", jsonb, nullable=True),
            sa.Column(
                "estimates_count", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("celery_task_id", sa.String(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending', 'running', 'completed', 'failed')",
                name="ck_analysis_runs_status",
            ),
        )
    if not _has_index(_RUNS, "ix_analysis_runs_spec_hash"):
        op.create_index("ix_analysis_runs_spec_hash", _RUNS, ["spec_hash"])
    if not _has_index(_RUNS, "ix_analysis_runs_project_created"):
        op.create_index(
            "ix_analysis_runs_project_created", _RUNS, ["project_id", "created_at"]
        )

    if not _has_table(_ESTIMATES):
        op.create_table(
            _ESTIMATES,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "run_id", sa.String(),
                sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("estimand_id", sa.String(200), nullable=False),
            sa.Column("contrast_id", sa.String(200), nullable=True),
            sa.Column("estimator", sa.String(32), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False, server_default="linear"),
            sa.Column("outcome", sa.String(100), nullable=False),
            sa.Column("scope", sa.String(500), nullable=False),
            sa.Column("scope_values", jsonb, nullable=True),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("estimate", sa.Float(), nullable=True),
            sa.Column("std_error", sa.Float(), nullable=True),
            sa.Column("statistic", sa.Float(), nullable=True),
            sa.Column("df", sa.Integer(), nullable=True),
            sa.Column("p_value", sa.Float(), nullable=True),
            sa.Column("null_value", sa.Float(), nullable=True),
            sa.Column("ci_level", sa.Float(), nullable=True),
            sa.Column("ci_lower", sa.Float(), nullable=True),
            sa.Column("ci_upper", sa.Float(), nullable=True),
            sa.Column("equivalent", sa.Boolean(), nullable=True),
            sa.Column("tost", jsonb, nullable=True),
            sa.Column("mde", jsonb, nullable=True),
            sa.Column("ratio", jsonb, nullable=True),
            sa.Column("family", sa.String(200), nullable=True),
            sa.Column("p_adjusted", sa.Float(), nullable=True),
            sa.Column("adjustments", jsonb, nullable=True),
            sa.Column("n_obs", sa.Integer(), nullable=True),
            sa.Column("n_clusters", jsonb, nullable=True),
            sa.Column("k_params", sa.Integer(), nullable=True),
            sa.Column("conventions", jsonb, nullable=True),
            sa.UniqueConstraint(
                "run_id", "position", name="uq_analysis_estimates_run_position"
            ),
        )
    if not _has_index(_ESTIMATES, "ix_analysis_estimates_run_estimand"):
        op.create_index(
            "ix_analysis_estimates_run_estimand", _ESTIMATES, ["run_id", "estimand_id"]
        )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_table(_ESTIMATES):
        op.drop_table(_ESTIMATES)
    if _has_table(_RUNS):
        op.drop_table(_RUNS)
