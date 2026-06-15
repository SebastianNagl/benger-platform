"""Behavioral integration tests for ``routers/storage.py``.

Run through the real ``client`` + ``test_db`` (Postgres) and the real
``UploadedData`` ORM model. Object-storage *primitive* calls
(``object_storage.upload_file`` / ``get_download_url`` / ``delete_file`` /
``create_multipart_upload`` / ``complete_multipart_upload``) are patched so the
tests don't depend on a live MinIO bucket's object state — but the router's own
logic (permission checks, DB row creation/deletion, response shaping) runs for
real and every mutating test asserts the persisted ``uploaded_data`` row.

The mock-heavy sibling ``tests/unit/test_storage_router.py`` stubs the DB with
``Mock(spec=Session)``, so the actual ORM INSERT/DELETE + the
permission-branch reads against real rows are never exercised. This file is the
behavioral complement:

  - ``/storage/upload`` persists an UploadedData row (asserted via test_db) and
    parses the metadata blob (valid + malformed-JSON-swallowed branches).
  - ``/storage/download-url`` 404 (missing row), owner-grant, superadmin-grant,
    non-owner-no-task 403 — each asserted against a real row.
  - ``/storage/file/{id}`` DELETE removes the real row on success; 404 missing;
    403 non-owner leaves the row intact; storage-delete-returns-False → 500 and
    the row is NOT removed.
  - ``/storage/multipart/complete`` persists a row with the metadata-derived
    original_filename.
  - ``/storage/cdn/assets/{path}`` shaping + ``/storage/health`` superadmin gate.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from models import UploadedData


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_uploaded(
    test_db: Session,
    *,
    uploaded_by: str,
    file_id: str = None,
    task_id: str = None,
) -> UploadedData:
    row = UploadedData(
        id=file_id or _uid(),
        name="doc.txt",
        original_filename="doc.txt",
        file_path="uploads/2026/06/14/doc.txt",
        size=11,
        format="txt",
        uploaded_by=uploaded_by,
        task_id=task_id,
        storage_url="file:///tmp/benger-storage/uploads/doc.txt",
        storage_backend="local",
    )
    test_db.add(row)
    test_db.commit()
    return row


def _exists(test_db: Session, file_id: str) -> bool:
    test_db.expire_all()
    return (
        test_db.query(UploadedData).filter(UploadedData.id == file_id).first()
        is not None
    )


# ---------------------------------------------------------------------------
# POST /storage/upload — real INSERT
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUploadFileToStorage:
    def test_upload_persists_row_and_parses_metadata(
        self, client, test_db, test_users, auth_headers
    ):
        admin = test_users[0]
        upload_result = {
            "file_key": "uploads/2026/06/14/note.txt",
            "url": "file:///tmp/benger-storage/uploads/note.txt",
            "size": 12,
            "content_type": "text/plain",
            "hash": "deadbeef",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": "local",
        }
        with patch(
            "routers.storage.object_storage.upload_file", return_value=upload_result
        ) as mock_up:
            resp = client.post(
                "/storage/upload",
                headers=auth_headers["admin"],
                files={"file": ("note.txt", b"hello world!", "text/plain")},
                data={"file_type": "uploads", "metadata": '{"kind": "doc"}'},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["file_key"] == "uploads/2026/06/14/note.txt"
        assert body["size"] == 12
        mock_up.assert_called_once()

        # A real uploaded_data row was persisted, owned by admin, with the
        # parsed metadata blob.
        test_db.expire_all()
        row = test_db.query(UploadedData).filter(UploadedData.id == body["id"]).first()
        assert row is not None
        assert row.uploaded_by == admin.id
        assert row.file_path == "uploads/2026/06/14/note.txt"
        assert row.file_metadata == {"kind": "doc"}
        assert row.format == "txt"

    def test_upload_malformed_metadata_is_swallowed(
        self, client, test_db, test_users, auth_headers
    ):
        """Invalid JSON in the metadata form field is ignored (empty dict),
        not fatal — the row still persists."""
        upload_result = {
            "file_key": "uploads/x/bad.bin",
            "url": "file:///tmp/x/bad.bin",
            "size": 3,
            "content_type": "application/octet-stream",
            "hash": "abc",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": "local",
        }
        with patch(
            "routers.storage.object_storage.upload_file", return_value=upload_result
        ):
            resp = client.post(
                "/storage/upload",
                headers=auth_headers["admin"],
                files={"file": ("bad.bin", b"xyz", "application/octet-stream")},
                data={"metadata": "{not valid json"},
            )
        assert resp.status_code == 200, resp.text
        row_id = resp.json()["id"]
        test_db.expire_all()
        row = test_db.query(UploadedData).filter(UploadedData.id == row_id).first()
        assert row is not None
        assert row.file_metadata == {}

    def test_upload_storage_failure_returns_500_no_row(
        self, client, test_db, test_users, auth_headers
    ):
        before = test_db.query(UploadedData).count()
        with patch(
            "routers.storage.object_storage.upload_file",
            side_effect=Exception("backend down"),
        ):
            resp = client.post(
                "/storage/upload",
                headers=auth_headers["admin"],
                files={"file": ("note.txt", b"hello", "text/plain")},
            )
        assert resp.status_code == 500, resp.text
        assert "Failed to upload file" in resp.json()["detail"]
        test_db.expire_all()
        assert test_db.query(UploadedData).count() == before


# ---------------------------------------------------------------------------
# GET /storage/download-url/{file_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDownloadUrl:
    def test_missing_file_404(self, client, auth_headers):
        resp = client.get(
            f"/storage/download-url/{_uid()}", headers=auth_headers["admin"]
        )
        assert resp.status_code == 404, resp.text
        assert "File not found" in resp.json()["detail"]

    def test_owner_gets_presigned_url(
        self, client, test_db, test_users, auth_headers
    ):
        contributor = test_users[1]
        row = _seed_uploaded(test_db, uploaded_by=contributor.id)
        with patch(
            "routers.storage.object_storage.get_download_url",
            return_value="https://signed.example/download",
        ) as mock_dl:
            resp = client.get(
                f"/storage/download-url/{row.id}",
                headers=auth_headers["contributor"],
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["url"] == "https://signed.example/download"
        assert body["filename"] == "doc.txt"
        assert body["size"] == 11
        mock_dl.assert_called_once()

    def test_superadmin_grant_for_other_users_file(
        self, client, test_db, test_users, auth_headers
    ):
        contributor = test_users[1]
        row = _seed_uploaded(test_db, uploaded_by=contributor.id)
        with patch(
            "routers.storage.object_storage.get_download_url",
            return_value="https://signed.example/admin-dl",
        ):
            resp = client.get(
                f"/storage/download-url/{row.id}", headers=auth_headers["admin"]
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["url"] == "https://signed.example/admin-dl"

    def test_non_owner_no_task_403(
        self, client, test_db, test_users, auth_headers
    ):
        """A file with no task_id, requested by a non-owner non-superadmin →
        the final else 403 (Access denied)."""
        contributor = test_users[1]
        row = _seed_uploaded(test_db, uploaded_by=contributor.id, task_id=None)
        resp = client.get(
            f"/storage/download-url/{row.id}", headers=auth_headers["annotator"]
        )
        assert resp.status_code == 403, resp.text
        assert "Access denied" in resp.json()["detail"]

    def test_non_owner_with_missing_associated_task_404(
        self, client, test_db, test_users, auth_headers
    ):
        """task_id set but the referenced project row doesn't exist → the
        'Associated task not found' 404 branch (returns before the
        organization_ids access)."""
        contributor = test_users[1]
        row = _seed_uploaded(
            test_db, uploaded_by=contributor.id, task_id="no-such-project"
        )
        resp = client.get(
            f"/storage/download-url/{row.id}", headers=auth_headers["annotator"]
        )
        assert resp.status_code == 404, resp.text
        assert "Associated task not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /storage/file/{file_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteFile:
    def test_missing_file_404(self, client, auth_headers):
        resp = client.delete(
            f"/storage/file/{_uid()}", headers=auth_headers["admin"]
        )
        assert resp.status_code == 404, resp.text
        assert "File not found" in resp.json()["detail"]

    def test_owner_delete_removes_row(
        self, client, test_db, test_users, auth_headers
    ):
        contributor = test_users[1]
        row = _seed_uploaded(test_db, uploaded_by=contributor.id)
        with patch(
            "routers.storage.object_storage.delete_file", return_value=True
        ) as mock_del:
            resp = client.delete(
                f"/storage/file/{row.id}", headers=auth_headers["contributor"]
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "File deleted successfully"
        mock_del.assert_called_once_with(row.file_path)
        assert not _exists(test_db, row.id)

    def test_non_owner_delete_403_row_intact(
        self, client, test_db, test_users, auth_headers
    ):
        contributor = test_users[1]
        row = _seed_uploaded(test_db, uploaded_by=contributor.id)
        resp = client.delete(
            f"/storage/file/{row.id}", headers=auth_headers["annotator"]
        )
        assert resp.status_code == 403, resp.text
        assert "Access denied" in resp.json()["detail"]
        assert _exists(test_db, row.id)

    def test_storage_delete_false_returns_500_row_intact(
        self, client, test_db, test_users, auth_headers
    ):
        """When the storage backend reports failure, the endpoint 500s and the
        DB row is NOT removed (delete is gated on storage success)."""
        contributor = test_users[1]
        row = _seed_uploaded(test_db, uploaded_by=contributor.id)
        with patch(
            "routers.storage.object_storage.delete_file", return_value=False
        ):
            resp = client.delete(
                f"/storage/file/{row.id}", headers=auth_headers["contributor"]
            )
        assert resp.status_code == 500, resp.text
        assert _exists(test_db, row.id)


# ---------------------------------------------------------------------------
# POST /storage/multipart/complete — real INSERT
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCompleteMultipart:
    def test_complete_persists_row_with_metadata_filename(
        self, client, test_db, test_users, auth_headers
    ):
        with patch(
            "routers.storage.object_storage.complete_multipart_upload",
            return_value={"size": 9000, "etag": "etag-xyz", "storage_backend": "local"},
        ) as mock_complete:
            resp = client.post(
                "/storage/multipart/complete",
                headers=auth_headers["admin"],
                json={
                    "file_key": "uploads/2026/06/big.zip",
                    "upload_id": "mp-1",
                    "parts": [{"PartNumber": 1, "ETag": "e1"}],
                    "metadata": {"original_filename": "report-final.zip"},
                },
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["size"] == 9000
        assert body["etag"] == "etag-xyz"
        mock_complete.assert_called_once()

        test_db.expire_all()
        row = test_db.query(UploadedData).filter(UploadedData.id == body["id"]).first()
        assert row is not None
        # original_filename pulled from metadata; name derived from the key tail.
        assert row.original_filename == "report-final.zip"
        assert row.name == "big.zip"
        assert row.size == 9000
        assert row.uploaded_by == test_users[0].id


# ---------------------------------------------------------------------------
# CDN asset URL + health (no DB; behavioral on cdn_service / object_storage)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCdnAndHealth:
    def test_cdn_asset_url_shape(self, client):
        from unittest.mock import Mock

        mock_cdn = Mock()
        mock_cdn.get_asset_url.return_value = "https://cdn.example/static/logo.png"
        mock_cdn.cdn_enabled = True
        with patch("routers.storage.cdn_service", mock_cdn):
            resp = client.get("/storage/cdn/assets/static/logo.png")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["asset_path"] == "static/logo.png"
        assert body["cdn_url"] == "https://cdn.example/static/logo.png"
        assert body["cdn_enabled"] is True
        mock_cdn.get_asset_url.assert_called_once_with("/static/logo.png")

    def test_health_requires_superadmin(self, client, auth_headers):
        """A non-superadmin is rejected by the require_superadmin gate."""
        resp = client.get("/storage/health", headers=auth_headers["contributor"])
        assert resp.status_code in (401, 403), resp.text

    def test_health_superadmin_reports_backends(self, client, auth_headers):
        from unittest.mock import Mock

        mock_cdn = Mock()
        mock_cdn.health_check.return_value = {"status": "ok"}
        with patch(
            "routers.storage.object_storage.health_check",
            return_value={"healthy": True, "storage_backend": "local"},
        ):
            with patch("routers.storage.cdn_service", mock_cdn):
                resp = client.get("/storage/health", headers=auth_headers["admin"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "storage" in body and "cdn" in body and "timestamp" in body
        assert body["storage"]["healthy"] is True
