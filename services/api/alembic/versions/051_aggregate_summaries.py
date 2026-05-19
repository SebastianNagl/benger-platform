"""Precomputed leaderboard + project summary tables.

Two summary tables let the LLM leaderboard and dashboard read tiny indexed
rows instead of scanning task_evaluations on every request. Both are kept
fresh by the Celery task `recompute_aggregates` (12h beat + manual triggers).

- `llm_leaderboard_scores`: one row per (model_id, scope, period, metric).
  Stores the precomputed weighted-mean score plus 95% CI bounds and the
  per-model row counts that the API surfaces (samples_evaluated,
  evaluation_count, generation_count, last_evaluated_at).

- `project_summaries`: one row per (project_id, period). Holds the counters
  that feed /api/dashboard/stats and the per-project tiles, plus a JSONB
  `available_models` list so the picker can skip the live DISTINCT scan.

Both tables are write-once-per-cycle from the worker and read-only from
the API; refreshing replaces rows in place via ON CONFLICT DO UPDATE.

Idempotent — both tables and their indexes guard against an already-created
state so the migration is safe to re-apply.

Revision ID: 051_aggregate_summaries
Revises: 050_polymorphize_timer_sessions
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "051_aggregate_summaries"
down_revision = "050_polymorphize_timer_sessions"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in insp.get_table_names()


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(idx["name"] == name for idx in insp.get_indexes(table))


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    names = {uc["name"] for uc in insp.get_unique_constraints(table)}
    return name in names


def upgrade():
    if not _table_exists("llm_leaderboard_scores"):
        op.create_table(
            "llm_leaderboard_scores",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("model_id", sa.String(), nullable=False),
            sa.Column(
                "project_scope_key",
                sa.String(),
                nullable=False,
                comment="'all' | 'public' | <project_id>",
            ),
            sa.Column(
                "period",
                sa.String(),
                nullable=False,
                comment="'overall' | 'monthly' | 'weekly'",
            ),
            sa.Column(
                "metric",
                sa.String(),
                nullable=False,
                comment="Specific metric key, or 'average' for cross-metric mean",
            ),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("ci_lower", sa.Float(), nullable=True),
            sa.Column("ci_upper", sa.Float(), nullable=True),
            sa.Column(
                "samples_evaluated",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "evaluation_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "generation_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "computed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _constraint_exists("llm_leaderboard_scores", "uq_lls_scope"):
        op.create_unique_constraint(
            "uq_lls_scope",
            "llm_leaderboard_scores",
            ["model_id", "project_scope_key", "period", "metric"],
        )

    if not _index_exists("llm_leaderboard_scores", "ix_lls_lookup"):
        op.create_index(
            "ix_lls_lookup",
            "llm_leaderboard_scores",
            ["project_scope_key", "period", "metric", "score"],
        )

    if not _table_exists("project_summaries"):
        op.create_table(
            "project_summaries",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "period",
                sa.String(),
                nullable=False,
                comment="'overall' | 'monthly' | 'weekly'",
            ),
            sa.Column(
                "total_tasks",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "labeled_tasks",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "annotations_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "generations_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "response_generations_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "evaluation_pairs_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "available_models",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "computed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _constraint_exists("project_summaries", "uq_ps_scope"):
        op.create_unique_constraint(
            "uq_ps_scope",
            "project_summaries",
            ["project_id", "period"],
        )

    if not _index_exists("project_summaries", "ix_ps_lookup"):
        op.create_index(
            "ix_ps_lookup",
            "project_summaries",
            ["project_id", "period"],
        )


def downgrade():
    if _table_exists("project_summaries"):
        op.drop_table("project_summaries")
    if _table_exists("llm_leaderboard_scores"):
        op.drop_table("llm_leaderboard_scores")
