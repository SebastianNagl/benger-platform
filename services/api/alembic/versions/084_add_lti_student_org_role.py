"""add student_org_role to lti_platform_registrations

Per-registration policy knob for the org role granted to LMS *learners* on
launch (mirrors ``instructor_org_role``): ``annotator`` (default) makes every
LTI student an ANNOTATOR member of the university's org — org-shared
(non-private, non-archived) exams become their ongoing-training catalog via
the participant tier; ``none`` preserves the old entitlement-only behavior
for privacy-strict tenants. ``server_default`` applies the new default to
existing registrations (decided 2026-07-24); no backfill of memberships —
provisioning self-heals them on each launch.

Pure additive. Idempotent — guards on column existence; safe to re-run.

Revision ID: 084_add_lti_student_org_role
Revises: 083_add_lti_registration_invites
Create Date: 2026-07-24
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa

revision = "084_add_lti_student_org_role"
down_revision = "083_add_lti_registration_invites"
branch_labels = None
depends_on = None

_TABLE = "lti_platform_registrations"
_COLUMN = "student_org_role"


def _has_column() -> bool:
    inspector = inspect(op.get_bind())
    return _COLUMN in {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    if _has_column():
        return
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN,
            sa.String(length=32),
            nullable=False,
            server_default="annotator",
        ),
    )


def downgrade() -> None:
    if not _has_column():
        return
    op.drop_column(_TABLE, _COLUMN)
