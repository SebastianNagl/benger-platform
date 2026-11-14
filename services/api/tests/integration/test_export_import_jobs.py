"""Model tests for ExportJob / ImportJob (issue #158).

These rows track async export/import jobs whose bulk data plane lives in object
storage rather than the request thread. The tests assert the server-side
defaults and the CHECK constraints that guard ``status`` and ``progress``.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models import ExportJob, ImportJob, JobStatus, User
from project_models import Project


@pytest.fixture
def project_and_user(test_db):
    user = User(
        id=str(uuid.uuid4()),
        email=f"jobs-{uuid.uuid4().hex[:8]}@example.com",
        username=f"jobsuser-{uuid.uuid4().hex[:8]}",
        name="Jobs User",
        is_active=True,
    )
    test_db.add(user)
    test_db.flush()

    project = Project(
        id=str(uuid.uuid4()),
        title="Jobs Test Project",
        created_by=user.id,
    )
    test_db.add(project)
    test_db.flush()
    return project, user


@pytest.mark.integration
class TestExportJobModel:
    def test_defaults_applied_on_insert(self, test_db, project_and_user):
        project, user = project_and_user
        job = ExportJob(
            id=str(uuid.uuid4()),
            project_id=project.id,
            requested_by=user.id,
            format="json",
        )
        test_db.add(job)
        test_db.flush()
        test_db.refresh(job)

        assert job.status == JobStatus.PENDING.value == "pending"
        assert job.progress == 0
        assert job.created_at is not None
        assert job.updated_at is not None
        assert job.object_key is None
        assert job.byte_size is None

    def test_invalid_status_rejected(self, test_db, project_and_user):
        project, user = project_and_user
        job = ExportJob(
            id=str(uuid.uuid4()),
            project_id=project.id,
            requested_by=user.id,
            format="json",
            status="bogus",
        )
        test_db.add(job)
        with pytest.raises(IntegrityError):
            test_db.flush()

    def test_progress_out_of_range_rejected(self, test_db, project_and_user):
        project, user = project_and_user
        job = ExportJob(
            id=str(uuid.uuid4()),
            project_id=project.id,
            requested_by=user.id,
            format="json",
            progress=150,
        )
        test_db.add(job)
        with pytest.raises(IntegrityError):
            test_db.flush()

    def test_byte_size_holds_large_value(self, test_db, project_and_user):
        # BigInteger column must hold a multi-GB artifact size without overflow.
        project, user = project_and_user
        big = 8 * 1024 * 1024 * 1024  # 8 GB, beyond 32-bit Integer range
        job = ExportJob(
            id=str(uuid.uuid4()),
            project_id=project.id,
            requested_by=user.id,
            format="comprehensive",
            status="completed",
            byte_size=big,
            progress=100,
        )
        test_db.add(job)
        test_db.flush()
        test_db.refresh(job)
        assert job.byte_size == big


@pytest.mark.integration
class TestImportJobModel:
    def test_requires_object_key(self, test_db, project_and_user):
        # object_key is NOT NULL — the client uploads before the job is created.
        project, user = project_and_user
        job = ImportJob(
            id=str(uuid.uuid4()),
            project_id=project.id,
            requested_by=user.id,
        )
        test_db.add(job)
        with pytest.raises(IntegrityError):
            test_db.flush()

    def test_nullable_project_id_for_comprehensive_import(self, test_db, project_and_user):
        # Comprehensive import creates its target project, so project_id is unknown
        # at job-creation time → must be nullable.
        _, user = project_and_user
        job = ImportJob(
            id=str(uuid.uuid4()),
            project_id=None,
            requested_by=user.id,
            object_key="imports/u1/file.json",
        )
        test_db.add(job)
        test_db.flush()
        test_db.refresh(job)
        assert job.project_id is None
        assert job.status == "pending"
        assert job.progress == 0

    def test_result_jsonb_round_trips(self, test_db, project_and_user):
        project, user = project_and_user
        summary = {"created_tasks": 12, "created_annotations": 34, "nested": {"x": [1, 2]}}
        job = ImportJob(
            id=str(uuid.uuid4()),
            project_id=project.id,
            requested_by=user.id,
            object_key="imports/u1/file.json",
            status="completed",
            progress=100,
            result=summary,
        )
        test_db.add(job)
        test_db.flush()
        test_db.refresh(job)
        assert job.result == summary


@pytest.mark.integration
class TestJobCompletionTime:
    """``updated_at`` of a job is when the job last changed, i.e. its
    completion time once it is final. The export worker streams the whole
    export inside one transaction and marks the job completed at its end;
    Postgres ``now()`` is the start of the transaction, so an ``updated_at``
    taken from it showed a 529 s export as finished about 1 s after it was
    created. One transaction that outlives a sleep reproduces that here."""

    @pytest.mark.parametrize("model", [ExportJob, ImportJob])
    def test_completion_in_a_long_transaction_records_the_wall_clock(
        self, test_db, project_and_user, model
    ):
        project, user = project_and_user
        job = model(
            id=str(uuid.uuid4()),
            project_id=project.id,
            requested_by=user.id,
            format="ndjson_gz",
            object_key="imports/u1/file.json" if model is ImportJob else None,
        )
        test_db.add(job)
        test_db.flush()
        test_db.refresh(job)
        created = job.created_at

        test_db.execute(text("SELECT pg_sleep(0.3)"))
        job.status = "completed"
        job.progress = 100
        test_db.flush()
        test_db.refresh(job)

        assert (job.updated_at - created).total_seconds() >= 0.3
