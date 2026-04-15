"""Add review settings to projects and annotations

Revision ID: 002_add_review_settings
Revises: 001_complete_baseline
Create Date: 2026-02-04

Adds project-level review configuration and annotation-level review data:
- review_enabled: Whether review stage is active for the project
- review_mode: Type of review (in_place, independent, both)
- review_annotation: Reviewer's independent annotation (JSONB)
- review_comment: Reviewer's feedback text
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '002_add_review_settings'
down_revision: Union[str, None] = '001_complete_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add review settings to projects table
    op.add_column(
        'projects',
        sa.Column('review_enabled', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'projects', sa.Column('review_mode', sa.String(), nullable=False, server_default='in_place')
    )

    # Add review data to annotations table
    op.add_column('annotations', sa.Column('review_annotation', postgresql.JSONB(), nullable=True))
    op.add_column('annotations', sa.Column('review_comment', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('annotations', 'review_comment')
    op.drop_column('annotations', 'review_annotation')
    op.drop_column('projects', 'review_mode')
    op.drop_column('projects', 'review_enabled')
