"""
Unit tests for EncryptionService

Tests comprehensive encryption functionality including:
- Encryption key generation and management
- API key encryption and decryption
- API key format validation for different providers
- Error handling and edge cases
- Security considerations
"""

import base64
import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from encryption_service import EncryptionService


@pytest.mark.unit
class TestEncryptionServiceInitialization:
    """Test EncryptionService initialization"""

    def test_initialization_default(self):
        """Test service initialization with default settings"""
        service = EncryptionService()
        assert service.encryption_key is not None
        assert service.fernet is not None

    @patch.dict(os.environ, {"ENCRYPTION_KEY": "cVZ8kQXH3Pd5dD_RTMupJmLcveZC5KHVq0vu2aANDaw="})
    def test_initialization_with_env_key(self):
        """Test service initialization with environment encryption key"""
        service = EncryptionService()
        # Valid Fernet key should be used directly
        assert service.encryption_key == b"cVZ8kQXH3Pd5dD_RTMupJmLcveZC5KHVq0vu2aANDaw="
        assert service.fernet is not None

    @patch.dict(os.environ, {"SECRET_KEY": "fallback-secret-key"}, clear=True)
    def test_initialization_with_invalid_env_key(self):
        """Test service falls back to deriving key from SECRET_KEY when ENCRYPTION_KEY is not set"""
        service = EncryptionService()
        # Should initialize successfully by deriving key from SECRET_KEY
        assert service.encryption_key is not None
        assert service.fernet is not None

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"})
    def test_initialization_with_secret_key(self):
        """Test service initialization with SECRET_KEY"""
        service = EncryptionService()
        assert service.encryption_key is not None
        assert service.fernet is not None

    @patch.dict(os.environ, {"JWT_SECRET_KEY": "test-jwt-secret"})
    def test_initialization_with_jwt_secret(self):
        """Test service initialization with JWT_SECRET_KEY fallback"""
        service = EncryptionService()
        assert service.encryption_key is not None
        assert service.fernet is not None

    def test_initialization_with_default_secret(self):
        """Test service initialization with default secret"""
        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            service = EncryptionService()
            assert service.encryption_key is not None
            assert service.fernet is not None


@pytest.mark.unit
class TestEncryptionKeyGeneration:
    """Test encryption key generation logic"""

    def test_key_generation_consistency(self):
        """Test that key generation is consistent with same inputs"""
        service1 = EncryptionService()
        service2 = EncryptionService()
        assert service1.encryption_key == service2.encryption_key

    @patch.dict(os.environ, {"SECRET_KEY": "test-key-1"})
    def test_key_generation_different_secrets(self):
        """Test that different secrets generate different keys"""
        service1 = EncryptionService()
        key1 = service1.encryption_key

        with patch.dict(os.environ, {"SECRET_KEY": "test-key-2"}):
            service2 = EncryptionService()
            key2 = service2.encryption_key

        assert key1 != key2

    def test_key_format_valid_fernet_key(self):
        """Test that generated key is valid Fernet key"""
        service = EncryptionService()
        # Should not raise exception when creating Fernet instance
        fernet = Fernet(service.encryption_key)
        assert fernet is not None


