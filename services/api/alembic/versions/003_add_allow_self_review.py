"""Add allow_self_review setting to projects

Revision ID: 003_add_allow_self_review
Revises: 002_add_review_settings
Create Date: 2026-02-04

Adds allow_self_review flag so project admins can optionally permit
reviewers to review their own annotations.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '003_add_allow_self_review'
down_revision: Union[str, None] = '002_add_review_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('allow_self_review', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('projects', 'allow_self_review')
