"""
Extended unit tests for services/storage/storage_config.py

Covers all 43 uncovered lines (5-108) by testing the actual module functions
with mocked module-level config instances.

pydantic_settings is not available in the test container, so we cannot
instantiate StorageConfig/CDNConfig directly. Instead, we:
1. Mock the module import to provide a working BaseSettings
2. Test get_storage_config() and get_cdn_config() by patching the module-level config objects
"""

import importlib
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixture to load storage_config module with a mock pydantic_settings
# ---------------------------------------------------------------------------

@pytest.fixture
def storage_config_module():
    """
    Import services.storage.storage_config with pydantic_settings mocked out.
    Returns the module so tests can call its functions and inspect its objects.
    """
    # Remove cached imports that might interfere
    mods_to_remove = [k for k in sys.modules if "storage_config" in k]
    saved = {}
    for k in mods_to_remove:
        saved[k] = sys.modules.pop(k)

    # Create a mock pydantic_settings module with a working BaseSettings
    from pydantic import BaseModel

    class FakeBaseSettings(BaseModel):
        """Minimal BaseSettings replacement for testing."""
        class Config:
            env_file = ".env"
            case_sensitive = False

        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)

        def __init__(self, **kwargs):
            # Read defaults from Field annotations, allow env var overrides
            super().__init__(**kwargs)

    mock_pydantic_settings = ModuleType("pydantic_settings")
    mock_pydantic_settings.BaseSettings = FakeBaseSettings
    sys.modules["pydantic_settings"] = mock_pydantic_settings

    # Now import the module fresh
    import services.storage.storage_config as mod
    importlib.reload(mod)

    yield mod

    # Restore original module state
    sys.modules.pop("pydantic_settings", None)
    for k, v in saved.items():
        sys.modules[k] = v


class TestGetStorageConfig:
    """Test get_storage_config() helper function (lines 69-82)."""

    def test_s3_storage_returns_s3_config(self, storage_config_module):
        """S3 storage type returns full S3 config dict."""
        mod = storage_config_module

        mock_config = MagicMock()
        mock_config.storage_type = "s3"
        mock_config.s3_bucket_name = "my-bucket"
        mock_config.s3_endpoint_url = "https://s3.amazonaws.com"
        mock_config.s3_access_key = "AKIA123"
        mock_config.s3_secret_key = "secret"
        mock_config.s3_region = "eu-central-1"
        mock_config.s3_use_ssl = True

        original = mod.storage_config
        mod.storage_config = mock_config
        try:
            result = mod.get_storage_config()
        finally:
            mod.storage_config = original

        assert result["storage_type"] == "s3"
        assert result["bucket_name"] == "my-bucket"
        assert result["endpoint_url"] == "https://s3.amazonaws.com"
        assert result["access_key"] == "AKIA123"
        assert result["secret_key"] == "secret"
        assert result["region"] == "eu-central-1"
        assert result["use_ssl"] is True

    def test_minio_storage_returns_s3_config(self, storage_config_module):
        """MinIO storage type returns S3-style config dict."""
        mod = storage_config_module

        mock_config = MagicMock()
        mock_config.storage_type = "minio"
        mock_config.s3_bucket_name = "minio-bucket"
        mock_config.s3_endpoint_url = "http://minio:9000"
        mock_config.s3_access_key = "minioadmin"
        mock_config.s3_secret_key = "minioadmin"
        mock_config.s3_region = "us-east-1"
        mock_config.s3_use_ssl = False

        original = mod.storage_config
        mod.storage_config = mock_config
        try:
            result = mod.get_storage_config()
        finally:
            mod.storage_config = original

        assert result["storage_type"] == "minio"
        assert result["bucket_name"] == "minio-bucket"
        assert result["use_ssl"] is False

    def test_local_storage_returns_local_config(self, storage_config_module):
        """Local storage type returns base_path config."""
        mod = storage_config_module

        mock_config = MagicMock()
        mock_config.storage_type = "local"
        mock_config.local_storage_path = "/data/uploads"

        original = mod.storage_config
        mod.storage_config = mock_config
        try:
            result = mod.get_storage_config()
        finally:
            mod.storage_config = original

        assert result["storage_type"] == "local"
        assert result["base_path"] == "/data/uploads"
        assert "bucket_name" not in result

    def test_unknown_storage_type_returns_local(self, storage_config_module):
        """Unknown storage type falls through to local config."""
        mod = storage_config_module

        mock_config = MagicMock()
        mock_config.storage_type = "unknown"
        mock_config.local_storage_path = "/fallback"

        original = mod.storage_config
        mod.storage_config = mock_config
        try:
            result = mod.get_storage_config()
        finally:
            mod.storage_config = original

        assert result["storage_type"] == "local"
        assert result["base_path"] == "/fallback"


