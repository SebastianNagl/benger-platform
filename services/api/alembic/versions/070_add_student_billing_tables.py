"""add student_subscriptions and grading_usage_events tables

Vertretbar student billing (subscriptions + metered AI exam grading). The
schema is platform-owned; the proprietary subscription state machine, Stripe
orchestration and metering decisions live in ``benger_extended``.

- ``student_subscriptions``: one row per user (unique ``user_id``). Provider-
  agnostic ``status`` and ``provider_*`` columns so a Merchant-of-Record could
  replace Stripe without a migration.
- ``grading_usage_events``: the authoritative metered ledger. Unique
  ``evaluation_run_id`` is the idempotency key — a re-dispatched / re-polled
  grading can never be double-billed. ``status`` covers the lifecycle
  (pending -> billable -> reported, or void / free).

FKs to users use ``ondelete=CASCADE`` (right-to-erasure self-cleans a deleted
user's billing rows); ``subscription_id`` / ``project_id`` use ``SET NULL`` so
the ledger survives the parent.

Idempotent — guards on table/index existence; safe to re-run.

Revision ID: 070_add_student_billing_tables
Revises: 069_add_flashcard_srs_settings
Create Date: 2026-06-28
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "070_add_student_billing_tables"
down_revision = "069_add_flashcard_srs_settings"
branch_labels = None
depends_on = None


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


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    if not _table_exists("student_subscriptions"):
        op.create_table(
            "student_subscriptions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("provider", sa.String(), nullable=False, server_default="stripe"),
            sa.Column("provider_customer_id", sa.String(), nullable=True),
            sa.Column("provider_subscription_id", sa.String(), nullable=True),
            sa.Column("provider_metered_item_id", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="incomplete"),
            sa.Column("base_price_cents", sa.Integer(), nullable=False, server_default="500"),
            sa.Column(
                "per_grading_price_cents", sa.Integer(), nullable=False, server_default="200"
            ),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="eur"),
            sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "cancel_at_period_end",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("provider_metadata", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing(
        "ix_student_subscriptions_user", "student_subscriptions", ["user_id"]
    )
    _create_index_if_missing(
        "ix_student_subscriptions_customer",
        "student_subscriptions",
        ["provider_customer_id"],
    )
    _create_index_if_missing(
        "ix_student_subscriptions_subscription",
        "student_subscriptions",
        ["provider_subscription_id"],
    )

    if not _table_exists("grading_usage_events"):
        op.create_table(
            "grading_usage_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "subscription_id",
                sa.String(),
                sa.ForeignKey("student_subscriptions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("evaluation_run_id", sa.String(), nullable=True, unique=True),
            sa.Column(
                "event_type", sa.String(), nullable=False, server_default="exam_grading"
            ),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_price_cents", sa.Integer(), nullable=False, server_default="200"),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="eur"),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("provider_usage_record_id", sa.String(), nullable=True),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing(
        "ix_grading_usage_events_user", "grading_usage_events", ["user_id"]
    )
    _create_index_if_missing(
        "ix_grading_usage_events_subscription",
        "grading_usage_events",
        ["subscription_id"],
    )
    _create_index_if_missing(
        "ix_grading_usage_events_occurred", "grading_usage_events", ["occurred_at"]
    )
    _create_index_if_missing(
        "ix_grading_usage_events_user_occurred",
        "grading_usage_events",
        ["user_id", "occurred_at"],
    )


def downgrade() -> None:
    if _table_exists("grading_usage_events"):
        op.drop_table("grading_usage_events")
    if _table_exists("student_subscriptions"):
        op.drop_table("student_subscriptions")
