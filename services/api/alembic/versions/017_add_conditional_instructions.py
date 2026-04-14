"""Add conditional instruction variants and variant tracking

Adds:
- projects.instructions_always_visible (bool) - force instructions on every task
- projects.conditional_instructions (JSONB) - [{id, content, weight}] variants
- annotations.instruction_variant (string) - which variant was shown

Revision ID: 017_add_conditional_instructions
Revises: 016_rename_evaluation_tables
Create Date: 2026-02-24

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "017_add_conditional_instructions"
down_revision = "016_rename_evaluation_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add instructions_always_visible to projects
    op.add_column(
        "projects",
        sa.Column(
            "instructions_always_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Add conditional_instructions JSONB to projects
    op.add_column(
        "projects",
        sa.Column("conditional_instructions", JSONB, nullable=True),
    )

    # Add instruction_variant to annotations
    op.add_column(
        "annotations",
        sa.Column("instruction_variant", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("annotations", "instruction_variant")
    op.drop_column("projects", "conditional_instructions")
    op.drop_column("projects", "instructions_always_visible")
