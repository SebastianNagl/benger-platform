"""project reports: public visibility flag + snapshot-friendly indexes

``project_reports.is_public`` — a published report is visible to members of
the project's organizations; a *public* report is additionally readable by
every signed-in user and by anonymous visitors (benchmark result pages).
Publishing stays a superadmin action; ``is_public`` is only meaningful while
``is_published`` is true.

Idempotent — guards on column/index existence; safe to re-run.

Revision ID: 098_project_report_public
Revises: 097_add_organization_groups
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

revision = "098_project_report_public"
down_revision = "097_add_organization_groups"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_index(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(i["name"] == name for i in insp.get_indexes(table))


def upgrade() -> None:
    if not _has_column("project_reports", "is_public"):
        op.add_column(
            "project_reports",
            sa.Column(
                "is_public",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if not _has_index("project_reports", "ix_project_reports_public_published"):
        op.create_index(
            "ix_project_reports_public_published",
            "project_reports",
            ["is_public", "is_published"],
        )


def downgrade() -> None:
    if _has_index("project_reports", "ix_project_reports_public_published"):
        op.drop_index("ix_project_reports_public_published", table_name="project_reports")
    if _has_column("project_reports", "is_public"):
        op.drop_column("project_reports", "is_public")
