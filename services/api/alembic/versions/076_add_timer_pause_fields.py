"""add pause fields to timer_sessions (non-strict pause/resume)

Non-strict timed annotation gets a real pause/resume (the extended timer
router provides the endpoints; strict sessions can never pause):

- ``paused_at``: open pause marker (NULL = clock running). Set by pause,
  cleared by resume.
- ``total_paused_seconds``: accumulated duration of completed pauses.

Effective elapsed time everywhere becomes
``(now - started_at) - total_paused_seconds - (now - paused_at if paused)``.
The strict Celery auto-submit eta (``started_at + time_limit_seconds``)
stays exact without rescheduling because strict sessions reject pause.

Idempotent — guards on column existence.

Revision ID: 076_add_timer_pause_fields
Revises: 075_default_checkpoints_enabled
Create Date: 2026-07-13
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "076_add_timer_pause_fields"
down_revision = "075_default_checkpoints_enabled"
branch_labels = None
depends_on = None


TABLE_NAME = "timer_sessions"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, "paused_at"):
        op.add_column(
            TABLE_NAME,
            sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _column_exists(TABLE_NAME, "total_paused_seconds"):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "total_paused_seconds",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, "total_paused_seconds"):
        op.drop_column(TABLE_NAME, "total_paused_seconds")
    if _column_exists(TABLE_NAME, "paused_at"):
        op.drop_column(TABLE_NAME, "paused_at")
