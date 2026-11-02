"""Shape tests for migration 125: submission_ocr_jobs + OCR columns.

The shared test DB already carries everything (``Base.metadata.create_all``),
so ``upgrade()`` must be a no-op through its guards, twice. ``downgrade()``
removes the table and columns, a re-run ``upgrade()`` rebuilds them, and the
check constraint only lets ``pending`` jobs go without a user.
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

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "alembic", "versions",
        "125_submission_ocr_jobs.py",
    )
)


def _load_migration(path=MIGRATION_PATH, name="mig_125"):
    spec = importlib.util.spec_from_file_location(name, path)
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


def _columns(conn, table):
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _project_and_task(test_db: Session):
    from models import User
    from project_models import Project, Task

    owner = User(
        id=str(uuid.uuid4()),
        username=f"mig125-{uuid.uuid4().hex[:8]}",
        email=f"mig125-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Mig 125",
    )
    test_db.add(owner)
    test_db.flush()
    project = Project(id=str(uuid.uuid4()), title="mig125", created_by=owner.id)
    test_db.add(project)
    test_db.flush()
    task = Task(id=str(uuid.uuid4()), project_id=project.id, data={"text": "x"}, inner_id=1)
    test_db.add(task)
    test_db.flush()
    return owner, project, task


class TestMigration125Shape:
    def test_revision_chains_after_124(self):
        mig = _load_migration()
        assert mig.revision == "125_submission_ocr_jobs"
        assert mig.down_revision == "124_project_allow_solution_upload"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        jobs = _columns(conn, "submission_ocr_jobs")
        assert jobs["user_id"]["nullable"] is True
        assert jobs["mode"]["nullable"] is False
        assert "ocr_job_id" in _columns(conn, "submission_files")
        assert _columns(conn, "projects")["handwriting_ocr_model"]["nullable"] is True
        assert _columns(conn, "projects")["handwriting_ocr_enabled"]["nullable"] is False

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        # 126 (pending_submission_uploads) references submission_ocr_jobs, so
        # it goes first, as in a real downgrade, and comes back last.
        later = _load_migration(
            MIGRATION_PATH.replace("125_submission_ocr_jobs", "126_pending_submission_uploads"),
            "mig_126",
        )
        with _op_context(conn):
            later.downgrade()
            mig.downgrade()
        assert "submission_ocr_jobs" not in inspect(conn).get_table_names()
        assert "ocr_job_id" not in _columns(conn, "submission_files")
        assert "handwriting_ocr_model" not in _columns(conn, "projects")
        assert "handwriting_ocr_enabled" not in _columns(conn, "projects")
        with _op_context(conn):
            mig.upgrade()
            later.upgrade()
        assert "submission_ocr_jobs" in inspect(conn).get_table_names()
        assert "page_index" in _columns(conn, "submission_files")
        assert "pending_submission_uploads" in inspect(conn).get_table_names()

    def test_only_pending_jobs_may_lack_a_user(self, test_db: Session):
        _, project, task = _project_and_task(test_db)
        conn = test_db.get_bind()
        conn.execute(
            text(
                "INSERT INTO submission_ocr_jobs (id, project_id, task_id, mode) "
                "VALUES (:id, :p, :t, 'pending')"
            ),
            {"id": str(uuid.uuid4()), "p": project.id, "t": task.id},
        )
        savepoint = conn.begin_nested()
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO submission_ocr_jobs (id, project_id, task_id, mode) "
                    "VALUES (:id, :p, :t, 'own')"
                ),
                {"id": str(uuid.uuid4()), "p": project.id, "t": task.id},
            )
        savepoint.rollback()


class TestAttachOcrJobToUser:
    def _job(self, test_db, project, task, requester):
        from project_models import SubmissionOcrJob

        job = SubmissionOcrJob(
            id=str(uuid.uuid4()),
            project_id=project.id,
            task_id=task.id,
            user_id=None,
            requested_by=requester.id,
            mode="pending",
            status="done",
            page_keys=[
                {"storage_key": "submissions/a.jpg", "original_filename": "a.jpg",
                 "content_type": "image/jpeg", "size_bytes": 10, "sha256": "a" * 64},
                {"storage_key": "submissions/b.pdf", "original_filename": "b.pdf",
                 "content_type": "application/pdf", "size_bytes": 20, "sha256": "b" * 64},
            ],
            page_count=3,
            text="Transkript",
        )
        test_db.add(job)
        test_db.flush()
        return job

    def test_attach_creates_files_and_sets_user(self, test_db: Session):
        from models import User
        from project_models import attach_ocr_job_to_user

        owner, project, task = _project_and_task(test_db)
        student = User(
            id=str(uuid.uuid4()), username=f"s-{uuid.uuid4().hex[:8]}",
            email=f"s-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", name="S",
        )
        test_db.add(student)
        test_db.flush()
        job = self._job(test_db, project, task, owner)

        rows = attach_ocr_job_to_user(test_db, job, student.id)
        test_db.flush()

        assert job.user_id == student.id and job.mode == "on_behalf"
        assert [r.page_index for r in rows] == [0, 1]
        assert [r.source_format for r in rows] == ["image", "pdf"]
        assert all(r.ocr_job_id == job.id and r.uploaded_by == owner.id for r in rows)
        # idempotent for the same person
        assert attach_ocr_job_to_user(test_db, job, student.id) == []

    def test_attach_to_someone_else_is_refused(self, test_db: Session):
        from project_models import attach_ocr_job_to_user

        owner, project, task = _project_and_task(test_db)
        job = self._job(test_db, project, task, owner)
        attach_ocr_job_to_user(test_db, job, owner.id)
        with pytest.raises(ValueError):
            attach_ocr_job_to_user(test_db, job, str(uuid.uuid4()))
