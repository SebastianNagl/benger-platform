"""Creation-wizard drafts: ``projects.is_wizard_draft`` and ``project_wizard_drafts``

The creation wizard of an exam creates a real project when the teacher leaves
its first step, so tasks and grading sheets exist (and can be checked) before
"Create". Until the wizard finishes, the project is a draft:

- ``projects.is_wizard_draft`` (NOT NULL, default FALSE; a constant default,
  so the column is added without a table rewrite and no existing row
  changes) and the partial index ``ix_projects_wizard_draft (created_by)
  WHERE is_wizard_draft``.
- New table ``project_wizard_drafts``: one row per draft with the creator,
  the wizard's ``client_key`` (unique per creator, for idempotent create and
  finish), the target organization and group the finish route attaches
  (both ``SET NULL``, so deleting a group or an org is never blocked by a
  draft), the wizard state (JSONB) with its version, the current step and
  ``touched_at`` for the stale-draft sweep. The finish route keeps the row
  (``finished_at`` set, state cleared) so a repeated finish with the same
  key is recognized. Cascades with the project and with its creator.

Idempotent: every step is guarded, so a database built from the models (the
test DB) runs it as a no-op.

Revision ID: 141_project_wizard_drafts
Revises: 140_generation_cascades_and_purge_jobs
Create Date: 2026-11-17
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "141_project_wizard_drafts"
down_revision = "140_generation_cascades_and_purge_jobs"
branch_labels = None
depends_on = None

_DRAFTS = "project_wizard_drafts"


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _insp().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    if not _has_column("projects", "is_wizard_draft"):
        op.add_column(
            "projects",
            sa.Column(
                "is_wizard_draft", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    if not _has_index("projects", "ix_projects_wizard_draft"):
        op.create_index(
            "ix_projects_wizard_draft",
            "projects",
            ["created_by"],
            postgresql_where=sa.text("is_wizard_draft"),
        )

    if not _has_table(_DRAFTS):
        op.create_table(
            _DRAFTS,
            sa.Column(
                "project_id", sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True,
            ),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("client_key", sa.String(64), nullable=False),
            sa.Column(
                "target_organization_id", sa.String(),
                sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "target_group_id", sa.String(),
                sa.ForeignKey("organization_groups.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("state", postgresql.JSONB(), nullable=True),
            sa.Column(
                "state_version", sa.Integer(), nullable=False, server_default=sa.text("1")
            ),
            sa.Column("step_id", sa.String(64), nullable=True),
            sa.Column(
                "touched_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "created_by", "client_key", name="uq_project_wizard_drafts_client_key"
            ),
        )
    if not _has_index(_DRAFTS, "ix_project_wizard_drafts_touched_at"):
        op.create_index("ix_project_wizard_drafts_touched_at", _DRAFTS, ["touched_at"])


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_table(_DRAFTS):
        op.drop_table(_DRAFTS)
    if _has_index("projects", "ix_projects_wizard_draft"):
        op.drop_index("ix_projects_wizard_draft", table_name="projects")
    if _has_column("projects", "is_wizard_draft"):
        op.drop_column("projects", "is_wizard_draft")