class TestGetCDNConfig:
    """Test get_cdn_config() helper function (lines 86-108)."""

    def test_no_provider_returns_none(self, storage_config_module):
        """No CDN provider returns None."""
        mod = storage_config_module

        mock_cdn = MagicMock()
        mock_cdn.cdn_provider = None

        original = mod.cdn_config
        mod.cdn_config = mock_cdn
        try:
            result = mod.get_cdn_config()
        finally:
            mod.cdn_config = original

        assert result is None

    def test_cloudfront_provider(self, storage_config_module):
        """CloudFront provider returns CloudFront config dict."""
        mod = storage_config_module

        mock_cdn = MagicMock()
        mock_cdn.cdn_provider = "cloudfront"
        mock_cdn.cloudfront_distribution_id = "E123"
        mock_cdn.cloudfront_domain_name = "d123.cloudfront.net"

        mock_storage = MagicMock()
        mock_storage.s3_access_key = "AKIA123"
        mock_storage.s3_secret_key = "secret"
        mock_storage.s3_region = "us-east-1"

        orig_cdn = mod.cdn_config
        orig_storage = mod.storage_config
        mod.cdn_config = mock_cdn
        mod.storage_config = mock_storage
        try:
            result = mod.get_cdn_config()
        finally:
            mod.cdn_config = orig_cdn
            mod.storage_config = orig_storage

        assert result is not None
        assert result["provider_type"] == "cloudfront"
        assert result["distribution_id"] == "E123"
        assert result["domain_name"] == "d123.cloudfront.net"
        assert result["access_key"] == "AKIA123"
        assert result["secret_key"] == "secret"
        assert result["region"] == "us-east-1"

    def test_cloudflare_provider(self, storage_config_module):
        """Cloudflare provider returns Cloudflare config dict."""
        mod = storage_config_module

        mock_cdn = MagicMock()
        mock_cdn.cdn_provider = "cloudflare"
        mock_cdn.cloudflare_zone_id = "zone-abc"
        mock_cdn.cloudflare_api_token = "token-xyz"
        mock_cdn.cloudflare_domain_name = "cdn.example.com"

        original = mod.cdn_config
        mod.cdn_config = mock_cdn
        try:
            result = mod.get_cdn_config()
        finally:
            mod.cdn_config = original

        assert result is not None
        assert result["provider_type"] == "cloudflare"
        assert result["zone_id"] == "zone-abc"
        assert result["api_token"] == "token-xyz"
        assert result["domain_name"] == "cdn.example.com"

    def test_unknown_provider_returns_none(self, storage_config_module):
        """Unknown CDN provider returns None."""
        mod = storage_config_module

        mock_cdn = MagicMock()
        mock_cdn.cdn_provider = "fastly"

        original = mod.cdn_config
        mod.cdn_config = mock_cdn
        try:
            result = mod.get_cdn_config()
        finally:
            mod.cdn_config = original

        assert result is None

    def test_empty_string_provider_returns_none(self, storage_config_module):
        """Empty string provider is treated as no provider."""
        mod = storage_config_module

        mock_cdn = MagicMock()
        mock_cdn.cdn_provider = ""

        original = mod.cdn_config
        mod.cdn_config = mock_cdn
        try:
            result = mod.get_cdn_config()
        finally:
            mod.cdn_config = original

        assert result is None


class TestStorageConfigModelFields:
    """Test StorageConfig and CDNConfig model fields exist after import (lines 16-65)."""

    def test_storage_config_has_expected_fields(self, storage_config_module):
        """StorageConfig class defines expected fields."""
        mod = storage_config_module
        config_cls = mod.StorageConfig

        # Check field names exist in the schema
        field_names = set(config_cls.model_fields.keys())
        expected = {
            "storage_type", "local_storage_path", "s3_bucket_name",
            "s3_endpoint_url", "s3_access_key", "s3_secret_key",
            "s3_region", "s3_use_ssl", "storage_base_url",
        }
        assert expected.issubset(field_names)

    def test_cdn_config_has_expected_fields(self, storage_config_module):
        """CDNConfig class defines expected fields."""
        mod = storage_config_module
        config_cls = mod.CDNConfig

        field_names = set(config_cls.model_fields.keys())
        expected = {
            "cdn_provider", "cloudfront_distribution_id", "cloudfront_domain_name",
            "cloudflare_zone_id", "cloudflare_api_token", "cloudflare_domain_name",
        }
        assert expected.issubset(field_names)

    def test_storage_config_default_storage_type(self, storage_config_module):
        """StorageConfig defaults storage_type to 'local'."""
        mod = storage_config_module
        field = mod.StorageConfig.model_fields["storage_type"]
        assert field.default == "local"

    def test_storage_config_default_bucket(self, storage_config_module):
        """StorageConfig defaults s3_bucket_name."""
        mod = storage_config_module
        field = mod.StorageConfig.model_fields["s3_bucket_name"]
        assert field.default == "benger-assets"

    def test_storage_config_default_region(self, storage_config_module):
        """StorageConfig defaults s3_region to us-east-1."""
        mod = storage_config_module
        field = mod.StorageConfig.model_fields["s3_region"]
        assert field.default == "us-east-1"

    def test_storage_config_default_ssl(self, storage_config_module):
        """StorageConfig defaults s3_use_ssl to True."""
        mod = storage_config_module
        field = mod.StorageConfig.model_fields["s3_use_ssl"]
        assert field.default is True

    def test_cdn_config_default_provider_is_none(self, storage_config_module):
        """CDNConfig defaults cdn_provider to None."""
        mod = storage_config_module
        field = mod.CDNConfig.model_fields["cdn_provider"]
        assert field.default is None

    def test_storage_config_default_local_path(self, storage_config_module):
        """StorageConfig defaults local_storage_path."""
        mod = storage_config_module
        field = mod.StorageConfig.model_fields["local_storage_path"]
        assert field.default == "/tmp/benger-uploads"


class TestModuleLevelInstances:
    """Test module-level global config instances and helper functions exist."""

    def test_storage_config_instance_exists(self, storage_config_module):
        """Module has a global storage_config instance."""
        mod = storage_config_module
        assert hasattr(mod, "storage_config")
        assert mod.storage_config is not None

    def test_cdn_config_instance_exists(self, storage_config_module):
        """Module has a global cdn_config instance."""
        mod = storage_config_module
        assert hasattr(mod, "cdn_config")
        assert mod.cdn_config is not None

    def test_helper_functions_exist(self, storage_config_module):
        """Module exports get_storage_config and get_cdn_config."""
        mod = storage_config_module
        assert callable(mod.get_storage_config)
        assert callable(mod.get_cdn_config)
