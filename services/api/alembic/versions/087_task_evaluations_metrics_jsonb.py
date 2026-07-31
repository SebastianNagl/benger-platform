"""Convert task_evaluations.metrics from json (text) to native jsonb.

Every score reader parses this column per row: the by-task-model matrix and
/statistics slim it via a correlated jsonb_each (metrics_lite), and the
metric= filter uses has_key — all of which needed a full text->jsonb reparse
of a ~6 KB blob per row while the column was text json (issue #280). Binary
jsonb removes the reparse for every reader at the root.

Semantic surface is minimal: the blobs are produced by Python json.dumps of
dicts (no duplicate keys), so jsonb's last-key-wins and key-reordering are
non-issues. Scoped to `metrics` only — ground_truth/prediction and the other
json columns are not on the hot read path.

Operational note: ALTER COLUMN ... TYPE jsonb USING metrics::jsonb rewrites
the table under ACCESS EXCLUSIVE. At prod scale (~78k rows / ~500 MB of
JSON) this is seconds-to-a-minute; the startup migration runner holds its
advisory lock for the duration, so ship in a low-traffic window.

Idempotent — checks the current column type before altering.

Revision ID: 087_task_evaluations_metrics_jsonb
Revises: 086_task_eval_results_indexes
Create Date: 2026-07-31
"""

from sqlalchemy import inspect

from alembic import op


revision = "087_task_evaluations_metrics_jsonb"
down_revision = "086_task_eval_results_indexes"
branch_labels = None
depends_on = None


def _column_type(table: str, column: str) -> str:
    bind = op.get_bind()
    insp = inspect(bind)
    for col in insp.get_columns(table):
        if col["name"] == column:
            return str(col["type"]).lower()
    raise RuntimeError(f"{table}.{column} not found")


def upgrade() -> None:
    if _column_type("task_evaluations", "metrics") != "jsonb":
        op.execute(
            "ALTER TABLE task_evaluations "
            "ALTER COLUMN metrics TYPE jsonb USING metrics::jsonb"
        )
        # The rewrite invalidates planner statistics; until autovacuum
        # re-analyzes, row estimates collapse (observed rows=4 vs actual 70k
        # on prod ZJS right after this shipped) and the by-task-model plans
        # degrade to pathological nested loops (22s vs ~5s). Refresh
        # immediately so no such window exists.
        op.execute("ANALYZE task_evaluations")


def downgrade() -> None:
    if _column_type("task_evaluations", "metrics") == "jsonb":
        op.execute(
            "ALTER TABLE task_evaluations "
            "ALTER COLUMN metrics TYPE json USING metrics::json"
        )
