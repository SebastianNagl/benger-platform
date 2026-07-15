"""Org-owned (shared) credentials for custom (BYOM) models.

Lets an ORG_ADMIN provision ONE shared API key for a custom model shared
with the org, instead of every member entering their own. The org-level
counterpart of the per-user credential endpoints in ``custom_models.py``
(which this router deliberately does NOT touch).

Persistence lives in the platform ``custom_model_org_credentials`` table
(migration 081) via ``custom_model_org_credential_service``. Key material is
Fernet-encrypted and NEVER returned by any endpoint — only booleans and
timestamps.

Guards (same pattern as ``org_api_keys.py``): the caller must be a
superadmin or an active ORG_ADMIN of the organization, and the target model
must be a CUSTOM (non-official) model that is shared with THIS organization
(a ``model_organizations`` row exists). Missing/official/unshared models all
404 to avoid existence leaks.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import User, require_user
from custom_model_org_credential_service import (
    delete_org_credential_async,
    get_org_credential_model_ids_async,
    set_org_credential_async,
)
from database import get_async_db
from models import CustomModelOrgCredential
from models import LLMModel as DBLLMModel
from models import ModelOrganization, Organization, OrganizationMembership, OrganizationRole

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/organizations", tags=["Organization Custom Model Credentials"]
)


# ===== Guards (mirror routers/org_api_keys.py) =====


async def _require_org_exists(org_id: str, db: AsyncSession):
    """Raise 404 if organization does not exist."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )


async def _require_org_admin(user: User, org_id: str, db: AsyncSession):
    """Raise 403 unless the caller is a superadmin or an active ORG_ADMIN.

    Same membership lookup as ``org_api_keys._require_org_admin`` — a hook,
    not proprietary logic, inlined to keep this router fully async.
    """
    if user.is_superadmin:
        return

    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this organization",
        )


async def _require_shared_custom_model(
    org_id: str, model_id: str, db: AsyncSession
) -> DBLLMModel:
    """Return the model iff it is a CUSTOM model shared with THIS org.

    404 when: the row is missing, it is an OFFICIAL catalog row (org
    shared-credentials are a custom-model feature), or it is not shared with
    this organization. 404 rather than 403 for the unshared case to avoid
    leaking which custom models exist to an org admin they were never shared
    with.
    """
    result = await db.execute(select(DBLLMModel).where(DBLLMModel.id == model_id))
    model: Optional[DBLLMModel] = result.scalar_one_or_none()
    if model is None or model.is_official:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Custom model not found"
        )

    shared = await db.execute(
        select(ModelOrganization).where(
            ModelOrganization.model_id == model_id,
            ModelOrganization.organization_id == org_id,
        )
    )
    if shared.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model is not shared with this organization",
        )
    return model


# ===== List shared custom models (with credential status) =====


@router.get("/{organization_id}/custom-models")
async def list_org_shared_custom_models(
    organization_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
) -> List[Dict]:
    """Custom models shared with the org + whether a shared key is set.

    Admin-only. Flat array; ``has_org_credential`` reflects the
    ``custom_model_org_credentials`` row, never the key itself.
    """
    await _require_org_exists(organization_id, db)
    await _require_org_admin(current_user, organization_id, db)

    result = await db.execute(
        select(DBLLMModel)
        .join(ModelOrganization, ModelOrganization.model_id == DBLLMModel.id)
        .where(
            ModelOrganization.organization_id == organization_id,
            DBLLMModel.is_official.is_(False),
            DBLLMModel.is_active == True,  # noqa: E712
        )
    )
    models = result.scalars().all()

    credentialed_ids = await get_org_credential_model_ids_async(db, organization_id)

    return [
        {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "provider": model.provider,
            "base_url": model.base_url,
            "endpoint_model_name": model.endpoint_model_name,
            "requires_api_key": model.requires_api_key,
            "has_org_credential": model.id in credentialed_ids,
        }
        for model in models
    ]


# ===== Per-model shared credential =====


@router.put("/{organization_id}/custom-models/{model_id}/credential")
async def set_org_custom_model_credential(
    organization_id: str,
    model_id: str,
    request_body: Dict[str, str],
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Set (or replace) the org's shared key for a custom model."""
    await _require_org_exists(organization_id, db)
    await _require_org_admin(current_user, organization_id, db)
    await _require_shared_custom_model(organization_id, model_id, db)

    api_key = request_body.get("api_key")
    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_key is required",
        )

    ok = await set_org_credential_async(
        db, organization_id, model_id, api_key, created_by=current_user.id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key could not be stored",
        )
    return {"has_credential": True}


@router.get("/{organization_id}/custom-models/{model_id}/credential")
async def get_org_custom_model_credential_status(
    organization_id: str,
    model_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Credential STATUS only — the key itself is never serialized."""
    await _require_org_exists(organization_id, db)
    await _require_org_admin(current_user, organization_id, db)
    await _require_shared_custom_model(organization_id, model_id, db)

    row = (
        await db.execute(
            select(CustomModelOrgCredential).where(
                CustomModelOrgCredential.organization_id == organization_id,
                CustomModelOrgCredential.model_id == model_id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        return {"has_credential": False, "updated_at": None}
    last_updated = row.updated_at or row.created_at
    return {
        "has_credential": True,
        "updated_at": last_updated.isoformat() if last_updated else None,
    }


@router.delete("/{organization_id}/custom-models/{model_id}/credential")
async def delete_org_custom_model_credential(
    organization_id: str,
    model_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Remove the org's shared key for a custom model."""
    await _require_org_exists(organization_id, db)
    await _require_org_admin(current_user, organization_id, db)
    await _require_shared_custom_model(organization_id, model_id, db)

    deleted = await delete_org_credential_async(db, organization_id, model_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No shared credential stored for this model",
        )
    return {"has_credential": False}
