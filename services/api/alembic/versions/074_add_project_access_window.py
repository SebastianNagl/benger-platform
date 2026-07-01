"""add projects.window_start_at / window_end_at (timed access window)

Project-level availability window (annotate / generate / evaluate). When both
timestamps are set, the project is only writable between them, and its task data
is hidden before ``window_start_at`` — for the *access group* only; owners and
org admins/contributors (anyone who can edit the project) are always exempt.
Both NULL ⇒ no window ⇒ always open (fully back-compatible).

Two nullable ``timestamptz`` columns, each indexed (so "not yet open" / "closed"
listing filters stay cheap), plus a check constraint enforcing
``window_end_at > window_start_at`` when both are present. The upcoming/open/
closed state is DERIVED at read time (see ``project_window_state`` in
``routers/projects/helpers.py``) — no persisted status column.

Idempotent — guards on column / index / constraint existence; safe to re-run.
Mirrors the 064 (two-nullable-columns + index) pattern.

Revision ID: 074_add_project_access_window
Revises: 073_add_draft_checkpoints
Create Date: 2026-07-01
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "074_add_project_access_window"
down_revision = "073_add_draft_checkpoints"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"
CONSTRAINT_NAME = "ck_projects_window_bounds"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def _check_constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {c["name"] for c in insp.get_check_constraints(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, "window_start_at"):
        op.add_column(
            TABLE_NAME,
            sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _column_exists(TABLE_NAME, "window_end_at"):
        op.add_column(
            TABLE_NAME,
            sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _index_exists(TABLE_NAME, "ix_projects_window_start_at"):
        op.create_index("ix_projects_window_start_at", TABLE_NAME, ["window_start_at"])
    if not _index_exists(TABLE_NAME, "ix_projects_window_end_at"):
        op.create_index("ix_projects_window_end_at", TABLE_NAME, ["window_end_at"])

    if not _check_constraint_exists(TABLE_NAME, CONSTRAINT_NAME):
        op.create_check_constraint(
            CONSTRAINT_NAME,
            TABLE_NAME,
            "window_start_at IS NULL OR window_end_at IS NULL "
            "OR window_end_at > window_start_at",
        )


def downgrade() -> None:
    if _check_constraint_exists(TABLE_NAME, CONSTRAINT_NAME):
        op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, type_="check")
    if _index_exists(TABLE_NAME, "ix_projects_window_end_at"):
        op.drop_index("ix_projects_window_end_at", table_name=TABLE_NAME)
    if _index_exists(TABLE_NAME, "ix_projects_window_start_at"):
        op.drop_index("ix_projects_window_start_at", table_name=TABLE_NAME)
    if _column_exists(TABLE_NAME, "window_end_at"):
        op.drop_column(TABLE_NAME, "window_end_at")
    if _column_exists(TABLE_NAME, "window_start_at"):
        op.drop_column(TABLE_NAME, "window_start_at")
