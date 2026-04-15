"""Rename evaluation tables for clarity (Issue #1208)

Renames:
- evaluations -> evaluation_runs (project-level run records)
- evaluation_sample_results -> task_evaluations (per-task evaluation data)
- evaluation_metrics -> evaluation_run_metrics (per-run metric records)

Revision ID: 016_rename_evaluation_tables
Revises: 015_post_annotation_questionnaire
Create Date: 2026-02-21

"""

from sqlalchemy import inspect

from alembic import op

# revision identifiers
revision = "016_rename_evaluation_tables"
down_revision = "015_post_annotation_questionnaire"
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(index_name):
    """Check if an index exists in any table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    for table_name in inspector.get_table_names():
        indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
        if index_name in indexes:
            return True
    return False


def constraint_exists(table_name, constraint_name):
    """Check if a foreign key constraint exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    fks = inspector.get_foreign_keys(table_name)
    return any(fk['name'] == constraint_name for fk in fks)


def upgrade() -> None:
    # === 1. Rename tables ===
    if table_exists('evaluations') and not table_exists('evaluation_runs'):
        op.rename_table('evaluations', 'evaluation_runs')

    if table_exists('evaluation_sample_results') and not table_exists('task_evaluations'):
        op.rename_table('evaluation_sample_results', 'task_evaluations')

    if table_exists('evaluation_metrics') and not table_exists('evaluation_run_metrics'):
        op.rename_table('evaluation_metrics', 'evaluation_run_metrics')

    # === 2. Rename indexes on evaluation_runs (was evaluations) ===
    if index_exists('ix_evaluations_id'):
        op.drop_index('ix_evaluations_id', table_name='evaluation_runs')
        op.create_index('ix_evaluation_runs_id', 'evaluation_runs', ['id'])

    if index_exists('idx_evaluations_project_id'):
        op.drop_index('idx_evaluations_project_id', table_name='evaluation_runs')
        op.create_index('idx_evaluation_runs_project_id', 'evaluation_runs', ['project_id'])

    # === 3. Rename indexes on task_evaluations (was evaluation_sample_results) ===
    if index_exists('idx_evaluation_sample_results_eval_id'):
        op.drop_index('idx_evaluation_sample_results_eval_id', table_name='task_evaluations')
        op.create_index('idx_task_evaluations_eval_id', 'task_evaluations', ['evaluation_id'])

    if index_exists('idx_evaluation_sample_results_task_id'):
        op.drop_index('idx_evaluation_sample_results_task_id', table_name='task_evaluations')
        op.create_index('idx_task_evaluations_task_id', 'task_evaluations', ['task_id'])

    if index_exists('idx_evaluation_sample_results_field_name'):
        op.drop_index('idx_evaluation_sample_results_field_name', table_name='task_evaluations')
        op.create_index('idx_task_evaluations_field_name', 'task_evaluations', ['field_name'])

    if index_exists('idx_evaluation_sample_results_passed'):
        op.drop_index('idx_evaluation_sample_results_passed', table_name='task_evaluations')
        op.create_index('idx_task_evaluations_passed', 'task_evaluations', ['passed'])

    # === 4. Rename indexes on evaluation_run_metrics (was evaluation_metrics) ===
    if index_exists('ix_evaluation_metrics_id'):
        op.drop_index('ix_evaluation_metrics_id', table_name='evaluation_run_metrics')
        op.create_index('ix_evaluation_run_metrics_id', 'evaluation_run_metrics', ['id'])

    # === 5. Rename foreign key constraints ===
    # evaluation_run_metrics (was evaluation_metrics)
    if constraint_exists('evaluation_run_metrics', 'evaluation_metrics_evaluation_id_fkey'):
        op.drop_constraint('evaluation_metrics_evaluation_id_fkey', 'evaluation_run_metrics', type_='foreignkey')
        op.create_foreign_key(
            'evaluation_run_metrics_evaluation_id_fkey',
            'evaluation_run_metrics', 'evaluation_runs',
            ['evaluation_id'], ['id'],
        )

    if constraint_exists('evaluation_run_metrics', 'evaluation_metrics_evaluation_type_id_fkey'):
        op.drop_constraint('evaluation_metrics_evaluation_type_id_fkey', 'evaluation_run_metrics', type_='foreignkey')
        op.create_foreign_key(
            'evaluation_run_metrics_evaluation_type_id_fkey',
            'evaluation_run_metrics', 'evaluation_types',
            ['evaluation_type_id'], ['id'],
        )

    # task_evaluations (was evaluation_sample_results)
    if constraint_exists('task_evaluations', 'evaluation_sample_results_evaluation_id_fkey'):
        op.drop_constraint('evaluation_sample_results_evaluation_id_fkey', 'task_evaluations', type_='foreignkey')
        op.create_foreign_key(
            'task_evaluations_evaluation_id_fkey',
            'task_evaluations', 'evaluation_runs',
            ['evaluation_id'], ['id'],
            ondelete='CASCADE',
        )

    if constraint_exists('task_evaluations', 'evaluation_sample_results_generation_id_fkey'):
        op.drop_constraint('evaluation_sample_results_generation_id_fkey', 'task_evaluations', type_='foreignkey')
        op.create_foreign_key(
            'task_evaluations_generation_id_fkey',
            'task_evaluations', 'generations',
            ['generation_id'], ['id'],
            ondelete='SET NULL',
        )

    if constraint_exists('task_evaluations', 'evaluation_sample_results_task_id_fkey'):
        op.drop_constraint('evaluation_sample_results_task_id_fkey', 'task_evaluations', type_='foreignkey')
        op.create_foreign_key(
            'task_evaluations_task_id_fkey',
            'task_evaluations', 'tasks',
            ['task_id'], ['id'],
            ondelete='CASCADE',
        )

    # evaluation_runs FK to projects (was fk_evaluations_project_id)
    if constraint_exists('evaluation_runs', 'fk_evaluations_project_id'):
        op.drop_constraint('fk_evaluations_project_id', 'evaluation_runs', type_='foreignkey')
        op.create_foreign_key(
            'fk_evaluation_runs_project_id',
            'evaluation_runs', 'projects',
            ['project_id'], ['id'],
            ondelete='CASCADE',
        )


