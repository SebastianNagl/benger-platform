"""LTI resource links can be bound to one task, or cover a whole collection

``lti_resource_links.task_id`` (nullable, FK ``tasks.id`` ON DELETE SET NULL)
scopes an LMS activity to one task of a Klausurensammlung, so each activity
gets exactly that task's grade.

``lti_resource_links.grade_scope`` (NOT NULL, default ``'exam'``, CHECK
``ck_lti_resource_links_grade_scope``) says what the activity's grade is:

- ``'exam'``: the legacy whole-exam link, only valid while the exam has
  exactly one task.
- ``'task'``: the grade of ``task_id``. A NULL ``task_id`` here means the task
  was deleted (SET NULL), so no constraint ties the scope to ``task_id``.
- ``'collection'``: one gradebook column per task, ``task_id`` stays NULL. The
  per-task columns live in ``lti_task_lineitems``.

``lti_grade_syncs.task_id`` (nullable, FK ``tasks.id`` ON DELETE CASCADE,
index ``ix_lti_grade_syncs_task``) names the task whose column a row feeds;
NULL is the activity's own column. ``uq_lti_grade_sync`` keeps its name and
becomes ``UNIQUE NULLS NOT DISTINCT (resource_link_id, user_id, kind,
task_id)``, so two NULL-task rows for the same link, user and kind still
conflict. Every Postgres we run is 15 or newer (dev 15, tests and prod 18).

New table ``lti_task_lineitems``: one tool-created gradebook column per
(link, task, kind) with its line-item URL, status and last error.

Backfill: every link whose exam has exactly one task is bound to that task,
then every bound link gets ``grade_scope = 'task'``. Links on exams with zero
or several tasks stay ``'exam'`` with NULL ``task_id``.

Downgrade drops the table, deletes the per-task outbox rows (they cannot
exist under the old uniqueness), restores the three-column constraint and
drops the columns. Every step is guarded, so a re-run is a no-op.

Revision ID: 112_lti_resource_link_task
Revises: 111_group_membership_roles
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op


revision = "112_lti_resource_link_task"
down_revision = "111_group_membership_roles"
branch_labels = None
depends_on = None

_LINKS = "lti_resource_links"
_SYNCS = "lti_grade_syncs"
_LINEITEMS = "lti_task_lineitems"

_TASK_INDEX = "ix_lti_resource_links_task"
# The name Postgres gives the unnamed FK that create_all emits for the model.
_TASK_FK = "lti_resource_links_task_id_fkey"

GRADE_SCOPES = ("exam", "task", "collection")
_SCOPE_CHECK = "ck_lti_resource_links_grade_scope"

_SYNC_TASK_INDEX = "ix_lti_grade_syncs_task"
_SYNC_TASK_FK = "lti_grade_syncs_task_id_fkey"
_SYNC_UNIQUE = "uq_lti_grade_sync"

# Same values as ck_lti_resource_links_ai_lineitem_status.
LINEITEM_STATUSES = ("ready", "unavailable", "error", "deleted")
LINEITEM_KINDS = ("final", "ai")

# Bind every still-unbound link to the only task of its exam. Exams with zero
# or several tasks keep NULL (whole-exam link or legacy collection link).
BACKFILL_SQL = """
    UPDATE lti_resource_links rl
       SET task_id = only_task.task_id
      FROM (
            SELECT project_id, MIN(id) AS task_id
              FROM tasks
             GROUP BY project_id
            HAVING COUNT(*) = 1
           ) AS only_task
     WHERE rl.task_id IS NULL
       AND rl.project_id IS NOT NULL
       AND rl.project_id = only_task.project_id
"""

# Runs after BACKFILL_SQL: a bound link grades its task.
SCOPE_BACKFILL_SQL = """
    UPDATE lti_resource_links
       SET grade_scope = 'task'
     WHERE task_id IS NOT NULL
       AND grade_scope = 'exam'
