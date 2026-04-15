"""
API endpoints for organization-level API key management (Issue #1180)
"""

import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from models import LLMModel as DBLLMModel
from models import Organization, OrganizationMembership
from org_api_key_service import org_api_key_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizations", tags=["Organization API Keys"])


def _require_org_admin(user: User, org_id: str, db: Session):
    """Raise 403 if user cannot manage the organization."""
    from routers.organizations import can_manage_organization

    if not can_manage_organization(user, org_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this organization",
        )


def _require_org_member(user: User, org_id: str, db: Session):
    """Raise 403 if user is not a member of the organization (or superadmin)."""
    if user.is_superadmin:
        return

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.is_active == True,
        )
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )


def _require_org_exists(org_id: str, db: Session):
    """Raise 404 if organization does not exist."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )


# ===== Admin endpoints =====


@router.get("/{org_id}/api-keys/status")
async def get_org_api_key_status(
    org_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get API key status for all providers in an organization."""
    _require_org_exists(org_id, db)
    _require_org_admin(current_user, org_id, db)

    status_data = org_api_key_service.get_org_api_key_status(db, org_id)
    available_providers = org_api_key_service.get_org_available_providers(db, org_id)

    return {"api_key_status": status_data, "available_providers": available_providers}


@router.post("/{org_id}/api-keys/{provider}")
async def set_org_api_key(
    org_id: str,
    provider: str,
    request_body: Dict[str, str],
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Set an API key for an organization provider."""
    _require_org_exists(org_id, db)
    _require_org_admin(current_user, org_id, db)

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

    success = org_api_key_service.set_org_api_key(db, org_id, provider, api_key, current_user.id)

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
    db: Session = Depends(get_db),
):
    """Remove an API key for an organization provider."""
    _require_org_exists(org_id, db)
    _require_org_admin(current_user, org_id, db)

    success = org_api_key_service.remove_org_api_key(db, org_id, provider)

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
    db: Session = Depends(get_db),
):
    """Test an unsaved API key for an organization provider."""
    _require_org_exists(org_id, db)
    _require_org_admin(current_user, org_id, db)

    api_key = request_body.get("api_key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_key is required",
        )

    if provider.lower() not in org_api_key_service.SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider",
        )

    from user_api_key_service import user_api_key_service

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
    db: Session = Depends(get_db),
):
    """Test a saved API key for an organization provider."""
    _require_org_exists(org_id, db)
    _require_org_admin(current_user, org_id, db)

    api_key = org_api_key_service.get_org_api_key(db, org_id, provider)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key found for provider {provider}",
        )

    from user_api_key_service import user_api_key_service

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
    db: Session = Depends(get_db),
):
    """Get API key settings for an organization. Accessible by any member."""
    _require_org_exists(org_id, db)
    _require_org_member(current_user, org_id, db)

    require_private = org_api_key_service._get_org_setting_require_private_keys(db, org_id)
    return {"require_private_keys": require_private}


@router.put("/{org_id}/api-keys/settings")
async def update_org_api_key_settings(
    org_id: str,
    request_body: Dict,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Update API key settings for an organization. Admin only."""
    _require_org_exists(org_id, db)
    _require_org_admin(current_user, org_id, db)

    require_private_keys = request_body.get("require_private_keys")
    if require_private_keys is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="require_private_keys is required",
        )

    org = db.query(Organization).filter(Organization.id == org_id).first()
    settings = org.settings or {}
    settings["require_private_keys"] = bool(require_private_keys)
    org.settings = settings

    # Force SQLAlchemy to detect the change on JSON column
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(org, "settings")

    db.commit()

    return {
        "message": "Settings updated successfully",
        "require_private_keys": bool(require_private_keys),
    }


# ===== Available models endpoint =====


@router.get("/{org_id}/api-keys/available-models")
async def get_org_available_models(
    org_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get models available in this organization context."""
    _require_org_exists(org_id, db)
    _require_org_member(current_user, org_id, db)

    available_providers = org_api_key_service.get_available_providers_for_context(
        db, current_user.id, org_id
    )

    models = db.query(DBLLMModel).filter(DBLLMModel.is_active == True).all()

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
                    "is_active": model.is_active,
                    "created_at": (model.created_at.isoformat() if model.created_at else None),
                    "updated_at": (model.updated_at.isoformat() if model.updated_at else None),
                }
            )

    return available_models
