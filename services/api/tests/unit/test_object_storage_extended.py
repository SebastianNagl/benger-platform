"""
Extended unit tests for services/storage/object_storage.py

Covers uncovered lines including:
- S3/MinIO initialization with boto3 (lines 106-141)
- _ensure_bucket_exists (lines 153-180)
- _configure_bucket_cors (lines 184-203)
- S3 upload_file path (lines 253-310)
- get_upload_url for both local and S3 (lines 345-400)
- get_download_url for S3 with CDN (lines 421-451)
- delete_file for S3 path (lines 466-479)
- list_files for both local and S3 (lines 498-557)
- copy_file for both local and S3 (lines 576-630)
- get_file_info for S3 path (lines 652-684)
- create_multipart_upload (lines 705-740)
- get_multipart_upload_urls (lines 761-788)
- complete_multipart_upload (lines 804-829)
- health_check for S3 path (lines 851-871)
"""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: build an ObjectStorageService with a mocked boto3 S3 client
# ---------------------------------------------------------------------------

def _make_s3_service(mock_s3_client=None, env_overrides=None):
    """Create an ObjectStorageService configured for S3 with a mock boto3 client."""
    if mock_s3_client is None:
        mock_s3_client = MagicMock()
        mock_s3_client.head_bucket.return_value = {}

    env = {
        "STORAGE_BACKEND": "s3",
        "S3_ENDPOINT_URL": "https://s3.example.com",
        "S3_ACCESS_KEY_ID": "test-key",
        "S3_SECRET_ACCESS_KEY": "test-secret",
        "S3_REGION": "us-east-1",
        "S3_BUCKET_NAME": "test-bucket",
        "CDN_ENABLED": "false",
    }
    if env_overrides:
        env.update(env_overrides)

    mock_boto3 = MagicMock()
    mock_config_cls = MagicMock()
    mock_boto3.client.return_value = mock_s3_client

    with patch.dict(os.environ, env, clear=False):
        with patch.dict(
            "services.storage.object_storage.__builtins__"
            if hasattr(__builtins__, "__getitem__")
            else {},
            {},
        ):
            pass
        # Patch the module-level symbols that were set during initial import
        with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
             patch("services.storage.object_storage.boto3", mock_boto3), \
             patch("services.storage.object_storage.Config", mock_config_cls):
            from services.storage.object_storage import ObjectStorageService
            service = ObjectStorageService()

    return service, mock_s3_client


def _make_minio_service(mock_s3_client=None):
    """Create an ObjectStorageService configured for MinIO."""
    if mock_s3_client is None:
        mock_s3_client = MagicMock()
        mock_s3_client.head_bucket.return_value = {}

    env = {
        "STORAGE_BACKEND": "minio",
        "S3_ENDPOINT_URL": "http://minio:9000",
        "S3_ACCESS_KEY_ID": "minio-key",
        "S3_SECRET_ACCESS_KEY": "minio-secret",
        "S3_REGION": "us-east-1",
        "S3_BUCKET_NAME": "minio-bucket",
        "CDN_ENABLED": "false",
    }

    mock_boto3 = MagicMock()
    mock_config_cls = MagicMock()
    mock_boto3.client.return_value = mock_s3_client

    with patch.dict(os.environ, env, clear=False):
        with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
             patch("services.storage.object_storage.boto3", mock_boto3), \
             patch("services.storage.object_storage.Config", mock_config_cls):
            from services.storage.object_storage import ObjectStorageService
            service = ObjectStorageService()

    return service, mock_s3_client


# ===========================================================================
# Initialization tests
# ===========================================================================

