"""
Unit Tests for CDN Service

Tests the CDN functionality including:
- Service initialization with providers
- URL generation for different content types
"""

import os
from unittest.mock import Mock, patch

import pytest

from cdn_service import CDNService


@pytest.fixture
def cdn_service():
    """Create a CDNService instance for testing"""
    mock_provider = Mock()
    mock_provider.invalidate_cache = Mock(return_value=True)
    mock_provider.get_cache_headers = Mock(return_value={})
    return CDNService(provider=mock_provider)


class TestCDNServiceInitialization:
    """Test CDN service initialization"""

    def test_default_initialization(self):
        """Test service initialization with mock provider"""
        mock_provider = Mock()
        mock_provider.get_cdn_url = Mock(return_value="https://example.com/test")

        service = CDNService(mock_provider)

        assert service.provider is mock_provider
        assert hasattr(service, 'get_cdn_url')
        assert hasattr(service, 'invalidate_cache')
        assert hasattr(service, 'warm_cache')
        assert hasattr(service, 'get_cache_headers')
        assert hasattr(service, 'generate_cache_key')

    @patch.dict(
        os.environ,
        {
            "CDN_PROVIDER": "cloudfront",
            "CDN_DOMAIN": "cdn.test.com",
            "CLOUDFRONT_DISTRIBUTION_ID": "E1234567890",
            "AWS_ACCESS_KEY_ID": "test-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret",
        },
    )
    def test_cloudfront_initialization(self):
        """Test CloudFront service initialization with mocked provider"""
        from cdn_service import CloudFrontProvider

        with patch('builtins.__import__') as mock_import:

            def side_effect(name, *args, **kwargs):
                if name == 'boto3':
                    mock_boto3 = Mock()
                    mock_boto3.client = Mock(return_value=Mock())
                    return mock_boto3
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            mock_provider = CloudFrontProvider("E1234567890", "cdn.test.com")
            service = CDNService(mock_provider)

        assert service is not None
        assert service.provider is mock_provider
        assert hasattr(service.provider, 'distribution_id')
        assert service.provider.distribution_id == "E1234567890"
        assert service.provider.domain_name == "cdn.test.com"

    @patch.dict(
        os.environ,
        {
            "CDN_PROVIDER": "cloudflare",
            "CDN_DOMAIN": "cdn.test.com",
            "CLOUDFLARE_ZONE_ID": "zone123",
            "CLOUDFLARE_API_TOKEN": "token123",
        },
    )
    def test_cloudflare_initialization(self):
        """Test Cloudflare service initialization"""
        from cdn_service import CloudflareProvider

        provider = CloudflareProvider("zone123", "cdn.test.com", "token123")
        service = CDNService(provider)

        assert service is not None
        assert service.provider is provider
        assert hasattr(service.provider, 'zone_id')
        assert service.provider.zone_id == "zone123"


class TestCDNURLGeneration:
    """Test CDN URL generation"""

    @patch.dict(os.environ, {"CDN_PROVIDER": "cloudfront", "CDN_DOMAIN": "cdn.test.com"})
    def test_get_cdn_url_static(self):
        """Test CDN URL generation for static assets"""
        mock_provider = Mock()
        mock_provider.get_cdn_url = Mock(return_value="https://cdn.test.com/static/js/app.js")

        service = CDNService(mock_provider)
        url = service.get_cdn_url("/static/js/app.js")

        assert url == "https://cdn.test.com/static/js/app.js"
        mock_provider.get_cdn_url.assert_called_once_with("/static/js/app.js")

    @patch.dict(os.environ, {"CDN_PROVIDER": "cloudfront", "CDN_DOMAIN": "cdn.test.com"})
    def test_get_cdn_url_no_version(self):
        """Test CDN URL generation without versioning"""
        mock_provider = Mock()
        mock_provider.get_cdn_url = Mock(return_value="https://cdn.test.com/images/logo.png")

        service = CDNService(mock_provider)
        url = service.get_cdn_url("/images/logo.png")

        assert url == "https://cdn.test.com/images/logo.png"
        assert "v=" not in url
        mock_provider.get_cdn_url.assert_called_once_with("/images/logo.png")

    def test_get_cdn_url_disabled(self):
        """Test URL generation when CDN is disabled"""
        mock_provider = Mock()
        mock_provider.get_cdn_url = Mock(return_value="https://api.test.com/static/app.js")

        service = CDNService(mock_provider)
        url = service.get_cdn_url("/static/app.js")

        assert url == "https://api.test.com/static/app.js"
        mock_provider.get_cdn_url.assert_called_once_with("/static/app.js")
