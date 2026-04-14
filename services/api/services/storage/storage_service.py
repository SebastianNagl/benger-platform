"""
Object Storage Service for BenGER

This module provides abstraction for object storage operations,
supporting multiple backends like AWS S3, MinIO, or local filesystem.
"""

import hashlib
import io
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, BinaryIO, Dict, Optional, Union

# boto3 imports moved to S3StorageBackend to avoid system-level import issues
# Assume boto3 is available, and let S3StorageBackend handle import errors gracefully
BOTO3_AVAILABLE = True
import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends"""

    @abstractmethod
    async def upload_file(
        self,
        file_data: Union[bytes, BinaryIO],
        key: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload a file to storage"""

    @abstractmethod
    async def download_file(self, key: str) -> bytes:
        """Download a file from storage"""

    @abstractmethod
    async def delete_file(self, key: str) -> bool:
        """Delete a file from storage"""

    @abstractmethod
    async def generate_presigned_url(
        self, key: str, expires_in: int = 3600, method: str = "GET"
    ) -> str:
        """Generate a presigned URL for direct access"""

    @abstractmethod
    async def file_exists(self, key: str) -> bool:
        """Check if a file exists"""


class S3StorageBackend(StorageBackend):
    """AWS S3 compatible storage backend (works with S3, MinIO, etc.)"""

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1",
        use_ssl: bool = True,
    ):
        # Import boto3 locally to avoid module-level import issues
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise ImportError("boto3 is required for S3 storage backend but is not available")

        self.bucket_name = bucket_name

        # Configure S3 client
        config = Config(
            region_name=region,
            signature_version="s3v4",
            retries={"max_attempts": 10, "mode": "standard"},
        )

        client_kwargs = {"config": config, "use_ssl": use_ssl}

        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key

        self.s3_client = boto3.client("s3", **client_kwargs)

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        from botocore.exceptions import ClientError

        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created bucket: {self.bucket_name}")
                except Exception as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    raise

    async def upload_file(
        self,
        file_data: Union[bytes, BinaryIO],
        key: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload file to S3"""
        try:
            # Convert bytes to file-like object if needed
            if isinstance(file_data, bytes):
                file_data = io.BytesIO(file_data)

            # Detect content type
            content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"

            # Prepare upload parameters
            upload_kwargs = {
                "Bucket": self.bucket_name,
                "Key": key,
                "Body": file_data,
                "ContentType": content_type,
            }

            if metadata:
                upload_kwargs["Metadata"] = metadata

            # Upload file
            self.s3_client.upload_fileobj(**upload_kwargs)

            logger.info(f"Uploaded file to S3: {key}")
            return key

        except Exception as e:
            logger.error(f"Failed to upload file to S3: {e}")
            raise

    async def download_file(self, key: str) -> bytes:
        """Download file from S3"""
        from botocore.exceptions import ClientError

        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {key}")
            raise

    async def delete_file(self, key: str) -> bool:
        """Delete file from S3"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Deleted file from S3: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file from S3: {e}")
            return False

    async def generate_presigned_url(
        self, key: str, expires_in: int = 3600, method: str = "GET"
    ) -> str:
        """Generate presigned URL for S3 object"""
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object" if method == "GET" else "put_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    async def file_exists(self, key: str) -> bool:
        """Check if file exists in S3"""
        from botocore.exceptions import ClientError

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend (for development)"""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, key: str) -> Path:
        """Get full filesystem path for a key"""
        # Ensure key doesn't escape base path
        safe_key = key.lstrip("/")
        full_path = self.base_path / safe_key

        # Ensure the path is within base_path
        try:
            full_path.resolve().relative_to(self.base_path.resolve())
        except ValueError:
            raise ValueError(f"Invalid key: {key}")

        return full_path

    async def upload_file(
        self,
        file_data: Union[bytes, BinaryIO],
        key: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Save file to local filesystem"""
        try:
            full_path = self._get_full_path(key)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(file_data, bytes):
                full_path.write_bytes(file_data)
            else:
                full_path.write_bytes(file_data.read())

            # Store metadata as .meta file
            if metadata:
                meta_path = full_path.with_suffix(full_path.suffix + ".meta")
                import json

                meta_path.write_text(json.dumps(metadata))

            logger.info(f"Saved file locally: {full_path}")
            return key

        except Exception as e:
            logger.error(f"Failed to save file locally: {e}")
            raise

    async def download_file(self, key: str) -> bytes:
        """Read file from local filesystem"""
        full_path = self._get_full_path(key)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        return full_path.read_bytes()

    async def delete_file(self, key: str) -> bool:
        """Delete file from local filesystem"""
        try:
            full_path = self._get_full_path(key)
            if full_path.exists():
                full_path.unlink()

                # Delete metadata file if exists
                meta_path = full_path.with_suffix(full_path.suffix + ".meta")
                if meta_path.exists():
                    meta_path.unlink()

                logger.info(f"Deleted file locally: {full_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file locally: {e}")
            return False

    async def generate_presigned_url(
        self, key: str, expires_in: int = 3600, method: str = "GET"
    ) -> str:
        """Generate URL for local file access"""
        # For local storage, return a file:// URL or implement a serving endpoint
        full_path = self._get_full_path(key)
        return f"file://{full_path.absolute()}"

    async def file_exists(self, key: str) -> bool:
        """Check if file exists locally"""
        return self._get_full_path(key).exists()


