"""add response_generations pause/resume/retry lifecycle columns

The generation router (``services/api/routers/generation.py``) writes
``paused_at`` (pause endpoint), ``resumed_at`` (resume endpoint) and
reads-then-increments ``retry_count`` (retry endpoint) on the
``response_generations`` row. None of these were mapped columns, so the
attribute access fell through to the instance ``__dict__``: writes were
silently dropped at flush and — critically — the retry endpoint's
``generation.retry_count or 0`` READ raised ``AttributeError`` on a
freshly-loaded row, 500ing the retry endpoint on real production data.

This migration adds the columns the code's intent assumes: two nullable
timestamps (``paused_at``/``resumed_at``), a NOT NULL ``retry_count`` and a NOT
NULL ``dispatch_epoch`` (both default 0 so existing rows backfill cleanly).

``dispatch_epoch`` is bumped on every re-dispatch (resume/retry) so the
re-dispatched fan-out gets FRESH deterministic Celery ids
``{gen_id}:{run_idx}:{epoch}``. stop/pause/supersede revoke the CURRENT epoch
reconstructed from ``runs_requested`` + ``dispatch_epoch`` — no per-generation id
column needs storing. Reusing an id across a revoke would make Celery's
in-memory revoked set discard the re-dispatch (resume/retry would regenerate
nothing); the epoch makes the new ids un-revoked. Progress/completed counters are
DERIVED (the worker recomputes ``runs_completed``/``runs_failed`` from the child
Generation rows), so no extra progress columns are needed.

Idempotent — guards on column existence; safe to re-run.

Revision ID: 063_generation_pause_resume_retry
Revises: 062_annotator_full_visibility_after_submit
Create Date: 2026-06-21
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "063_generation_pause_resume_retry"
down_revision = "062_annotator_full_visibility_after_submit"
branch_labels = None
depends_on = None


TABLE_NAME = "response_generations"


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
    if not _column_exists(TABLE_NAME, "resumed_at"):
        op.add_column(
            TABLE_NAME,
            sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _column_exists(TABLE_NAME, "retry_count"):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if not _column_exists(TABLE_NAME, "dispatch_epoch"):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "dispatch_epoch",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, "dispatch_epoch"):
        op.drop_column(TABLE_NAME, "dispatch_epoch")
    if _column_exists(TABLE_NAME, "retry_count"):
        op.drop_column(TABLE_NAME, "retry_count")
    if _column_exists(TABLE_NAME, "resumed_at"):
        op.drop_column(TABLE_NAME, "resumed_at")
    if _column_exists(TABLE_NAME, "paused_at"):
        op.drop_column(TABLE_NAME, "paused_at")
