"""Add mandatory demographic & psychometric profile fields (Issue #1206)

Adds new columns to users table for:
- Gender enum
- Subjective competence (3 areas of law, Likert 1-7)
- Objective grades (conditional on legal expertise level)
- Psychometric scales (ATI-S, PTT-A, KI-Erfahrung as JSON)
- Mandatory profile completion tracking
- Profile confirmation tracking (half-yearly re-confirmation)

Creates user_profile_history table for research audit trails.

This migration is idempotent - it only adds columns/tables if they don't exist.

Revision ID: 012_mandatory_profile_fields
Revises: 011_add_strict_timer
Create Date: 2026-02-21

"""


import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = '012_mandatory_profile_fields'
down_revision = '011_add_strict_timer'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [col['name'] for col in insp.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def index_exists(table_name, index_name):
    """Check if an index exists on a table."""
    bind = op.get_bind()
    insp = inspect(bind)
    indexes = [idx['name'] for idx in insp.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    # ============= Gender =============
    if not column_exists('users', 'gender'):
        op.add_column('users', sa.Column('gender', sa.String(20), nullable=True))

    # ============= Subjective competence (Likert 1-7) =============
    if not column_exists('users', 'subjective_competence_civil'):
        op.add_column(
            'users', sa.Column('subjective_competence_civil', sa.Integer(), nullable=True)
        )
    if not column_exists('users', 'subjective_competence_public'):
        op.add_column(
            'users', sa.Column('subjective_competence_public', sa.Integer(), nullable=True)
        )
    if not column_exists('users', 'subjective_competence_criminal'):
        op.add_column(
            'users', sa.Column('subjective_competence_criminal', sa.Integer(), nullable=True)
        )

    # ============= Objective grades (conditional on expertise level) =============
    if not column_exists('users', 'grade_zwischenpruefung'):
        op.add_column('users', sa.Column('grade_zwischenpruefung', sa.Float(), nullable=True))
    if not column_exists('users', 'grade_vorgeruecktenubung'):
        op.add_column('users', sa.Column('grade_vorgeruecktenubung', sa.Float(), nullable=True))
    if not column_exists('users', 'grade_first_staatsexamen'):
        op.add_column('users', sa.Column('grade_first_staatsexamen', sa.Float(), nullable=True))
    if not column_exists('users', 'grade_second_staatsexamen'):
        op.add_column('users', sa.Column('grade_second_staatsexamen', sa.Float(), nullable=True))

    # ============= Psychometric scales (JSON) =============
    if not column_exists('users', 'ati_s_scores'):
        op.add_column('users', sa.Column('ati_s_scores', sa.JSON(), nullable=True))
    if not column_exists('users', 'ptt_a_scores'):
        op.add_column('users', sa.Column('ptt_a_scores', sa.JSON(), nullable=True))
    if not column_exists('users', 'ki_experience_scores'):
        op.add_column('users', sa.Column('ki_experience_scores', sa.JSON(), nullable=True))

    # ============= Mandatory profile tracking =============
    if not column_exists('users', 'mandatory_profile_completed'):
        op.add_column(
            'users',
            sa.Column(
                'mandatory_profile_completed',
                sa.Boolean(),
                nullable=False,
                server_default='false',
            ),
        )
    if not column_exists('users', 'profile_confirmed_at'):
        op.add_column(
            'users',
            sa.Column('profile_confirmed_at', sa.DateTime(timezone=True), nullable=True),
        )

    # ============= Create user_profile_history table =============
    if not table_exists('user_profile_history'):
        op.create_table(
            'user_profile_history',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column(
                'changed_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
            sa.Column('change_type', sa.String(50), nullable=False),
            sa.Column('snapshot', sa.JSON(), nullable=False),
            sa.Column('changed_fields', sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_profile_history_id', 'user_profile_history', ['id'])
        op.create_index('ix_profile_history_user_id', 'user_profile_history', ['user_id'])
        op.create_index('ix_profile_history_changed_at', 'user_profile_history', ['changed_at'])


def downgrade() -> None:
    # Drop user_profile_history table
    if table_exists('user_profile_history'):
        if index_exists('user_profile_history', 'ix_profile_history_changed_at'):
            op.drop_index('ix_profile_history_changed_at', table_name='user_profile_history')
        if index_exists('user_profile_history', 'ix_profile_history_user_id'):
            op.drop_index('ix_profile_history_user_id', table_name='user_profile_history')
        if index_exists('user_profile_history', 'ix_profile_history_id'):
            op.drop_index('ix_profile_history_id', table_name='user_profile_history')
        op.drop_table('user_profile_history')

    # Drop mandatory profile tracking columns
    if column_exists('users', 'profile_confirmed_at'):
        op.drop_column('users', 'profile_confirmed_at')
    if column_exists('users', 'mandatory_profile_completed'):
        op.drop_column('users', 'mandatory_profile_completed')

    # Drop psychometric scales
    if column_exists('users', 'ki_experience_scores'):
        op.drop_column('users', 'ki_experience_scores')
    if column_exists('users', 'ptt_a_scores'):
        op.drop_column('users', 'ptt_a_scores')
    if column_exists('users', 'ati_s_scores'):
        op.drop_column('users', 'ati_s_scores')

    # Drop objective grades
    if column_exists('users', 'grade_second_staatsexamen'):
        op.drop_column('users', 'grade_second_staatsexamen')
    if column_exists('users', 'grade_first_staatsexamen'):
        op.drop_column('users', 'grade_first_staatsexamen')
    if column_exists('users', 'grade_vorgeruecktenubung'):
        op.drop_column('users', 'grade_vorgeruecktenubung')
    if column_exists('users', 'grade_zwischenpruefung'):
        op.drop_column('users', 'grade_zwischenpruefung')

    # Drop subjective competence
    if column_exists('users', 'subjective_competence_criminal'):
        op.drop_column('users', 'subjective_competence_criminal')
    if column_exists('users', 'subjective_competence_public'):
        op.drop_column('users', 'subjective_competence_public')
    if column_exists('users', 'subjective_competence_civil'):
        op.drop_column('users', 'subjective_competence_civil')

    # Drop gender
    if column_exists('users', 'gender'):
        op.drop_column('users', 'gender')
