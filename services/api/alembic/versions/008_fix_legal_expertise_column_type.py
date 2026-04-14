"""Fix legal_expertise_level column type for production

Production has legal_expertise_level as integer (from old migration history),
but the ORM expects string enum values like 'judge_professor'.
Fresh installs already have varchar(50) from the baseline migration.

This migration is idempotent - it only alters the column if the type is integer.
All existing production users have NULL for this column, so no data conversion needed.

Revision ID: 008_fix_legal_expertise_type
Revises: 007_sync_prod_dev
Create Date: 2026-02-06

"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = '008_fix_legal_expertise_type'
down_revision = '007_sync_prod_dev'
branch_labels = None
depends_on = None


def get_column_type(table_name, column_name):
    """Get the database type name of a column."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = inspector.get_columns(table_name)
    for col in columns:
        if col['name'] == column_name:
            return str(col['type'])
    return None


def upgrade():
    """Fix legal_expertise_level column type from integer to varchar(50).

    Only applies to production where the column was created as integer
    by the old migration history. Fresh installs already have varchar(50)
    from the baseline migration.
    """
    col_type = get_column_type('users', 'legal_expertise_level')

    if col_type is not None and 'INT' in col_type.upper():
        op.alter_column(
            'users',
            'legal_expertise_level',
            type_=sa.String(50),
            existing_type=sa.Integer(),
            existing_nullable=True,
            postgresql_using='NULL',
        )


def downgrade():
    """Revert legal_expertise_level back to integer.

    Only safe if all values are NULL.
    """
    col_type = get_column_type('users', 'legal_expertise_level')

    if col_type is not None and 'VARCHAR' in col_type.upper():
        op.alter_column(
            'users',
            'legal_expertise_level',
            type_=sa.Integer(),
            existing_type=sa.String(50),
            existing_nullable=True,
            postgresql_using='NULL',
        )
