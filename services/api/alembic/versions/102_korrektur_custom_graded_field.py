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

#: `human:`/`model:` is a ROLE prefix, not part of the field name (platform's
#: own row-to-config matcher strips it). A row filed under the prefixed form
#: sits apart from the LLM judge's row for the same answer.
_ROLE_PREFIXES = ("human:", "model:")

#: The LLM judges a human rubric grading is meant to pair with, in order.
_PEER_METRICS = ("llm_judge_rubric", "llm_judge_custom")


def _bare(field):
    """A field selector reduced to the name it refers to.

    Deliberately a local copy of ``eval_field_classification.bare_field_name``
    rather than an import: a migration is a snapshot of an intent at a point
    in time and must keep doing exactly this even if the shared rule later
    changes. Application code should import the shared helper instead.
    """
    value = (field or "").strip()
    if not value or value in ("__all_human__", "__all_model__"):
        return None
    for prefix in _ROLE_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value or None


def _prediction_field(configs, metric):
    for entry in configs or []:
        if not isinstance(entry, dict) or entry.get("metric") != metric:
            continue
        for field in entry.get("prediction_fields") or []:
            if isinstance(field, str):
                bare = _bare(field)
                if bare:
                    return bare
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
            SELECT te.id, te.task_id, te.field_name, p.evaluation_config
            FROM task_evaluations te
            JOIN tasks t ON t.id = te.task_id
            JOIN projects p ON p.id = t.project_id
            WHERE (te.field_name = :stale
                   OR te.field_name LIKE 'human:%'
                   OR te.field_name LIKE 'model:%')
              AND jsonb_typeof(CAST(te.metrics AS jsonb)) = 'object'
              AND CAST(te.metrics AS jsonb) ? 'korrektur_custom'
            """
        ),
        {"stale": STALE_FIELD},
    ).fetchall()

    updated = 0
    for row_id, task_id, field_name, config in rows:
        # A role-prefixed row already names its field; just drop the prefix.
        field = _bare(field_name) if field_name != STALE_FIELD else None
        if not field:
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
        if field == field_name:
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
        f"off '{STALE_FIELD}' / a role prefix"
    )


def downgrade() -> None:
    # The old value was a hardcoded placeholder, not data worth restoring.
    pass
