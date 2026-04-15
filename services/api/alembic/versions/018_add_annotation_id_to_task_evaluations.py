"""Add annotation_id to task_evaluations

Enables storing evaluation results for human annotations (not just generations).
Used by the Standard Falloesung LLM judge to evaluate annotator solutions.

Revision ID: 018_add_annotation_id_to_task_evaluations
Revises: 017_add_conditional_instructions
Create Date: 2026-02-27

"""

import sqlalchemy as sa
from alembic import op

revision = "018_add_annotation_id_to_task_evaluations"
down_revision = "017_add_conditional_instructions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_evaluations",
        sa.Column(
            "annotation_id",
            sa.String(),
            sa.ForeignKey("annotations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_task_evaluations_annotation_id",
        "task_evaluations",
        ["annotation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_evaluations_annotation_id", table_name="task_evaluations")
    op.drop_column("task_evaluations", "annotation_id")
