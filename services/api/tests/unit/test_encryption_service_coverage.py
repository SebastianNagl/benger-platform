"""
Unit tests for services/encryption_service.py — 0% coverage (95 uncovered lines).

Tests EncryptionService including key generation, encrypt/decrypt, and API key validation.
"""

import base64
import os
from unittest.mock import patch

import pytest


class TestEncryptionServiceInit:
    """Test EncryptionService initialization and key derivation."""

    def test_default_init_uses_fallback_key(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove all key env vars to force fallback
            for k in ("ENCRYPTION_KEY", "SECRET_KEY", "JWT_SECRET_KEY"):
                os.environ.pop(k, None)
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            assert svc.encryption_key is not None
            assert len(svc.encryption_key) > 0

    def test_init_with_secret_key(self):
        with patch.dict(os.environ, {"SECRET_KEY": "my-secret-key-for-testing"}, clear=False):
            os.environ.pop("ENCRYPTION_KEY", None)
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            assert svc.encryption_key is not None

    def test_init_with_jwt_secret_key(self):
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "jwt-secret-for-test"}, clear=False):
            os.environ.pop("ENCRYPTION_KEY", None)
            os.environ.pop("SECRET_KEY", None)
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            assert svc.encryption_key is not None

    def test_init_with_valid_fernet_key(self):
        from cryptography.fernet import Fernet
        valid_key = Fernet.generate_key().decode('utf-8')
        with patch.dict(os.environ, {"ENCRYPTION_KEY": valid_key}, clear=False):
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            assert svc.encryption_key is not None

    def test_init_with_test_key(self):
        test_key = "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw=="
        with patch.dict(os.environ, {"ENCRYPTION_KEY": test_key}, clear=False):
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            assert svc.encryption_key == test_key.encode('utf-8')

    def test_init_with_short_base64_key(self):
        # A short base64 string that decodes to < 32 bytes
        short_key = base64.b64encode(b"short").decode('utf-8')
        with patch.dict(os.environ, {"ENCRYPTION_KEY": short_key}, clear=False):
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            assert svc.encryption_key is not None

    def test_init_with_long_base64_key(self):
        long_key = base64.b64encode(b"a" * 64).decode('utf-8')
        with patch.dict(os.environ, {"ENCRYPTION_KEY": long_key}, clear=False):
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            assert svc.encryption_key is not None

    def test_init_with_invalid_encryption_key_falls_back(self):
        with patch.dict(os.environ, {
            "ENCRYPTION_KEY": "not-valid-base64!!!",
            "SECRET_KEY": "fallback-secret"
        }, clear=False):
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            assert svc.encryption_key is not None


class TestEncryptDecrypt:
    """Test encrypt and decrypt operations."""

    def _make_service(self):
        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"}, clear=False):
            os.environ.pop("ENCRYPTION_KEY", None)
            from services.encryption_service import EncryptionService
            return EncryptionService()

    def test_encrypt_and_decrypt_roundtrip(self):
        svc = self._make_service()
        original = "sk-test-api-key-12345"
        encrypted = svc.encrypt_api_key(original)
        assert encrypted is not None
        assert encrypted != original
        decrypted = svc.decrypt_api_key(encrypted)
        assert decrypted == original

    def test_encrypt_none_returns_none(self):
        svc = self._make_service()
        assert svc.encrypt_api_key(None) is None

    def test_encrypt_empty_string_returns_none(self):
        svc = self._make_service()
        assert svc.encrypt_api_key("") is None

    def test_encrypt_whitespace_only_returns_none(self):
        svc = self._make_service()
        assert svc.encrypt_api_key("   ") is None

    def test_encrypt_null_byte_returns_none(self):
        svc = self._make_service()
        assert svc.encrypt_api_key("\x00") is None

    def test_decrypt_none_returns_none(self):
        svc = self._make_service()
        assert svc.decrypt_api_key(None) is None

    def test_decrypt_empty_returns_none(self):
        svc = self._make_service()
        assert svc.decrypt_api_key("") is None

    def test_decrypt_invalid_data_returns_none(self):
        svc = self._make_service()
        assert svc.decrypt_api_key("not-valid-encrypted-data") is None

    def test_decrypt_corrupted_base64_returns_none(self):
        svc = self._make_service()
        corrupted = base64.b64encode(b"corrupted-data").decode('utf-8')
        assert svc.decrypt_api_key(corrupted) is None

    def test_encrypt_unicode_api_key(self):
        svc = self._make_service()
        key = "sk-test-unicode-\u00e4\u00f6\u00fc"
        encrypted = svc.encrypt_api_key(key)
        assert encrypted is not None
        decrypted = svc.decrypt_api_key(encrypted)
        assert decrypted == key

    def test_encrypt_long_api_key(self):
        svc = self._make_service()
        key = "sk-" + "a" * 1000
        encrypted = svc.encrypt_api_key(key)
        assert encrypted is not None
        decrypted = svc.decrypt_api_key(encrypted)
        assert decrypted == key


