"""Add judge_prompts_used column to task_evaluations for prompt provenance

Stores the exact prompts (system + evaluation + criteria) used by LLM judge
evaluations, enabling scientific reproducibility and audit trails.

Revision ID: 030_add_judge_prompt_provenance
Revises: 029_json_to_jsonb
Create Date: 2026-04-10
"""

import sqlalchemy as sa
from alembic import op

revision = "030_add_judge_prompt_provenance"
down_revision = "029_json_to_jsonb"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_evaluations",
        sa.Column("judge_prompts_used", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("task_evaluations", "judge_prompts_used")
