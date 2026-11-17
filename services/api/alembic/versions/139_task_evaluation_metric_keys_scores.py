"""Mirror task, field, creation time and lite metrics of every task evaluation

The project-level by-task-model grid of the evaluations page
(``GET /api/evaluations/projects/{id}/results/by-task-model``) ranked every
task evaluation of the project and then read each survivor's metrics blob
to build its score. On the ltvm2 dev copy (same data as production) ZJS
Fälle has 160k task evaluations whose llm_judge_falloesung rows carry
about 7 KB of compressed judge rubric text each: building the lite metrics
of the 13k surviving rows of one judge config took 9.8 s of a 10.2 s
statement, and with the metric filter the page sends, the request returned
500 at the API's 15 s statement timeout.

This migration widens the trigger-kept mirror ``task_evaluation_metric_keys``
(migration 138) with everything that grid reads, so it never touches
``task_evaluations``:

- ``task_id``, ``field_name``, ``created_at``: the cell key and the
  latest-wins order of the grid's ``row_number()`` window.
- ``metrics_lite``: ``task_evaluation_metrics_lite(metrics)``, the metrics
  without the heavy nested fields score extraction never reads (``details``,
  ``method``, ``raw``, ``justification``). The read-time projection
  (``routers/evaluations/metrics_lite.py``) calls the same function from now
  on, so both give identical dicts.

``task_evaluation_metric_keys_sync()`` writes the new columns and the row
trigger also fires on updates of ``task_id``, ``field_name`` and
``created_at``. The statements are the same as
``models.TASK_EVALUATION_METRIC_KEYS_DDL``, kept verbatim here because a
migration never imports the models.

Operational note: the schema step is catalog-only (nullable columns without
a default, function and trigger replacement; 5 s lock_timeout, retried by
env.py). The fill then runs outside that transaction (``autocommit_block``)
like migration 138's: 2000 heap blocks of ``task_evaluations`` per short
transaction, upserting the mirror row of every task evaluation whose new
columns are still empty. A row written meanwhile gets them from the
trigger, and the fill never overwrites a filled row. A catch-up pass takes
rows a concurrent writer committed behind the walk, the orphan cleanup of
138 follows, and the columns become NOT NULL, so a mirror at this revision
is always complete. Last, indexes on ``generation_id`` and ``annotation_id``
are built ``CONCURRENTLY`` for the grid's joins to the latest generation and
annotation of each cell; without them the planner, misestimating both
sides, joined them with a filtered nested loop (307M comparisons, 12.5 s on
ZJS Fälle). The fill reads every metrics blob once:
expect about 3 minutes per million task evaluations, and a mirror about
twice its size until autovacuum reclaims the old row versions.

Idempotent: every step is guarded (IF NOT EXISTS, OR REPLACE, the filled
check, a NOT NULL and index check), so a database built from the models (the test DB)
and a re-run after an interrupted migration are both safe.

Revision ID: 139_task_evaluation_metric_keys_scores
Revises: 138_task_evaluation_metric_keys
Create Date: 2026-11-17
"""

from sqlalchemy import text

from alembic import op

revision = "139_task_evaluation_metric_keys_scores"
down_revision = "138_task_evaluation_metric_keys"
branch_labels = None
depends_on = None

_TABLE = "task_evaluation_metric_keys"
_NEW_COLUMNS = ("task_id", "field_name", "created_at", "metrics_lite")
# For the grid's joins to the latest generation / annotation of each cell.
_INDEXES = {
    "ix_task_evaluation_metric_keys_generation_id": "generation_id",
    "ix_task_evaluation_metric_keys_annotation_id": "annotation_id",
}
# ~16 MB of task_evaluations heap per batch: about 13000 rows on dev.
FILL_BLOCKS = 2000

