"""Add projects.icon — a user-chosen emoji shown in lists, headers and the
discover directory.

Nullable, short (emoji sequences are at most a handful of code points);
no default so existing rows keep rendering their kind-derived fallback icon.

Revision ID: 092_add_project_icon
Revises: 091_add_user_exam_layout_prefs
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "092_add_project_icon"
down_revision = "091_add_user_exam_layout_prefs"
branch_labels = None
depends_on = None

TABLE_NAME = "projects"
COLUMN_NAME = "icon"


def _has_column() -> bool:
    inspector = inspect(op.get_bind())
    return any(c["name"] == COLUMN_NAME for c in inspector.get_columns(TABLE_NAME))


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.String(length=16), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE_NAME, COLUMN_NAME)
