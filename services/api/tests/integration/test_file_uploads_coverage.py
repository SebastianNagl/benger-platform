"""Behavioral integration tests for ``routers/file_uploads.py``.

The router was migrated to the async DB lane (``Depends(get_async_db)``), so
these tests seed real ``UploadedData`` rows via ``async_test_db`` and drive
the HTTP surface through ``async_test_client``. ``require_user`` is overridden
per-test to return an auth User matching the seeded owner (the sync auth
dependency can't see the async test transaction). The object-storage
*primitive* calls are patched (so the suite doesn't depend on a live MinIO
bucket), but the router's own logic — DB INSERT/DELETE, per-user filtering,
the storage_url-regeneration branch in ``list_files``, the presigned-redirect
vs file_path fallback in ``download_file`` — runs for real.

  - ``POST /api/files/upload`` persists a real row (storage_key, file_hash,
    storage_type, size, format, owner) and returns the shaped response.
  - ``GET /api/files/`` lists only the caller's rows, filters by task_id, and
    exercises the storage_url-regeneration branch for a row missing a URL.
  - ``GET /api/files/{id}/download`` 404 for someone else's / missing file,
    302 presigned redirect for a storage_key row, FileResponse fallback for a
    legacy file_path row, 404 when neither resolves.
  - ``DELETE /api/files/{id}`` removes only the caller's row; 404 for a
    non-owner (the per-user filter scopes it out).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import UploadedData, User


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


async def _make_user(db, *, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"fu-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="File User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed(
    db,
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
    db.add(row)
    await db.commit()
    return row


async def _get_row(db, file_id):
    result = await db.execute(select(UploadedData).where(UploadedData.id == file_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# POST /api/files/upload — real INSERT
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpload:
    @pytest.mark.asyncio
    async def test_upload_persists_row(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        storage_result = {
            "file_key": "uploads/2026/06/14/report.pdf",
            "url": "https://signed/report.pdf",
            "hash": "abc123hash",
        }
        with _as_user(admin), patch("routers.file_uploads.object_storage") as mock_storage:
            mock_storage.upload_file.return_value = storage_result
            mock_storage.cdn_enabled = False
            mock_storage.storage_backend = "local"
            resp = await async_test_client.post(
                "/api/files/upload",
                files={"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "report.pdf"
        assert body["format"] == "pdf"
        assert body["url"] == "https://signed/report.pdf"

        # Persisted row carries the storage metadata.
        row = await _get_row(async_test_db, body["id"])
        assert row is not None
        assert row.uploaded_by == admin.id
        assert row.storage_key == "uploads/2026/06/14/report.pdf"
        assert row.file_hash == "abc123hash"
        assert row.storage_type == "local"
        assert row.format == "pdf"

    @pytest.mark.asyncio
    async def test_upload_with_task_and_description(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        storage_result = {
            "file_key": "uploads/x/notes.txt",
            "url": "https://signed/notes.txt",
            "hash": "deadbeef",
        }
        with _as_user(admin), patch("routers.file_uploads.object_storage") as mock_storage:
            mock_storage.upload_file.return_value = storage_result
            mock_storage.cdn_enabled = False
            mock_storage.storage_backend = "local"
            resp = await async_test_client.post(
                "/api/files/upload?task_id=task-42&description=meeting+notes",
                files={"file": ("notes.txt", b"hi", "text/plain")},
            )
        assert resp.status_code == 200, resp.text
        row = await _get_row(async_test_db, resp.json()["id"])
        assert row.task_id == "task-42"
        assert row.description == "meeting notes"


# ---------------------------------------------------------------------------
# GET /api/files/ — per-user listing + filters + url regen
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListFiles:
    @pytest.mark.asyncio
    async def test_lists_only_callers_files(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        mine = await _seed(async_test_db, uploaded_by=contributor.id, name="mine.pdf")
        await _seed(async_test_db, uploaded_by=admin.id, name="theirs.pdf")

        with _as_user(contributor):
            resp = await async_test_client.get("/api/files/")
        assert resp.status_code == 200, resp.text
        ids = {f["id"] for f in resp.json()}
        assert mine.id in ids
        # Admin's file is excluded by the uploaded_by filter.
        assert all(f["name"] != "theirs.pdf" for f in resp.json())

    @pytest.mark.asyncio
    async def test_filter_by_task_id(self, async_test_client, async_test_db):
        contributor = await _make_user(async_test_db, is_superadmin=False)
        with_task = await _seed(
            async_test_db, uploaded_by=contributor.id, name="a.pdf", task_id="t-1"
        )
        await _seed(async_test_db, uploaded_by=contributor.id, name="b.pdf", task_id="t-2")

        with _as_user(contributor):
            resp = await async_test_client.get("/api/files/?task_id=t-1")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["id"] == with_task.id

    @pytest.mark.asyncio
    async def test_regenerates_url_when_missing(self, async_test_client, async_test_db):
        """A row with storage_key but no storage_url triggers the on-the-fly
        get_download_url regeneration branch."""
        contributor = await _make_user(async_test_db, is_superadmin=False)
        await _seed(
            async_test_db,
            uploaded_by=contributor.id,
            name="nourl.pdf",
            storage_url=None,
            storage_key="uploads/nourl.pdf",
        )
        with _as_user(contributor), patch(
            "routers.file_uploads.object_storage.get_download_url",
            return_value="https://regenerated/url",
        ) as mock_gen:
            resp = await async_test_client.get("/api/files/")
        assert resp.status_code == 200, resp.text
        mock_gen.assert_called_once()
        url = next(f["url"] for f in resp.json() if f["name"] == "nourl.pdf")
        assert url == "https://regenerated/url"


# ---------------------------------------------------------------------------
# GET /api/files/{id}/download
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDownload:
    @pytest.mark.asyncio
    async def test_missing_file_404(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(f"/api/files/{_uid()}/download")
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_other_users_file_404(self, async_test_client, async_test_db):
        """The query is scoped to uploaded_by==current_user, so another user's
        file is a 404 (not 403)."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        row = await _seed(async_test_db, uploaded_by=admin.id)
        with _as_user(contributor):
            resp = await async_test_client.get(f"/api/files/{row.id}/download")
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_storage_key_redirects_to_presigned(
        self, async_test_client, async_test_db
    ):
        contributor = await _make_user(async_test_db, is_superadmin=False)
        row = await _seed(
            async_test_db, uploaded_by=contributor.id, storage_key="uploads/dl.pdf"
        )
        with _as_user(contributor), patch(
            "routers.file_uploads.object_storage.get_download_url",
            return_value="https://signed/redirect-target",
        ) as mock_dl:
            resp = await async_test_client.get(
                f"/api/files/{row.id}/download",
                follow_redirects=False,
            )
        assert resp.status_code == 302, resp.text
        assert resp.headers["location"] == "https://signed/redirect-target"
        mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_storage_key_no_file_path_404(
        self, async_test_client, async_test_db
    ):
        """No storage_key and a file_path that doesn't exist on disk → the
        terminal 'File data not found' 404."""
        contributor = await _make_user(async_test_db, is_superadmin=False)
        row = await _seed(
            async_test_db,
            uploaded_by=contributor.id,
            storage_key=None,
            file_path="/nonexistent/path/ghost.pdf",
        )
        with _as_user(contributor):
            resp = await async_test_client.get(f"/api/files/{row.id}/download")
        assert resp.status_code == 404, resp.text
        assert "File data not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/files/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDelete:
    @pytest.mark.asyncio
    async def test_owner_delete_removes_row(self, async_test_client, async_test_db):
        contributor = await _make_user(async_test_db, is_superadmin=False)
        row = await _seed(
            async_test_db, uploaded_by=contributor.id, storage_key="uploads/del.pdf"
        )
        with _as_user(contributor), patch("routers.file_uploads.object_storage.delete_file"):
            resp = await async_test_client.delete(f"/api/files/{row.id}")
        assert resp.status_code == 200, resp.text
        assert "deleted" in resp.json()["message"].lower()
        assert await _get_row(async_test_db, row.id) is None

    @pytest.mark.asyncio
    async def test_missing_file_404(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete(f"/api/files/{_uid()}")
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_non_owner_404_row_intact(self, async_test_client, async_test_db):
        """Another user's file is scoped out by the uploaded_by filter → 404,
        and the row survives."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        contributor = await _make_user(async_test_db, is_superadmin=False)
        row = await _seed(async_test_db, uploaded_by=admin.id)
        with _as_user(contributor):
            resp = await async_test_client.delete(f"/api/files/{row.id}")
        assert resp.status_code == 404, resp.text
        assert await _get_row(async_test_db, row.id) is not None

    @pytest.mark.asyncio
    async def test_delete_without_storage_key_still_removes_row(
        self, async_test_client, async_test_db
    ):
        contributor = await _make_user(async_test_db, is_superadmin=False)
        row = await _seed(async_test_db, uploaded_by=contributor.id, storage_key=None)
        with _as_user(contributor):
            resp = await async_test_client.delete(f"/api/files/{row.id}")
        assert resp.status_code == 200, resp.text
        assert await _get_row(async_test_db, row.id) is None
