"""
Unit-level smoke tests for routers/file_uploads.py.

The router was migrated to the async DB lane, so the ``db.query``-Mock /
``get_db``-override pattern no longer reaches the handlers (they depend on
``get_async_db`` and call ``db.execute``). These now seed real rows via
``async_test_db`` and drive the surface through ``async_test_client``; the
exhaustive branch coverage lives in
``tests/integration/test_file_uploads_coverage.py``.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

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


async def _make_user(db):
    u = User(
        id=_uid(),
        username=f"fu-unit-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="File Unit User",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed(db, owner, *, storage_key="uploads/test.pdf", storage_url="https://s/test.pdf"):
    row = UploadedData(
        id=_uid(),
        name="test.pdf",
        original_filename="test.pdf",
        file_path="uploads/test.pdf",
        storage_key=storage_key,
        storage_url=storage_url,
        file_hash="h" * 8,
        storage_type="local",
        size=1024,
        format="pdf",
        uploaded_by=owner.id,
        upload_date=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()
    return row


class TestListFiles:
    @pytest.mark.asyncio
    async def test_empty_list(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get("/api/files/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_with_files(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await _seed(async_test_db, user)
        with _as_user(user):
            resp = await async_test_client.get("/api/files/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_filter_by_task_id(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get("/api/files/?task_id=task-1")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_file_without_storage_url(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await _seed(async_test_db, user, storage_url=None)
        with _as_user(user), patch("routers.file_uploads.object_storage") as mock_storage:
            mock_storage.get_download_url.return_value = "https://generated-url.com"
            resp = await async_test_client.get("/api/files/")
        assert resp.status_code == 200


class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_file_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get("/api/files/nonexistent/download")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_redirect_to_presigned_url(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        row = await _seed(async_test_db, user, storage_key="uploads/test.pdf")
        with _as_user(user), patch("routers.file_uploads.object_storage") as mock_storage:
            mock_storage.get_download_url.return_value = "https://storage.example.com/presigned"
            resp = await async_test_client.get(
                f"/api/files/{row.id}/download", follow_redirects=False
            )
        assert resp.status_code == 302


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_file_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.delete("/api/files/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_successful_delete(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        row = await _seed(async_test_db, user, storage_key="uploads/test.pdf")
        with _as_user(user), patch("routers.file_uploads.object_storage"):
            resp = await async_test_client.delete(f"/api/files/{row.id}")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_without_storage_key(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        row = await _seed(async_test_db, user, storage_key=None)
        with _as_user(user):
            resp = await async_test_client.delete(f"/api/files/{row.id}")
        assert resp.status_code == 200
