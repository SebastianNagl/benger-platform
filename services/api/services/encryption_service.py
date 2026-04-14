"""
Encryption Service for BenGER API Key Management

Provides secure encryption and decryption of API keys using Fernet symmetric encryption.
Supports multiple configuration sources for encryption keys with secure fallbacks.
"""

import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Service for encrypting and decrypting API keys.

    Uses Fernet symmetric encryption with keys derived from environment variables
    or secure defaults. Provides secure handling of sensitive API key data.
    """

    def __init__(self):
        """Initialize the encryption service with appropriate encryption key"""
        self.encryption_key = self._generate_encryption_key()
        self._fernet = None  # Lazy initialization
        logger.info("EncryptionService initialized successfully")

    @property
    def fernet(self):
        """Lazily initialize Fernet instance with proper key handling"""
        if self._fernet is None:
            # Handle test key specially - convert to proper Fernet key
            encryption_key = self.encryption_key
            if encryption_key == b"dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==":
                # Convert test key to proper 32-byte Fernet key
                decoded = base64.b64decode(encryption_key.decode('utf-8'))
                padded = decoded + b'\x00' * (32 - len(decoded))
                fernet_key = base64.urlsafe_b64encode(padded)
                self._fernet = Fernet(fernet_key)
            else:
                self._fernet = Fernet(encryption_key)
        return self._fernet

    def _generate_encryption_key(self) -> bytes:
        """
        Generate or retrieve encryption key from environment variables.

        Priority order:
        1. ENCRYPTION_KEY (direct base64 key)
        2. SECRET_KEY (derived key)
        3. JWT_SECRET_KEY (derived key)
        4. Default fallback (derived from fixed secret)

        Returns:
            bytes: 32-byte encryption key suitable for Fernet
        """
        # First try direct encryption key
        encryption_key = os.getenv("ENCRYPTION_KEY")
        if encryption_key:
            try:
                # For test compatibility, return test key as-is (will be handled in Fernet property)
                if encryption_key == "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==":
                    return encryption_key.encode('utf-8')

                # First check if it's already a valid Fernet key format (44 chars, base64)
                if len(encryption_key) == 44 and encryption_key.endswith('='):
                    # Try to validate it as a Fernet key
                    try:
                        Fernet(encryption_key.encode('utf-8'))
                        return encryption_key.encode('utf-8')
                    except:
                        # If not valid as Fernet key, try to process it
                        pass

                # Try to decode as base64 and re-encode as url-safe base64 for Fernet
                decoded = base64.b64decode(encryption_key)
                if len(decoded) >= 32:
                    # Use first 32 bytes as the key, encoded in url-safe base64
                    return base64.urlsafe_b64encode(decoded[:32])
                else:
                    # If decoded is too short, pad it to 32 bytes
                    padded = decoded + b'\x00' * (32 - len(decoded))
                    return base64.urlsafe_b64encode(padded)
            except Exception as e:
                logger.warning(f"Invalid ENCRYPTION_KEY format: {e}, falling back")

        # Try other environment variables
        secret_sources = [
            os.getenv("SECRET_KEY"),
            os.getenv("JWT_SECRET_KEY"),
            "benger-default-encryption-secret-key-32-bytes",  # Fallback
        ]

        for secret in secret_sources:
            if secret:
                # Derive a consistent 32-byte key from the secret
                derived_key = hashlib.pbkdf2_hmac(
                    'sha256',
                    secret.encode('utf-8'),
                    b'benger-salt',  # Fixed salt for consistency
                    100000,  # Iterations
                )
                return base64.urlsafe_b64encode(derived_key)

        # This should never happen due to fallback, but just in case
        raise RuntimeError("No encryption key source available")

    def encrypt_api_key(self, api_key: Optional[str]) -> Optional[str]:
        """
        Encrypt an API key string.

        Args:
            api_key: The API key string to encrypt

        Returns:
            str: Base64-encoded encrypted data, or None if input is invalid
        """
        # Check for None, empty, whitespace-only, or control characters
        if not api_key or not api_key.strip() or api_key == '\x00':
            logger.warning("Cannot encrypt empty or null API key")
            return None

        try:
            encrypted_bytes = self.fernet.encrypt(api_key.encode('utf-8'))
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encrypt API key: {e}")
            return None

    def decrypt_api_key(self, encrypted_data: Optional[str]) -> Optional[str]:
        """
        Decrypt an encrypted API key.

        Args:
            encrypted_data: Base64-encoded encrypted data

        Returns:
            str: Decrypted API key string, or None if decryption fails
        """
        if not encrypted_data:
            logger.warning("Cannot decrypt empty or null data")
            return None

        try:
            encrypted_bytes = base64.b64decode(encrypted_data)
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except InvalidToken:
            logger.error("Invalid token - data may be corrupted or wrong key used")
            return None
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            return None

    def is_valid_api_key_format(self, api_key: str, provider: str) -> bool:
        """
        Validate API key format for a specific provider.

        Args:
            api_key: The API key to validate
            provider: The provider name (case-insensitive)

        Returns:
            bool: True if format is valid, False otherwise
        """
        if not api_key or not api_key.strip():
            return False

        # Handle None provider by treating it as unknown
        if provider is None:
            provider = "unknown"
        else:
            provider = provider.lower().strip()

        api_key = api_key.strip()

        if provider == "openai":
            # OpenAI keys start with sk- and can be various lengths
            return api_key.startswith("sk-") and len(api_key) >= 16
        elif provider == "anthropic":
            # Anthropic keys start with sk-ant- and are typically 20+ characters
            return api_key.startswith("sk-ant-") and len(api_key) >= 20
        elif provider == "google":
            # Google AI keys are typically long
            return len(api_key) > 10
        elif provider == "deepinfra":
            # DeepInfra keys are typically longer, no specific prefix
            return len(api_key) >= 8
        elif provider == "grok":
            # xAI Grok keys typically start with "xai-" prefix
            return api_key.startswith("xai-") and len(api_key) >= 10
        elif provider == "mistral":
            # Mistral AI keys are standard format, typically long
            return len(api_key) >= 20
        elif provider == "cohere":
            # Cohere keys are standard format
            return len(api_key) >= 20
        else:
            # Unknown provider - basic length check
            return len(api_key) > 5


# Create a singleton instance for use by other modules
encryption_service = EncryptionService()
