"""add users.pending_activation_email

Account-activation flow for passwordless LTI-provisioned students: when a
sub-only account (synthetic ``@lti.invalid`` address) requests standalone
access, the address they enter is parked here and only adopted onto
``users.email`` when the activation link is clicked — receiving the mail IS
the mailbox-ownership proof. NULL for everyone else; cleared on activation.

Idempotent — guards on column existence; safe to re-run. Mirrors the 081
guard pattern (users.vertretbar_onboarding_completed_at).

Revision ID: 085_add_pending_activation_email
Revises: 084_add_lti_student_org_role
Create Date: 2026-07-24
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "085_add_pending_activation_email"
down_revision = "084_add_lti_student_org_role"
branch_labels = None
depends_on = None


TABLE_NAME = "users"
COLUMN_NAME = "pending_activation_email"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
