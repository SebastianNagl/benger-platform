"""Drop legacy projects.organization_id FK column.

The Project↔Organization relationship is many-to-many via the
`project_organizations` junction table (see `ProjectOrganization` in
`project_models.py`). The single-FK `projects.organization_id` column
was made nullable in migration 020 but never dropped. Code reads only
the M2M; having two sources of truth for the same relationship caused
a real bug: the generation-trigger endpoint resolved org context only
from the request header, falling back to user keys when the header was
absent — silently bypassing org-level `require_private_keys: False`
settings even when the project was linked to an org via the M2M.

Backfill before drop: any project with `organization_id IS NOT NULL`
that has no matching `project_organizations` row gets one inserted,
using the project's own `created_by` as `assigned_by`. Prod has 7
such rows at write time (2026-05-08); skipping the backfill would
silently lose those org links.

Revision ID: 047_drop_projects_organization_id
Revises: 046_add_recommended_parameters_column
Create Date: 2026-05-08
"""

from sqlalchemy import inspect

import sqlalchemy as sa
from alembic import op


revision = "047_drop_projects_organization_id"
down_revision = "046_add_recommended_parameters_column"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column_name in {col["name"] for col in insp.get_columns(table_name)}


def _fk_constraint_name(table_name: str, column_name: str) -> str | None:
    bind = op.get_bind()
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table_name):
        if column_name in fk.get("constrained_columns", []):
            return fk["name"]
    return None


def upgrade() -> None:
    if not _column_exists("projects", "organization_id"):
        return

    # Backfill any project_organizations rows that the legacy FK implied
    # but the M2M lacks. gen_random_uuid() is available in Postgres 13+;
    # the prod cluster runs 18 (see CLAUDE.md note on the Bitnami drift).
    op.execute(
        """
        INSERT INTO project_organizations (id, project_id, organization_id, assigned_by, created_at)
        SELECT gen_random_uuid()::text,
               p.id,
               p.organization_id,
               p.created_by,
               NOW()
        FROM projects p
        WHERE p.organization_id IS NOT NULL
          AND p.created_by IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM project_organizations po
              WHERE po.project_id = p.id
                AND po.organization_id = p.organization_id
          )
        """
    )

    fk_name = _fk_constraint_name("projects", "organization_id")
    if fk_name:
        op.drop_constraint(fk_name, "projects", type_="foreignkey")

    op.drop_column("projects", "organization_id")


def downgrade() -> None:
    # Restore the column as nullable and best-effort populate from the M2M
    # (pick the oldest link per project — arbitrary but deterministic).
    if _column_exists("projects", "organization_id"):
        return

    op.add_column(
        "projects",
        sa.Column("organization_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "projects_organization_id_fkey",
        "projects",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.execute(
        """
        UPDATE projects p
        SET organization_id = sub.organization_id
        FROM (
            SELECT DISTINCT ON (project_id) project_id, organization_id
            FROM project_organizations
            ORDER BY project_id, created_at ASC
        ) sub
        WHERE sub.project_id = p.id
        """
    )
