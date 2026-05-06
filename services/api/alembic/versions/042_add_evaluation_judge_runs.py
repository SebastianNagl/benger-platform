"""Add per-judge-run table and migrate legacy single-judge config to ensemble shape.

Splits evaluation execution from configuration: an `EvaluationRun` stays the
user-visible "evaluation job", and a new `evaluation_judge_runs` child table
records one row per (judge_model, run_index) execution. `TaskEvaluation` rows
link to the specific judge_run that produced them, so multi-judge ensembles and
same-model multi-run both fit under one schema.

Backfill: one synthetic `EvaluationJudgeRun` per existing `EvaluationRun` with
`run_index = 0` and `judge_model_id` lifted from `eval_metadata.judge_model` if
present (else NULL for non-judge metrics). Every existing `TaskEvaluation` is
re-parented to that synthetic row.

Legacy rewrite: any `metric_parameters.judge_model = "X"` inside
`projects.evaluation_config.evaluation_configs[*].metric_parameters` is
rewritten to `judges = [{judge_model_id: "X", runs: 1}]` and the legacy
`judge_model` key is dropped. After this migration the worker reads only the
new shape — no fallback path remains.

Revision ID: 042_add_evaluation_judge_runs
Revises: 041_add_generation_run_index
Create Date: 2026-05-06
"""

import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "042_add_evaluation_judge_runs"
down_revision = "041_add_generation_run_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_judge_runs",
        sa.Column("id", sa.String(), primary_key=True, index=True),
        sa.Column(
            "evaluation_id",
            sa.String(),
            sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("judge_model_id", sa.String(), nullable=True),
        sa.Column("run_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("samples_evaluated", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metric_parameters_snapshot",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "evaluation_id",
            "judge_model_id",
            "run_index",
            name="uq_evaluation_judge_runs_eval_model_index",
        ),
    )

    op.add_column(
        "task_evaluations",
        sa.Column(
            "judge_run_id",
            sa.String(),
            sa.ForeignKey("evaluation_judge_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_task_evaluations_judge_run_id",
        "task_evaluations",
        ["judge_run_id"],
    )

    # ── Backfill synthetic EvaluationJudgeRun rows ─────────────────────────
    bind = op.get_bind()

    eval_rows = bind.execute(
        sa.text(
            """
            SELECT id, status, completed_at, samples_evaluated, error_message,
                   eval_metadata
            FROM evaluation_runs
            """
        )
    ).fetchall()

    for row in eval_rows:
        eval_id = row[0]
        status = row[1] or "completed"
        completed_at = row[2]
        samples_evaluated = row[3]
        error_message = row[4]
        eval_metadata = row[5] or {}

        if isinstance(eval_metadata, str):
            try:
                eval_metadata = json.loads(eval_metadata)
            except (TypeError, ValueError):
                eval_metadata = {}

        judge_model_id = None
        if isinstance(eval_metadata, dict):
            judge_model_id = (
                eval_metadata.get("judge_model")
                or eval_metadata.get("judge_model_id")
            )

        judge_run_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                """
                INSERT INTO evaluation_judge_runs
                    (id, evaluation_id, judge_model_id, run_index,
                     status, completed_at, samples_evaluated, error_message,
                     metric_parameters_snapshot)
                VALUES
                    (:id, :evaluation_id, :judge_model_id, 0,
                     :status, :completed_at, :samples_evaluated, :error_message,
                     NULL)
                """
            ),
            {
                "id": judge_run_id,
                "evaluation_id": eval_id,
                "judge_model_id": judge_model_id,
                "status": status,
                "completed_at": completed_at,
                "samples_evaluated": samples_evaluated,
                "error_message": error_message,
            },
        )

        bind.execute(
            sa.text(
                """
                UPDATE task_evaluations
                SET judge_run_id = :judge_run_id
                WHERE evaluation_id = :evaluation_id
                """
            ),
            {"judge_run_id": judge_run_id, "evaluation_id": eval_id},
        )

    # NOTE on judge_run_id nullability:
    # The backfill above sets judge_run_id on every existing TaskEvaluation row.
    # The column is left nullable for now so worker code paths that haven't been
    # updated to pass judge_run_id keep working through the rollout. A follow-up
    # migration tightens it to NOT NULL once all writers populate it.

    # ── Rewrite legacy metric_parameters.judge_model on Project.evaluation_config
    project_rows = bind.execute(
        sa.text("SELECT id, evaluation_config FROM projects WHERE evaluation_config IS NOT NULL")
    ).fetchall()

    for prow in project_rows:
        proj_id = prow[0]
        eval_config = prow[1]
        if isinstance(eval_config, str):
            try:
                eval_config = json.loads(eval_config)
            except (TypeError, ValueError):
                continue
        if not isinstance(eval_config, dict):
            continue

        configs = eval_config.get("evaluation_configs") or eval_config.get("multi_field_evaluations")
        if not isinstance(configs, list):
            continue

        mutated = False
        for cfg in configs:
            if not isinstance(cfg, dict):
                continue
            mp = cfg.get("metric_parameters")
            if not isinstance(mp, dict):
                continue
            if "judge_model" in mp and "judges" not in mp:
                judge_model = mp.pop("judge_model")
                if judge_model:
                    mp["judges"] = [{"judge_model_id": judge_model, "runs": 1}]
                    mutated = True

        if mutated:
            bind.execute(
                sa.text(
                    "UPDATE projects SET evaluation_config = :cfg WHERE id = :id"
                ),
                {"cfg": json.dumps(eval_config), "id": proj_id},
            )


def downgrade() -> None:
    # No reverse rewrite of the JSONB legacy field — the new shape is a
    # superset; downgrading the schema does not require collapsing the data.
    op.drop_index("ix_task_evaluations_judge_run_id", table_name="task_evaluations")
    op.drop_column("task_evaluations", "judge_run_id")
    op.drop_table("evaluation_judge_runs")
