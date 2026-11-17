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

The projection is the SQL function ``task_evaluation_metrics_lite(jsonb)``
(migration 139, ``models.TASK_EVALUATION_METRICS_LITE_FUNCTION``). The
trigger that keeps ``task_evaluation_metric_keys`` stores the same function's
result per row, so a reader of that mirror's ``metrics_lite`` column and a
reader of this expression see identical dicts.

Rows whose metrics hold a JSON non-object (``null`` is written when a row is
saved with ``metrics=None``) project to ``{}``: ``jsonb_each`` raises on a
non-object, which failed the whole query and returned a 500 for every
history-including by-task-model read of such a project.
"""
import re

from sqlalchemy import literal_column

_METRICS_LITE_SQL = "task_evaluation_metrics_lite({table}.metrics::jsonb)"

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def metrics_lite_expr(label: str = "metrics", table: str = "task_evaluations"):
    """A labeled SQL expression selecting the slimmed metrics blob.

    Use in place of ``TaskEvaluation.metrics`` in any query that only
    extracts scores; the result keeps the ``metrics`` row-attribute name
    (or ``label``) so consumers are unchanged. ``table`` names the relation
    (or alias) whose ``metrics`` column it reads — the default matches the
    bare table so existing callers are unchanged.
    """
    if not _IDENTIFIER.match(table):
        raise ValueError(f"invalid table identifier for metrics_lite_expr: {table!r}")
    return literal_column(_METRICS_LITE_SQL.replace("{table}", table)).label(label)
