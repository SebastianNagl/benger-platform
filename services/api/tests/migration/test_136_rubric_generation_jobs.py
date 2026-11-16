"""Shape tests for migration 136: rubric_generation_jobs.

The shared test DB already carries the table (``Base.metadata.create_all``),
so ``upgrade()`` must be a no-op through its guards, twice. ``downgrade()``
drops the table and a re-run ``upgrade()`` rebuilds it with its checks,
unique ``celery_task_id`` and ``SET NULL`` foreign keys.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"mig_{name}", os.path.join(VERSIONS, f"{name}.py"))
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


def _seed(test_db: Session):
    from models import Organization, User
    from project_models import Project, Task, TaskRubric

    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=str(uuid.uuid4()), username=f"mig136-{suffix}", email=f"mig136-{suffix}@example.com",
        hashed_password="x", name="Mig 136",
    )
    org = Organization(
        id=str(uuid.uuid4()), name=f"Org {suffix}", display_name=f"Org {suffix}", slug=f"org-{suffix}",
    )
    test_db.add_all([user, org])
    test_db.flush()
    project = Project(id=str(uuid.uuid4()), title="mig136", created_by=user.id)
    test_db.add(project)
    test_db.flush()
    task = Task(id=str(uuid.uuid4()), project_id=project.id, data={"text": "x"}, inner_id=1)
    test_db.add(task)
    test_db.flush()
    rubric = TaskRubric(
        id=str(uuid.uuid4()), task_id=task.id, project_id=project.id,
        criteria={"s01": {"name": "A", "rubric": "r", "max_score": 10}}, total_points=10,
    )
    test_db.add(rubric)
    test_db.flush()
    return user, org, project, task, rubric


def _insert(conn, **values):
    values.setdefault("id", str(uuid.uuid4()))
    values.setdefault("entry_point", "task")
    columns = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    conn.execute(text(f"INSERT INTO rubric_generation_jobs ({columns}) VALUES ({params})"), values)
    return values["id"]


class TestMigration136:
    def test_revision_chains_after_135(self):
        mig = _load("136_rubric_generation_jobs")
        assert mig.revision == "136_rubric_generation_jobs"
        assert mig.down_revision == "135_custom_model_request_timeout"

    def test_upgrade_is_idempotent_and_matches_the_model(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load("136_rubric_generation_jobs")
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        from project_models import RubricGenerationJob

        columns = {c["name"]: c for c in inspect(conn).get_columns("rubric_generation_jobs")}
        assert set(columns) == {c.name for c in RubricGenerationJob.__table__.columns}
        assert columns["entry_point"]["nullable"] is False
        assert columns["details"]["nullable"] is False
        indexes = {i["name"] for i in inspect(conn).get_indexes("rubric_generation_jobs")}
        assert {name for name, _ in mig._INDEXES} <= indexes

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load("136_rubric_generation_jobs")
        with _op_context(conn):
            mig.downgrade()
        assert "rubric_generation_jobs" not in inspect(conn).get_table_names()
        with _op_context(conn):
            mig.upgrade()
        assert "rubric_generation_jobs" in inspect(conn).get_table_names()
        # The rebuilt table takes a row with every foreign key NULL and the
        # server defaults fill status and details.
        job_id = _insert(conn, celery_task_id=None)
        row = conn.execute(
            text("SELECT status, details FROM rubric_generation_jobs WHERE id = :id"), {"id": job_id}
        ).one()
        assert row.status == "queued" and row.details == {}

    @pytest.mark.parametrize(
        "column,value",
        [("status", "done"), ("entry_point", "cli")],
    )
    def test_checks_reject_unknown_values(self, test_db: Session, column, value):
        conn = test_db.get_bind()
        savepoint = conn.begin_nested()
        with pytest.raises(IntegrityError):
            _insert(conn, **{column: value})
        savepoint.rollback()

    def test_celery_task_id_is_unique(self, test_db: Session):
        conn = test_db.get_bind()
        celery_id = f"celery-{uuid.uuid4()}"
        _insert(conn, celery_task_id=celery_id)
        savepoint = conn.begin_nested()
        with pytest.raises(IntegrityError):
            _insert(conn, celery_task_id=celery_id)
        savepoint.rollback()

    def test_every_foreign_key_sets_null_on_delete(self, test_db: Session):
        user, org, project, task, rubric = _seed(test_db)
        conn = test_db.get_bind()
        first = _insert(conn, project_id=project.id, task_id=task.id, user_id=user.id,
                        organization_id=org.id, rubric_id=rubric.id)
        retry = _insert(conn, retry_of=first, project_id=project.id)

        conn.execute(text("DELETE FROM task_rubrics WHERE id = :id"), {"id": rubric.id})
        conn.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task.id})
        conn.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project.id})
        conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org.id})
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
        row = conn.execute(
            text("SELECT * FROM rubric_generation_jobs WHERE id = :id"), {"id": first}
        ).mappings().one()
        assert all(
            row[fk] is None
            for fk in ("project_id", "task_id", "user_id", "organization_id", "rubric_id")
        )
        conn.execute(text("DELETE FROM rubric_generation_jobs WHERE id = :id"), {"id": first})

        row = conn.execute(
            text("SELECT * FROM rubric_generation_jobs WHERE id = :id"), {"id": retry}
        ).mappings().one()
        assert row["retry_of"] is None and row["project_id"] is None
        test_db.expire_all()
