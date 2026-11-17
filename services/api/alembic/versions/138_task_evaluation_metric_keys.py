"""Mirror the cell columns and metric keys of every task evaluation

The evaluation counters (project tiles, project list, dashboard, the hourly
``project_summaries`` refresh) count distinct (answer, evaluation config,
metric) cells. They need only the top-level keys of
``task_evaluations.metrics``, but ``jsonb_object_keys(metrics)`` has to
de-TOAST the whole blob of every row: on the dev database (1.36M rows,
12 GB) one project-list page took 49 s, past the API's 15 s statement
timeout, and the hourly refresh hit its 600 s soft limit before writing a
single row.

- ``task_evaluation_metric_keys``: one narrow row per task evaluation (its
  id, run, annotation, generation, evaluation config and the sorted
  top-level keys of its metrics, ``[]`` when metrics is not an object). The
  counters read only this table.
- ``task_evaluation_metric_keys(jsonb)``: the IMMUTABLE SQL function that
  derives the keys.
- ``trg_task_evaluation_metric_keys`` (row) and
  ``trg_task_evaluation_metric_keys_truncate`` (statement) on
  ``task_evaluations``: insert and every update of a mirrored column upsert
  the row (the ON DELETE SET NULL of annotation and generation included),
  delete and truncate remove it, for every writer (ORM, raw-SQL migrations
  and scripts, the overlay).
- ``ix_task_evaluation_metric_keys_evaluation_id``, built last: readers
  (``aggregate_summaries._metric_keys_filled``) take it as the sign that the
  table is complete.

The statements are the same as ``models.TASK_EVALUATION_METRIC_KEYS_DDL``,
kept verbatim here because a migration never imports the models.

Why a mirror table and not a column on ``task_evaluations``: filling a new
column rewrites every row, and each non-HOT row version also goes into all
eleven indexes of the table; on a dev copy that ran at about 1300 rows/s
(17 minutes for 1.36M rows, inside the API's startup migration) and grew
the heap by half. Filling the mirror only reads ``task_evaluations``: about
5800 rows/s on the same copy.

Operational note: the schema steps are catalog-only (5 s lock_timeout,
retried by env.py). The fill then runs outside that transaction
(``autocommit_block``) in physical order, 2000 heap blocks of
``task_evaluations`` per short transaction (``INSERT ... ON CONFLICT DO
NOTHING``), so nothing waits on it: a row written meanwhile gets its mirror
from the trigger, and an upsert by the trigger always wins over the older
snapshot a batch read. A row deleted between a batch's snapshot and its
insert could leave an orphan, so the fill ends with an anti-join cleanup;
the index follows ``CONCURRENTLY``. Expect about 3 minutes per million task
evaluations.

Idempotent: every step is guarded (IF NOT EXISTS, OR REPLACE, ON CONFLICT,
catalog checks), so a database built from the models (the test DB, which
gets table, function and triggers from ``create_all``) and a re-run after an
interrupted migration are both safe.

Revision ID: 138_task_evaluation_metric_keys
Revises: 137_task_rubric_review
Create Date: 2026-11-17
"""

from sqlalchemy import text

from alembic import op

revision = "138_task_evaluation_metric_keys"
down_revision = "137_task_rubric_review"
branch_labels = None
depends_on = None

_TABLE = "task_evaluation_metric_keys"
_INDEX = "ix_task_evaluation_metric_keys_evaluation_id"
# ~16 MB of task_evaluations heap per batch: about 13000 rows on dev.
FILL_BLOCKS = 2000

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS task_evaluation_metric_keys (
    task_evaluation_id VARCHAR NOT NULL PRIMARY KEY,
    evaluation_id VARCHAR NOT NULL,
    annotation_id VARCHAR,
    generation_id VARCHAR,
    evaluation_config_id VARCHAR,
    metric_keys JSONB NOT NULL
)
"""
_KEYS_FUNCTION = """
CREATE OR REPLACE FUNCTION task_evaluation_metric_keys(m jsonb) RETURNS jsonb AS $fn$
    SELECT CASE WHEN jsonb_typeof(m) = 'object'
        THEN COALESCE((SELECT jsonb_agg(k ORDER BY k) FROM jsonb_object_keys(m) AS k), '[]'::jsonb)
        ELSE '[]'::jsonb
    END
