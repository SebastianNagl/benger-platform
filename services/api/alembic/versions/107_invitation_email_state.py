"""invitations: invitation-mail delivery state

The ``invitations`` table kept no record of whether its mail actually went
out. The only traces were a worker log line and the Celery result in Redis,
which expires after a day, and the admin UI showed "invite sent" as soon as
the task was queued. When the mail worker was OOM-killed, nobody could tell
a delivered invitation from a lost one, and the only repair was to cancel and
create the invitation again.

Four nullable-or-defaulted columns, no data rewrite:

- ``email_sent_at``: set once SendGrid accepted the message.
- ``email_last_attempt_at``: when a send was last attempted or queued. The
  API stamps it at queue time and the worker stamps it again per attempt, so
  the resend guard keeps a clock even while the worker is down.
- ``email_attempts``: how many send attempts the worker started. ``NOT NULL
  DEFAULT 0``, so existing rows read 0.
- ``email_last_error``: last failure reason, cleared on a confirmed send.

Backfill: none on purpose. Existing rows keep NULL timestamps, which the API
reports as ``unknown`` rather than ``failed``. We cannot know after the fact
which of the old invitations were delivered, and guessing ``sent`` from
``created_at`` would hide exactly the losses this change exists to surface.

``invitations`` is a small, quiet table (writes only on invite create, accept
and cancel), so the ALTERs take the exclusive lock for a moment. A
``lock_timeout`` still guards it: on a timeout the migration fails and the
pod retries instead of queueing requests behind the ALTER.

Revision ID: 107_invitation_email_state
Revises: 106_users_anon_and_eval_updated_at
Create Date: 2026-09-17
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "107_invitation_email_state"
down_revision = "106_users_anon_and_eval_updated_at"
branch_labels = None
depends_on = None

_TABLE = "invitations"

# name -> column factory. Every column is additive and independently
# idempotent, so a partially applied migration finishes cleanly on a re-run.
_COLUMNS = {
    "email_sent_at": lambda: sa.Column(
        "email_sent_at", sa.DateTime(timezone=True), nullable=True
    ),
    "email_last_attempt_at": lambda: sa.Column(
        "email_last_attempt_at", sa.DateTime(timezone=True), nullable=True
    ),
    "email_attempts": lambda: sa.Column(
        "email_attempts", sa.Integer(), nullable=False, server_default="0"
    ),
    "email_last_error": lambda: sa.Column(
        "email_last_error", sa.Text(), nullable=True
    ),
}


def _existing_columns() -> set:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(_TABLE)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    present = _existing_columns()
    if not present:
        # Table missing entirely: nothing this migration can attach to.
        return
    for name, factory in _COLUMNS.items():
        if name not in present:
            op.add_column(_TABLE, factory())


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    present = _existing_columns()
    for name in reversed(list(_COLUMNS)):
        if name in present:
            op.drop_column(_TABLE, name)