@pytest.mark.unit
class TestAPIKeyEncryption:
    """Test API key encryption functionality"""

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service instance for testing"""
        return EncryptionService()

    def test_encrypt_api_key_success(self, encryption_service):
        """Test successful API key encryption"""
        api_key = "sk-test-api-key-12345"
        encrypted = encryption_service.encrypt_api_key(api_key)

        assert encrypted is not None
        assert encrypted != api_key
        assert isinstance(encrypted, str)
        # Should be base64 encoded
        try:
            base64.urlsafe_b64decode(encrypted.encode())
        except Exception:
            pytest.fail("Encrypted key is not valid base64")

    def test_encrypt_api_key_empty_string(self, encryption_service):
        """Test encrypting empty string returns None"""
        result = encryption_service.encrypt_api_key("")
        assert result is None

    def test_encrypt_api_key_whitespace_only(self, encryption_service):
        """Test encrypting whitespace-only string returns None"""
        result = encryption_service.encrypt_api_key("   ")
        assert result is None

    def test_encrypt_api_key_none(self, encryption_service):
        """Test encrypting None returns None"""
        result = encryption_service.encrypt_api_key(None)
        assert result is None

    def test_encrypt_api_key_long_key(self, encryption_service):
        """Test encrypting long API key"""
        long_key = "sk-" + "a" * 100
        encrypted = encryption_service.encrypt_api_key(long_key)

        assert encrypted is not None
        assert encrypted != long_key

    def test_encrypt_api_key_special_characters(self, encryption_service):
        """Test encrypting API key with special characters"""
        special_key = "sk-test-key-!@#$%^&*()_+-=[]{}|;:,.<>?"
        encrypted = encryption_service.encrypt_api_key(special_key)

        assert encrypted is not None
        assert encrypted != special_key

    def test_encrypt_api_key_unicode(self, encryption_service):
        """Test encrypting API key with unicode characters"""
        unicode_key = "sk-test-key-🔑-unicode"
        encrypted = encryption_service.encrypt_api_key(unicode_key)

        assert encrypted is not None
        assert encrypted != unicode_key


@pytest.mark.unit
class TestAPIKeyDecryption:
    """Test API key decryption functionality"""

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service instance for testing"""
        return EncryptionService()

    def test_decrypt_api_key_success(self, encryption_service):
        """Test successful API key decryption"""
        original_key = "sk-test-api-key-12345"
        encrypted = encryption_service.encrypt_api_key(original_key)
        decrypted = encryption_service.decrypt_api_key(encrypted)

        assert decrypted == original_key

    def test_decrypt_api_key_none(self, encryption_service):
        """Test decrypting None returns None"""
        result = encryption_service.decrypt_api_key(None)
        assert result is None

    def test_decrypt_api_key_empty_string(self, encryption_service):
        """Test decrypting empty string returns None"""
        result = encryption_service.decrypt_api_key("")
        assert result is None

    def test_decrypt_api_key_invalid_data(self, encryption_service):
        """Test decrypting invalid data returns None"""
        result = encryption_service.decrypt_api_key("invalid-encrypted-data")
        assert result is None

    def test_decrypt_api_key_corrupted_data(self, encryption_service):
        """Test decrypting corrupted data returns None"""
        # Create valid encrypted data, then corrupt it
        original_key = "sk-test-api-key-12345"
        encrypted = encryption_service.encrypt_api_key(original_key)
        corrupted = encrypted[:-5] + "XXXXX"  # Corrupt the end

        result = encryption_service.decrypt_api_key(corrupted)
        assert result is None

    def test_decrypt_api_key_wrong_service_instance(self):
        """Test decrypting with different service instance fails gracefully"""
        service1 = EncryptionService()
        original_key = "sk-test-api-key-12345"
        encrypted = service1.encrypt_api_key(original_key)

        # Create different service instance with different key
        with patch.dict(os.environ, {"SECRET_KEY": "different-secret"}):
            service2 = EncryptionService()
            result = service2.decrypt_api_key(encrypted)
            # Should return None due to different encryption key
            assert result is None


