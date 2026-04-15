"""Add randomize_task_order to projects

Add randomize_task_order boolean column to projects table for
per-user deterministic task shuffling to achieve even annotation
distribution across tasks.

Revision ID: 022_add_randomize_task_order
Revises: 021_add_llm_model_pricing_columns
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "022_add_randomize_task_order"
down_revision = "021_add_llm_model_pricing_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "randomize_task_order",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "randomize_task_order")
