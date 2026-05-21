"""Composite index supporting the notifications SSE cursor query.

The cursor query from `routers/notifications.py:stream_notifications` is:

    SELECT ... FROM notifications
    WHERE user_id = :uid
      AND ((created_at > :cdt) OR (created_at = :cdt AND id > :cid))
    ORDER BY created_at ASC, id ASC
    LIMIT 50

Notifications had no index on `user_id` at all (just the PK on `id`), so
every SSE poll did a full-table scan + sort. A composite on
`(user_id, created_at, id)` is exactly the planner's preferred shape — it
supports both the `WHERE user_id = ?` predicate and the `ORDER BY
created_at, id` so the LIMIT can stop early without a sort step.

Idempotent — guarded against re-application.

Revision ID: 056_notifications_cursor_index
Revises: 055_completed_generations_summary
Create Date: 2026-05-20
"""

from sqlalchemy import inspect

from alembic import op


revision = "056_notifications_cursor_index"
down_revision = "055_completed_generations_summary"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_notifications_user_created_id"


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _index_exists("notifications", INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            "notifications",
            ["user_id", "created_at", "id"],
        )


def downgrade() -> None:
    if _index_exists("notifications", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="notifications")