class TestIsValidApiKeyFormat:
    """Test API key format validation."""

    def _make_service(self):
        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}, clear=False):
            os.environ.pop("ENCRYPTION_KEY", None)
            from services.encryption_service import EncryptionService
            return EncryptionService()

    def test_openai_valid(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("sk-1234567890abcdef", "openai") is True

    def test_openai_too_short(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("sk-abc", "openai") is False

    def test_openai_wrong_prefix(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("pk-1234567890abcdef", "openai") is False

    def test_anthropic_valid(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("sk-ant-123456789012345678", "anthropic") is True

    def test_anthropic_too_short(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("sk-ant-abc", "anthropic") is False

    def test_anthropic_wrong_prefix(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("sk-1234567890abcdef12345", "anthropic") is False

    def test_google_valid(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("AIzaSyB1234567890", "google") is True

    def test_google_too_short(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("short", "google") is False

    def test_deepinfra_valid(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("12345678", "deepinfra") is True

    def test_deepinfra_too_short(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("short", "deepinfra") is False

    def test_grok_valid(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("xai-1234567890", "grok") is True

    def test_grok_too_short(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("xai-12", "grok") is False

    def test_grok_wrong_prefix(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("sk-1234567890", "grok") is False

    def test_mistral_valid(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("a" * 25, "mistral") is True

    def test_mistral_too_short(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("short", "mistral") is False

    def test_cohere_valid(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("b" * 25, "cohere") is True

    def test_cohere_too_short(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("short", "cohere") is False

    def test_unknown_provider_valid(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("some-long-key", "unknown_provider") is True

    def test_unknown_provider_too_short(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("ab", "unknown_provider") is False

    def test_empty_key_all_providers(self):
        svc = self._make_service()
        for provider in ["openai", "anthropic", "google", "deepinfra", "grok", "mistral", "cohere"]:
            assert svc.is_valid_api_key_format("", provider) is False

    def test_whitespace_key_all_providers(self):
        svc = self._make_service()
        for provider in ["openai", "anthropic", "google"]:
            assert svc.is_valid_api_key_format("   ", provider) is False

    def test_none_provider(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("some-valid-key-12345", None) is True

    def test_case_insensitive_provider(self):
        svc = self._make_service()
        assert svc.is_valid_api_key_format("sk-1234567890abcdef", "OpenAI") is True
        assert svc.is_valid_api_key_format("sk-ant-123456789012345678", "ANTHROPIC") is True


class TestFernetProperty:
    """Test the lazy Fernet initialization."""

    def _make_service(self):
        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}, clear=False):
            os.environ.pop("ENCRYPTION_KEY", None)
            from services.encryption_service import EncryptionService
            return EncryptionService()

    def test_fernet_lazy_init(self):
        svc = self._make_service()
        assert svc._fernet is None
        _ = svc.fernet
        assert svc._fernet is not None

    def test_fernet_returns_same_instance(self):
        svc = self._make_service()
        f1 = svc.fernet
        f2 = svc.fernet
        assert f1 is f2

    def test_test_key_fernet_init(self):
        test_key = "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw=="
        with patch.dict(os.environ, {"ENCRYPTION_KEY": test_key}, clear=False):
            from services.encryption_service import EncryptionService
            svc = EncryptionService()
            # Should be able to create fernet from test key
            f = svc.fernet
            assert f is not None
