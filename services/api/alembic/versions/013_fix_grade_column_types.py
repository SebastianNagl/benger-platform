"""Fix grade columns from Float to Numeric for exact decimal storage

Float (32-bit) cannot represent values like 9.2 exactly, causing
9.2 to be stored as 9.18. Numeric(4,2) stores exact decimals.

Revision ID: 013_fix_grade_column_types
Revises: 012_mandatory_profile_fields
Create Date: 2026-02-22

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "013_fix_grade_column_types"
down_revision = "012_mandatory_profile_fields"
branch_labels = None
depends_on = None

GRADE_COLUMNS = [
    "grade_zwischenpruefung",
    "grade_vorgeruecktenubung",
    "grade_first_staatsexamen",
    "grade_second_staatsexamen",
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    for col in GRADE_COLUMNS:
        if col in existing_columns:
            op.alter_column(
                "users",
                col,
                type_=sa.Numeric(4, 2),
                existing_type=sa.Float(),
                existing_nullable=True,
            )


def downgrade() -> None:
    for col in GRADE_COLUMNS:
        op.alter_column(
            "users",
            col,
            type_=sa.Float(),
            existing_type=sa.Numeric(4, 2),
            existing_nullable=True,
        )
