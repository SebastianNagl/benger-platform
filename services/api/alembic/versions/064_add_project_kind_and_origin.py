"""add projects.kind and projects.origin

Student exam-training experience (issue #35). Two free-form nullable strings —
deliberately NOT Postgres ENUMs — so the community edition ships a
forward-compatible schema and an extended overlay can introduce new kinds
without an ``ALTER TYPE``:

- ``kind``: "exam" / "flashcard_deck" / NULL (plain benchmark project).
- ``origin``: "student" / NULL — marks student-generated projects so they can
  be excluded from public leaderboards while staying benchmarkable in the
  expert view.

Both indexed (filtered listing + leaderboard-exclusion joins). Write-once at
project creation (accepted in ProjectCreate, omitted from ProjectUpdate).

Idempotent — guards on column/index existence; safe to re-run. Mirrors the 062
guard pattern.

Revision ID: 064_add_project_kind_and_origin
Revises: 063_generation_pause_resume_retry
Create Date: 2026-06-25
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "064_add_project_kind_and_origin"
down_revision = "063_generation_pause_resume_retry"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, "kind"):
        op.add_column(TABLE_NAME, sa.Column("kind", sa.String(length=32), nullable=True))
    if not _column_exists(TABLE_NAME, "origin"):
        op.add_column(TABLE_NAME, sa.Column("origin", sa.String(length=32), nullable=True))

    if not _index_exists(TABLE_NAME, "ix_projects_kind"):
        op.create_index("ix_projects_kind", TABLE_NAME, ["kind"])
    if not _index_exists(TABLE_NAME, "ix_projects_origin"):
        op.create_index("ix_projects_origin", TABLE_NAME, ["origin"])


def downgrade() -> None:
    if _index_exists(TABLE_NAME, "ix_projects_origin"):
        op.drop_index("ix_projects_origin", table_name=TABLE_NAME)
    if _index_exists(TABLE_NAME, "ix_projects_kind"):
        op.drop_index("ix_projects_kind", table_name=TABLE_NAME)
    if _column_exists(TABLE_NAME, "origin"):
        op.drop_column(TABLE_NAME, "origin")
    if _column_exists(TABLE_NAME, "kind"):
        op.drop_column(TABLE_NAME, "kind")
