"""
Unit Tests for Object Storage Service

Tests the S3-compatible object storage functionality including:
- File upload and download
- Presigned URL generation
- Multipart uploads
- File management operations
- Health checks
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from object_storage import ObjectStorageService


@pytest.fixture
def storage_service():
    """Create an ObjectStorageService instance for testing"""
    return ObjectStorageService()


@pytest.fixture
def s3_storage_service(mock_s3_client):
    """Create an ObjectStorageService instance configured for S3 testing"""
    with patch.dict(os.environ, {"STORAGE_BACKEND": "s3", "S3_BUCKET": "test-bucket"}):
        with patch("object_storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            service = ObjectStorageService()
            service.s3_client = mock_s3_client
            service.bucket_name = "test-bucket"
            return service


@pytest.fixture
def mock_s3_client():
    """Create a mock S3 client"""
    client = Mock()
    client.put_object = Mock()
    client.get_object = Mock()
    client.delete_object = Mock()
    client.head_object = Mock()
    client.head_bucket = Mock()
    client.create_bucket = Mock()
    client.put_bucket_cors = Mock()
    client.list_objects_v2 = Mock()
    client.copy_object = Mock()
    client.generate_presigned_url = Mock()
    client.generate_presigned_post = Mock()
    client.create_multipart_upload = Mock()
    client.upload_part = Mock()
    client.complete_multipart_upload = Mock()
    return client


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for local storage testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


class TestObjectStorageServiceInitialization:
    """Test object storage service initialization"""

    def test_default_initialization(self):
        """Test default service initialization"""
        service = ObjectStorageService()

        assert service.storage_backend == "local"
        assert service.cdn_enabled is False
        assert service.local_storage_path == "/tmp/benger-storage"
        assert service.bucket_name == "benger-storage"


class TestLocalStorage:
    """Test local filesystem storage operations"""

    @patch.dict(os.environ, {"STORAGE_BACKEND": "local"})
    def test_upload_file_local(self, temp_storage_dir):
        """Test file upload to local storage"""
        with patch.dict(os.environ, {"LOCAL_STORAGE_PATH": temp_storage_dir}):
            service = ObjectStorageService()

            file_data = b"test file content"
            filename = "test.txt"

            result = service.upload_file(
                file_data=file_data,
                filename=filename,
                file_type="uploads",
                user_id="user123",
            )

            assert "file_key" in result
            assert "url" in result
            assert result["size"] == len(file_data)
            assert result["storage_backend"] == "local"

            # Check that file was actually written
            file_path = os.path.join(temp_storage_dir, result["file_key"])
            assert os.path.exists(file_path)

            with open(file_path, "rb") as f:
                assert f.read() == file_data

    @patch.dict(os.environ, {"STORAGE_BACKEND": "local"})
    def test_delete_file_local(self, temp_storage_dir):
        """Test file deletion from local storage"""
        with patch.dict(os.environ, {"LOCAL_STORAGE_PATH": temp_storage_dir}):
            service = ObjectStorageService()

            # Create a test file
            file_data = b"test content"
            result = service.upload_file(file_data, "test.txt", user_id="user123")
            file_key = result["file_key"]

            # Verify file exists
            file_path = os.path.join(temp_storage_dir, file_key)
            assert os.path.exists(file_path)

            # Delete file
            success = service.delete_file(file_key)
            assert success is True
            assert not os.path.exists(file_path)

    @patch.dict(os.environ, {"STORAGE_BACKEND": "local"})
    def test_get_file_info_local(self, temp_storage_dir):
        """Test getting file info from local storage"""
        with patch.dict(os.environ, {"LOCAL_STORAGE_PATH": temp_storage_dir}):
            service = ObjectStorageService()

            # Upload a file
            file_data = b"test content"
            result = service.upload_file(file_data, "test.txt", user_id="user123")
            file_key = result["file_key"]

            # Get file info
            info = service.get_file_info(file_key)

            assert info is not None
            assert info["key"] == file_key
            assert info["size"] == len(file_data)
            assert "last_modified" in info
            assert "metadata" in info


class TestFileOrganization:
    """Test file organization and key generation"""

    def test_get_file_key_uploads(self, storage_service):
        """Test file key generation for uploads"""
        with patch("services.storage.object_storage.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.year = 2025
            mock_now.month = 7
            mock_now.day = 14
            mock_now.strftime.return_value = "20250714_120000"
            mock_datetime.now.return_value = mock_now

            file_key = storage_service._get_file_key(
                file_type="uploads", filename="test.txt", user_id="user123"
            )

            assert "uploads/2025/07/14/user123/" in file_key
            assert "20250714_120000_test.txt" in file_key

    def test_get_file_key_exports(self, storage_service):
        """Test file key generation for exports"""
        with patch("services.storage.object_storage.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.year = 2025
            mock_now.month = 7
            mock_now.day = 14
            mock_now.strftime.return_value = "20250714_120000"
            mock_datetime.now.return_value = mock_now

            file_key = storage_service._get_file_key(file_type="exports", filename="report.pdf")

            assert "exports/2025/07/" in file_key
            assert "20250714_120000_report.pdf" in file_key

    def test_get_file_key_static(self, storage_service):
        """Test file key generation for static assets"""
        file_key = storage_service._get_file_key(file_type="static", filename="app.js")

        assert file_key.startswith("static/assets/")
        assert "app.js" in file_key


class TestCDNIntegration:
    """Test CDN integration features"""

    @patch.dict(os.environ, {"STORAGE_BACKEND": "s3"})
    def test_regular_url_for_uploads(self, storage_service, mock_s3_client):
        """Test regular presigned URL for user uploads"""
        storage_service.s3_client = mock_s3_client
        storage_service.cdn_enabled = True

        expected_url = "https://test-bucket.s3.amazonaws.com/uploads/test.txt?signature=abc"
        mock_s3_client.generate_presigned_url.return_value = expected_url

        result = storage_service.upload_file(
            file_data=b"user content", filename="document.pdf", file_type="uploads"
        )

        # User uploads should not use CDN
        assert "cdn.test.com" not in result["url"]


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_invalid_backend(self):
        """Test invalid storage backend handling"""
        with patch.dict(os.environ, {"STORAGE_BACKEND": "invalid"}):
            service = ObjectStorageService()
            # Should fall back to local storage
            assert service.storage_backend == "local"


class TestHealthCheck:
    """Test service health checking"""

    @patch.dict(os.environ, {"STORAGE_BACKEND": "local"})
    def test_local_health_check(self, storage_service, temp_storage_dir):
        """Test local storage health check"""
        with patch.dict(os.environ, {"LOCAL_STORAGE_PATH": temp_storage_dir}):
            service = ObjectStorageService()
            health = service.health_check()

            assert health["healthy"] is True
            assert health["storage_backend"] == "local"
            assert health["details"]["writable"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