def downgrade() -> None:
    # === Reverse FK renames ===
    if constraint_exists('evaluation_runs', 'fk_evaluation_runs_project_id'):
        op.drop_constraint('fk_evaluation_runs_project_id', 'evaluation_runs', type_='foreignkey')
        op.create_foreign_key(
            'fk_evaluations_project_id',
            'evaluation_runs', 'projects',
            ['project_id'], ['id'],
            ondelete='CASCADE',
        )

    if constraint_exists('task_evaluations', 'task_evaluations_task_id_fkey'):
        op.drop_constraint('task_evaluations_task_id_fkey', 'task_evaluations', type_='foreignkey')
        op.create_foreign_key(
            'evaluation_sample_results_task_id_fkey',
            'task_evaluations', 'tasks',
            ['task_id'], ['id'],
            ondelete='CASCADE',
        )

    if constraint_exists('task_evaluations', 'task_evaluations_generation_id_fkey'):
        op.drop_constraint('task_evaluations_generation_id_fkey', 'task_evaluations', type_='foreignkey')
        op.create_foreign_key(
            'evaluation_sample_results_generation_id_fkey',
            'task_evaluations', 'generations',
            ['generation_id'], ['id'],
            ondelete='SET NULL',
        )

    if constraint_exists('task_evaluations', 'task_evaluations_evaluation_id_fkey'):
        op.drop_constraint('task_evaluations_evaluation_id_fkey', 'task_evaluations', type_='foreignkey')
        op.create_foreign_key(
            'evaluation_sample_results_evaluation_id_fkey',
            'task_evaluations', 'evaluation_runs',
            ['evaluation_id'], ['id'],
            ondelete='CASCADE',
        )

    if constraint_exists('evaluation_run_metrics', 'evaluation_run_metrics_evaluation_type_id_fkey'):
        op.drop_constraint('evaluation_run_metrics_evaluation_type_id_fkey', 'evaluation_run_metrics', type_='foreignkey')
        op.create_foreign_key(
            'evaluation_metrics_evaluation_type_id_fkey',
            'evaluation_run_metrics', 'evaluation_types',
            ['evaluation_type_id'], ['id'],
        )

    if constraint_exists('evaluation_run_metrics', 'evaluation_run_metrics_evaluation_id_fkey'):
        op.drop_constraint('evaluation_run_metrics_evaluation_id_fkey', 'evaluation_run_metrics', type_='foreignkey')
        op.create_foreign_key(
            'evaluation_metrics_evaluation_id_fkey',
            'evaluation_run_metrics', 'evaluation_runs',
            ['evaluation_id'], ['id'],
        )

    # === Reverse index renames ===
    if index_exists('ix_evaluation_run_metrics_id'):
        op.drop_index('ix_evaluation_run_metrics_id', table_name='evaluation_run_metrics')
        op.create_index('ix_evaluation_metrics_id', 'evaluation_run_metrics', ['id'])

    if index_exists('idx_task_evaluations_passed'):
        op.drop_index('idx_task_evaluations_passed', table_name='task_evaluations')
        op.create_index('idx_evaluation_sample_results_passed', 'task_evaluations', ['passed'])

    if index_exists('idx_task_evaluations_field_name'):
        op.drop_index('idx_task_evaluations_field_name', table_name='task_evaluations')
        op.create_index('idx_evaluation_sample_results_field_name', 'task_evaluations', ['field_name'])

    if index_exists('idx_task_evaluations_task_id'):
        op.drop_index('idx_task_evaluations_task_id', table_name='task_evaluations')
        op.create_index('idx_evaluation_sample_results_task_id', 'task_evaluations', ['task_id'])

    if index_exists('idx_task_evaluations_eval_id'):
        op.drop_index('idx_task_evaluations_eval_id', table_name='task_evaluations')
        op.create_index('idx_evaluation_sample_results_eval_id', 'task_evaluations', ['evaluation_id'])

    if index_exists('idx_evaluation_runs_project_id'):
        op.drop_index('idx_evaluation_runs_project_id', table_name='evaluation_runs')
        op.create_index('idx_evaluations_project_id', 'evaluation_runs', ['project_id'])

    if index_exists('ix_evaluation_runs_id'):
        op.drop_index('ix_evaluation_runs_id', table_name='evaluation_runs')
        op.create_index('ix_evaluations_id', 'evaluation_runs', ['id'])

    # === Reverse table renames ===
    if table_exists('evaluation_run_metrics') and not table_exists('evaluation_metrics'):
        op.rename_table('evaluation_run_metrics', 'evaluation_metrics')

    if table_exists('task_evaluations') and not table_exists('evaluation_sample_results'):
        op.rename_table('task_evaluations', 'evaluation_sample_results')

    if table_exists('evaluation_runs') and not table_exists('evaluations'):
        op.rename_table('evaluation_runs', 'evaluations')
