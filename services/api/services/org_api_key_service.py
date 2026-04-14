"""
Organization API Key Service for BenGER (Issue #1180)

Manages organization-level API keys with encryption,
key resolution based on org settings, and provider availability.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from models import Organization, OrganizationApiKey

logger = logging.getLogger(__name__)


class OrgApiKeyService:
    """Service for managing organization-level API keys"""

    SUPPORTED_PROVIDERS = [
        "openai",
        "anthropic",
        "google",
        "deepinfra",
        "grok",
        "mistral",
        "cohere",
    ]

    PROVIDER_DISPLAY_NAMES = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google",
        "deepinfra": "DeepInfra",
        "grok": "Grok",
        "mistral": "Mistral",
        "cohere": "Cohere",
    }

    def __init__(self, encryption_service):
        self.encryption_service = encryption_service
        logger.info("OrgApiKeyService initialized")

    def _get_org_setting_require_private_keys(self, db: Session, org_id: str) -> bool:
        """Get the require_private_keys setting for an org. Defaults to True."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org or not org.settings:
            return True
        return org.settings.get("require_private_keys", True)

    def set_org_api_key(
        self, db: Session, org_id: str, provider: str, api_key: str, created_by: str
    ) -> bool:
        """Set an encrypted API key for an organization and provider."""
        try:
            provider = provider.lower()
            if provider not in self.SUPPORTED_PROVIDERS:
                logger.error(f"Unsupported provider: {provider}")
                return False

            if not self.encryption_service.is_valid_api_key_format(api_key, provider):
                logger.error(f"Invalid API key format for provider {provider}")
                return False

            encrypted_key = self.encryption_service.encrypt_api_key(api_key)
            if not encrypted_key:
                logger.error("Failed to encrypt API key")
                return False

            # Upsert: update if exists, insert if not
            existing = (
                db.query(OrganizationApiKey)
                .filter(
                    OrganizationApiKey.organization_id == org_id,
                    OrganizationApiKey.provider == provider,
                )
                .first()
            )

            if existing:
                existing.encrypted_key = encrypted_key
                existing.updated_at = datetime.now(timezone.utc)
            else:
                new_key = OrganizationApiKey(
                    id=str(uuid.uuid4()),
                    organization_id=org_id,
                    provider=provider,
                    encrypted_key=encrypted_key,
                    created_by=created_by,
                )
                db.add(new_key)

            db.commit()
            logger.info(f"Org API key set for org {org_id}, provider {provider}")
            return True

        except Exception as e:
            logger.error(f"Failed to set org API key: {e}")
            db.rollback()
            return False

    def get_org_api_key(self, db: Session, org_id: str, provider: str) -> Optional[str]:
        """Get decrypted API key for an organization and provider."""
        try:
            provider = provider.lower()
            if provider not in self.SUPPORTED_PROVIDERS:
                return None

            record = (
                db.query(OrganizationApiKey)
                .filter(
                    OrganizationApiKey.organization_id == org_id,
                    OrganizationApiKey.provider == provider,
                )
                .first()
            )

            if not record:
                return None

            return self.encryption_service.decrypt_api_key(record.encrypted_key)

        except Exception as e:
            logger.error(f"Failed to get org API key: {e}")
            return None

    def remove_org_api_key(self, db: Session, org_id: str, provider: str) -> bool:
        """Remove API key for an organization and provider."""
        try:
            provider = provider.lower()
            if provider not in self.SUPPORTED_PROVIDERS:
                return False

            record = (
                db.query(OrganizationApiKey)
                .filter(
                    OrganizationApiKey.organization_id == org_id,
                    OrganizationApiKey.provider == provider,
                )
                .first()
            )

            if not record:
                return False

            db.delete(record)
            db.commit()
            logger.info(f"Org API key removed for org {org_id}, provider {provider}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove org API key: {e}")
            db.rollback()
            return False

    def get_org_api_key_status(self, db: Session, org_id: str) -> Dict[str, bool]:
        """Get API key status for all providers for an organization."""
        try:
            records = (
                db.query(OrganizationApiKey)
                .filter(OrganizationApiKey.organization_id == org_id)
                .all()
            )
            providers_with_keys = {r.provider for r in records}

            return {
                provider: provider in providers_with_keys for provider in self.SUPPORTED_PROVIDERS
            }

        except Exception as e:
            logger.error(f"Failed to get org API key status: {e}")
            return {}

    def get_org_available_providers(self, db: Session, org_id: str) -> List[str]:
        """Get display names of providers for which org has API keys."""
        status = self.get_org_api_key_status(db, org_id)
        return [
            self.PROVIDER_DISPLAY_NAMES[provider] for provider, has_key in status.items() if has_key
        ]

    def resolve_api_key(
        self, db: Session, user_id: str, org_id: Optional[str], provider: str
    ) -> Optional[str]:
        """
        Resolve which API key to use based on context.

        - If org_id is None: use personal key (backward compat / private context)
        - If org requires private keys: use personal key
        - If org provides keys: use org key (None if org hasn't set it)
        """
        from user_api_key_service import user_api_key_service

        if not org_id:
            # Private context - always personal key
            return user_api_key_service.get_user_api_key(db, user_id, provider)

        require_private = self._get_org_setting_require_private_keys(db, org_id)

        if require_private:
            # Members pay - use personal key
            return user_api_key_service.get_user_api_key(db, user_id, provider)
        else:
            # Org pays - use org key only (None if not set = provider unavailable)
            return self.get_org_api_key(db, org_id, provider)

    def get_available_providers_for_context(
        self, db: Session, user_id: str, org_id: Optional[str]
    ) -> List[str]:
        """
        Get provider display names based on context.

        - Private context or org with require_private_keys=true: user's personal providers
        - Org with require_private_keys=false: org's providers
        """
        from user_api_key_service import user_api_key_service

        if not org_id:
            return user_api_key_service.get_user_available_providers(db, user_id)

        require_private = self._get_org_setting_require_private_keys(db, org_id)

        if require_private:
            return user_api_key_service.get_user_available_providers(db, user_id)
        else:
            return self.get_org_available_providers(db, org_id)


# Create singleton instance
try:
    from encryption_service import encryption_service

    org_api_key_service = OrgApiKeyService(encryption_service)
except ImportError:
    org_api_key_service = None