class StorageService:
    """Main storage service that manages different backends"""

    def __init__(self, backend: StorageBackend):
        self.backend = backend

    async def upload_file(
        self,
        file_data: Union[bytes, BinaryIO],
        filename: str,
        user_id: str,
        file_type: str = "upload",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file with proper organization

        Returns dict with:
        - key: Storage key
        - url: Access URL (presigned if using S3)
        - size: File size
        - hash: File hash
        """
        # Generate storage key with organization
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        key = f"{file_type}/{user_id}/{timestamp}_{safe_filename}"

        # Calculate file hash
        if isinstance(file_data, bytes):
            file_hash = hashlib.sha256(file_data).hexdigest()
            file_size = len(file_data)
        else:
            # Read file to calculate hash
            content = file_data.read()
            file_hash = hashlib.sha256(content).hexdigest()
            file_size = len(content)
            file_data.seek(0)  # Reset file pointer

        # Prepare metadata
        if metadata is None:
            metadata = {}
        metadata.update(
            {
                "user_id": user_id,
                "original_filename": filename,
                "upload_timestamp": timestamp,
                "file_hash": file_hash,
            }
        )

        # Upload file
        await self.backend.upload_file(file_data, key, metadata)

        # Generate access URL
        url = await self.backend.generate_presigned_url(key, expires_in=86400)  # 24 hours

        return {
            "key": key,
            "url": url,
            "size": file_size,
            "hash": file_hash,
            "filename": filename,
        }

    async def get_file_url(self, key: str, expires_in: int = 3600) -> str:
        """Get presigned URL for file access"""
        return await self.backend.generate_presigned_url(key, expires_in)

    async def delete_file(self, key: str) -> bool:
        """Delete a file from storage"""
        return await self.backend.delete_file(key)

    async def download_file(self, key: str) -> bytes:
        """Download file content"""
        return await self.backend.download_file(key)


# Factory function to create storage service based on configuration
def create_storage_service(storage_type: str = "local", **kwargs) -> StorageService:
    """
    Create storage service instance

    Args:
        storage_type: "s3", "minio", or "local"
        **kwargs: Backend-specific configuration
    """
    if storage_type in ["s3", "minio"]:
        backend = S3StorageBackend(**kwargs)
    elif storage_type == "local":
        backend = LocalStorageBackend(**kwargs)
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")

    return StorageService(backend)
