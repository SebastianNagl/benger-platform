"""Add post-annotation questionnaire and enhanced timing (Issue #1208)

Adds questionnaire_enabled and questionnaire_config to projects.
Adds active_duration_ms, focused_duration_ms, tab_switches to annotations.
Creates post_annotation_responses table.

Revision ID: 015_post_annotation_questionnaire
Revises: 014_profile_confirm_notif
Create Date: 2026-02-21

"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers
revision = "015_post_annotation_questionnaire"
down_revision = "014_profile_confirm_notif"
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in the table."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [col['name'] for col in insp.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(table_name, index_name):
    """Check if an index exists on the table."""
    bind = op.get_bind()
    insp = inspect(bind)
    indexes = [idx['name'] for idx in insp.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    # ============= Add questionnaire fields to projects =============
    if not column_exists('projects', 'questionnaire_enabled'):
        op.add_column(
            'projects',
            sa.Column(
                'questionnaire_enabled',
                sa.Boolean(),
                nullable=False,
                server_default='false',
            ),
        )

    if not column_exists('projects', 'questionnaire_config'):
        op.add_column(
            'projects',
            sa.Column('questionnaire_config', sa.Text(), nullable=True),
        )

    # ============= Add enhanced timing to annotations =============
    if not column_exists('annotations', 'active_duration_ms'):
        op.add_column(
            'annotations',
            sa.Column('active_duration_ms', sa.BigInteger(), nullable=True),
        )

    if not column_exists('annotations', 'focused_duration_ms'):
        op.add_column(
            'annotations',
            sa.Column('focused_duration_ms', sa.BigInteger(), nullable=True),
        )

    if not column_exists('annotations', 'tab_switches'):
        op.add_column(
            'annotations',
            sa.Column(
                'tab_switches',
                sa.Integer(),
                nullable=False,
                server_default='0',
            ),
        )

    # ============= Create post_annotation_responses table =============
    if not table_exists('post_annotation_responses'):
        op.create_table(
            'post_annotation_responses',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('annotation_id', sa.String(), nullable=False),
            sa.Column('task_id', sa.String(), nullable=False),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('result', JSONB(), nullable=False),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ['annotation_id'], ['annotations.id'], ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['task_id'], ['tasks.id'], ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['project_id'], ['projects.id'], ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['user_id'], ['users.id'], ondelete='CASCADE',
            ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_par_id', 'post_annotation_responses', ['id'])
        op.create_index('ix_par_annotation_id', 'post_annotation_responses', ['annotation_id'])
        op.create_index('ix_par_project_id', 'post_annotation_responses', ['project_id'])
        op.create_index(
            'ix_par_user_project',
            'post_annotation_responses',
            ['user_id', 'project_id'],
        )


def downgrade() -> None:
    # Drop post_annotation_responses table
    if table_exists('post_annotation_responses'):
        if index_exists('post_annotation_responses', 'ix_par_user_project'):
            op.drop_index('ix_par_user_project', table_name='post_annotation_responses')
        if index_exists('post_annotation_responses', 'ix_par_project_id'):
            op.drop_index('ix_par_project_id', table_name='post_annotation_responses')
        if index_exists('post_annotation_responses', 'ix_par_annotation_id'):
            op.drop_index('ix_par_annotation_id', table_name='post_annotation_responses')
        if index_exists('post_annotation_responses', 'ix_par_id'):
            op.drop_index('ix_par_id', table_name='post_annotation_responses')
        op.drop_table('post_annotation_responses')

    # Drop enhanced timing columns from annotations
    if column_exists('annotations', 'tab_switches'):
        op.drop_column('annotations', 'tab_switches')
    if column_exists('annotations', 'focused_duration_ms'):
        op.drop_column('annotations', 'focused_duration_ms')
    if column_exists('annotations', 'active_duration_ms'):
        op.drop_column('annotations', 'active_duration_ms')

    # Drop questionnaire columns from projects
    if column_exists('projects', 'questionnaire_config'):
        op.drop_column('projects', 'questionnaire_config')
    if column_exists('projects', 'questionnaire_enabled'):
        op.drop_column('projects', 'questionnaire_enabled')
