"""Integration coverage for the project import/export router.

Complements the existing async-job suites (``test_export_jobs_api.py`` and
``test_import_jobs_api.py``) by exercising the arms they leave uncovered in
``services/api/routers/projects/import_export.py``:

  * ``POST /{id}/exports`` subset-export validation: the ``task_ids`` body must
    be a list of strings (422 otherwise), an empty ``task_ids`` is treated as
    "whole project", and a non-empty subset is json-only (422 for csv/etc).
  * The full-project (create-new) import flow under the literal
    ``/project-imports`` prefix: presigned upload URL scoped to the user,
    object_key validation (missing 400 / wrong-prefix 400 / wrong-user 400),
    202 + enqueue, the enqueue-failure 503 path, and status read authz
    (requester-only — a different user gets 403, an unknown id 404).
  * The synchronous multi-project ``POST /bulk-export`` (json + csv, the
    include_data toggle, unsupported-format 400, access-filtered projects) and
    ``POST /bulk-export-full`` (zip archive, empty-selection 400, all-skipped
    404).

These two surfaces diverge on the DB lane:

  * The job-CRUD handlers (``/{id}/exports``, ``/project-imports*``) were
    migrated to the ASYNC lane (``Depends(get_async_db)``). Their tests seed
    real ORM rows via ``async_test_db`` and drive ``async_test_client`` with
    ``require_user`` overridden per-test (``_as_user``); ``send_task_safe`` and
    ``object_storage`` are patched so only the endpoint runs (the worker body is
    covered in the worker suite). Persisted ``ExportJob`` / ``ImportJob`` rows
    are re-queried via ``async_test_db``.
  * ``bulk_export_projects`` (POST /bulk-export) and
    ``bulk_export_full_projects`` (POST /bulk-export-full) STAYED on the SYNC
    lane (``Depends(get_db)`` + sync ``check_project_accessible`` +
    ``yield_per`` streaming). Their tests keep the sync ``client`` + ``test_db``
    fixtures and seed via sync ``test_db.add()``; they were already green and
    are left untouched.
"""

import io
import json
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from auth_module import require_user
from auth_module.models import User as AuthUser
from main import app
from models import ExportJob, ImportJob, JobStatus, User
from project_models import Project, ProjectOrganization, Task


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Async helpers (job-CRUD surface) — seed real rows + override require_user
# ---------------------------------------------------------------------------


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


