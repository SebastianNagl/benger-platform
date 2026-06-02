"""Integration tests for the async import-job API (issue #158).

The inverse of the async export flow. The synchronous ``POST /{project_id}/import``
and ``POST /import-project`` stream-parse the uploaded body in the request thread
(bounded, but still tying up an API worker for the whole parse). The async import
endpoints move that off the request path:

  * ``POST /{project_id}/imports/upload-url`` -> presigned upload URL
  * ``POST /{project_id}/imports``            -> create job + enqueue worker (202)
  * ``GET  /{project_id}/imports/{job_id}``   -> poll status

These tests lock the HTTP contract: presigned-URL gating + authz, 202/job-creation
+ enqueue, object_key validation (must be under the import prefix AND scoped to
this project), and status fields + authz (requester vs. write-access vs. forbidden,
cross-project leak guard). The whole path is inert (409) on the local backend so
the client falls back to the synchronous import. The worker body is covered in
``services/workers/tests/test_import_task.py``; here ``send_task_safe`` and
``object_storage`` are mocked so we exercise only the endpoints.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from models import ImportJob, JobStatus
from project_models import Project, ProjectOrganization


# The admin fixture user's id (see tests/fixtures/users.py).
_ADMIN_ID = "admin-test-id"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def import_project_row(test_db, test_users, test_org):
    """A minimal project owned by the admin user and bound to ``test_org``."""
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title="Import Jobs Project",
        description="async import-job fixture",
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


def _valid_key(project_id: str) -> str:
    """A key shaped like one create_import_upload_url would mint for this project."""
    return f"imports/2026/06/{project_id}/20260601_120000_import.json"


def _make_job(test_db, project_id, requested_by, **overrides):
    job = ImportJob(
        id=_uid(),
        project_id=project_id,
        requested_by=requested_by,
        object_key=overrides.pop("object_key", _valid_key(project_id or _uid())),
        status=overrides.pop("status", JobStatus.PENDING.value),
        progress=overrides.pop("progress", 0),
        **overrides,
    )
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)
    return job


@pytest.mark.integration
class TestCreateImportUploadUrl:
    def test_returns_presigned_post_when_storage_configured(
        self, client, import_project_row, auth_headers, test_org
    ):
        project = import_project_row
        fake_upload = {
            "upload_url": "https://storage.example/upload",
            "method": "POST",
            "file_key": _valid_key(project.id),
            "fields": {"key": _valid_key(project.id)},
        }
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.object_storage.get_upload_url",
            return_value=fake_upload,
        ) as mock_url:
            resp = client.post(
                f"/api/projects/{project.id}/imports/upload-url?filename=import.json",
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["file_key"] == _valid_key(project.id)
        # Key must be scoped to this project so the later create-job can verify it.
        assert mock_url.call_args.kwargs["file_type"] == "imports"
        assert mock_url.call_args.kwargs["user_id"] == project.id
        assert mock_url.call_args.kwargs["max_size"] > 0

    def test_409_when_storage_is_local(
        self, client, import_project_row, auth_headers, test_org
    ):
        project = import_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "local"
        ):
            resp = client.post(
                f"/api/projects/{project.id}/imports/upload-url",
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 409

    def test_403_for_non_writer(
        self, client, import_project_row, auth_headers, test_org
    ):
        project = import_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = client.post(
                f"/api/projects/{project.id}/imports/upload-url",
                headers={
                    **auth_headers["annotator"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 403

    def test_404_unknown_project(self, client, auth_headers, test_org):
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = client.post(
                f"/api/projects/{_uid()}/imports/upload-url",
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 404


@pytest.mark.integration
class TestCreateImportJob:
    def test_post_creates_pending_job_and_enqueues(
        self, client, test_db, import_project_row, auth_headers, test_org
    ):
        project = import_project_row
        key = _valid_key(project.id)
        fake_result = MagicMock()
        fake_result.id = "celery-import-xyz"
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.send_task_safe", return_value=fake_result
        ) as mock_send:
            resp = client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": key},
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == JobStatus.PENDING.value
        job_id = body["job_id"]

        mock_send.assert_called_once()
        assert mock_send.call_args.args[0] == "tasks.import_project"
        assert mock_send.call_args.kwargs["args"] == [job_id]

        job = test_db.query(ImportJob).filter(ImportJob.id == job_id).first()
        assert job is not None
        assert job.status == JobStatus.PENDING.value
        assert job.object_key == key
        assert job.project_id == project.id
        assert job.requested_by == _ADMIN_ID
        assert job.celery_task_id == "celery-import-xyz"

    def test_409_when_storage_is_local(
        self, client, test_db, import_project_row, auth_headers, test_org
    ):
        project = import_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "local"
        ), patch("routers.projects.import_export.send_task_safe") as mock_send:
            resp = client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": _valid_key(project.id)},
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 409
        mock_send.assert_not_called()
        assert (
            test_db.query(ImportJob)
            .filter(ImportJob.project_id == project.id)
            .first()
            is None
        )

    def test_400_missing_object_key(
        self, client, import_project_row, auth_headers, test_org
    ):
        project = import_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = client.post(
                f"/api/projects/{project.id}/imports",
                json={},
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 400

    def test_400_object_key_outside_import_prefix(
        self, client, import_project_row, auth_headers, test_org
    ):
        # A key not under imports/ must be rejected — a client can't point the
        # worker at an arbitrary stored object (e.g. another project's export).
        project = import_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": f"exports/2026/06/{project.id}/leak.json"},
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 400

    def test_400_object_key_for_different_project(
        self, client, import_project_row, auth_headers, test_org
    ):
        # Correct prefix but scoped to a *different* project id — also rejected.
        project = import_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ):
            resp = client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": _valid_key(_uid())},
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 400

    def test_403_for_non_writer(
        self, client, import_project_row, auth_headers, test_org
    ):
        project = import_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch("routers.projects.import_export.send_task_safe") as mock_send:
            resp = client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": _valid_key(project.id)},
                headers={
                    **auth_headers["annotator"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 403
        mock_send.assert_not_called()

    def test_enqueue_failure_marks_job_failed_503(
        self, client, test_db, import_project_row, auth_headers, test_org
    ):
        project = import_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.send_task_safe",
            side_effect=RuntimeError("broker down"),
        ):
            resp = client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": _valid_key(project.id)},
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 503
        job = (
            test_db.query(ImportJob)
            .filter(ImportJob.project_id == project.id)
            .first()
        )
        assert job is not None
        assert job.status == JobStatus.FAILED.value
        assert "broker down" in (job.error_message or "")


@pytest.mark.integration
class TestGetImportJobStatus:
    def test_status_returns_job_fields(
        self, client, test_db, import_project_row, auth_headers
    ):
        job = _make_job(
            test_db,
            import_project_row.id,
            _ADMIN_ID,
            status=JobStatus.RUNNING.value,
            progress=42,
            byte_size=12345,
            result={"created_tasks": 7},
        )
        resp = client.get(
            f"/api/projects/{import_project_row.id}/imports/{job.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job.id
        assert body["project_id"] == import_project_row.id
        assert body["status"] == JobStatus.RUNNING.value
        assert body["progress"] == 42
        assert body["byte_size"] == 12345
        assert body["result"] == {"created_tasks": 7}
        assert body["created_at"] is not None

    def test_status_unknown_job_404(
        self, client, import_project_row, auth_headers
    ):
        resp = client.get(
            f"/api/projects/{import_project_row.id}/imports/{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_status_cross_project_job_404(
        self, client, test_db, import_project_row, auth_headers, test_users
    ):
        other = Project(
            id=_uid(),
            title="Other Import Project",
            created_by=test_users[0].id,
        )
        test_db.add(other)
        test_db.commit()
        job = _make_job(test_db, other.id, test_users[0].id)
        resp = client.get(
            f"/api/projects/{import_project_row.id}/imports/{job.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_status_forbidden_for_non_requester_without_write(
        self, client, test_db, import_project_row, auth_headers, test_users
    ):
        job = _make_job(test_db, import_project_row.id, test_users[0].id)
        resp = client.get(
            f"/api/projects/{import_project_row.id}/imports/{job.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_status_allowed_for_contributor_with_write(
        self, client, test_db, import_project_row, auth_headers, test_users
    ):
        job = _make_job(test_db, import_project_row.id, test_users[0].id)
        resp = client.get(
            f"/api/projects/{import_project_row.id}/imports/{job.id}",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200
