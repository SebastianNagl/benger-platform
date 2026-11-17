"""Migration 140: generation rows cascade from task and project; purge jobs.

The shared test DB is built from the models, so it already has the cascading
keys and the ``project_purge_jobs`` table: ``upgrade()`` must be a no-op
there. After ``downgrade()`` (the pre-140 schema) orphans of a purged project
can be inserted again, and ``upgrade()`` must remove exactly those before it
adds the keys. Everything runs in the test transaction and is rolled back.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)
NAME = "140_generation_cascades_and_purge_jobs"


def _load():
    spec = importlib.util.spec_from_file_location(f"mig_{NAME}", os.path.join(VERSIONS, f"{NAME}.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _on_delete(conn, table, column, referred):
    """pg_constraint.confdeltype of the FK, or None when there is none."""
    return conn.execute(
        text(
            """
            SELECT c.confdeltype FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            WHERE c.contype = 'f' AND c.conrelid = CAST(:t AS regclass)
              AND c.confrelid = CAST(:r AS regclass) AND a.attname = :c
            """
        ),
        {"t": table, "r": referred, "c": column},
    ).scalar()


KEYS = (
    ("generations", "generation_id", "response_generations"),
    ("generations", "task_id", "tasks"),
    ("response_generations", "task_id", "tasks"),
    ("response_generations", "project_id", "projects"),
)


def _seed_project(test_db: Session):
    from models import User
    from project_models import Project, Task

    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()), username=f"mig140-{suffix}", email=f"mig140-{suffix}@example.com",
        hashed_password="x", name="Mig 140",
    )
    test_db.add(user)
    test_db.flush()
    project = Project(id=str(uuid.uuid4()), title="mig140", created_by=user.id)
    test_db.add(project)
    test_db.flush()
    task = Task(id=str(uuid.uuid4()), project_id=project.id, data={"text": "x"}, inner_id=1)
    test_db.add(task)
    test_db.flush()
    return user, project, task


def _job(conn, project_id, task_id) -> str:
    job_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO response_generations (id, project_id, task_id, model_id, status, "
            "responses_generated, created_by) VALUES (:id, :p, :t, 'm', 'completed', 1, 'x')"
        ),
        {"id": job_id, "p": project_id, "t": task_id},
    )
    return job_id


def _generation(conn, job_id, task_id, run_index=0) -> str:
    gen_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO generations (id, generation_id, task_id, model_id, case_data, "
            "response_content, status, run_index) "
            "VALUES (:id, :j, :t, 'm', 'c', 'r', 'completed', :run)"
        ),
        {"id": gen_id, "j": job_id, "t": task_id, "run": run_index},
    )
    return gen_id


def _exists(conn, table, row_id) -> bool:
    return conn.execute(text(f"SELECT 1 FROM {table} WHERE id = :id"), {"id": row_id}).first() is not None


class TestMigration140:
    def test_revision_chains_after_139(self):
        mig = _load()
        assert mig.revision == NAME
        assert mig.down_revision == "139_task_evaluation_metric_keys_scores"

    def test_upgrade_is_a_no_op_on_the_model_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        for key in KEYS:
            assert _on_delete(conn, *key) == "c", key
        from models import ProjectPurgeJob

        columns = {c["name"] for c in inspect(conn).get_columns("project_purge_jobs")}
        assert columns == {c.name for c in ProjectPurgeJob.__table__.columns}

    def test_downgrade_restores_the_old_keys(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        assert "project_purge_jobs" not in inspect(conn).get_table_names()
        assert _on_delete(conn, "generations", "generation_id", "response_generations") == "a"
        for key in KEYS[1:]:
            assert _on_delete(conn, *key) is None, key

    def test_upgrade_removes_the_orphans_then_cascades(self, test_db: Session):
        _, project, task = _seed_project(test_db)
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()

        # Rows of the live project, task-level and project-level.
        kept_job = _job(conn, project.id, task.id)
        kept_gen = _generation(conn, kept_job, task.id)
        kept_project_job = _job(conn, project.id, None)
        kept_fanout = _generation(conn, kept_project_job, task.id)
        # Orphans a purge left behind before 140: the project and task ids no
        # longer exist, and the job of a live task whose project row is gone.
        orphan_job = _job(conn, "purged-project", "purged-task")
        orphan_gen = _generation(conn, orphan_job, "purged-task")
        orphan_project_job = _job(conn, "purged-project", None)
        orphan_fanout = _generation(conn, orphan_project_job, "purged-task")
        # A generation of a deleted task under a live job (task delete).
        stray_gen = _generation(conn, kept_project_job, "deleted-task", run_index=1)

        with _op_context(conn):
            mig.upgrade()

        for row_id in (orphan_job, orphan_project_job):
            assert not _exists(conn, "response_generations", row_id)
        for row_id in (orphan_gen, orphan_fanout, stray_gen):
            assert not _exists(conn, "generations", row_id)
        for row_id in (kept_job, kept_project_job):
            assert _exists(conn, "response_generations", row_id)
        for row_id in (kept_gen, kept_fanout):
            assert _exists(conn, "generations", row_id)
        for key in KEYS:
            assert _on_delete(conn, *key) == "c", key
        assert "project_purge_jobs" in inspect(conn).get_table_names()

        # The keys now do what the purge relies on.
        conn.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task.id})
        assert not _exists(conn, "response_generations", kept_job)
        assert not _exists(conn, "generations", kept_gen)
        assert not _exists(conn, "generations", kept_fanout)
        assert _exists(conn, "response_generations", kept_project_job)
        conn.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project.id})
        assert not _exists(conn, "response_generations", kept_project_job)
