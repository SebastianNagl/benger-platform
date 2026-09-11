"""Re-file human rubric gradings under the field they actually grade

`korrektur_custom` rows were written with a hardcoded `field_name = "answer"`:
the client sent the literal and the server's default was the same string, so
the field the creator picks when configuring the evaluation method was never
read. The `llm_judge_rubric` row of the SAME submission carries the real field
(`loesung`), so the two halves of a grading pair sat under different names —
the Korrektur modal rendered them as two unrelated "Evaluierung: x" sections,
and any per-field comparison split them apart.

The code now resolves the field from the project's evaluation setup
(`_resolve_graded_field`). This repairs the rows already written: for each
`korrektur_custom` row still filed under "answer", adopt the field of the
project's own configuration — the `korrektur_custom` entry's
`prediction_fields`, else its LLM judge peer's — and fall back to the field
the task's other evaluation rows use. Rows whose project offers no answer are
left alone rather than guessed at.

`korrektur_falloesung` is NOT touched: its literal was "loesung", which is the
field exams actually use, so those rows are already right.

Idempotent — only rewrites rows still saying "answer".

Revision ID: 102_korrektur_custom_graded_field
Revises: 101_drop_falloesung_prompt_version
Create Date: 2026-09-11
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "102_korrektur_custom_graded_field"
down_revision = "101_drop_falloesung_prompt_version"
branch_labels = None
depends_on = None

#: What the rows were wrongly filed under.
STALE_FIELD = "answer"

#: The LLM judges a human rubric grading is meant to pair with, in order.
_PEER_METRICS = ("llm_judge_rubric", "llm_judge_custom")


def _prediction_field(configs, metric):
    for entry in configs or []:
        if not isinstance(entry, dict) or entry.get("metric") != metric:
            continue
        for field in entry.get("prediction_fields") or []:
            if isinstance(field, str) and field.strip():
                return field.strip()
    return None


def _field_for_project(config):
    """The field this project's setup says the human rubric lane grades."""
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except ValueError:
            return None
    if not isinstance(config, dict):
        return None
    configs = config.get("evaluation_configs") or config.get(
        "multi_field_evaluations"
    )
    field = _prediction_field(configs, "korrektur_custom")
    if field:
        return field
    for peer in _PEER_METRICS:
        field = _prediction_field(configs, peer)
        if field:
            return field
    return None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT te.id, te.task_id, p.evaluation_config
            FROM task_evaluations te
            JOIN tasks t ON t.id = te.task_id
            JOIN projects p ON p.id = t.project_id
            WHERE te.field_name = :stale
              AND jsonb_typeof(CAST(te.metrics AS jsonb)) = 'object'
              AND CAST(te.metrics AS jsonb) ? 'korrektur_custom'
            """
        ),
        {"stale": STALE_FIELD},
    ).fetchall()

    updated = 0
    for row_id, task_id, config in rows:
        field = _field_for_project(config)
        if not field:
            # Last resort: the field the task's OTHER evaluation rows use.
            field = conn.execute(
                sa.text(
                    "SELECT field_name FROM task_evaluations "
                    "WHERE task_id = :task_id AND field_name IS NOT NULL "
                    "AND field_name <> :stale "
                    "GROUP BY field_name ORDER BY count(*) DESC LIMIT 1"
                ),
                {"task_id": task_id, "stale": STALE_FIELD},
            ).scalar()
        if not field:
            continue
        conn.execute(
            sa.text(
                "UPDATE task_evaluations SET field_name = :field WHERE id = :id"
            ),
            {"field": field, "id": row_id},
        )
        updated += 1
    print(
        f"102: re-filed {updated} of {len(rows)} korrektur_custom row(s) "
        f"off '{STALE_FIELD}'"
    )


def downgrade() -> None:
    # The old value was a hardcoded placeholder, not data worth restoring.
    pass
