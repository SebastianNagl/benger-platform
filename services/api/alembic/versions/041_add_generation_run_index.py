"""Add multi-run support to generation pipeline.

Each `Generation` row gets a `run_index` so multiple trials of the same
(task, model, structure) can coexist under one parent `ResponseGeneration`.
The parent gets `runs_requested`/`runs_completed`/`runs_failed` counters so
the worker can fan out N trials, atomically tick progress, and mark the
parent `failed` on the first trial failure (per the multi-run UX decision).

Backfill: every existing Generation gets `run_index = 0`; every existing
ResponseGeneration gets `runs_requested = 1` and `runs_completed = 1` if the
parent is `completed`, else 0.

Revision ID: 041_add_generation_run_index
Revises: 040_add_llm_call_metadata_columns
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "041_add_generation_run_index"
down_revision = "040_add_llm_call_metadata_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # generations.run_index — 0-indexed trial number within the parent job
    op.add_column(
        "generations",
        sa.Column(
            "run_index",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )

    # response_generations counters
    op.add_column(
        "response_generations",
        sa.Column(
            "runs_requested",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "response_generations",
        sa.Column(
            "runs_completed",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "response_generations",
        sa.Column(
            "runs_failed",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )

    # Backfill Generation.run_index per parent so multiple historical retries
    # under the same ResponseGeneration get distinct indices instead of all
    # collapsing to 0. The dev DB has parents with several Generation rows
    # from failed-then-rerun cycles; without this the unique index fails.
    # Order is by created_at then id so the assignment is deterministic and
    # reproducible across re-runs of the migration.
    op.execute(
        """
        WITH numbered AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY generation_id
                       ORDER BY created_at NULLS LAST, id
                   ) - 1 AS new_run_index
            FROM generations
        )
        UPDATE generations g
        SET run_index = numbered.new_run_index
        FROM numbered
        WHERE g.id = numbered.id
        """
    )

    # Backfill the parent counters from the now-numbered children.
    # runs_requested = number of children that exist (snapshot of "what was tried")
    # runs_completed = children with status='completed'
    # runs_failed = children with status='failed'
    op.execute(
        """
        UPDATE response_generations rg
        SET runs_requested = COALESCE(child_counts.total, 1),
            runs_completed = COALESCE(child_counts.completed, 0),
            runs_failed = COALESCE(child_counts.failed, 0)
        FROM (
            SELECT generation_id,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                   COUNT(*) FILTER (WHERE status = 'failed') AS failed
            FROM generations
            GROUP BY generation_id
        ) child_counts
        WHERE rg.id = child_counts.generation_id
        """
    )

    # Idempotency for Celery redelivery: at most one Generation per (parent, run_index)
    op.create_index(
        "uq_generations_parent_run_index",
        "generations",
        ["generation_id", "run_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_generations_parent_run_index", table_name="generations")
    op.drop_column("response_generations", "runs_failed")
    op.drop_column("response_generations", "runs_completed")
    op.drop_column("response_generations", "runs_requested")
    op.drop_column("generations", "run_index")
