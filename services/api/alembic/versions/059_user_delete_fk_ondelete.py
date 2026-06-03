"""add ON DELETE rules to user FK constraints so user deletion self-cleans

Deleting a user 500'd with a ForeignKeyViolation because most FKs referencing
``users.id`` were created with no ``ON DELETE`` action (RESTRICT). The reported
case was ``korrektur_comments`` (constraint still named ``feedback_comments_*``
from before the table rename), but ~30 FKs were RESTRICT.

This migration only converts the cases where the DB can safely self-clean:
  - nullable reference columns          -> ``SET NULL``
  - per-user ephemeral data             -> ``CASCADE``

NOT-NULL ownership/audit columns (projects.created_by, korrektur_comments.
created_by, templates, etc.) intentionally stay RESTRICT — a user delete must
never silently destroy authored content. Those are reassigned to a fallback
superadmin in application code (``auth_module/user_service.py:delete_user``).

Defensive by design: the actual constraint name is looked up per (table,
column) instead of hardcoded (legacy ``feedback_comments_*`` / ``annotation_
timer_sessions_*`` names exist), and tables absent from a ``create_all``-built
schema are skipped. Re-running is a no-op.

Revision ID: 059_user_delete_fk_ondelete
Revises: 058_add_export_import_jobs
Create Date: 2026-06-03
"""

from sqlalchemy import inspect

from alembic import op


revision = "059_user_delete_fk_ondelete"
down_revision = "058_add_export_import_jobs"
branch_labels = None
depends_on = None


# Nullable reference columns -> NULL the reference when the user is deleted.
SET_NULL_FKS = [
    ("annotations", "reviewed_by"),
    ("default_evaluation_configs", "updated_by"),
    ("default_prompts", "updated_by"),
    ("korrektur_comments", "resolved_by"),
    ("project_reports", "published_by"),
    ("tags", "created_by"),
    ("users", "email_verified_by_id"),  # self-referential (verifier)
]

# Per-user ephemeral data -> delete with the user.
CASCADE_FKS = [
    ("notifications", "user_id"),
    ("notification_preferences", "user_id"),
    ("user_column_preferences", "user_id"),
    ("refresh_tokens", "user_id"),
]


def _existing_users_fk(insp, table: str, column: str):
    """Return the name of the FK on table.column referencing users, or None."""
    for fk in insp.get_foreign_keys(table):
        if fk.get("referred_table") == "users" and column in fk.get(
            "constrained_columns", []
        ):
            return fk.get("name")
    return None


def _set_ondelete(table: str, column: str, ondelete) -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return
    existing = _existing_users_fk(insp, table, column)
    if existing:
        op.drop_constraint(existing, table, type_="foreignkey")
    op.create_foreign_key(
        f"{table}_{column}_fkey",
        table,
        "users",
        [column],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    for table, column in SET_NULL_FKS:
        _set_ondelete(table, column, "SET NULL")
    for table, column in CASCADE_FKS:
        _set_ondelete(table, column, "CASCADE")


def downgrade() -> None:
    for table, column in SET_NULL_FKS + CASCADE_FKS:
        _set_ondelete(table, column, None)
