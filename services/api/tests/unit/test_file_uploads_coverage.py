"""
Unit tests for routers/file_uploads.py to increase coverage.
Tests upload, list, download, and delete file endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_user


def _make_user(is_superadmin=True, user_id="user-123"):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_db.query.return_value = mock_q
    return mock_db


class TestListFiles:
    def test_empty_list(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/files/")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_with_files(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        file_record = Mock()
        file_record.id = "file-1"
        file_record.name = "test.pdf"
        file_record.size = 1024
        file_record.format = "pdf"
        file_record.upload_date = datetime.now(timezone.utc)
        file_record.task_id = None
        file_record.storage_url = "https://storage.example.com/test.pdf"
        file_record.storage_key = "uploads/test.pdf"
        file_record.cdn_url = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [file_record]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/files/")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["name"] == "test.pdf"
        finally:
            app.dependency_overrides.clear()

    def test_filter_by_task_id(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/files/?task_id=task-1")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_file_without_storage_url(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        file_record = Mock()
        file_record.id = "file-1"
        file_record.name = "test.pdf"
        file_record.size = 1024
        file_record.format = "pdf"
        file_record.upload_date = datetime.now(timezone.utc)
        file_record.task_id = None
        file_record.storage_url = None
        file_record.storage_key = "uploads/test.pdf"
        file_record.cdn_url = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [file_record]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.file_uploads.object_storage") as mock_storage:
                mock_storage.get_download_url.return_value = "https://generated-url.com"
                resp = client.get("/api/files/")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestDownloadFile:
    def test_file_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/files/nonexistent/download")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_redirect_to_presigned_url(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        file_record = Mock()
        file_record.id = "file-1"
        file_record.storage_key = "uploads/test.pdf"
        file_record.file_path = None
        file_record.original_filename = "test.pdf"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = file_record
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.file_uploads.object_storage") as mock_storage:
                mock_storage.get_download_url.return_value = "https://storage.example.com/presigned"
                resp = client.get("/api/files/file-1/download", follow_redirects=False)
                assert resp.status_code == 302
        finally:
            app.dependency_overrides.clear()


class TestDeleteFile:
    def test_file_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/files/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_successful_delete(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        file_record = Mock()
        file_record.id = "file-1"
        file_record.storage_key = "uploads/test.pdf"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = file_record
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.file_uploads.object_storage"):
                resp = client.delete("/api/files/file-1")
                assert resp.status_code == 200
                assert "deleted" in resp.json()["message"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_delete_without_storage_key(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        file_record = Mock()
        file_record.id = "file-1"
        file_record.storage_key = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = file_record
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/files/file-1")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()
