"""Annotation original result: the author's answer before an in-place review.

A review that fixes an annotation replaces ``annotations.result`` in place.
``original_result`` (JSONB, nullable) keeps the author's result as it stood
before that first replacement, so the original answer is not lost and a
comparison of the two versions stays possible. Null for every existing row
and for every annotation no review has changed. The step is idempotent.

Revision ID: 159_annotation_original_result
Revises: 158_peer_review_grant
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "159_annotation_original_result"
down_revision = "158_peer_review_grant"
branch_labels = None
depends_on = None


TABLE_NAME = "annotations"
COLUMN_NAME = "original_result"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