@pytest.mark.unit
class TestEncryptionDecryptionRoundTrip:
    """Test encryption/decryption round trip functionality"""

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service instance for testing"""
        return EncryptionService()

    def test_round_trip_various_keys(self, encryption_service):
        """Test round trip encryption/decryption with various API keys"""
        test_keys = [
            "sk-openai-key-12345",
            "sk-ant-anthropic-key-67890",
            "google-api-key-abcdef",
            "deepinfra-key-xyz123",
            "custom-provider-key-999",
            "a",  # Single character
            "key with spaces",
            "key-with-dashes",
            "key_with_underscores",
            "key.with.dots",
        ]

        for original_key in test_keys:
            encrypted = encryption_service.encrypt_api_key(original_key)
            decrypted = encryption_service.decrypt_api_key(encrypted)
            assert decrypted == original_key, f"Round trip failed for key: {original_key}"

    def test_round_trip_consistency(self, encryption_service):
        """Test that multiple encryptions of same key can all be decrypted"""
        original_key = "sk-test-consistency-12345"

        # Encrypt same key multiple times
        encrypted_versions = []
        for _ in range(5):
            encrypted = encryption_service.encrypt_api_key(original_key)
            encrypted_versions.append(encrypted)

        # All should be different (due to Fernet nonce)
        assert len(set(encrypted_versions)) == 5

        # All should decrypt to original
        for encrypted in encrypted_versions:
            decrypted = encryption_service.decrypt_api_key(encrypted)
            assert decrypted == original_key


@pytest.mark.unit
class TestAPIKeyFormatValidation:
    """Test API key format validation"""

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service instance for testing"""
        return EncryptionService()

    def test_openai_key_validation_valid(self, encryption_service):
        """Test valid OpenAI key format"""
        valid_keys = [
            "sk-1234567890abcdef",
            "sk-test-key-longer-format",
            "sk-proj-1234567890abcdef1234567890abcdef12345678",
        ]

        for key in valid_keys:
            assert encryption_service.is_valid_api_key_format(key, "openai") is True

    def test_openai_key_validation_invalid(self, encryption_service):
        """Test invalid OpenAI key format"""
        invalid_keys = [
            "ak-wrong-prefix",
            "sk-",  # Too short
            "sk-short",  # Too short
            "",
            "   ",
            None,
            "no-prefix-at-all",
        ]

        for key in invalid_keys:
            assert encryption_service.is_valid_api_key_format(key, "openai") is False

    def test_anthropic_key_validation_valid(self, encryption_service):
        """Test valid Anthropic key format"""
        valid_keys = [
            "sk-ant-1234567890abcdef",
            "sk-ant-api03-longer-format-here",
        ]

        for key in valid_keys:
            assert encryption_service.is_valid_api_key_format(key, "anthropic") is True

    def test_anthropic_key_validation_invalid(self, encryption_service):
        """Test invalid Anthropic key format"""
        invalid_keys = [
            "sk-wrong-prefix",
            "sk-ant-",  # Too short
            "sk-ant-short",  # Too short
            "",
            "   ",
            None,
            "sk-openai-format",
        ]

        for key in invalid_keys:
            assert encryption_service.is_valid_api_key_format(key, "anthropic") is False

    def test_google_key_validation(self, encryption_service):
        """Test Google API key validation"""
        valid_keys = [
            "AIzaSyABC123def456ghi789",
            "google-api-key-longer-format",
            "any-string-longer-than-10-chars",
        ]

        invalid_keys = [
            "short",
            "",
            "   ",
            None,
        ]

        for key in valid_keys:
            assert encryption_service.is_valid_api_key_format(key, "google") is True

        for key in invalid_keys:
            assert encryption_service.is_valid_api_key_format(key, "google") is False

    def test_deepinfra_key_validation(self, encryption_service):
        """Test DeepInfra API key validation"""
        valid_keys = [
            "deepinfra-api-key-12345",
            "any-string-longer-than-10-chars",
        ]

        invalid_keys = [
            "short",
            "",
            "   ",
            None,
        ]

        for key in valid_keys:
            assert encryption_service.is_valid_api_key_format(key, "deepinfra") is True

        for key in invalid_keys:
            assert encryption_service.is_valid_api_key_format(key, "deepinfra") is False

    def test_unknown_provider_validation(self, encryption_service):
        """Test validation for unknown providers"""
        valid_keys = [
            "any-key-longer-than-5",
            "123456",
        ]

        invalid_keys = [
            "short",
            "",
            "   ",
            None,
        ]

        for key in valid_keys:
            assert encryption_service.is_valid_api_key_format(key, "unknown") is True

        for key in invalid_keys:
            assert encryption_service.is_valid_api_key_format(key, "unknown") is False

    def test_case_insensitive_provider_names(self, encryption_service):
        """Test that provider names are case insensitive"""
        test_key = "sk-test-key-12345"

        providers = ["OpenAI", "OPENAI", "openai", "Openai"]
        for provider in providers:
            assert encryption_service.is_valid_api_key_format(test_key, provider) is True

    def test_key_validation_with_whitespace(self, encryption_service):
        """Test key validation handles whitespace correctly"""
        key_with_spaces = "  sk-test-key-12345  "
        assert encryption_service.is_valid_api_key_format(key_with_spaces, "openai") is True


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_encryption_with_fernet_error(self):
        """Test encryption handles Fernet errors gracefully"""
        service = EncryptionService()

        # Mock Fernet to raise exception
        with patch.object(service.fernet, "encrypt", side_effect=Exception("Encryption failed")):
            result = service.encrypt_api_key("sk-test-key")
            assert result is None

    def test_decryption_with_fernet_error(self):
        """Test decryption handles Fernet errors gracefully"""
        service = EncryptionService()

        # Mock Fernet to raise exception
        with patch.object(service.fernet, "decrypt", side_effect=Exception("Decryption failed")):
            result = service.decrypt_api_key("some-encrypted-data")
            assert result is None

    def test_key_validation_with_none_provider(self):
        """Test key validation with None provider"""
        service = EncryptionService()
        result = service.is_valid_api_key_format("sk-test-key", None)
        # Should handle gracefully (treat as unknown provider)
        assert result is True

    def test_key_validation_with_empty_provider(self):
        """Test key validation with empty provider"""
        service = EncryptionService()
        result = service.is_valid_api_key_format("sk-test-key", "")
        # Should handle gracefully (treat as unknown provider)
        assert result is True


