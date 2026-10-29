"""add organization_groups.jurisdiction

Per-group override of the organization's ``settings.jurisdiction`` (the
legal system that picks the project wizard's jurisdiction-specific project
types), e.g. a French-law group inside a German faculty:

- NULL (default): the group follows its organization.
- 'DE' / 'FR': projects created in the group get that jurisdiction's types.

The organization-wide value stays in ``organizations.settings``; the
effective rule lives in ``org_jurisdiction.group_jurisdiction``. Existing
groups get NULL, so nothing changes until someone sets a group override.

Idempotent: guards on column existence, safe to re-run (091 pattern).

Revision ID: 120_group_jurisdiction
Revises: 119_korrektur_reservations
Create Date: 2026-10-29
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "120_group_jurisdiction"
down_revision = "119_korrektur_reservations"
branch_labels = None
depends_on = None


TABLE_NAME = "organization_groups"
COLUMN_NAME = "jurisdiction"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.String(8), nullable=True))


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
