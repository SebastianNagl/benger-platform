"""Shape tests for migration 156: submission_files.purpose and
task_evaluation_id, and the upload_batches table.

The shared test DB already carries both (created from the models by
``Base.metadata.create_all``), so ``upgrade()`` must be a clean no-op through
its inspector guards, twice. ``downgrade()`` removes them and a re-run
``upgrade()`` restores the columns, the check constraints, the foreign key
rules and the indexes.
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
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "156_upload_batches_and_grading_files.py",
    )
)

FILES = "submission_files"
BATCHES = "upload_batches"


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_156", MIGRATION_PATH)
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


def _shape(conn):
    insp = inspect(conn)
    columns = {c["name"]: c for c in insp.get_columns(FILES)}
    return {
        "purpose": columns.get("purpose"),
        "task_evaluation_id": columns.get("task_evaluation_id"),
        "checks": {c["name"] for c in insp.get_check_constraints(FILES)},
        "indexes": {i["name"] for i in insp.get_indexes(FILES)},
        "fk_rules": {
            fk["referred_table"]: (fk.get("options") or {}).get("ondelete")
            for fk in insp.get_foreign_keys(FILES)
        },
        "batches": insp.has_table(BATCHES),
    }


def _people_and_task(db: Session):
    from models import User
    from project_models import Project, Task

    owner = User(
        id=str(uuid.uuid4()),
        username=f"mig156-{uuid.uuid4().hex[:8]}",
        email=f"mig156-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Mig 156",
    )
    db.add(owner)
    db.flush()
    project = Project(id=str(uuid.uuid4()), title="mig156", created_by=owner.id)
    db.add(project)
    db.flush()
    task = Task(id=str(uuid.uuid4()), project_id=project.id, data={}, inner_id=1)
    db.add(task)
    db.flush()
    return owner, project, task


def _file(owner, project, task, **extra):
    from project_models import SubmissionFile

    return SubmissionFile(
        id=str(uuid.uuid4()),
        project_id=project.id,
        task_id=task.id,
        user_id=owner.id,
        storage_key=f"submissions/{uuid.uuid4().hex}.pdf",
        original_filename="a.pdf",
        size_bytes=1,
        sha256="0" * 64,
        source_format="pdf",
        **extra,
    )


class TestMigration156Shape:
    def test_revision_chains_after_155(self):
        mig = _load_migration()
        assert mig.revision == "156_upload_batches_and_grading_files"
        assert mig.down_revision == "155_add_evaluation_released_notification_type"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        before = _shape(conn)
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        after = _shape(conn)
        assert after["purpose"] is not None and after["purpose"]["nullable"] is False
        assert after["task_evaluation_id"]["nullable"] is True
        assert after["checks"] == before["checks"]
        assert after["fk_rules"]["task_evaluations"] == "SET NULL"
        assert after["batches"]

    def test_downgrade_then_upgrade_restores_the_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        gone = _shape(conn)
        assert gone["purpose"] is None and gone["task_evaluation_id"] is None
        assert "ck_submission_files_purpose" not in gone["checks"]
        assert "task_evaluations" not in gone["fk_rules"]
        assert not gone["batches"]
        with _op_context(conn):
            mig.upgrade()
        back = _shape(conn)
        assert back["purpose"]["nullable"] is False
        assert "submission" in str(back["purpose"]["default"])
        assert "ck_submission_files_purpose" in back["checks"]
        assert "ix_submission_files_task_evaluation" in back["indexes"]
        assert back["fk_rules"]["task_evaluations"] == "SET NULL"
        insp = inspect(conn)
        assert {"ck_upload_batches_status"} <= {c["name"] for c in insp.get_check_constraints(BATCHES)}
        assert {"ix_upload_batches_project_created", "ix_upload_batches_task"} <= {
            i["name"] for i in insp.get_indexes(BATCHES)
        }
        rules = {
            tuple(fk["constrained_columns"]): (fk.get("options") or {}).get("ondelete")
            for fk in insp.get_foreign_keys(BATCHES)
        }
        assert rules == {
            ("project_id",): "CASCADE",
            ("task_id",): "SET NULL",
            ("created_by",): "SET NULL",
            ("undone_by",): "SET NULL",
        }

    def test_existing_rows_become_handed_in_files(self, test_db: Session):
        """A row written before the column exists reads ``submission``."""
        conn = test_db.get_bind()
        mig = _load_migration()
        owner, project, task = _people_and_task(test_db)
        with _op_context(conn):
            mig.downgrade()
        conn.execute(
            text(
                "INSERT INTO submission_files (id, project_id, task_id, user_id, storage_key,"
                " original_filename, size_bytes, sha256, source_format, extracted_chars)"
                " VALUES (:id, :p, :t, :u, 'k', 'a.pdf', 1, :sha, 'pdf', 0)"
            ),
            {"id": "mig156-old", "p": project.id, "t": task.id, "u": owner.id, "sha": "0" * 64},
        )
        with _op_context(conn):
            mig.upgrade()
        purpose = conn.execute(
            text("SELECT purpose FROM submission_files WHERE id = 'mig156-old'")
        ).scalar_one()
        assert purpose == "submission"


class TestRules:
    def test_purpose_defaults_and_is_checked(self, test_db: Session):
        owner, project, task = _people_and_task(test_db)
        row = _file(owner, project, task)
        test_db.add(row)
        test_db.flush()
        assert row.purpose == "submission"
        test_db.add(_file(owner, project, task, purpose="scan"))
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_a_grading_file_outlives_its_grading_row(self, test_db: Session):
        from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation

        owner, project, task = _people_and_task(test_db)
        run = EvaluationRun(
            id=str(uuid.uuid4()), project_id=project.id, model_id="m",
            evaluation_type_ids=["x"], metrics={}, status="completed", created_by=owner.id,
        )
        test_db.add(run)
        test_db.flush()
        judge = EvaluationJudgeRun(id=str(uuid.uuid4()), evaluation_id=run.id, status="completed")
        test_db.add(judge)
        test_db.flush()
        grading = TaskEvaluation(
            id=str(uuid.uuid4()), evaluation_id=run.id, judge_run_id=judge.id, task_id=task.id,
            field_name="answer", answer_type="text", ground_truth={}, prediction={}, metrics={},
            passed=True,
        )
        test_db.add(grading)
        test_db.flush()
        row = _file(owner, project, task, purpose="grading", task_evaluation_id=grading.id)
        test_db.add(row)
        test_db.flush()
        test_db.delete(grading)
        test_db.flush()
        test_db.refresh(row)
        assert row.task_evaluation_id is None and row.purpose == "grading"

    def test_upload_batch_defaults_status_check_and_task_delete(self, test_db: Session):
        from project_models import UploadBatch

        owner, project, task = _people_and_task(test_db)
        batch = UploadBatch(id=str(uuid.uuid4()), project_id=project.id, task_id=task.id,
                            kind="example", created_by=owner.id)
        test_db.add(batch)
        test_db.flush()
        test_db.refresh(batch)
        assert (batch.status, batch.options, batch.report, batch.rows_total, batch.rows_written) == (
            "committed", {}, [], 0, 0,
        )
        assert batch.created_at is not None
        test_db.delete(task)
        test_db.flush()
        test_db.refresh(batch)
        assert batch.task_id is None
        test_db.add(UploadBatch(id=str(uuid.uuid4()), project_id=project.id, kind="example",
                                status="pending"))
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()