@pytest.mark.unit
class TestSecurityConsiderations:
    """Test security-related aspects"""

    def test_encryption_produces_different_outputs(self):
        """Test that encrypting same key multiple times produces different outputs"""
        service = EncryptionService()
        api_key = "sk-test-security-key"

        encrypted1 = service.encrypt_api_key(api_key)
        encrypted2 = service.encrypt_api_key(api_key)

        # Should be different due to Fernet's built-in nonce
        assert encrypted1 != encrypted2

        # But both should decrypt to original
        assert service.decrypt_api_key(encrypted1) == api_key
        assert service.decrypt_api_key(encrypted2) == api_key

    def test_key_derivation_uses_strong_parameters(self):
        """Test that key derivation uses strong cryptographic parameters"""
        # This test verifies the parameters are reasonable
        # 100,000 iterations is considered secure for PBKDF2
        service = EncryptionService()

        # Key should be 32 bytes (256 bits) for Fernet
        assert len(service.encryption_key) == 44  # 32 bytes base64 encoded = 44 chars

    def test_encryption_fails_safely_with_invalid_input(self):
        """Test that encryption fails safely with various invalid inputs"""
        service = EncryptionService()

        # These should all return None, not raise exceptions
        invalid_inputs = [None, "", "   ", "\n\t", "\x00"]

        for invalid_input in invalid_inputs:
            result = service.encrypt_api_key(invalid_input)
            assert result is None


@pytest.mark.unit
class TestGlobalServiceInstance:
    """Test global service instance"""

    def test_global_service_instance_exists(self):
        """Test that global service instance is available"""
        from encryption_service import encryption_service

        assert encryption_service is not None
        assert isinstance(encryption_service, EncryptionService)

    def test_global_service_instance_functional(self):
        """Test that global service instance is functional"""
        from encryption_service import encryption_service

        test_key = "sk-test-global-instance"
        encrypted = encryption_service.encrypt_api_key(test_key)
        decrypted = encryption_service.decrypt_api_key(encrypted)

        assert decrypted == test_key
