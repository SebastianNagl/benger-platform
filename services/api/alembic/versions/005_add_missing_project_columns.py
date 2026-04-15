"""Add missing project columns from baseline squash

This migration adds columns that existed in the squashed baseline but were
missing from production due to the migration history divergence.

Revision ID: 005_add_missing_project_columns
Revises: 004_add_missing_user_columns
Create Date: 2026-02-05

"""
import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = '005_add_missing_project_columns'
down_revision = '004_add_missing_user_columns'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    """Add columns that were in baseline but missing from production."""
    # Label config versioning
    if not column_exists('projects', 'label_config_version'):
        op.add_column(
            'projects',
            sa.Column('label_config_version', sa.Integer(), nullable=True, server_default='1'),
        )
    if not column_exists('projects', 'label_config_history'):
        op.add_column('projects', sa.Column('label_config_history', sa.JSON(), nullable=True))

    # Immediate evaluation feature
    if not column_exists('projects', 'immediate_evaluation_enabled'):
        op.add_column(
            'projects',
            sa.Column(
                'immediate_evaluation_enabled', sa.Boolean(), nullable=False, server_default='false'
            ),
        )

    # Annotation time limit feature
    if not column_exists('projects', 'annotation_time_limit_enabled'):
        op.add_column(
            'projects',
            sa.Column(
                'annotation_time_limit_enabled',
                sa.Boolean(),
                nullable=False,
                server_default='false',
            ),
        )
    if not column_exists('projects', 'annotation_time_limit_seconds'):
        op.add_column(
            'projects',
            sa.Column(
                'annotation_time_limit_seconds', sa.Integer(), nullable=True, server_default='0'
            ),
        )

    # Project archiving
    if not column_exists('projects', 'is_archived'):
        op.add_column(
            'projects',
            sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'),
        )


def downgrade():
    """Remove the added columns."""
    if column_exists('projects', 'is_archived'):
        op.drop_column('projects', 'is_archived')
    if column_exists('projects', 'annotation_time_limit_seconds'):
        op.drop_column('projects', 'annotation_time_limit_seconds')
    if column_exists('projects', 'annotation_time_limit_enabled'):
        op.drop_column('projects', 'annotation_time_limit_enabled')
    if column_exists('projects', 'immediate_evaluation_enabled'):
        op.drop_column('projects', 'immediate_evaluation_enabled')
    if column_exists('projects', 'label_config_history'):
        op.drop_column('projects', 'label_config_history')
    if column_exists('projects', 'label_config_version'):
        op.drop_column('projects', 'label_config_version')
