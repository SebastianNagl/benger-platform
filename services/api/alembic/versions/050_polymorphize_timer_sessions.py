"""Rename `annotation_timer_sessions` → `timer_sessions` and polymorphize.

Issue #30 PR 3 — korrektur timer. The existing annotation-only timer infra
(model, worker, frontend slot) is exactly the shape we need for korrektur
per-item timing. Rather than build a parallel table, we rename the existing
one and add a `target_type` (default `'task'` for legacy annotation rows)
+ `target_id` (nullable) so the same row shape can carry both annotation
sessions (target_id NULL) and korrektur sessions (target_id pointing at
the annotation_id or generation_id being graded).

Idempotent. Existing annotation rows get `target_type='task'`, `target_id=NULL`
on rename — the column default takes care of it.

The unique constraint widens to include `(target_type, target_id)` so a
grader can time multiple korrektur targets within the same task without
the constraint colliding. Annotation rows (`target_id IS NULL`) still
uniqueify on (task_id, user_id, target_type='task').

Revision ID: 050_polymorphize_timer_sessions
Revises: 049_unique_task_evaluation_cell_per_grader
Create Date: 2026-05-18
"""

from sqlalchemy import inspect

from alembic import op


revision = "050_polymorphize_timer_sessions"
down_revision = "049_unique_task_evaluation_cell_per_grader"
branch_labels = None
depends_on = None


OLD_TABLE = "annotation_timer_sessions"
NEW_TABLE = "timer_sessions"
OLD_CONSTRAINT = "unique_timer_session"
NEW_CONSTRAINT = "unique_timer_session_per_target"


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return name in {c["name"] for c in insp.get_unique_constraints(table)}


def upgrade() -> None:
    # 1. Rename the table if it still has the old name (idempotent).
    if _table_exists(OLD_TABLE) and not _table_exists(NEW_TABLE):
        op.rename_table(OLD_TABLE, NEW_TABLE)

    if not _table_exists(NEW_TABLE):
        # Table doesn't exist on either name — nothing to migrate (fresh
        # install will create directly under the new name via the model).
        return

    # 2. Add target_type with default 'task' for legacy annotation rows.
    if not _column_exists(NEW_TABLE, "target_type"):
        op.execute(
            f"ALTER TABLE {NEW_TABLE} ADD COLUMN target_type "
            "VARCHAR NOT NULL DEFAULT 'task'"
        )

    # 3. Add target_id nullable (NULL for annotation/task-level rows;
    #    annotation_id or generation_id for korrektur rows).
    if not _column_exists(NEW_TABLE, "target_id"):
        op.execute(
            f"ALTER TABLE {NEW_TABLE} ADD COLUMN target_id VARCHAR NULL"
        )

    # 4. Drop the old (task_id, user_id) unique constraint — too narrow now
    #    that a grader can time multiple per-target korrektur sessions on
    #    the same task.
    if _constraint_exists(NEW_TABLE, OLD_CONSTRAINT):
        op.drop_constraint(OLD_CONSTRAINT, NEW_TABLE, type_="unique")

    # 5. Add the wider unique constraint including target_type/target_id.
    #    For NULL target_id (annotation sessions), Postgres treats NULL as
    #    distinct, so two annotators would normally collide — but the
    #    target_type='task' part still gives us the original semantic
    #    (one annotation timer session per (task, user)) by coincidence,
    #    since NULL == NULL is false in unique constraints. Use a partial
    #    expression-index instead for annotation rows.
    if not _constraint_exists(NEW_TABLE, NEW_CONSTRAINT):
        # COALESCE makes the NULL-target case still de-dup correctly
        # alongside the per-target korrektur case.
        op.execute(
            f"CREATE UNIQUE INDEX {NEW_CONSTRAINT} "
            f"ON {NEW_TABLE} (task_id, user_id, target_type, "
            f"COALESCE(target_id, '__no_target__'))"
        )


def downgrade() -> None:
    # Reverse-step: drop wider unique index, drop columns, rename back.
    bind = op.get_bind()
    insp = inspect(bind)
    if NEW_CONSTRAINT in {ix["name"] for ix in insp.get_indexes(NEW_TABLE)}:
        op.execute(f"DROP INDEX IF EXISTS {NEW_CONSTRAINT}")

    if _column_exists(NEW_TABLE, "target_id"):
        op.execute(f"ALTER TABLE {NEW_TABLE} DROP COLUMN target_id")
    if _column_exists(NEW_TABLE, "target_type"):
        op.execute(f"ALTER TABLE {NEW_TABLE} DROP COLUMN target_type")

    if not _constraint_exists(NEW_TABLE, OLD_CONSTRAINT):
        op.create_unique_constraint(
            OLD_CONSTRAINT, NEW_TABLE, ["task_id", "user_id"],
        )

    if _table_exists(NEW_TABLE) and not _table_exists(OLD_TABLE):
        op.rename_table(NEW_TABLE, OLD_TABLE)
