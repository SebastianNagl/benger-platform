"""add korrektur_reservations (grader has a Korrektur target open)

One row per (user, metric, target): a grader has that annotation or
generation open in the grading modal right now. ``last_seen_at`` is
refreshed by a heartbeat; the row is deleted on submit or close and counts
as gone once the heartbeat stops for longer than the overlay's TTL.

Written by the extended edition, which uses it to keep a second grader away
from the last free slot of a target with a grader cap; the platform owns
the schema.

Idempotent: guards on table existence, safe to re-run.

Revision ID: 119_korrektur_reservations
Revises: 118_api_keys
Create Date: 2026-10-19
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "119_korrektur_reservations"
down_revision = "118_api_keys"
branch_labels = None
depends_on = None


TABLE_NAME = "korrektur_reservations"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if inspect(op.get_bind()).has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.String(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
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
        sa.UniqueConstraint(
            "user_id",
            "metric",
            "target_type",
            "target_id",
            name="uq_korrektur_reservation_user_target",
        ),
    )
    op.create_index("ix_korrektur_reservations_id", TABLE_NAME, ["id"])
    op.create_index(
        "ix_korrektur_reservations_project_metric",
        TABLE_NAME,
        ["project_id", "metric"],
    )
    op.create_index("ix_korrektur_reservations_task_id", TABLE_NAME, ["task_id"])


def downgrade() -> None:
    if inspect(op.get_bind()).has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)
