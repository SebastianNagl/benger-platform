"""add access keys (api_keys, api_key_usage_events, users.is_service_account)

Programmatic access to the public ``/api/v1`` surface (benger-compliance
issue #3):

* ``users.is_service_account``: marks the machine user behind an
  organization key. Such accounts never log in, never get notifications and
  are hidden from member lists.
* ``api_keys``: one row per key. Only the SHA-256 of the peppered secret is
  stored; ``key_prefix`` is the public lookup handle. Personal keys
  (``owner_type='user'``) act as their owner, organization keys
  (``owner_type='org'``) act as their own service-account user.
* ``api_key_usage_events``: one row per ``/api/v1`` request made with a key
  (route template, status, timing, no bodies), pruned after
  ``API_USAGE_RETENTION_DAYS``.

Idempotent: guards on column, table and index existence, safe to re-run.

Revision ID: 118_api_keys
Revises: 117_task_work_presence
Create Date: 2026-10-13
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa


revision = "118_api_keys"
down_revision = "117_task_work_presence"
branch_labels = None
depends_on = None


KEYS_TABLE = "api_keys"
USAGE_TABLE = "api_key_usage_events"

# The enum type organization_memberships.role already uses (migration 001).
_ROLE_ENUM = postgresql.ENUM(
    "ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", name="organizationrole", create_type=False
)


def _columns(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set:
    return {i["name"] for i in inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    insp = inspect(op.get_bind())

    if "is_service_account" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column(
                "is_service_account",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "ix_users_is_service_account" not in _indexes("users"):
        op.create_index(
            "ix_users_is_service_account",
            "users",
            ["is_service_account"],
            postgresql_where=sa.text("is_service_account"),
        )

    if not insp.has_table(KEYS_TABLE):
        op.create_table(
            KEYS_TABLE,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("key_prefix", sa.String(32), nullable=False),
            sa.Column("key_hash", sa.String(64), nullable=False),
            sa.Column(
                "hash_version", sa.SmallInteger(), nullable=False, server_default="1"
            ),
            sa.Column("owner_type", sa.String(8), nullable=False),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("group_id", sa.String(), nullable=True),
            sa.Column("org_role", _ROLE_ENUM, nullable=True),
            sa.Column(
                "scopes",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("project_ids", postgresql.JSONB(), nullable=True),
            sa.Column(
                "environment", sa.String(8), nullable=False, server_default="live"
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "revoked_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("revoke_reason", sa.Text(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_ip", sa.String(64), nullable=True),
            sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True),
            sa.Column("rate_limit_per_day", sa.Integer(), nullable=True),
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("key_prefix", name="uq_api_keys_key_prefix"),
            sa.CheckConstraint(
                "owner_type IN ('user', 'org')", name="ck_api_keys_owner_type"
            ),
            sa.CheckConstraint(
                "environment IN ('live', 'test')", name="ck_api_keys_environment"
            ),
            sa.CheckConstraint(
                "(owner_type = 'user' AND organization_id IS NULL AND group_id IS NULL"
                " AND org_role IS NULL)"
                " OR (owner_type = 'org' AND organization_id IS NOT NULL"
                " AND org_role IS NOT NULL)",
                name="ck_api_keys_owner_shape",
            ),
            sa.ForeignKeyConstraint(
                ["organization_id", "group_id"],
                ["organization_groups.organization_id", "organization_groups.id"],
                name="fk_api_keys_group_scope",
                ondelete="CASCADE",
            ),
        )
    key_indexes = _indexes(KEYS_TABLE)
    if "ix_api_keys_user_id" not in key_indexes:
        op.create_index("ix_api_keys_user_id", KEYS_TABLE, ["user_id"])
    if "ix_api_keys_organization_id" not in key_indexes:
        op.create_index("ix_api_keys_organization_id", KEYS_TABLE, ["organization_id"])
    if "ix_api_keys_org_active" not in key_indexes:
        op.create_index(
            "ix_api_keys_org_active",
            KEYS_TABLE,
            ["organization_id"],
            postgresql_where=sa.text("revoked_at IS NULL"),
        )

    if not insp.has_table(USAGE_TABLE):
        op.create_table(
            USAGE_TABLE,
            sa.Column(
                "id", sa.BigInteger(), sa.Identity(always=False), primary_key=True
            ),
            sa.Column(
                "api_key_id",
                sa.String(),
                sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("key_prefix", sa.String(32), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("request_id", sa.String(64), nullable=True),
            sa.Column("method", sa.String(8), nullable=True),
            sa.Column("route", sa.String(200), nullable=True),
            sa.Column("project_id", sa.String(), nullable=True),
            sa.Column("status_code", sa.SmallInteger(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("scope_used", sa.String(64), nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(256), nullable=True),
            sa.Column("request_bytes", sa.Integer(), nullable=True),
            sa.Column("response_bytes", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    usage_indexes = _indexes(USAGE_TABLE)
    if "ix_api_key_usage_events_key_created" not in usage_indexes:
        op.create_index(
            "ix_api_key_usage_events_key_created",
            USAGE_TABLE,
            ["api_key_id", sa.text("created_at DESC")],
        )
    if "ix_api_key_usage_events_org_created" not in usage_indexes:
        op.create_index(
            "ix_api_key_usage_events_org_created",
            USAGE_TABLE,
            ["organization_id", sa.text("created_at DESC")],
        )
    if "ix_api_key_usage_events_created_brin" not in usage_indexes:
        op.create_index(
            "ix_api_key_usage_events_created_brin",
            USAGE_TABLE,
            ["created_at"],
            postgresql_using="brin",
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(USAGE_TABLE):
        op.drop_table(USAGE_TABLE)
    if insp.has_table(KEYS_TABLE):
        op.drop_table(KEYS_TABLE)
    if "ix_users_is_service_account" in _indexes("users"):
        op.drop_index("ix_users_is_service_account", table_name="users")
    if "is_service_account" in _columns("users"):
        op.drop_column("users", "is_service_account")
