"""Make legacy NOT NULL columns nullable

Legacy columns that are no longer in the SQLAlchemy models but still exist
in the database with NOT NULL constraints cause 500 errors on INSERT because
SQLAlchemy omits them from the statement.

- projects.organization_id: replaced by project_organizations junction table
- tasks.total_predictions: removed from Task model

Revision ID: 020_make_organization_id_nullable
Revises: 019_add_ai_assisted_to_annotations
Create Date: 2026-03-06

"""

from sqlalchemy import inspect

from alembic import op

# revision identifiers
revision = "020_make_organization_id_nullable"
down_revision = "019_add_ai_assisted_to_annotations"
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in the table."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [col['name'] for col in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if column_exists('projects', 'organization_id'):
        op.alter_column('projects', 'organization_id', nullable=True)
    if column_exists('tasks', 'total_predictions'):
        op.alter_column('tasks', 'total_predictions', nullable=True)


def downgrade() -> None:
    # Don't restore NOT NULL - it would break project creation and data import
    pass
