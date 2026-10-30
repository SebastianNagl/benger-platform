"""Partial unique index for the korrektur_feedback human-run singleton

Third sibling of migrations 037 (``korrektur_falloesung``) and 061
(``korrektur_custom``). The extended edition's ``submit_feedback_grade``
endpoint (human Korrektur of the French exam types on the barème /20)
resolves its destination run through
``get_or_create_human_eval_run(db, project_id, "korrektur_feedback", ...)``,
which upserts with ``INSERT ... ON CONFLICT`` against a per-metric partial
unique index. Without this index the upsert raises "no unique or exclusion
constraint matching the ON CONFLICT specification".

One index per metric, not one combined predicate: the unique key is
``(project_id, model_id)`` with ``model_id`` always ``'human'``, so a
combined predicate would collapse the metrics' singletons into one row.

Idempotent (``IF NOT EXISTS`` / ``IF EXISTS``), like 037 and 061.

Revision ID: 122_korrektur_feedback_human_run_singleton
Revises: 121_project_enable_prompts
Create Date: 2026-10-30
"""

from alembic import op


revision = "122_korrektur_feedback_human_run_singleton"
down_revision = "121_project_enable_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_human_eval_run_per_project_metric_feedback
        ON evaluation_runs (project_id, model_id)
        WHERE model_id = 'human'
          AND (eval_metadata ->> 'evaluation_type') = 'korrektur_feedback'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_human_eval_run_per_project_metric_feedback")
