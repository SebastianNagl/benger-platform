"""Add pricing columns to llm_models table

Add input_cost_per_million and output_cost_per_million columns for
storing per-model pricing as the single source of truth, eliminating
redundant pricing dicts in provider_capabilities.py and the frontend.

Revision ID: 021_add_llm_model_pricing_columns
Revises: 020_make_organization_id_nullable
Create Date: 2026-03-07

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "021_add_llm_model_pricing_columns"
down_revision = "020_make_organization_id_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_models",
        sa.Column("input_cost_per_million", sa.Float(), nullable=True),
    )
    op.add_column(
        "llm_models",
        sa.Column("output_cost_per_million", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_models", "output_cost_per_million")
    op.drop_column("llm_models", "input_cost_per_million")
