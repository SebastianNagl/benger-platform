"""grading_usage_events: tier/model audit columns + race-safe weekly free slot

The vertretbar grading model moves from "3 free lifetime, then €2 each" to
tiered: non-subscribers grade free on the base judge model, subscribers get
one free grading per calendar week (Europe/Berlin) on the premium model and
pay €1 per further grading. Schema is platform-owned; the tier decision and
metering logic live in ``benger_extended``.

- ``tier`` / ``judge_model``: audit columns — which tier priced the event and
  which judge model actually graded it.
- ``free_week_start``: the Monday (Berlin local date) whose weekly free slot
  this event consumed; NULL for everything else. The partial-by-NULL unique
  index ``uq_grading_usage_weekly_free (user_id, free_week_start)`` makes the
  weekly claim race-safe: the INSERT itself arbitrates concurrent claims
  (Postgres treats NULLs as distinct, so non-claiming rows never collide).
  A failed grading is voided and its ``free_week_start`` cleared, releasing
  the slot for a retry.
- Price defaults drop 200 -> 100 (both tables); existing informational
  ``per_grading_price_cents`` rows are backfilled 200 -> 100 (the charged
  amount is read from env at record time, not from these columns).

Idempotent — guards on column/index existence; safe to re-run.

Revision ID: 077_grading_usage_weekly_tiering
Revises: 076_add_timer_pause_fields
Create Date: 2026-07-13
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "077_grading_usage_weekly_tiering"
down_revision = "076_add_timer_pause_fields"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _column_exists("grading_usage_events", "tier"):
        op.add_column(
            "grading_usage_events", sa.Column("tier", sa.String(), nullable=True)
        )
    if not _column_exists("grading_usage_events", "judge_model"):
        op.add_column(
            "grading_usage_events", sa.Column("judge_model", sa.String(), nullable=True)
        )
    if not _column_exists("grading_usage_events", "free_week_start"):
        op.add_column(
            "grading_usage_events", sa.Column("free_week_start", sa.Date(), nullable=True)
        )
    if not _index_exists("grading_usage_events", "uq_grading_usage_weekly_free"):
        op.create_index(
            "uq_grading_usage_weekly_free",
            "grading_usage_events",
            ["user_id", "free_week_start"],
            unique=True,
        )

    op.alter_column("grading_usage_events", "unit_price_cents", server_default="100")
    op.alter_column(
        "student_subscriptions", "per_grading_price_cents", server_default="100"
    )
    op.execute(
        "UPDATE student_subscriptions SET per_grading_price_cents = 100 "
        "WHERE per_grading_price_cents = 200"
    )


def downgrade() -> None:
    op.alter_column("grading_usage_events", "unit_price_cents", server_default="200")
    op.alter_column(
        "student_subscriptions", "per_grading_price_cents", server_default="200"
    )
    if _index_exists("grading_usage_events", "uq_grading_usage_weekly_free"):
        op.drop_index("uq_grading_usage_weekly_free", table_name="grading_usage_events")
    for column in ("free_week_start", "judge_model", "tier"):
        if _column_exists("grading_usage_events", column):
            op.drop_column("grading_usage_events", column)
