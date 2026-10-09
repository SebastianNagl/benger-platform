"""add projects.annotator_step_detail_after_submit

Splits the post-submit reveal of a project in two. Until now
``annotator_full_visibility_after_submit`` decided both whether a solver sees
the reference solution after submitting AND whether they see the per-step
detail of their AI grading (step scores, reasons, evidence, the filled
grading sheet). Some exams need the grading steps without the reference.

- NULL (default): step detail follows ``annotator_full_visibility_after_submit``,
  exactly the previous behaviour.
- True / False: step detail is shown / withheld regardless of the reference
  reveal.

The effective rule lives in ``solution_reveal.step_detail_revealed``. Existing
projects get NULL, so nothing changes until someone sets the new switch.

Idempotent: guards on column existence, safe to re-run (091 pattern).

Revision ID: 116_project_step_detail_after_submit
Revises: 115_group_require_private_keys
Create Date: 2026-10-09
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "116_project_step_detail_after_submit"
down_revision = "115_group_require_private_keys"
branch_labels = None
depends_on = None


TABLE_NAME = "projects"
COLUMN_NAME = "annotator_step_detail_after_submit"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.Boolean(), nullable=True))


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
