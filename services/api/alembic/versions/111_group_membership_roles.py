"""Per-group roles: group memberships and group invitations carry a role

Every group membership now carries its own role (ORG_ADMIN / CONTRIBUTOR /
ANNOTATOR), independent of the org role. On a project attached to a group
the group role decides what the member can do; the org role keeps applying
to org-wide projects and org-level actions.

* ``organization_group_memberships.role`` (``organizationrole``, NOT NULL)
  replaces ``is_group_admin``. The backfill keeps every effective right:
  ``is_group_admin`` -> ORG_ADMIN; otherwise the user's ACTIVE org role in
  the group's org (a plain member acted with their org role on group
  projects); no active org membership -> ANNOTATOR.
* ``invitations.group_role`` (``organizationrole``, nullable, set iff
  ``group_id`` is set) replaces ``invited_as_group_admin``:
  ``invited_as_group_admin`` -> ORG_ADMIN, else the invitation's org role.

* ``import_jobs.organization_group_id`` (nullable, no FK): the group a
  create-new import attaches the new project through.

Downgrade restores the booleans (``role = ORG_ADMIN``). Every step is
guarded, so a re-run is a no-op.

Revision ID: 111_group_membership_roles
Revises: 110_feature_flag_rollout
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "111_group_membership_roles"
down_revision = "110_feature_flag_rollout"
branch_labels = None
depends_on = None

# The enum type organization_memberships.role already uses (migration 001).
_ROLE_ENUM = postgresql.ENUM(
    "ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", name="organizationrole", create_type=False
)


def _columns(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    cols = _columns("organization_group_memberships")
    if "role" not in cols:
        op.add_column(
            "organization_group_memberships",
            sa.Column("role", _ROLE_ENUM, nullable=True),
        )
    if "is_group_admin" in cols:
        op.execute(
            """
            UPDATE organization_group_memberships gm
               SET role = 'ORG_ADMIN'
             WHERE gm.is_group_admin AND gm.role IS NULL
            """
        )
    op.execute(
        """
        UPDATE organization_group_memberships gm
           SET role = om.role
          FROM organization_groups g, organization_memberships om
         WHERE gm.role IS NULL
           AND g.id = gm.group_id
           AND om.organization_id = g.organization_id
           AND om.user_id = gm.user_id
           AND om.is_active
        """
    )
    op.execute(
        "UPDATE organization_group_memberships SET role = 'ANNOTATOR' WHERE role IS NULL"
    )
    op.alter_column("organization_group_memberships", "role", nullable=False)
    if "is_group_admin" in cols:
        op.drop_column("organization_group_memberships", "is_group_admin")

    cols = _columns("invitations")
    if "group_role" not in cols:
        op.add_column("invitations", sa.Column("group_role", _ROLE_ENUM, nullable=True))
    if "invited_as_group_admin" in cols:
        op.execute(
            """
            UPDATE invitations SET group_role = 'ORG_ADMIN'
             WHERE group_id IS NOT NULL AND group_role IS NULL AND invited_as_group_admin
            """
        )
    op.execute(
        """
        UPDATE invitations SET group_role = role
         WHERE group_id IS NOT NULL AND group_role IS NULL
        """
    )
    op.execute("UPDATE invitations SET group_role = NULL WHERE group_id IS NULL")
    if "invited_as_group_admin" in cols:
        op.drop_column("invitations", "invited_as_group_admin")

    if "organization_group_id" not in _columns("import_jobs"):
        op.add_column(
            "import_jobs",
            sa.Column("organization_group_id", sa.String(), nullable=True),
        )


def downgrade() -> None:
    if "organization_group_id" in _columns("import_jobs"):
        op.drop_column("import_jobs", "organization_group_id")

    cols = _columns("organization_group_memberships")
    if "is_group_admin" not in cols:
        op.add_column(
            "organization_group_memberships",
            sa.Column(
                "is_group_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        if "role" in cols:
            op.execute(
                "UPDATE organization_group_memberships "
                "SET is_group_admin = (role = 'ORG_ADMIN')"
            )
    if "role" in cols:
        op.drop_column("organization_group_memberships", "role")

    cols = _columns("invitations")
    if "invited_as_group_admin" not in cols:
        op.add_column(
            "invitations",
            sa.Column(
                "invited_as_group_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        if "group_role" in cols:
            op.execute(
                "UPDATE invitations SET invited_as_group_admin = "
                "(group_id IS NOT NULL AND group_role = 'ORG_ADMIN')"
            )
    if "group_role" in cols:
        op.drop_column("invitations", "group_role")
