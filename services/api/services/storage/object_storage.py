"""
Object Storage Service for BenGER

Provides S3-compatible object storage functionality for:
- User file uploads
- Generated exports
- Static assets
- Backups

Supports multiple backends:
- AWS S3
- MinIO (self-hosted)
- Local filesystem (development)

Features:
- Presigned URLs for secure direct uploads/downloads
- Automatic file organization by type and date
- CDN integration for static assets
- Access control and security
- File lifecycle management
"""

import hashlib
import json
import logging
import mimetypes
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except Exception as e:
    # Boto3 not available, only local storage will work
    boto3 = None
    Config = None
    ClientError = Exception
    NoCredentialsError = Exception
    BOTO3_AVAILABLE = False
    print(f"Warning: Boto3 not available: {e}. Only local storage will be supported.")

logger = logging.getLogger(__name__)


class ObjectStorageService:
    """
    S3-compatible object storage service for BenGER.

    Handles all file storage operations including uploads, downloads,
    and CDN integration for static assets.
    """

    def __init__(self):
        """Initialize object storage service with configuration from environment"""
        # Storage backend configuration
        self.storage_backend = os.getenv("STORAGE_BACKEND", "local")  # 's3', 'minio', 'local'

        # S3/MinIO configuration
        self.endpoint_url = os.getenv("S3_ENDPOINT_URL")  # For MinIO or S3-compatible
        self.access_key = os.getenv("S3_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID"))
        self.secret_key = os.getenv("S3_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY"))
        self.region = os.getenv("S3_REGION", os.getenv("AWS_REGION", "us-east-1"))
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "benger-storage")

        # CDN configuration
        self.cdn_enabled = os.getenv("CDN_ENABLED", "false").lower() == "true"
        self.cdn_domain = os.getenv("CDN_DOMAIN")  # e.g., "cdn.benger.example.com"
        self.cdn_prefix = os.getenv("CDN_PREFIX", "")  # Optional path prefix

        # Local storage configuration (fallback)
        self.local_storage_path = os.getenv("LOCAL_STORAGE_PATH", "/tmp/benger-storage")

        # Initialize storage client
        self.s3_client = None
        self._initialize_storage()

        # File organization prefixes
        self.PREFIXES = {
            "uploads": "uploads/{year}/{month}/{day}",
            "exports": "exports/{year}/{month}",
            "static": "static/assets",
            "temp": "temp",
            "backups": "backups/{year}/{month}",
        }

        # Presigned URL expiration times (in seconds)
        self.EXPIRATION_TIMES = {
            "upload": 3600,  # 1 hour for uploads
            "download": 86400,  # 24 hours for downloads
            "public": 604800,  # 7 days for public files
        }

    def _initialize_storage(self):
        """Initialize storage backend based on configuration"""
        if self.storage_backend == "local":
            # Create local storage directory if it doesn't exist
            os.makedirs(self.local_storage_path, exist_ok=True)
            logger.info(f"Using local filesystem storage at: {self.local_storage_path}")

        elif self.storage_backend in ["s3", "minio"]:
            # Initialize S3 client
            if not BOTO3_AVAILABLE:
                logger.error(f"Boto3 not available, cannot use {self.storage_backend} storage")
                # Fall back to local storage
                self.storage_backend = "local"
                self._initialize_storage()
                return

            try:
                config = Config(
                    signature_version="s3v4",
                    s3={
                        "addressing_style": ("path" if self.storage_backend == "minio" else "auto")
                    },
                )

                self.s3_client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region,
                    config=config,
                )

                # Create bucket if it doesn't exist
                self._ensure_bucket_exists()

                logger.info(
                    f"Initialized {self.storage_backend} storage with bucket: {self.bucket_name}"
                )

            except Exception as e:
                logger.error(f"Failed to initialize {self.storage_backend} storage: {e}")
                # Fall back to local storage
                self.storage_backend = "local"
                self._initialize_storage()

        else:
            # Invalid storage backend, fall back to local
            logger.warning(
                f"Invalid storage backend '{self.storage_backend}', falling back to local storage"
            )
            self.storage_backend = "local"
            self._initialize_storage()

    def _ensure_bucket_exists(self):
        """Ensure the S3 bucket exists, create if not"""
        if not self.s3_client:
            return

        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                # Bucket doesn't exist, create it
                try:
                    if self.region == "us-east-1":
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": self.region},
                        )
                    logger.info(f"Created bucket: {self.bucket_name}")

                    # Set bucket CORS for direct uploads
                    self._configure_bucket_cors()

                except Exception as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    raise
            else:
                logger.error(f"Error checking bucket: {e}")
                raise

    def _configure_bucket_cors(self):
        """Configure CORS for the S3 bucket to allow direct browser uploads"""
        if not self.s3_client:
            return

        cors_config = {
            "CORSRules": [
                {
                    "AllowedOrigins": ["*"],  # Configure based on your domains
                    "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
                    "AllowedHeaders": ["*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3600,
                }
            ]
        }

        try:
            self.s3_client.put_bucket_cors(Bucket=self.bucket_name, CORSConfiguration=cors_config)
            logger.info("Configured bucket CORS policy")
        except Exception as e:
            logger.error(f"Failed to configure bucket CORS: {e}")

    def _get_file_key(self, file_type: str, filename: str, user_id: Optional[str] = None) -> str:
        """Generate organized file key based on type and date"""
        now = datetime.now()

        # Get prefix template
        prefix_template = self.PREFIXES.get(file_type, "misc/{year}/{month}")
        prefix = prefix_template.format(
            year=now.year, month=str(now.month).zfill(2), day=str(now.day).zfill(2)
        )

        # Add user ID if provided
        if user_id:
            prefix = f"{prefix}/{user_id}"

        # Generate unique filename with timestamp
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        name, ext = os.path.splitext(filename)
        unique_filename = f"{timestamp}_{name}{ext}"

        return f"{prefix}/{unique_filename}"

    def upload_file(
        self,
        file_data: bytes,
        filename: str,
        file_type: str = "uploads",
        user_id: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to object storage

        Args:
            file_data: File content as bytes
            filename: Original filename
            file_type: Type of file (uploads, exports, static, etc.)
            user_id: User ID for organization
            content_type: MIME type of the file
            metadata: Additional metadata to store with the file

        Returns:
            Dict with file_key, url, size, and other metadata
        """
        # Generate file key
        file_key = self._get_file_key(file_type, filename, user_id)

        # Detect content type if not provided
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

        # Calculate file hash
        file_hash = hashlib.sha256(file_data).hexdigest()

        # Prepare metadata
        file_metadata = {
            "original_filename": filename,
            "user_id": user_id or "",
            "upload_timestamp": datetime.now().isoformat(),
            "file_hash": file_hash,
            "file_size": str(len(file_data)),
        }
        if metadata:
            file_metadata.update(metadata)

        if self.storage_backend == "local":
            # Local filesystem storage
            file_path = os.path.join(self.local_storage_path, file_key)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "wb") as f:
                f.write(file_data)

            # Store metadata
            metadata_path = f"{file_path}.metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(file_metadata, f)

            file_url = f"file://{file_path}"

        else:
            # S3/MinIO storage
            try:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=file_key,
                    Body=file_data,
                    ContentType=content_type,
                    Metadata=file_metadata,
                )

                # Generate URL
                if self.cdn_enabled and file_type == "static":
                    file_url = f"https://{self.cdn_domain}/{self.cdn_prefix}/{file_key}".replace(
                        "//", "/"
                    )
                else:
                    file_url = self.get_download_url(
                        file_key, expires_in=self.EXPIRATION_TIMES["download"]
                    )

            except Exception as e:
                logger.error(f"Failed to upload file to S3: {e}")
                raise

        return {
            "file_key": file_key,
            "url": file_url,
            "size": len(file_data),
            "content_type": content_type,
            "hash": file_hash,
            "storage_backend": self.storage_backend,
            "uploaded_at": datetime.now().isoformat(),
        }

    def get_upload_url(
        self,
        filename: str,
        file_type: str = "uploads",
        user_id: Optional[str] = None,
        content_type: Optional[str] = None,
        max_size: Optional[int] = None,
        expires_in: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for direct file upload from browser

        Args:
            filename: Original filename
            file_type: Type of file
            user_id: User ID for organization
            content_type: MIME type of the file
            max_size: Maximum allowed file size in bytes
            expires_in: URL expiration time in seconds

        Returns:
            Dict with upload_url, file_key, and form fields for upload
        """
        if self.storage_backend == "local":
            # For local storage, return an API endpoint
            return {
                "upload_url": "/api/upload",  # Handle via regular API
                "method": "POST",
                "file_key": self._get_file_key(file_type, filename, user_id),
            }

        # Generate file key
        file_key = self._get_file_key(file_type, filename, user_id)

        # Detect content type if not provided
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

        # Set expiration
        if not expires_in:
            expires_in = self.EXPIRATION_TIMES["upload"]

        # Prepare conditions for the presigned POST
        conditions = [
            {"bucket": self.bucket_name},
            ["starts-with", "$key", os.path.dirname(file_key)],
            {"Content-Type": content_type},
        ]

        if max_size:
            conditions.append(["content-length-range", 0, max_size])

        # Generate presigned POST URL
        try:
            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=file_key,
                Fields={
                    "Content-Type": content_type,
                    "x-amz-meta-original-filename": filename,
                    "x-amz-meta-user-id": user_id or "",
                },
                Conditions=conditions,
                ExpiresIn=expires_in,
            )

            return {
                "upload_url": response["url"],
                "method": "POST",
                "file_key": file_key,
                "fields": response["fields"],
                "expires_at": (datetime.now() + timedelta(seconds=expires_in)).isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to generate presigned upload URL: {e}")
            raise

    def get_download_url(
        self,
        file_key: str,
        expires_in: Optional[int] = None,
        response_content_type: Optional[str] = None,
        response_content_disposition: Optional[str] = None,
    ) -> str:
        """
        Generate a presigned URL for file download

        Args:
            file_key: The S3 key of the file
            expires_in: URL expiration time in seconds
            response_content_type: Override content type for download
            response_content_disposition: Set content disposition (e.g., for forced download)

        Returns:
            Presigned download URL
        """
        if self.storage_backend == "local":
            # For local storage, return file path
            file_path = os.path.join(self.local_storage_path, file_key)
            return f"file://{file_path}"

        # Check if file should be served via CDN
        if self.cdn_enabled and file_key.startswith("static/"):
            return f"https://{self.cdn_domain}/{self.cdn_prefix}/{file_key}".replace("//", "/")

        # Set expiration
        if not expires_in:
            expires_in = self.EXPIRATION_TIMES["download"]

        # Prepare response parameters
        params = {}
        if response_content_type:
            params["ResponseContentType"] = response_content_type
        if response_content_disposition:
            params["ResponseContentDisposition"] = response_content_disposition

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_key, **params},
                ExpiresIn=expires_in,
            )
            return url

        except Exception as e:
            logger.error(f"Failed to generate presigned download URL: {e}")
            raise

    def delete_file(self, file_key: str) -> bool:
        """
        Delete a file from storage

        Args:
            file_key: The storage key of the file

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.storage_backend == "local":
                file_path = os.path.join(self.local_storage_path, file_key)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    # Remove metadata file if exists
                    metadata_path = f"{file_path}.metadata.json"
                    if os.path.exists(metadata_path):
                        os.remove(metadata_path)
                return True
            else:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
                return True

        except Exception as e:
            logger.error(f"Failed to delete file {file_key}: {e}")
            return False

    def list_files(
        self,
        prefix: str,
        max_results: int = 1000,
        continuation_token: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        List files with a given prefix

        Args:
            prefix: Prefix to filter files
            max_results: Maximum number of results to return
            continuation_token: Token for pagination

        Returns:
            Tuple of (list of file info dicts, next continuation token)
        """
        files = []

        try:
            if self.storage_backend == "local":
                # Local filesystem listing
                search_path = os.path.join(self.local_storage_path, prefix)
                if os.path.exists(search_path):
                    for root, _, filenames in os.walk(search_path):
                        for filename in filenames:
                            if filename.endswith(".metadata.json"):
                                continue

                            file_path = os.path.join(root, filename)
                            rel_path = os.path.relpath(file_path, self.local_storage_path)

                            # Get file info
                            stat = os.stat(file_path)
                            files.append(
                                {
                                    "key": rel_path,
                                    "size": stat.st_size,
                                    "last_modified": datetime.fromtimestamp(
                                        stat.st_mtime
                                    ).isoformat(),
                                }
                            )

                            if len(files) >= max_results:
                                break

                return files[:max_results], None

            else:
                # S3 listing
                params = {
                    "Bucket": self.bucket_name,
                    "Prefix": prefix,
                    "MaxKeys": max_results,
                }

                if continuation_token:
                    params["ContinuationToken"] = continuation_token

                response = self.s3_client.list_objects_v2(**params)

                for obj in response.get("Contents", []):
                    files.append(
                        {
                            "key": obj["Key"],
                            "size": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                        }
                    )

                next_token = response.get("NextContinuationToken")
                return files, next_token

        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            return [], None

    def copy_file(
        self,
        source_key: str,
        destination_key: str,
        metadata_updates: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Copy a file within storage

        Args:
            source_key: Source file key
            destination_key: Destination file key
            metadata_updates: Metadata to update during copy

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.storage_backend == "local":
                source_path = os.path.join(self.local_storage_path, source_key)
                dest_path = os.path.join(self.local_storage_path, destination_key)

                if os.path.exists(source_path):
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                    # Copy file
                    with open(source_path, "rb") as src:
                        with open(dest_path, "wb") as dst:
                            dst.write(src.read())

                    # Copy and update metadata
                    metadata_src = f"{source_path}.metadata.json"
                    metadata_dst = f"{dest_path}.metadata.json"

                    if os.path.exists(metadata_src):
                        with open(metadata_src, "r") as f:
                            metadata = json.load(f)

                        if metadata_updates:
                            metadata.update(metadata_updates)

                        with open(metadata_dst, "w") as f:
                            json.dump(metadata, f)

                    return True

                return False

            else:
                # S3 copy
                copy_source = {"Bucket": self.bucket_name, "Key": source_key}

                # Get existing metadata
                head_response = self.s3_client.head_object(Bucket=self.bucket_name, Key=source_key)

                metadata = head_response.get("Metadata", {})
                if metadata_updates:
                    metadata.update(metadata_updates)

                self.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=self.bucket_name,
                    Key=destination_key,
                    Metadata=metadata,
                    MetadataDirective="REPLACE",
                )

                return True

        except Exception as e:
            logger.error(f"Failed to copy file from {source_key} to {destination_key}: {e}")
            return False

    def get_file_info(self, file_key: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a file

        Args:
            file_key: The storage key of the file

        Returns:
            Dict with file information or None if not found
        """
        try:
            if self.storage_backend == "local":
                file_path = os.path.join(self.local_storage_path, file_key)

                if os.path.exists(file_path):
                    stat = os.stat(file_path)

                    # Load metadata if exists
                    metadata = {}
                    metadata_path = f"{file_path}.metadata.json"
                    if os.path.exists(metadata_path):
                        with open(metadata_path, "r") as f:
                            metadata = json.load(f)

                    return {
                        "key": file_key,
                        "size": stat.st_size,
                        "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "metadata": metadata,
                    }

                return None

            else:
                response = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_key)

                return {
                    "key": file_key,
                    "size": response["ContentLength"],
                    "last_modified": response["LastModified"].isoformat(),
                    "content_type": response.get("ContentType"),
                    "etag": response.get("ETag"),
                    "metadata": response.get("Metadata", {}),
                }

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            logger.error(f"Failed to get file info for {file_key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get file info for {file_key}: {e}")
            return None

    def create_multipart_upload(
        self,
        filename: str,
        file_type: str = "uploads",
        user_id: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initialize a multipart upload for large files

        Args:
            filename: Original filename
            file_type: Type of file
            user_id: User ID for organization
            content_type: MIME type of the file

        Returns:
            Dict with upload_id and file_key
        """
        if self.storage_backend == "local":
            # Local storage doesn't support multipart
            return {
                "upload_id": "local-upload",
                "file_key": self._get_file_key(file_type, filename, user_id),
                "part_size": 5 * 1024 * 1024,  # 5MB parts
            }

        file_key = self._get_file_key(file_type, filename, user_id)

        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

        try:
            response = self.s3_client.create_multipart_upload(
                Bucket=self.bucket_name,
                Key=file_key,
                ContentType=content_type,
                Metadata={
                    "original_filename": filename,
                    "user_id": user_id or "",
                    "upload_timestamp": datetime.now().isoformat(),
                },
            )

            return {
                "upload_id": response["UploadId"],
                "file_key": file_key,
                "part_size": 5 * 1024 * 1024,  # 5MB parts
            }

        except Exception as e:
            logger.error(f"Failed to create multipart upload: {e}")
            raise

    def get_multipart_upload_urls(
        self,
        file_key: str,
        upload_id: str,
        part_numbers: List[int],
        expires_in: Optional[int] = None,
    ) -> Dict[int, str]:
        """
        Generate presigned URLs for multipart upload parts

        Args:
            file_key: The S3 key of the file
            upload_id: The multipart upload ID
            part_numbers: List of part numbers to generate URLs for
            expires_in: URL expiration time in seconds

        Returns:
            Dict mapping part numbers to presigned URLs
        """
        if self.storage_backend == "local":
            # Local storage doesn't support multipart
            return {part: "/api/upload-part" for part in part_numbers}

        if not expires_in:
            expires_in = self.EXPIRATION_TIMES["upload"]

        urls = {}

        try:
            for part_number in part_numbers:
                url = self.s3_client.generate_presigned_url(
                    "upload_part",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": file_key,
                        "UploadId": upload_id,
                        "PartNumber": part_number,
                    },
                    ExpiresIn=expires_in,
                )
                urls[part_number] = url

            return urls

        except Exception as e:
            logger.error(f"Failed to generate multipart upload URLs: {e}")
            raise

    def complete_multipart_upload(
        self, file_key: str, upload_id: str, parts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Complete a multipart upload

        Args:
            file_key: The S3 key of the file
            upload_id: The multipart upload ID
            parts: List of part info dicts with 'PartNumber' and 'ETag'

        Returns:
            Dict with file information
        """
        if self.storage_backend == "local":
            # Local storage doesn't support multipart
            return {"file_key": file_key, "storage_backend": "local"}

        try:
            response = self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=file_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            # Get file info
            file_info = self.get_file_info(file_key)

            return {
                "file_key": file_key,
                "etag": response.get("ETag"),
                "location": response.get("Location"),
                "storage_backend": self.storage_backend,
                **file_info,
            }

        except Exception as e:
            logger.error(f"Failed to complete multipart upload: {e}")
            raise

    def health_check(self) -> Dict[str, Any]:
        """
        Check storage service health

        Returns:
            Dict with health status information
        """
        health = {
            "storage_backend": self.storage_backend,
            "healthy": False,
            "details": {},
        }

        try:
            if self.storage_backend == "local":
                # Check local storage
                test_file = os.path.join(self.local_storage_path, ".health_check")
                with open(test_file, "w") as f:
                    f.write(str(datetime.now()))

                if os.path.exists(test_file):
                    os.remove(test_file)
                    health["healthy"] = True
                    health["details"]["path"] = self.local_storage_path
                    health["details"]["writable"] = True

            else:
                # Check S3 connectivity
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                health["healthy"] = True
                health["details"]["bucket"] = self.bucket_name
                health["details"]["endpoint"] = self.endpoint_url or "AWS S3"

                # Check CDN if enabled
                if self.cdn_enabled:
                    health["details"]["cdn_enabled"] = True
                    health["details"]["cdn_domain"] = self.cdn_domain

        except Exception as e:
            health["error"] = str(e)
            health["details"]["error_type"] = type(e).__name__

        return health


# Global instance
object_storage = ObjectStorageService()
