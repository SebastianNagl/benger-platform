"""Partial unique index for the korrektur_custom human-run singleton

Companion to migration 037 (extended#33). The extended edition's
``submit_custom_grade`` endpoint resolves its destination run through
``get_or_create_human_eval_run(db, project_id, "korrektur_custom", ...)``,
which upserts with ``INSERT ... ON CONFLICT`` against a per-metric partial
unique index. Migration 037 only created the index for
``korrektur_falloesung``; without an equivalent index for
``korrektur_custom`` the upsert raises "no unique or exclusion constraint
matching the ON CONFLICT specification" (a live prod 500).

Deliberately a second per-metric index rather than one combined
``evaluation_type IN (...)`` index: the unique key is
``(project_id, model_id)`` and ``model_id`` is always ``'human'`` here, so
a combined predicate would collapse the falloesung and custom singletons
into ONE allowed row per project — but each metric must keep its own run.
The upsert helper passes a per-metric predicate so Postgres infers the
right index for each metric.

Idempotent — uses ``CREATE UNIQUE INDEX IF NOT EXISTS`` / ``DROP INDEX IF
EXISTS`` so re-running is a no-op (mirrors the 037 raw-SQL approach with
the 057/058-style guard semantics).

Revision ID: 061_korrektur_custom_human_run_singleton
Revises: 060_add_export_job_task_ids
Create Date: 2026-06-12
"""

from alembic import op


revision = "061_korrektur_custom_human_run_singleton"
down_revision = "060_add_export_job_task_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Raw SQL: alembic's op.create_index doesn't expose partial-index
    # predicates with JSON operators in a portable way (same as 037).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_human_eval_run_per_project_metric_custom
        ON evaluation_runs (project_id, model_id)
        WHERE model_id = 'human'
          AND (eval_metadata ->> 'evaluation_type') = 'korrektur_custom'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_human_eval_run_per_project_metric_custom")