$fn$ LANGUAGE sql IMMUTABLE PARALLEL SAFE
"""
_SYNC_FUNCTION = """
CREATE OR REPLACE FUNCTION task_evaluation_metric_keys_sync() RETURNS trigger AS $fn$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        TRUNCATE task_evaluation_metric_keys;
        RETURN NULL;
    END IF;
    IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND NEW.id IS DISTINCT FROM OLD.id) THEN
        DELETE FROM task_evaluation_metric_keys WHERE task_evaluation_id = OLD.id;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        INSERT INTO task_evaluation_metric_keys (
            task_evaluation_id, evaluation_id, annotation_id, generation_id,
            evaluation_config_id, metric_keys
        ) VALUES (
            NEW.id, NEW.evaluation_id, NEW.annotation_id, NEW.generation_id,
            NEW.evaluation_config_id, task_evaluation_metric_keys(NEW.metrics)
        )
        ON CONFLICT (task_evaluation_id) DO UPDATE SET
            evaluation_id = EXCLUDED.evaluation_id,
            annotation_id = EXCLUDED.annotation_id,
            generation_id = EXCLUDED.generation_id,
            evaluation_config_id = EXCLUDED.evaluation_config_id,
            metric_keys = EXCLUDED.metric_keys;
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql
"""
_ROW_TRIGGER = """
CREATE OR REPLACE TRIGGER trg_task_evaluation_metric_keys
AFTER INSERT OR DELETE OR UPDATE OF
    id, evaluation_id, annotation_id, generation_id, evaluation_config_id, metrics
ON task_evaluations
FOR EACH ROW EXECUTE FUNCTION task_evaluation_metric_keys_sync()
"""
_TRUNCATE_TRIGGER = """
CREATE OR REPLACE TRIGGER trg_task_evaluation_metric_keys_truncate
AFTER TRUNCATE ON task_evaluations
FOR EACH STATEMENT EXECUTE FUNCTION task_evaluation_metric_keys_sync()
"""
# One batch: the task evaluations stored in heap blocks [:first, :last).
_FILL_SQL = """
INSERT INTO task_evaluation_metric_keys (
    task_evaluation_id, evaluation_id, annotation_id, generation_id,
    evaluation_config_id, metric_keys
)
SELECT te.id, te.evaluation_id, te.annotation_id, te.generation_id,
       te.evaluation_config_id, task_evaluation_metric_keys(te.metrics)
FROM task_evaluations te
WHERE te.ctid >= CAST('(' || CAST(:first AS text) || ',0)' AS tid)
  AND te.ctid < CAST('(' || CAST(:last AS text) || ',0)' AS tid)
ON CONFLICT (task_evaluation_id) DO NOTHING
"""
_CLEANUP_SQL = """
DELETE FROM task_evaluation_metric_keys mk
WHERE NOT EXISTS (SELECT 1 FROM task_evaluations te WHERE te.id = mk.task_evaluation_id)
"""
_CREATE_INDEX = """
CREATE INDEX CONCURRENTLY ix_task_evaluation_metric_keys_evaluation_id
ON task_evaluation_metric_keys (evaluation_id)
"""


def _scalar(bind, sql: str, **params):
    return bind.execute(text(sql), params).scalar()


def _index_state(bind):
    """None (missing), True (valid) or False (left invalid by an
    interrupted concurrent build)."""
    return _scalar(
        bind,
        "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = :name",
        name=_INDEX,
    )


def add_schema() -> None:
    """Table, function and triggers: catalog-only, inside the migration
    transaction."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(_CREATE_TABLE)
    op.execute(_KEYS_FUNCTION)
    op.execute(_SYNC_FUNCTION)
    op.execute(_ROW_TRIGGER)
    op.execute(_TRUNCATE_TRIGGER)


def fill(bind, blocks: int = FILL_BLOCKS) -> int:
    """Mirror every task evaluation not mirrored yet, ``blocks`` heap blocks
    per statement, then drop rows whose task evaluation is gone. Returns the
    number of rows added. On an autocommit connection each batch commits on
    its own. The walk covers the blocks the table had when it started; rows
    written later get their mirror from the trigger."""
    end = int(
        _scalar(
            bind,
            "SELECT pg_relation_size('task_evaluations') / current_setting('block_size')::int",
        )
    )
    added = 0
    for first in range(0, end + 1, blocks):
        result = bind.execute(text(_FILL_SQL), {"first": first, "last": first + blocks})
        added += max(result.rowcount or 0, 0)
    bind.execute(text(_CLEANUP_SQL))
    return added


def build_index(bind) -> None:
    state = _index_state(bind)
    if state is True:
        return
    if state is False:
        bind.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}"))
    # Parallel maintenance workers share memory through /dev/shm, which is
    # 64 MB in a default Docker container (the dev stack); a parallel
    # VACUUM of a dev database copy failed there. A serial build needs none.
    bind.execute(text("SET max_parallel_maintenance_workers = 0"))
    try:
        bind.execute(text(_CREATE_INDEX))
    finally:
        bind.execute(text("RESET max_parallel_maintenance_workers"))


def upgrade() -> None:
    add_schema()
    if _index_state(op.get_bind()) is True:
        return
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        fill(bind)
        build_index(bind)
        bind.execute(text(f"ANALYZE {_TABLE}"))


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_task_evaluation_metric_keys ON task_evaluations")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_task_evaluation_metric_keys_truncate ON task_evaluations"
    )
    op.execute("DROP FUNCTION IF EXISTS task_evaluation_metric_keys_sync()")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
    op.execute("DROP FUNCTION IF EXISTS task_evaluation_metric_keys(jsonb)")
