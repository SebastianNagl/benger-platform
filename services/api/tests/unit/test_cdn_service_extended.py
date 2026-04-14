"""
Extended unit tests for services/storage/cdn_service.py

Covers uncovered lines including:
- CloudFrontProvider.__init__ with/without credentials (lines 54-55)
- CloudFrontProvider.purge_cache (lines 61-79)
- CloudFrontProvider.get_cdn_url (line 83)
- CloudFrontProvider.warm_cache (lines 86-96)
- initialize_cdn_service for cloudfront path (lines 259-270)
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixture to ensure boto3 is available as a mock in sys.modules
# CloudFrontProvider does `import boto3` inside __init__
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_boto3_module():
    """Inject a mock boto3 module into sys.modules for CloudFrontProvider."""
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = MagicMock()
    original = sys.modules.get("boto3")
    sys.modules["boto3"] = mock_boto3
    yield mock_boto3
    if original is not None:
        sys.modules["boto3"] = original
    else:
        sys.modules.pop("boto3", None)


class TestCloudFrontProviderInit:
    """Test CloudFrontProvider initialization (lines 38-57)."""

    def test_init_with_credentials(self, mock_boto3_module):
        """CloudFrontProvider stores config and creates boto3 client with creds."""
        mock_cf_client = MagicMock()
        mock_boto3_module.client.return_value = mock_cf_client

        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider(
            distribution_id="E123ABC",
            domain_name="d123.cloudfront.net/",
            access_key="AKIA123",
            secret_key="secret456",
            region="eu-west-1",
        )

        assert provider.distribution_id == "E123ABC"
        assert provider.domain_name == "d123.cloudfront.net"  # trailing slash stripped
        assert provider.cloudfront_client is mock_cf_client

        mock_boto3_module.client.assert_called_with(
            "cloudfront",
            region_name="eu-west-1",
            aws_access_key_id="AKIA123",
            aws_secret_access_key="secret456",
        )

    def test_init_without_credentials(self, mock_boto3_module):
        """CloudFrontProvider works without explicit credentials (uses IAM role)."""
        mock_cf_client = MagicMock()
        mock_boto3_module.client.return_value = mock_cf_client

        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider(
            distribution_id="EDIST",
            domain_name="cdn.example.com",
        )

        assert provider.distribution_id == "EDIST"
        # Should not pass credentials
        mock_boto3_module.client.assert_called_with(
            "cloudfront",
            region_name="us-east-1",
        )

    def test_init_with_access_key_only_no_secret(self, mock_boto3_module):
        """If only access_key is provided without secret, no credentials passed."""
        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider(
            distribution_id="E111",
            domain_name="cdn.test.com",
            access_key="AKIA123",
            secret_key=None,
        )

        # access_key and secret_key both must be truthy for creds to be added
        call_kwargs = mock_boto3_module.client.call_args[1]
        assert "aws_access_key_id" not in call_kwargs


class TestCloudFrontProviderGetCdnUrl:
    """Test CloudFrontProvider.get_cdn_url (line 83)."""

    def test_get_cdn_url_with_leading_slash(self, mock_boto3_module):
        """Leading slash is stripped from path."""
        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider("E123", "cdn.example.com")

        url = provider.get_cdn_url("/images/photo.jpg")
        assert url == "https://cdn.example.com/images/photo.jpg"

    def test_get_cdn_url_without_leading_slash(self, mock_boto3_module):
        """Path without leading slash works correctly."""
        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider("E123", "cdn.example.com")

        url = provider.get_cdn_url("assets/app.js")
        assert url == "https://cdn.example.com/assets/app.js"


class TestCloudFrontProviderPurgeCache:
    """Test CloudFrontProvider.purge_cache (lines 61-79)."""

    @pytest.mark.asyncio
    async def test_purge_cache_success(self, mock_boto3_module):
        """Successful cache purge creates invalidation."""
        mock_cf_client = MagicMock()
        mock_cf_client.create_invalidation.return_value = {
            "Invalidation": {"Id": "INV123"}
        }
        mock_boto3_module.client.return_value = mock_cf_client

        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider("E123", "cdn.example.com")

        result = await provider.purge_cache(["/images/photo.jpg", "assets/app.js"])

        assert result is True
        mock_cf_client.create_invalidation.assert_called_once()
        call_kwargs = mock_cf_client.create_invalidation.call_args[1]
        assert call_kwargs["DistributionId"] == "E123"
        paths = call_kwargs["InvalidationBatch"]["Paths"]["Items"]
        # All paths should start with /
        assert paths[0] == "/images/photo.jpg"
        assert paths[1] == "/assets/app.js"
        assert call_kwargs["InvalidationBatch"]["Paths"]["Quantity"] == 2

    @pytest.mark.asyncio
    async def test_purge_cache_normalizes_paths(self, mock_boto3_module):
        """Paths without leading slash get / prepended."""
        mock_cf_client = MagicMock()
        mock_cf_client.create_invalidation.return_value = {
            "Invalidation": {"Id": "INV456"}
        }
        mock_boto3_module.client.return_value = mock_cf_client

        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider("E123", "cdn.example.com")

        await provider.purge_cache(["no-slash.jpg"])

        call_kwargs = mock_cf_client.create_invalidation.call_args[1]
        paths = call_kwargs["InvalidationBatch"]["Paths"]["Items"]
        assert paths[0] == "/no-slash.jpg"

    @pytest.mark.asyncio
    async def test_purge_cache_failure(self, mock_boto3_module):
        """Cache purge failure returns False."""
        mock_cf_client = MagicMock()
        mock_cf_client.create_invalidation.side_effect = Exception("AWS error")
        mock_boto3_module.client.return_value = mock_cf_client

        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider("E123", "cdn.example.com")

        result = await provider.purge_cache(["/test.png"])

        assert result is False


class TestCloudFrontProviderWarmCache:
    """Test CloudFrontProvider.warm_cache (lines 86-96)."""

    @pytest.mark.asyncio
    async def test_warm_cache_success(self, mock_boto3_module):
        """Successful cache warming requests each URL."""
        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider("E123", "cdn.example.com")

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("services.storage.cdn_service.requests.head", return_value=mock_response) as mock_head:
            result = await provider.warm_cache(["/img1.jpg", "/img2.jpg"])

        assert result is True
        assert mock_head.call_count == 2
        calls = mock_head.call_args_list
        assert calls[0][0][0] == "https://cdn.example.com/img1.jpg"
        assert calls[1][0][0] == "https://cdn.example.com/img2.jpg"

    @pytest.mark.asyncio
    async def test_warm_cache_failure(self, mock_boto3_module):
        """Cache warming failure returns False."""
        from services.storage.cdn_service import CloudFrontProvider
        provider = CloudFrontProvider("E123", "cdn.example.com")

        with patch("services.storage.cdn_service.requests.head", side_effect=Exception("timeout")):
            result = await provider.warm_cache(["/img1.jpg"])

        assert result is False


class TestInitializeCDNServiceCloudfront:
    """Test initialize_cdn_service for CloudFront path (lines 250-270)."""

    def test_cloudfront_initialization_success(self, mock_boto3_module):
        """Successful CloudFront initialization sets global cdn_service."""
        import services.storage.cdn_service as cdn_mod

        env = {
            "CDN_PROVIDER": "cloudfront",
            "CLOUDFRONT_DISTRIBUTION_ID": "E123",
            "CDN_DOMAIN": "cdn.example.com",
            "AWS_ACCESS_KEY_ID": "AKIA123",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_REGION": "us-west-2",
        }

        with patch.dict(os.environ, env, clear=False):
            cdn_mod.cdn_service = None
            cdn_mod.initialize_cdn_service()

        assert cdn_mod.cdn_service is not None

    def test_cloudfront_initialization_with_default_region(self, mock_boto3_module):
        """CloudFront initialization uses default region when AWS_REGION not set."""
        import services.storage.cdn_service as cdn_mod

        env = {
            "CDN_PROVIDER": "cloudfront",
            "CLOUDFRONT_DISTRIBUTION_ID": "EDIST",
            "CDN_DOMAIN": "cdn.test.com",
            "AWS_ACCESS_KEY_ID": "key",
            "AWS_SECRET_ACCESS_KEY": "secret",
        }

        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("AWS_REGION", None)
            cdn_mod.cdn_service = None
            cdn_mod.initialize_cdn_service()

        assert cdn_mod.cdn_service is not None

    def test_cloudflare_initialization_success(self, mock_boto3_module):
        """Successful Cloudflare initialization sets global cdn_service."""
        import services.storage.cdn_service as cdn_mod

        env = {
            "CDN_PROVIDER": "cloudflare",
            "CLOUDFLARE_ZONE_ID": "zone-123",
            "CLOUDFLARE_API_TOKEN": "token-456",
            "CDN_DOMAIN": "cdn.example.com",
        }

        with patch.dict(os.environ, env, clear=False):
            cdn_mod.cdn_service = None
            cdn_mod.initialize_cdn_service()

        assert cdn_mod.cdn_service is not None

    def test_no_provider_returns_none(self, mock_boto3_module):
        """No CDN_PROVIDER env var results in None service."""
        import services.storage.cdn_service as cdn_mod

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CDN_PROVIDER", None)
            cdn_mod.cdn_service = None
            cdn_mod.initialize_cdn_service()

        assert cdn_mod.cdn_service is None

    def test_initialize_with_exception_sets_none(self, mock_boto3_module):
        """Exception during initialization sets cdn_service to None."""
        import services.storage.cdn_service as cdn_mod

        env = {
            "CDN_PROVIDER": "cloudfront",
            "CLOUDFRONT_DISTRIBUTION_ID": "E123",
            "CDN_DOMAIN": "cdn.example.com",
        }

        with patch.dict(os.environ, env, clear=False), \
             patch("services.storage.cdn_service.create_cdn_service", side_effect=Exception("init error")):
            cdn_mod.cdn_service = None
            cdn_mod.initialize_cdn_service()

        assert cdn_mod.cdn_service is None

    def test_create_returns_none_logs_warning(self, mock_boto3_module):
        """When create_cdn_service returns None, cdn_service stays None."""
        import services.storage.cdn_service as cdn_mod

        env = {"CDN_PROVIDER": "cloudfront"}

        with patch.dict(os.environ, env, clear=False), \
             patch("services.storage.cdn_service.create_cdn_service", return_value=None):
            cdn_mod.cdn_service = "old_value"
            cdn_mod.initialize_cdn_service()

        assert cdn_mod.cdn_service is None


class TestCreateCDNServiceCloudfront:
    """Test create_cdn_service factory with CloudFront."""

    def test_create_cloudfront_service(self, mock_boto3_module):
        """Factory creates CDNService with CloudFrontProvider."""
        from services.storage.cdn_service import create_cdn_service, CloudFrontProvider
        service = create_cdn_service(
            "cloudfront",
            distribution_id="E123",
            domain_name="cdn.example.com",
            access_key="key",
            secret_key="secret",
        )

        assert service is not None
        assert isinstance(service.provider, CloudFrontProvider)

    def test_create_with_empty_provider_returns_none(self, mock_boto3_module):
        """Factory with empty string returns None."""
        from services.storage.cdn_service import create_cdn_service
        result = create_cdn_service("")
        assert result is None

    def test_create_with_none_provider_returns_none(self, mock_boto3_module):
        """Factory with None returns None."""
        from services.storage.cdn_service import create_cdn_service
        result = create_cdn_service(None)
        assert result is None
