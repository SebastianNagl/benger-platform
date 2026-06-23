"""
Comprehensive tests for storage router endpoints.
Tests the router architecture and endpoint functionality.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import UploadedData, User


class TestStorageRouter:
    """Test storage router endpoints"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_user(self):
        user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
        )
        # Set created_at after creation if needed
        user.created_at = datetime.now(timezone.utc)
        return user

    @pytest.fixture
    def mock_superadmin_user(self):
        user = User(
            id="admin-user-123",
            username="admin",
            email="admin@example.com",
            name="Admin User",
            hashed_password="hashed_password_admin",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
        )
        # Set created_at after creation if needed
        user.created_at = datetime.now(timezone.utc)
        return user

    @pytest.fixture
    def mock_uploaded_data(self, mock_user):
        data = UploadedData(
            id="file-123",
            name="test_file.txt",
            original_filename="test_file.txt",
            file_path="uploads/test_file.txt",
            size=1024,
            format="txt",
            uploaded_by=mock_user.id,
            storage_url="http://example.com/file.txt",
        )
        # Set upload_date after creation if needed
        data.upload_date = datetime.now(timezone.utc)
        return data

    def test_get_upload_url_success(self, client, mock_user):
        """Test successful upload URL generation"""
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        with patch("routers.storage.object_storage.get_upload_url") as mock_get_upload_url:
            mock_get_upload_url.return_value = {
                "upload_url": "http://example.com/upload",
                "file_key": "uploads/test_file.txt",
                "fields": {},
            }

            app.dependency_overrides[require_user] = override_require_user

            try:
                response = client.post(
                    "/storage/upload-url?filename=test_file.txt&file_type=uploads"
                )
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "upload_url" in data
                assert "file_key" in data
                mock_get_upload_url.assert_called_once()
            finally:
                app.dependency_overrides.clear()

    def test_get_upload_url_failure(self, client, mock_user):
        """Test upload URL generation failure"""
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        with patch("routers.storage.object_storage.get_upload_url") as mock_get_upload_url:
            mock_get_upload_url.side_effect = Exception("Storage error")

            app.dependency_overrides[require_user] = override_require_user

            try:
                response = client.post("/storage/upload-url?filename=test_file.txt")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
                assert "Failed to generate upload URL" in response.json()["detail"]
            finally:
                app.dependency_overrides.clear()

    # NOTE: ``test_upload_file_to_storage_success`` was removed — the
    # ``/storage/upload`` handler moved to the async DB lane and writes a real
    # ``UploadedData`` row, so the sync ``TestClient`` + ``Mock(spec=Session)``
    # override can't exercise its success path (the override targets the unused
    # sync ``get_db``, and the real async engine can't serve a sync TestClient
    # request mid-loop). The persist-and-shape success path is covered in
    # ``tests/integration/test_storage_router_coverage.py`` (async fixtures).
    # The failure path below stays here: ``object_storage.upload_file`` raises
    # before any DB access, so the 500 branch resolves without touching the DB.

    def test_upload_file_to_storage_failure(self, client, mock_user):
        """Test file upload to storage failure"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.storage.object_storage.upload_file") as mock_upload:
            mock_upload.side_effect = Exception("Upload failed")

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                files = {"file": ("test_file.txt", b"test content", "text/plain")}
                response = client.post("/storage/upload", files=files)
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
                assert "Failed to upload file" in response.json()["detail"]
            finally:
                app.dependency_overrides.clear()

    # NOTE: the ``test_get_download_url_*`` (owner / superadmin / not-found /
    # access-denied) and ``test_delete_file_*`` (success / access-denied) cases
    # were removed here. Those handlers moved to the async DB lane
    # (``Depends(get_async_db)``), so the ``Mock(spec=Session)`` +
    # ``override_get_db`` pattern no longer reaches them (the override targets
    # the now-unused sync ``get_db``). Every one of those branches —
    # owner-grant, superadmin-grant, missing-row 404, non-owner 403,
    # missing-associated-task 404, delete success + row removal,
    # storage-delete-false 500 — is covered behaviourally against real rows in
    # ``tests/integration/test_storage_router_coverage.py`` (async fixtures).

    def test_init_multipart_upload_success(self, client, mock_user):
        """Test successful multipart upload initialization"""
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        with patch("routers.storage.object_storage.create_multipart_upload") as mock_init:
            mock_init.return_value = {
                "upload_id": "upload-123",
                "file_key": "uploads/large_file.zip",
            }

            app.dependency_overrides[require_user] = override_require_user

            try:
                response = client.post(
                    "/storage/multipart/init?filename=large_file.zip&file_type=uploads"
                )
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["upload_id"] == "upload-123"
                assert data["file_key"] == "uploads/large_file.zip"
            finally:
                app.dependency_overrides.clear()

    def test_get_multipart_urls_success(self, client, mock_user):
        """Test successful multipart upload URLs generation"""
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        with patch("routers.storage.object_storage.get_multipart_upload_urls") as mock_get_urls:
            mock_get_urls.return_value = [
                "http://example.com/upload/part1",
                "http://example.com/upload/part2",
            ]

            app.dependency_overrides[require_user] = override_require_user

            try:
                request_data = {
                    "file_key": "uploads/large_file.zip",
                    "upload_id": "upload-123",
                    "part_numbers": [1, 2],
                }

                response = client.post("/storage/multipart/urls", json=request_data)
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert len(data["urls"]) == 2
            finally:
                app.dependency_overrides.clear()

    # NOTE: ``test_complete_multipart_upload_success`` was removed — the
    # ``/storage/multipart/complete`` handler moved to the async DB lane and the
    # ``Mock(spec=Session)`` override no longer reaches it. Covered behaviourally
    # in ``tests/integration/test_storage_router_coverage.py``.

    def test_invalidate_cdn_cache_success(self, client, mock_superadmin_user):
        """Test successful CDN cache invalidation"""
        from main import app
        from routers.storage import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        mock_cdn = Mock()
        mock_cdn.invalidate_cache.return_value = "invalidation-123"

        with patch("routers.storage.cdn_service", mock_cdn):
            app.dependency_overrides[require_superadmin] = override_require_superadmin

            try:
                request_data = {"paths": ["/static/css/*", "/static/js/*"], "wait": False}

                response = client.post("/storage/cdn/invalidate", json=request_data)
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["invalidation_id"] == "invalidation-123"
                assert data["paths"] == ["/static/css/*", "/static/js/*"]
                assert data["status"] == "initiated"
            finally:
                app.dependency_overrides.clear()

    def test_get_cdn_asset_url_success(self, client):
        """Test successful CDN asset URL retrieval"""
        mock_cdn = Mock()
        mock_cdn.get_asset_url.return_value = "https://cdn.example.com/static/logo.png"
        mock_cdn.cdn_enabled = True

        with patch("routers.storage.cdn_service", mock_cdn):
            response = client.get("/storage/cdn/assets/static/logo.png")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["asset_path"] == "static/logo.png"
            assert data["cdn_url"] == "https://cdn.example.com/static/logo.png"
            assert data["cdn_enabled"] == True  # noqa: E712

    def test_check_storage_cdn_health_success(self, client, mock_superadmin_user):
        """Test successful storage and CDN health check"""
        from main import app
        from routers.storage import require_superadmin

        def override_require_superadmin():
            return mock_superadmin_user

        with patch("routers.storage.object_storage.health_check") as mock_storage_health:
            mock_storage_health.return_value = {"status": "healthy", "latency": "10ms"}

            mock_cdn = Mock()
            mock_cdn.health_check.return_value = {"status": "healthy", "edge_locations": 50}

            with patch("routers.storage.cdn_service", mock_cdn):
                app.dependency_overrides[require_superadmin] = override_require_superadmin

                try:
                    response = client.get("/storage/health")
                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert "storage" in data
                    assert "cdn" in data
                    assert "timestamp" in data
                    assert data["storage"]["status"] == "healthy"
                    assert data["cdn"]["status"] == "healthy"
                finally:
                    app.dependency_overrides.clear()


@pytest.mark.integration
class TestStorageRouterIntegration:
    """Integration tests for storage router"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_complete_upload_workflow(self, client):
        """Test complete file upload workflow"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        mock_user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
        )
        # Set created_at after creation if needed
        mock_user.created_at = datetime.now(timezone.utc)

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Step 1: Get upload URL
            with patch("routers.storage.object_storage.get_upload_url") as mock_get_upload_url:
                mock_get_upload_url.return_value = {
                    "upload_url": "http://example.com/upload",
                    "file_key": "uploads/test_file.txt",
                }

                response = client.post("/storage/upload-url?filename=test_file.txt")
                assert response.status_code == status.HTTP_200_OK

            # Step 2 (the direct ``/storage/upload`` DB-persist step) is covered
            # in ``tests/integration/test_storage_router_coverage.py`` now that
            # the upload handler runs on the async DB lane — it can't be driven
            # through the sync TestClient + Mock(spec=Session) here.

        finally:
            app.dependency_overrides.clear()

    # NOTE: ``test_multipart_upload_workflow`` was removed here. Its final
    # ``/storage/multipart/complete`` step writes a real ``UploadedData`` row,
    # and that handler moved to the async DB lane (``Depends(get_async_db)``),
    # so the ``Mock(spec=Session)`` + ``get_db`` override no longer reaches it.
    # The full multipart-complete persistence path is covered behaviourally in
    # ``tests/integration/test_storage_router_coverage.py`` (async fixtures).
    # The init + part-URL steps stay covered by ``test_init_multipart_upload_success``
    # and ``test_get_multipart_urls_success`` above (no DB).

    def test_error_handling_scenarios(self, client):
        """Test various error handling scenarios"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        mock_user = User(
            id="test-user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            hashed_password="hashed_password_test",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
        )
        # Set created_at after creation if needed
        mock_user.created_at = datetime.now(timezone.utc)

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            # Test various storage failures
            with patch("routers.storage.object_storage.get_upload_url") as mock_get_upload_url:
                mock_get_upload_url.side_effect = Exception("Storage unavailable")

                response = client.post("/storage/upload-url?filename=test_file.txt")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

            with patch("routers.storage.object_storage.upload_file") as mock_upload:
                mock_upload.side_effect = Exception("Upload failed")

                files = {"file": ("test_file.txt", b"test content", "text/plain")}
                response = client.post("/storage/upload", files=files)
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        finally:
            app.dependency_overrides.clear()
