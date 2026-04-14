"""
Tests for object storage service implementation
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, Mock, patch

import pytest

# Mock boto3 and botocore to avoid OpenSSL dependency issues during test collection
# Need to mock all submodules that S3StorageBackend imports


# Create a proper ClientError mock that behaves like botocore's ClientError
class MockClientError(Exception):
    """Mock of botocore.exceptions.ClientError with response attribute"""

    def __init__(self, error_response, operation_name):
        self.response = error_response
        self.operation_name = operation_name
        super().__init__(str(error_response))


if "boto3" not in sys.modules:
    mock_botocore = MagicMock()
    mock_botocore.config = MagicMock()
    mock_botocore.config.Config = MagicMock()
    mock_botocore.exceptions = MagicMock()
    mock_botocore.exceptions.ClientError = MockClientError

    sys.modules["boto3"] = MagicMock()
    sys.modules["botocore"] = mock_botocore
    sys.modules["botocore.config"] = mock_botocore.config
    sys.modules["botocore.exceptions"] = mock_botocore.exceptions

try:
    import boto3
    from botocore.exceptions import ClientError
except Exception:
    # Fallback mocks if import still fails
    boto3 = MagicMock()
    ClientError = MockClientError

from storage_service import (
    LocalStorageBackend,
    S3StorageBackend,
    StorageBackend,
    StorageService,
    create_storage_service,
)


@pytest.mark.asyncio
class TestLocalStorageBackend:
    """Test local filesystem storage backend"""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def local_backend(self, temp_dir):
        return LocalStorageBackend(temp_dir)

    async def test_upload_file_bytes(self, local_backend):
        """Test uploading file as bytes"""
        content = b"test file content"
        key = "test/file.txt"

        result = await local_backend.upload_file(content, key)

        assert result == key
        assert os.path.exists(os.path.join(local_backend.base_path, key))

    async def test_download_file(self, local_backend):
        """Test downloading file"""
        content = b"test file content"
        key = "test/file.txt"

        await local_backend.upload_file(content, key)
        downloaded = await local_backend.download_file(key)

        assert downloaded == content

    async def test_delete_file(self, local_backend):
        """Test deleting file"""
        content = b"test file content"
        key = "test/file.txt"

        await local_backend.upload_file(content, key)
        assert await local_backend.file_exists(key)

        deleted = await local_backend.delete_file(key)
        assert deleted is True
        assert not await local_backend.file_exists(key)

    async def test_file_exists(self, local_backend):
        """Test checking if file exists"""
        content = b"test file content"
        key = "test/file.txt"

        assert not await local_backend.file_exists(key)

        await local_backend.upload_file(content, key)
        assert await local_backend.file_exists(key)

    async def test_metadata_storage(self, local_backend):
        """Test storing metadata with file"""
        content = b"test file content"
        key = "test/file.txt"
        metadata = {"user": "test", "type": "document"}

        await local_backend.upload_file(content, key, metadata)

        # Check metadata file exists
        meta_path = os.path.join(local_backend.base_path, key + ".meta")
        assert os.path.exists(meta_path)

    async def test_path_traversal_protection(self, local_backend):
        """Test protection against path traversal attacks"""
        content = b"test file content"

        # Try to escape base directory
        with pytest.raises(ValueError):
            await local_backend.upload_file(content, "../../../etc/passwd")


@pytest.mark.asyncio
class TestS3StorageBackend:
    """Test S3 storage backend - tests S3StorageBackend methods using mock S3 client"""

    @pytest.fixture
    def mock_s3_client(self):
        return MagicMock()

    @pytest.fixture
    def s3_backend(self, mock_s3_client):
        # Create backend instance by mocking the __init__ entirely
        # This avoids boto3 import issues while allowing method testing
        backend = object.__new__(S3StorageBackend)
        backend.bucket_name = "test-bucket"
        backend.s3_client = mock_s3_client
        return backend

    async def test_upload_file_success(self, s3_backend, mock_s3_client):
        """Test successful file upload to S3"""
        content = b"test file content"
        key = "test/file.txt"

        mock_s3_client.upload_fileobj.return_value = None

        result = await s3_backend.upload_file(content, key)

        assert result == key
        mock_s3_client.upload_fileobj.assert_called_once()

    async def test_download_file_success(self, s3_backend, mock_s3_client):
        """Test successful file download from S3"""
        content = b"test file content"
        key = "test/file.txt"

        mock_response = {"Body": MagicMock()}
        mock_response["Body"].read.return_value = content
        mock_s3_client.get_object.return_value = mock_response

        downloaded = await s3_backend.download_file(key)

        assert downloaded == content
        mock_s3_client.get_object.assert_called_with(Bucket="test-bucket", Key=key)

    async def test_download_file_not_found(self, s3_backend, mock_s3_client):
        """Test downloading non-existent file"""
        key = "test/nonexistent.txt"

        error = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        mock_s3_client.get_object.side_effect = error

        with pytest.raises(FileNotFoundError):
            await s3_backend.download_file(key)

    async def test_generate_presigned_url(self, s3_backend, mock_s3_client):
        """Test generating presigned URL"""
        key = "test/file.txt"
        expected_url = "https://test-bucket.s3.amazonaws.com/test/file.txt?signature=xyz"

        mock_s3_client.generate_presigned_url.return_value = expected_url

        url = await s3_backend.generate_presigned_url(key)

        assert url == expected_url
        mock_s3_client.generate_presigned_url.assert_called_with(
            "get_object", Params={"Bucket": "test-bucket", "Key": key}, ExpiresIn=3600
        )

    async def test_file_exists_true(self, s3_backend, mock_s3_client):
        """Test file exists check - file present"""
        key = "test/file.txt"

        mock_s3_client.head_object.return_value = {"ContentLength": 100}

        exists = await s3_backend.file_exists(key)

        assert exists is True
        mock_s3_client.head_object.assert_called_with(Bucket="test-bucket", Key=key)

    async def test_file_exists_false(self, s3_backend, mock_s3_client):
        """Test file exists check - file not present"""
        key = "test/nonexistent.txt"

        error = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        mock_s3_client.head_object.side_effect = error

        exists = await s3_backend.file_exists(key)

        assert exists is False


@pytest.mark.asyncio
class TestStorageService:
    """Test main storage service"""

    @pytest.fixture
    def mock_backend(self):
        from unittest.mock import AsyncMock

        backend = Mock(spec=StorageBackend)
        backend.upload_file = AsyncMock(return_value=None)
        backend.generate_presigned_url = AsyncMock(return_value="https://example.com/file")
        return backend

    @pytest.fixture
    def storage_service(self, mock_backend):
        return StorageService(mock_backend)

    async def test_upload_file_with_organization(self, storage_service, mock_backend):
        """Test file upload with proper organization"""
        content = b"test file content"
        filename = "document.pdf"
        user_id = "user123"

        result = await storage_service.upload_file(
            file_data=content, filename=filename, user_id=user_id, file_type="upload"
        )

        assert result["filename"] == filename
        assert result["size"] == len(content)
        assert result["hash"] is not None
        assert result["url"] == "https://example.com/file"
        assert user_id in result["key"]

        # Verify backend was called
        mock_backend.upload_file.assert_called_once()
        mock_backend.generate_presigned_url.assert_called_once()

    async def test_upload_file_with_metadata(self, storage_service, mock_backend):
        """Test file upload with custom metadata"""
        content = b"test file content"
        filename = "document.pdf"
        user_id = "user123"
        custom_metadata = {"task_id": "task456", "version": "1.0"}

        result = await storage_service.upload_file(
            file_data=content,
            filename=filename,
            user_id=user_id,
            file_type="upload",
            metadata=custom_metadata,
        )

        # Check that metadata was passed to backend
        # StorageService.upload_file calls backend.upload_file(file_data, key, metadata)
        # So metadata is the third positional argument
        call_args = mock_backend.upload_file.call_args
        # call_args is a tuple: (positional_args, keyword_args)
        # upload_file is called as: self.backend.upload_file(file_data, key, metadata)
        metadata = call_args[0][2]  # Third positional argument

        assert metadata["task_id"] == "task456"
        assert metadata["version"] == "1.0"
        assert metadata["user_id"] == user_id
        assert metadata["original_filename"] == filename

    async def test_get_file_url(self, storage_service, mock_backend):
        """Test getting presigned URL for file"""
        key = "uploads/user123/file.pdf"
        expected_url = "https://example.com/signed-url"

        mock_backend.generate_presigned_url.return_value = expected_url

        url = await storage_service.get_file_url(key, expires_in=7200)

        assert url == expected_url
        mock_backend.generate_presigned_url.assert_called_with(key, 7200)

    async def test_delete_file(self, storage_service, mock_backend):
        """Test deleting file"""
        from unittest.mock import AsyncMock

        key = "uploads/user123/file.pdf"

        mock_backend.delete_file = AsyncMock(return_value=True)

        result = await storage_service.delete_file(key)

        assert result is True
        mock_backend.delete_file.assert_called_with(key)


class TestStorageFactory:
    """Test storage service factory"""

    def test_create_local_storage(self):
        """Test creating local storage service"""
        service = create_storage_service(storage_type="local", base_path="/tmp/test")

        assert isinstance(service, StorageService)
        assert isinstance(service.backend, LocalStorageBackend)

    def test_create_s3_storage(self):
        """Test creating S3 storage service"""
        # Need to mock the entire boto3 and botocore imports that happen inside S3StorageBackend.__init__
        mock_s3_client = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3_client
        mock_s3_client.head_bucket.return_value = None  # Bucket exists

        mock_botocore_config = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "boto3": mock_boto3,
                "botocore": MagicMock(),
                "botocore.config": mock_botocore_config,
                "botocore.exceptions": MagicMock(),
            },
        ):
            # Need to reimport to pick up mocked modules
            import importlib

            import storage_service as ss

            importlib.reload(ss)

            service = ss.create_storage_service(
                storage_type="s3",
                bucket_name="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            assert isinstance(service, ss.StorageService)
            assert isinstance(service.backend, ss.S3StorageBackend)

    def test_create_invalid_storage_type(self):
        """Test creating service with invalid type"""
        with pytest.raises(ValueError):
            create_storage_service(storage_type="invalid")
