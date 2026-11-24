"""add korrektur_comments.highlight_field

A grader's highlight comment stored only character offsets, not the answer
field they belong to. A submission renders several fields (the case text,
the answer, notes), and the offsets alone were drawn in every one of them,
so a comment on the answer also showed at the same offsets in the case text.

``highlight_field`` is the label-config name of the field the passage was
marked in (e.g. ``loesung``). Nullable and without a default: comments
written before it stay NULL and readers fall back to the graded answer
field; general comments and replies never carry one.

Idempotent: guards on column existence, safe to re-run (091 pattern).

Revision ID: 153_korrektur_comment_highlight_field
Revises: 152_platform_flags_tum_rollout
Create Date: 2026-11-24
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "153_korrektur_comment_highlight_field"
down_revision = "152_platform_flags_tum_rollout"
branch_labels = None
depends_on = None


TABLE_NAME = "korrektur_comments"
COLUMN_NAME = "highlight_field"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.String(), nullable=True))


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
