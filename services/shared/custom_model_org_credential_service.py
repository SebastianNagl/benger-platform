"""Org-owned (shared) credentials for custom (BYOM) LLM models.

The org-level counterpart of ``custom_model_credential_service`` (which keys
by ``(user, model)``): here credentials are keyed by ``(organization, model)``
so an org can provision ONE shared key for a custom model instead of every
member entering their own.

Unlike per-user custom-model credentials, these DO participate in the org
``require_private_keys`` shared-billing machinery — exactly like the
per-provider ``OrganizationApiKey`` rows. The dispatch path
(``user_aware_ai_service.get_ai_service_for_model_row``) consults the shared
key only when the org runs shared-billing mode (``require_private_keys`` is
False) and the invoking user has no personal credential. The model owner's
key is NEVER used implicitly.

Keys are Fernet-encrypted via the shared encryption_service, same format as
``User.encrypted_*_api_key`` and ``CustomModelCredential.encrypted_api_key``.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from encryption_service import encryption_service

logger = logging.getLogger(__name__)


def org_requires_private_keys(db: Session, org_id: str) -> bool:
    """Whether the org bills members individually (True) or provides shared
    keys (False). Defaults to True.

    Same read as ``shared_org_api_key_service`` / ``org_api_key_service``:
    ``Organization.settings.require_private_keys`` with a True default.
    Kept here so the sync worker lane can resolve the shared-billing decision
    without importing the org-api-key service.
    """
    from models import Organization

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org or not org.settings:
        return True
    return org.settings.get("require_private_keys", True)


def get_org_credential(db: Session, org_id: str, model_id: str) -> Optional[str]:
    """Decrypt and return the org's shared API key for a custom model.

    Sync lane — used by workers (Celery process pool, no event loop).
    Returns None when no credential is stored or decryption fails.
    """
    from models import CustomModelOrgCredential

    row = (
        db.query(CustomModelOrgCredential)
        .filter(
            CustomModelOrgCredential.organization_id == org_id,
            CustomModelOrgCredential.model_id == model_id,
        )
        .first()
    )
    if not row:
        return None
    return encryption_service.decrypt_api_key(row.encrypted_api_key)


async def _get_row_async(db: AsyncSession, org_id: str, model_id: str):
    from models import CustomModelOrgCredential

    result = await db.execute(
        select(CustomModelOrgCredential).where(
            CustomModelOrgCredential.organization_id == org_id,
            CustomModelOrgCredential.model_id == model_id,
        )
    )
    return result.scalar_one_or_none()


async def get_org_credential_async(
    db: AsyncSession, org_id: str, model_id: str
) -> Optional[str]:
    """Async twin of get_org_credential (API lane)."""
    row = await _get_row_async(db, org_id, model_id)
    if not row:
        return None
    return encryption_service.decrypt_api_key(row.encrypted_api_key)


async def has_org_credential_async(
    db: AsyncSession, org_id: str, model_id: str
) -> bool:
    row = await _get_row_async(db, org_id, model_id)
    return row is not None


async def get_org_credential_model_ids_async(db: AsyncSession, org_id: str) -> set:
    """All model_ids the org has stored a shared credential for (one query —
    used by the available-models pass to annotate has_credential /
    credential_source under org context)."""
    from models import CustomModelOrgCredential

    result = await db.execute(
        select(CustomModelOrgCredential.model_id).where(
            CustomModelOrgCredential.organization_id == org_id
        )
    )
    return {r[0] for r in result.all()}


async def set_org_credential_async(
    db: AsyncSession,
    org_id: str,
    model_id: str,
    api_key: str,
    created_by: Optional[str] = None,
) -> bool:
    """Upsert the org's shared credential for a custom model.

    Returns False when the key is empty/unencryptable. Commits on success.
    """
    from models import CustomModelOrgCredential

    if not api_key or not api_key.strip():
        return False
    encrypted = encryption_service.encrypt_api_key(api_key)
    if not encrypted:
        logger.error("Failed to encrypt custom-model org credential")
        return False

    row = await _get_row_async(db, org_id, model_id)
    if row:
        row.encrypted_api_key = encrypted
    else:
        row = CustomModelOrgCredential(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            model_id=model_id,
            encrypted_api_key=encrypted,
            created_by=created_by,
        )
        db.add(row)
    await db.commit()
    return True


async def delete_org_credential_async(
    db: AsyncSession, org_id: str, model_id: str
) -> bool:
    """Delete the org's shared credential. Returns True if a row was removed."""
    row = await _get_row_async(db, org_id, model_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