_ADD_COLUMNS = """
ALTER TABLE task_evaluation_metric_keys
    ADD COLUMN IF NOT EXISTS task_id VARCHAR,
    ADD COLUMN IF NOT EXISTS field_name VARCHAR,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS metrics_lite JSONB
"""
_LITE_FUNCTION = """
CREATE OR REPLACE FUNCTION task_evaluation_metrics_lite(m jsonb) RETURNS jsonb AS $fn$
    SELECT COALESCE(jsonb_object_agg(k,
        CASE WHEN jsonb_typeof(v) = 'object'
             THEN v - 'details' - 'method' - 'raw' - 'justification'
             ELSE v END
      ), '{}'::jsonb)
    FROM jsonb_each(CASE WHEN jsonb_typeof(m) = 'object' THEN m ELSE '{}'::jsonb END) AS j(k, v)
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
            evaluation_config_id, metric_keys, task_id, field_name, created_at,
            metrics_lite
        ) VALUES (
            NEW.id, NEW.evaluation_id, NEW.annotation_id, NEW.generation_id,
            NEW.evaluation_config_id, task_evaluation_metric_keys(NEW.metrics),
            NEW.task_id, NEW.field_name, NEW.created_at,
            task_evaluation_metrics_lite(NEW.metrics)
        )
        ON CONFLICT (task_evaluation_id) DO UPDATE SET
            evaluation_id = EXCLUDED.evaluation_id,
            annotation_id = EXCLUDED.annotation_id,
            generation_id = EXCLUDED.generation_id,
            evaluation_config_id = EXCLUDED.evaluation_config_id,
            metric_keys = EXCLUDED.metric_keys,
            task_id = EXCLUDED.task_id,
            field_name = EXCLUDED.field_name,
            created_at = EXCLUDED.created_at,
            metrics_lite = EXCLUDED.metrics_lite;
    END IF;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql
"""
_ROW_TRIGGER = """
CREATE OR REPLACE TRIGGER trg_task_evaluation_metric_keys
AFTER INSERT OR DELETE OR UPDATE OF
    id, evaluation_id, annotation_id, generation_id, evaluation_config_id, metrics,
    task_id, field_name, created_at
ON task_evaluations
FOR EACH ROW EXECUTE FUNCTION task_evaluation_metric_keys_sync()
"""
# Migration 138's sync function and trigger, restored by downgrade().
_SYNC_FUNCTION_138 = """
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
_ROW_TRIGGER_138 = """
CREATE OR REPLACE TRIGGER trg_task_evaluation_metric_keys
AFTER INSERT OR DELETE OR UPDATE OF
    id, evaluation_id, annotation_id, generation_id, evaluation_config_id, metrics
ON task_evaluations
FOR EACH ROW EXECUTE FUNCTION task_evaluation_metric_keys_sync()
"""

# Upsert the full mirror row of the selected task evaluations; a row whose
# new columns are filled (by the trigger, or an earlier batch) is left alone.
_UPSERT_SELECT = """
INSERT INTO task_evaluation_metric_keys (
    task_evaluation_id, evaluation_id, annotation_id, generation_id,
    evaluation_config_id, metric_keys, task_id, field_name, created_at, metrics_lite
)
SELECT te.id, te.evaluation_id, te.annotation_id, te.generation_id,
       te.evaluation_config_id, task_evaluation_metric_keys(te.metrics),
       te.task_id, te.field_name, te.created_at, task_evaluation_metrics_lite(te.metrics)
FROM task_evaluations te
{where}
ON CONFLICT (task_evaluation_id) DO UPDATE SET
    task_id = EXCLUDED.task_id,
    field_name = EXCLUDED.field_name,
    created_at = EXCLUDED.created_at,
    metrics_lite = EXCLUDED.metrics_lite
