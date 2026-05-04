"""Backfill TaskEvaluation.metrics to the {value, details} dict shape

Phase 2 of the academic-rigor overhaul. Before this migration, metrics
in `TaskEvaluation.metrics` were a mix of:
  * bare floats (legacy bleu/rouge/exact_match/etc):
        {"bleu": 0.42, "raw_score": 0.42}
  * already-dict shapes (LLM judges) with various ad-hoc keys.

After this migration, every numeric metric value lives under
`{"value": <float>, "method": <metric_name>, "details": {"backfilled_legacy": true}}`
so consumers see one uniform structure. Read-side shims (`_coerce_metric_value`)
remain in place to handle the rare edge case where a row missed migration.

The "raw_score" companion key is left as bare float (it's a denormalized
display field already, not the canonical metric record).

Existing dict-shaped values (LLM judge runs, korrektur_falloesung) are
left untouched — they already carry their own provenance under
metric-specific keys.

Revision ID: 036_taskevaluation_metrics_to_dict_shape
Revises: 035_add_project_public_visibility
Create Date: 2026-05-03
"""

from alembic import op


revision = "036_taskevaluation_metrics_to_dict_shape"
down_revision = "035_add_project_public_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Wrap every bare-float metric value in {"value", "method", "details"}.

    Implementation: we walk every JSONB key, skip the metadata-style keys
    (anything ending in _details / _passed / _raw / _grade_points, plus
    the "raw_score" denorm and "error" flag), and rewrite numeric values
    into the dict shape. SQL-side jsonb_object_agg + CASE keeps it to a
    single UPDATE per affected row.

    Idempotent: a value that's already a dict (jsonb_typeof = 'object') is
    passed through unchanged, so re-running the migration is safe.
    """
    op.execute(
        """
        UPDATE task_evaluations te
        SET metrics = sub.new_metrics
        FROM (
          SELECT
            id,
            jsonb_object_agg(
              key,
              CASE
                -- Already a dict — leave as-is (LLM judge / korrektur shapes).
                WHEN jsonb_typeof(value) = 'object' THEN value
                -- Metadata / denormalized companions — keep bare.
                WHEN key IN ('raw_score', 'error') THEN value
                WHEN key LIKE '%\\_details' ESCAPE '\\' THEN value
                WHEN key LIKE '%\\_passed' ESCAPE '\\' THEN value
                WHEN key LIKE '%\\_raw' ESCAPE '\\' THEN value
                WHEN key LIKE '%\\_grade\\_points' ESCAPE '\\' THEN value
                -- Bare numeric — wrap into the standard shape.
                WHEN jsonb_typeof(value) IN ('number', 'string', 'boolean') THEN
                  jsonb_build_object(
                    'value', value,
                    'method', key,
                    'details', jsonb_build_object('backfilled_legacy', true),
                    'error', NULL
                  )
                ELSE value
              END
            ) AS new_metrics
          FROM task_evaluations,
               LATERAL jsonb_each(metrics)
          WHERE metrics IS NOT NULL
            AND jsonb_typeof(metrics) = 'object'
          GROUP BY id
        ) sub
        WHERE te.id = sub.id;
        """
    )


def downgrade() -> None:
    """Unwrap {"value": x, ...} dicts back to bare values.

    Best-effort: only entries that look like our backfilled wrappers (i.e.
    have a `backfilled_legacy: true` marker in `details`) are unwrapped.
    Leaves genuine dict-shaped values (LLM judges) alone.
    """
    op.execute(
        """
        UPDATE task_evaluations te
        SET metrics = sub.new_metrics
        FROM (
          SELECT
            id,
            jsonb_object_agg(
              key,
              CASE
                WHEN jsonb_typeof(value) = 'object'
                     AND value -> 'details' ->> 'backfilled_legacy' = 'true'
                     AND value ? 'value'
                THEN value -> 'value'
                ELSE value
              END
            ) AS new_metrics
          FROM task_evaluations,
               LATERAL jsonb_each(metrics)
          WHERE metrics IS NOT NULL
            AND jsonb_typeof(metrics) = 'object'
          GROUP BY id
        ) sub
        WHERE te.id = sub.id;
        """
    )
