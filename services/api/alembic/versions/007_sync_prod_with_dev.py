"""Sync production schema with development

This migration adds missing tables and columns to production to match
the development schema. It only adds - never removes - to preserve data.

Revision ID: 007_sync_prod_dev
Revises: 006_eval_reports
Create Date: 2026-02-05

"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = '007_sync_prod_dev'
down_revision = '006_eval_reports'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(index_name):
    """Check if an index exists."""
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :name"), {"name": index_name}
    )
    return result.fetchone() is not None


def upgrade():
    """Add missing tables and columns to match dev schema."""

    # ============= Create skipped_tasks table =============
    if not table_exists('skipped_tasks'):
        op.create_table(
            'skipped_tasks',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('task_id', sa.String(), nullable=False),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('skipped_by', sa.String(), nullable=False),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column(
                'skipped_at',
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['skipped_by'], ['users.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_skipped_tasks_id', 'skipped_tasks', ['id'])
        op.create_index('ix_skipped_tasks_task_id', 'skipped_tasks', ['task_id'])
        op.create_index('ix_skipped_tasks_project_id', 'skipped_tasks', ['project_id'])
        op.create_index('ix_skipped_tasks_skipped_by', 'skipped_tasks', ['skipped_by'])

    # ============= Add missing columns to evaluation_sample_results =============
    # Dev has these columns that prod is missing
    if not column_exists('evaluation_sample_results', 'field_name'):
        op.add_column(
            'evaluation_sample_results', sa.Column('field_name', sa.String(), nullable=True)
        )

    if not column_exists('evaluation_sample_results', 'answer_type'):
        op.add_column(
            'evaluation_sample_results', sa.Column('answer_type', sa.String(), nullable=True)
        )

    if not column_exists('evaluation_sample_results', 'ground_truth'):
        op.add_column(
            'evaluation_sample_results', sa.Column('ground_truth', JSONB(), nullable=True)
        )

    if not column_exists('evaluation_sample_results', 'prediction'):
        op.add_column('evaluation_sample_results', sa.Column('prediction', JSONB(), nullable=True))

    if not column_exists('evaluation_sample_results', 'metrics'):
        op.add_column('evaluation_sample_results', sa.Column('metrics', JSONB(), nullable=True))

    if not column_exists('evaluation_sample_results', 'confidence_score'):
        op.add_column(
            'evaluation_sample_results', sa.Column('confidence_score', sa.Float(), nullable=True)
        )

    if not column_exists('evaluation_sample_results', 'processing_time_ms'):
        op.add_column(
            'evaluation_sample_results',
            sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        )

    # ============= Add missing columns to generations =============
    if not column_exists('generations', 'parsed_annotation'):
        op.add_column('generations', sa.Column('parsed_annotation', JSONB(), nullable=True))

    if not column_exists('generations', 'parse_status'):
        op.add_column('generations', sa.Column('parse_status', sa.String(), nullable=True))

    if not column_exists('generations', 'parse_error'):
        op.add_column('generations', sa.Column('parse_error', sa.Text(), nullable=True))

    if not column_exists('generations', 'parse_metadata'):
        op.add_column('generations', sa.Column('parse_metadata', sa.JSON(), nullable=True))

    if not column_exists('generations', 'label_config_version'):
        op.add_column(
            'generations', sa.Column('label_config_version', sa.String(50), nullable=True)
        )

    if not column_exists('generations', 'label_config_snapshot'):
        op.add_column('generations', sa.Column('label_config_snapshot', sa.Text(), nullable=True))

    # ============= Add missing column to llm_models =============
    if not column_exists('llm_models', 'parameter_constraints'):
        op.add_column('llm_models', sa.Column('parameter_constraints', JSONB(), nullable=True))

    # ============= Add missing column to response_generations =============
    if not column_exists('response_generations', 'structure_key'):
        op.add_column(
            'response_generations', sa.Column('structure_key', sa.String(), nullable=True)
        )


def downgrade():
    """Remove added tables and columns (use with caution)."""
    # Remove response_generations column
    if column_exists('response_generations', 'structure_key'):
        op.drop_column('response_generations', 'structure_key')

    # Remove llm_models column
    if column_exists('llm_models', 'parameter_constraints'):
        op.drop_column('llm_models', 'parameter_constraints')

    # Remove generations columns
    for col in [
        'label_config_snapshot',
        'label_config_version',
        'parse_metadata',
        'parse_error',
        'parse_status',
        'parsed_annotation',
    ]:
        if column_exists('generations', col):
            op.drop_column('generations', col)

    # Remove evaluation_sample_results columns
    for col in [
        'processing_time_ms',
        'confidence_score',
        'metrics',
        'prediction',
        'ground_truth',
        'answer_type',
        'field_name',
    ]:
        if column_exists('evaluation_sample_results', col):
            op.drop_column('evaluation_sample_results', col)

    # Drop skipped_tasks table
    if table_exists('skipped_tasks'):
        op.drop_index('ix_skipped_tasks_skipped_by', table_name='skipped_tasks')
        op.drop_index('ix_skipped_tasks_project_id', table_name='skipped_tasks')
        op.drop_index('ix_skipped_tasks_task_id', table_name='skipped_tasks')
        op.drop_index('ix_skipped_tasks_id', table_name='skipped_tasks')
        op.drop_table('skipped_tasks')
