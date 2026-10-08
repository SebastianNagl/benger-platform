"""add organization_groups.require_private_keys

Per-group override of the organization's ``settings.require_private_keys``
("who pays for AI calls"):

- NULL (default): the group follows its organization.
- False: the organization provides keys for the group's projects (the
  group's own key first, then the organization-wide key).
- True: members pay with their personal keys on the group's projects.

The organization-wide switch stays in ``organizations.settings``; the
effective rule lives in ``org_groups.require_private_keys_for``. Existing
groups get NULL, so nothing changes until someone sets a group override.

Idempotent: guards on column existence, safe to re-run (091 pattern).

Revision ID: 115_group_require_private_keys
Revises: 114_user_bundesland_onboarding
Create Date: 2026-10-08
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "115_group_require_private_keys"
down_revision = "114_user_bundesland_onboarding"
branch_labels = None
depends_on = None


TABLE_NAME = "organization_groups"
COLUMN_NAME = "require_private_keys"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.Boolean(), nullable=True))


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
