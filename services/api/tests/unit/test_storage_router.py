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

    def test_upload_file_to_storage_success(self, client, mock_user):
        """Test successful file upload to storage"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            return mock_db

        with patch("routers.storage.object_storage.upload_file") as mock_upload:
            mock_upload.return_value = {
                "file_key": "uploads/test_file.txt",
                "url": "http://example.com/file.txt",
                "size": 1024,
                "content_type": "text/plain",
                "uploaded_at": datetime.now().isoformat(),
                "storage_backend": "local",
            }

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                # Create mock file
                files = {"file": ("test_file.txt", b"test content", "text/plain")}
                data = {"file_type": "uploads", "metadata": '{"type": "document"}'}

                response = client.post("/storage/upload", files=files, data=data)
                assert response.status_code == status.HTTP_200_OK
                response_data = response.json()
                assert response_data["file_key"] == "uploads/test_file.txt"
                assert response_data["size"] == 1024
            finally:
                app.dependency_overrides.clear()

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

    def test_get_download_url_success_owner(self, client, mock_user, mock_uploaded_data):
        """Test successful download URL generation for file owner"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = mock_uploaded_data
            return mock_db

        with patch("routers.storage.object_storage.get_download_url") as mock_get_download_url:
            mock_get_download_url.return_value = "http://example.com/download/file.txt"

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/storage/download-url/file-123")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["url"] == "http://example.com/download/file.txt"
                assert data["filename"] == "test_file.txt"
                assert data["size"] == 1024
            finally:
                app.dependency_overrides.clear()

    def test_get_download_url_success_superadmin(
        self, client, mock_superadmin_user, mock_uploaded_data
    ):
        """Test successful download URL generation for superadmin"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_superadmin_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = mock_uploaded_data
            return mock_db

        with patch("routers.storage.object_storage.get_download_url") as mock_get_download_url:
            mock_get_download_url.return_value = "http://example.com/download/file.txt"

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.get("/storage/download-url/file-123")
                assert response.status_code == status.HTTP_200_OK
            finally:
                app.dependency_overrides.clear()

    def test_get_download_url_file_not_found(self, client, mock_user):
        """Test download URL generation when file not found"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = None
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/storage/download-url/nonexistent-file")
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "File not found" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_get_download_url_access_denied(self, client, mock_uploaded_data):
        """Test download URL generation with access denied"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        # Different user than file owner
        different_user = User(
            id="different-user-456",
            username="differentuser",
            email="different@example.com",
            name="Different User",
            hashed_password="hashed_password_different",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
        )
        # Set created_at after creation if needed
        different_user.created_at = datetime.now(timezone.utc)

        def override_require_user():
            return different_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = mock_uploaded_data
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.get("/storage/download-url/file-123")
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "Access denied" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_delete_file_from_storage_success(self, client, mock_user, mock_uploaded_data):
        """Test successful file deletion from storage"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        mock_db = Mock(spec=Session)
        mock_db.query().filter().first.return_value = mock_uploaded_data

        def override_require_user():
            return mock_user

        def override_get_db():
            return mock_db

        with patch("routers.storage.object_storage.delete_file") as mock_delete:
            mock_delete.return_value = True

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                response = client.delete("/storage/file/file-123")
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["message"] == "File deleted successfully"
                mock_db.delete.assert_called_once()
                mock_db.commit.assert_called_once()
            finally:
                app.dependency_overrides.clear()

    def test_delete_file_access_denied(self, client, mock_uploaded_data):
        """Test file deletion with access denied"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        # Different user than file owner
        different_user = User(
            id="different-user-456",
            username="differentuser",
            email="different@example.com",
            name="Different User",
            hashed_password="hashed_password_different",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
        )
        # Set created_at after creation if needed
        different_user.created_at = datetime.now(timezone.utc)

        def override_require_user():
            return different_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            mock_db.query().filter().first.return_value = mock_uploaded_data
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            response = client.delete("/storage/file/file-123")
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "Access denied" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

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

    def test_complete_multipart_upload_success(self, client, mock_user):
        """Test successful multipart upload completion"""
        from database import get_db
        from main import app
        from routers.storage import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            mock_db = Mock(spec=Session)
            return mock_db

        with patch("routers.storage.object_storage.complete_multipart_upload") as mock_complete:
            mock_complete.return_value = {
                "size": 5000000,
                "etag": "etag-123",
                "storage_backend": "s3",
            }

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db

            try:
                request_data = {
                    "file_key": "uploads/large_file.zip",
                    "upload_id": "upload-123",
                    "parts": [
                        {"PartNumber": 1, "ETag": "etag1"},
                        {"PartNumber": 2, "ETag": "etag2"},
                    ],
                    "metadata": {"type": "archive"},
                }

                response = client.post("/storage/multipart/complete", json=request_data)
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["file_key"] == "uploads/large_file.zip"
                assert data["size"] == 5000000
            finally:
                app.dependency_overrides.clear()

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
            assert data["cdn_enabled"] is True

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

            # Step 2: Upload file directly
            with patch("routers.storage.object_storage.upload_file") as mock_upload:
                mock_upload.return_value = {
                    "file_key": "uploads/test_file.txt",
                    "url": "http://example.com/file.txt",
                    "size": 1024,
                    "content_type": "text/plain",
                    "uploaded_at": datetime.now().isoformat(),
                    "storage_backend": "local",
                }

                files = {"file": ("test_file.txt", b"test content", "text/plain")}
                response = client.post("/storage/upload", files=files)
                assert response.status_code == status.HTTP_200_OK

        finally:
            app.dependency_overrides.clear()

    def test_multipart_upload_workflow(self, client):
        """Test complete multipart upload workflow"""
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
            # Step 1: Initialize multipart upload
            with patch("routers.storage.object_storage.create_multipart_upload") as mock_init:
                mock_init.return_value = {
                    "upload_id": "upload-123",
                    "file_key": "uploads/large_file.zip",
                }

                response = client.post("/storage/multipart/init?filename=large_file.zip")
                assert response.status_code == status.HTTP_200_OK
                init_data = response.json()

            # Step 2: Get part upload URLs
            with patch("routers.storage.object_storage.get_multipart_upload_urls") as mock_get_urls:
                mock_get_urls.return_value = ["http://example.com/upload/part1"]

                request_data = {
                    "file_key": init_data["file_key"],
                    "upload_id": init_data["upload_id"],
                    "part_numbers": [1],
                }

                response = client.post("/storage/multipart/urls", json=request_data)
                assert response.status_code == status.HTTP_200_OK

            # Step 3: Complete multipart upload
            with patch("routers.storage.object_storage.complete_multipart_upload") as mock_complete:
                mock_complete.return_value = {
                    "size": 5000000,
                    "etag": "etag-123",
                    "storage_backend": "s3",
                }

                complete_data = {
                    "file_key": init_data["file_key"],
                    "upload_id": init_data["upload_id"],
                    "parts": [{"PartNumber": 1, "ETag": "etag1"}],
                }

                response = client.post("/storage/multipart/complete", json=complete_data)
                assert response.status_code == status.HTTP_200_OK

        finally:
            app.dependency_overrides.clear()

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
