"""Add missing user columns from baseline squash

This migration adds columns that existed in the squashed baseline but were
missing from production due to the migration history divergence.

For fresh installs (which run baseline), these columns already exist.
For production (which had old migrations), these columns were missing.
This migration is idempotent - it only adds columns if they don't exist.

Revision ID: 004_add_missing_user_columns
Revises: 003_add_allow_self_review
Create Date: 2026-02-05

"""
import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = '004_add_missing_user_columns'
down_revision = '003_add_allow_self_review'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(table_name, index_name):
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade():
    """Add columns that were in baseline but missing from production.

    These columns were added incrementally in dev but squashed into baseline.
    Production skipped them when alembic_version was set to 001_complete_baseline.

    This migration is idempotent for fresh installs where baseline already added these.
    """
    # User pseudonymization
    if not column_exists('users', 'pseudonym'):
        op.add_column('users', sa.Column('pseudonym', sa.String(100), nullable=True))
    if not column_exists('users', 'use_pseudonym'):
        op.add_column(
            'users',
            sa.Column('use_pseudonym', sa.Boolean(), nullable=False, server_default='false'),
        )

    # Additional LLM API keys
    if not column_exists('users', 'encrypted_glm_api_key'):
        op.add_column('users', sa.Column('encrypted_glm_api_key', sa.Text(), nullable=True))
    if not column_exists('users', 'encrypted_grok_api_key'):
        op.add_column('users', sa.Column('encrypted_grok_api_key', sa.Text(), nullable=True))
    if not column_exists('users', 'encrypted_mistral_api_key'):
        op.add_column('users', sa.Column('encrypted_mistral_api_key', sa.Text(), nullable=True))
    if not column_exists('users', 'encrypted_cohere_api_key'):
        op.add_column('users', sa.Column('encrypted_cohere_api_key', sa.Text(), nullable=True))

    # Extended user profile fields
    if not column_exists('users', 'german_proficiency'):
        op.add_column('users', sa.Column('german_proficiency', sa.String(50), nullable=True))
    if not column_exists('users', 'degree_program_type'):
        op.add_column('users', sa.Column('degree_program_type', sa.String(50), nullable=True))
    if not column_exists('users', 'current_semester'):
        op.add_column('users', sa.Column('current_semester', sa.Integer(), nullable=True))
    if not column_exists('users', 'legal_specializations'):
        op.add_column('users', sa.Column('legal_specializations', sa.JSON(), nullable=True))

    # Create unique index for pseudonyms (if not exists)
    if not index_exists('users', 'ix_users_pseudonym'):
        op.create_index('ix_users_pseudonym', 'users', ['pseudonym'], unique=True)


def downgrade():
    """Remove the added columns."""
    if index_exists('users', 'ix_users_pseudonym'):
        op.drop_index('ix_users_pseudonym', table_name='users')
    if column_exists('users', 'legal_specializations'):
        op.drop_column('users', 'legal_specializations')
    if column_exists('users', 'current_semester'):
        op.drop_column('users', 'current_semester')
    if column_exists('users', 'degree_program_type'):
        op.drop_column('users', 'degree_program_type')
    if column_exists('users', 'german_proficiency'):
        op.drop_column('users', 'german_proficiency')
    if column_exists('users', 'encrypted_cohere_api_key'):
        op.drop_column('users', 'encrypted_cohere_api_key')
    if column_exists('users', 'encrypted_mistral_api_key'):
        op.drop_column('users', 'encrypted_mistral_api_key')
    if column_exists('users', 'encrypted_grok_api_key'):
        op.drop_column('users', 'encrypted_grok_api_key')
    if column_exists('users', 'encrypted_glm_api_key'):
        op.drop_column('users', 'encrypted_glm_api_key')
    if column_exists('users', 'use_pseudonym'):
        op.drop_column('users', 'use_pseudonym')
    if column_exists('users', 'pseudonym'):
        op.drop_column('users', 'pseudonym')
