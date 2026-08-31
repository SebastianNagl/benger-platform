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

    def _get_org_api_key(
        self, db: Session, org_id: str, provider: str, group_id: Optional[str] = None
    ) -> Optional[str]:
        """Get decrypted org API key for one scope.

        ``group_id`` None = the org-wide key row. The predicate is always
        explicit — a bare (org, provider) filter would silently mix org-wide
        and group-scoped rows once groups exist.
        """
        from models import OrganizationApiKey

        query = db.query(OrganizationApiKey).filter(
            OrganizationApiKey.organization_id == org_id,
            OrganizationApiKey.provider == provider.lower(),
        )
        if group_id:
            query = query.filter(OrganizationApiKey.group_id == str(group_id))
        else:
            query = query.filter(OrganizationApiKey.group_id.is_(None))
        record = query.first()
        if not record:
            return None
        return self.encryption_service.decrypt_api_key(record.encrypted_key)

    def _user_may_spend_org_key(self, db: Session, user_id: str, org_id: str) -> bool:
        """Active org membership or superadmin — fail-closed.

        Mirrors the BYOM lane's ``_user_is_active_org_member`` gate: an org
        that pays (``require_private_keys`` False) pays for its members, not
        for anyone who reaches a dispatch with its id (unvalidated headers,
        historical first-org fallbacks).
        """
        try:
            from models import OrganizationMembership, User

            member = (
                db.query(OrganizationMembership)
                .filter(
                    OrganizationMembership.user_id == str(user_id),
                    OrganizationMembership.organization_id == str(org_id),
                    OrganizationMembership.is_active == True,  # noqa: E712
                )
                .first()
            )
            if member is not None:
                return True
            row = (
                db.query(User.is_superadmin).filter(User.id == str(user_id)).first()
            )
            return bool(row and row[0])
        except Exception:
            logger.warning(
                "org-key membership check failed for user %s / org %s; refusing org key",
                user_id,
                org_id,
                exc_info=True,
            )
            return False

    def resolve_api_key(
        self,
        db: Session,
        user_id: str,
        org_id: Optional[str],
        provider: str,
        *,
        org_billing_authorized: bool = False,
        project_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolve which API key to use based on context.

        - If org_id is None: use personal key
        - If org requires private keys: use personal key
        - If org provides keys: use org key (None if not set) — but only for
          an active member or a superadmin; anyone else degrades to their
          personal key ("individual pays") instead of spending org money.

        ``org_billing_authorized`` is a policy-asserted flag: set True ONLY
        by code that re-derived the caller's consumer entitlement from the
        DB in the same process (the extended dispatch policy / flashcard
        worker recompute) — never from HTTP or task-payload input. It
        bypasses only the membership gate, never the require_private_keys
        check: an org that requires private keys is never charged.

        ``project_id`` selects WHICH org key row is spent: when the
        project's attachment to ``org_id`` is scoped to an organization
        group, that group's key is tried first, falling back to the org-wide
        row (a group without its own key spends the org's shared pool, never
        another group's). The key follows the PROJECT's attachment, not the
        dispatching user's groups — an org admin grading a group exam spends
        that group's key. Callers that omit ``project_id`` resolve the
        org-wide row only.
        """
        from user_api_key_service import user_api_key_service

        if not org_id:
            return user_api_key_service.get_user_api_key(db, user_id, provider)

        require_private = self._get_org_setting_require_private_keys(db, org_id)

        if require_private:
            return user_api_key_service.get_user_api_key(db, user_id, provider)
        if not org_billing_authorized and not self._user_may_spend_org_key(
            db, user_id, org_id
        ):
            logger.warning(
                "org-pays key refused: user %s is not an active member of org %s; "
                "falling back to the personal key",
                user_id,
                org_id,
            )
            return user_api_key_service.get_user_api_key(db, user_id, provider)
        # Org pays - use org key only (None if not set = provider unavailable).
        # Group-scoped projects spend their group's key first.
        if project_id:
            from org_groups import resolve_project_group_for_org

            group_id = resolve_project_group_for_org(db, project_id, org_id)
            if group_id:
                group_key = self._get_org_api_key(db, org_id, provider, group_id)
                if group_key is not None:
                    return group_key
        return self._get_org_api_key(db, org_id, provider)


# Create singleton instance
try:
    from encryption_service import encryption_service

    org_api_key_service = OrgApiKeyService(encryption_service)
except ImportError as e:
    logger.warning(f"encryption_service not available - org API key resolution disabled: {e}")
    org_api_key_service = None
