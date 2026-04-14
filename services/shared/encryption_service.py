"""
Encryption service for securely storing user API keys
"""

import base64
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive data like API keys"""

    def __init__(self):
        self.encryption_key = self._get_or_create_encryption_key()
        self.fernet = Fernet(self.encryption_key)

    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key from environment or generate new one"""
        key_env = os.getenv("ENCRYPTION_KEY")
        if key_env:
            try:
                return key_env.encode()
            except Exception as e:
                logger.warning(f"Invalid ENCRYPTION_KEY in environment: {e}")

        # Generate key from secret key + salt
        password = os.getenv(
            "SECRET_KEY", os.getenv("JWT_SECRET_KEY", "default-secret-key")
        ).encode()
        salt = b"benger-api-key-encryption-salt"  # Fixed salt for consistency

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key

    def encrypt_api_key(self, api_key: str) -> Optional[str]:
        """Encrypt an API key for storage"""
        if not api_key or api_key.strip() == "":
            return None
        # Check for non-printable characters (invalid key content)
        if not api_key.isprintable() or api_key.strip() != api_key.strip().replace('\x00', ''):
            return None

        try:
            encrypted_data = self.fernet.encrypt(api_key.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt API key: {e}")
            return None

    def decrypt_api_key(self, encrypted_api_key: Optional[str]) -> Optional[str]:
        """Decrypt an API key for use"""
        if not encrypted_api_key:
            return None

        try:
            encrypted_data = base64.urlsafe_b64decode(encrypted_api_key.encode())
            decrypted_data = self.fernet.decrypt(encrypted_data)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            return None

    def is_valid_api_key_format(self, api_key: str, provider: str) -> bool:
        """Validate API key format for different providers"""
        if not api_key or api_key.strip() == "":
            return False

        api_key = api_key.strip()

        # Handle None or empty provider - treat as unknown provider
        if not provider:
            return len(api_key) > 5

        if provider.lower() == "openai":
            return api_key.startswith("sk-") and len(api_key) > 10
        elif provider.lower() == "anthropic":
            return api_key.startswith("sk-ant-") and len(api_key) > 15
        elif provider.lower() == "google":
            # Google API keys don't have standard prefix
            return len(api_key) > 10
        elif provider.lower() == "deepinfra":
            # DeepInfra keys don't have standard prefix
            return len(api_key) > 10

        return len(api_key) > 5  # Basic length check for unknown providers


# Global service instance
encryption_service = EncryptionService()