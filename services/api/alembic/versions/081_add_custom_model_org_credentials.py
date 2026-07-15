"""Org-owned (shared) credentials for custom (BYOM) models.

``custom_model_credentials`` (migration 080) stores a Fernet key per
``(user, model)`` — every member brings their own key. This migration adds
the org-level counterpart so an organization can provision ONE shared key
for a custom model instead of every member entering their own:

- ``custom_model_org_credentials``: per-``(organization, model)`` Fernet key.
  Unique on ``(organization_id, model_id)`` — one shared key per model per
  org, exactly mirroring ``organization_api_keys``' unique
  ``(organization_id, provider)``.

Resolution precedence (implemented in
``user_aware_ai_service.get_ai_service_for_model_row``) reuses the org
``settings.require_private_keys`` flag, same as
``shared_org_api_key_service.resolve_api_key``: True (default) → the invoking
user's own ``custom_model_credentials`` key; False → fall back to this org's
shared key when the user has none. The model owner's key is NEVER used.

Idempotent — guards on table/index existence; safe to re-run. Reversible —
downgrade drops the table.

Revision ID: 081_add_custom_model_org_credentials
Revises: 080_add_custom_llm_models
Create Date: 2026-07-15
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "081_add_custom_model_org_credentials"
down_revision = "080_add_custom_llm_models"
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


def upgrade() -> None:
    # ----------------------------------------------------------------- #
    # custom_model_org_credentials — per-(org, model) encrypted keys
    # ----------------------------------------------------------------- #
    if not _table_exists("custom_model_org_credentials"):
        op.create_table(
            "custom_model_org_credentials",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "model_id",
                sa.String(),
                sa.ForeignKey("llm_models.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("encrypted_api_key", sa.Text(), nullable=False),
            # SET NULL: deleting the admin who set the shared key must not
            # revoke the org's access to it.
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
            sa.UniqueConstraint(
                "organization_id",
                "model_id",
                name="unique_custom_model_org_credential",
            ),
        )
    if not _index_exists(
        "custom_model_org_credentials",
        "ix_custom_model_org_credentials_organization_id",
    ):
        op.create_index(
            "ix_custom_model_org_credentials_organization_id",
            "custom_model_org_credentials",
            ["organization_id"],
        )
    if not _index_exists(
        "custom_model_org_credentials", "ix_custom_model_org_credentials_model_id"
    ):
        op.create_index(
            "ix_custom_model_org_credentials_model_id",
            "custom_model_org_credentials",
            ["model_id"],
        )


def downgrade() -> None:
    if _table_exists("custom_model_org_credentials"):
        op.drop_table("custom_model_org_credentials")
