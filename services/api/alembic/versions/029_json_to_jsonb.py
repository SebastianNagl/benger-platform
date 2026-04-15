"""Convert annotation JSON columns to JSONB for consistency

The Annotation model declares result/draft/prediction_scores as JSONB
but the baseline migration created them as JSON. This caused
json_array_length(jsonb) errors since PostgreSQL's json_array_length
only accepts json type. Aligning the DB to JSONB.

Revision ID: 029_json_to_jsonb
Revises: 028_populate_parameter_constraints
Create Date: 2026-03-26
"""

from alembic import op

revision = "029_json_to_jsonb"
down_revision = "028_populate_parameter_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE annotations ALTER COLUMN result TYPE jsonb USING result::jsonb")
    op.execute("ALTER TABLE annotations ALTER COLUMN draft TYPE jsonb USING draft::jsonb")
    op.execute(
        "ALTER TABLE annotations ALTER COLUMN prediction_scores TYPE jsonb USING prediction_scores::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE annotations ALTER COLUMN result TYPE json USING result::json")
    op.execute("ALTER TABLE annotations ALTER COLUMN draft TYPE json USING draft::json")
    op.execute(
        "ALTER TABLE annotations ALTER COLUMN prediction_scores TYPE json USING prediction_scores::json"
    )