async def _make_user(db, *, is_superadmin=False, name="IE User"):
    u = User(
        id=_uid(),
        username=f"ie-{_uid()[:8]}",
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


async def _make_project(
    db,
    *,
    created_by,
    title="IE Coverage Project",
    is_private=False,
    is_public=False,
    label_config='<View><Text name="text" value="$text"/></View>',
):
    p = Project(
        id=_uid(),
        title=title,
        description="import/export coverage fixture",
        created_by=created_by,
        is_private=is_private,
        is_public=is_public,
        label_config=label_config,
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    return p


async def _make_import_job(db, *, requested_by, project_id=None, **overrides):
    job = ImportJob(
        id=_uid(),
        project_id=project_id,
        requested_by=requested_by,
        object_key=overrides.pop(
            "object_key", f"imports/2026/06/{requested_by}/full.json"
        ),
        status=overrides.pop("status", JobStatus.RUNNING.value),
        progress=overrides.pop("progress", 30),
        **overrides,
    )
    db.add(job)
    await db.flush()
    return job


# ---------------------------------------------------------------------------
# Subset export validation (POST /{id}/exports with a task_ids body) — ASYNC
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSubsetExportValidation:
    @pytest.mark.asyncio
    async def test_task_ids_not_a_list_is_422(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.import_export.send_task_safe"
        ) as mock_send:
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/exports?format=json",
                json={"task_ids": "not-a-list"},
            )
        assert resp.status_code == 422, resp.text
        assert "task_ids" in resp.json()["detail"]
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_ids_non_string_elements_is_422(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.import_export.send_task_safe"
        ) as mock_send:
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/exports?format=json",
                json={"task_ids": ["ok", 123]},
            )
        assert resp.status_code == 422, resp.text
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_subset_with_non_json_format_is_422(
        self, async_test_client, async_test_db
    ):
        """A non-empty task_ids subset is only supported for json — csv is
        rejected before any job is created."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        with _as_user(admin), patch(
            "routers.projects.import_export.send_task_safe"
        ) as mock_send:
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/exports?format=csv",
                json={"task_ids": [_uid()]},
            )
        assert resp.status_code == 422, resp.text
        assert "json" in resp.json()["detail"].lower()
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_task_ids_means_whole_project(
        self, async_test_client, async_test_db
    ):
        """An empty task_ids list is normalised to None (whole project), so the
        persisted job stores task_ids=None and still enqueues."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        fake_result = MagicMock()
        fake_result.id = "celery-subset"
        with _as_user(admin), patch(
            "routers.projects.import_export.send_task_safe", return_value=fake_result
        ):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/exports?format=json",
                json={"task_ids": []},
            )
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["job_id"]
        job = (
            await async_test_db.execute(
                select(ExportJob).where(ExportJob.id == job_id)
            )
        ).scalar_one_or_none()
        assert job is not None
        assert job.task_ids is None

    @pytest.mark.asyncio
    async def test_valid_subset_persists_task_ids(
        self, async_test_client, async_test_db
    ):
        """A non-empty json subset persists the exact task_ids on the job row."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(async_test_db, created_by=admin.id)
        await async_test_db.commit()

        subset = [_uid(), _uid()]
        fake_result = MagicMock()
        fake_result.id = "celery-subset2"
        with _as_user(admin), patch(
            "routers.projects.import_export.send_task_safe", return_value=fake_result
        ):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/exports?format=json",
                json={"task_ids": subset},
            )
        assert resp.status_code == 202, resp.text
        job = (
            await async_test_db.execute(
                select(ExportJob).where(ExportJob.id == resp.json()["job_id"])
            )
        ).scalar_one_or_none()
        assert job.task_ids == subset

    @pytest.mark.asyncio
    async def test_export_access_denied_for_non_member(
        self, async_test_client, async_test_db
    ):
        """A private project the caller doesn't own → 403 (access check)."""
        owner = await _make_user(async_test_db, is_superadmin=False)
        other = await _make_user(async_test_db, is_superadmin=False)
        private = await _make_project(
            async_test_db, created_by=owner.id, title="Private", is_private=True
        )
        await async_test_db.commit()

        with _as_user(other), patch(
            "routers.projects.import_export.send_task_safe"
        ):
            resp = await async_test_client.post(
                f"/api/projects/{private.id}/exports?format=json",
                headers={"X-Organization-Context": "private"},
            )
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Full-project (create-new) import flow — /project-imports* — ASYNC
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFullProjectImportUploadUrl:
    @pytest.mark.asyncio
    async def test_returns_presigned_url_scoped_to_user(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        fake_upload = {
            "upload_url": "https://storage.example/upload",
            "file_key": f"imports/2026/06/{admin.id}/x.json",
        }
        with _as_user(admin), patch(
            "routers.projects.import_export.object_storage.get_upload_url",
            return_value=fake_upload,
        ) as mock_url:
            resp = await async_test_client.post(
                "/api/projects/project-imports/upload-url?filename=full.json",
            )
        assert resp.status_code == 200, resp.text
        # Key is scoped to the requesting USER (not a project).
        assert mock_url.call_args.kwargs["file_type"] == "imports"
        assert mock_url.call_args.kwargs["user_id"] == admin.id
        assert mock_url.call_args.kwargs["max_size"] > 0


@pytest.mark.integration
class TestCreateFullProjectImportJob:
    def _valid_user_key(self, user_id):
        return f"imports/2026/06/{user_id}/20260601_120000_full.json"

    @pytest.mark.asyncio
    async def test_creates_pending_job_with_null_project_and_enqueues(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        key = self._valid_user_key(admin.id)
        fake_result = MagicMock()
        fake_result.id = "celery-full-import"
        with _as_user(admin), patch(
            "routers.projects.import_export.send_task_safe", return_value=fake_result
        ) as mock_send:
            resp = await async_test_client.post(
                "/api/projects/project-imports",
                json={"object_key": key},
            )
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["job_id"]
        mock_send.assert_called_once()
        assert mock_send.call_args.args[0] == "tasks.import_project"

        job = (
            await async_test_db.execute(
                select(ImportJob).where(ImportJob.id == job_id)
            )
        ).scalar_one_or_none()
        assert job is not None
        assert job.project_id is None  # back-filled by the worker later
        assert job.object_key == key
        assert job.requested_by == admin.id
        assert job.celery_task_id == "celery-full-import"

    @pytest.mark.asyncio
    async def test_missing_object_key_400(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/projects/project-imports",
                json={},
            )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_object_key_outside_import_prefix_400(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/projects/project-imports",
                json={"object_key": f"exports/2026/06/{admin.id}/leak.json"},
            )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_object_key_for_different_user_400(
        self, async_test_client, async_test_db
    ):
        """Correct prefix but scoped to someone else's user id → rejected."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.post(
                "/api/projects/project-imports",
                json={"object_key": self._valid_user_key(_uid())},
            )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_enqueue_failure_marks_failed_503(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        key = self._valid_user_key(admin.id)
        with _as_user(admin), patch(
            "routers.projects.import_export.send_task_safe",
            side_effect=RuntimeError("broker down"),
        ):
            resp = await async_test_client.post(
                "/api/projects/project-imports",
                json={"object_key": key},
            )
        assert resp.status_code == 503, resp.text
        job = (
            await async_test_db.execute(
                select(ImportJob).where(ImportJob.object_key == key)
            )
        ).scalar_one_or_none()
        assert job is not None
        assert job.status == JobStatus.FAILED.value
        assert "broker down" in (job.error_message or "")


@pytest.mark.integration
class TestGetFullProjectImportJob:
    @pytest.mark.asyncio
    async def test_status_returns_fields_for_requester(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        job = await _make_import_job(
            async_test_db,
            requested_by=admin.id,
            progress=55,
            byte_size=999,
            result={"x": 1},
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/project-imports/{job.id}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["job_id"] == job.id
        assert body["project_id"] is None
        assert body["progress"] == 55
        assert body["byte_size"] == 999
        assert body["result"] == {"x": 1}

    @pytest.mark.asyncio
    async def test_status_unknown_job_404(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.get(
                f"/api/projects/project-imports/{_uid()}",
            )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_status_other_user_forbidden(
        self, async_test_client, async_test_db
    ):
        """A full-project import job has no project to scope on, so only its
        requester may read it — a different user gets 403 for the owner's job."""
        owner = await _make_user(async_test_db, is_superadmin=True)
        other = await _make_user(async_test_db, is_superadmin=False)
        job = await _make_import_job(async_test_db, requested_by=owner.id)
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.get(
                f"/api/projects/project-imports/{job.id}",
            )
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Synchronous multi-project bulk-export  (POST /bulk-export) — SYNC, unchanged
#
# These handlers stayed on the SYNC DB lane (``Depends(get_db)`` + sync
# ``check_project_accessible`` + ``yield_per`` streaming), so the tests keep the
# sync ``client`` + ``test_db`` fixtures and seed via sync ``test_db.add()``.
# ---------------------------------------------------------------------------


def _sync_add_task(test_db, project, *, inner_id=1, text="hello"):
    task = Task(
        id=_uid(),
        project_id=project.id,
        inner_id=inner_id,
        data={"text": text},
        is_labeled=False,
    )
    test_db.add(task)
    test_db.commit()
    return task


@pytest.fixture
def project_row(test_db, test_users, test_org):
    """Project owned by admin, bound to test_org (sync fixture for bulk-export)."""
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title="IE Coverage Project",
        description="import/export coverage fixture",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(
        ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=test_org.id,
            assigned_by=admin.id,
        )
    )
    test_db.commit()
    return project


@pytest.mark.integration
class TestBulkExport:
    def test_json_export_includes_tasks(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        admin = test_users[0]
        p1 = Project(
            id=_uid(), title="P1", created_by=admin.id,
            label_config="<View></View>",
        )
        p2 = Project(
            id=_uid(), title="P2", created_by=admin.id,
            label_config="<View></View>",
        )
        test_db.add_all([p1, p2])
        test_db.flush()
        for p in (p1, p2):
            test_db.add(
                ProjectOrganization(
                    id=_uid(), project_id=p.id,
                    organization_id=test_org.id, assigned_by=admin.id,
                )
            )
        test_db.commit()
        _sync_add_task(test_db, p1, inner_id=1, text="t1")
        _sync_add_task(test_db, p2, inner_id=1, text="t2")

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p1.id, p2.id], "format": "json"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/json")
        payload = json.loads(resp.content)
        assert "projects" in payload
        assert len(payload["projects"]) == 2
        # Each project carries its streamed tasks array.
        for proj in payload["projects"]:
            assert "tasks" in proj
            assert len(proj["tasks"]) == 1
            assert proj["tasks"][0]["annotations"] == []
        assert payload["format"] == "json"

    def test_json_export_without_data_omits_tasks(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """include_data=False writes only the per-project metadata head, no
        tasks key."""
        admin = test_users[0]
        p = Project(
            id=_uid(), title="MetaOnly", created_by=admin.id,
            label_config="<View></View>",
        )
        test_db.add(p)
        test_db.flush()
        test_db.add(
            ProjectOrganization(
                id=_uid(), project_id=p.id,
                organization_id=test_org.id, assigned_by=admin.id,
            )
        )
        test_db.commit()
        _sync_add_task(test_db, p, inner_id=1)

        resp = client.post(
            "/api/projects/bulk-export",
            json={
                "project_ids": [p.id],
                "format": "json",
                "include_data": False,
            },
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        payload = json.loads(resp.content)
        assert len(payload["projects"]) == 1
        assert "tasks" not in payload["projects"][0]
        # Metadata still carries the task_count.
        assert payload["projects"][0]["task_count"] == 1

    def test_csv_export_emits_metadata_rows(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        admin = test_users[0]
        p = Project(
            id=_uid(), title="CsvProj", created_by=admin.id,
            description="desc", label_config="<View></View>",
        )
        test_db.add(p)
        test_db.flush()
        test_db.add(
            ProjectOrganization(
                id=_uid(), project_id=p.id,
                organization_id=test_org.id, assigned_by=admin.id,
            )
        )
        test_db.commit()
        _sync_add_task(test_db, p, inner_id=1)

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [p.id], "format": "csv"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        import csv as _csv

        rows = list(_csv.reader(io.StringIO(resp.text)))
        assert rows[0] == [
            "project_id",
            "project_title",
            "description",
            "task_count",
            "annotation_count",
            "created_at",
        ]
        data_row = rows[1]
        assert data_row[0] == p.id
        assert data_row[1] == "CsvProj"
        assert data_row[3] == "1"  # task_count

    def test_unsupported_format_400(
        self, client, project_row, auth_headers, test_org
    ):
        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [project_row.id], "format": "xml"},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 400, resp.text
        assert "format" in resp.json()["detail"].lower()

    def test_inaccessible_and_missing_projects_skipped(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A missing id and another user's private project are filtered out; the
        export emits an empty projects array (still 200)."""
        annotator = test_users[2]
        private = Project(
            id=_uid(), title="Other private", created_by=annotator.id,
            is_private=True, label_config="<View></View>",
        )
        test_db.add(private)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export",
            json={"project_ids": [_uid(), private.id], "format": "json"},
            # contributor: not a superadmin, not the creator, private context
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 200, resp.text
        payload = json.loads(resp.content)
        assert payload["projects"] == []


# ---------------------------------------------------------------------------
# Synchronous bulk-export-full  (POST /bulk-export-full → zip) — SYNC, unchanged
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestBulkExportFull:
    def test_empty_selection_400(self, client, auth_headers, test_org):
        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": []},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 400, resp.text
        assert "no project" in resp.json()["detail"].lower()

    def test_zip_contains_one_entry_per_exported_project(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        admin = test_users[0]
        p = Project(
            id=_uid(), title="ZipMe", created_by=admin.id,
            label_config="<View></View>",
        )
        test_db.add(p)
        test_db.flush()
        test_db.add(
            ProjectOrganization(
                id=_uid(), project_id=p.id,
                organization_id=test_org.id, assigned_by=admin.id,
            )
        )
        test_db.commit()
        _sync_add_task(test_db, p, inner_id=1)

        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": [p.id]},
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/zip")

        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert len(names) == 1
        # Entry name embeds the (sanitised) title + project id prefix.
        assert names[0].startswith("ZipMe_")
        assert names[0].endswith(".json")
        # The streamed JSON entry is valid and identifies the project.
        entry = json.loads(zf.read(names[0]))
        assert isinstance(entry, dict)

    def test_all_projects_inaccessible_404(
        self, client, test_db, test_users, auth_headers
    ):
        """When nothing in the selection can be exported (all missing /
        access-denied), the endpoint 404s rather than returning an empty zip."""
        annotator = test_users[2]
        private = Project(
            id=_uid(), title="No access", created_by=annotator.id,
            is_private=True, label_config="<View></View>",
        )
        test_db.add(private)
        test_db.commit()

        resp = client.post(
            "/api/projects/bulk-export-full",
            json={"project_ids": [_uid(), private.id]},
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 404, resp.text
        assert "no projects" in resp.json()["detail"].lower()
