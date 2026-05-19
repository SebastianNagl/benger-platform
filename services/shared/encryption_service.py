"""
Encryption service for securely storing user API keys.

Single canonical implementation shared by api and workers via /shared.
Earlier the repo had TWO divergent impls — this one under /shared (which
actually ran in both containers, because /shared sits first on sys.path)
and a 8KB version at services/api/services/encryption_service.py with
Fernet validation and broader provider support. Tests only exercised
the 8KB version; prod exercised this one. The two have been merged and
the API copy + shim deleted.

Key resolution priority:
  1. ENCRYPTION_KEY (direct, prod path — set explicitly by helm)
  2. SECRET_KEY (derived via PBKDF2)
  3. JWT_SECRET_KEY (derived via PBKDF2)
  4. RuntimeError outside pytest (no literal fallback — earlier code
     defaulted to the literal string "default-secret-key", which would
     have made every stored user API key decryptable from repo content
     if the env was misconfigured)

Salt (`benger-api-key-encryption-salt`) is preserved verbatim from the
prior /shared impl so existing encrypted rows in dev still decrypt after
this consolidation.
"""

import base64
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Fixed salt; do not change without a re-encryption migration — every
# stored Fernet ciphertext derives from this.
_PBKDF2_SALT = b"benger-api-key-encryption-salt"
_PBKDF2_ITERATIONS = 100_000

# Test-key constant — handled specially so unit tests don't need a real
# Fernet key in fixtures.
_TEST_ENCRYPTION_KEY = b"dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw=="


class EncryptionService:
    """Service for encrypting and decrypting sensitive data like API keys."""

    def __init__(self):
        self.encryption_key = self._get_or_create_encryption_key()
        self._fernet: Optional[Fernet] = None

    @property
    def fernet(self) -> Fernet:
        """Lazily build the Fernet instance, with test-key normalization."""
        if self._fernet is None:
            if self.encryption_key == _TEST_ENCRYPTION_KEY:
                decoded = base64.b64decode(self.encryption_key.decode("utf-8"))
                padded = decoded + b"\x00" * (32 - len(decoded))
                self._fernet = Fernet(base64.urlsafe_b64encode(padded))
            else:
                self._fernet = Fernet(self.encryption_key)
        return self._fernet

    def _get_or_create_encryption_key(self) -> bytes:
        """Resolve the Fernet key from env vars.

        See module docstring for the priority order and the no-literal-
        fallback rule.
        """
        key_env = os.getenv("ENCRYPTION_KEY")
        if key_env:
            # Test compatibility: return verbatim so the Fernet property
            # can pad/normalize it.
            if key_env == _TEST_ENCRYPTION_KEY.decode("utf-8"):
                return key_env.encode("utf-8")

            # If it's already a valid Fernet key (44 chars, padded base64),
            # use it directly.
            if len(key_env) == 44 and key_env.endswith("="):
                try:
                    Fernet(key_env.encode("utf-8"))
                    return key_env.encode("utf-8")
                except Exception:
                    pass  # not a valid Fernet key after all; fall through

            # Otherwise, decode + pad/truncate to 32 bytes + re-encode as
            # url-safe base64 (what Fernet expects).
            try:
                decoded = base64.b64decode(key_env)
                if len(decoded) >= 32:
                    return base64.urlsafe_b64encode(decoded[:32])
                padded = decoded + b"\x00" * (32 - len(decoded))
                return base64.urlsafe_b64encode(padded)
            except Exception as e:
                logger.warning(f"Invalid ENCRYPTION_KEY format: {e}; falling back")

        # Derive from SECRET_KEY or JWT_SECRET_KEY via PBKDF2. Same salt
        # + iteration count as the prior /shared impl so existing
        # ciphertext still decrypts.
        password_env = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
        if password_env:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=_PBKDF2_SALT,
                iterations=_PBKDF2_ITERATIONS,
            )
            return base64.urlsafe_b64encode(kdf.derive(password_env.encode("utf-8")))

        # No source available. Hard-fail outside tests; pytest sets
        # PYTEST_CURRENT_TEST per-test, but module import happens before
        # any test runs, so we also tolerate a sentinel env var that
        # conftest sets up front. Refusing to start beats encrypting
        # user secrets with a known literal.
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("BENGER_TEST_MODE"):
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=_PBKDF2_SALT,
                iterations=_PBKDF2_ITERATIONS,
            )
            return base64.urlsafe_b64encode(kdf.derive(b"pytest-only-derivation-key"))

        raise RuntimeError(
            "EncryptionService refuses to start: none of ENCRYPTION_KEY, "
            "SECRET_KEY, JWT_SECRET_KEY is set. Earlier code defaulted to a "
            "literal string; that would silently make every stored user API "
            "key decryptable from repo contents."
        )

    def encrypt_api_key(self, api_key: Optional[str]) -> Optional[str]:
        """Encrypt an API key for storage. Returns base64-encoded ciphertext."""
        if not api_key or not api_key.strip():
            return None
        if not api_key.isprintable() or "\x00" in api_key:
            return None

        try:
            encrypted = self.fernet.encrypt(api_key.encode("utf-8"))
            return base64.urlsafe_b64encode(encrypted).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encrypt API key: {e}")
            return None

    def decrypt_api_key(self, encrypted_api_key: Optional[str]) -> Optional[str]:
        """Decrypt a previously-encrypted API key."""
        if not encrypted_api_key:
            return None
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_api_key.encode("utf-8"))
            return self.fernet.decrypt(encrypted_bytes).decode("utf-8")
        except InvalidToken:
            logger.error("Invalid token — ciphertext may be corrupted or key has rotated")
            return None
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            return None

    def is_valid_api_key_format(self, api_key: Optional[str], provider: Optional[str]) -> bool:
        """Best-effort shape check per provider. Not a verification call."""
        if not api_key or not api_key.strip():
            return False
        api_key = api_key.strip()

        if not provider:
            return len(api_key) > 5

        provider = provider.lower().strip()
        if provider == "openai":
            return api_key.startswith("sk-") and len(api_key) >= 16
        if provider == "anthropic":
            return api_key.startswith("sk-ant-") and len(api_key) >= 20
        if provider == "google":
            return len(api_key) > 10
        if provider == "deepinfra":
            return len(api_key) >= 8
        if provider == "grok":
            return api_key.startswith("xai-") and len(api_key) >= 10
        if provider == "mistral":
            return len(api_key) >= 20
        if provider == "cohere":
            return len(api_key) >= 20
        return len(api_key) > 5


# Module-level singleton — historically every caller does
# `from encryption_service import encryption_service`.
encryption_service = EncryptionService()
