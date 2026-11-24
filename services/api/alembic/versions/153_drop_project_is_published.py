"""Drop the unused ``projects.is_published`` column

``projects.is_published`` was never read: no access check, list filter or
student view looks at it. Who sees a project is decided by its visibility
(private, organization or group attachment, public), archiving and its
access window. The flag still showed up in the project API, so it looked
like a publish switch that did nothing. Report publication
(``project_reports.is_published``) is a different column and stays.

Upgrade drops the column when it exists (a database built from the models,
such as the test DB, never had it after this change). Downgrade adds it back
as NOT NULL with the default FALSE, which is the value every project had
unless a script set it; the stored values are not restored, since no code
read them.

Revision ID: 153_drop_project_is_published
Revises: 152_platform_flags_tum_rollout
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "153_drop_project_is_published"
down_revision = "152_platform_flags_tum_rollout"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_column("projects", "is_published"):
        op.drop_column("projects", "is_published")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if not _has_column("projects", "is_published"):
        op.add_column(
            "projects",
            sa.Column(
                "is_published", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
