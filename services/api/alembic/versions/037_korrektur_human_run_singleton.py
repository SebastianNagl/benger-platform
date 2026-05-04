"""Korrektur Falllösung as a first-class human-graded evaluation run

Two structural pieces this migration lays down for the human-graded
Falllösung redesign (the actual write/read wiring lands in the same
release's app code):

1. `task_evaluations.created_by` (nullable FK to users) — first-class
   grader identity, replacing the ad-hoc `judge_prompts_used.grader_user_id`
   JSON path. Nullable because legacy LLM-judge rows have no human grader
   and the backfill in migration 038 will populate human rows from the
   JSON path before we'd consider tightening the column.

2. A composite index on (evaluation_id, generation_id, annotation_id,
   field_name, created_by) — this column order matches the partition_by
   the cell endpoint uses for window-function dedup (latest grade per
   target+grader) and the group_by for mean aggregation (history-on
   toggle). One index drives both code paths.

3. A partial unique index on `evaluation_runs(project_id, model_id)`
   scoped to `WHERE model_id='human' AND eval_metadata->>'evaluation_type'
   = 'korrektur_falloesung'`. This is what makes the upsert helper
   (services/human_eval_runs.py) safe under concurrent submit_falloesung_grade
   calls — INSERT ... ON CONFLICT DO UPDATE RETURNING id resolves to the
   existing singleton instead of racing two grader requests into two
   parallel runs.

Revision ID: 037_korrektur_human_run_singleton
Revises: 036_taskevaluation_metrics_to_dict_shape
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa


revision = "037_korrektur_human_run_singleton"
down_revision = "036_taskevaluation_metrics_to_dict_shape"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First-class grader column. Nullable so adding it is online and so
    # legacy LLM-judge rows (no human grader) stay valid.
    op.add_column(
        "task_evaluations",
        sa.Column(
            "created_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Composite index covering both the latest-per-(target,grader) window
    # function and the AVG-per-(target,grader) group-by used by the
    # eval-results cell endpoint. Either generation_id or annotation_id is
    # NULL on a given row (a TaskEvaluation grades exactly one target),
    # which is fine for a B-tree composite index.
    op.create_index(
        "ix_task_evaluations_partition",
        "task_evaluations",
        ["evaluation_id", "generation_id", "annotation_id", "field_name", "created_by"],
    )

    # Partial unique guarantees one persistent EvaluationRun per project
    # for the Korrektur-Falllösung human-grading workflow. The predicate
    # uses `eval_metadata ->> 'evaluation_type'` (operator is IMMUTABLE on
    # both json and jsonb), which the upsert helper sets to the string
    # 'korrektur_falloesung'.
    #
    # Raw SQL: alembic's op.create_index doesn't expose partial-index
    # predicates with JSON operators in a portable way.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_human_eval_run_per_project_metric
        ON evaluation_runs (project_id, model_id)
        WHERE model_id = 'human'
          AND (eval_metadata ->> 'evaluation_type') = 'korrektur_falloesung'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_human_eval_run_per_project_metric")
    op.drop_index("ix_task_evaluations_partition", table_name="task_evaluations")
    op.drop_column("task_evaluations", "created_by")
