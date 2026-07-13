"""add LTI 1.3 (Moodle integration) tables

LTI 1.3 tool-side persistence: organizations register their Moodle site
(platform) once, place BenGER exams as LTI activities, and get AI grades
pushed back through AGS. The schema is platform-owned (split rule: ALL DB
tables live in benger-platform); the proprietary protocol logic — OIDC
third-party login, id_token validation, deep linking, AGS grade passback —
lives in ``benger_extended``. The community edition only carries this
forward-compatible schema.

- ``lti_platform_registrations``: one row per (issuer, client_id) — a Moodle
  site's OIDC/JWKS endpoints plus per-tenant policy knobs. ``organization_id``
  uses ``ondelete=RESTRICT``: deleting an org with live LMS wiring must be an
  explicit two-step act.
- ``lti_deployments``: known deployment ids under a registration; launches
  for unknown deployments are rejected. Unique (registration, deployment_id).
- ``lti_resource_links``: a placed Moodle activity mapped to a project
  (``project_id`` SET NULL keeps the row as an audit/config record). Caches
  the AGS lineitem endpoints/scopes from the launch claims.
- ``lti_user_links``: platform ``sub`` -> BenGER user mapping with a
  minimized claims cache and GDPR consent provenance. CASCADE on ``user_id``
  (right-to-erasure self-cleans).
- ``lti_grade_syncs``: the grade-passback outbox, one row per (resource link,
  student), driven pending -> synced/failed with bounded retries.
  ``ix_lti_grade_syncs_due`` serves the worker's due-scan.

Tables are created in dependency order (registrations -> deployments ->
resource_links -> user_links -> grade_syncs). Pure additive.
Idempotent — guards on table/index existence; safe to re-run.

Revision ID: 076_add_lti_tables
Revises: 075_default_checkpoints_enabled
Create Date: 2026-07-13
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "076_add_lti_tables"
down_revision = "075_default_checkpoints_enabled"
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


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    # ----------------------------------------------------------------- #
    # lti_platform_registrations — one Moodle site per (issuer, client_id)
    # ----------------------------------------------------------------- #
    if not _table_exists("lti_platform_registrations"):
        op.create_table(
            "lti_platform_registrations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("issuer", sa.String(length=500), nullable=False),
            sa.Column("client_id", sa.String(length=255), nullable=False),
            sa.Column("auth_login_url", sa.String(length=500), nullable=False),
            sa.Column("auth_token_url", sa.String(length=500), nullable=False),
            sa.Column("jwks_uri", sa.String(length=500), nullable=False),
            sa.Column(
                "link_existing_users_by_email",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "instructor_org_role",
                sa.String(length=32),
                nullable=False,
                server_default="contributor",
            ),
            sa.Column(
                "status", sa.String(length=16), nullable=False, server_default="active"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "issuer", "client_id", name="uq_lti_registration_issuer_client"
            ),
        )
    _create_index_if_missing(
        "ix_lti_platform_registrations_organization_id",
        "lti_platform_registrations",
        ["organization_id"],
    )
    _create_index_if_missing(
        "ix_lti_platform_registrations_issuer",
        "lti_platform_registrations",
        ["issuer"],
    )
    _create_index_if_missing(
        "ix_lti_platform_registrations_status",
        "lti_platform_registrations",
        ["status"],
    )

    # ----------------------------------------------------------------- #
    # lti_deployments — known deployment ids under a registration
    # ----------------------------------------------------------------- #
    if not _table_exists("lti_deployments"):
        op.create_table(
            "lti_deployments",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "registration_id",
                sa.String(),
                sa.ForeignKey("lti_platform_registrations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("deployment_id", sa.String(length=255), nullable=False),
            sa.Column(
                "status", sa.String(length=16), nullable=False, server_default="active"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "registration_id", "deployment_id", name="uq_lti_deployment"
            ),
        )
    _create_index_if_missing(
        "ix_lti_deployments_registration_id", "lti_deployments", ["registration_id"]
    )

    # ----------------------------------------------------------------- #
    # lti_resource_links — placed Moodle activity -> project mapping
    # ----------------------------------------------------------------- #
    if not _table_exists("lti_resource_links"):
        op.create_table(
            "lti_resource_links",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "registration_id",
                sa.String(),
                sa.ForeignKey("lti_platform_registrations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("deployment_id", sa.String(length=255), nullable=False),
            sa.Column("resource_link_id", sa.String(length=255), nullable=False),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("context_id", sa.String(length=255), nullable=True),
            sa.Column("context_title", sa.String(length=500), nullable=True),
            sa.Column("resource_title", sa.String(length=500), nullable=True),
            sa.Column("lineitem_url", sa.Text(), nullable=True),
            sa.Column("lineitems_url", sa.Text(), nullable=True),
            sa.Column("ags_scopes", sa.JSON(), nullable=True),
            sa.Column(
                "sync_ai_grades", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "linked_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "registration_id",
                "deployment_id",
                "resource_link_id",
                name="uq_lti_resource_link",
            ),
        )
    _create_index_if_missing(
        "ix_lti_resource_links_registration_id",
        "lti_resource_links",
        ["registration_id"],
    )
    _create_index_if_missing(
        "ix_lti_resource_links_project", "lti_resource_links", ["project_id"]
    )

    # ----------------------------------------------------------------- #
    # lti_user_links — platform sub -> BenGER user (consent provenance)
    # ----------------------------------------------------------------- #
    if not _table_exists("lti_user_links"):
        op.create_table(
            "lti_user_links",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "registration_id",
                sa.String(),
                sa.ForeignKey("lti_platform_registrations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sub", sa.String(length=255), nullable=False),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("claims", sa.JSON(), nullable=True),
            sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consent_version", sa.String(length=32), nullable=True),
            sa.Column("last_launch_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("registration_id", "sub", name="uq_lti_user_link"),
        )
    _create_index_if_missing("ix_lti_user_links_user_id", "lti_user_links", ["user_id"])

    # ----------------------------------------------------------------- #
    # lti_grade_syncs — AGS grade-passback outbox
    # ----------------------------------------------------------------- #
    if not _table_exists("lti_grade_syncs"):
        op.create_table(
            "lti_grade_syncs",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "resource_link_id",
                sa.String(),
                sa.ForeignKey("lti_resource_links.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "status", sa.String(length=16), nullable=False, server_default="pending"
            ),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_synced_score", sa.Float(), nullable=True),
            sa.Column("last_synced_hash", sa.String(length=64), nullable=True),
            sa.Column(
                "source_task_evaluation_id",
                sa.String(),
                sa.ForeignKey("task_evaluations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "resource_link_id", "user_id", name="uq_lti_grade_sync"
            ),
        )
    _create_index_if_missing(
        "ix_lti_grade_syncs_resource_link_id", "lti_grade_syncs", ["resource_link_id"]
    )
    _create_index_if_missing(
        "ix_lti_grade_syncs_due", "lti_grade_syncs", ["status", "next_retry_at"]
    )


def downgrade() -> None:
    # Reverse dependency order (children first).
    if _table_exists("lti_grade_syncs"):
        op.drop_table("lti_grade_syncs")
    if _table_exists("lti_user_links"):
        op.drop_table("lti_user_links")
    if _table_exists("lti_resource_links"):
        op.drop_table("lti_resource_links")
    if _table_exists("lti_deployments"):
        op.drop_table("lti_deployments")
    if _table_exists("lti_platform_registrations"):
        op.drop_table("lti_platform_registrations")
