"""one active annotation per (task, user): partial unique index

Strict-timer exam tasks have two concurrent writers for the same (task, user):
the client auto-submit (``POST /annotations`` -> ``create_annotation``) and the
server-side timer worker (``tasks.auto_submit_expired_timer``). They were
coordinated only by a transaction-scoped advisory lock, which turned out to be
fragile: the worker task name ``tasks.auto_submit_expired_timer`` is registered
by BOTH the platform ``tasks.py`` (no lock) and the extended overlay's
``register_tasks`` (locked), and which implementation wins at worker startup —
and therefore whether the lock is taken at all — is non-deterministic. When the
unlocked implementation wins, the worker races the client and both INSERT a row,
so a single student ends up with 2+ duplicate annotations (each then graded ->
wasted tokens, inflated counts).

This adds the DB-level guarantee the advisory lock couldn't reliably provide: a
partial unique index over ``(task_id, completed_by)`` where ``was_cancelled =
false``. The second concurrent INSERT now fails with IntegrityError, which both
writers catch and resolve (the endpoint updates the surviving row in place —
latest content wins; the worker treats it as "client beat us" and skips).
Partial on ``was_cancelled = false`` so a withdrawn annotation never blocks a
legitimate resubmit.

Before creating the index we dedup any pre-existing duplicates so the unique
constraint can be built: keep the richest row per (task, user) (most grades,
then longest result, then newest), reassign the duplicates' unique
``(evaluation_id, field_name)`` task_evaluations onto the kept row (preserving
multi-run grading data — this matters for research projects like Benchathon),
drop the now-redundant grades, and soft-cancel the duplicate annotations.

Idempotent — ``CREATE UNIQUE INDEX IF NOT EXISTS`` + the dedup only touches rows
that are still duplicated, so re-running is a no-op.

Revision ID: 064_annotation_active_unique_index
Revises: 063_generation_pause_resume_retry
Create Date: 2026-06-30
"""

from sqlalchemy import inspect

from alembic import op


revision = "064_annotation_active_unique_index"
down_revision = "063_generation_pause_resume_retry"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_annotations_active_task_user"

# Rank duplicates: per (task, completed_by), rn=1 is the row we keep (most
# grades, then longest result, then newest); rn>1 are the duplicates to fold in.
_RANKED = """
    WITH ranked AS (
        SELECT a.id, a.task_id, a.completed_by,
               row_number() OVER (
                   PARTITION BY a.task_id, a.completed_by
                   ORDER BY (SELECT count(*) FROM task_evaluations te
                             WHERE te.annotation_id = a.id) DESC,
                            length(a.result::text) DESC,
                            a.created_at DESC
               ) AS rn
        FROM annotations a
        WHERE a.was_cancelled = false AND a.completed_by IS NOT NULL
    ),
    keep AS (
        SELECT task_id, completed_by, id AS keep_id FROM ranked WHERE rn = 1
    ),
    dup AS (
        SELECT r.id AS dup_id, k.keep_id
        FROM ranked r JOIN keep k USING (task_id, completed_by)
        WHERE r.rn > 1
    )
"""


def _index_exists() -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return INDEX_NAME in {ix["name"] for ix in insp.get_indexes("annotations")}


def upgrade() -> None:
    # 1. Reassign each duplicate's grades to the kept row, but only those the
    #    kept row doesn't already carry (preserve distinct multi-run gradings).
    op.execute(
        _RANKED
        + """
        UPDATE task_evaluations te
        SET annotation_id = dup.keep_id
        FROM dup
        WHERE te.annotation_id = dup.dup_id
          AND NOT EXISTS (
              SELECT 1 FROM task_evaluations x
              WHERE x.annotation_id = dup.keep_id
                AND x.evaluation_id = te.evaluation_id
                AND x.field_name IS NOT DISTINCT FROM te.field_name
          );
        """
    )
    # 2. Drop the now-redundant grades still pointing at the duplicates.
    op.execute(
        _RANKED
        + """
        DELETE FROM task_evaluations te
        USING dup
        WHERE te.annotation_id = dup.dup_id;
        """
    )
    # 3. Soft-cancel the duplicate annotations (reversible; the partial index
    #    ignores was_cancelled = true rows).
    op.execute(
        _RANKED
        + """
        UPDATE annotations
        SET was_cancelled = true
        WHERE id IN (SELECT dup_id FROM dup);
        """
    )
    # 4. Build the guarantee.
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} "
        "ON annotations (task_id, completed_by) "
        "WHERE was_cancelled = false;"
    )


def downgrade() -> None:
    if _index_exists():
        op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME};")