class TestS3Initialization:
    """Test S3/MinIO storage initialization (lines 104-141)."""

    def test_s3_init_creates_client_and_checks_bucket(self):
        """Successful S3 init: boto3.client called, head_bucket called."""
        service, mock_client = _make_s3_service()

        assert service.storage_backend == "s3"
        assert service.s3_client is mock_client
        mock_client.head_bucket.assert_called_once_with(Bucket="test-bucket")

    def test_minio_init_uses_path_addressing(self):
        """MinIO uses path-style addressing in Config."""
        mock_client = MagicMock()
        mock_client.head_bucket.return_value = {}

        mock_boto3 = MagicMock()
        mock_config_cls = MagicMock()
        mock_boto3.client.return_value = mock_client

        env = {
            "STORAGE_BACKEND": "minio",
            "S3_ENDPOINT_URL": "http://minio:9000",
            "S3_ACCESS_KEY_ID": "key",
            "S3_SECRET_ACCESS_KEY": "secret",
            "S3_REGION": "us-east-1",
            "S3_BUCKET_NAME": "minio-bucket",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
                 patch("services.storage.object_storage.boto3", mock_boto3), \
                 patch("services.storage.object_storage.Config", mock_config_cls):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

        # Verify Config was called with path addressing for minio
        mock_config_cls.assert_called_once()
        call_kwargs = mock_config_cls.call_args
        assert call_kwargs[1]["s3"]["addressing_style"] == "path"

    def test_s3_init_uses_auto_addressing(self):
        """S3 uses auto addressing style in Config."""
        mock_client = MagicMock()
        mock_client.head_bucket.return_value = {}

        mock_boto3 = MagicMock()
        mock_config_cls = MagicMock()
        mock_boto3.client.return_value = mock_client

        env = {
            "STORAGE_BACKEND": "s3",
            "S3_ENDPOINT_URL": "https://s3.amazonaws.com",
            "S3_ACCESS_KEY_ID": "key",
            "S3_SECRET_ACCESS_KEY": "secret",
            "S3_REGION": "eu-central-1",
            "S3_BUCKET_NAME": "bucket",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
                 patch("services.storage.object_storage.boto3", mock_boto3), \
                 patch("services.storage.object_storage.Config", mock_config_cls):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

        mock_config_cls.assert_called_once()
        call_kwargs = mock_config_cls.call_args
        assert call_kwargs[1]["s3"]["addressing_style"] == "auto"

    def test_s3_init_falls_back_to_local_when_boto3_unavailable(self):
        """If BOTO3_AVAILABLE is False, falls back to local storage."""
        env = {
            "STORAGE_BACKEND": "s3",
            "LOCAL_STORAGE_PATH": "/tmp/test-fallback-storage",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("services.storage.object_storage.BOTO3_AVAILABLE", False):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

        assert service.storage_backend == "local"
        assert service.s3_client is None

    def test_s3_init_falls_back_to_local_on_exception(self):
        """If S3 client creation fails, falls back to local storage."""
        mock_boto3 = MagicMock()
        mock_boto3.client.side_effect = Exception("Connection refused")
        mock_config_cls = MagicMock()

        env = {
            "STORAGE_BACKEND": "s3",
            "S3_ACCESS_KEY_ID": "key",
            "S3_SECRET_ACCESS_KEY": "secret",
            "LOCAL_STORAGE_PATH": "/tmp/test-fallback",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
                 patch("services.storage.object_storage.boto3", mock_boto3), \
                 patch("services.storage.object_storage.Config", mock_config_cls):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

        assert service.storage_backend == "local"


# ===========================================================================
# _ensure_bucket_exists tests (lines 151-180)
# ===========================================================================

class TestEnsureBucketExists:
    """Test _ensure_bucket_exists for bucket creation logic."""

    def test_bucket_already_exists(self):
        """head_bucket succeeds, nothing else happens."""
        service, mock_client = _make_s3_service()
        # head_bucket already called during init
        mock_client.head_bucket.assert_called_once()
        mock_client.create_bucket.assert_not_called()

    def test_bucket_does_not_exist_us_east_1(self):
        """404 from head_bucket creates bucket without LocationConstraint for us-east-1."""
        mock_client = MagicMock()

        # First call (during init) raises 404, triggering creation
        error_response = {"Error": {"Code": "404"}}
        client_error = type("ClientError", (Exception,), {})
        exc = client_error("Bucket not found")
        exc.response = error_response
        mock_client.head_bucket.side_effect = exc

        mock_boto3 = MagicMock()
        mock_config_cls = MagicMock()
        mock_boto3.client.return_value = mock_client

        env = {
            "STORAGE_BACKEND": "s3",
            "S3_ACCESS_KEY_ID": "key",
            "S3_SECRET_ACCESS_KEY": "secret",
            "S3_REGION": "us-east-1",
            "S3_BUCKET_NAME": "new-bucket",
        }

        # Patch ClientError at module level so isinstance check works
        with patch.dict(os.environ, env, clear=False):
            with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
                 patch("services.storage.object_storage.boto3", mock_boto3), \
                 patch("services.storage.object_storage.Config", mock_config_cls), \
                 patch("services.storage.object_storage.ClientError", client_error):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

        mock_client.create_bucket.assert_called_once_with(Bucket="new-bucket")
        mock_client.put_bucket_cors.assert_called_once()

    def test_bucket_does_not_exist_non_us_east_1(self):
        """404 from head_bucket creates bucket with LocationConstraint for eu-central-1."""
        mock_client = MagicMock()

        error_response = {"Error": {"Code": "404"}}
        client_error = type("ClientError", (Exception,), {})
        exc = client_error("Bucket not found")
        exc.response = error_response
        mock_client.head_bucket.side_effect = exc

        mock_boto3 = MagicMock()
        mock_config_cls = MagicMock()
        mock_boto3.client.return_value = mock_client

        env = {
            "STORAGE_BACKEND": "s3",
            "S3_ACCESS_KEY_ID": "key",
            "S3_SECRET_ACCESS_KEY": "secret",
            "S3_REGION": "eu-central-1",
            "S3_BUCKET_NAME": "eu-bucket",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
                 patch("services.storage.object_storage.boto3", mock_boto3), \
                 patch("services.storage.object_storage.Config", mock_config_cls), \
                 patch("services.storage.object_storage.ClientError", client_error):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

        mock_client.create_bucket.assert_called_once_with(
            Bucket="eu-bucket",
            CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
        )

    def test_bucket_create_fails_raises(self):
        """If create_bucket fails, the exception propagates and fallback to local."""
        mock_client = MagicMock()

        error_response = {"Error": {"Code": "404"}}
        client_error = type("ClientError", (Exception,), {})
        exc = client_error("Bucket not found")
        exc.response = error_response
        mock_client.head_bucket.side_effect = exc
        mock_client.create_bucket.side_effect = Exception("Permission denied")

        mock_boto3 = MagicMock()
        mock_config_cls = MagicMock()
        mock_boto3.client.return_value = mock_client

        env = {
            "STORAGE_BACKEND": "s3",
            "S3_ACCESS_KEY_ID": "key",
            "S3_SECRET_ACCESS_KEY": "secret",
            "S3_REGION": "us-east-1",
            "S3_BUCKET_NAME": "fail-bucket",
            "LOCAL_STORAGE_PATH": "/tmp/fallback-test",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
                 patch("services.storage.object_storage.boto3", mock_boto3), \
                 patch("services.storage.object_storage.Config", mock_config_cls), \
                 patch("services.storage.object_storage.ClientError", client_error):
                from services.storage.object_storage import ObjectStorageService
                # The exception in create_bucket causes fallback to local
                service = ObjectStorageService()

        assert service.storage_backend == "local"

    def test_head_bucket_non_404_error_causes_fallback(self):
        """Non-404 error from head_bucket triggers fallback to local."""
        mock_client = MagicMock()

        error_response = {"Error": {"Code": "403"}}
        client_error = type("ClientError", (Exception,), {})
        exc = client_error("Access denied")
        exc.response = error_response
        mock_client.head_bucket.side_effect = exc

        mock_boto3 = MagicMock()
        mock_config_cls = MagicMock()
        mock_boto3.client.return_value = mock_client

        env = {
            "STORAGE_BACKEND": "s3",
            "S3_ACCESS_KEY_ID": "key",
            "S3_SECRET_ACCESS_KEY": "secret",
            "S3_BUCKET_NAME": "forbidden-bucket",
            "LOCAL_STORAGE_PATH": "/tmp/fallback-403",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("services.storage.object_storage.BOTO3_AVAILABLE", True), \
                 patch("services.storage.object_storage.boto3", mock_boto3), \
                 patch("services.storage.object_storage.Config", mock_config_cls), \
                 patch("services.storage.object_storage.ClientError", client_error):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

        # The re-raised exception in _ensure_bucket_exists causes the outer
        # except in _initialize_storage to catch and fall back to local
        assert service.storage_backend == "local"

    def test_ensure_bucket_no_client_returns_early(self):
        """_ensure_bucket_exists returns immediately if s3_client is None."""
        from services.storage.object_storage import ObjectStorageService
        with patch.dict(os.environ, {"STORAGE_BACKEND": "local"}):
            service = ObjectStorageService()
        service.s3_client = None
        # Should not raise
        service._ensure_bucket_exists()


# ===========================================================================
# _configure_bucket_cors tests (lines 182-203)
# ===========================================================================

class TestConfigureBucketCors:
    """Test _configure_bucket_cors."""

    def test_cors_configuration_applied(self):
        """CORS config is applied to the bucket."""
        service, mock_client = _make_s3_service()
        # Reset to test explicitly
        mock_client.put_bucket_cors.reset_mock()

        service._configure_bucket_cors()

        mock_client.put_bucket_cors.assert_called_once()
        call_kwargs = mock_client.put_bucket_cors.call_args
        assert call_kwargs[1]["Bucket"] == "test-bucket"
        cors = call_kwargs[1]["CORSConfiguration"]
        assert "CORSRules" in cors
        assert cors["CORSRules"][0]["AllowedOrigins"] == ["*"]

    def test_cors_no_client_returns_early(self):
        """_configure_bucket_cors returns immediately if s3_client is None."""
        from services.storage.object_storage import ObjectStorageService
        with patch.dict(os.environ, {"STORAGE_BACKEND": "local"}):
            service = ObjectStorageService()
        service.s3_client = None
        # Should not raise
        service._configure_bucket_cors()

    def test_cors_exception_is_logged_not_raised(self):
        """If put_bucket_cors fails, exception is logged but not raised."""
        service, mock_client = _make_s3_service()
        mock_client.put_bucket_cors.side_effect = Exception("CORS error")

        # Should not raise
        service._configure_bucket_cors()


# ===========================================================================
# upload_file S3 path tests (lines 253-310)
# ===========================================================================

class TestUploadFileS3:
    """Test upload_file S3 code path."""

    def test_upload_to_s3_with_explicit_content_type(self):
        """Upload with explicit content_type calls put_object."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed-url"

        result = service.upload_file(
            file_data=b"test data",
            filename="test.pdf",
            file_type="uploads",
            user_id="user1",
            content_type="application/pdf",
        )

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Body"] == b"test data"
        assert call_kwargs["ContentType"] == "application/pdf"
        assert "file_key" in result
        assert result["storage_backend"] == "s3"

    def test_upload_to_s3_auto_detects_content_type(self):
        """Content type is auto-detected when not provided."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        result = service.upload_file(
            file_data=b"<html>test</html>",
            filename="page.html",
            file_type="uploads",
        )

        call_kwargs = mock_client.put_object.call_args[1]
        assert "html" in call_kwargs["ContentType"]

    def test_upload_to_s3_unknown_content_type_defaults_to_octet_stream(self):
        """Unknown file extensions default to application/octet-stream."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        result = service.upload_file(
            file_data=b"binary data",
            filename="data.xyz123",
            file_type="uploads",
        )

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "application/octet-stream"

    def test_upload_to_s3_with_custom_metadata(self):
        """Custom metadata is merged into file_metadata."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        result = service.upload_file(
            file_data=b"data",
            filename="test.txt",
            metadata={"project_id": "proj-123", "custom_key": "custom_val"},
        )

        call_kwargs = mock_client.put_object.call_args[1]
        metadata = call_kwargs["Metadata"]
        assert metadata["project_id"] == "proj-123"
        assert metadata["custom_key"] == "custom_val"
        assert metadata["original_filename"] == "test.txt"

    def test_upload_to_s3_static_with_cdn_uses_cdn_url(self):
        """Static files with CDN enabled use CDN URL."""
        service, mock_client = _make_s3_service(
            env_overrides={"CDN_ENABLED": "true", "CDN_DOMAIN": "cdn.example.com", "CDN_PREFIX": ""}
        )

        result = service.upload_file(
            file_data=b"js content",
            filename="app.js",
            file_type="static",
        )

        assert "cdn.example.com" in result["url"]
        # Should NOT call generate_presigned_url for static CDN files
        mock_client.generate_presigned_url.assert_not_called()

    def test_upload_to_s3_non_static_with_cdn_uses_presigned_url(self):
        """Non-static files with CDN enabled still use presigned URLs."""
        service, mock_client = _make_s3_service(
            env_overrides={"CDN_ENABLED": "true", "CDN_DOMAIN": "cdn.example.com"}
        )
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        result = service.upload_file(
            file_data=b"data",
            filename="export.zip",
            file_type="exports",
        )

        mock_client.generate_presigned_url.assert_called_once()
        assert result["url"] == "https://s3.example.com/presigned"

    def test_upload_to_s3_failure_raises(self):
        """Exception from S3 put_object propagates."""
        service, mock_client = _make_s3_service()
        mock_client.put_object.side_effect = Exception("S3 write failed")

        with pytest.raises(Exception, match="S3 write failed"):
            service.upload_file(file_data=b"data", filename="fail.txt")

    def test_upload_file_hash_is_correct(self):
        """File hash in result matches SHA-256 of file_data."""
        import hashlib
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        data = b"hash verification content"
        result = service.upload_file(file_data=data, filename="hash.txt")

        expected_hash = hashlib.sha256(data).hexdigest()
        assert result["hash"] == expected_hash


# ===========================================================================
# get_upload_url tests (lines 345-400)
# ===========================================================================

class TestGetUploadUrl:
    """Test presigned upload URL generation."""

    def test_local_returns_api_endpoint(self):
        """Local backend returns /api/upload endpoint."""
        from services.storage.object_storage import ObjectStorageService
        with patch.dict(os.environ, {"STORAGE_BACKEND": "local"}):
            service = ObjectStorageService()

        result = service.get_upload_url("test.txt", user_id="user1")

        assert result["upload_url"] == "/api/upload"
        assert result["method"] == "POST"
        assert "file_key" in result

    def test_s3_returns_presigned_post(self):
        """S3 backend returns presigned POST data."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_post.return_value = {
            "url": "https://test-bucket.s3.amazonaws.com",
            "fields": {"key": "uploads/test.txt", "policy": "base64policy"},
        }

        result = service.get_upload_url("test.txt", user_id="user1", content_type="text/plain")

        mock_client.generate_presigned_post.assert_called_once()
        assert result["upload_url"] == "https://test-bucket.s3.amazonaws.com"
        assert result["method"] == "POST"
        assert "file_key" in result
        assert "fields" in result
        assert "expires_at" in result

    def test_s3_auto_detects_content_type(self):
        """S3 presigned post auto-detects content type."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_post.return_value = {
            "url": "https://test-bucket.s3.amazonaws.com",
            "fields": {},
        }

        service.get_upload_url("photo.jpg")

        call_kwargs = mock_client.generate_presigned_post.call_args[1]
        assert "image/jpeg" in call_kwargs["Fields"]["Content-Type"]

    def test_s3_unknown_content_type_defaults_to_octet_stream(self):
        """Unknown content type defaults to application/octet-stream."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_post.return_value = {
            "url": "https://test-bucket.s3.amazonaws.com",
            "fields": {},
        }

        service.get_upload_url("data.xyz999")

        call_kwargs = mock_client.generate_presigned_post.call_args[1]
        assert call_kwargs["Fields"]["Content-Type"] == "application/octet-stream"

    def test_s3_max_size_adds_condition(self):
        """max_size parameter adds content-length-range condition."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_post.return_value = {
            "url": "https://s3.example.com",
            "fields": {},
        }

        service.get_upload_url("test.txt", max_size=10 * 1024 * 1024)

        call_kwargs = mock_client.generate_presigned_post.call_args[1]
        conditions = call_kwargs["Conditions"]
        # Find the content-length-range condition
        length_conditions = [c for c in conditions if isinstance(c, list) and c[0] == "content-length-range"]
        assert len(length_conditions) == 1
        assert length_conditions[0] == ["content-length-range", 0, 10 * 1024 * 1024]

    def test_s3_custom_expires_in(self):
        """Custom expiration is passed through."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_post.return_value = {
            "url": "https://s3.example.com",
            "fields": {},
        }

        service.get_upload_url("test.txt", expires_in=7200)

        call_kwargs = mock_client.generate_presigned_post.call_args[1]
        assert call_kwargs["ExpiresIn"] == 7200

    def test_s3_default_expires_in(self):
        """Default expiration is used when not specified."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_post.return_value = {
            "url": "https://s3.example.com",
            "fields": {},
        }

        service.get_upload_url("test.txt")

        call_kwargs = mock_client.generate_presigned_post.call_args[1]
        assert call_kwargs["ExpiresIn"] == 3600  # default upload expiration

    def test_s3_presigned_post_failure_raises(self):
        """Exception from generate_presigned_post propagates."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_post.side_effect = Exception("AWS error")

        with pytest.raises(Exception, match="AWS error"):
            service.get_upload_url("test.txt")


# ===========================================================================
# get_download_url tests (lines 421-451)
# ===========================================================================

class TestGetDownloadUrl:
    """Test presigned download URL generation."""

    def test_local_returns_file_path(self):
        """Local backend returns file:// URL."""
        from services.storage.object_storage import ObjectStorageService
        with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": "/tmp/test"}):
            service = ObjectStorageService()

        url = service.get_download_url("uploads/test.txt")
        assert url.startswith("file://")
        assert "test.txt" in url

    def test_s3_cdn_static_file_returns_cdn_url(self):
        """Static files with CDN enabled return CDN URL."""
        service, mock_client = _make_s3_service(
            env_overrides={"CDN_ENABLED": "true", "CDN_DOMAIN": "cdn.example.com", "CDN_PREFIX": "assets"}
        )

        url = service.get_download_url("static/js/app.js")

        assert "cdn.example.com" in url
        assert "static/js/app.js" in url
        mock_client.generate_presigned_url.assert_not_called()

    def test_s3_non_static_returns_presigned_url(self):
        """Non-static files return presigned URL even with CDN enabled."""
        service, mock_client = _make_s3_service(
            env_overrides={"CDN_ENABLED": "true", "CDN_DOMAIN": "cdn.example.com"}
        )
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        url = service.get_download_url("uploads/doc.pdf")

        assert url == "https://s3.example.com/presigned"
        mock_client.generate_presigned_url.assert_called_once()

    def test_s3_default_expiration(self):
        """Default download expiration (86400) is used."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        service.get_download_url("uploads/test.txt")

        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == 86400

    def test_s3_custom_expiration(self):
        """Custom expiration is passed through."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        service.get_download_url("uploads/test.txt", expires_in=3600)

        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == 3600

    def test_s3_response_params_passed(self):
        """Response content type and disposition are passed to S3."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        service.get_download_url(
            "uploads/test.txt",
            response_content_type="application/pdf",
            response_content_disposition="attachment; filename=report.pdf",
        )

        call_kwargs = mock_client.generate_presigned_url.call_args
        params = call_kwargs[1]["Params"]
        assert params["ResponseContentType"] == "application/pdf"
        assert params["ResponseContentDisposition"] == "attachment; filename=report.pdf"

    def test_s3_presigned_url_failure_raises(self):
        """Exception from generate_presigned_url propagates."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.side_effect = Exception("Token expired")

        with pytest.raises(Exception, match="Token expired"):
            service.get_download_url("uploads/test.txt")


# ===========================================================================
# delete_file tests (lines 466-479)
# ===========================================================================

class TestDeleteFileS3:
    """Test delete_file S3 code path."""

    def test_s3_delete_success(self):
        """Successful S3 delete returns True."""
        service, mock_client = _make_s3_service()

        result = service.delete_file("uploads/test.txt")

        assert result is True
        mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="uploads/test.txt"
        )

    def test_s3_delete_failure_returns_false(self):
        """S3 delete failure returns False."""
        service, mock_client = _make_s3_service()
        mock_client.delete_object.side_effect = Exception("Access denied")

        result = service.delete_file("uploads/test.txt")

        assert result is False

    def test_local_delete_nonexistent_returns_true(self):
        """Deleting a nonexistent file from local storage returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            result = service.delete_file("nonexistent/file.txt")
            assert result is True

    def test_local_delete_with_metadata(self):
        """Deleting a local file also removes its .metadata.json file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            # Create file + metadata
            file_path = os.path.join(tmpdir, "testfile.txt")
            metadata_path = f"{file_path}.metadata.json"
            with open(file_path, "w") as f:
                f.write("content")
            with open(metadata_path, "w") as f:
                json.dump({"key": "val"}, f)

            assert os.path.exists(file_path)
            assert os.path.exists(metadata_path)

            result = service.delete_file("testfile.txt")

            assert result is True
            assert not os.path.exists(file_path)
            assert not os.path.exists(metadata_path)


# ===========================================================================
# list_files tests (lines 498-557)
# ===========================================================================

class TestListFiles:
    """Test list_files for both local and S3."""

    def test_local_list_files(self):
        """List files from local storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            # Create files
            subdir = os.path.join(tmpdir, "uploads", "2025")
            os.makedirs(subdir, exist_ok=True)
            with open(os.path.join(subdir, "file1.txt"), "w") as f:
                f.write("content1")
            with open(os.path.join(subdir, "file2.txt"), "w") as f:
                f.write("content2")
            # Metadata files should be skipped
            with open(os.path.join(subdir, "file1.txt.metadata.json"), "w") as f:
                f.write("{}")

            files, token = service.list_files("uploads")

            assert len(files) == 2
            assert token is None
            for f in files:
                assert "key" in f
                assert "size" in f
                assert "last_modified" in f
                assert not f["key"].endswith(".metadata.json")

    def test_local_list_files_max_results(self):
        """List files respects max_results limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            # Create many files
            subdir = os.path.join(tmpdir, "many")
            os.makedirs(subdir, exist_ok=True)
            for i in range(10):
                with open(os.path.join(subdir, f"file{i}.txt"), "w") as f:
                    f.write(f"content{i}")

            files, token = service.list_files("many", max_results=3)

            assert len(files) <= 3

    def test_local_list_files_empty_prefix(self):
        """List files with nonexistent prefix returns empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            files, token = service.list_files("nonexistent")
            assert files == []
            assert token is None

    def test_s3_list_files(self):
        """List files from S3."""
        service, mock_client = _make_s3_service()
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "uploads/file1.txt", "Size": 100, "LastModified": datetime(2025, 1, 1)},
                {"Key": "uploads/file2.txt", "Size": 200, "LastModified": datetime(2025, 1, 2)},
            ],
            "NextContinuationToken": "next-token-123",
        }

        files, token = service.list_files("uploads", max_results=100)

        assert len(files) == 2
        assert files[0]["key"] == "uploads/file1.txt"
        assert files[0]["size"] == 100
        assert files[1]["key"] == "uploads/file2.txt"
        assert token == "next-token-123"

        call_kwargs = mock_client.list_objects_v2.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Prefix"] == "uploads"
        assert call_kwargs["MaxKeys"] == 100

    def test_s3_list_files_with_continuation_token(self):
        """List files with continuation token passes it to S3."""
        service, mock_client = _make_s3_service()
        mock_client.list_objects_v2.return_value = {"Contents": []}

        service.list_files("uploads", continuation_token="prev-token")

        call_kwargs = mock_client.list_objects_v2.call_args[1]
        assert call_kwargs["ContinuationToken"] == "prev-token"

    def test_s3_list_files_empty_response(self):
        """S3 response with no Contents returns empty list."""
        service, mock_client = _make_s3_service()
        mock_client.list_objects_v2.return_value = {}

        files, token = service.list_files("empty-prefix")

        assert files == []
        assert token is None

    def test_list_files_exception_returns_empty(self):
        """Exception during listing returns empty list."""
        service, mock_client = _make_s3_service()
        mock_client.list_objects_v2.side_effect = Exception("Network error")

        files, token = service.list_files("uploads")

        assert files == []
        assert token is None


# ===========================================================================
# copy_file tests (lines 576-630)
# ===========================================================================

class TestCopyFile:
    """Test copy_file for both local and S3."""

    def test_local_copy_file_success(self):
        """Copy file in local storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            # Create source file
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(src_dir, exist_ok=True)
            src_path = os.path.join(src_dir, "original.txt")
            with open(src_path, "w") as f:
                f.write("original content")

            result = service.copy_file("src/original.txt", "dst/copy.txt")

            assert result is True
            dst_path = os.path.join(tmpdir, "dst", "copy.txt")
            assert os.path.exists(dst_path)
            with open(dst_path) as f:
                assert f.read() == "original content"

    def test_local_copy_with_metadata(self):
        """Copy file with metadata in local storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            # Create source file with metadata
            src_path = os.path.join(tmpdir, "source.txt")
            with open(src_path, "w") as f:
                f.write("content")
            meta_path = f"{src_path}.metadata.json"
            with open(meta_path, "w") as f:
                json.dump({"original_filename": "source.txt"}, f)

            result = service.copy_file(
                "source.txt", "dest.txt",
                metadata_updates={"copied_at": "2025-01-01"}
            )

            assert result is True
            dest_meta = os.path.join(tmpdir, "dest.txt.metadata.json")
            assert os.path.exists(dest_meta)
            with open(dest_meta) as f:
                metadata = json.load(f)
            assert metadata["original_filename"] == "source.txt"
            assert metadata["copied_at"] == "2025-01-01"

    def test_local_copy_nonexistent_returns_false(self):
        """Copying nonexistent file returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            result = service.copy_file("nonexistent.txt", "dest.txt")
            assert result is False

    def test_s3_copy_file_success(self):
        """Copy file in S3 storage."""
        service, mock_client = _make_s3_service()
        mock_client.head_object.return_value = {
            "Metadata": {"original_filename": "source.txt"},
        }

        result = service.copy_file("source.txt", "dest.txt")

        assert result is True
        mock_client.copy_object.assert_called_once()
        call_kwargs = mock_client.copy_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "dest.txt"
        assert call_kwargs["MetadataDirective"] == "REPLACE"

    def test_s3_copy_with_metadata_updates(self):
        """Copy file in S3 merges metadata updates."""
        service, mock_client = _make_s3_service()
        mock_client.head_object.return_value = {
            "Metadata": {"original_filename": "source.txt"},
        }

        result = service.copy_file(
            "source.txt", "dest.txt",
            metadata_updates={"copied_by": "admin"}
        )

        assert result is True
        call_kwargs = mock_client.copy_object.call_args[1]
        metadata = call_kwargs["Metadata"]
        assert metadata["original_filename"] == "source.txt"
        assert metadata["copied_by"] == "admin"

    def test_s3_copy_failure_returns_false(self):
        """S3 copy failure returns False."""
        service, mock_client = _make_s3_service()
        mock_client.head_object.side_effect = Exception("Not found")

        result = service.copy_file("source.txt", "dest.txt")
        assert result is False


# ===========================================================================
# get_file_info S3 tests (lines 652-684)
# ===========================================================================

class TestGetFileInfoS3:
    """Test get_file_info S3 code path."""

    def test_s3_get_file_info_success(self):
        """Get file info from S3."""
        service, mock_client = _make_s3_service()
        mock_client.head_object.return_value = {
            "ContentLength": 1024,
            "LastModified": datetime(2025, 7, 14),
            "ContentType": "application/pdf",
            "ETag": '"abc123"',
            "Metadata": {"original_filename": "report.pdf"},
        }

        info = service.get_file_info("uploads/report.pdf")

        assert info is not None
        assert info["key"] == "uploads/report.pdf"
        assert info["size"] == 1024
        assert info["content_type"] == "application/pdf"
        assert info["etag"] == '"abc123"'
        assert info["metadata"]["original_filename"] == "report.pdf"

    def test_s3_get_file_info_not_found(self):
        """File not found returns None (ClientError 404)."""
        service, mock_client = _make_s3_service()

        # Create a proper ClientError-like exception
        client_error = type("ClientError", (Exception,), {})
        exc = client_error("Not found")
        exc.response = {"Error": {"Code": "404"}}
        mock_client.head_object.side_effect = exc

        with patch("services.storage.object_storage.ClientError", client_error):
            info = service.get_file_info("nonexistent.txt")

        assert info is None

    def test_s3_get_file_info_other_client_error(self):
        """Non-404 ClientError returns None and logs error."""
        service, mock_client = _make_s3_service()

        client_error = type("ClientError", (Exception,), {})
        exc = client_error("Forbidden")
        exc.response = {"Error": {"Code": "403"}}
        mock_client.head_object.side_effect = exc

        with patch("services.storage.object_storage.ClientError", client_error):
            info = service.get_file_info("forbidden.txt")

        assert info is None

    def test_s3_get_file_info_generic_exception(self):
        """Generic exception returns None."""
        service, mock_client = _make_s3_service()
        # Use an exception type that won't be caught by the ClientError handler
        # In the test env, ClientError is aliased to Exception, so we need to use
        # an exception that has .response to avoid AttributeError in the first handler,
        # OR we patch ClientError to a specific type so our generic Exception falls
        # through to the second except.
        error = Exception("Network error")
        error.response = {"Error": {"Code": "500"}}
        mock_client.head_object.side_effect = error

        # The first except catches ClientError (=Exception), sees code != 404, returns None
        info = service.get_file_info("error.txt")

        assert info is None

    def test_local_get_file_info_not_found(self):
        """Local file not found returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            info = service.get_file_info("nonexistent.txt")
            assert info is None

    def test_local_get_file_info_with_metadata(self):
        """Local file info includes metadata when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            # Create file with metadata
            file_path = os.path.join(tmpdir, "test.txt")
            with open(file_path, "w") as f:
                f.write("content")
            meta_path = f"{file_path}.metadata.json"
            with open(meta_path, "w") as f:
                json.dump({"original_filename": "test.txt", "user_id": "u1"}, f)

            info = service.get_file_info("test.txt")

            assert info is not None
            assert info["key"] == "test.txt"
            assert info["metadata"]["original_filename"] == "test.txt"
            assert info["metadata"]["user_id"] == "u1"


# ===========================================================================
# create_multipart_upload tests (lines 705-740)
# ===========================================================================

class TestCreateMultipartUpload:
    """Test multipart upload initialization."""

    def test_local_returns_local_upload_info(self):
        """Local backend returns local upload info."""
        from services.storage.object_storage import ObjectStorageService
        with patch.dict(os.environ, {"STORAGE_BACKEND": "local"}):
            service = ObjectStorageService()

        result = service.create_multipart_upload("large_file.zip", user_id="user1")

        assert result["upload_id"] == "local-upload"
        assert "file_key" in result
        assert result["part_size"] == 5 * 1024 * 1024

    def test_s3_creates_multipart_upload(self):
        """S3 backend creates multipart upload."""
        service, mock_client = _make_s3_service()
        mock_client.create_multipart_upload.return_value = {"UploadId": "mp-upload-123"}

        result = service.create_multipart_upload(
            "large_file.zip", user_id="user1", content_type="application/zip"
        )

        assert result["upload_id"] == "mp-upload-123"
        assert "file_key" in result
        assert result["part_size"] == 5 * 1024 * 1024
        mock_client.create_multipart_upload.assert_called_once()

    def test_s3_auto_detects_content_type(self):
        """Content type is auto-detected for multipart upload."""
        service, mock_client = _make_s3_service()
        mock_client.create_multipart_upload.return_value = {"UploadId": "mp-123"}

        service.create_multipart_upload("video.mp4")

        call_kwargs = mock_client.create_multipart_upload.call_args[1]
        assert "video" in call_kwargs["ContentType"]

    def test_s3_unknown_content_type_defaults(self):
        """Unknown content type defaults to octet-stream."""
        service, mock_client = _make_s3_service()
        mock_client.create_multipart_upload.return_value = {"UploadId": "mp-123"}

        service.create_multipart_upload("data.xyz999")

        call_kwargs = mock_client.create_multipart_upload.call_args[1]
        assert call_kwargs["ContentType"] == "application/octet-stream"

    def test_s3_multipart_failure_raises(self):
        """Exception from create_multipart_upload propagates."""
        service, mock_client = _make_s3_service()
        mock_client.create_multipart_upload.side_effect = Exception("S3 error")

        with pytest.raises(Exception, match="S3 error"):
            service.create_multipart_upload("fail.zip")


# ===========================================================================
# get_multipart_upload_urls tests (lines 761-788)
# ===========================================================================

class TestGetMultipartUploadUrls:
    """Test multipart upload URL generation."""

    def test_local_returns_api_endpoints(self):
        """Local backend returns /api/upload-part for each part."""
        from services.storage.object_storage import ObjectStorageService
        with patch.dict(os.environ, {"STORAGE_BACKEND": "local"}):
            service = ObjectStorageService()

        urls = service.get_multipart_upload_urls("key", "upload-id", [1, 2, 3])

        assert urls == {1: "/api/upload-part", 2: "/api/upload-part", 3: "/api/upload-part"}

    def test_s3_returns_presigned_urls(self):
        """S3 backend returns presigned URLs for each part."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.side_effect = [
            "https://s3.example.com/part1",
            "https://s3.example.com/part2",
        ]

        urls = service.get_multipart_upload_urls("key", "upload-id", [1, 2])

        assert urls[1] == "https://s3.example.com/part1"
        assert urls[2] == "https://s3.example.com/part2"
        assert mock_client.generate_presigned_url.call_count == 2

    def test_s3_default_expiration(self):
        """Default upload expiration is used."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        service.get_multipart_upload_urls("key", "upload-id", [1])

        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == 3600

    def test_s3_custom_expiration(self):
        """Custom expiration is passed through."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        service.get_multipart_upload_urls("key", "upload-id", [1], expires_in=7200)

        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == 7200

    def test_s3_url_params_correct(self):
        """Presigned URL params include bucket, key, upload ID, and part number."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/signed"

        service.get_multipart_upload_urls("uploads/file.zip", "mp-123", [5])

        call_args = mock_client.generate_presigned_url.call_args
        assert call_args[0][0] == "upload_part"
        params = call_args[1]["Params"]
        assert params["Bucket"] == "test-bucket"
        assert params["Key"] == "uploads/file.zip"
        assert params["UploadId"] == "mp-123"
        assert params["PartNumber"] == 5

    def test_s3_url_generation_failure_raises(self):
        """Exception from generate_presigned_url propagates."""
        service, mock_client = _make_s3_service()
        mock_client.generate_presigned_url.side_effect = Exception("Token error")

        with pytest.raises(Exception, match="Token error"):
            service.get_multipart_upload_urls("key", "upload-id", [1])


# ===========================================================================
# complete_multipart_upload tests (lines 804-829)
# ===========================================================================

class TestCompleteMultipartUpload:
    """Test multipart upload completion."""

    def test_local_returns_minimal_info(self):
        """Local backend returns minimal completion info."""
        from services.storage.object_storage import ObjectStorageService
        with patch.dict(os.environ, {"STORAGE_BACKEND": "local"}):
            service = ObjectStorageService()

        result = service.complete_multipart_upload(
            "uploads/file.zip", "local-upload",
            [{"PartNumber": 1, "ETag": "abc"}]
        )

        assert result["file_key"] == "uploads/file.zip"
        assert result["storage_backend"] == "local"

    def test_s3_completes_upload(self):
        """S3 backend completes multipart upload and fetches file info."""
        service, mock_client = _make_s3_service()
        mock_client.complete_multipart_upload.return_value = {
            "ETag": '"final-etag"',
            "Location": "https://test-bucket.s3.amazonaws.com/uploads/file.zip",
        }
        mock_client.head_object.return_value = {
            "ContentLength": 50000,
            "LastModified": datetime(2025, 7, 14),
            "ContentType": "application/zip",
            "ETag": '"final-etag"',
            "Metadata": {},
        }

        parts = [
            {"PartNumber": 1, "ETag": '"part1"'},
            {"PartNumber": 2, "ETag": '"part2"'},
        ]
        result = service.complete_multipart_upload("uploads/file.zip", "mp-123", parts)

        assert result["file_key"] == "uploads/file.zip"
        assert result["etag"] == '"final-etag"'
        assert result["storage_backend"] == "s3"
        mock_client.complete_multipart_upload.assert_called_once_with(
            Bucket="test-bucket",
            Key="uploads/file.zip",
            UploadId="mp-123",
            MultipartUpload={"Parts": parts},
        )

    def test_s3_complete_failure_raises(self):
        """Exception from complete_multipart_upload propagates."""
        service, mock_client = _make_s3_service()
        mock_client.complete_multipart_upload.side_effect = Exception("Invalid upload ID")

        with pytest.raises(Exception, match="Invalid upload ID"):
            service.complete_multipart_upload("key", "bad-id", [])


# ===========================================================================
# health_check tests (lines 851-871)
# ===========================================================================

class TestHealthCheckS3:
    """Test health_check for S3 backend."""

    def test_s3_healthy(self):
        """Healthy S3 backend returns correct status."""
        service, mock_client = _make_s3_service()
        # Reset head_bucket to return normally for health check
        mock_client.head_bucket.reset_mock()
        mock_client.head_bucket.return_value = {}

        health = service.health_check()

        assert health["healthy"] is True
        assert health["storage_backend"] == "s3"
        assert health["details"]["bucket"] == "test-bucket"
        assert health["details"]["endpoint"] == "https://s3.example.com"

    def test_s3_healthy_without_endpoint_shows_aws(self):
        """S3 without endpoint_url shows 'AWS S3'."""
        service, mock_client = _make_s3_service()
        service.endpoint_url = None
        mock_client.head_bucket.reset_mock()
        mock_client.head_bucket.return_value = {}

        health = service.health_check()

        assert health["healthy"] is True
        assert health["details"]["endpoint"] == "AWS S3"

    def test_s3_healthy_with_cdn(self):
        """Health check includes CDN details when enabled."""
        service, mock_client = _make_s3_service(
            env_overrides={"CDN_ENABLED": "true", "CDN_DOMAIN": "cdn.example.com"}
        )
        mock_client.head_bucket.reset_mock()
        mock_client.head_bucket.return_value = {}

        health = service.health_check()

        assert health["healthy"] is True
        assert health["details"]["cdn_enabled"] is True
        assert health["details"]["cdn_domain"] == "cdn.example.com"

    def test_s3_unhealthy_on_exception(self):
        """S3 connectivity failure returns unhealthy."""
        service, mock_client = _make_s3_service()
        mock_client.head_bucket.reset_mock()
        mock_client.head_bucket.side_effect = Exception("Connection timeout")

        health = service.health_check()

        assert health["healthy"] is False
        assert "error" in health
        assert "Connection timeout" in health["error"]
        assert health["details"]["error_type"] == "Exception"


# ===========================================================================
# upload_file local path: content type edge cases (lines 253-256)
# ===========================================================================

class TestUploadFileLocalContentType:
    """Test content type detection in local upload path."""

    def test_local_upload_auto_detect_content_type(self):
        """Auto-detect content type for local upload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            result = service.upload_file(b"data", "photo.png")
            assert result["content_type"] == "image/png"

    def test_local_upload_unknown_content_type_defaults(self):
        """Unknown extension defaults to application/octet-stream."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            result = service.upload_file(b"data", "file.xyz999")
            assert result["content_type"] == "application/octet-stream"

    def test_local_upload_with_metadata(self):
        """Custom metadata is merged in local upload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": tmpdir}):
                from services.storage.object_storage import ObjectStorageService
                service = ObjectStorageService()

            result = service.upload_file(
                b"data", "test.txt",
                metadata={"custom_key": "custom_val"},
            )

            # Verify metadata was written to disk
            meta_path = os.path.join(tmpdir, result["file_key"]) + ".metadata.json"
            assert os.path.exists(meta_path)
            with open(meta_path) as f:
                metadata = json.load(f)
            assert metadata["custom_key"] == "custom_val"
            assert metadata["original_filename"] == "test.txt"
