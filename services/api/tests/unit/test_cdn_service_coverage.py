"""
Unit tests for services/storage/cdn_service.py — 37.58% coverage (71 uncovered lines).

Tests CDN providers, CDNService, cache headers, URL generation, and factory functions.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCloudflareProviderInit:
    """Test CloudflareProvider initialization and URL generation."""

    def test_init_stores_config(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="test-zone",
            api_token="test-token",
            domain_name="cdn.example.com",
        )
        assert provider.zone_id == "test-zone"
        assert provider.api_token == "test-token"
        assert provider.domain_name == "cdn.example.com"

    def test_get_cdn_url(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com"
        )
        url = provider.get_cdn_url("/images/test.png")
        assert url == "https://cdn.example.com/images/test.png"

    def test_get_cdn_url_strips_leading_slash(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com"
        )
        url = provider.get_cdn_url("images/test.png")
        assert url == "https://cdn.example.com/images/test.png"

    def test_domain_trailing_slash_stripped(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com/"
        )
        assert provider.domain_name == "cdn.example.com"

    @pytest.mark.asyncio
    async def test_purge_cache_success(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("services.storage.cdn_service.requests.post", return_value=mock_response):
            result = await provider.purge_cache(["/test.png"])
        assert result is True

    @pytest.mark.asyncio
    async def test_purge_cache_failure(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com"
        )
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        with patch("services.storage.cdn_service.requests.post", return_value=mock_response):
            result = await provider.purge_cache(["/test.png"])
        assert result is False

    @pytest.mark.asyncio
    async def test_purge_cache_exception(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com"
        )
        with patch("services.storage.cdn_service.requests.post", side_effect=Exception("conn error")):
            result = await provider.purge_cache(["/test.png"])
        assert result is False

    @pytest.mark.asyncio
    async def test_warm_cache_success(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("services.storage.cdn_service.requests.head", return_value=mock_response):
            result = await provider.warm_cache(["/test.png", "/test2.png"])
        assert result is True

    @pytest.mark.asyncio
    async def test_warm_cache_failure(self):
        from services.storage.cdn_service import CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com"
        )
        with patch("services.storage.cdn_service.requests.head", side_effect=Exception("timeout")):
            result = await provider.warm_cache(["/test.png"])
        assert result is False


class TestCDNService:
    """Test main CDNService class."""

    def _make_service(self):
        from services.storage.cdn_service import CDNService, CloudflareProvider
        provider = CloudflareProvider(
            zone_id="zone", api_token="token", domain_name="cdn.example.com"
        )
        return CDNService(provider)

    def test_get_cache_headers_js(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("app.js")
        assert "Cache-Control" in headers
        assert "immutable" in headers["Cache-Control"]

    def test_get_cache_headers_css(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("style.css")
        assert "immutable" in headers["Cache-Control"]

    def test_get_cache_headers_jpg(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("photo.jpg")
        assert "31536000" in headers["Cache-Control"]

    def test_get_cache_headers_jpeg(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("photo.jpeg")
        assert "31536000" in headers["Cache-Control"]

    def test_get_cache_headers_png(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("image.png")
        assert "31536000" in headers["Cache-Control"]

    def test_get_cache_headers_gif(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("anim.gif")
        assert "31536000" in headers["Cache-Control"]

    def test_get_cache_headers_svg(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("icon.svg")
        assert "31536000" in headers["Cache-Control"]

    def test_get_cache_headers_woff(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("font.woff")
        assert "31536000" in headers["Cache-Control"]

    def test_get_cache_headers_woff2(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("font.woff2")
        assert "31536000" in headers["Cache-Control"]

    def test_get_cache_headers_pdf(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("doc.pdf")
        assert "3600" in headers["Cache-Control"]

    def test_get_cache_headers_doc(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("file.doc")
        assert "3600" in headers["Cache-Control"]

    def test_get_cache_headers_docx(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("file.docx")
        assert "3600" in headers["Cache-Control"]

    def test_get_cache_headers_json(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("data.json")
        assert headers["Cache-Control"] == "no-cache"

    def test_get_cache_headers_xml(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("feed.xml")
        assert headers["Cache-Control"] == "no-cache"

    def test_get_cache_headers_unknown_ext(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("file.xyz")
        assert "3600" in headers["Cache-Control"]

    def test_security_headers_present(self):
        svc = self._make_service()
        headers = svc.get_cache_headers("test.js")
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-XSS-Protection"] == "1; mode=block"

    def test_get_cdn_url_delegates_to_provider(self):
        svc = self._make_service()
        url = svc.get_cdn_url("/test/path")
        assert "cdn.example.com" in url

    def test_generate_cache_key_with_version(self):
        svc = self._make_service()
        key = svc.generate_cache_key("/assets/app.js", version="abc123")
        assert key == "/assets/app.abc123.js"

    def test_generate_cache_key_without_version(self):
        svc = self._make_service()
        key = svc.generate_cache_key("/assets/app.js")
        assert key == "/assets/app.js"

    def test_generate_cache_key_no_extension(self):
        svc = self._make_service()
        key = svc.generate_cache_key("/path/no-ext", version="v1")
        assert key == "/path/no-ext.v1"

    @pytest.mark.asyncio
    async def test_invalidate_cache(self):
        svc = self._make_service()
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("services.storage.cdn_service.requests.post", return_value=mock_response):
            result = await svc.invalidate_cache(["/test.png"])
        assert result is True

    @pytest.mark.asyncio
    async def test_warm_cache(self):
        svc = self._make_service()
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("services.storage.cdn_service.requests.head", return_value=mock_response):
            result = await svc.warm_cache(["/test.png"])
        assert result is True


class TestCreateCDNService:
    """Test the factory function."""

    def test_create_none_provider_returns_none(self):
        from services.storage.cdn_service import create_cdn_service
        result = create_cdn_service(None)
        assert result is None

    def test_create_cloudflare_provider(self):
        from services.storage.cdn_service import create_cdn_service
        svc = create_cdn_service(
            "cloudflare",
            zone_id="zone",
            api_token="token",
            domain_name="cdn.example.com",
        )
        assert svc is not None

    def test_create_unknown_provider_raises(self):
        from services.storage.cdn_service import create_cdn_service
        with pytest.raises(ValueError, match="Unknown CDN provider"):
            create_cdn_service("unknown_provider")


class TestInitializeCDNService:
    """Test the global CDN service initialization."""

    def test_no_provider_configured(self):
        import services.storage.cdn_service as cdn_mod
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CDN_PROVIDER", None)
            cdn_mod.cdn_service = None
            cdn_mod.initialize_cdn_service()
            assert cdn_mod.cdn_service is None

    def test_cloudflare_init(self):
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

    def test_init_with_error(self):
        import services.storage.cdn_service as cdn_mod
        with patch.dict(os.environ, {"CDN_PROVIDER": "cloudfront"}, clear=False):
            # Missing required kwargs should cause an error
            cdn_mod.cdn_service = None
            cdn_mod.initialize_cdn_service()
            # Should gracefully handle error
            assert cdn_mod.cdn_service is None
