"""Rename feedback_* schema objects to korrektur_*.

Companion to the user-facing rename of "Feedback" → "Korrektur" in
benger-extended. Renames the table, project flag/config columns, task
denormalized counters, and all associated indexes/constraints. Also
backfills `korrektur_classic` into `evaluation_config.evaluation_configs`
for any project that previously had `feedback_enabled = true`, so the new
wizard-driven enablement keeps surfacing the flow for existing projects.

Revision ID: 031_rename_feedback_to_korrektur
Revises: 030_add_judge_prompt_provenance
Create Date: 2026-04-28
"""

import json
import uuid

from alembic import op
from sqlalchemy import text


revision = "031_rename_feedback_to_korrektur"
down_revision = "030_add_judge_prompt_provenance"
branch_labels = None
depends_on = None


def _backfill_korrektur_classic_eval_config() -> None:
    """For every project that has korrektur_enabled=true, ensure the
    evaluation_config.evaluation_configs array contains a korrektur_classic
    entry. Idempotent.
    """
    bind = op.get_bind()
    rows = bind.execute(
        text(
            "SELECT id, evaluation_config FROM projects WHERE korrektur_enabled = true"
        )
    ).fetchall()
    for row in rows:
        project_id = row[0]
        config = row[1] or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (TypeError, ValueError):
                config = {}
        configs = list(config.get("evaluation_configs") or [])
        if any(
            isinstance(entry, dict) and entry.get("metric") == "korrektur_classic"
            for entry in configs
        ):
            continue
        configs.append({
            "id": f"korrektur_classic-{uuid.uuid4().hex[:8]}",
            "metric": "korrektur_classic",
            "display_name": "Korrektur (Classic)",
            "prediction_fields": [],
            "reference_fields": [],
            "enabled": True,
        })
        config["evaluation_configs"] = configs
        bind.execute(
            text(
                "UPDATE projects SET evaluation_config = :cfg WHERE id = :pid"
            ),
            {"cfg": json.dumps(config), "pid": project_id},
        )


def upgrade() -> None:
    # Project-level flag + config
    op.alter_column("projects", "feedback_enabled", new_column_name="korrektur_enabled")
    op.alter_column("projects", "feedback_config", new_column_name="korrektur_config")

    # Denormalized counters on tasks
    op.alter_column("tasks", "feedback_count", new_column_name="korrektur_count")
    op.alter_column(
        "tasks",
        "unresolved_feedback_count",
        new_column_name="unresolved_korrektur_count",
    )

    # Drop indexes that reference the old table name before renaming
    op.drop_index("ix_feedback_comments_created_by", table_name="feedback_comments")
    op.drop_index("ix_feedback_comments_parent", table_name="feedback_comments")
    op.drop_index("ix_feedback_comments_target", table_name="feedback_comments")
    op.drop_index("ix_feedback_comments_project_task", table_name="feedback_comments")

    # Rename the table itself (PG also renames the implicit PK index)
    op.rename_table("feedback_comments", "korrektur_comments")

    # Recreate indexes with the new naming convention
    op.create_index(
        "ix_korrektur_comments_project_task",
        "korrektur_comments",
        ["project_id", "task_id"],
    )
    op.create_index(
        "ix_korrektur_comments_target",
        "korrektur_comments",
        ["target_type", "target_id"],
    )
    op.create_index(
        "ix_korrektur_comments_parent",
        "korrektur_comments",
        ["parent_id"],
    )
    op.create_index(
        "ix_korrektur_comments_created_by",
        "korrektur_comments",
        ["created_by"],
    )

    # Backfill korrektur_classic into evaluation_config for projects that
    # previously had feedback enabled, so the wizard-driven flow surfaces
    # without manual reconfiguration.
    _backfill_korrektur_classic_eval_config()


def downgrade() -> None:
    op.drop_index("ix_korrektur_comments_created_by", table_name="korrektur_comments")
    op.drop_index("ix_korrektur_comments_parent", table_name="korrektur_comments")
    op.drop_index("ix_korrektur_comments_target", table_name="korrektur_comments")
    op.drop_index("ix_korrektur_comments_project_task", table_name="korrektur_comments")

    op.rename_table("korrektur_comments", "feedback_comments")

    op.create_index(
        "ix_feedback_comments_project_task",
        "feedback_comments",
        ["project_id", "task_id"],
    )
    op.create_index(
        "ix_feedback_comments_target",
        "feedback_comments",
        ["target_type", "target_id"],
    )
    op.create_index(
        "ix_feedback_comments_parent",
        "feedback_comments",
        ["parent_id"],
    )
    op.create_index(
        "ix_feedback_comments_created_by",
        "feedback_comments",
        ["created_by"],
    )

    op.alter_column(
        "tasks",
        "unresolved_korrektur_count",
        new_column_name="unresolved_feedback_count",
    )
    op.alter_column("tasks", "korrektur_count", new_column_name="feedback_count")

    op.alter_column("projects", "korrektur_config", new_column_name="feedback_config")
    op.alter_column("projects", "korrektur_enabled", new_column_name="feedback_enabled")
