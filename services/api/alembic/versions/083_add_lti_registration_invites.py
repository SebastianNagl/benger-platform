"""add lti_registration_invites table

One-time, org-bound invites for IMS LTI Dynamic Registration: a superadmin
mints an invite URL in BenGER, the university's Moodle admin pastes it into
"Manage tools", and the tool's registration endpoint (``benger_extended``)
validates the token and auto-creates the ``lti_platform_registrations`` row.
The schema is platform-owned (split rule: ALL DB tables live in
benger-platform); the registration-protocol logic lives in the extended
edition. The community edition only carries this forward-compatible schema.

- ``token_hash``: sha256 hex of the raw invite token (raw token is never
  stored) — unique index, it's the lookup key for the registration endpoint.
- ``organization_id``: CASCADE — invites are org-scoped ephemera/audit, not
  live LMS wiring; they must never block an org deletion the way
  registrations (RESTRICT) deliberately do.
- ``used_at`` + ``resulting_registration_id`` (SET NULL): a consumed invite
  stays as an audit record; pending invites are revoked by hard delete.

Pure additive. Idempotent — guards on table/index existence; safe to re-run.

Revision ID: 083_add_lti_registration_invites
Revises: 082_add_custom_model_org_credentials
Create Date: 2026-07-17
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "083_add_lti_registration_invites"
down_revision = "082_add_custom_model_org_credentials"
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


def _create_index_if_missing(
    name: str, table: str, columns: list, unique: bool = False
) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    if not _table_exists("lti_registration_invites"):
        op.create_table(
            "lti_registration_invites",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
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
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "resulting_registration_id",
                sa.String(),
                sa.ForeignKey("lti_platform_registrations.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    _create_index_if_missing(
        "ix_lti_registration_invites_token_hash",
        "lti_registration_invites",
        ["token_hash"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_lti_registration_invites_organization_id",
        "lti_registration_invites",
        ["organization_id"],
    )


def downgrade() -> None:
    if _table_exists("lti_registration_invites"):
        op.drop_table("lti_registration_invites")
