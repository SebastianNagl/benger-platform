"""Promote academic-rigor LLM-call metadata to discrete columns.

Phase 6.6 of the academic-rigor overhaul. Until now, every per-call
metadata field captured by `services/shared/ai_services/*_service.py`
landed inside JSON columns (`generations.response_metadata`,
`generations.usage_stats`, `task_evaluations.metrics`). That was fine
for export but expensive to slice — questions like "fraction of all
evaluation runs where the judge truncated" or "median latency by
provider" required JSON path queries on hot tables.

This migration promotes the eight most-queried fields to first-class
columns on both `generations` and `task_evaluations`, plus a `raw_output`
TEXT column on `task_evaluations` (the generic LLM judge path didn't
previously persist the unparsed judge response — only the Falllösung
overlay did).

The JSON columns stay where they are: `response_metadata` continues to
hold the long tail (retry_attempts, provider_route, billed_user_id,
temperature_coerced, unsupported_params_dropped, …). The new columns
mirror keys inside the JSON; worker write paths populate both from a
single source dict so they stay in sync.

Backfill: existing rows get NULL / default-false. Researchers filter
on ``WHERE latency_ms IS NOT NULL`` (or any other new column) to
restrict to "post-instrumentation" data — pre-migration rows have no
fidelity to recover from the JSON blob deterministically (some keys
were inconsistently named across providers before this pass).

Revision ID: 040_add_llm_call_metadata_columns
Revises: 039_fix_label_config_version_type
Create Date: 2026-05-06
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision = "040_add_llm_call_metadata_columns"
down_revision = "039_fix_label_config_version_type"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


# Eight fields shared by both tables. `raw_output` is added only to
# task_evaluations (generations already has `response_content`).
_SHARED_COLUMNS = (
    ("seed", sa.Integer(), True, None),
    ("finish_reason", sa.String(length=64), True, None),
    ("truncated", sa.Boolean(), False, sa.text("false")),
    ("refusal", sa.Boolean(), False, sa.text("false")),
    ("error_type", sa.String(length=64), True, None),
    ("latency_ms", sa.Integer(), True, None),
    ("input_tokens", sa.Integer(), True, None),
    ("output_tokens", sa.Integer(), True, None),
)


def _column_exists(conn, table: str, column: str) -> bool:
    """Idempotency guard — re-running the migration on a partially-
    applied DB shouldn't fail. Mirrors the pattern in 039 and earlier
    repair-style migrations."""
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()

    for table in ("generations", "task_evaluations"):
        for name, col_type, nullable, server_default in _SHARED_COLUMNS:
            if _column_exists(conn, table, name):
                logger.info("[040] %s.%s already exists; skipping", table, name)
                continue
            kwargs = {"nullable": nullable}
            if server_default is not None:
                kwargs["server_default"] = server_default
            op.add_column(table, sa.Column(name, col_type, **kwargs))
            logger.info("[040] added %s.%s", table, name)

    # raw_output: only task_evaluations gets it. generations already
    # stores the unparsed model output in response_content.
    if not _column_exists(conn, "task_evaluations", "raw_output"):
        op.add_column(
            "task_evaluations",
            sa.Column("raw_output", sa.Text(), nullable=True),
        )
        logger.info("[040] added task_evaluations.raw_output")
    else:
        logger.info("[040] task_evaluations.raw_output already exists; skipping")


def downgrade() -> None:
    conn = op.get_bind()

    if _column_exists(conn, "task_evaluations", "raw_output"):
        op.drop_column("task_evaluations", "raw_output")

    for table in ("task_evaluations", "generations"):
        for name, _col_type, _nullable, _server_default in _SHARED_COLUMNS:
            if _column_exists(conn, table, name):
                op.drop_column(table, name)
