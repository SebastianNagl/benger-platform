"""
Storage and CDN configuration for BenGER
"""

from typing import Optional

from pydantic import Field

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings


class StorageConfig(BaseSettings):
    """Storage configuration settings"""

    # Storage backend type: "local", "s3", or "minio"
    storage_type: str = Field(default="local", env="STORAGE_TYPE")

    # Local storage settings
    local_storage_path: str = Field(default="/tmp/benger-uploads", env="LOCAL_STORAGE_PATH")

    # S3/MinIO settings
    s3_bucket_name: str = Field(default="benger-assets", env="S3_BUCKET_NAME")
    s3_endpoint_url: Optional[str] = Field(default=None, env="S3_ENDPOINT_URL")
    s3_access_key: Optional[str] = Field(default=None, env="S3_ACCESS_KEY")
    s3_secret_key: Optional[str] = Field(default=None, env="S3_SECRET_KEY")
    s3_region: str = Field(default="us-east-1", env="S3_REGION")
    s3_use_ssl: bool = Field(default=True, env="S3_USE_SSL")

    # URL settings for file access
    storage_base_url: Optional[str] = Field(default=None, env="STORAGE_BASE_URL")

    class Config:
        env_file = ".env"
        case_sensitive = False


class CDNConfig(BaseSettings):
    """CDN configuration settings"""

    # CDN provider: "cloudfront", "cloudflare", or None
    cdn_provider: Optional[str] = Field(default=None, env="CDN_PROVIDER")

    # CloudFront settings
    cloudfront_distribution_id: Optional[str] = Field(
        default=None, env="CLOUDFRONT_DISTRIBUTION_ID"
    )
    cloudfront_domain_name: Optional[str] = Field(default=None, env="CLOUDFRONT_DOMAIN_NAME")

    # Cloudflare settings
    cloudflare_zone_id: Optional[str] = Field(default=None, env="CLOUDFLARE_ZONE_ID")
    cloudflare_api_token: Optional[str] = Field(default=None, env="CLOUDFLARE_API_TOKEN")
    cloudflare_domain_name: Optional[str] = Field(default=None, env="CLOUDFLARE_DOMAIN_NAME")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Create global config instances
storage_config = StorageConfig()
cdn_config = CDNConfig()


# Helper function to get storage service configuration
def get_storage_config():
    """Get storage configuration for creating storage service"""
    if storage_config.storage_type in ["s3", "minio"]:
        return {
            "storage_type": storage_config.storage_type,
            "bucket_name": storage_config.s3_bucket_name,
            "endpoint_url": storage_config.s3_endpoint_url,
            "access_key": storage_config.s3_access_key,
            "secret_key": storage_config.s3_secret_key,
            "region": storage_config.s3_region,
            "use_ssl": storage_config.s3_use_ssl,
        }
    else:
        return {"storage_type": "local", "base_path": storage_config.local_storage_path}


# Helper function to get CDN configuration
def get_cdn_config():
    """Get CDN configuration for creating CDN service"""
    if not cdn_config.cdn_provider:
        return None

    if cdn_config.cdn_provider == "cloudfront":
        return {
            "provider_type": "cloudfront",
            "distribution_id": cdn_config.cloudfront_distribution_id,
            "domain_name": cdn_config.cloudfront_domain_name,
            "access_key": storage_config.s3_access_key,  # Reuse S3 credentials
            "secret_key": storage_config.s3_secret_key,
            "region": storage_config.s3_region,
        }
    elif cdn_config.cdn_provider == "cloudflare":
        return {
            "provider_type": "cloudflare",
            "zone_id": cdn_config.cloudflare_zone_id,
            "api_token": cdn_config.cloudflare_api_token,
            "domain_name": cdn_config.cloudflare_domain_name,
        }

    return None
