"""Add public visibility tier to projects.

Adds a third visibility state alongside the existing private/org-assigned
model. A public project is visible and interactable by every authenticated
user regardless of org membership. The publisher picks `public_role` —
either ANNOTATOR or CONTRIBUTOR — which determines what non-creator,
non-superadmin visitors are allowed to do (settings edit always stays
with creator + superadmins, enforced separately in authorization).

Three CHECK constraints encode the invariants:
- visibility-exclusive: a project cannot be both private and public.
- public_role valid: only ANNOTATOR or CONTRIBUTOR (or NULL).
- public_role required when public: NULL only when is_public=false.

Revision ID: 035_add_project_public_visibility
Revises: 034_add_korrektur_assigned_notification_type
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "035_add_project_public_visibility"
down_revision = "034_add_korrektur_assigned_notification_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "is_public",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "public_role",
            sa.String(length=32),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_projects_visibility_exclusive",
        "projects",
        "NOT (is_private AND is_public)",
    )
    op.create_check_constraint(
        "ck_projects_public_role_valid",
        "projects",
        "public_role IS NULL OR public_role IN ('ANNOTATOR', 'CONTRIBUTOR')",
    )
    op.create_check_constraint(
        "ck_projects_public_role_required_when_public",
        "projects",
        "NOT is_public OR public_role IS NOT NULL",
    )
    op.create_index(
        "ix_projects_is_public",
        "projects",
        ["is_public"],
        postgresql_where=sa.text("is_public = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_projects_is_public", table_name="projects")
    op.drop_constraint(
        "ck_projects_public_role_required_when_public", "projects", type_="check"
    )
    op.drop_constraint("ck_projects_public_role_valid", "projects", type_="check")
    op.drop_constraint("ck_projects_visibility_exclusive", "projects", type_="check")
    op.drop_column("projects", "public_role")
    op.drop_column("projects", "is_public")
