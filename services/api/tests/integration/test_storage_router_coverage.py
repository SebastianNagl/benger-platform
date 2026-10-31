"""Behavioral integration tests for ``routers/storage.py``.

The DB-touching storage handlers were migrated to the async DB lane
(``Depends(get_async_db)``), so these tests seed real ``UploadedData`` rows via
``async_test_db`` and drive the HTTP surface through ``async_test_client``.
``require_user`` / ``require_superadmin`` are overridden per-test via the
``_as_user`` context manager to return an auth User matching the seeded owner
(the sync auth dependency can't see the async test transaction). Object-storage
*primitive* calls (``object_storage.upload_file`` / ``get_download_url`` /
``delete_file`` / ``complete_multipart_upload`` / ``health_check``) are patched
so the tests don't depend on a live MinIO bucket — but the router's own logic
(permission checks, DB row creation/deletion, response shaping) runs for real
and every mutating test asserts the persisted ``uploaded_data`` row.

  - ``/storage/upload`` persists an UploadedData row (asserted via DB) and
    parses the metadata blob (valid + malformed-JSON-swallowed branches).
  - ``/storage/download-url`` 404 (missing row), owner-grant, superadmin-grant,
    non-owner-no-task 403, missing-associated-task 404 — each against a real row.
  - ``/storage/file/{id}`` DELETE removes the real row on success; 404 missing;
    403 non-owner leaves the row intact; storage-delete-returns-False → 500 and
    the row is NOT removed.
  - ``/storage/multipart/complete`` persists a row with the metadata-derived
    original_filename.
  - ``/storage/cdn/assets/{path}`` shaping + ``/storage/health`` superadmin gate
    (these two touch no DB; they run through the async client unchanged).
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import func, select

from auth_module.dependencies import require_superadmin, require_user
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
    # require_superadmin is a distinct dependency; mirror it so superadmin-gated
    # endpoints (health) see the same identity. Non-superadmins still get
    # rejected because the real require_superadmin gate only passes superadmins
    # — but for tests we override it directly with the seeded user's flag.
    if db_user.is_superadmin:
        app.dependency_overrides[require_superadmin] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(require_superadmin, None)


async def _make_user(db, *, is_superadmin=False, prefix="stg") -> User:
    u = User(
        id=_uid(),
        username=f"{prefix}-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Storage User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_uploaded(
    db,
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
    db.add(row)
    await db.commit()
    return row


async def _exists(db, file_id: str) -> bool:
    # `populate_existing` forces the SELECT to refresh any expired/identity-map
    # instance so its column attrs are loaded without a lazy (off-greenlet) IO.
    row = (
        await db.execute(
            select(UploadedData)
            .where(UploadedData.id == file_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    return row is not None


async def _get_row(db, file_id: str):
    return (
        await db.execute(
            select(UploadedData)
            .where(UploadedData.id == file_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _count(db) -> int:
    return (await db.execute(select(func.count(UploadedData.id)))).scalar()


# ---------------------------------------------------------------------------
# POST /storage/upload — real INSERT
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUploadFileToStorage:
    @pytest.mark.asyncio
    async def test_upload_persists_row_and_parses_metadata(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        upload_result = {
            "file_key": "uploads/2026/06/14/note.txt",
            "url": "file:///tmp/benger-storage/uploads/note.txt",
            "size": 12,
            "content_type": "text/plain",
            "hash": "deadbeef",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": "local",
        }
        with _as_user(admin), patch(
            "routers.storage.object_storage.upload_file", return_value=upload_result
        ) as mock_up:
            resp = await async_test_client.post(
                "/storage/upload",
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
        row = await _get_row(async_test_db, body["id"])
        assert row is not None
        assert row.uploaded_by == admin.id
        assert row.file_path == "uploads/2026/06/14/note.txt"
        # The client's metadata plus the server-owned validated type.
        assert row.file_metadata == {"kind": "doc", "stored_content_type": "text/plain"}
        assert row.format == "txt"

    @pytest.mark.asyncio
    async def test_upload_malformed_metadata_is_swallowed(
        self, async_test_client, async_test_db
    ):
        """Invalid JSON in the metadata form field is ignored (empty dict),
        not fatal — the row still persists."""
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        upload_result = {
            "file_key": "uploads/x/note.txt",
            "url": "file:///tmp/x/note.txt",
            "size": 3,
            "content_type": "text/plain",
            "hash": "abc",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": "local",
        }
        with _as_user(admin), patch(
            "routers.storage.object_storage.upload_file", return_value=upload_result
        ):
            resp = await async_test_client.post(
                "/storage/upload",
                files={"file": ("note.txt", b"xyz", "text/plain")},
                data={"metadata": "{not valid json"},
            )
        assert resp.status_code == 200, resp.text
        row_id = resp.json()["id"]
        row = await _get_row(async_test_db, row_id)
        assert row is not None
        assert row.file_metadata == {"stored_content_type": "text/plain"}

    @pytest.mark.asyncio
    async def test_upload_storage_failure_returns_500_no_row(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        before = await _count(async_test_db)
        with _as_user(admin), patch(
            "routers.storage.object_storage.upload_file",
            side_effect=Exception("backend down"),
        ):
            resp = await async_test_client.post(
                "/storage/upload",
                files={"file": ("note.txt", b"hello", "text/plain")},
            )
        assert resp.status_code == 500, resp.text
        assert "Failed to upload file" in resp.json()["detail"]
        async_test_db.expire_all()
        assert await _count(async_test_db) == before


# ---------------------------------------------------------------------------
# GET /storage/download-url/{file_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDownloadUrl:
    @pytest.mark.asyncio
    async def test_missing_file_404(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.get(f"/storage/download-url/{_uid()}")
        assert resp.status_code == 404, resp.text
        assert "File not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_owner_gets_presigned_url(self, async_test_client, async_test_db):
        contributor = await _make_user(async_test_db)
        row = await _seed_uploaded(async_test_db, uploaded_by=contributor.id)
        with _as_user(contributor), patch(
            "routers.storage.object_storage.get_download_url",
            return_value="https://signed.example/download",
        ) as mock_dl:
            resp = await async_test_client.get(f"/storage/download-url/{row.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["url"] == "https://signed.example/download"
        assert body["filename"] == "doc.txt"
        assert body["size"] == 11
        mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_superadmin_grant_for_other_users_file(
        self, async_test_client, async_test_db
    ):
        contributor = await _make_user(async_test_db)
        admin = await _make_user(async_test_db, is_superadmin=True)
        row = await _seed_uploaded(async_test_db, uploaded_by=contributor.id)
        with _as_user(admin), patch(
            "routers.storage.object_storage.get_download_url",
            return_value="https://signed.example/admin-dl",
        ):
            resp = await async_test_client.get(f"/storage/download-url/{row.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["url"] == "https://signed.example/admin-dl"

    @pytest.mark.asyncio
    async def test_non_owner_no_task_403(self, async_test_client, async_test_db):
        """A file with no task_id, requested by a non-owner non-superadmin →
        the final else 403 (Access denied)."""
        contributor = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        row = await _seed_uploaded(
            async_test_db, uploaded_by=contributor.id, task_id=None
        )
        with _as_user(other):
            resp = await async_test_client.get(f"/storage/download-url/{row.id}")
        assert resp.status_code == 403, resp.text
        assert "Access denied" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_owner_with_missing_associated_task_404(
        self, async_test_client, async_test_db
    ):
        """task_id set but the referenced project row doesn't exist → the
        'Associated task not found' 404 branch (returns before the
        organization_ids access)."""
        contributor = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        row = await _seed_uploaded(
            async_test_db, uploaded_by=contributor.id, task_id="no-such-project"
        )
        with _as_user(other):
            resp = await async_test_client.get(f"/storage/download-url/{row.id}")
        assert resp.status_code == 404, resp.text
        assert "Associated task not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /storage/file/{file_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_missing_file_404(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin):
            resp = await async_test_client.delete(f"/storage/file/{_uid()}")
        assert resp.status_code == 404, resp.text
        assert "File not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_owner_delete_removes_row(self, async_test_client, async_test_db):
        contributor = await _make_user(async_test_db)
        row = await _seed_uploaded(async_test_db, uploaded_by=contributor.id)
        file_path = row.file_path
        file_id = row.id
        with _as_user(contributor), patch(
            "routers.storage.object_storage.delete_file", return_value=True
        ) as mock_del:
            resp = await async_test_client.delete(f"/storage/file/{file_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "File deleted successfully"
        mock_del.assert_called_once_with(file_path)
        assert not await _exists(async_test_db, file_id)

    @pytest.mark.asyncio
    async def test_non_owner_delete_403_row_intact(
        self, async_test_client, async_test_db
    ):
        contributor = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        row = await _seed_uploaded(async_test_db, uploaded_by=contributor.id)
        file_id = row.id
        with _as_user(other):
            resp = await async_test_client.delete(f"/storage/file/{file_id}")
        assert resp.status_code == 403, resp.text
        assert "Access denied" in resp.json()["detail"]
        assert await _exists(async_test_db, file_id)

    @pytest.mark.asyncio
    async def test_storage_delete_false_returns_500_row_intact(
        self, async_test_client, async_test_db
    ):
        """When the storage backend reports failure, the endpoint 500s and the
        DB row is NOT removed (delete is gated on storage success)."""
        contributor = await _make_user(async_test_db)
        row = await _seed_uploaded(async_test_db, uploaded_by=contributor.id)
        file_id = row.id
        with _as_user(contributor), patch(
            "routers.storage.object_storage.delete_file", return_value=False
        ):
            resp = await async_test_client.delete(f"/storage/file/{file_id}")
        assert resp.status_code == 500, resp.text
        assert await _exists(async_test_db, file_id)


# ---------------------------------------------------------------------------
# POST /storage/multipart/complete — real INSERT
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCompleteMultipart:
    @pytest.mark.asyncio
    async def test_complete_persists_row_with_metadata_filename(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        with _as_user(admin), patch(
            "routers.storage.object_storage.complete_multipart_upload",
            return_value={"size": 9000, "etag": "etag-xyz", "storage_backend": "local"},
        ) as mock_complete:
            resp = await async_test_client.post(
                "/storage/multipart/complete",
                json={
                    "file_key": f"uploads/2026/06/14/{admin.id}/big.zip",
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

        row = await _get_row(async_test_db, body["id"])
        assert row is not None
        # original_filename pulled from metadata; name derived from the key tail.
        assert row.original_filename == "report-final.zip"
        assert row.name == "big.zip"
        assert row.size == 9000
        assert row.uploaded_by == admin.id


# ---------------------------------------------------------------------------
# Upload / download policy (audit S1): types, prefixes, sizes, expiry,
# disposition, multipart key ownership
# ---------------------------------------------------------------------------

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.mark.integration
class TestStoragePolicy:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "content_type,filename",
        [
            ("text/html", "x.html"),
            ("image/svg+xml", "x.svg"),
            ("application/xml", "x.xml"),
            ("text/javascript", "x.js"),
        ],
    )
    async def test_upload_url_refuses_scriptable_types(
        self, async_test_client, async_test_db, content_type, filename
    ):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.storage.object_storage.get_upload_url"
        ) as mock_url:
            resp = await async_test_client.post(
                "/storage/upload-url",
                params={"filename": filename, "content_type": content_type},
            )
        assert resp.status_code == 415, resp.text
        mock_url.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("file_type", ["static", "exports", "imports", "submissions"])
    async def test_upload_url_refuses_server_prefixes(
        self, async_test_client, async_test_db, file_type
    ):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.storage.object_storage.get_upload_url"
        ) as mock_url:
            resp = await async_test_client.post(
                "/storage/upload-url",
                params={"filename": "a.png", "file_type": file_type},
            )
        assert resp.status_code == 400, resp.text
        mock_url.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "max_size,expected",
        [("0", 100 * 1024 * 1024), ("999999999999", 100 * 1024 * 1024), ("1024", 1024)],
    )
    async def test_upload_url_clamps_max_size_and_pins_type(
        self, async_test_client, async_test_db, max_size, expected
    ):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.storage.object_storage.get_upload_url",
            return_value={"upload_url": "u", "file_key": "k", "fields": {}},
        ) as mock_url:
            resp = await async_test_client.post(
                "/storage/upload-url",
                params={"filename": "deck.apkg", "file_type": "temp", "max_size": max_size},
            )
        assert resp.status_code == 200, resp.text
        kwargs = mock_url.call_args.kwargs
        assert kwargs["max_size"] == expected
        assert kwargs["file_type"] == "temp"
        assert kwargs["content_type"] == "application/zip"

    @pytest.mark.asyncio
    async def test_upload_refuses_html_and_magic_mismatch(
        self, async_test_client, async_test_db
    ):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        before = await _count(async_test_db)
        with _as_user(user), patch("routers.storage.object_storage.upload_file") as mock_up:
            html = await async_test_client.post(
                "/storage/upload",
                files={"file": ("x.html", b"<script>1</script>", "text/html")},
            )
            disguised = await async_test_client.post(
                "/storage/upload",
                files={"file": ("x.png", b"<html><script>1</script>", "image/png")},
            )
            static = await async_test_client.post(
                "/storage/upload",
                files={"file": ("x.png", PNG_BYTES, "image/png")},
                data={"file_type": "static"},
            )
        assert html.status_code == 415, html.text
        assert disguised.status_code == 415, disguised.text
        assert static.status_code == 400, static.text
        mock_up.assert_not_called()
        async_test_db.expire_all()
        assert await _count(async_test_db) == before

    @pytest.mark.asyncio
    async def test_upload_over_ceiling_is_413(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch.dict(
            "storage.upload_policy.CLIENT_PREFIX_MAX_BYTES", {"uploads": 8}
        ), patch("routers.storage.object_storage.upload_file") as mock_up:
            resp = await async_test_client.post(
                "/storage/upload",
                files={"file": ("a.txt", b"123456789", "text/plain")},
            )
        assert resp.status_code == 413, resp.text
        mock_up.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_valid_png_stores_validated_type(
        self, async_test_client, async_test_db
    ):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        upload_result = {
            "file_key": f"uploads/2026/10/31/{user.id}/p.png",
            "url": "file:///tmp/p.png",
            "size": len(PNG_BYTES),
            "content_type": "image/png",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": "local",
        }
        with _as_user(user), patch(
            "routers.storage.object_storage.upload_file", return_value=upload_result
        ) as mock_up:
            resp = await async_test_client.post(
                "/storage/upload",
                files={"file": ("p.png", PNG_BYTES, "image/png")},
                # A client cannot forge the server-owned type key.
                data={"metadata": '{"stored_content_type": "text/html"}'},
            )
        assert resp.status_code == 200, resp.text
        assert mock_up.call_args.kwargs["content_type"] == "image/png"
        row = await _get_row(async_test_db, resp.json()["id"])
        assert row.file_metadata["stored_content_type"] == "image/png"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "requested,expected", [(None, 3600), ("86400", 3600), ("5", 60), ("600", 600)]
    )
    async def test_download_url_clamps_expiry_and_forces_attachment(
        self, async_test_client, async_test_db, requested, expected
    ):
        owner = await _make_user(async_test_db)
        row = await _seed_uploaded(async_test_db, uploaded_by=owner.id)
        params = {} if requested is None else {"expires_in": requested}
        with _as_user(owner), patch(
            "routers.storage.object_storage.get_download_url",
            return_value="https://signed.example/x",
        ) as mock_dl:
            resp = await async_test_client.get(
                f"/storage/download-url/{row.id}", params=params
            )
        assert resp.status_code == 200, resp.text
        kwargs = mock_dl.call_args.kwargs
        assert kwargs["expires_in"] == expected
        # doc.txt has no stored type key: the extension decides, re-validated.
        assert kwargs["response_content_type"] == "text/plain"
        assert kwargs["response_content_disposition"] == 'attachment; filename="doc.txt"'

    @pytest.mark.asyncio
    async def test_download_url_never_echoes_html_type(
        self, async_test_client, async_test_db
    ):
        owner = await _make_user(async_test_db)
        row = UploadedData(
            id=_uid(),
            name="x.html",
            original_filename="x.html",
            file_path="uploads/2026/06/14/x.html",
            size=5,
            format="html",
            uploaded_by=owner.id,
            storage_backend="local",
            file_metadata={"stored_content_type": "text/html"},
        )
        async_test_db.add(row)
        await async_test_db.commit()
        with _as_user(owner), patch(
            "routers.storage.object_storage.get_download_url",
            return_value="https://signed.example/x",
        ) as mock_dl:
            resp = await async_test_client.get(f"/storage/download-url/{row.id}")
        assert resp.status_code == 200, resp.text
        kwargs = mock_dl.call_args.kwargs
        assert kwargs["response_content_type"] == "application/octet-stream"
        assert kwargs["response_content_disposition"].startswith("attachment;")

    @pytest.mark.asyncio
    async def test_multipart_init_refuses_svg(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user), patch(
            "routers.storage.object_storage.create_multipart_upload"
        ) as mock_init:
            resp = await async_test_client.post(
                "/storage/multipart/init", params={"filename": "x.svg"}
            )
        assert resp.status_code == 415, resp.text
        mock_init.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "key_template",
        [
            "uploads/2026/10/31/someone-else/big.zip",
            "exports/2026/10/{uid}/big.zip",
            "uploads/2026/../../exports/{uid}/big.zip",
            "big.zip",
        ],
    )
    async def test_multipart_refuses_keys_the_caller_does_not_own(
        self, async_test_client, async_test_db, key_template
    ):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        key = key_template.format(uid=user.id)
        with _as_user(user), patch(
            "routers.storage.object_storage.get_multipart_upload_urls"
        ) as mock_urls, patch(
            "routers.storage.object_storage.complete_multipart_upload"
        ) as mock_complete:
            urls = await async_test_client.post(
                "/storage/multipart/urls",
                json={"file_key": key, "upload_id": "u", "part_numbers": [1]},
            )
            complete = await async_test_client.post(
                "/storage/multipart/complete",
                json={"file_key": key, "upload_id": "u", "parts": []},
            )
        assert urls.status_code == 403, urls.text
        assert complete.status_code == 403, complete.text
        mock_urls.assert_not_called()
        mock_complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_multipart_complete_over_ceiling_deletes_and_413(
        self, async_test_client, async_test_db
    ):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        before = await _count(async_test_db)
        key = f"uploads/2026/10/31/{user.id}/big.zip"
        with _as_user(user), patch(
            "routers.storage.object_storage.complete_multipart_upload",
            return_value={"size": 200 * 1024 * 1024, "storage_backend": "s3"},
        ), patch("routers.storage.object_storage.delete_file") as mock_delete:
            resp = await async_test_client.post(
                "/storage/multipart/complete",
                json={"file_key": key, "upload_id": "u", "parts": []},
            )
        assert resp.status_code == 413, resp.text
        mock_delete.assert_called_once_with(key)
        async_test_db.expire_all()
        assert await _count(async_test_db) == before


# ---------------------------------------------------------------------------
# CDN asset URL + health (no DB; behavioral on cdn_service / object_storage)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCdnAndHealth:
    @pytest.mark.asyncio
    async def test_cdn_asset_url_shape(self, async_test_client):
        mock_cdn = Mock()
        mock_cdn.get_asset_url.return_value = "https://cdn.example/static/logo.png"
        mock_cdn.cdn_enabled = True
        with patch("routers.storage.cdn_service", mock_cdn):
            resp = await async_test_client.get("/storage/cdn/assets/static/logo.png")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["asset_path"] == "static/logo.png"
        assert body["cdn_url"] == "https://cdn.example/static/logo.png"
        assert body["cdn_enabled"] is True
        mock_cdn.get_asset_url.assert_called_once_with("/static/logo.png")

    @pytest.mark.asyncio
    async def test_health_requires_superadmin(self, async_test_client, async_test_db):
        """A non-superadmin is rejected by the require_superadmin gate."""
        contributor = await _make_user(async_test_db)
        await async_test_db.commit()
        # Note: _as_user only overrides require_superadmin for superadmins, so a
        # contributor hits the real gate and is rejected.
        with _as_user(contributor):
            resp = await async_test_client.get("/storage/health")
        assert resp.status_code in (401, 403), resp.text

    @pytest.mark.asyncio
    async def test_health_superadmin_reports_backends(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()
        mock_cdn = Mock()
        mock_cdn.health_check.return_value = {"status": "ok"}
        with _as_user(admin), patch(
            "routers.storage.object_storage.health_check",
            return_value={"healthy": True, "storage_backend": "local"},
        ), patch("routers.storage.cdn_service", mock_cdn):
            resp = await async_test_client.get("/storage/health")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "storage" in body and "cdn" in body and "timestamp" in body
        assert body["storage"]["healthy"] is True
