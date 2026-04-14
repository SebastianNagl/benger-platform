"""Add require_confirm_before_submit to projects

Project-level setting that requires annotators to check a confirmation
checkbox before submitting annotations. Bypassed on auto-submit after
timer expiry.

Revision ID: 024_add_require_confirm_before_submit
Revises: 023_remove_glm_api_key_column
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "024_add_require_confirm_before_submit"
down_revision = "023_remove_glm_api_key_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "require_confirm_before_submit",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "require_confirm_before_submit")
