"""
API endpoints for organization-level API key management (Issue #1180)
"""

import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import User, require_user
from database import get_async_db
from models import LLMModel as DBLLMModel
from models import Organization, OrganizationMembership, OrganizationRole
from services.org_api_key_service import org_api_key_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizations", tags=["Organization API Keys"])


async def _require_org_admin(user: User, org_id: str, db: AsyncSession):
    """Raise 403 if user cannot manage the organization.

    Mirrors ``routers.organizations.can_manage_organization`` (superadmin or
    active ORG_ADMIN membership) on the async lane. The check is a plain
    membership lookup — a hook, not proprietary logic — so inlining it keeps
    this router fully async without reaching into the (sync) organizations
    domain owned by another agent.
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


async def _require_org_member(user: User, org_id: str, db: AsyncSession):
    """Raise 403 if user is not a member of the organization (or superadmin)."""
    if user.is_superadmin:
        return

    result = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    )

    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )


async def _require_org_exists(org_id: str, db: AsyncSession):
    """Raise 404 if organization does not exist."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )


# ===== Admin endpoints =====


@router.get("/{org_id}/api-keys/status")
async def get_org_api_key_status(
    org_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get API key status for all providers in an organization."""
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)

    status_data = await org_api_key_service.get_org_api_key_status_async(db, org_id)
    available_providers = await org_api_key_service.get_org_available_providers_async(db, org_id)

    return {"api_key_status": status_data, "available_providers": available_providers}


@router.post("/{org_id}/api-keys/{provider}")
async def set_org_api_key(
    org_id: str,
    provider: str,
    request_body: Dict[str, str],
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Set an API key for an organization provider."""
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)

    api_key = request_body.get("api_key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_key is required",
        )

    if provider.lower() not in org_api_key_service.SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider. Valid: {', '.join(org_api_key_service.SUPPORTED_PROVIDERS)}",
        )

    success = await org_api_key_service.set_org_api_key_async(
        db, org_id, provider, api_key, current_user.id
    )

    if success:
        return {"message": f"API key for {provider} set successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set API key. Check key format.",
        )


@router.delete("/{org_id}/api-keys/{provider}")
async def remove_org_api_key(
    org_id: str,
    provider: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Remove an API key for an organization provider."""
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)

    success = await org_api_key_service.remove_org_api_key_async(db, org_id, provider)

    if success:
        return {"message": f"API key for {provider} removed successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key found for provider {provider}",
        )


@router.post("/{org_id}/api-keys/{provider}/test")
async def test_org_api_key(
    org_id: str,
    provider: str,
    request_body: Dict[str, str],
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Test an unsaved API key for an organization provider."""
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)

    api_key = request_body.get("api_key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_key is required",
        )

    if provider.lower() not in org_api_key_service.SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported provider",
        )

    from services.user_api_key_service import user_api_key_service

    try:
        is_valid, message, error_type = await user_api_key_service.validate_api_key(
            api_key, provider
        )
        if is_valid:
            return {"status": "success", "message": message, "error_type": None}
        else:
            return {"status": "error", "message": message, "error_type": error_type}
    except Exception as e:
        logger.error(f"Org API key test failed for {provider}: {e}")
        return {
            "status": "error",
            "message": f"Connection test failed: {str(e)}",
            "error_type": "unknown",
        }


@router.post("/{org_id}/api-keys/{provider}/test-saved")
async def test_saved_org_api_key(
    org_id: str,
    provider: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Test a saved API key for an organization provider."""
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)

    api_key = await org_api_key_service.get_org_api_key_async(db, org_id, provider)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key found for provider {provider}",
        )

    from services.user_api_key_service import user_api_key_service

    try:
        is_valid, message, error_type = await user_api_key_service.validate_api_key(
            api_key, provider
        )
        if is_valid:
            return {"status": "success", "message": message, "error_type": None}
        else:
            return {"status": "error", "message": message, "error_type": error_type}
    except Exception as e:
        logger.error(f"Saved org API key test failed for {provider}: {e}")
        return {
            "status": "error",
            "message": f"Connection test failed: {str(e)}",
            "error_type": "unknown",
        }


# ===== Settings endpoints =====


@router.get("/{org_id}/api-keys/settings")
async def get_org_api_key_settings(
    org_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get API key settings for an organization. Accessible by any member."""
    await _require_org_exists(org_id, db)
    await _require_org_member(current_user, org_id, db)

    require_private = await org_api_key_service._get_org_setting_require_private_keys_async(
        db, org_id
    )
    return {"require_private_keys": require_private}


@router.put("/{org_id}/api-keys/settings")
async def update_org_api_key_settings(
    org_id: str,
    request_body: Dict,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Update API key settings for an organization. Admin only."""
    await _require_org_exists(org_id, db)
    await _require_org_admin(current_user, org_id, db)

    require_private_keys = request_body.get("require_private_keys")
    if require_private_keys is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="require_private_keys is required",
        )

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    settings = org.settings or {}
    settings["require_private_keys"] = bool(require_private_keys)
    org.settings = settings

    # Force SQLAlchemy to detect the change on JSON column
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(org, "settings")

    await db.commit()

    return {
        "message": "Settings updated successfully",
        "require_private_keys": bool(require_private_keys),
    }


# ===== Available models endpoint =====


@router.get("/{org_id}/api-keys/available-models")
async def get_org_available_models(
    org_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Get models available in this organization context."""
    await _require_org_exists(org_id, db)
    await _require_org_member(current_user, org_id, db)

    available_providers = await org_api_key_service.get_available_providers_for_context_async(
        db, current_user.id, org_id
    )

    result = await db.execute(select(DBLLMModel).where(DBLLMModel.is_active == True))  # noqa: E712
    models = result.scalars().all()

    available_models = []
    for model in models:
        if model.provider in available_providers:
            available_models.append(
                {
                    "id": model.id,
                    "name": model.name,
                    "description": model.description,
                    "provider": model.provider,
                    "model_type": model.model_type,
                    "capabilities": model.capabilities,
                    "config_schema": model.config_schema,
                    "default_config": model.default_config,
                    "input_cost_per_million": model.input_cost_per_million,
                    "output_cost_per_million": model.output_cost_per_million,
                    "parameter_constraints": model.parameter_constraints,
                    "recommended_parameters": model.recommended_parameters,
                    "is_active": model.is_active,
                    "created_at": (model.created_at.isoformat() if model.created_at else None),
                    "updated_at": (model.updated_at.isoformat() if model.updated_at else None),
                }
            )

    return available_models
