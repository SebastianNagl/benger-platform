"""Store the reasoning a model returns next to its answer.

- ``generations.reasoning`` (Text, nullable): the reasoning text the
  provider returned beside the generated answer (Anthropic thinking blocks,
  Gemini thought summaries, ``reasoning_content`` / ``reasoning`` of
  OpenAI-compatible servers, Magistral and Cohere thinking chunks). NULL
  when the provider returned none.
- ``task_evaluations.raw_reasoning`` (Text, nullable): the same for the
  judge model's call, beside ``raw_output``.

Both are research data only: answer parsing, scoring and judges never read
them. Pure additive and idempotent: each column is guarded by an inspector
check, so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 131_model_reasoning_columns
Revises: 130_task_source_task_id
Create Date: 2026-11-13
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "131_model_reasoning_columns"
down_revision = "130_task_source_task_id"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("generations", "reasoning"),
    ("task_evaluations", "raw_reasoning"),
)


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def upgrade() -> None:
    for table, column in _COLUMNS:
        if not _column_exists(table, column):
            op.add_column(table, sa.Column(column, sa.Text(), nullable=True))


def downgrade() -> None:
    for table, column in _COLUMNS:
        if _column_exists(table, column):
            op.drop_column(table, column)
