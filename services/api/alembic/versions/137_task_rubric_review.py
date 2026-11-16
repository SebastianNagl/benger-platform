"""Check step for grading sheets: review state, flag and the edit log

- ``projects.rubric_review_required`` (NOT NULL, default FALSE): a task
  rubric of such a project becomes active only after a person confirmed it.
  Existing rows stay FALSE, so no existing project changes behaviour.
- ``task_rubrics.review_state`` (NULL = no check recorded, else
  ``'confirmed'`` / ``'unusable'``), ``reviewed_at``, ``reviewed_by``
  (users, SET NULL) and the index ``ix_task_rubrics_project_review_state``.
- New table ``task_rubric_review_events``: the append-only edit and check
  log the overlay's review workflow writes (provenance, structured diff,
  checklist, verdict, the outline before and after, time taken, app
  version). A ``BEFORE UPDATE`` trigger refuses every UPDATE except setting
  ``rubric_id`` and/or ``actor_id`` to NULL (the two ``ON DELETE SET NULL``
  actions); DELETE stays allowed (project and task cascades, account
  erasure). The trigger SQL is the same as
  ``project_models.TASK_RUBRIC_REVIEW_EVENTS_APPEND_ONLY_DDL``, kept verbatim
  here because a migration never imports the models.

Idempotent: every step is guarded by an inspector or catalog check, so a
database built from the models (the test DB, which gets the trigger from the
model's ``after_create`` listener) runs it as a no-op.

Revision ID: 137_task_rubric_review
Revises: 136_rubric_generation_jobs
Create Date: 2026-11-16
"""

from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "137_task_rubric_review"
down_revision = "136_rubric_generation_jobs"
branch_labels = None
depends_on = None

_EVENTS = "task_rubric_review_events"
_TRIGGER = "trg_task_rubric_review_events_append_only"
_FUNCTION = "task_rubric_review_events_append_only"

_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION task_rubric_review_events_append_only() RETURNS trigger AS $fn$
BEGIN
    IF (to_jsonb(NEW) - 'rubric_id' - 'actor_id') IS DISTINCT FROM (to_jsonb(OLD) - 'rubric_id' - 'actor_id')
       OR (NEW.rubric_id IS DISTINCT FROM OLD.rubric_id AND NEW.rubric_id IS NOT NULL)
       OR (NEW.actor_id IS DISTINCT FROM OLD.actor_id AND NEW.actor_id IS NOT NULL) THEN
        RAISE EXCEPTION 'task_rubric_review_events is append-only'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql
"""
_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER trg_task_rubric_review_events_append_only
BEFORE UPDATE ON task_rubric_review_events
FOR EACH ROW EXECUTE FUNCTION task_rubric_review_events_append_only()
"""


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _insp().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def _has_trigger() -> bool:
    found = op.get_bind().execute(
        text("SELECT 1 FROM pg_trigger WHERE tgname = :name AND NOT tgisinternal"),
        {"name": _TRIGGER},
    )
    return found.first() is not None


def upgrade() -> None:
    if not _has_column("projects", "rubric_review_required"):
        op.add_column(
            "projects",
            sa.Column(
                "rubric_review_required", sa.Boolean(), nullable=False,
                server_default=sa.false(),
            ),
        )

    if not _has_column("task_rubrics", "review_state"):
        op.add_column("task_rubrics", sa.Column("review_state", sa.String(16), nullable=True))
    if not _has_column("task_rubrics", "reviewed_at"):
        op.add_column(
            "task_rubrics", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
        )
    if not _has_column("task_rubrics", "reviewed_by"):
        op.add_column(
            "task_rubrics",
            sa.Column(
                "reviewed_by", sa.String(),
                sa.ForeignKey(
                    "users.id", ondelete="SET NULL", name="task_rubrics_reviewed_by_fkey"
                ),
                nullable=True,
            ),
        )
    if not _has_index("task_rubrics", "ix_task_rubrics_project_review_state"):
        op.create_index(
            "ix_task_rubrics_project_review_state",
            "task_rubrics",
            ["project_id", "review_state"],
        )

    if not _has_table(_EVENTS):
        op.create_table(
            _EVENTS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id", sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "task_id", sa.String(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "rubric_id", sa.String(),
                sa.ForeignKey("task_rubrics.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "actor_id", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("event", sa.String(24), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column("provenance", postgresql.JSONB(), nullable=True),
            sa.Column("diff", postgresql.JSONB(), nullable=True),
            sa.Column("checklist", postgresql.JSONB(), nullable=True),
            sa.Column("verdict", sa.String(16), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("structure_before", postgresql.JSONB(), nullable=True),
            sa.Column("structure_after", postgresql.JSONB(), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("app_version", sa.String(128), nullable=True),
            sa.Column("context", postgresql.JSONB(), nullable=True),
        )
    for name, columns in (
        ("ix_task_rubric_review_events_project_id", ["project_id"]),
        ("ix_task_rubric_review_events_task_id", ["task_id"]),
        ("ix_task_rubric_review_events_rubric_id", ["rubric_id"]),
        ("ix_task_rubric_review_events_created_at", ["created_at"]),
        ("ix_task_rubric_review_events_project_created", ["project_id", "created_at"]),
    ):
        if not _has_index(_EVENTS, name):
            op.create_index(name, _EVENTS, columns)

    op.execute(_APPEND_ONLY_FUNCTION)
    if not _has_trigger():
        op.execute(_APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    if _has_table(_EVENTS):
        op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON {_EVENTS}")
        op.drop_table(_EVENTS)
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
    if _has_index("task_rubrics", "ix_task_rubrics_project_review_state"):
        op.drop_index("ix_task_rubrics_project_review_state", table_name="task_rubrics")
    for column in ("reviewed_by", "reviewed_at", "review_state"):
        if _has_column("task_rubrics", column):
            op.drop_column("task_rubrics", column)
    if _has_column("projects", "rubric_review_required"):
        op.drop_column("projects", "rubric_review_required")
