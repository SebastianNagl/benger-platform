"""Add is_private column to projects table

Supports private projects that are not assigned to any organization.
Private projects are only visible to their creator and superadmins.

Revision ID: 009_add_private_projects
Revises: 008_fix_legal_expertise_type
Create Date: 2026-02-12

"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = '009_add_private_projects'
down_revision = '008_fix_legal_expertise_type'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in the table."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [col['name'] for col in insp.get_columns(table_name)]
    return column_name in columns


def index_exists(table_name, index_name):
    """Check if an index exists on the table."""
    bind = op.get_bind()
    insp = inspect(bind)
    indexes = [idx['name'] for idx in insp.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    # Add is_private column to projects table
    if not column_exists('projects', 'is_private'):
        op.add_column(
            'projects',
            sa.Column('is_private', sa.Boolean(), server_default='false', nullable=False),
        )

    # Add index on is_private for efficient filtering
    if not index_exists('projects', 'ix_projects_is_private'):
        op.create_index('ix_projects_is_private', 'projects', ['is_private'])

    # Add index on created_by for efficient private project lookup
    if not index_exists('projects', 'ix_projects_created_by'):
        op.create_index('ix_projects_created_by', 'projects', ['created_by'])


def downgrade() -> None:
    if index_exists('projects', 'ix_projects_created_by'):
        op.drop_index('ix_projects_created_by', table_name='projects')

    if index_exists('projects', 'ix_projects_is_private'):
        op.drop_index('ix_projects_is_private', table_name='projects')

    if column_exists('projects', 'is_private'):
        op.drop_column('projects', 'is_private')
