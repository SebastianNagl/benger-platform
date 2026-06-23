"""Integration tests for the async export-job API (issue #158).

The synchronous ``GET /{project_id}/export`` streams the whole project through
the API request thread — fine for small projects, but it OOMKilled the pod on
the Benchathon export. The async job endpoints move the bulk data plane off the
request path:

  * ``POST /{project_id}/exports``            -> create job + enqueue worker (202)
  * ``GET  /{project_id}/exports/{job_id}``   -> poll status
  * ``GET  /{project_id}/exports/{job_id}/download`` -> presigned download

These tests lock the HTTP contract: 202/job-creation + enqueue, status fields +
authz (requester vs. project-write-access vs. forbidden, cross-project leak
guard), and download gating (404 until completed, 410 once expired, 302 / JSON
URL when ready). The worker body itself is covered in
``services/workers/tests/test_export_task.py``; here ``send_task_safe`` and
``object_storage.get_download_url`` are mocked so we exercise only the endpoints.

Async-DB migration note: the export-job endpoints now depend on
``get_async_db``, so these tests seed real rows via ``async_test_db`` and drive
the surface through ``async_test_client``. ``require_user`` is overridden
per-test (the sync auth path can't see the async test transaction); org
memberships are seeded so the contributor-write-access branch resolves for
real.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    ExportJob,
    JobStatus,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import Project, ProjectOrganization


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, is_superadmin=False, name="User") -> User:
    u = User(
        id=_uid(),
        username=f"ej-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_org(db, *, name="Export Org") -> Organization:
    oid = _uid()
    org = Organization(
        id=oid,
        name=name,
        display_name=name,
        slug=f"org-{oid[:8]}",
    )
    db.add(org)
    await db.flush()
    return org


async def _add_member(db, user, org, role):
    db.add(
        OrganizationMembership(
            id=_uid(),
            user_id=user.id,
            organization_id=org.id,
            role=role,
            is_active=True,
        )
    )
    await db.flush()


async def _make_project(db, *, owner, org) -> Project:
    project = Project(
        id=_uid(),
        title="Export Jobs Project",
        description="async export-job fixture",
        created_by=owner.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    await db.flush()
    db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=org.id,
            assigned_by=owner.id,
        )
    )
    await db.flush()
    return project


async def _make_job(db, project, requested_by, **overrides) -> ExportJob:
    job = ExportJob(
        id=_uid(),
        project_id=project.id,
        requested_by=requested_by,
        format=overrides.pop("format", "json"),
        status=overrides.pop("status", JobStatus.PENDING.value),
        progress=overrides.pop("progress", 0),
        **overrides,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _seed_world(db):
    """Seed admin owner + org + a CONTRIBUTOR and ANNOTATOR member, and a
    project bound to the org. Returns (admin, contributor, annotator, org,
    project)."""
    org = await _make_org(db)
    admin = await _make_user(db, is_superadmin=True, name="Admin")
    contributor = await _make_user(db, name="Contributor")
    annotator = await _make_user(db, name="Annotator")
    await _add_member(db, admin, org, OrganizationRole.ORG_ADMIN)
    await _add_member(db, contributor, org, OrganizationRole.CONTRIBUTOR)
    await _add_member(db, annotator, org, OrganizationRole.ANNOTATOR)
    project = await _make_project(db, owner=admin, org=org)
    await db.commit()
    return admin, contributor, annotator, org, project


async def _get_job(db, job_id):
    return (
        await db.execute(select(ExportJob).where(ExportJob.id == job_id))
    ).scalar_one_or_none()


@pytest.mark.integration
class TestCreateExportJob:
    @pytest.mark.asyncio
    async def test_post_creates_pending_job_and_enqueues(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        fake_result = MagicMock()
        fake_result.id = "celery-task-xyz"
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.send_task_safe", return_value=fake_result
        ) as mock_send:
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/exports?format=json",
                headers={"X-Organization-Context": org.id},
            )

        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == JobStatus.PENDING.value
        job_id = body["job_id"]

        # Enqueued exactly once, targeting the worker task with the job id.
        mock_send.assert_called_once()
        assert mock_send.call_args.args[0] == "tasks.export_project"
        assert mock_send.call_args.kwargs["args"] == [job_id]

        # Row persisted with the celery task id captured for traceability.
        job = await _get_job(async_test_db, job_id)
        assert job is not None
        assert job.status == JobStatus.PENDING.value
        assert job.format == "json"
        assert job.requested_by == admin.id
        assert job.celery_task_id == "celery-task-xyz"

    @pytest.mark.asyncio
    async def test_post_unknown_project_404(self, async_test_client, async_test_db):
        admin, _contrib, _annot, org, _project = await _seed_world(async_test_db)
        with _as_user(admin), patch(
            "routers.projects.import_export.send_task_safe"
        ):
            resp = await async_test_client.post(
                f"/api/projects/{_uid()}/exports?format=json",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_post_invalid_format_422(self, async_test_client, async_test_db):
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/exports?format=bogus",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_post_enqueue_failure_marks_job_failed_503(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.send_task_safe",
            side_effect=RuntimeError("broker down"),
        ):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/exports?format=json",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 503
        # The pre-created job must not be left dangling as pending.
        job = (
            await async_test_db.execute(
                select(ExportJob).where(ExportJob.project_id == project.id)
            )
        ).scalars().first()
        assert job is not None
        assert job.status == JobStatus.FAILED.value
        assert "broker down" in (job.error_message or "")


@pytest.mark.integration
class TestGetExportJobStatus:
    @pytest.mark.asyncio
    async def test_status_returns_job_fields(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, _org, project = await _seed_world(async_test_db)
        job = await _make_job(
            async_test_db,
            project,
            admin.id,
            status=JobStatus.RUNNING.value,
            progress=42,
            byte_size=12345,
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{job.id}",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job.id
        assert body["project_id"] == project.id
        assert body["status"] == JobStatus.RUNNING.value
        assert body["progress"] == 42
        assert body["byte_size"] == 12345
        assert body["created_at"] is not None

    @pytest.mark.asyncio
    async def test_status_unknown_job_404(self, async_test_client, async_test_db):
        admin, _contrib, _annot, _org, project = await _seed_world(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{_uid()}",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_cross_project_job_404(
        self, async_test_client, async_test_db
    ):
        # A job that exists but belongs to a *different* project must 404 (not
        # 403) under this project's URL — don't leak job-id existence.
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        other = await _make_project(async_test_db, owner=admin, org=org)
        job = await _make_job(async_test_db, other, admin.id)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{job.id}",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_forbidden_for_non_requester_without_write(
        self, async_test_client, async_test_db
    ):
        # Job requested by admin; annotator is neither requester nor a writer.
        admin, _contrib, annotator, _org, project = await _seed_world(async_test_db)
        job = await _make_job(async_test_db, project, admin.id)
        with _as_user(annotator):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{job.id}",
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_status_allowed_for_contributor_with_write(
        self, async_test_client, async_test_db
    ):
        # Job requested by admin; a CONTRIBUTOR org member has write access and
        # may inspect a colleague's export job.
        admin, contributor, _annot, _org, project = await _seed_world(async_test_db)
        job = await _make_job(async_test_db, project, admin.id)
        with _as_user(contributor):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{job.id}",
            )
        assert resp.status_code == 200


@pytest.mark.integration
class TestDownloadExportJob:
    @pytest.mark.asyncio
    async def test_download_404_when_not_completed(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, _org, project = await _seed_world(async_test_db)
        job = await _make_job(
            async_test_db, project, admin.id, status=JobStatus.RUNNING.value
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{job.id}/download",
                follow_redirects=False,
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_410_when_expired(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, _org, project = await _seed_world(async_test_db)
        job = await _make_job(
            async_test_db,
            project,
            admin.id,
            status=JobStatus.COMPLETED.value,
            object_key="exports/old.json",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{job.id}/download",
                follow_redirects=False,
            )
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_download_redirects_to_presigned_url(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, _org, project = await _seed_world(async_test_db)
        job = await _make_job(
            async_test_db,
            project,
            admin.id,
            status=JobStatus.COMPLETED.value,
            object_key="exports/ready.json",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        presigned = "https://storage.example/presigned-get?sig=abc"
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.get_download_url",
            return_value=presigned,
        ) as mock_url:
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{job.id}/download",
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert resp.headers["location"] == presigned
        # Object key is read from the DB row, never trusted from the client.
        assert mock_url.call_args.args[0] == "exports/ready.json"
        assert mock_url.call_args.kwargs["expires_in"] == 300
        assert "attachment" in mock_url.call_args.kwargs[
            "response_content_disposition"
        ]

    @pytest.mark.asyncio
    async def test_download_json_mode_returns_url_body(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, _org, project = await _seed_world(async_test_db)
        job = await _make_job(
            async_test_db,
            project,
            admin.id,
            status=JobStatus.COMPLETED.value,
            object_key="exports/ready.json",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        presigned = "https://storage.example/presigned-get?sig=def"
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.get_download_url",
            return_value=presigned,
        ):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/exports/{job.id}/download?json=1",
                follow_redirects=False,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["url"] == presigned
        assert body["expires_in"] == 300
