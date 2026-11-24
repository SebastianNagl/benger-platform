"""Peer review grant: the project switch, the peer run and its notice type.

Three additive pieces of one feature (a project's participants may grade
each other's submissions, as feedback that never counts as a grade):

- ``projects.peer_review_enabled`` (Boolean, not null, default false): the
  switch. False keeps every existing project as it is.
- The partial unique index for the human-graded singleton run of the peer
  method ``korrektur_peer``, the fourth sibling of migrations 037, 061 and
  122: ``get_or_create_human_eval_run`` upserts against it.
- The ``peer_feedback_received`` value of the ``notificationtype`` enum: the
  author of a submission hears that a fellow participant graded it.

``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction, so it comes
last, after its own ``COMMIT`` (the pattern of 104 and 155). Every step is
idempotent.

Revision ID: 156_peer_review_grant
Revises: 155_add_evaluation_released_notification_type
Create Date: 2026-11-24
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "156_peer_review_grant"
down_revision = "155_add_evaluation_released_notification_type"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"
COLUMN_NAME = "peer_review_enabled"
INDEX_NAME = "uq_human_eval_run_per_project_metric_peer"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                COLUMN_NAME,
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
        ON evaluation_runs (project_id, model_id)
        WHERE model_id = 'human'
          AND (eval_metadata ->> 'evaluation_type') = 'korrektur_peer'
        """
    )
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'peer_feedback_received'")


def downgrade() -> None:
    # The enum value stays: PostgreSQL does not remove enum values easily.
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
