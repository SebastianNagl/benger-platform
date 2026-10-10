"""add task_work_presence (writing-page presence)

One row per (task, user): when the current working session on the task
started (``started_at``), when the writing page last reported in
(``last_seen_at``), whether its tab was in the foreground at that moment
(``visible``) and when the session ended by a submit (``ended_at``).

Written by the extended edition; the platform owns the schema. Only the
current state is kept; there is no history.

Idempotent: guards on table existence, safe to re-run.

Revision ID: 117_task_work_presence
Revises: 116_project_step_detail_after_submit
Create Date: 2026-10-09
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "117_task_work_presence"
down_revision = "116_project_step_detail_after_submit"
branch_labels = None
depends_on = None


TABLE_NAME = "task_work_presence"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if inspect(op.get_bind()).has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("task_id", "user_id", name="uq_task_work_presence_task_user"),
    )
    op.create_index(
        "ix_task_work_presence_project_seen",
        TABLE_NAME,
        ["project_id", "last_seen_at"],
    )
    op.create_index("ix_task_work_presence_user_id", TABLE_NAME, ["user_id"])


def downgrade() -> None:
    if inspect(op.get_bind()).has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)
