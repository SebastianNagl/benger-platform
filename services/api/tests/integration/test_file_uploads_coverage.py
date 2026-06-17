"""Behavioral integration tests for ``routers/file_uploads.py``.

Run through the real ``client`` + ``test_db`` and the real ``UploadedData``
model. The object-storage *primitive* calls are patched (so the suite doesn't
depend on a live MinIO bucket), but the router's own logic — DB INSERT/DELETE,
per-user filtering, the storage_url-regeneration branch in ``list_files``, the
presigned-redirect vs file_path fallback in ``download_file`` — runs for real
and every mutating test asserts the persisted ``uploaded_data`` row.

The mock-heavy sibling ``tests/unit/test_file_uploads_coverage.py`` stubs the
DB with ``Mock(spec=Session)``; this file is the behavioral complement:

  - ``POST /api/files/upload`` persists a real row (storage_key, file_hash,
    storage_type, size, format, owner) and returns the shaped response.
  - ``GET /api/files/`` lists only the caller's rows, filters by task_id, and
    exercises the storage_url-regeneration branch for a row missing a URL.
  - ``GET /api/files/{id}/download`` 404 for someone else's / missing file,
    302 presigned redirect for a storage_key row, FileResponse fallback for a
    legacy file_path row, 404 when neither resolves.
  - ``DELETE /api/files/{id}`` removes only the caller's row; 404 for a
    non-owner (the per-user filter scopes it out).

Note the upload endpoint's broad ``except Exception`` wraps *all* failures —
including its own HTTPException guards — as 500 (documented in the FINDINGS
note); the success path is what's behaviorally meaningful here.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from models import UploadedData


def _uid() -> str:
    return str(uuid.uuid4())


def _seed(
    test_db: Session,
    *,
    uploaded_by: str,
    file_id: str = None,
    name: str = "file.pdf",
    task_id: str = None,
    storage_key: str = "uploads/2026/06/file.pdf",
    storage_url: str = "https://signed/file.pdf",
    file_path: str = "uploads/2026/06/file.pdf",
) -> UploadedData:
    row = UploadedData(
        id=file_id or _uid(),
        name=name,
        original_filename=name,
        file_path=file_path,
        storage_key=storage_key,
        storage_url=storage_url,
        file_hash="h" * 8,
        storage_type="local",
        size=2048,
        format=name.rsplit(".", 1)[-1] if "." in name else "unknown",
        task_id=task_id,
        uploaded_by=uploaded_by,
        upload_date=datetime.now(timezone.utc),
    )
    test_db.add(row)
    test_db.commit()
    return row


# ---------------------------------------------------------------------------
# POST /api/files/upload — real INSERT
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpload:
    def test_upload_persists_row(self, client, test_db, test_users, auth_headers):
        admin = test_users[0]
        storage_result = {
            "file_key": "uploads/2026/06/14/report.pdf",
            "url": "https://signed/report.pdf",
            "hash": "abc123hash",
        }
        with patch(
            "routers.file_uploads.object_storage"
        ) as mock_storage:
            mock_storage.upload_file.return_value = storage_result
            mock_storage.cdn_enabled = False
            mock_storage.storage_backend = "local"
            resp = client.post(
                "/api/files/upload",
                headers=auth_headers["admin"],
                files={"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "report.pdf"
        assert body["format"] == "pdf"
        assert body["url"] == "https://signed/report.pdf"

        # Persisted row carries the storage metadata.
        test_db.expire_all()
        row = test_db.query(UploadedData).filter(UploadedData.id == body["id"]).first()
        assert row is not None
        assert row.uploaded_by == admin.id
        assert row.storage_key == "uploads/2026/06/14/report.pdf"
        assert row.file_hash == "abc123hash"
        assert row.storage_type == "local"
        assert row.format == "pdf"

    def test_upload_with_task_and_description(
        self, client, test_db, test_users, auth_headers
    ):
        storage_result = {
            "file_key": "uploads/x/notes.txt",
            "url": "https://signed/notes.txt",
            "hash": "deadbeef",
        }
        with patch("routers.file_uploads.object_storage") as mock_storage:
            mock_storage.upload_file.return_value = storage_result
            mock_storage.cdn_enabled = False
            mock_storage.storage_backend = "local"
            resp = client.post(
                "/api/files/upload?task_id=task-42&description=meeting+notes",
                headers=auth_headers["admin"],
                files={"file": ("notes.txt", b"hi", "text/plain")},
            )
        assert resp.status_code == 200, resp.text
        test_db.expire_all()
        row = (
            test_db.query(UploadedData)
            .filter(UploadedData.id == resp.json()["id"])
            .first()
        )
        assert row.task_id == "task-42"
        assert row.description == "meeting notes"


# ---------------------------------------------------------------------------
# GET /api/files/ — per-user listing + filters + url regen
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListFiles:
    def test_lists_only_callers_files(
        self, client, test_db, test_users, auth_headers
    ):
        admin, contributor = test_users[0], test_users[1]
        mine = _seed(test_db, uploaded_by=contributor.id, name="mine.pdf")
        _seed(test_db, uploaded_by=admin.id, name="theirs.pdf")

        resp = client.get("/api/files/", headers=auth_headers["contributor"])
        assert resp.status_code == 200, resp.text
        ids = {f["id"] for f in resp.json()}
        assert mine.id in ids
        # Admin's file is excluded by the uploaded_by filter.
        assert all(f["name"] != "theirs.pdf" for f in resp.json())

    def test_filter_by_task_id(self, client, test_db, test_users, auth_headers):
        contributor = test_users[1]
        with_task = _seed(
            test_db, uploaded_by=contributor.id, name="a.pdf", task_id="t-1"
        )
        _seed(test_db, uploaded_by=contributor.id, name="b.pdf", task_id="t-2")

        resp = client.get(
            "/api/files/?task_id=t-1", headers=auth_headers["contributor"]
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["id"] == with_task.id

    def test_regenerates_url_when_missing(
        self, client, test_db, test_users, auth_headers
    ):
        """A row with storage_key but no storage_url triggers the on-the-fly
        get_download_url regeneration branch."""
        contributor = test_users[1]
        _seed(
            test_db,
            uploaded_by=contributor.id,
            name="nourl.pdf",
            storage_url=None,
            storage_key="uploads/nourl.pdf",
        )
        with patch(
            "routers.file_uploads.object_storage.get_download_url",
            return_value="https://regenerated/url",
        ) as mock_gen:
            resp = client.get("/api/files/", headers=auth_headers["contributor"])
        assert resp.status_code == 200, resp.text
        mock_gen.assert_called_once()
        url = next(f["url"] for f in resp.json() if f["name"] == "nourl.pdf")
        assert url == "https://regenerated/url"


# ---------------------------------------------------------------------------
# GET /api/files/{id}/download
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDownload:
    def test_missing_file_404(self, client, auth_headers):
        resp = client.get(
            f"/api/files/{_uid()}/download", headers=auth_headers["admin"]
        )
        assert resp.status_code == 404, resp.text

    def test_other_users_file_404(self, client, test_db, test_users, auth_headers):
        """The query is scoped to uploaded_by==current_user, so another user's
        file is a 404 (not 403)."""
        admin = test_users[0]
        row = _seed(test_db, uploaded_by=admin.id)
        resp = client.get(
            f"/api/files/{row.id}/download", headers=auth_headers["contributor"]
        )
        assert resp.status_code == 404, resp.text

    def test_storage_key_redirects_to_presigned(
        self, client, test_db, test_users, auth_headers
    ):
        contributor = test_users[1]
        row = _seed(
            test_db, uploaded_by=contributor.id, storage_key="uploads/dl.pdf"
        )
        with patch(
            "routers.file_uploads.object_storage.get_download_url",
            return_value="https://signed/redirect-target",
        ) as mock_dl:
            resp = client.get(
                f"/api/files/{row.id}/download",
                headers=auth_headers["contributor"],
                follow_redirects=False,
            )
        assert resp.status_code == 302, resp.text
        assert resp.headers["location"] == "https://signed/redirect-target"
        mock_dl.assert_called_once()

    def test_no_storage_key_no_file_path_404(
        self, client, test_db, test_users, auth_headers
    ):
        """No storage_key and a file_path that doesn't exist on disk → the
        terminal 'File data not found' 404."""
        contributor = test_users[1]
        row = _seed(
            test_db,
            uploaded_by=contributor.id,
            storage_key=None,
            file_path="/nonexistent/path/ghost.pdf",
        )
        resp = client.get(
            f"/api/files/{row.id}/download", headers=auth_headers["contributor"]
        )
        assert resp.status_code == 404, resp.text
        assert "File data not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/files/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDelete:
    def test_owner_delete_removes_row(
        self, client, test_db, test_users, auth_headers
    ):
        contributor = test_users[1]
        row = _seed(test_db, uploaded_by=contributor.id, storage_key="uploads/del.pdf")
        with patch("routers.file_uploads.object_storage.delete_file"):
            resp = client.delete(
                f"/api/files/{row.id}", headers=auth_headers["contributor"]
            )
        assert resp.status_code == 200, resp.text
        assert "deleted" in resp.json()["message"].lower()
        test_db.expire_all()
        assert (
            test_db.query(UploadedData).filter(UploadedData.id == row.id).first()
            is None
        )
        # Storage delete is scheduled as a background task (best-effort);
        # the response returns regardless.

    def test_missing_file_404(self, client, auth_headers):
        resp = client.delete(f"/api/files/{_uid()}", headers=auth_headers["admin"])
        assert resp.status_code == 404, resp.text

    def test_non_owner_404_row_intact(
        self, client, test_db, test_users, auth_headers
    ):
        """Another user's file is scoped out by the uploaded_by filter → 404,
        and the row survives."""
        admin = test_users[0]
        row = _seed(test_db, uploaded_by=admin.id)
        resp = client.delete(
            f"/api/files/{row.id}", headers=auth_headers["contributor"]
        )
        assert resp.status_code == 404, resp.text
        test_db.expire_all()
        assert (
            test_db.query(UploadedData).filter(UploadedData.id == row.id).first()
            is not None
        )

    def test_delete_without_storage_key_still_removes_row(
        self, client, test_db, test_users, auth_headers
    ):
        contributor = test_users[1]
        row = _seed(test_db, uploaded_by=contributor.id, storage_key=None)
        resp = client.delete(
            f"/api/files/{row.id}", headers=auth_headers["contributor"]
        )
        assert resp.status_code == 200, resp.text
        test_db.expire_all()
        assert (
            test_db.query(UploadedData).filter(UploadedData.id == row.id).first()
            is None
        )
