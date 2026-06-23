"""Integration tests for the async import-job API (issue #158).

The inverse of the async export flow. The synchronous ``POST /{project_id}/import``
and ``POST /import-project`` were removed in the #158 follow-up — object storage is
the only import transport. The async import endpoints move the parse off the
request path:

  * ``POST /{project_id}/imports/upload-url`` -> presigned upload URL
  * ``POST /{project_id}/imports``            -> create job + enqueue worker (202)
  * ``GET  /{project_id}/imports/{job_id}``   -> poll status

These tests lock the HTTP contract: presigned-URL gating + authz, 202/job-creation
+ enqueue, object_key validation (must be under the import prefix AND scoped to
this project), and status fields + authz (requester vs. write-access vs. forbidden,
cross-project leak guard). The worker body is covered in
``services/workers/tests/test_import_task.py``; here ``send_task_safe`` and
``object_storage`` are mocked so we exercise only the endpoints.

Async-DB migration note: the import-job endpoints now depend on ``get_async_db``,
so these tests seed real rows via ``async_test_db`` and drive the surface through
``async_test_client``. ``require_user`` is overridden per-test; org memberships
are seeded so the contributor-write-access branch resolves for real.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    ImportJob,
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
        username=f"ij-{_uid()[:8]}",
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


async def _make_org(db, *, name="Import Org") -> Organization:
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
        title="Import Jobs Project",
        description="async import-job fixture",
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


def _valid_key(project_id: str) -> str:
    """A key shaped like one create_import_upload_url would mint for this project."""
    return f"imports/2026/06/{project_id}/20260601_120000_import.json"


async def _make_job(db, project_id, requested_by, **overrides) -> ImportJob:
    job = ImportJob(
        id=_uid(),
        project_id=project_id,
        requested_by=requested_by,
        object_key=overrides.pop("object_key", _valid_key(project_id or _uid())),
        status=overrides.pop("status", JobStatus.PENDING.value),
        progress=overrides.pop("progress", 0),
        **overrides,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _seed_world(db):
    """Seed admin owner + org + CONTRIBUTOR/ANNOTATOR members, and a project
    bound to the org. Returns (admin, contributor, annotator, org, project)."""
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
        await db.execute(select(ImportJob).where(ImportJob.id == job_id))
    ).scalar_one_or_none()


@pytest.mark.integration
class TestCreateImportUploadUrl:
    @pytest.mark.asyncio
    async def test_returns_presigned_post_when_storage_configured(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        fake_upload = {
            "upload_url": "https://storage.example/upload",
            "method": "POST",
            "file_key": _valid_key(project.id),
            "fields": {"key": _valid_key(project.id)},
        }
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.object_storage.get_upload_url",
            return_value=fake_upload,
        ) as mock_url:
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports/upload-url?filename=import.json",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 200
        assert resp.json()["file_key"] == _valid_key(project.id)
        # Key must be scoped to this project so the later create-job can verify it.
        assert mock_url.call_args.kwargs["file_type"] == "imports"
        assert mock_url.call_args.kwargs["user_id"] == project.id
        assert mock_url.call_args.kwargs["max_size"] > 0

    @pytest.mark.asyncio
    async def test_403_for_non_writer(self, async_test_client, async_test_db):
        admin, _contrib, annotator, org, project = await _seed_world(async_test_db)
        with _as_user(annotator), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports/upload-url",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_404_unknown_project(self, async_test_client, async_test_db):
        admin, _contrib, _annot, org, _project = await _seed_world(async_test_db)
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = await async_test_client.post(
                f"/api/projects/{_uid()}/imports/upload-url",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 404


@pytest.mark.integration
class TestCreateImportJob:
    @pytest.mark.asyncio
    async def test_post_creates_pending_job_and_enqueues(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        key = _valid_key(project.id)
        fake_result = MagicMock()
        fake_result.id = "celery-import-xyz"
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.send_task_safe", return_value=fake_result
        ) as mock_send:
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": key},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == JobStatus.PENDING.value
        job_id = body["job_id"]

        mock_send.assert_called_once()
        assert mock_send.call_args.args[0] == "tasks.import_project"
        assert mock_send.call_args.kwargs["args"] == [job_id]

        job = await _get_job(async_test_db, job_id)
        assert job is not None
        assert job.status == JobStatus.PENDING.value
        assert job.object_key == key
        assert job.project_id == project.id
        assert job.requested_by == admin.id
        assert job.celery_task_id == "celery-import-xyz"

    @pytest.mark.asyncio
    async def test_400_missing_object_key(self, async_test_client, async_test_db):
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports",
                json={},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_400_object_key_outside_import_prefix(
        self, async_test_client, async_test_db
    ):
        # A key not under imports/ must be rejected — a client can't point the
        # worker at an arbitrary stored object (e.g. another project's export).
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": f"exports/2026/06/{project.id}/leak.json"},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_400_object_key_for_different_project(
        self, async_test_client, async_test_db
    ):
        # Correct prefix but scoped to a *different* project id — also rejected.
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": _valid_key(_uid())},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_403_for_non_writer(self, async_test_client, async_test_db):
        admin, _contrib, annotator, org, project = await _seed_world(async_test_db)
        with _as_user(annotator), patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch("routers.projects.import_export.send_task_safe") as mock_send:
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": _valid_key(project.id)},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 403
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueue_failure_marks_job_failed_503(
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
                f"/api/projects/{project.id}/imports",
                json={"object_key": _valid_key(project.id)},
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == 503
        job = (
            await async_test_db.execute(
                select(ImportJob).where(ImportJob.project_id == project.id)
            )
        ).scalars().first()
        assert job is not None
        assert job.status == JobStatus.FAILED.value
        assert "broker down" in (job.error_message or "")


@pytest.mark.integration
class TestGetImportJobStatus:
    @pytest.mark.asyncio
    async def test_status_returns_job_fields(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, _org, project = await _seed_world(async_test_db)
        job = await _make_job(
            async_test_db,
            project.id,
            admin.id,
            status=JobStatus.RUNNING.value,
            progress=42,
            byte_size=12345,
            result={"created_tasks": 7},
        )
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/imports/{job.id}",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job.id
        assert body["project_id"] == project.id
        assert body["status"] == JobStatus.RUNNING.value
        assert body["progress"] == 42
        assert body["byte_size"] == 12345
        assert body["result"] == {"created_tasks": 7}
        assert body["created_at"] is not None

    @pytest.mark.asyncio
    async def test_status_unknown_job_404(self, async_test_client, async_test_db):
        admin, _contrib, _annot, _org, project = await _seed_world(async_test_db)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/imports/{_uid()}",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_cross_project_job_404(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, _annot, org, project = await _seed_world(async_test_db)
        other = await _make_project(async_test_db, owner=admin, org=org)
        job = await _make_job(async_test_db, other.id, admin.id)
        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/imports/{job.id}",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_forbidden_for_non_requester_without_write(
        self, async_test_client, async_test_db
    ):
        admin, _contrib, annotator, _org, project = await _seed_world(async_test_db)
        job = await _make_job(async_test_db, project.id, admin.id)
        with _as_user(annotator):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/imports/{job.id}",
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_status_allowed_for_contributor_with_write(
        self, async_test_client, async_test_db
    ):
        admin, contributor, _annot, _org, project = await _seed_world(async_test_db)
        job = await _make_job(async_test_db, project.id, admin.id)
        with _as_user(contributor):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/imports/{job.id}",
            )
        assert resp.status_code == 200
