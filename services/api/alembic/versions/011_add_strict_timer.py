"""Add strict timer mode with server-side time tracking (Issue #1205)

Creates annotation_timer_sessions table for server-side timer tracking.
Adds strict_timer_enabled to projects, auto_submitted to annotations.

Revision ID: 011_add_strict_timer
Revises: 010_add_org_api_keys
Create Date: 2026-02-18

"""


import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = '011_add_strict_timer'
down_revision = '010_add_org_api_keys'
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
    # ============= Create annotation_timer_sessions table =============
    if not table_exists('annotation_timer_sessions'):
        op.create_table(
            'annotation_timer_sessions',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('task_id', sa.String(), nullable=False),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column(
                'started_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
            sa.Column('time_limit_seconds', sa.Integer(), nullable=False),
            sa.Column(
                'is_strict',
                sa.Boolean(),
                server_default='false',
                nullable=False,
            ),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                'auto_submitted',
                sa.Boolean(),
                server_default='false',
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ['task_id'],
                ['tasks.id'],
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['project_id'],
                ['projects.id'],
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['user_id'],
                ['users.id'],
                ondelete='CASCADE',
            ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('task_id', 'user_id', name='unique_timer_session'),
        )
        op.create_index('ix_timer_session_id', 'annotation_timer_sessions', ['id'])
        op.create_index('ix_timer_session_task_id', 'annotation_timer_sessions', ['task_id'])
        op.create_index('ix_timer_session_project_id', 'annotation_timer_sessions', ['project_id'])
        op.create_index('ix_timer_session_user_id', 'annotation_timer_sessions', ['user_id'])
        op.create_index(
            'ix_timer_session_project_user',
            'annotation_timer_sessions',
            ['project_id', 'user_id'],
        )

    # ============= Add strict_timer_enabled to projects =============
    if not column_exists('projects', 'strict_timer_enabled'):
        op.add_column(
            'projects',
            sa.Column(
                'strict_timer_enabled',
                sa.Boolean(),
                nullable=False,
                server_default='false',
            ),
        )

    # ============= Add auto_submitted to annotations =============
    if not column_exists('annotations', 'auto_submitted'):
        op.add_column(
            'annotations',
            sa.Column(
                'auto_submitted',
                sa.Boolean(),
                nullable=False,
                server_default='false',
            ),
        )


def downgrade() -> None:
    # Drop auto_submitted from annotations
    if column_exists('annotations', 'auto_submitted'):
        op.drop_column('annotations', 'auto_submitted')

    # Drop strict_timer_enabled from projects
    if column_exists('projects', 'strict_timer_enabled'):
        op.drop_column('projects', 'strict_timer_enabled')

    # Drop annotation_timer_sessions table
    if table_exists('annotation_timer_sessions'):
        if index_exists('annotation_timer_sessions', 'ix_timer_session_project_user'):
            op.drop_index(
                'ix_timer_session_project_user',
                table_name='annotation_timer_sessions',
            )
        if index_exists('annotation_timer_sessions', 'ix_timer_session_user_id'):
            op.drop_index(
                'ix_timer_session_user_id',
                table_name='annotation_timer_sessions',
            )
        if index_exists('annotation_timer_sessions', 'ix_timer_session_project_id'):
            op.drop_index(
                'ix_timer_session_project_id',
                table_name='annotation_timer_sessions',
            )
        if index_exists('annotation_timer_sessions', 'ix_timer_session_task_id'):
            op.drop_index(
                'ix_timer_session_task_id',
                table_name='annotation_timer_sessions',
            )
        if index_exists('annotation_timer_sessions', 'ix_timer_session_id'):
            op.drop_index('ix_timer_session_id', table_name='annotation_timer_sessions')
        op.drop_table('annotation_timer_sessions')