WHERE task_evaluation_metric_keys.created_at IS NULL
"""
# One batch: the task evaluations stored in heap blocks [:first, :last).
_FILL_SQL = _UPSERT_SELECT.replace(
    "{where}",
    "WHERE te.ctid >= CAST('(' || CAST(:first AS text) || ',0)' AS tid)\n"
    "  AND te.ctid < CAST('(' || CAST(:last AS text) || ',0)' AS tid)",
)
# Mirror rows still empty: written behind the walk by a transaction that
# began before the new trigger function. Driven from the narrow mirror, so
# the pass under the lock in set_not_null() stays short. (Every task
# evaluation has a mirror row since migration 138; the walk adds any that
# is missing.)
_CATCH_UP_SQL = _UPSERT_SELECT.replace(
    "{where}",
    "WHERE te.id IN (SELECT mk.task_evaluation_id FROM task_evaluation_metric_keys mk\n"
    "                WHERE mk.created_at IS NULL)",
)
_CLEANUP_SQL = """
DELETE FROM task_evaluation_metric_keys mk
WHERE NOT EXISTS (SELECT 1 FROM task_evaluations te WHERE te.id = mk.task_evaluation_id)
"""
_SET_NOT_NULL = """
ALTER TABLE task_evaluation_metric_keys
    ALTER COLUMN task_id SET NOT NULL,
    ALTER COLUMN field_name SET NOT NULL,
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN metrics_lite SET NOT NULL
"""


def _scalar(bind, sql: str, **params):
    return bind.execute(text(sql), params).scalar()


def _index_state(bind, name: str):
    """None (missing), True (valid) or False (left invalid by an
    interrupted concurrent build)."""
    return _scalar(
        bind,
        "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = :name",
        name=name,
    )


def is_complete(bind) -> bool:
    """Whether every new column is NOT NULL and both indexes are valid."""
    if any(_index_state(bind, name) is not True for name in _INDEXES):
        return False
    return (
        _scalar(
            bind,
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = "
            "current_schema() AND table_name = :table AND column_name = ANY(:cols) "
            "AND is_nullable = 'NO'",
            table=_TABLE,
            cols=list(_NEW_COLUMNS),
        )
        == len(_NEW_COLUMNS)
    )


def add_schema() -> None:
    """Columns, function and trigger: catalog-only, inside the migration
    transaction."""
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(_ADD_COLUMNS)
    op.execute(_LITE_FUNCTION)
    op.execute(_SYNC_FUNCTION)
    op.execute(_ROW_TRIGGER)


def fill(bind, blocks: int = FILL_BLOCKS) -> int:
    """Fill the new columns of every mirror row that lacks them (adding a
    missing mirror row on the way), ``blocks`` heap blocks of
    ``task_evaluations`` per statement, then catch up and drop orphans.
    Returns the number of rows written. On an autocommit connection each
    batch commits on its own."""
    end = int(
        _scalar(
            bind,
            "SELECT pg_relation_size('task_evaluations') / current_setting('block_size')::int",
        )
    )
    written = 0
    for first in range(0, end + 1, blocks):
        result = bind.execute(text(_FILL_SQL), {"first": first, "last": first + blocks})
        written += max(result.rowcount or 0, 0)
    result = bind.execute(text(_CATCH_UP_SQL))
    written += max(result.rowcount or 0, 0)
    bind.execute(text(_CLEANUP_SQL))
    return written


def set_not_null(bind) -> None:
    """Inside a transaction: hold off writers, take the rows committed since
    the catch-up and make the new columns NOT NULL (which checks that every
    row is filled)."""
    bind.execute(text("SET LOCAL lock_timeout = '5s'"))
    bind.execute(text("LOCK TABLE task_evaluation_metric_keys IN SHARE ROW EXCLUSIVE MODE"))
    bind.execute(text(_CATCH_UP_SQL))
    bind.execute(text(_SET_NOT_NULL))


def build_indexes(bind) -> None:
    """On an autocommit connection: build the missing indexes concurrently
    (rebuilding one an interrupted build left invalid)."""
    # Serial builds: parallel maintenance workers need /dev/shm, which is
    # 64 MB in a default Docker container (see migration 138).
    bind.execute(text("SET max_parallel_maintenance_workers = 0"))
    try:
        for name, column in _INDEXES.items():
            state = _index_state(bind, name)
            if state is True:
                continue
            if state is False:
                bind.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
            bind.execute(text(f"CREATE INDEX CONCURRENTLY {name} ON {_TABLE} ({column})"))
    finally:
        bind.execute(text("RESET max_parallel_maintenance_workers"))


def upgrade() -> None:
    add_schema()
    if is_complete(op.get_bind()):
        return
    with op.get_context().autocommit_block():
        fill(op.get_bind())
    # Back in a migration transaction (committed by the next block).
    set_not_null(op.get_bind())
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        build_indexes(bind)
        bind.execute(text(f"ANALYZE {_TABLE}"))


def downgrade() -> None:
    op.execute(_SYNC_FUNCTION_138)
    op.execute(_ROW_TRIGGER_138)
    op.execute(
        "ALTER TABLE task_evaluation_metric_keys "
        "DROP COLUMN IF EXISTS task_id, DROP COLUMN IF EXISTS field_name, "
        "DROP COLUMN IF EXISTS created_at, DROP COLUMN IF EXISTS metrics_lite"
    )
    op.execute("DROP FUNCTION IF EXISTS task_evaluation_metrics_lite(jsonb)")
    for name in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
