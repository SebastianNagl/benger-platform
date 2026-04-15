"""Add missing evaluation columns and project_reports table

This migration adds columns that existed in the squashed baseline but were
missing from production due to the migration history divergence.

Revision ID: 006_add_missing_evaluation_and_reports
Revises: 005_add_missing_project_columns
Create Date: 2026-02-05

"""
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = '006_eval_reports'
down_revision = '005_add_missing_project_columns'
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
    """Add missing evaluation columns and create project_reports table."""
    # ============= Evaluations table fixes =============

    # Add project_id column to evaluations
    if not column_exists('evaluations', 'project_id'):
        op.add_column('evaluations', sa.Column('project_id', sa.String(), nullable=True))
        # Add foreign key constraint
        op.create_foreign_key(
            'fk_evaluations_project_id',
            'evaluations',
            'projects',
            ['project_id'],
            ['id'],
            ondelete='CASCADE',
        )
        # Add index for project_id
        if not index_exists('ix_evaluations_project_id'):
            op.create_index('ix_evaluations_project_id', 'evaluations', ['project_id'])

    # Add has_sample_results column to evaluations
    if not column_exists('evaluations', 'has_sample_results'):
        op.add_column(
            'evaluations',
            sa.Column('has_sample_results', sa.Boolean(), nullable=True, server_default='false'),
        )

    # ============= Evaluation Sample Results table =============

    if not table_exists('evaluation_sample_results'):
        op.create_table(
            'evaluation_sample_results',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('evaluation_id', sa.String(), nullable=False),
            sa.Column('task_id', sa.String(), nullable=False),
            sa.Column('generation_id', sa.String(), nullable=True),
            sa.Column('field_results', JSONB(), nullable=True),
            sa.Column('overall_score', sa.Float(), nullable=True),
            sa.Column('passed', sa.Boolean(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('response_data', JSONB(), nullable=True),
            sa.Column('reference_data', JSONB(), nullable=True),
            sa.Column('eval_metadata', JSONB(), nullable=True),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['generation_id'], ['generations.id'], ondelete='SET NULL'),
        )
        op.create_index('ix_evaluation_sample_results_id', 'evaluation_sample_results', ['id'])
        op.create_index(
            'ix_evaluation_sample_results_evaluation_id',
            'evaluation_sample_results',
            ['evaluation_id'],
        )
        op.create_index(
            'ix_evaluation_sample_results_task_id', 'evaluation_sample_results', ['task_id']
        )

    # ============= Project Reports table =============

    if not table_exists('project_reports'):
        op.create_table(
            'project_reports',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('content', JSONB(), nullable=False),
            sa.Column('is_published', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('published_by', sa.String(), nullable=True),
            sa.Column('created_by', sa.String(), nullable=False),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['published_by'], ['users.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.UniqueConstraint('project_id', name='uq_project_reports_project_id'),
        )
        op.create_index('ix_project_reports_id', 'project_reports', ['id'])
        op.create_index('ix_project_reports_project_id', 'project_reports', ['project_id'])
        op.create_index('ix_project_reports_is_published', 'project_reports', ['is_published'])


def downgrade():
    """Remove the added columns and tables."""
    # Drop evaluation_sample_results table
    if table_exists('evaluation_sample_results'):
        op.drop_index(
            'ix_evaluation_sample_results_task_id', table_name='evaluation_sample_results'
        )
        op.drop_index(
            'ix_evaluation_sample_results_evaluation_id', table_name='evaluation_sample_results'
        )
        op.drop_index('ix_evaluation_sample_results_id', table_name='evaluation_sample_results')
        op.drop_table('evaluation_sample_results')

    # Drop project_reports table
    if table_exists('project_reports'):
        op.drop_index('ix_project_reports_is_published', table_name='project_reports')
        op.drop_index('ix_project_reports_project_id', table_name='project_reports')
        op.drop_index('ix_project_reports_id', table_name='project_reports')
        op.drop_table('project_reports')

    # Remove evaluations columns
    if column_exists('evaluations', 'has_sample_results'):
        op.drop_column('evaluations', 'has_sample_results')

    if column_exists('evaluations', 'project_id'):
        if index_exists('ix_evaluations_project_id'):
            op.drop_index('ix_evaluations_project_id', table_name='evaluations')
        op.drop_constraint('fk_evaluations_project_id', 'evaluations', type_='foreignkey')
        op.drop_column('evaluations', 'project_id')
