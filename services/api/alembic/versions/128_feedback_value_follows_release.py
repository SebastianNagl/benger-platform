"""Feedback rows carry a number only once it is the student's.

A feedback-judge row (``llm_judge_feedback``) used to store the judge's note in
``value`` from the start. ``value`` is what every generic numeric reader takes,
so a teacher's draft reached attempt scores, statistics and rollups, and a
released row kept the judge's number after the teacher corrected it. The writer
now keeps ``value`` empty until release and then stores the note that counts.

This brings stored rows into that shape:
- unreleased row: ``value`` null, and the run's rollup loses the metric
- released row with a teacher grade: ``value`` is the teacher's note on 0-1

The judge's own grade stays in ``details.grade``, so nothing is lost. Downgrade
is a no-op because the old numbers are still derivable from there.

Revision ID: 128_feedback_value_follows_release
Revises: 127_exam_tools
"""

from alembic import op

revision = "128_feedback_value_follows_release"
down_revision = "127_exam_tools"
branch_labels = None
depends_on = None

UNRELEASED = """
    metrics ? 'llm_judge_feedback'
    AND metrics #>> '{llm_judge_feedback,details,feedback_only}' = 'true'
    AND metrics #>> '{llm_judge_feedback,details,review,status}' IS DISTINCT FROM 'released'
"""


def upgrade() -> None:
    # Rollups first, while the drafts can still be told apart by their value.
    op.execute(
        f"""
        UPDATE evaluation_runs AS r
        SET metrics = (
            SELECT COALESCE(json_object_agg(key, value), '{{}}'::json)
            FROM json_each(r.metrics)
            WHERE key NOT LIKE '%|llm_judge_feedback'
        )
        WHERE r.id IN (
            SELECT evaluation_id FROM task_evaluations
            WHERE {UNRELEASED}
              AND metrics #>> '{{llm_judge_feedback,value}}' IS NOT NULL
        )
        """
    )
    op.execute(
        f"""
        UPDATE task_evaluations
        SET metrics = jsonb_set(metrics, '{{llm_judge_feedback,value}}', 'null'::jsonb)
        WHERE {UNRELEASED}
          AND metrics #>> '{{llm_judge_feedback,value}}' IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE task_evaluations
        SET metrics = jsonb_set(
            metrics,
            '{llm_judge_feedback,value}',
            to_jsonb((metrics #>> '{llm_judge_feedback,details,review,grade,note}')::float / 20)
        )
        WHERE metrics ? 'llm_judge_feedback'
          AND metrics #>> '{llm_judge_feedback,details,review,status}' = 'released'
          AND metrics #>> '{llm_judge_feedback,details,review,grade,note}' IS NOT NULL
        """
    )


def downgrade() -> None:
    pass
