"""Add organization-level API key management (Issue #1180)

Creates organization_api_keys table for storing encrypted API keys at the
org level. Adds organization_id to response_generations for tracking which
org context a generation was dispatched from. Inserts ORG_API_KEYS feature flag.

Revision ID: 010_add_org_api_keys
Revises: 009_add_private_projects
Create Date: 2026-02-12

"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op

# revision identifiers, used by Alembic.
revision = '010_add_org_api_keys'
down_revision = '009_add_private_projects'
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
    # ============= Create organization_api_keys table =============
    if not table_exists('organization_api_keys'):
        op.create_table(
            'organization_api_keys',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('organization_id', sa.String(), nullable=False),
            sa.Column('provider', sa.String(), nullable=False),
            sa.Column('encrypted_key', sa.Text(), nullable=False),
            sa.Column('created_by', sa.String(), nullable=False),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ['organization_id'],
                ['organizations.id'],
                ondelete='CASCADE',
            ),
            sa.ForeignKeyConstraint(
                ['created_by'],
                ['users.id'],
            ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('organization_id', 'provider', name='unique_org_provider_key'),
        )
        op.create_index('ix_org_api_keys_id', 'organization_api_keys', ['id'], unique=False)
        op.create_index('ix_org_api_keys_org_id', 'organization_api_keys', ['organization_id'])

    # ============= Add organization_id to response_generations =============
    if not column_exists('response_generations', 'organization_id'):
        op.add_column(
            'response_generations',
            sa.Column('organization_id', sa.String(), nullable=True),
        )

    if not index_exists('response_generations', 'ix_response_gen_org_id'):
        op.create_index(
            'ix_response_gen_org_id',
            'response_generations',
            ['organization_id'],
        )

    # ============= Insert ORG_API_KEYS feature flag =============
    conn = op.get_bind()
    result = conn.execute(text("SELECT id FROM feature_flags WHERE name = 'ORG_API_KEYS'"))
    if result.fetchone() is None:
        # Get the first superadmin user ID for created_by (required NOT NULL)
        admin_result = conn.execute(text("SELECT id FROM users WHERE is_superadmin = true LIMIT 1"))
        admin_row = admin_result.fetchone()
        if admin_row is not None:
            admin_id = admin_row[0]
            conn.execute(
                text(
                    "INSERT INTO feature_flags (id, name, description, is_enabled, created_by, created_at) "
                    "VALUES (:id, :name, :description, :is_enabled, :created_by, :created_at)"
                ),
                {
                    'id': str(uuid.uuid4()),
                    'name': 'ORG_API_KEYS',
                    'description': 'Organization-level API key management. When enabled, org admins can configure shared API keys for their organization.',
                    'is_enabled': False,
                    'created_by': admin_id,
                    'created_at': datetime.now(timezone.utc),
                },
            )
        # If no admin user exists (fresh DB), skip - init_complete.py will create feature flags


def downgrade() -> None:
    # Remove feature flag
    conn = op.get_bind()
    conn.execute(text("DELETE FROM feature_flags WHERE name = 'ORG_API_KEYS'"))

    # Drop index and column from response_generations
    if index_exists('response_generations', 'ix_response_gen_org_id'):
        op.drop_index('ix_response_gen_org_id', table_name='response_generations')

    if column_exists('response_generations', 'organization_id'):
        op.drop_column('response_generations', 'organization_id')

    # Drop organization_api_keys table
    if table_exists('organization_api_keys'):
        op.drop_index('ix_org_api_keys_org_id', table_name='organization_api_keys')
        op.drop_index('ix_org_api_keys_id', table_name='organization_api_keys')
        op.drop_table('organization_api_keys')
