"""add projects.annotator_full_visibility_after_submit

Per-project toggle controlling what an annotator sees when reviewing their own
submitted work in "Meine Aufgaben". When False (default) the post-submission
view is filtered to only the fields the annotator saw while labeling, so the
reference solution (Musterlösung) and raw ground_truth are never exposed —
preventing leaks to peers who still have to sit the same exam. When True,
annotators see all task fields after submission to compare and learn.

Idempotent — guards on column existence; safe to re-run.

Revision ID: 062_annotator_full_visibility_after_submit
Revises: 061_korrektur_custom_human_run_singleton
Create Date: 2026-06-17
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "062_annotator_full_visibility_after_submit"
down_revision = "061_korrektur_custom_human_run_singleton"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"
COLUMN_NAME = "annotator_full_visibility_after_submit"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                COLUMN_NAME,
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
