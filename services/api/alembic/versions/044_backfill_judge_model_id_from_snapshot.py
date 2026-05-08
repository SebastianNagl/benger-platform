"""Backfill evaluation_judge_runs.judge_model_id from eval_metadata snapshot.

Migration 042 lifted judge_model from `eval_metadata.judge_model` (a path
that doesn't actually exist) and so left every historical synthetic
EvaluationJudgeRun row with `judge_model_id = NULL`. The legacy field
actually lives at the deeply-nested
`eval_metadata.evaluation_config_snapshot.evaluation_configs[*].metric_parameters.judge_model`.

This migration walks that snapshot path, picks the first llm_judge_* config
that names a judge model, and writes it onto the synthetic judge_run row
(the one with run_index = 0 created by 042). Skipped when:
- the judge_run already has a judge_model_id (idempotent — never overwrite)
- the parent EvaluationRun has no llm_judge_* config in its snapshot
- the snapshot is missing or malformed

This is a backfill only; there's no down-migration step (judge_model_id is
nullable, so leaving the populated values in place on rollback is safe).

Revision ID: 044_backfill_judge_model_id_from_snapshot
Revises: 043_tighten_judge_run_id_not_null
Create Date: 2026-05-06
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "044_backfill_judge_model_id_from_snapshot"
down_revision = "043_tighten_judge_run_id_not_null"
branch_labels = None
depends_on = None


def _extract_judge_model(eval_metadata) -> str | None:
    """Walk the snapshot path. Returns the first non-empty judge_model
    string found inside an llm_judge_* metric's metric_parameters; None
    if nothing matches. Defensive against partially-malformed JSON."""
    if eval_metadata is None:
        return None
    if isinstance(eval_metadata, str):
        try:
            eval_metadata = json.loads(eval_metadata)
        except (TypeError, ValueError):
            return None
    if not isinstance(eval_metadata, dict):
        return None

    snapshot = eval_metadata.get("evaluation_config_snapshot") or {}
    configs = snapshot.get("evaluation_configs") or []
    if not isinstance(configs, list):
        return None

    for cfg in configs:
        if not isinstance(cfg, dict):
            continue
        metric = cfg.get("metric") or ""
        if not metric.startswith("llm_judge_"):
            continue
        params = cfg.get("metric_parameters") or {}
        if not isinstance(params, dict):
            continue
        # Prefer the new shape if it's already there (a partial migration
        # scenario); fall back to the legacy `judge_model` field.
        judges = params.get("judges")
        if isinstance(judges, list) and judges:
            jid = (judges[0] or {}).get("judge_model_id")
            if jid:
                return str(jid)
        legacy = params.get("judge_model")
        if legacy:
            return str(legacy)
    return None


def upgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(
        sa.text(
            """
            SELECT ejr.id AS jr_id, er.eval_metadata
            FROM evaluation_judge_runs ejr
            JOIN evaluation_runs er ON er.id = ejr.evaluation_id
            WHERE ejr.judge_model_id IS NULL
              AND ejr.run_index = 0
            """
        )
    ).fetchall()

    updates = []
    for r in rows:
        judge_model = _extract_judge_model(r[1])
        if judge_model:
            updates.append({"jr_id": r[0], "judge_model_id": judge_model})

    if updates:
        bind.execute(
            sa.text(
                "UPDATE evaluation_judge_runs SET judge_model_id = :judge_model_id "
                "WHERE id = :jr_id"
            ),
            updates,
        )


def downgrade() -> None:
    # No-op: clearing judge_model_id back to NULL would lose information
    # without a corresponding source-of-truth; the column stays nullable.
    pass
