"""
CDN Service for BenGER

This module provides CDN integration for static assets and file delivery,
supporting CloudFront, Cloudflare, and other CDN providers.
"""

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class CDNProvider(ABC):
    """Abstract base class for CDN providers"""

    @abstractmethod
    async def purge_cache(self, paths: List[str]) -> bool:
        """Purge/invalidate cache for specific paths"""

    @abstractmethod
    def get_cdn_url(self, path: str) -> str:
        """Get CDN URL for a given path"""

    @abstractmethod
    async def warm_cache(self, paths: List[str]) -> bool:
        """Pre-warm cache by requesting paths"""


class CloudFrontProvider(CDNProvider):
    """AWS CloudFront CDN provider"""

    def __init__(
        self,
        distribution_id: str,
        domain_name: str,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1",
    ):
        self.distribution_id = distribution_id
        self.domain_name = domain_name.rstrip("/")

        # Initialize boto3 client for CloudFront
        import boto3

        client_kwargs = {"region_name": region}
        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key

        self.cloudfront_client = boto3.client("cloudfront", **client_kwargs)

    async def purge_cache(self, paths: List[str]) -> bool:
        """Create CloudFront invalidation"""
        try:
            # CloudFront requires paths to start with /
            paths = [f"/{p.lstrip('/')}" for p in paths]

            response = self.cloudfront_client.create_invalidation(
                DistributionId=self.distribution_id,
                InvalidationBatch={
                    "Paths": {"Quantity": len(paths), "Items": paths},
                    "CallerReference": f"benger-{int(time.time())}",
                },
            )

            invalidation_id = response["Invalidation"]["Id"]
            logger.info(f"Created CloudFront invalidation: {invalidation_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to purge CloudFront cache: {e}")
            return False

    def get_cdn_url(self, path: str) -> str:
        """Get CloudFront URL for a path"""
        path = path.lstrip("/")
        return f"https://{self.domain_name}/{path}"

    async def warm_cache(self, paths: List[str]) -> bool:
        """Warm CloudFront cache by requesting URLs"""
        try:
            for path in paths:
                url = self.get_cdn_url(path)
                response = requests.head(url, timeout=10)
                logger.debug(f"Warmed cache for {url}: {response.status_code}")
            return True
        except Exception as e:
            logger.error(f"Failed to warm cache: {e}")
            return False


class CloudflareProvider(CDNProvider):
    """Cloudflare CDN provider"""

    def __init__(self, zone_id: str, api_token: str, domain_name: str):
        self.zone_id = zone_id
        self.api_token = api_token
        self.domain_name = domain_name.rstrip("/")
        self.api_base = "https://api.cloudflare.com/client/v4"

        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def purge_cache(self, paths: List[str]) -> bool:
        """Purge Cloudflare cache for specific paths"""
        try:
            # Convert paths to full URLs
            urls = [self.get_cdn_url(path) for path in paths]

            response = requests.post(
                f"{self.api_base}/zones/{self.zone_id}/purge_cache",
                headers=self.headers,
                json={"files": urls},
            )

            if response.status_code == 200:
                logger.info(f"Purged Cloudflare cache for {len(urls)} URLs")
                return True
            else:
                logger.error(f"Cloudflare purge failed: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to purge Cloudflare cache: {e}")
            return False

    def get_cdn_url(self, path: str) -> str:
        """Get Cloudflare URL for a path"""
        path = path.lstrip("/")
        return f"https://{self.domain_name}/{path}"

    async def warm_cache(self, paths: List[str]) -> bool:
        """Warm Cloudflare cache by requesting URLs"""
        try:
            for path in paths:
                url = self.get_cdn_url(path)
                response = requests.head(url, timeout=10)
                logger.debug(f"Warmed cache for {url}: {response.status_code}")
            return True
        except Exception as e:
            logger.error(f"Failed to warm cache: {e}")
            return False


