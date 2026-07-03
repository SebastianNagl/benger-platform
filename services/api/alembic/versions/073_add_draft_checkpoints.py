"""add restorable draft checkpoints (opt-in)

Adds an opt-in safety net for in-progress annotation work:

- Two ``projects`` flags: ``restorable_checkpoints_enabled`` (off by default)
  and ``checkpoint_interval_seconds`` (default 300 = 5 min).
- ``task_draft_checkpoints``: an APPEND-ONLY history of draft snapshots, one
  row per checkpoint. Unlike ``task_drafts`` (single overwrite-in-place row,
  deleted on submit) this has NO unique (task_id,user_id) constraint, carries a
  ``created_at``, and is never deleted on submit — so an annotator can restore
  an earlier checkpoint.

Idempotent — guards on table/column/index existence; safe to re-run.

Revision ID: 073_add_draft_checkpoints
Revises: 072_add_marketplace_human_grading
Create Date: 2026-06-30
"""

from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op
import sqlalchemy as sa


revision = "073_add_draft_checkpoints"
down_revision = "072_add_marketplace_human_grading"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    insp = inspect(op.get_bind())
    return table in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if not _column_exists(table, column.name):
        op.add_column(table, column)


def upgrade() -> None:
    # --- project opt-in flags ------------------------------------------------ #
    _add_column_if_missing(
        "projects",
        sa.Column(
            "restorable_checkpoints_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    _add_column_if_missing(
        "projects",
        sa.Column(
            "checkpoint_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
    )

    # --- append-only checkpoint history table -------------------------------- #
    if not _table_exists("task_draft_checkpoints"):
        op.create_table(
            "task_draft_checkpoints",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "task_id",
                sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("draft_result", JSONB, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if not _index_exists(
        "task_draft_checkpoints", "ix_task_draft_checkpoints_task_user_created"
    ):
        op.create_index(
            "ix_task_draft_checkpoints_task_user_created",
            "task_draft_checkpoints",
            ["task_id", "user_id", "created_at"],
        )


def downgrade() -> None:
    if _index_exists(
        "task_draft_checkpoints", "ix_task_draft_checkpoints_task_user_created"
    ):
        op.drop_index(
            "ix_task_draft_checkpoints_task_user_created",
            table_name="task_draft_checkpoints",
        )
    if _table_exists("task_draft_checkpoints"):
        op.drop_table("task_draft_checkpoints")
    if _column_exists("projects", "checkpoint_interval_seconds"):
        op.drop_column("projects", "checkpoint_interval_seconds")
    if _column_exists("projects", "restorable_checkpoints_enabled"):
        op.drop_column("projects", "restorable_checkpoints_enabled")
