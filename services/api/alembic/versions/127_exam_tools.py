"""Exam tools (Hilfsmittel) per project and tool providers

- ``projects.exam_tools`` (JSONB, NULL): the tools a project's writers may
  use in the exam interface and, for content tools (law texts, commentary),
  the whitelist of sources and codes; shape in ``shared/exam_tools.py``.
  NULL = the project never chose.
- ``tool_providers``: content providers BenGER syncs from (the built-in
  gesetze-im-internet provider or an external one implementing the BenGER
  Tool Provider API), incl. the OAuth client settings for student linking
  (client secret Fernet-encrypted).
- ``org_tool_provider_connections``: an organization's credential for a
  provider (Fernet-encrypted, one row per org and provider) and its sync
  status.
- ``user_tool_provider_links``: a user's own account at a provider (OAuth
  tokens Fernet-encrypted, one row per user and provider) and its sync
  status.
- ``tool_bundles`` / ``tool_bundle_items``: one code or commentary of a
  provider in one content version (deduplicated by content hash), its items
  with a German full-text index.
- ``tool_entitlements``: which bundle a link, an org connection or a
  built-in provider currently holds per kind and code.
- ``exam_tool_pins``: the bundle a writer saw in a project, kept from the
  first read until the attempt ends, so content never changes mid-exam.
- ``exam_tool_notes``: a writer's scratch notes per task from the notes
  tool (one row per task and user; never graded, not exported).

Content is synced ahead of time (when an account is linked, nightly, on
"sync now"), never during an exam. The logic using these tables lives in the
extended edition.

Idempotent: every step is guarded, a re-run is a no-op.

Revision ID: 127_exam_tools
Revises: 126_pending_submission_uploads
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "127_exam_tools"
down_revision = "126_pending_submission_uploads"
branch_labels = None
depends_on = None

_PROJECTS = "projects"
_COLUMN = "exam_tools"
_PROVIDERS = "tool_providers"
_CONNECTIONS = "org_tool_provider_connections"
_LINKS = "user_tool_provider_links"
_BUNDLES = "tool_bundles"
_ITEMS = "tool_bundle_items"
_ITEMS_SEARCH_INDEX = "ix_tool_bundle_items_search"
_ENTITLEMENTS = "tool_entitlements"
_PINS = "exam_tool_pins"
_NOTES = "exam_tool_notes"


def _has_table(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _sync_columns() -> list:
    return [
        sa.Column("last_sync_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_finished_at", sa.DateTime(timezone=True), nullable=True),
        # ok | error | skipped_exam (null = never synced)
        sa.Column("last_sync_status", sa.String(32), nullable=True),
        sa.Column("last_sync_error", sa.String(500), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _jsonb(name: str, default: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text(f"'{default}'::jsonb"),
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    if not _column_exists(_PROJECTS, _COLUMN):
        op.add_column(
            _PROJECTS,
            sa.Column(_COLUMN, postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )

    if not _has_table(_PROVIDERS):
        op.create_table(
            _PROVIDERS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("slug", sa.String(64), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column(
                "kinds",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("base_url", sa.String(500), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("contact", sa.String(255), nullable=True),
            sa.Column(
                "supports_student_links", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("oauth_client_id", sa.String(255), nullable=True),
            sa.Column("encrypted_oauth_client_secret", sa.Text(), nullable=True),
            sa.Column("oauth_authorize_url", sa.String(500), nullable=True),
            sa.Column("oauth_token_url", sa.String(500), nullable=True),
            sa.Column("oauth_revoke_url", sa.String(500), nullable=True),
            sa.Column("oauth_scopes", sa.String(500), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "is_builtin OR base_url IS NOT NULL",
                name="ck_tool_providers_external_has_base_url",
            ),
        )

    if not _has_table(_CONNECTIONS):
        op.create_table(
            _CONNECTIONS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "provider_id",
                sa.String(),
                sa.ForeignKey("tool_providers.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("encrypted_credential", sa.Text(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
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
            *_sync_columns(),
            sa.UniqueConstraint(
                "organization_id", "provider_id", name="uq_org_tool_provider_connection"
            ),
        )

    if not _has_table(_LINKS):
        op.create_table(
            _LINKS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "provider_id",
                sa.String(),
                sa.ForeignKey("tool_providers.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
            sa.Column("encrypted_access_token", sa.Text(), nullable=True),
            sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("account_label", sa.String(255), nullable=True),
            # active | expired | revoked
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column(
                "linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            *_sync_columns(),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "provider_id", name="uq_user_tool_provider_link"),
        )

    if not _has_table(_BUNDLES):
        op.create_table(
            _BUNDLES,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("provider_slug", sa.String(64), nullable=False),
            # law_texts | commentary
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("as_of", sa.String(32), nullable=True),
            _jsonb("toc", "[]"),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            _created_at(),
            # Last time an entitlement or pin referred to it (GC).
            sa.Column(
                "last_referenced_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "provider_slug", "kind", "code", "content_hash", name="uq_tool_bundle_version"
            ),
        )
        op.create_index(
            "ix_tool_bundles_provider_kind_code", _BUNDLES, ["provider_slug", "kind", "code"]
        )

    if not _has_table(_ITEMS):
        op.create_table(
            _ITEMS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "bundle_id",
                sa.String(),
                sa.ForeignKey("tool_bundles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("item_id", sa.String(128), nullable=False),
            sa.Column("label", sa.String(255), nullable=False),
            sa.Column("title", sa.Text(), nullable=True),
            _jsonb("blocks", "[]"),
            # commentary entries: [{code, norm}] they comment
            _jsonb("refs", "[]"),
            sa.Column("plain_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("previous_id", sa.String(128), nullable=True),
            sa.Column("next_id", sa.String(128), nullable=True),
            sa.UniqueConstraint("bundle_id", "item_id", name="uq_tool_bundle_item"),
        )
        op.create_index("ix_tool_bundle_items_order", _ITEMS, ["bundle_id", "ordinal"])
    # Expression indexes are not part of the models, so they are created
    # even when the table already exists (e.g. built by create_all).
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_ITEMS_SEARCH_INDEX} ON {_ITEMS} "
        "USING gin (to_tsvector('german', coalesce(label, '') || ' ' || "
        "coalesce(title, '') || ' ' || plain_text))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_bundle_items_refs ON tool_bundle_items "
        "USING gin (refs jsonb_path_ops)"
    )

    if not _has_table(_ENTITLEMENTS):
        op.create_table(
            _ENTITLEMENTS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "link_id",
                sa.String(),
                sa.ForeignKey("user_tool_provider_links.id", ondelete="CASCADE"),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "org_connection_id",
                sa.String(),
                sa.ForeignKey("org_tool_provider_connections.id", ondelete="CASCADE"),
                nullable=True,
                index=True,
            ),
            # Built-in providers (gii) hold their bundles without an owner.
            sa.Column("builtin_provider_slug", sa.String(64), nullable=True),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column(
                "bundle_id",
                sa.String(),
                sa.ForeignKey("tool_bundles.id", ondelete="RESTRICT"),
                nullable=False,
                index=True,
            ),
            # The provider's opaque version / ETag of that bundle.
            sa.Column("version", sa.String(256), nullable=True),
            sa.Column("etag", sa.String(256), nullable=True),
            sa.Column(
                "synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.CheckConstraint(
                "(link_id IS NOT NULL)::int + (org_connection_id IS NOT NULL)::int"
                " + (builtin_provider_slug IS NOT NULL)::int = 1",
                name="ck_tool_entitlements_one_owner",
            ),
            sa.UniqueConstraint("link_id", "kind", "code", name="uq_tool_entitlement_link"),
            sa.UniqueConstraint(
                "org_connection_id", "kind", "code", name="uq_tool_entitlement_org"
            ),
            sa.UniqueConstraint(
                "builtin_provider_slug", "kind", "code", name="uq_tool_entitlement_builtin"
            ),
        )

    if not _has_table(_PINS):
        op.create_table(
            _PINS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("provider_slug", sa.String(64), nullable=False),
            sa.Column(
                "bundle_id",
                sa.String(),
                sa.ForeignKey("tool_bundles.id", ondelete="RESTRICT"),
                nullable=False,
                index=True,
            ),
            # student | org | builtin
            sa.Column("source_mode", sa.String(16), nullable=False),
            sa.Column(
                "pinned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("project_id", "user_id", "kind", "code", name="uq_exam_tool_pin"),
        )

    if not _has_table(_NOTES):
        op.create_table(
            _NOTES,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "task_id",
                sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("text", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("task_id", "user_id", name="uq_exam_tool_notes_task_user"),
        )


def downgrade() -> None:
    for table in (_NOTES, _PINS, _ENTITLEMENTS, _ITEMS, _BUNDLES, _LINKS, _CONNECTIONS, _PROVIDERS):
        if _has_table(table):
            op.drop_table(table)
    if _column_exists(_PROJECTS, _COLUMN):
        op.drop_column(_PROJECTS, _COLUMN)
