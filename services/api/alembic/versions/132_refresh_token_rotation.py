"""Refresh token rotation: token families and the rotation timestamp.

- ``refresh_tokens.family_id`` (String, nullable, indexed): the id of the
  first token of a login session. Every refresh replaces the presented
  token with a successor in the same family, so a whole session can be
  revoked at once when a replaced token is presented again (reuse of a
  stolen token). Rows from before this revision keep NULL, which the code
  reads as "the family is the row's own id", so open sessions keep working.
- ``refresh_tokens.rotated_at`` (DateTime with time zone, nullable): when
  the token was replaced by its successor. NULL for live tokens and for
  tokens ended by logout.

Pure additive and idempotent: each column is guarded by an inspector check,
so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 132_refresh_token_rotation
Revises: 131_model_reasoning_columns
Create Date: 2026-11-13
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "132_refresh_token_rotation"
down_revision = "131_model_reasoning_columns"
branch_labels = None
depends_on = None

_TABLE = "refresh_tokens"
_INDEX = "ix_refresh_tokens_family_id"


def _columns() -> set:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(_TABLE)}


def _indexes() -> set:
    return {ix["name"] for ix in inspect(op.get_bind()).get_indexes(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if "family_id" not in columns:
        op.add_column(_TABLE, sa.Column("family_id", sa.String(), nullable=True))
    if "rotated_at" not in columns:
        op.add_column(
            _TABLE, sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True)
        )
    if _INDEX not in _indexes():
        op.create_index(_INDEX, _TABLE, ["family_id"])


def downgrade() -> None:
    if _INDEX in _indexes():
        op.drop_index(_INDEX, table_name=_TABLE)
    columns = _columns()
    for column in ("rotated_at", "family_id"):
        if column in columns:
            op.drop_column(_TABLE, column)
