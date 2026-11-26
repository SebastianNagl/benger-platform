"""Bug reports: problems reported from inside the app.

New table ``bug_reports``: one row per report sent with "Report a problem"
(the reporter, SET NULL when the account is deleted, or an optional contact
address for a report sent without a session; title, what happened, what was
expected; the technical context as JSONB; the optional screenshot's storage
key, type and size; the delivery state ``pending`` | ``delivered`` |
``failed`` | ``stored`` with attempts, error, issue URL and number), with
indexes for the newest-first list, the status filter and the reporter.

Purely additive; downgrade drops the table. Every step is guarded, so a
re-run is a no-op.

Revision ID: 160_bug_reports
Revises: 159_annotation_original_result
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op


revision = "160_bug_reports"
down_revision = "159_annotation_original_result"
branch_labels = None
depends_on = None

TABLE = "bug_reports"


def upgrade() -> None:
    if inspect(op.get_bind()).has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "reporter_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("contact_email", sa.String(254), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("context", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("screenshot_key", sa.String(), nullable=True),
        sa.Column("screenshot_content_type", sa.String(64), nullable=True),
        sa.Column("screenshot_size", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivery_error", sa.Text(), nullable=True),
        sa.Column("issue_url", sa.String(), nullable=True),
        sa.Column("issue_number", sa.Integer(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'delivered', 'failed', 'stored')",
            name="ck_bug_reports_status",
        ),
    )
    op.create_index("ix_bug_reports_created", TABLE, ["created_at"])
    op.create_index("ix_bug_reports_status_created", TABLE, ["status", "created_at"])
    op.create_index("ix_bug_reports_reporter", TABLE, ["reporter_id"])


def downgrade() -> None:
    if inspect(op.get_bind()).has_table(TABLE):
        op.drop_table(TABLE)
