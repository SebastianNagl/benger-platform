"""
Organization API Key Service for BenGER (Issue #1180)

Manages organization-level API keys with encryption,
key resolution based on org settings, and provider availability.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
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

    def _get_org_setting_require_private_keys(
        self, db: Session, org_id: str, group_id: Optional[str] = None
    ) -> bool:
        """Effective require_private_keys for the org, or for one of its
        groups (the group's override, else the org's). Defaults to True."""
        from org_groups import require_private_keys_for

        return require_private_keys_for(db, org_id, group_id)

    @staticmethod
    def _group_scope_filter(query, group_id: Optional[str]):
        """Apply the MANDATORY group-scope predicate to a sync key query.

        Every read/write against ``organization_api_keys`` must state its
        scope explicitly — a bare (org, provider) filter would silently mix
        the org-wide row and group rows once groups exist (an org-wide
        upsert could overwrite a group key, or a get could decrypt one).
        """
        if group_id:
            return query.filter(OrganizationApiKey.group_id == str(group_id))
        return query.filter(OrganizationApiKey.group_id.is_(None))

    def set_org_api_key(
        self,
        db: Session,
        org_id: str,
        provider: str,
        api_key: str,
        created_by: str,
        group_id: Optional[str] = None,
    ) -> bool:
        """Set an encrypted API key for an organization and provider.

        ``group_id`` None = the org-wide key row; set = that group's row.
        """
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
            existing = self._group_scope_filter(
                db.query(OrganizationApiKey).filter(
                    OrganizationApiKey.organization_id == org_id,
                    OrganizationApiKey.provider == provider,
                ),
                group_id,
            ).first()

            if existing:
                existing.encrypted_key = encrypted_key
                existing.updated_at = datetime.now(timezone.utc)
            else:
                new_key = OrganizationApiKey(
                    id=str(uuid.uuid4()),
                    organization_id=org_id,
                    provider=provider,
                    group_id=str(group_id) if group_id else None,
                    encrypted_key=encrypted_key,
                    created_by=created_by,
                )
                db.add(new_key)

            db.commit()
            logger.info(
                f"Org API key set for org {org_id}, provider {provider}, "
                f"scope {group_id or 'org-wide'}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to set org API key: {e}")
            db.rollback()
            return False

    def get_org_api_key(
        self, db: Session, org_id: str, provider: str, group_id: Optional[str] = None
    ) -> Optional[str]:
        """Get decrypted API key for an organization and provider (one scope)."""
        try:
            provider = provider.lower()
            if provider not in self.SUPPORTED_PROVIDERS:
                return None

            record = self._group_scope_filter(
                db.query(OrganizationApiKey).filter(
                    OrganizationApiKey.organization_id == org_id,
                    OrganizationApiKey.provider == provider,
                ),
                group_id,
            ).first()

            if not record:
                return None

            return self.encryption_service.decrypt_api_key(record.encrypted_key)

        except Exception as e:
            logger.error(f"Failed to get org API key: {e}")
            return None

    def remove_org_api_key(
        self, db: Session, org_id: str, provider: str, group_id: Optional[str] = None
    ) -> bool:
        """Remove API key for an organization and provider (one scope)."""
        try:
            provider = provider.lower()
            if provider not in self.SUPPORTED_PROVIDERS:
                return False

            record = self._group_scope_filter(
                db.query(OrganizationApiKey).filter(
                    OrganizationApiKey.organization_id == org_id,
                    OrganizationApiKey.provider == provider,
                ),
                group_id,
            ).first()

            if not record:
                return False

            db.delete(record)
            db.commit()
            logger.info(
                f"Org API key removed for org {org_id}, provider {provider}, "
                f"scope {group_id or 'org-wide'}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to remove org API key: {e}")
            db.rollback()
            return False

    def get_org_api_key_status(
        self, db: Session, org_id: str, group_id: Optional[str] = None
    ) -> Dict[str, bool]:
        """Get API key status for all providers for one scope of an org."""
        try:
            records = self._group_scope_filter(
                db.query(OrganizationApiKey).filter(
                    OrganizationApiKey.organization_id == org_id
                ),
                group_id,
            ).all()
            providers_with_keys = {r.provider for r in records}

            return {
                provider: provider in providers_with_keys for provider in self.SUPPORTED_PROVIDERS
            }

        except Exception as e:
            logger.error(f"Failed to get org API key status: {e}")
            return {}

    def get_org_available_providers(
        self, db: Session, org_id: str, group_id: Optional[str] = None
    ) -> List[str]:
        """Get display names of providers for which org has API keys (one scope)."""
        status = self.get_org_api_key_status(db, org_id, group_id)
        return [
            self.PROVIDER_DISPLAY_NAMES[provider] for provider, has_key in status.items() if has_key
        ]

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
            row = db.query(User.is_superadmin).filter(User.id == str(user_id)).first()
            return bool(row and row[0])
        except Exception:
            logger.warning(
                f"org-key membership check failed for user {user_id} / org {org_id}; "
                "refusing org key",
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
        group_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolve which API key to use based on context.

        - If org_id is None: use personal key (backward compat / private context)
        - If members pay in the scope: use personal key
        - If the org provides keys in the scope: use org key (None if not
          set) — but only for an active member or a superadmin; anyone else
          degrades to their personal key ("individual pays") instead of
          spending org money.

        The scope is the project's attachment group (or ``group_id`` below);
        a group's own ``require_private_keys`` overrides the org's
        (``org_groups.require_private_keys_for``).

        ``org_billing_authorized`` is a policy-asserted flag: set True ONLY
        by code that re-derived the caller's consumer entitlement from the
        DB in the same process — never from HTTP or task-payload input. It
        bypasses only the membership gate, never the require_private_keys
        check: a scope whose members pay is never charged.

        ``project_id`` selects the scope and WHICH org key row is spent: when
        the project's attachment to ``org_id`` is scoped to an organization
        group, that group's setting decides who pays and that group's key is
        tried first, falling back to the org-wide row (a group without its own key spends the org's shared pool, never
        another group's). The key follows the PROJECT's attachment, not the
        dispatching user's groups. Callers that omit ``project_id`` resolve
        the org-wide row only. ``group_id`` is that choice before the project
        exists (the creation wizard), honored only without ``project_id`` and
        only for a caller who may create a project in that group
        (``org_groups.user_may_scope_to_group``); otherwise ignored. Kept in
        lockstep with ``services/shared/shared_org_api_key_service.py``.
        """
        from services.user_api_key_service import user_api_key_service

        if not org_id:
            # Private context - always personal key
            return user_api_key_service.get_user_api_key(db, user_id, provider)

        # The scope: the project's attachment group, or the group a project
        # being created will be scoped to (only for someone allowed to).
        attachment_group_id = None
        if project_id:
            from org_groups import resolve_project_group_for_org

            attachment_group_id = resolve_project_group_for_org(db, project_id, org_id)
        elif group_id:
            from org_groups import user_may_scope_to_group

            if user_may_scope_to_group(db, user_id, org_id, group_id):
                attachment_group_id = str(group_id)

        require_private = self._get_org_setting_require_private_keys(
            db, org_id, attachment_group_id
        )

        if require_private:
            # Members pay - use personal key
            return user_api_key_service.get_user_api_key(db, user_id, provider)
        if not org_billing_authorized and not self._user_may_spend_org_key(
            db, user_id, org_id
        ):
            logger.warning(
                f"org-pays key refused: user {user_id} is not an active member of "
                f"org {org_id}; falling back to the personal key"
            )
            return user_api_key_service.get_user_api_key(db, user_id, provider)
        # Org pays - use org key only (None if not set = provider unavailable).
        # Group-scoped projects spend their group's key first.
        if attachment_group_id:
            group_key = self.get_org_api_key(db, org_id, provider, attachment_group_id)
            if group_key is not None:
                return group_key
        return self.get_org_api_key(db, org_id, provider)

    def _user_group_ids_in_org(self, db: Session, user_id: str, org_id: str) -> List[str]:
        """Group ids the user belongs to WITHIN this org (sync)."""
        return [gid for gid, _ in self._user_groups_in_org(db, user_id, org_id)]

    def _user_groups_in_org(self, db: Session, user_id: str, org_id: str) -> list:
        """``(group_id, require_private_keys override)`` of the user's groups
        WITHIN this org (sync)."""
        from models import OrganizationGroup, OrganizationGroupMembership

        rows = (
            db.query(
                OrganizationGroupMembership.group_id,
                OrganizationGroup.require_private_keys,
            )
            .join(
                OrganizationGroup,
                OrganizationGroup.id == OrganizationGroupMembership.group_id,
            )
            .filter(
                OrganizationGroupMembership.user_id == str(user_id),
                OrganizationGroup.organization_id == str(org_id),
            )
            .all()
        )
        return [(r[0], r[1]) for r in rows]

    @staticmethod
    def _plan_provider_scopes(org_settings, scopes) -> tuple:
        """Which key rows a member may spend across ``scopes`` and whether
        personal keys apply somewhere.

        ``scopes`` are ``(group_id or None, override)`` pairs; None is the
        org-wide scope. A paying group spends its key, then the org-wide key;
        a members-pay scope uses the personal keys. Returns
        ``(personal, key_group_ids, include_org_wide)``.
        """
        from org_groups import effective_require_private_keys

        personal = False
        key_groups: List[str] = []
        org_wide = False
        for scope_group, override in scopes:
            if effective_require_private_keys(org_settings, override):
                personal = True
                continue
            org_wide = True
            if scope_group:
                key_groups.append(str(scope_group))
        return personal, key_groups, org_wide

    def _providers_for_scopes(
        self, db: Session, org_id: str, group_ids: List[str]
    ) -> List[str]:
        """Display names of providers with a key in the org-wide pool OR any
        of the given group scopes (sync)."""
        from sqlalchemy import or_ as _or

        scope_clause = OrganizationApiKey.group_id.is_(None)
        if group_ids:
            scope_clause = _or(
                scope_clause, OrganizationApiKey.group_id.in_(group_ids)
            )
        records = (
            db.query(OrganizationApiKey.provider)
            .filter(OrganizationApiKey.organization_id == org_id, scope_clause)
            .all()
        )
        providers_with_keys = {r[0] for r in records}
        return [
            self.PROVIDER_DISPLAY_NAMES[p]
            for p in self.SUPPORTED_PROVIDERS
            if p in providers_with_keys
        ]

    def get_available_providers_for_context(
        self,
        db: Session,
        user_id: str,
        org_id: Optional[str],
        project_id: Optional[str] = None,
    ) -> List[str]:
        """
        Get provider display names based on context.

        - Private context or non-member: user's personal providers
        - With ``project_id``: the project's scope only (its attachment
          group's setting, else the org's) — the personal providers when
          members pay there, else the group's keys plus the org-wide pool.
        - Without: the union over the org-wide scope and every group the
          user belongs to in that org, each by its own setting (an org whose
          keys are all group-scoped must not report zero providers to group
          members).

        Members only — mirrors resolve_api_key so the UI never advertises a
        provider the key resolution would refuse. Deliberately does NOT
        model consumer inheritance: key-management UI stays member-scoped;
        the who-pays surface for consumers is the billing/grading-payer
        endpoint.
        """
        from org_groups import resolve_project_group_for_org
        from services.user_api_key_service import user_api_key_service

        if not org_id or not self._user_may_spend_org_key(db, user_id, org_id):
            return user_api_key_service.get_user_available_providers(db, user_id)

        org = db.query(Organization).filter(Organization.id == org_id).first()
        org_settings = org.settings if org is not None else None
        if project_id:
            scope_group = resolve_project_group_for_org(db, project_id, org_id)
            override = self._group_override(db, org_id, scope_group) if scope_group else None
            scopes = [(scope_group, override)]
        else:
            scopes = [(None, None)] + self._user_groups_in_org(db, user_id, org_id)
        personal, key_groups, org_wide = self._plan_provider_scopes(org_settings, scopes)

        providers = set()
        if personal:
            providers.update(user_api_key_service.get_user_available_providers(db, user_id))
        if org_wide:
            providers.update(self._providers_for_scopes(db, org_id, key_groups))
        return self._ordered_display_names(providers)

    def _group_override(self, db: Session, org_id: str, group_id: str):
        """A group's require_private_keys override (None = follow the org)."""
        from models import OrganizationGroup

        row = (
            db.query(OrganizationGroup.require_private_keys)
            .filter(
                OrganizationGroup.id == str(group_id),
                OrganizationGroup.organization_id == str(org_id),
            )
            .first()
        )
        return row[0] if row is not None else None

    def _ordered_display_names(self, display_names) -> List[str]:
        """Display names in SUPPORTED_PROVIDERS order, deduplicated."""
        names = set(display_names)
        return [
            self.PROVIDER_DISPLAY_NAMES[p]
            for p in self.SUPPORTED_PROVIDERS
            if self.PROVIDER_DISPLAY_NAMES[p] in names
        ]

    # ------------------------------------------------------------------
    # Async twins (async DB lane). Share pure ``_build_select_*`` builders
    # with the sync methods above; the sync methods stay byte-identical.
    # ------------------------------------------------------------------

    @staticmethod
    def _build_select_org(org_id: str):
        return select(Organization).where(Organization.id == org_id)

    @staticmethod
    def _build_select_org_key(org_id: str, provider: str, group_id: Optional[str] = None):
        stmt = select(OrganizationApiKey).where(
            OrganizationApiKey.organization_id == org_id,
            OrganizationApiKey.provider == provider,
        )
        if group_id:
            return stmt.where(OrganizationApiKey.group_id == str(group_id))
        return stmt.where(OrganizationApiKey.group_id.is_(None))

    @staticmethod
    def _build_select_org_keys(org_id: str, group_id: Optional[str] = None):
        stmt = select(OrganizationApiKey).where(
            OrganizationApiKey.organization_id == org_id
        )
        if group_id:
            return stmt.where(OrganizationApiKey.group_id == str(group_id))
        return stmt.where(OrganizationApiKey.group_id.is_(None))

    async def _get_org_setting_require_private_keys_async(
        self, db: AsyncSession, org_id: str, group_id: Optional[str] = None
    ) -> bool:
        """Async twin of :meth:`_get_org_setting_require_private_keys`."""
        from org_groups import require_private_keys_for_async

        return await require_private_keys_for_async(db, org_id, group_id)

    async def set_org_api_key_async(
        self,
        db: AsyncSession,
        org_id: str,
        provider: str,
        api_key: str,
        created_by: str,
        group_id: Optional[str] = None,
    ) -> bool:
        """Async twin of :meth:`set_org_api_key`."""
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

            result = await db.execute(
                self._build_select_org_key(org_id, provider, group_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.encrypted_key = encrypted_key
                existing.updated_at = datetime.now(timezone.utc)
            else:
                new_key = OrganizationApiKey(
                    id=str(uuid.uuid4()),
                    organization_id=org_id,
                    provider=provider,
                    group_id=str(group_id) if group_id else None,
                    encrypted_key=encrypted_key,
                    created_by=created_by,
                )
                db.add(new_key)

            await db.commit()
            logger.info(
                f"Org API key set for org {org_id}, provider {provider}, "
                f"scope {group_id or 'org-wide'}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to set org API key: {e}")
            await db.rollback()
            return False

    async def get_org_api_key_async(
        self, db: AsyncSession, org_id: str, provider: str, group_id: Optional[str] = None
    ) -> Optional[str]:
        """Async twin of :meth:`get_org_api_key`."""
        try:
            provider = provider.lower()
            if provider not in self.SUPPORTED_PROVIDERS:
                return None

            result = await db.execute(
                self._build_select_org_key(org_id, provider, group_id)
            )
            record = result.scalar_one_or_none()

            if not record:
                return None

            return self.encryption_service.decrypt_api_key(record.encrypted_key)

        except Exception as e:
            logger.error(f"Failed to get org API key: {e}")
            return None

    async def remove_org_api_key_async(
        self, db: AsyncSession, org_id: str, provider: str, group_id: Optional[str] = None
    ) -> bool:
        """Async twin of :meth:`remove_org_api_key`."""
        try:
            provider = provider.lower()
            if provider not in self.SUPPORTED_PROVIDERS:
                return False

            result = await db.execute(
                self._build_select_org_key(org_id, provider, group_id)
            )
            record = result.scalar_one_or_none()

            if not record:
                return False

            await db.delete(record)
            await db.commit()
            logger.info(
                f"Org API key removed for org {org_id}, provider {provider}, "
                f"scope {group_id or 'org-wide'}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to remove org API key: {e}")
            await db.rollback()
            return False

    async def get_org_api_key_status_async(
        self, db: AsyncSession, org_id: str, group_id: Optional[str] = None
    ) -> Dict[str, bool]:
        """Async twin of :meth:`get_org_api_key_status`."""
        try:
            result = await db.execute(self._build_select_org_keys(org_id, group_id))
            records = result.scalars().all()
            providers_with_keys = {r.provider for r in records}

            return {
                provider: provider in providers_with_keys for provider in self.SUPPORTED_PROVIDERS
            }

        except Exception as e:
            logger.error(f"Failed to get org API key status: {e}")
            return {}

    async def get_org_available_providers_async(
        self, db: AsyncSession, org_id: str, group_id: Optional[str] = None
    ) -> List[str]:
        """Async twin of :meth:`get_org_available_providers`."""
        status = await self.get_org_api_key_status_async(db, org_id, group_id)
        return [
            self.PROVIDER_DISPLAY_NAMES[provider] for provider, has_key in status.items() if has_key
        ]

    async def _user_may_spend_org_key_async(
        self, db: AsyncSession, user_id: str, org_id: str
    ) -> bool:
        """Async twin of :meth:`_user_may_spend_org_key`."""
        try:
            from models import OrganizationMembership, User

            member = (
                (
                    await db.execute(
                        select(OrganizationMembership.id).where(
                            OrganizationMembership.user_id == str(user_id),
                            OrganizationMembership.organization_id == str(org_id),
                            OrganizationMembership.is_active.is_(True),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if member is not None:
                return True
            row = (
                (await db.execute(select(User.is_superadmin).where(User.id == str(user_id))))
                .scalars()
                .first()
            )
            return bool(row)
        except Exception:
            logger.warning(
                f"org-key membership check failed for user {user_id} / org {org_id}; "
                "refusing org key",
                exc_info=True,
            )
            return False

    async def get_available_providers_for_context_async(
        self,
        db: AsyncSession,
        user_id: str,
        org_id: Optional[str],
        project_id: Optional[str] = None,
    ) -> List[str]:
        """Async twin of :meth:`get_available_providers_for_context`."""
        from sqlalchemy import or_ as _or

        from models import OrganizationGroup, OrganizationGroupMembership
        from org_groups import resolve_project_group_for_org_async
        from services.user_api_key_service import user_api_key_service

        if not org_id or not await self._user_may_spend_org_key_async(db, user_id, org_id):
            return await user_api_key_service.get_user_available_providers_async(db, user_id)

        org_settings = (
            await db.execute(select(Organization.settings).where(Organization.id == org_id))
        ).scalar_one_or_none()
        if project_id:
            scope_group = await resolve_project_group_for_org_async(db, project_id, org_id)
            override = None
            if scope_group:
                override = (
                    await db.execute(
                        select(OrganizationGroup.require_private_keys).where(
                            OrganizationGroup.id == scope_group,
                            OrganizationGroup.organization_id == str(org_id),
                        )
                    )
                ).scalar_one_or_none()
            scopes = [(scope_group, override)]
        else:
            group_rows = await db.execute(
                select(
                    OrganizationGroupMembership.group_id,
                    OrganizationGroup.require_private_keys,
                )
                .join(
                    OrganizationGroup,
                    OrganizationGroup.id == OrganizationGroupMembership.group_id,
                )
                .where(
                    OrganizationGroupMembership.user_id == str(user_id),
                    OrganizationGroup.organization_id == str(org_id),
                )
            )
            scopes = [(None, None)] + [(r[0], r[1]) for r in group_rows.all()]
        personal, key_groups, org_wide = self._plan_provider_scopes(org_settings, scopes)

        providers = set()
        if personal:
            providers.update(
                await user_api_key_service.get_user_available_providers_async(db, user_id)
            )
        if org_wide:
            scope_clause = OrganizationApiKey.group_id.is_(None)
            if key_groups:
                scope_clause = _or(scope_clause, OrganizationApiKey.group_id.in_(key_groups))
            records = await db.execute(
                select(OrganizationApiKey.provider).where(
                    OrganizationApiKey.organization_id == org_id, scope_clause
                )
            )
            providers.update(
                self.PROVIDER_DISPLAY_NAMES[r[0]]
                for r in records.all()
                if r[0] in self.PROVIDER_DISPLAY_NAMES
            )
        return self._ordered_display_names(providers)


# Create singleton instance
try:
    from encryption_service import encryption_service

    org_api_key_service = OrgApiKeyService(encryption_service)
except ImportError:
    org_api_key_service = None
