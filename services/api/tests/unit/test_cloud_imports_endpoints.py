"""Tests for the cloud-import endpoints (org storage connections → ImportJobs).

Targets: routers/projects/import_export.py —
``POST /api/projects/{id}/cloud-imports`` (fan-out job creation) and
``GET /api/projects/{id}/cloud-imports`` (history). Pins the gates (project
write access AND active membership in the connection's org), the prefix jail
and extension/key-cap validation, the one-job-per-file fan-out with
``source_connection_id`` set, and the joined-connection-name history read.

Async DB lane fixtures like ``test_org_api_keys_router.py``; celery enqueue is
patched at the router module (``send_task_safe``).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import status
from sqlalchemy import select

import org_storage_connection_service as storage_conn_service
from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    ImportJob,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrgStorageConnection,
    User as DBUser,
)
from project_models import Project


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


def _uid():
    return str(uuid.uuid4())


async def _seed_user(db, *, is_superadmin=False):
    u = DBUser(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@e.com",
        name="U",
        hashed_password="x",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_org(db):
    o = Organization(
        id=_uid(),
        name=f"org-{_uid()[:6]}",
        display_name="Org",
        slug=f"org-{_uid()[:8]}",
        is_active=True,
        settings={},
    )
    db.add(o)
    await db.flush()
    return o


async def _seed_project(db, owner):
    p = Project(
        id=_uid(),
        title=f"Cloud Import Project {uuid.uuid4().hex[:6]}",
        description="cloud import tests",
        created_by=owner.id,
        is_private=False,
        label_config="<View><Text name='text' value='$text'/></View>",
        assignment_mode="open",
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_connection(db, org, *, prefix="in/"):
    conn = OrgStorageConnection(
        id=_uid(),
        organization_id=org.id,
        name=f"Bucket {uuid.uuid4().hex[:6]}",
        endpoint_url="https://minio.example.com:9000",
        bucket="customer-bucket",
        prefix=prefix,
        use_ssl=True,
        encrypted_access_key=storage_conn_service.encrypt_secret("AKIAFAKEF4K3"),
        encrypted_secret_key=storage_conn_service.encrypt_secret("very-secret-key"),
    )
    db.add(conn)
    await db.flush()
    return conn


@contextmanager
def _enqueue_ok():
    with patch(
        "routers.projects.import_export.send_task_safe",
        return_value=SimpleNamespace(id="celery-task-1"),
    ) as mock_send:
        yield mock_send


async def _seed_actor(db, *, member_of=None):
    """A non-superadmin user; membership rows in the given orgs (any role)."""
    user = await _seed_user(db)
    for org in member_of or []:
        db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=user.id,
                organization_id=org.id,
                role=OrganizationRole.CONTRIBUTOR,
                is_active=True,
            )
        )
    await db.flush()
    return user


class TestCreateCloudImports:
    @pytest.mark.asyncio
    async def test_fanout_one_job_per_key(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="in/")
        owner = await _seed_actor(async_test_db, member_of=[org])
        project = await _seed_project(async_test_db, owner)

        keys = ["in/a.json", "in/b.csv", "in/c.txt"]
        with _as_user(owner), _enqueue_ok() as mock_send:
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": keys},
            )
        assert response.status_code == 202
        jobs = response.json()["jobs"]
        assert [j["object_key"] for j in jobs] == keys
        assert all(j["status"] == "pending" for j in jobs)
        assert mock_send.call_count == 3

        rows = (
            (
                await async_test_db.execute(
                    select(ImportJob).where(ImportJob.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 3
        by_key = {r.object_key: r for r in rows}
        assert all(r.source_connection_id == conn.id for r in rows)
        assert by_key["in/a.json"].format == "json"
        assert by_key["in/b.csv"].format == "csv"
        assert by_key["in/c.txt"].format == "txt"
        assert all(r.celery_task_id == "celery-task-1" for r in rows)

    @pytest.mark.asyncio
    async def test_write_access_gate(self, async_test_client, async_test_db):
        """A member of the connection's org WITHOUT project write access is
        rejected before any job is created."""
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org)
        owner = await _seed_actor(async_test_db, member_of=[org])
        project = await _seed_project(async_test_db, owner)
        bystander = await _seed_actor(async_test_db, member_of=[org])

        with _as_user(bystander), _enqueue_ok() as mock_send:
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": ["in/a.json"]},
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_connection_org_membership_gate(
        self, async_test_client, async_test_db
    ):
        """Project write access alone must not unlock another org's bucket:
        the requester needs an ACTIVE membership in the connection's org."""
        other_org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, other_org)
        owner = await _seed_actor(async_test_db)  # project creator, no org
        project = await _seed_project(async_test_db, owner)

        with _as_user(owner), _enqueue_ok() as mock_send:
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": ["in/a.json"]},
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_inactive_membership_rejected(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org)
        owner = await _seed_actor(async_test_db)
        async_test_db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=owner.id,
                organization_id=org.id,
                role=OrganizationRole.CONTRIBUTOR,
                is_active=False,
            )
        )
        await async_test_db.flush()
        project = await _seed_project(async_test_db, owner)

        with _as_user(owner), _enqueue_ok():
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": ["in/a.json"]},
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_superadmin_bypasses_membership_gate(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org)
        superadmin = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, superadmin)

        with _as_user(superadmin), _enqueue_ok():
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": ["in/a.json"]},
            )
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_key_outside_prefix_rejected(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="in/")
        owner = await _seed_actor(async_test_db, member_of=[org])
        project = await _seed_project(async_test_db, owner)

        with _as_user(owner), _enqueue_ok() as mock_send:
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={
                    "connection_id": conn.id,
                    "object_keys": ["in/ok.json", "outside/evil.json"],
                },
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_key", ["in/a.exe", "in/a.json.zip", "in/no-extension", "in/a.parquet"]
    )
    async def test_disallowed_extension_rejected(
        self, async_test_client, async_test_db, bad_key
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="in/")
        owner = await _seed_actor(async_test_db, member_of=[org])
        project = await _seed_project(async_test_db, owner)

        with _as_user(owner), _enqueue_ok():
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": [bad_key]},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_key_cap(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="in/")
        owner = await _seed_actor(async_test_db, member_of=[org])
        project = await _seed_project(async_test_db, owner)

        keys = [f"in/file-{i}.json" for i in range(21)]
        with _as_user(owner), _enqueue_ok():
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": keys},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_empty_keys_rejected(self, async_test_client, async_test_db):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org)
        owner = await _seed_actor(async_test_db, member_of=[org])
        project = await _seed_project(async_test_db, owner)

        with _as_user(owner), _enqueue_ok():
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": []},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_unknown_connection_404(self, async_test_client, async_test_db):
        owner = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, owner)

        with _as_user(owner), _enqueue_ok():
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": _uid(), "object_keys": ["in/a.json"]},
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_queue_down_marks_jobs_failed_503(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="in/")
        owner = await _seed_actor(async_test_db, member_of=[org])
        project = await _seed_project(async_test_db, owner)

        with _as_user(owner), patch(
            "routers.projects.import_export.send_task_safe",
            side_effect=RuntimeError("broker down"),
        ):
            response = await async_test_client.post(
                f"/api/projects/{project.id}/cloud-imports",
                json={"connection_id": conn.id, "object_keys": ["in/a.json"]},
            )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

        rows = (
            (
                await async_test_db.execute(
                    select(ImportJob).where(ImportJob.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].status == "failed"


class TestCloudImportHistory:
    @pytest.mark.asyncio
    async def test_history_lists_cloud_jobs_only_with_connection_name(
        self, async_test_client, async_test_db
    ):
        org = await _seed_org(async_test_db)
        conn = await _seed_connection(async_test_db, org, prefix="in/")
        owner = await _seed_actor(async_test_db, member_of=[org])
        project = await _seed_project(async_test_db, owner)

        # One plain upload-based import job (must NOT appear) ...
        async_test_db.add(
            ImportJob(
                id=_uid(),
                project_id=project.id,
                requested_by=owner.id,
                object_key=f"imports/x/{project.id}/upload.json",
                status="completed",
                progress=100,
            )
        )
        # ... and two cloud jobs.
        older = ImportJob(
            id=_uid(),
            project_id=project.id,
            requested_by=owner.id,
            object_key="in/older.csv",
            source_connection_id=conn.id,
            format="csv",
            status="completed",
            progress=100,
            created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        newer = ImportJob(
            id=_uid(),
            project_id=project.id,
            requested_by=owner.id,
            object_key="in/newer.json",
            source_connection_id=conn.id,
            format="json",
            status="pending",
            progress=0,
            created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
        )
        async_test_db.add(older)
        async_test_db.add(newer)
        await async_test_db.flush()

        with _as_user(owner):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/cloud-imports"
            )
        assert response.status_code == 200
        rows = response.json()
        assert [r["object_key"] for r in rows] == ["in/newer.json", "in/older.csv"]
        assert all(r["connection_name"] == conn.name for r in rows)
        assert rows[0]["status"] == "pending"
        assert rows[1]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_history_requires_write_access(
        self, async_test_client, async_test_db
    ):
        owner = await _seed_user(async_test_db, is_superadmin=True)
        project = await _seed_project(async_test_db, owner)
        outsider = await _seed_actor(async_test_db)

        with _as_user(outsider):
            response = await async_test_client.get(
                f"/api/projects/{project.id}/cloud-imports"
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_history_unknown_project_404(
        self, async_test_client, async_test_db
    ):
        user = await _seed_user(async_test_db, is_superadmin=True)
        with _as_user(user):
            response = await async_test_client.get(
                f"/api/projects/{_uid()}/cloud-imports"
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND
