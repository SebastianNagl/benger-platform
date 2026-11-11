"""OpenOlat as an LMS vendor, and the NRPS membership URL per activity.

- ``lti_platform_registrations.lms_family`` may now be ``'openolat'``
  (``ck_lti_platform_registrations_lms_family`` widened). OpenOlat 21 is an
  LTI 1.3 platform like Moodle and ILIAS; the tag drives the same admin-UI
  presets and the per-LMS capability table of the extended edition (OpenOlat
  refuses tool-created line items and drops the score comment).
- ``lti_resource_links.context_memberships_url`` (Text, nullable): the Names
  and Role Provisioning Services 2.0 URL the launch advertised
  (``namesroleservice.context_memberships_url``). The extended edition reads
  the course roster live from it for the teacher view; the roster itself is
  never stored.

Schema is platform-owned (split rule). Pure additive and idempotent: the
column and the constraint are guarded by inspector checks, so a database
built from the models (the test DB) runs it as a no-op.

Revision ID: 129_lti_openolat_and_nrps
Revises: 128_feedback_value_follows_release
Create Date: 2026-11-11
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "129_lti_openolat_and_nrps"
down_revision = "128_feedback_value_follows_release"
branch_labels = None
depends_on = None

_REG_TABLE = "lti_platform_registrations"
_CHECK = "ck_lti_platform_registrations_lms_family"
_FAMILIES_NEW = "lms_family IN ('moodle', 'ilias', 'openolat')"
_FAMILIES_OLD = "lms_family IN ('moodle', 'ilias')"

_LINK_TABLE = "lti_resource_links"
_COLUMN = "context_memberships_url"


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def _check_sql(table: str, name: str) -> str | None:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return None
    for ck in insp.get_check_constraints(table):
        if ck["name"] == name:
            return ck.get("sqltext") or ""
    return None


def _set_family_check(expression: str, keep_marker: str) -> None:
    current = _check_sql(_REG_TABLE, _CHECK)
    if current is not None and keep_marker in current:
        return
    if current is not None:
        op.drop_constraint(_CHECK, _REG_TABLE, type_="check")
    op.create_check_constraint(_CHECK, _REG_TABLE, expression)


def upgrade() -> None:
    _set_family_check(_FAMILIES_NEW, "openolat")
    if not _column_exists(_LINK_TABLE, _COLUMN):
        op.add_column(_LINK_TABLE, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    if _column_exists(_LINK_TABLE, _COLUMN):
        op.drop_column(_LINK_TABLE, _COLUMN)
    # Rows tagged openolat would violate the old constraint: untag them first.
    op.execute(f"UPDATE {_REG_TABLE} SET lms_family = NULL WHERE lms_family = 'openolat'")
    current = _check_sql(_REG_TABLE, _CHECK)
    if current is not None and "openolat" in current:
        op.drop_constraint(_CHECK, _REG_TABLE, type_="check")
        op.create_check_constraint(_CHECK, _REG_TABLE, _FAMILIES_OLD)
