"""
Shared services module for BenGER

This module contains shared services that are used across multiple services
to eliminate code duplication and ensure consistency.
"""

from .encryption_service import EncryptionService, encryption_service
from .user_api_key_service import UserApiKeyService, create_user_api_key_service

# Note: `bg_statistics` is intentionally NOT eagerly imported here. Callers
# use `from bg_statistics import ...` directly so the heavy AI-service
# initialization above doesn't run for callers that only need the stats helpers.

__all__ = [
    "EncryptionService",
    "encryption_service",
    "UserApiKeyService",
    "create_user_api_key_service",
]