"""add flashcard_srs_settings table (per-user, per-collection daily limits)

Anki-style daily caps for student flashcards (issue #35). Each student paces
themselves on a (possibly shared) deck, so the caps live per-(user, project) —
mirroring the per-user SRS sidecar. ``new_per_day`` caps never-seen cards
introduced/day; ``review_per_day`` caps review cards shown/day (and also gates
new cards once spent, Anki-faithfully). NULL on either = use the system default
(resolved in routers/projects/srs.py), so a row only stores genuine overrides.

All FKs ``ondelete=CASCADE`` so a deleted user/project self-cleans. Unique
(user_id, project_id). Idempotent — guards on table/index existence; safe to
re-run. Mirrors the 065 create pattern.

Revision ID: 069_add_flashcard_srs_settings
Revises: 068_add_share_link_is_listed
Create Date: 2026-06-28
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "069_add_flashcard_srs_settings"
down_revision = "068_add_share_link_is_listed"
branch_labels = None
depends_on = None


TABLE_NAME = "flashcard_srs_settings"
INDEX_NAME = "ix_flashcard_srs_settings_user_project"


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table in insp.get_table_names()


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _table_exists(TABLE_NAME):
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("new_per_day", sa.Integer(), nullable=True),
            sa.Column("review_per_day", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "user_id",
                "project_id",
                name="uq_flashcard_srs_settings_user_project",
            ),
        )
    if not _index_exists(TABLE_NAME, INDEX_NAME):
        op.create_index(INDEX_NAME, TABLE_NAME, ["user_id", "project_id"])


def downgrade() -> None:
    if _table_exists(TABLE_NAME):
        op.drop_table(TABLE_NAME)
