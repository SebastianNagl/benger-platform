"""add users.exam_layout_prefs

Per-user exam interface layout preference. Users choose in their profile how
exam-shaped labeling interfaces render: ``classic`` (the stacked cards, each
opening a full-screen modal) or ``modern`` (the Loesung editor as the always-
open main sheet with the case/notes/outline docked as slide-in side panels).

Nullable ``JSON`` holding the complete validated object, e.g.::

    {"mode": "modern", "case_position": "left",
     "notes_position": "right", "outline_position": "none"}

NULL means "never configured" and resolves to classic. The full object is
always stored — including with mode ``classic`` — so a user's modern docking
survives classic round-trips. Shape is enforced by the Pydantic model
``ExamLayoutPrefs`` (auth_schemas.py); the only writer is
``PUT /auth/me/exam-layout``. Plain JSON (not JSONB): read-whole/written-whole,
never queried or indexed server-side — matching every prior ``users`` JSON
column.

This is a display preference only — never an authorization or exam-integrity
input.

Chained on 090 (the committed head at authoring time). If the task-rubrics
migration ``088_add_task_rubrics`` (in flight on a parallel stream, itself
chained on 090) lands first, re-point ``down_revision`` to
``"088_add_task_rubrics"`` — the single-head meta-test
(tests/migration/test_single_alembic_head.py) turns the collision into a
PR-time failure either way.

Idempotent — guards on column existence; safe to re-run. Mirrors the 067
guard pattern.

Revision ID: 091_add_user_exam_layout_prefs
Revises: 090_exam_unlimited_annotations
Create Date: 2026-08-07
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "091_add_user_exam_layout_prefs"
down_revision = "090_exam_unlimited_annotations"
branch_labels = None
depends_on = None


TABLE_NAME = "users"
COLUMN_NAME = "exam_layout_prefs"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
