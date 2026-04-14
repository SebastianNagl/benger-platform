"""Add ai_assisted flag to annotations

Denormalized from the conditional instruction variant's ai_allowed flag.
Enables efficient querying for the Co-Creation leaderboard (Issue #1272).

Revision ID: 019_add_ai_assisted_to_annotations
Revises: 018_add_annotation_id_to_task_evaluations
Create Date: 2026-03-03

"""

import sqlalchemy as sa
from alembic import op

revision = "019_add_ai_assisted_to_annotations"
down_revision = "018_add_annotation_id_to_task_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "annotations",
        sa.Column(
            "ai_assisted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_annotations_ai_assisted",
        "annotations",
        ["ai_assisted"],
    )


def downgrade() -> None:
    op.drop_index("ix_annotations_ai_assisted", table_name="annotations")
    op.drop_column("annotations", "ai_assisted")
