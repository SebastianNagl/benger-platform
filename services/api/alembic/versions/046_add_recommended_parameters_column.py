"""Add llm_models.recommended_parameters JSON column.

Each LLM model can carry a `recommended_parameters` block sourced from
the provider's documented best values. Shape (filled by the YAML seed):

    {
      "default":    {temperature, max_tokens, top_p, seed, ...},
      "evaluation": {temperature, ...},   # optional; overrides keys from
                                           # `default` when the model is
                                           # used as a judge / for eval
      "provenance": {source: URL, retrieved: ISO-date}
    }

Worker resolves a parameter for `(model, mode, key)` by:
    recommended_parameters[mode][key]
    -> recommended_parameters["default"][key]
    -> SYSTEM_DEFAULTS[key]
…then user overrides win over recommended (project default → per-model)
and `parameter_constraints` clamps the final value last.

NULL means "no recommended set for this model" — UI surfaces a "keine
Empfehlung" badge so researchers know they're using system fallback.

Revision ID: 046_add_recommended_parameters_column
Revises: 045_add_research_data_consent
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa


revision = "046_add_recommended_parameters_column"
down_revision = "045_add_research_data_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_models",
        sa.Column("recommended_parameters", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_models", "recommended_parameters")
