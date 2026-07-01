"""add project_share_links.is_listed

Discoverable shared exams & decks (issue #35). Opt-in flag that surfaces a
password-protected share in the global discovery directory so other students can
find it and join with the password. Owners who only paste the link out-of-band
leave it false.

NOT NULL with a ``false`` server default so existing links default to
not-listed. Indexed because the discovery query filters on it.

Idempotent — guards on column existence; safe to re-run. Mirrors the 067 guard
pattern.

Revision ID: 068_add_share_link_is_listed
Revises: 067_add_user_preferred_ui_mode
Create Date: 2026-06-27
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "068_add_share_link_is_listed"
down_revision = "067_add_user_preferred_ui_mode"
branch_labels = None
depends_on = None


TABLE_NAME = "project_share_links"
COLUMN_NAME = "is_listed"
INDEX_NAME = "ix_project_share_links_is_listed"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return index in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                COLUMN_NAME,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    if not _index_exists(TABLE_NAME, INDEX_NAME):
        op.create_index(INDEX_NAME, TABLE_NAME, [COLUMN_NAME])


def downgrade() -> None:
    if _index_exists(TABLE_NAME, INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
