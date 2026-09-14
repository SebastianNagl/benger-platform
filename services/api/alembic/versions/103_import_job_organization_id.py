"""add import_jobs.organization_id (owning org of a create-new import)

A create-new project import used to hand the new project to the importer's
FIRST active membership, so importing inside one org's context could land the
copy in another org. ``POST /project-imports`` now records the org named by the
request's org context here, and the worker creates the project in that org
(membership re-checked at creation time).

Nullable: NULL means no org context ("private" or absent), which keeps the
first-active-membership fallback, and nested / cloud imports into an existing
project never set it. SET NULL on org delete keeps the job history row.

Idempotent: guards on column existence, like 096.

Revision ID: 103_import_job_organization_id
Revises: 102_korrektur_custom_graded_field
Create Date: 2026-09-14
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "103_import_job_organization_id"
down_revision = "102_korrektur_custom_graded_field"
branch_labels = None
depends_on = None

TABLE_NAME = "import_jobs"
COLUMN_NAME = "organization_id"


def _has_column() -> bool:
    inspector = inspect(op.get_bind())
    return any(c["name"] == COLUMN_NAME for c in inspector.get_columns(TABLE_NAME))


def upgrade() -> None:
    if not _has_column():
        op.add_column(
            TABLE_NAME,
            sa.Column(
                COLUMN_NAME,
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE_NAME, COLUMN_NAME)
