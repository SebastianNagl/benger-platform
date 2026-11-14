"""Pending email change: the new address waits for its confirmation link.

- ``users.pending_email`` (String(255), nullable): the address a user asked
  to change to on the profile page, stored lowercased. ``users.email`` stays
  the login address (and stays verified) until a link mailed to the pending
  address is used.
- ``users.pending_email_token`` (String(64), nullable, indexed): SHA-256 hex
  digest of the opaque token in that link. Only the digest is stored.
- ``users.pending_email_sent_at`` (DateTime tz, nullable): when the mail with
  the current token was accepted for delivery. NULL while a pending address
  has no delivered link; the link expires a fixed time after this.

Existing rows keep NULL in all three columns. Accounts that an earlier
profile change left unverified (address swapped, no mail ever sent) are not
rewritten here: their stored address is the one they typed, so the
verification page's resend control (or "Forgot password") now mails a
working link to it.

Pure additive and idempotent: columns and index are guarded by inspector
checks, so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 134_pending_email_change
Revises: 133_custom_model_concurrency_limit
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "134_pending_email_change"
down_revision = "133_custom_model_concurrency_limit"
branch_labels = None
depends_on = None

_TABLE = "users"
_INDEX = "ix_users_pending_email_token"


def _columns() -> set:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(_TABLE)}


def _indexes() -> set:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if "pending_email" not in columns:
        op.add_column(_TABLE, sa.Column("pending_email", sa.String(255), nullable=True))
    if "pending_email_token" not in columns:
        op.add_column(_TABLE, sa.Column("pending_email_token", sa.String(64), nullable=True))
    if "pending_email_sent_at" not in columns:
        op.add_column(
            _TABLE,
            sa.Column("pending_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        )
    if _INDEX not in _indexes():
        op.create_index(_INDEX, _TABLE, ["pending_email_token"])


def downgrade() -> None:
    if _INDEX in _indexes():
        op.drop_index(_INDEX, table_name=_TABLE)
    columns = _columns()
    for column in ("pending_email_sent_at", "pending_email_token", "pending_email"):
        if column in columns:
            op.drop_column(_TABLE, column)
