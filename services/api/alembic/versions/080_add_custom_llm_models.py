"""Add BYOM (bring-your-own-model) support to the model catalog.

Users register custom OpenAI-compatible models that live in the same
``llm_models`` table as the YAML-seeded catalog (Generation.model_id, cost
estimation and every picker key on llm_models.id, so a parallel table would
fracture all of them). New columns:

- ``is_official``: true for every catalog row seeded from the YAML, false
  for user-registered custom rows. The seeder's deactivation sweep and the
  drift checker filter on it so custom rows survive reseeds.
- ``created_by``: creator of a custom row (SET NULL on user deletion —
  shared/public models outlive their creator; superadmins keep edit rights).
- ``is_private`` / ``is_public``: project-style visibility (private /
  org-shared via model_organizations / public). No public_role for models:
  public means usable, never editable.
- ``base_url`` / ``endpoint_model_name``: the OpenAI-compatible endpoint and
  the remote "model" string. The PK of a custom row is a generated
  ``custom-<uuid>`` and is never sent to the remote server.
- ``requires_api_key``: false for open endpoints (local vLLM/Ollama).

New tables:

- ``model_organizations``: org-sharing join table (clone of
  project_organizations); a row grants usage, never edit.
- ``custom_model_credentials``: per-(user, model) Fernet-encrypted API keys —
  sharing a model shares only the endpoint definition, every user brings
  their own key.

CRITICAL backfill: ``UPDATE llm_models SET is_official = true`` runs here,
in the migration. The startup seed is gated on the YAML content hash
(main.py flag files) and will NOT re-run on deploy; without this backfill
the official-only public catalog endpoint would return an empty list.
Safe: no custom rows can exist before this migration.

Idempotent — guards on column/table/constraint existence; safe to re-run.

Revision ID: 080_add_custom_llm_models
Revises: 079_add_lti_tables
Create Date: 2026-07-14
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "080_add_custom_llm_models"
down_revision = "079_add_lti_tables"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {c["name"] for c in insp.get_check_constraints(table)}


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    # ----------------------------------------------------------------- #
    # llm_models — BYOM columns
    # ----------------------------------------------------------------- #
    added_is_official = False
    if not _column_exists("llm_models", "is_official"):
        op.add_column(
            "llm_models",
            sa.Column(
                "is_official",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )
        added_is_official = True
    if not _column_exists("llm_models", "created_by"):
        op.add_column(
            "llm_models",
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _column_exists("llm_models", "is_private"):
        op.add_column(
            "llm_models",
            sa.Column(
                "is_private",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )
    if not _column_exists("llm_models", "is_public"):
        op.add_column(
            "llm_models",
            sa.Column(
                "is_public",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )
    if not _column_exists("llm_models", "base_url"):
        op.add_column(
            "llm_models", sa.Column("base_url", sa.String(length=500), nullable=True)
        )
    if not _column_exists("llm_models", "endpoint_model_name"):
        op.add_column(
            "llm_models",
            sa.Column("endpoint_model_name", sa.String(length=255), nullable=True),
        )
    if not _column_exists("llm_models", "requires_api_key"):
        op.add_column(
            "llm_models",
            sa.Column(
                "requires_api_key",
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            ),
        )

    # Backfill: every row that exists before this migration is by definition
    # a catalog (official) row. Must happen HERE — the startup seed is gated
    # on the unchanged YAML hash and will not re-run on deploy.
    if added_is_official:
        op.execute("UPDATE llm_models SET is_official = true")

    if not _constraint_exists("llm_models", "ck_llm_models_visibility_exclusive"):
        op.create_check_constraint(
            "ck_llm_models_visibility_exclusive",
            "llm_models",
            "NOT (is_private AND is_public)",
        )
    if not _constraint_exists("llm_models", "ck_llm_models_custom_endpoint_required"):
        op.create_check_constraint(
            "ck_llm_models_custom_endpoint_required",
            "llm_models",
            "is_official OR (base_url IS NOT NULL AND endpoint_model_name IS NOT NULL)",
        )
    if not _constraint_exists(
        "llm_models", "ck_llm_models_official_no_visibility_flags"
    ):
        op.create_check_constraint(
            "ck_llm_models_official_no_visibility_flags",
            "llm_models",
            "NOT is_official OR (NOT is_private AND NOT is_public)",
        )

    if not _index_exists("llm_models", "ix_llm_models_created_by"):
        op.create_index("ix_llm_models_created_by", "llm_models", ["created_by"])
    if not _index_exists("llm_models", "ix_llm_models_is_public"):
        op.create_index(
            "ix_llm_models_is_public",
            "llm_models",
            ["is_public"],
            postgresql_where=sa.text("is_public = true"),
        )

    # ----------------------------------------------------------------- #
    # model_organizations — org sharing (usage grant, never edit)
    # ----------------------------------------------------------------- #
    if not _table_exists("model_organizations"):
        op.create_table(
            "model_organizations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "model_id",
                sa.String(),
                sa.ForeignKey("llm_models.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "assigned_by",
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
                "model_id", "organization_id", name="unique_model_organization"
            ),
        )
    if not _index_exists("model_organizations", "ix_model_organizations_model_id"):
        op.create_index(
            "ix_model_organizations_model_id", "model_organizations", ["model_id"]
        )
    if not _index_exists(
        "model_organizations", "ix_model_organizations_organization_id"
    ):
        op.create_index(
            "ix_model_organizations_organization_id",
            "model_organizations",
            ["organization_id"],
        )

    # ----------------------------------------------------------------- #
    # custom_model_credentials — per-(user, model) encrypted keys
    # ----------------------------------------------------------------- #
    if not _table_exists("custom_model_credentials"):
        op.create_table(
            "custom_model_credentials",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "model_id",
                sa.String(),
                sa.ForeignKey("llm_models.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("encrypted_api_key", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "user_id", "model_id", name="unique_custom_model_credential"
            ),
        )
    if not _index_exists(
        "custom_model_credentials", "ix_custom_model_credentials_user_id"
    ):
        op.create_index(
            "ix_custom_model_credentials_user_id",
            "custom_model_credentials",
            ["user_id"],
        )
    if not _index_exists(
        "custom_model_credentials", "ix_custom_model_credentials_model_id"
    ):
        op.create_index(
            "ix_custom_model_credentials_model_id",
            "custom_model_credentials",
            ["model_id"],
        )


def downgrade() -> None:
    if _table_exists("custom_model_credentials"):
        op.drop_table("custom_model_credentials")
    if _table_exists("model_organizations"):
        op.drop_table("model_organizations")

    if _index_exists("llm_models", "ix_llm_models_is_public"):
        op.drop_index("ix_llm_models_is_public", table_name="llm_models")
    if _index_exists("llm_models", "ix_llm_models_created_by"):
        op.drop_index("ix_llm_models_created_by", table_name="llm_models")
    for ck in (
        "ck_llm_models_official_no_visibility_flags",
        "ck_llm_models_custom_endpoint_required",
        "ck_llm_models_visibility_exclusive",
    ):
        if _constraint_exists("llm_models", ck):
            op.drop_constraint(ck, "llm_models", type_="check")
    for col in (
        "requires_api_key",
        "endpoint_model_name",
        "base_url",
        "is_public",
        "is_private",
        "created_by",
        "is_official",
    ):
        if _column_exists("llm_models", col):
            op.drop_column("llm_models", col)
