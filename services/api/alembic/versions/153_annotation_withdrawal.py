"""Withdrawal of a submission: ``annotations.withdrawn_*`` and ``submission_returned``

A handed-in submission can be withdrawn by its author or returned to the
author by a project editor. The row and its data stay; the withdrawal sets
``was_cancelled`` (so every reader that skips cancelled rows skips it, and the
partial unique index ``uq_annotations_active_task_user`` lets the author hand
in again) and records who did it, when and why:

- ``annotations.withdrawn_at`` (timestamptz), ``withdrawn_by`` (users,
  ``SET NULL`` so deleting the account never blocks) and
  ``withdrawal_reason`` (text). All nullable without a default, so adding
  them rewrites nothing and no existing row changes; a row cancelled before
  this migration keeps NULL in all three.
- The ``notificationtype`` enum value ``submission_returned`` (the author's
  notice when an editor returns the submission). ``ALTER TYPE ... ADD VALUE``
  cannot run inside a transaction, hence the COMMIT before it (same pattern
  as migration 034).

Idempotent: every step is guarded, so a database built from the models (the
test DB) runs it as a no-op.

Revision ID: 153_annotation_withdrawal
Revises: 152_platform_flags_tum_rollout
Create Date: 2026-11-24
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa

revision = "153_annotation_withdrawal"
down_revision = "152_platform_flags_tum_rollout"
branch_labels = None
depends_on = None

_TABLE = "annotations"
_FK = "fk_annotations_withdrawn_by_users"


def _columns() -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(_TABLE)}


def _foreign_keys() -> set:
    return {fk["name"] for fk in inspect(op.get_bind()).get_foreign_keys(_TABLE)}


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    columns = _columns()
    if "withdrawn_at" not in columns:
        op.add_column(_TABLE, sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True))
    if "withdrawn_by" not in columns:
        op.add_column(_TABLE, sa.Column("withdrawn_by", sa.String(), nullable=True))
    if "withdrawal_reason" not in columns:
        op.add_column(_TABLE, sa.Column("withdrawal_reason", sa.Text(), nullable=True))
    has_users_fk = any(
        fk["referred_table"] == "users" and fk["constrained_columns"] == ["withdrawn_by"]
        for fk in inspect(op.get_bind()).get_foreign_keys(_TABLE)
    )
    if not has_users_fk:
        op.create_foreign_key(
            _FK, _TABLE, "users", ["withdrawn_by"], ["id"], ondelete="SET NULL"
        )

    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'submission_returned'")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _FK in _foreign_keys():
        op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    columns = _columns()
    for column in ("withdrawal_reason", "withdrawn_by", "withdrawn_at"):
        if column in columns:
            op.drop_column(_TABLE, column)
    # PostgreSQL cannot drop a single enum value; ``submission_returned``
    # stays, unused by the code before this migration.
