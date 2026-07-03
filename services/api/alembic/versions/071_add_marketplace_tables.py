"""add vendor marketplace tables

Vendor marketplace: third-party vendors (flagged organizations) sell exams and
flashcard collections to students via Stripe Connect. The schema is platform-
owned; the proprietary Connect orchestration (onboarding, checkout, webhooks,
payouts) lives in ``benger_extended``.

- ``vendor_accounts``: one row per vendor org (unique ``organization_id``).
  Created by a superadmin (row existence == approval); ``charges_enabled`` is
  the publish/sell gate, set from the Stripe ``account.updated`` webhook.
- ``marketplace_listings``: a project's priced, published offering. At most one
  per project (unique ``project_id``).
- ``marketplace_orders``: the authoritative one-time-purchase ledger. Unique
  ``stripe_checkout_session_id`` is the webhook idempotency key — a replayed
  ``checkout.session.completed`` can never double-fulfil.
- ``marketplace_entitlements``: the permanent access row (purchase or
  vendor_grant). Unique ``(user_id, project_id)`` makes the grant idempotent.

FKs to users use ``ondelete=CASCADE`` (right-to-erasure self-cleans a deleted
user's marketplace rows). Listing/project/org/order references on the order and
entitlement ledgers use ``SET NULL`` so the ledger survives the parent.

Tables are created in dependency order (listings -> orders -> entitlements).
Idempotent — guards on table/index existence; safe to re-run.

Revision ID: 071_add_marketplace_tables
Revises: 070_add_student_billing_tables
Create Date: 2026-06-28
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "071_add_marketplace_tables"
down_revision = "070_add_student_billing_tables"
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
    # ----------------------------------------------------------------- #
    # vendor_accounts — superadmin-approved Stripe Connect selling account
    # ----------------------------------------------------------------- #
    if not _table_exists("vendor_accounts"):
        op.create_table(
            "vendor_accounts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "approved_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "approved_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("provider", sa.String(), nullable=False, server_default="stripe"),
            sa.Column("stripe_account_id", sa.String(), nullable=True),
            sa.Column(
                "charges_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "payouts_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "details_submitted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "onboarding_status",
                sa.String(),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("platform_fee_bps", sa.Integer(), nullable=True),
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
        "ix_vendor_accounts_organization", "vendor_accounts", ["organization_id"]
    )
    _create_index_if_missing(
        "ix_vendor_accounts_stripe_account", "vendor_accounts", ["stripe_account_id"]
    )

    # ----------------------------------------------------------------- #
    # marketplace_listings — a project's priced, published offering
    # ----------------------------------------------------------------- #
    if not _table_exists("marketplace_listings"):
        op.create_table(
            "marketplace_listings",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "vendor_org_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(length=32), nullable=True),
            sa.Column("price_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="eur"),
            sa.Column(
                "published", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("project_id", name="uq_marketplace_listing_project"),
        )
    _create_index_if_missing(
        "ix_marketplace_listings_published", "marketplace_listings", ["published"]
    )
    _create_index_if_missing(
        "ix_marketplace_listings_vendor_org", "marketplace_listings", ["vendor_org_id"]
    )

    # ----------------------------------------------------------------- #
    # marketplace_orders — one-time purchase ledger (Stripe Connect)
    # ----------------------------------------------------------------- #
    if not _table_exists("marketplace_orders"):
        op.create_table(
            "marketplace_orders",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "buyer_user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "listing_id",
                sa.String(),
                sa.ForeignKey("marketplace_listings.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "vendor_org_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="eur"),
            sa.Column(
                "platform_fee_cents", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("vendor_stripe_account_id", sa.String(), nullable=True),
            sa.Column(
                "stripe_checkout_session_id", sa.String(), nullable=True, unique=True
            ),
            sa.Column("stripe_payment_intent_id", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing(
        "ix_marketplace_orders_buyer", "marketplace_orders", ["buyer_user_id"]
    )
    _create_index_if_missing(
        "ix_marketplace_orders_checkout_session",
        "marketplace_orders",
        ["stripe_checkout_session_id"],
    )
    _create_index_if_missing(
        "ix_marketplace_orders_payment_intent",
        "marketplace_orders",
        ["stripe_payment_intent_id"],
    )

    # ----------------------------------------------------------------- #
    # marketplace_entitlements — permanent access (purchase | vendor_grant)
    # ----------------------------------------------------------------- #
    if not _table_exists("marketplace_entitlements"):
        op.create_table(
            "marketplace_entitlements",
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
            sa.Column(
                "listing_id",
                sa.String(),
                sa.ForeignKey("marketplace_listings.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column(
                "order_id",
                sa.String(),
                sa.ForeignKey("marketplace_orders.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "granted_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "granted_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "user_id", "project_id", name="uq_marketplace_entitlement_user_project"
            ),
        )
    _create_index_if_missing(
        "ix_marketplace_entitlements_user", "marketplace_entitlements", ["user_id"]
    )
    _create_index_if_missing(
        "ix_marketplace_entitlements_project", "marketplace_entitlements", ["project_id"]
    )


def downgrade() -> None:
    # Reverse dependency order.
    if _table_exists("marketplace_entitlements"):
        op.drop_table("marketplace_entitlements")
    if _table_exists("marketplace_orders"):
        op.drop_table("marketplace_orders")
    if _table_exists("marketplace_listings"):
        op.drop_table("marketplace_listings")
    if _table_exists("vendor_accounts"):
        op.drop_table("vendor_accounts")