class CDNService:
    """Main CDN service that manages cache and delivery"""

    def __init__(self, provider: CDNProvider):
        self.provider = provider
        self._cache_headers = {
            # Static assets - long cache
            ".js": "public, max-age=31536000, immutable",
            ".css": "public, max-age=31536000, immutable",
            ".jpg": "public, max-age=31536000",
            ".jpeg": "public, max-age=31536000",
            ".png": "public, max-age=31536000",
            ".gif": "public, max-age=31536000",
            ".svg": "public, max-age=31536000",
            ".woff": "public, max-age=31536000",
            ".woff2": "public, max-age=31536000",
            # Documents - shorter cache
            ".pdf": "public, max-age=3600",
            ".doc": "public, max-age=3600",
            ".docx": "public, max-age=3600",
            # Dynamic content - no cache
            ".json": "no-cache",
            ".xml": "no-cache",
        }

    def get_cache_headers(self, filename: str) -> Dict[str, str]:
        """Get appropriate cache headers for a file"""
        ext = os.path.splitext(filename)[1].lower()
        cache_control = self._cache_headers.get(ext, "public, max-age=3600")

        return {
            "Cache-Control": cache_control,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
        }

    def get_cdn_url(self, path: str) -> str:
        """Get CDN URL for a resource"""
        return self.provider.get_cdn_url(path)

    async def invalidate_cache(self, paths: List[str]) -> bool:
        """Invalidate CDN cache for specific paths"""
        return await self.provider.purge_cache(paths)

    async def warm_cache(self, paths: List[str]) -> bool:
        """Pre-warm CDN cache"""
        return await self.provider.warm_cache(paths)

    def generate_cache_key(self, path: str, version: Optional[str] = None) -> str:
        """Generate versioned cache key for cache busting"""
        if version:
            # Insert version before file extension
            base, ext = os.path.splitext(path)
            return f"{base}.{version}{ext}"
        return path


# Factory function to create CDN service
def create_cdn_service(provider_type: str, **kwargs) -> Optional[CDNService]:
    """
    Create CDN service instance

    Args:
        provider_type: "cloudfront", "cloudflare", or None
        **kwargs: Provider-specific configuration
    """
    if not provider_type:
        return None

    if provider_type == "cloudfront":
        provider = CloudFrontProvider(**kwargs)
    elif provider_type == "cloudflare":
        provider = CloudflareProvider(**kwargs)
    else:
        raise ValueError(f"Unknown CDN provider: {provider_type}")

    return CDNService(provider)


# Global CDN service instance
cdn_service = None


# Initialize CDN service based on environment configuration
def initialize_cdn_service():
    """Initialize the global CDN service"""
    global cdn_service

    try:
        provider_type = os.getenv("CDN_PROVIDER")  # "cloudfront", "cloudflare", or None

        if not provider_type:
            logger.info("No CDN provider configured")
            return None

        if provider_type == "cloudfront":
            cdn_service = create_cdn_service(
                provider_type="cloudfront",
                distribution_id=os.getenv("CLOUDFRONT_DISTRIBUTION_ID"),
                domain_name=os.getenv("CDN_DOMAIN"),
                access_key=os.getenv("AWS_ACCESS_KEY_ID"),
                secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region=os.getenv("AWS_REGION", "us-east-1"),
            )
        elif provider_type == "cloudflare":
            cdn_service = create_cdn_service(
                provider_type="cloudflare",
                zone_id=os.getenv("CLOUDFLARE_ZONE_ID"),
                api_token=os.getenv("CLOUDFLARE_API_TOKEN"),
                domain_name=os.getenv("CDN_DOMAIN"),
            )

        if cdn_service:
            logger.info(f"CDN service initialized with {provider_type}")
        else:
            logger.warning("CDN service initialization failed")

    except Exception as e:
        logger.error(f"Error initializing CDN service: {e}")
        cdn_service = None


# Initialize on module import
initialize_cdn_service()
