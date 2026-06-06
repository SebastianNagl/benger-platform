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
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import ExportJob, JobStatus
from project_models import Project, ProjectOrganization


# The admin fixture user's id (see tests/fixtures/users.py).
_ADMIN_ID = "admin-test-id"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def export_project_row(test_db, test_users, test_org):
    """A minimal project owned by the admin user and bound to ``test_org``."""
    admin = test_users[0]
    project = Project(
        id=_uid(),
        title="Export Jobs Project",
        description="async export-job fixture",
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


def _make_job(test_db, project, requested_by, **overrides):
    job = ExportJob(
        id=_uid(),
        project_id=project.id,
        requested_by=requested_by,
        format=overrides.pop("format", "json"),
        status=overrides.pop("status", JobStatus.PENDING.value),
        progress=overrides.pop("progress", 0),
        **overrides,
    )
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)
    return job


@pytest.mark.integration
class TestCreateExportJob:
    def test_post_creates_pending_job_and_enqueues(
        self, client, test_db, export_project_row, auth_headers, test_org
    ):
        project = export_project_row
        fake_result = MagicMock()
        fake_result.id = "celery-task-xyz"
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.send_task_safe", return_value=fake_result
        ) as mock_send:
            resp = client.post(
                f"/api/projects/{project.id}/exports?format=json",
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == JobStatus.PENDING.value
        job_id = body["job_id"]

        # Enqueued exactly once, targeting the worker task with the job id.
        mock_send.assert_called_once()
        assert mock_send.call_args.args[0] == "tasks.export_project"
        assert mock_send.call_args.kwargs["args"] == [job_id]

        # Row persisted with the celery task id captured for traceability.
        job = test_db.query(ExportJob).filter(ExportJob.id == job_id).first()
        assert job is not None
        assert job.status == JobStatus.PENDING.value
        assert job.format == "json"
        assert job.requested_by == _ADMIN_ID
        assert job.celery_task_id == "celery-task-xyz"

    def test_post_unknown_project_404(self, client, auth_headers, test_org):
        with patch("routers.projects.import_export.send_task_safe"):
            resp = client.post(
                f"/api/projects/{_uid()}/exports?format=json",
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 404

    def test_post_invalid_format_422(
        self, client, export_project_row, auth_headers, test_org
    ):
        resp = client.post(
            f"/api/projects/{export_project_row.id}/exports?format=bogus",
            headers={**auth_headers["admin"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 422

    def test_post_enqueue_failure_marks_job_failed_503(
        self, client, test_db, export_project_row, auth_headers, test_org
    ):
        project = export_project_row
        with patch(
            "routers.projects.import_export.object_storage.storage_backend", "minio"
        ), patch(
            "routers.projects.import_export.send_task_safe",
            side_effect=RuntimeError("broker down"),
        ):
            resp = client.post(
                f"/api/projects/{project.id}/exports?format=json",
                headers={
                    **auth_headers["admin"],
                    "X-Organization-Context": test_org.id,
                },
            )
        assert resp.status_code == 503
        # The pre-created job must not be left dangling as pending.
        job = (
            test_db.query(ExportJob)
            .filter(ExportJob.project_id == project.id)
            .first()
        )
        assert job is not None
        assert job.status == JobStatus.FAILED.value
        assert "broker down" in (job.error_message or "")


@pytest.mark.integration
class TestGetExportJobStatus:
    def test_status_returns_job_fields(
        self, client, test_db, export_project_row, auth_headers
    ):
        admin_id = _ADMIN_ID
        job = _make_job(
            test_db,
            export_project_row,
            admin_id,
            status=JobStatus.RUNNING.value,
            progress=42,
            byte_size=12345,
        )
        resp = client.get(
            f"/api/projects/{export_project_row.id}/exports/{job.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job.id
        assert body["project_id"] == export_project_row.id
        assert body["status"] == JobStatus.RUNNING.value
        assert body["progress"] == 42
        assert body["byte_size"] == 12345
        assert body["created_at"] is not None

    def test_status_unknown_job_404(
        self, client, export_project_row, auth_headers
    ):
        resp = client.get(
            f"/api/projects/{export_project_row.id}/exports/{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_status_cross_project_job_404(
        self, client, test_db, export_project_row, auth_headers, test_users, test_org
    ):
        # A job that exists but belongs to a *different* project must 404 (not
        # 403) under this project's URL — don't leak job-id existence.
        other = Project(
            id=_uid(),
            title="Other Project",
            created_by=test_users[0].id,
        )
        test_db.add(other)
        test_db.commit()
        job = _make_job(test_db, other, test_users[0].id)
        resp = client.get(
            f"/api/projects/{export_project_row.id}/exports/{job.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_status_forbidden_for_non_requester_without_write(
        self, client, test_db, export_project_row, auth_headers, test_users
    ):
        # Job requested by admin; annotator is neither requester nor a writer.
        job = _make_job(test_db, export_project_row, test_users[0].id)
        resp = client.get(
            f"/api/projects/{export_project_row.id}/exports/{job.id}",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 403

    def test_status_allowed_for_contributor_with_write(
        self, client, test_db, export_project_row, auth_headers, test_users
    ):
        # Job requested by admin; a CONTRIBUTOR org member has write access and
        # may inspect a colleague's export job.
        job = _make_job(test_db, export_project_row, test_users[0].id)
        resp = client.get(
            f"/api/projects/{export_project_row.id}/exports/{job.id}",
            headers=auth_headers["contributor"],
        )
        assert resp.status_code == 200


@pytest.mark.integration
class TestDownloadExportJob:
    def test_download_404_when_not_completed(
        self, client, test_db, export_project_row, auth_headers
    ):
        admin_id = _ADMIN_ID
        job = _make_job(
            test_db, export_project_row, admin_id, status=JobStatus.RUNNING.value
        )
        resp = client.get(
            f"/api/projects/{export_project_row.id}/exports/{job.id}/download",
            headers=auth_headers["admin"],
            follow_redirects=False,
        )
        assert resp.status_code == 404

    def test_download_410_when_expired(
        self, client, test_db, export_project_row, auth_headers
    ):
        admin_id = _ADMIN_ID
        job = _make_job(
            test_db,
            export_project_row,
            admin_id,
            status=JobStatus.COMPLETED.value,
            object_key="exports/old.json",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        resp = client.get(
            f"/api/projects/{export_project_row.id}/exports/{job.id}/download",
            headers=auth_headers["admin"],
            follow_redirects=False,
        )
        assert resp.status_code == 410

    def test_download_redirects_to_presigned_url(
        self, client, test_db, export_project_row, auth_headers
    ):
        admin_id = _ADMIN_ID
        job = _make_job(
            test_db,
            export_project_row,
            admin_id,
            status=JobStatus.COMPLETED.value,
            object_key="exports/ready.json",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        presigned = "https://storage.example/presigned-get?sig=abc"
        with patch(
            "routers.projects.import_export.object_storage.get_download_url",
            return_value=presigned,
        ) as mock_url:
            resp = client.get(
                f"/api/projects/{export_project_row.id}/exports/{job.id}/download",
                headers=auth_headers["admin"],
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

    def test_download_json_mode_returns_url_body(
        self, client, test_db, export_project_row, auth_headers
    ):
        admin_id = _ADMIN_ID
        job = _make_job(
            test_db,
            export_project_row,
            admin_id,
            status=JobStatus.COMPLETED.value,
            object_key="exports/ready.json",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        presigned = "https://storage.example/presigned-get?sig=def"
        with patch(
            "routers.projects.import_export.object_storage.get_download_url",
            return_value=presigned,
        ):
            resp = client.get(
                f"/api/projects/{export_project_row.id}/exports/{job.id}/download?json=1",
                headers=auth_headers["admin"],
                follow_redirects=False,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["url"] == presigned
        assert body["expires_in"] == 300
