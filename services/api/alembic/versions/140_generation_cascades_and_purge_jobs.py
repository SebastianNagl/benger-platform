"""Generation rows cascade from their task and project; project purge jobs

Before this, ``generations`` and ``response_generations`` had no foreign key to
``tasks`` or ``projects``, so a project purge (and a task delete) left the
project's generation jobs and generations behind without an owner. Production
had 16 such jobs and 83 generations of 3 purged projects on 2026-11-17.

- Deletes the orphans first: generations whose task is gone or whose job is
  an orphan, then generation jobs whose task or project is gone. Their task
  evaluations went with the task already (``task_evaluations.task_id``
  cascades), and any other reference to a deleted generation is set NULL.
- ``generations.task_id`` -> ``tasks.id`` ON DELETE CASCADE (new).
- ``generations.generation_id`` -> ``response_generations.id``: now
  ON DELETE CASCADE (was NO ACTION).
- ``response_generations.task_id`` -> ``tasks.id`` and
  ``response_generations.project_id`` -> ``projects.id``, both ON DELETE
  CASCADE (new).
- New table ``project_purge_jobs``: the purge runs as a worker job in short
  batches, because a large project took minutes and the API's 15 s statement
  timeout cancelled the single DELETE.

The four tables are locked in SHARE ROW EXCLUSIVE mode first (the mode the
foreign keys need anyway), so no new orphan can appear between the cleanup and
the constraint checks. The mode lets reads through and holds writes to these
tables for the few seconds the migration takes. Every step is guarded, so a
database built from the models (the test DB) runs it as a no-op.

Revision ID: 140_generation_cascades_and_purge_jobs
Revises: 139_task_evaluation_metric_keys_scores
Create Date: 2026-11-17
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "140_generation_cascades_and_purge_jobs"
down_revision = "139_task_evaluation_metric_keys_scores"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_JOBS = "project_purge_jobs"

# (table, column, referenced table, constraint name)
_CASCADES = (
    ("generations", "generation_id", "response_generations", "generations_generation_id_fkey"),
    ("generations", "task_id", "tasks", "generations_task_id_fkey"),
    ("response_generations", "task_id", "tasks", "response_generations_task_id_fkey"),
    ("response_generations", "project_id", "projects", "response_generations_project_id_fkey"),
)

_ORPHAN_JOB = """
    (rg.task_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.id = rg.task_id))
    OR (rg.project_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id = rg.project_id))
"""

_DELETE_ORPHAN_GENERATIONS = f"""
DELETE FROM generations g
WHERE (g.task_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.id = g.task_id))
   OR EXISTS (SELECT 1 FROM response_generations rg WHERE rg.id = g.generation_id AND ({_ORPHAN_JOB}))
"""

_DELETE_ORPHAN_JOBS = f"DELETE FROM response_generations rg WHERE {_ORPHAN_JOB}"


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _fk(table: str, column: str, referred: str):
    """``(name, on_delete)`` of the single-column FK ``table.column`` ->
    ``referred``, or None. ``on_delete`` is the pg_constraint code."""
    row = op.get_bind().execute(
        text(
            """
            SELECT c.conname, c.confdeltype
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            WHERE c.contype = 'f' AND c.conrelid = CAST(:table AS regclass)
              AND c.confrelid = CAST(:referred AS regclass)
              AND array_length(c.conkey, 1) = 1 AND a.attname = :column
            """
        ),
        {"table": table, "referred": referred, "column": column},
    ).first()
    return (row[0], row[1]) if row else None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    todo = [spec for spec in _CASCADES if (_fk(spec[0], spec[1], spec[2]) or (None, None))[1] != "c"]
    if todo:
        op.execute(
            "LOCK TABLE projects, tasks, response_generations, generations "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
        bind = op.get_bind()
        generations = bind.execute(text(_DELETE_ORPHAN_GENERATIONS)).rowcount
        jobs = bind.execute(text(_DELETE_ORPHAN_JOBS)).rowcount
        logger.info(
            "140: deleted %d orphan generation(s) and %d orphan generation job(s)",
            generations, jobs,
        )
        for table, column, referred, name in todo:
            existing = _fk(table, column, referred)
            if existing is not None:
                op.drop_constraint(existing[0], table, type_="foreignkey")
            op.create_foreign_key(name, table, referred, [column], ["id"], ondelete="CASCADE")

    if not _has_table(_JOBS):
        op.create_table(
            _JOBS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("project_title", sa.String(), nullable=True),
            sa.Column(
                "requested_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL",
                              name="project_purge_jobs_requested_by_fkey"),
                nullable=True,
            ),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("result", postgresql.JSONB(), nullable=True),
            sa.Column("celery_task_id", sa.String(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'running', 'completed', 'failed')",
                name="ck_project_purge_jobs_status",
            ),
            sa.CheckConstraint(
                "progress >= 0 AND progress <= 100",
                name="ck_project_purge_jobs_progress_range",
            ),
        )
    if "ix_project_purge_jobs_project_id" not in {i["name"] for i in _insp().get_indexes(_JOBS)}:
        op.create_index("ix_project_purge_jobs_project_id", _JOBS, ["project_id"])


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_table(_JOBS):
        op.drop_table(_JOBS)
    for table, column, referred, _name in _CASCADES:
        existing = _fk(table, column, referred)
        if existing is not None:
            op.drop_constraint(existing[0], table, type_="foreignkey")
    # The job key existed before 140, without ON DELETE.
    op.create_foreign_key(
        "generations_generation_id_fkey", "generations", "response_generations",
        ["generation_id"], ["id"],
    )
