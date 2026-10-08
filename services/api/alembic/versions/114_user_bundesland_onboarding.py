"""add users.exam_bundesland and users.onboarding_state

Two profile columns for the first-visit onboarding (extended edition):

- ``exam_bundesland`` (String(2), nullable): the German state the user writes
  the Staatsexamen in, as one of the 16 two-letter codes (BW, BY, BE, BB, HB,
  HH, HE, MV, NI, NW, RP, SL, SN, ST, SH, TH). Written through
  ``PUT /auth/profile``; validated by the ``Bundesland`` Literal in
  auth_schemas.py. Profile data, and later the default for the state-specific
  exam interface. Never an authorization input.
- ``onboarding_state`` (JSON, nullable): the first-visit setup modal and tour
  progress, e.g.::

      {"setup_completed_at": "2026-10-08T10:00:00+00:00",
       "tours": {"student": 1, "contributor": 1}}

  NULL means the user has never seen the onboarding. Shape is enforced by
  ``OnboardingStateUpdate``; the only writer is ``PUT /auth/me/onboarding``,
  which deep-merges into the stored object. Plain JSON like every other
  ``users`` JSON column: read and written whole, never queried.

Idempotent: guards on column existence, safe to re-run (091 pattern).

Revision ID: 114_user_bundesland_onboarding
Revises: 113_submission_files
Create Date: 2026-10-08
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "114_user_bundesland_onboarding"
down_revision = "113_submission_files"
branch_labels = None
depends_on = None


TABLE_NAME = "users"
COLUMNS = (
    ("exam_bundesland", sa.String(2)),
    ("onboarding_state", sa.JSON()),
)


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    for name, type_ in COLUMNS:
        if not _column_exists(TABLE_NAME, name):
            op.add_column(TABLE_NAME, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _type in reversed(COLUMNS):
        if _column_exists(TABLE_NAME, name):
            op.drop_column(TABLE_NAME, name)
