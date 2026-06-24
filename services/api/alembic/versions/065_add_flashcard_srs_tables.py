"""add flashcard_srs_state and flashcard_reviews tables

Student exam-training experience (issue #35) — Anki-style flashcards. Each deck
is a project and each card is a task; these two tables are a per-user sidecar so
a deck stays benchmarkable in the expert view while every student carries their
own SM-2 schedule.

- ``flashcard_srs_state``: mutable per-(card,user) snapshot of the current SM-2
  scheduling state. Unique (task_id, user_id); hot index (user_id, due_at) for
  the "due today" query. The SM-2 algorithm that mutates it lives in the
  extended worker; platform owns only the persistence.
- ``flashcard_reviews``: append-only log, one row per review event — preserves
  the full history that retention/score-over-time charts need and that a future
  FSRS optimizer would require. Graded-mode answers + judge scores live here,
  never in annotations/task_evaluations.

All FKs ``ondelete=CASCADE`` so a deleted user/project/task self-cleans (the
059 user-FK migration exists because earlier tables shipped without this).

Idempotent — guards on table/index existence; safe to re-run.

Revision ID: 065_add_flashcard_srs_tables
Revises: 064_add_project_kind_and_origin
Create Date: 2026-06-25
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "065_add_flashcard_srs_tables"
down_revision = "064_add_project_kind_and_origin"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table in insp.get_table_names()


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    if not _table_exists("flashcard_srs_state"):
        op.create_table(
            "flashcard_srs_state",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "task_id",
                sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
            sa.Column("interval_days", sa.Float(), nullable=False, server_default="0"),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reps", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("lapses", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("learning_step", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("state", sa.String(length=16), nullable=False, server_default="new"),
            sa.Column("last_rating", sa.String(length=8), nullable=True),
            sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("task_id", "user_id", name="uq_flashcard_srs_task_user"),
        )
    _create_index_if_missing(
        "ix_flashcard_srs_user_due", "flashcard_srs_state", ["user_id", "due_at"]
    )
    _create_index_if_missing(
        "ix_flashcard_srs_project", "flashcard_srs_state", ["project_id"]
    )

    if not _table_exists("flashcard_reviews"):
        op.create_table(
            "flashcard_reviews",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "task_id",
                sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("mode", sa.String(length=8), nullable=False),
            sa.Column("rating", sa.String(length=8), nullable=False),
            sa.Column("judge_score", sa.Float(), nullable=True),
            sa.Column("answer_text", sa.Text(), nullable=True),
            sa.Column("interval_days_after", sa.Float(), nullable=True),
            sa.Column("ease_factor_after", sa.Float(), nullable=True),
            sa.Column(
                "reviewed_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    _create_index_if_missing(
        "ix_flashcard_reviews_user_reviewed", "flashcard_reviews", ["user_id", "reviewed_at"]
    )
    _create_index_if_missing(
        "ix_flashcard_reviews_project", "flashcard_reviews", ["project_id"]
    )
    _create_index_if_missing(
        "ix_flashcard_reviews_task", "flashcard_reviews", ["task_id"]
    )


def downgrade() -> None:
    if _table_exists("flashcard_reviews"):
        op.drop_table("flashcard_reviews")
    if _table_exists("flashcard_srs_state"):
        op.drop_table("flashcard_srs_state")
