"""
Organization API Key Service (Shared/Worker version) - Issue #1180

Slim version for worker context. Only provides key resolution.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class OrgApiKeyService:
    """Shared service for resolving organization API keys in worker context"""

    def __init__(self, encryption_service):
        self.encryption_service = encryption_service

    def _get_org_setting_require_private_keys(self, db: Session, org_id: str) -> bool:
        """Get the require_private_keys setting for an org. Defaults to True."""
        from models import Organization

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org or not org.settings:
            return True
        return org.settings.get("require_private_keys", True)

    def _get_org_api_key(self, db: Session, org_id: str, provider: str) -> Optional[str]:
        """Get decrypted org API key."""
        from models import OrganizationApiKey

        record = (
            db.query(OrganizationApiKey)
            .filter(
                OrganizationApiKey.organization_id == org_id,
                OrganizationApiKey.provider == provider.lower(),
            )
            .first()
        )
        if not record:
            return None
        return self.encryption_service.decrypt_api_key(record.encrypted_key)

    def resolve_api_key(
        self, db: Session, user_id: str, org_id: Optional[str], provider: str
    ) -> Optional[str]:
        """
        Resolve which API key to use based on context.

        - If org_id is None: use personal key
        - If org requires private keys: use personal key
        - If org provides keys: use org key (None if not set)
        """
        from user_api_key_service import user_api_key_service

        if not org_id:
            return user_api_key_service.get_user_api_key(db, user_id, provider)

        require_private = self._get_org_setting_require_private_keys(db, org_id)

        if require_private:
            return user_api_key_service.get_user_api_key(db, user_id, provider)
        else:
            # Org pays - use org key only (None if not set = provider unavailable)
            return self._get_org_api_key(db, org_id, provider)


# Create singleton instance
try:
    from encryption_service import encryption_service

    org_api_key_service = OrgApiKeyService(encryption_service)
except ImportError as e:
    logger.warning(f"encryption_service not available - org API key resolution disabled: {e}")
    org_api_key_service = None
