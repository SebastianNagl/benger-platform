"""Shape tests for migration 126: pending_submission_uploads.

The shared test DB already carries the table (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guard, twice. ``downgrade()`` drops it and a re-run
``upgrade()`` rebuilds it with the status check and the partial unique index
that allows one open upload per task and email.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "126_pending_submission_uploads.py",
    )
)

TABLE = "pending_submission_uploads"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_126", MIGRATION_PATH)
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


def _task(test_db: Session):
    from models import User
    from project_models import Project, Task

    owner = User(
        id=str(uuid.uuid4()),
        username=f"mig126-{uuid.uuid4().hex[:8]}",
        email=f"mig126-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Mig 126",
    )
    test_db.add(owner)
    test_db.flush()
    project = Project(id=str(uuid.uuid4()), title="mig126", created_by=owner.id)
    test_db.add(project)
    test_db.flush()
    task = Task(id=str(uuid.uuid4()), project_id=project.id, data={}, inner_id=1)
    test_db.add(task)
    test_db.flush()
    return project, task


def _row(project, task, email, status="waiting"):
    from project_models import PendingSubmissionUpload

    return PendingSubmissionUpload(
        id=str(uuid.uuid4()),
        project_id=project.id,
        task_id=task.id,
        email=email,
        original_filename="a.pdf",
        source_format="pdf",
        extracted_text="Antwort",
        status=status,
    )


class TestMigration126Shape:
    def test_revision_id(self):
        mig = _load_migration()
        assert mig.revision == "126_pending_submission_uploads"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        assert inspect(conn).has_table(TABLE)

    def test_downgrade_then_upgrade_rebuilds_table(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        assert not inspect(conn).has_table(TABLE)
        with _op_context(conn):
            mig.upgrade()
        insp = inspect(conn)
        assert insp.has_table(TABLE)
        names = {i["name"] for i in insp.get_indexes(TABLE)}
        assert "uq_pending_submission_uploads_open" in names
        columns = {c["name"] for c in insp.get_columns(TABLE)}
        assert {"invitation_id", "email", "extracted_text", "ocr_job_id", "status"} <= columns


class TestOpenUploadUniqueness:
    def test_one_open_upload_per_task_and_email(self, test_db: Session):
        project, task = _task(test_db)
        test_db.add(_row(project, task, "a@example.com"))
        test_db.flush()
        test_db.add(_row(project, task, "a@example.com", status="extracting"))
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_closed_uploads_do_not_block(self, test_db: Session):
        project, task = _task(test_db)
        test_db.add(_row(project, task, "b@example.com", status="cancelled"))
        test_db.add(_row(project, task, "b@example.com", status="attached"))
        test_db.add(_row(project, task, "b@example.com"))
        test_db.flush()

    def test_unknown_status_is_rejected(self, test_db: Session):
        project, task = _task(test_db)
        test_db.add(_row(project, task, "c@example.com", status="lost"))
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()
