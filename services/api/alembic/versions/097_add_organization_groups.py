"""add organization groups (org → group → user layer)

Groups partition project visibility and provider API keys INSIDE an org so
that sub-units (e.g. university chairs) stop sharing projects and keys while
remaining one organization. Everything is opt-in via nullable ``group_id``
columns — NULL means "whole org", so existing orgs behave exactly as before.

- ``organization_groups``: the group entity, unique name per org.
- ``organization_group_memberships``: user↔group, with ``is_group_admin``
  (orthogonal to the org-level role — the org role stays the capability
  axis, the group is the visibility axis).
- ``project_organizations.group_id``: attachment scope, via a COMPOSITE FK
  ``(organization_id, group_id) → organization_groups(organization_id, id)``
  so the DB itself guarantees an attachment can only carry a group of its
  own org (MATCH SIMPLE: NULL group_id rows are unconstrained). Deliberately
  NO ondelete action (NOT RESTRICT): org→groups and org→project_organizations
  are both CASCADE and fire in unspecified order during an org delete;
  NO ACTION defers the FK check to end-of-statement so the org cascade
  works, while a direct group delete with live attachments still fails
  (no silent visibility widening).
- ``organization_api_keys.group_id``: key scope, same composite FK but
  CASCADE (a group's keys die with the group; SET NULL would silently
  promote a group key to org-wide). The plain ``unique_org_provider_key
  (organization_id, provider)`` constraint is replaced by a partial-unique
  pair because NULLs are distinct to a plain unique constraint:
    * ``uq_org_provider_key_orgwide (org, provider) WHERE group_id IS NULL``
    * ``uq_org_provider_key_group (org, provider, group_id) WHERE group_id IS NOT NULL``
- ``invitations.group_id`` (SET NULL — a deleted group degrades a pending
  invite to a plain org invite) + ``invited_as_group_admin``.
- ``lti_platform_registrations.group_id``: a group-scoped LMS (Moodle/ILIAS)
  registration provisions launched users INTO the group and links launched
  projects group-scoped — a chair's LMS never leaks into the rest of the
  university org. Composite FK, NO ondelete (live LMS wiring blocks group
  deletion, mirroring the org-level RESTRICT).

Idempotent — guards on table/column/index existence; safe to re-run.

Revision ID: 097_add_organization_groups
Revises: 096_add_import_job_cloud_source
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "097_add_organization_groups"
down_revision = "096_add_import_job_cloud_source"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    return table in inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _index_exists(table: str, index: str) -> bool:
    return index in {ix["name"] for ix in inspect(op.get_bind()).get_indexes(table)}


def _unique_constraint_exists(table: str, name: str) -> bool:
    return name in {
        uc["name"] for uc in inspect(op.get_bind()).get_unique_constraints(table)
    }


def upgrade() -> None:
    if not _table_exists("organization_groups"):
        op.create_table(
            "organization_groups",
            sa.Column("id", sa.String(), primary_key=True, index=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("organization_id", "name", name="uq_org_group_name"),
            sa.UniqueConstraint("organization_id", "id", name="uq_org_group_org_scope"),
        )

    if not _table_exists("organization_group_memberships"):
        op.create_table(
            "organization_group_memberships",
            sa.Column("id", sa.String(), primary_key=True, index=True),
            sa.Column(
                "group_id",
                sa.String(),
                sa.ForeignKey("organization_groups.id", ondelete="CASCADE"),
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
            sa.Column(
                "is_group_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("group_id", "user_id", name="uq_group_membership"),
        )

    # project_organizations.group_id — composite FK, NO ondelete (docstring).
    if not _column_exists("project_organizations", "group_id"):
        op.add_column(
            "project_organizations", sa.Column("group_id", sa.String(), nullable=True)
        )
        op.create_foreign_key(
            "fk_project_organizations_group_scope",
            "project_organizations",
            "organization_groups",
            ["organization_id", "group_id"],
            ["organization_id", "id"],
        )
    if not _index_exists("project_organizations", "ix_project_organizations_group_id"):
        op.create_index(
            "ix_project_organizations_group_id", "project_organizations", ["group_id"]
        )

    # organization_api_keys.group_id (composite FK, CASCADE) + unique swap.
    if not _column_exists("organization_api_keys", "group_id"):
        op.add_column(
            "organization_api_keys", sa.Column("group_id", sa.String(), nullable=True)
        )
        op.create_foreign_key(
            "fk_organization_api_keys_group_scope",
            "organization_api_keys",
            "organization_groups",
            ["organization_id", "group_id"],
            ["organization_id", "id"],
            ondelete="CASCADE",
        )
    if not _index_exists("organization_api_keys", "ix_organization_api_keys_group_id"):
        op.create_index(
            "ix_organization_api_keys_group_id", "organization_api_keys", ["group_id"]
        )
    if _unique_constraint_exists("organization_api_keys", "unique_org_provider_key"):
        op.drop_constraint(
            "unique_org_provider_key", "organization_api_keys", type_="unique"
        )
    if not _index_exists("organization_api_keys", "uq_org_provider_key_orgwide"):
        op.execute(
            """CREATE UNIQUE INDEX uq_org_provider_key_orgwide
               ON organization_api_keys (organization_id, provider)
               WHERE group_id IS NULL"""
        )
    if not _index_exists("organization_api_keys", "uq_org_provider_key_group"):
        op.execute(
            """CREATE UNIQUE INDEX uq_org_provider_key_group
               ON organization_api_keys (organization_id, provider, group_id)
               WHERE group_id IS NOT NULL"""
        )

    # lti_platform_registrations.group_id — a group-scoped LMS registration
    # provisions launched users into the group and links launched projects
    # group-scoped. Composite FK, NO ondelete (mirrors project_organizations;
    # a group with live LMS wiring must not be deletable).
    if not _column_exists("lti_platform_registrations", "group_id"):
        op.add_column(
            "lti_platform_registrations", sa.Column("group_id", sa.String(), nullable=True)
        )
        op.create_foreign_key(
            "fk_lti_platform_registrations_group_scope",
            "lti_platform_registrations",
            "organization_groups",
            ["organization_id", "group_id"],
            ["organization_id", "id"],
        )
    if not _index_exists("lti_platform_registrations", "ix_lti_platform_registrations_group_id"):
        op.create_index(
            "ix_lti_platform_registrations_group_id",
            "lti_platform_registrations",
            ["group_id"],
        )

    # lti_registration_invites.group_id — carried into the auto-created
    # registration by Dynamic Registration; SET NULL (invites are ephemera).
    if not _column_exists("lti_registration_invites", "group_id"):
        op.add_column(
            "lti_registration_invites",
            sa.Column(
                "group_id",
                sa.String(),
                sa.ForeignKey(
                    "organization_groups.id",
                    ondelete="SET NULL",
                    name="fk_lti_registration_invites_group_id",
                ),
                nullable=True,
            ),
        )
    if not _index_exists("lti_registration_invites", "ix_lti_registration_invites_group_id"):
        op.create_index(
            "ix_lti_registration_invites_group_id",
            "lti_registration_invites",
            ["group_id"],
        )

    # invitations.group_id + invited_as_group_admin.
    if not _column_exists("invitations", "group_id"):
        op.add_column(
            "invitations",
            sa.Column(
                "group_id",
                sa.String(),
                sa.ForeignKey(
                    "organization_groups.id",
                    ondelete="SET NULL",
                    name="fk_invitations_group_id",
                ),
                nullable=True,
            ),
        )
    if not _index_exists("invitations", "ix_invitations_group_id"):
        op.create_index("ix_invitations_group_id", "invitations", ["group_id"])
    if not _column_exists("invitations", "invited_as_group_admin"):
        op.add_column(
            "invitations",
            sa.Column(
                "invited_as_group_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    # Restoring the plain unique constraint fails if group-scoped key rows
    # exist — correct failure mode: those rows have no pre-groups meaning
    # and must be resolved by hand before downgrading.
    if _column_exists("invitations", "invited_as_group_admin"):
        op.drop_column("invitations", "invited_as_group_admin")
    if _column_exists("invitations", "group_id"):
        op.drop_column("invitations", "group_id")

    if _index_exists("organization_api_keys", "uq_org_provider_key_group"):
        op.execute("DROP INDEX uq_org_provider_key_group")
    if _index_exists("organization_api_keys", "uq_org_provider_key_orgwide"):
        op.execute("DROP INDEX uq_org_provider_key_orgwide")
    if _column_exists("organization_api_keys", "group_id"):
        op.drop_column("organization_api_keys", "group_id")
    if not _unique_constraint_exists("organization_api_keys", "unique_org_provider_key"):
        op.create_unique_constraint(
            "unique_org_provider_key",
            "organization_api_keys",
            ["organization_id", "provider"],
        )

    if _column_exists("lti_registration_invites", "group_id"):
        op.drop_column("lti_registration_invites", "group_id")

    if _column_exists("lti_platform_registrations", "group_id"):
        op.drop_column("lti_platform_registrations", "group_id")

    if _column_exists("project_organizations", "group_id"):
        op.drop_column("project_organizations", "group_id")

    if _table_exists("organization_group_memberships"):
        op.drop_table("organization_group_memberships")
    if _table_exists("organization_groups"):
        op.drop_table("organization_groups")
