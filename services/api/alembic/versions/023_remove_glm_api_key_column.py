"""Remove encrypted_glm_api_key column from users table

GLM provider removed; GLM models now accessed via DeepInfra.

Revision ID: 023_remove_glm_api_key_column
Revises: 022_add_randomize_task_order
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = '023_remove_glm_api_key_column'
down_revision = '022_add_randomize_task_order'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if column_exists('users', 'encrypted_glm_api_key'):
        op.drop_column('users', 'encrypted_glm_api_key')


def downgrade():
    if not column_exists('users', 'encrypted_glm_api_key'):
        op.add_column('users', sa.Column('encrypted_glm_api_key', sa.Text(), nullable=True))