"""


def _in_list(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _tables() -> set:
    return set(inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set:
    return {ix["name"] for ix in inspect(op.get_bind()).get_indexes(table)}


def _checks(table: str) -> set:
    return {ck["name"] for ck in inspect(op.get_bind()).get_check_constraints(table)}


def _sync_unique_width():
    """Column count of uq_lti_grade_sync, or None if it is missing."""
    return op.get_bind().execute(
        text(
            "SELECT cardinality(conkey) FROM pg_constraint "
            "WHERE conrelid = 'lti_grade_syncs'::regclass "
            "AND conname = :name"
        ),
        {"name": _SYNC_UNIQUE},
    ).scalar()


def _upgrade_links() -> None:
    columns = _columns(_LINKS)
    if "task_id" not in columns:
        op.add_column(_LINKS, sa.Column("task_id", sa.String(), nullable=True))
        op.create_foreign_key(
            _TASK_FK, _LINKS, "tasks", ["task_id"], ["id"], ondelete="SET NULL"
        )
    if _TASK_INDEX not in _indexes(_LINKS):
        op.create_index(_TASK_INDEX, _LINKS, ["task_id"])

    if "grade_scope" not in columns:
        op.add_column(
            _LINKS,
            sa.Column(
                "grade_scope",
                sa.String(length=16),
                nullable=False,
                server_default="exam",
            ),
        )
    if _SCOPE_CHECK not in _checks(_LINKS):
        op.create_check_constraint(
            _SCOPE_CHECK, _LINKS, f"grade_scope IN ({_in_list(GRADE_SCOPES)})"
        )

    op.execute(BACKFILL_SQL)
    op.execute(SCOPE_BACKFILL_SQL)


def _upgrade_syncs() -> None:
    if "task_id" not in _columns(_SYNCS):
        op.add_column(_SYNCS, sa.Column("task_id", sa.String(), nullable=True))
        op.create_foreign_key(
            _SYNC_TASK_FK, _SYNCS, "tasks", ["task_id"], ["id"], ondelete="CASCADE"
        )
    if _SYNC_TASK_INDEX not in _indexes(_SYNCS):
        op.create_index(_SYNC_TASK_INDEX, _SYNCS, ["task_id"])

    if _sync_unique_width() != 4:
        if _sync_unique_width() is not None:
            op.drop_constraint(_SYNC_UNIQUE, _SYNCS, type_="unique")
        op.execute(
            f"ALTER TABLE {_SYNCS} ADD CONSTRAINT {_SYNC_UNIQUE} "
            "UNIQUE NULLS NOT DISTINCT (resource_link_id, user_id, kind, task_id)"
        )


def _upgrade_lineitems() -> None:
    if _LINEITEMS not in _tables():
        op.create_table(
            _LINEITEMS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "resource_link_id",
                sa.String(),
                sa.ForeignKey("lti_resource_links.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "task_id",
                sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("lineitem_url", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "resource_link_id", "task_id", "kind", name="uq_lti_task_lineitem"
            ),
            sa.CheckConstraint(
                f"kind IN ({_in_list(LINEITEM_KINDS)})",
                name="ck_lti_task_lineitems_kind",
            ),
            sa.CheckConstraint(
                f"status IN ({_in_list(LINEITEM_STATUSES)})",
                name="ck_lti_task_lineitems_status",
            ),
        )
    indexes = _indexes(_LINEITEMS)
    if "ix_lti_task_lineitems_resource_link" not in indexes:
        op.create_index(
            "ix_lti_task_lineitems_resource_link", _LINEITEMS, ["resource_link_id"]
        )
    # Serves the ON DELETE CASCADE from tasks.
    if "ix_lti_task_lineitems_task" not in indexes:
        op.create_index("ix_lti_task_lineitems_task", _LINEITEMS, ["task_id"])


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    _upgrade_links()
    _upgrade_syncs()
    _upgrade_lineitems()


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    if _LINEITEMS in _tables():
        op.drop_table(_LINEITEMS)

    if "task_id" in _columns(_SYNCS):
        # Per-task rows have no place under the three-column uniqueness.
        op.execute(f"DELETE FROM {_SYNCS} WHERE task_id IS NOT NULL")
    if _sync_unique_width() != 3:
        if _sync_unique_width() is not None:
            op.drop_constraint(_SYNC_UNIQUE, _SYNCS, type_="unique")
        op.create_unique_constraint(
            _SYNC_UNIQUE, _SYNCS, ["resource_link_id", "user_id", "kind"]
        )
    if _SYNC_TASK_INDEX in _indexes(_SYNCS):
        op.drop_index(_SYNC_TASK_INDEX, table_name=_SYNCS)
    if "task_id" in _columns(_SYNCS):
        # Dropping the column drops its FK constraint with it.
        op.drop_column(_SYNCS, "task_id")

    if _SCOPE_CHECK in _checks(_LINKS):
        op.drop_constraint(_SCOPE_CHECK, _LINKS, type_="check")
    if "grade_scope" in _columns(_LINKS):
        op.drop_column(_LINKS, "grade_scope")
    if _TASK_INDEX in _indexes(_LINKS):
        op.drop_index(_TASK_INDEX, table_name=_LINKS)
    if "task_id" in _columns(_LINKS):
        op.drop_column(_LINKS, "task_id")
