"""Exam tools (Hilfsmittel) per project and tool providers

- ``projects.exam_tools`` (JSONB, NULL): the tools a project's writers may
  use in the exam interface (calculator, calendar, law texts, notes, ...),
  shape in ``shared/exam_tools.py``. NULL = the project never chose.
- ``tool_providers``: content providers BenGER calls server-side for a tool
  kind (first kind ``law_texts``), e.g. the built-in gesetze-im-internet
  provider or an external one implementing the BenGER Tool Provider API.
- ``org_tool_provider_connections``: an organization's credential for a
  provider (Fernet-encrypted, one row per org and provider).
- ``law_text_norms``: norms a law-text provider served or a built-in
  provider ingested, so exams keep working while a provider is down.
- ``exam_tool_notes``: a writer's scratch notes per task from the notes
  tool (one row per task and user; never graded, not exported).

The logic using these tables lives in the extended edition.

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
_NORMS = "law_text_norms"
_NORMS_SEARCH_INDEX = "ix_law_text_norms_search"
_NOTES = "exam_tool_notes"


def _has_table(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


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
            sa.Column("api_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("contact", sa.String(255), nullable=True),
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
            sa.UniqueConstraint(
                "organization_id", "provider_id", name="uq_org_tool_provider_connection"
            ),
        )

    if not _has_table(_NORMS):
        op.create_table(
            _NORMS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("provider_slug", sa.String(64), nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("norm_id", sa.String(128), nullable=False),
            sa.Column("label", sa.String(255), nullable=False),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column(
                "blocks",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("plain_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("as_of", sa.String(32), nullable=True),
            sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "fetched_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "provider_slug", "code", "norm_id", name="uq_law_text_norms_norm"
            ),
        )
        op.create_index(
            "ix_law_text_norms_code_order",
            _NORMS,
            ["provider_slug", "code", "ordinal"],
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {_NORMS_SEARCH_INDEX} ON {_NORMS} "
            "USING gin (to_tsvector('german', coalesce(label, '') || ' ' || "
            "coalesce(title, '') || ' ' || plain_text))"
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
    if _has_table(_NOTES):
        op.drop_table(_NOTES)
    if _has_table(_NORMS):
        op.execute(f"DROP INDEX IF EXISTS {_NORMS_SEARCH_INDEX}")
        op.drop_table(_NORMS)
    if _has_table(_CONNECTIONS):
        op.drop_table(_CONNECTIONS)
    if _has_table(_PROVIDERS):
        op.drop_table(_PROVIDERS)
    if _column_exists(_PROJECTS, _COLUMN):
        op.drop_column(_PROJECTS, _COLUMN)
