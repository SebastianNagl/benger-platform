"""Give the unused ``projects.is_published`` column a server default

``projects.is_published`` was never read: no access check, list filter or
student view looks at it. Who sees a project is decided by its visibility
(private, organization or group attachment, public), archiving and its
access window. The flag still showed up in the project API, so it looked
like a publish switch that did nothing. This release stops mapping and
serving it. Report publication (``project_reports.is_published``) is a
different column and stays.

The column is left in place in this release. Migrations run before the
rollout, so the old pods, whose model still maps the column, keep serving
for a while and must find it, and a ``helm rollback`` must find it too.
Upgrade only sets ``server_default`` FALSE on it (when it exists), so
inserts from the new model, which no longer names the column, get FALSE
instead of violating NOT NULL. A later release drops the column once no
deployed code maps it. Downgrade removes the server default again.

Revision ID: 153_project_is_published_server_default
Revises: 152_platform_flags_tum_rollout
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "153_project_is_published_server_default"
down_revision = "152_platform_flags_tum_rollout"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_column("projects", "is_published"):
        op.alter_column("projects", "is_published", server_default=sa.false())


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_column("projects", "is_published"):
        op.alter_column("projects", "is_published", server_default=None)
