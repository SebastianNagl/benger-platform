"""Shared "lite" projection of ``task_evaluations.metrics`` for score reads.

Drops the heavy nested fields (``details``, ``method``, ``raw``,
``justification``) that score-extraction paths never use — for an
llm_judge_falloesung row on ZJS Fälle this collapses ~6 KB of judge
rubric text down to ~50 B, so project-wide readers pull kilobytes from
Postgres instead of the full judge/annotation prose. First measured on
by-task-model (2026-05-18: ~45 MB → ~600 KB, page-load 3.1s → ~0.4s on
prod-shaped data); generalized here after `/statistics` — which selected
the full column across ALL of a project's sample rows (ZJS: ~78k rows /
140 MB of JSON, decoded to Python at a several-fold multiple) — OOM-killed
both prod api pods when two project evaluation pages were opened
side-by-side (2026-07-23, 3Gi limit).

Consumers rely on `_coerce_metric_value` semantics only: the bare-numeric
legacy shape, ``{"value": ...}`` (optionally with ``error``), and the
pre-unified Korrektur blob's top-level ``score``/``total_score`` all
survive this projection untouched.

``task_evaluations.metrics`` is ``Column(JSON)`` (text JSON), so
``jsonb_each`` requires an explicit cast — Postgres won't auto-promote
``json`` to ``jsonb``. Schemas where the column is already jsonb still
work because the cast is a no-op there.
"""
from sqlalchemy import literal_column

_METRICS_LITE_SQL = """
    (SELECT COALESCE(jsonb_object_agg(k,
        CASE WHEN jsonb_typeof(v) = 'object'
             THEN v - 'details' - 'method' - 'raw' - 'justification'
             ELSE v END
      ), '{}'::jsonb)
     FROM jsonb_each(task_evaluations.metrics::jsonb) AS j(k, v))
"""


def metrics_lite_expr(label: str = "metrics"):
    """A labeled SQL expression selecting the slimmed metrics blob.

    Use in place of ``TaskEvaluation.metrics`` in any query that only
    extracts scores; the result keeps the ``metrics`` row-attribute name
    (or ``label``) so consumers are unchanged.
    """
    return literal_column(_METRICS_LITE_SQL).label(label)
