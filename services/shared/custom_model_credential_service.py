"""Per-user, per-model credentials for custom (BYOM) LLM models.

Unlike the fixed per-provider key columns on ``User`` (user_api_key_service)
and the per-org ``OrganizationApiKey`` rows, custom-model credentials are
keyed by (user_id, model_id): sharing a custom model shares only its
endpoint definition, and every user stores their own key before using it.

This module stores strictly PERSONAL credentials; the org-shared counterpart
lives in ``custom_model_org_credential_service`` and participates in the org
``require_private_keys`` shared-billing machinery. Precedence between the two
lanes (personal wins; org key only in org-pays mode while still shared) is
implemented in ``user_aware_ai_service.get_ai_service_for_model_row`` (worker
lane) and ``custom_model_key_resolution`` (API lane). The model owner's key is
never used implicitly for another user.

Keys are Fernet-encrypted via the shared encryption_service, same format as
User.encrypted_*_api_key.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from encryption_service import encryption_service

logger = logging.getLogger(__name__)


def get_credential(db: Session, user_id: str, model_id: str) -> Optional[str]:
    """Decrypt and return the user's API key for a custom model.

    Sync lane — used by workers (Celery process pool, no event loop).
    Returns None when no credential is stored or decryption fails.
    """
    from models import CustomModelCredential

    row = (
        db.query(CustomModelCredential)
        .filter(
            CustomModelCredential.user_id == user_id,
            CustomModelCredential.model_id == model_id,
        )
        .first()
    )
    if not row:
        return None
    return encryption_service.decrypt_api_key(row.encrypted_api_key)


async def _get_row_async(db: AsyncSession, user_id: str, model_id: str):
    from models import CustomModelCredential

    result = await db.execute(
        select(CustomModelCredential).where(
            CustomModelCredential.user_id == user_id,
            CustomModelCredential.model_id == model_id,
        )
    )
    return result.scalar_one_or_none()


async def get_credential_async(
    db: AsyncSession, user_id: str, model_id: str
) -> Optional[str]:
    """Async twin of get_credential (API lane)."""
    row = await _get_row_async(db, user_id, model_id)
    if not row:
        return None
    return encryption_service.decrypt_api_key(row.encrypted_api_key)


async def has_credential_async(db: AsyncSession, user_id: str, model_id: str) -> bool:
    row = await _get_row_async(db, user_id, model_id)
    return row is not None


async def get_credential_model_ids_async(
    db: AsyncSession, user_id: str
) -> set:
    """All model_ids the user has stored a credential for (one query —
    used by the available-models pass to annotate has_credential)."""
    from models import CustomModelCredential

    result = await db.execute(
        select(CustomModelCredential.model_id).where(
            CustomModelCredential.user_id == user_id
        )
    )
    return {r[0] for r in result.all()}


async def set_credential_async(
    db: AsyncSession, user_id: str, model_id: str, api_key: str
) -> bool:
    """Upsert the user's credential for a custom model.

    Returns False when the key is empty/unencryptable. Commits on success.
    """
    from models import CustomModelCredential

    if not api_key or not api_key.strip():
        return False
    encrypted = encryption_service.encrypt_api_key(api_key)
    if not encrypted:
        logger.error("Failed to encrypt custom-model credential")
        return False

    row = await _get_row_async(db, user_id, model_id)
    if row:
        row.encrypted_api_key = encrypted
    else:
        row = CustomModelCredential(
            id=str(uuid.uuid4()),
            user_id=user_id,
            model_id=model_id,
            encrypted_api_key=encrypted,
        )
        db.add(row)
    await db.commit()
    return True


async def delete_credential_async(
    db: AsyncSession, user_id: str, model_id: str
) -> bool:
    """Delete the user's credential. Returns True if a row was removed."""
    row = await _get_row_async(db, user_id, model_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
