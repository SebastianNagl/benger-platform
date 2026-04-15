"""
API endpoints for user API key management
"""

import logging
import sys
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from models import LLMModel as DBLLMModel

# Add shared services to path
sys.path.append('/shared')

from encryption_service import encryption_service
from user_api_key_service import create_user_api_key_service

# Create service instance with dependency
user_api_key_service = create_user_api_key_service(encryption_service)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users/api-keys", tags=["User API Keys"])


@router.post("/{provider}")
async def set_user_api_key(
    provider: str,
    request: Dict[str, str],
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Set API key for a provider"""
    api_key = request.get("api_key")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="api_key is required")

    # Validate provider
    valid_providers = [
        "openai",
        "anthropic",
        "google",
        "deepinfra",
        "grok",
        "mistral",
        "cohere",
    ]
    if provider.lower() not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider. Valid providers: {', '.join(valid_providers)}",
        )

    # Optional: Validate API key by testing it
    try:
        is_valid = await user_api_key_service.validate_api_key(api_key, provider)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid API key - unable to authenticate with provider",
            )
    except Exception as e:
        logger.warning(f"API key validation failed, but proceeding with storage: {e}")

    # Store the API key
    success = user_api_key_service.set_user_api_key(db, current_user.id, provider, api_key)

    if success:
        return {"message": f"API key for {provider} set successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set API key",
        )


@router.get("/status")
async def get_user_api_key_status(
    current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Get status of user's API keys"""
    status_data = user_api_key_service.get_user_api_key_status(db, current_user.id)
    available_providers = user_api_key_service.get_user_available_providers(db, current_user.id)

    return {"api_key_status": status_data, "available_providers": available_providers}


@router.delete("/{provider}")
async def remove_user_api_key(
    provider: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Remove API key for a provider"""
    success = user_api_key_service.remove_user_api_key(db, current_user.id, provider)

    if success:
        return {"message": f"API key for {provider} removed successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove API key",
        )


@router.post("/{provider}/test")
async def test_user_api_key(
    provider: str,
    request: Dict[str, str],
    current_user: User = Depends(require_user),
):
    """Test API key connection for a provider"""
    api_key = request.get("api_key")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="api_key is required")

    # Validate provider
    valid_providers = [
        "openai",
        "anthropic",
        "google",
        "deepinfra",
        "grok",
        "mistral",
        "cohere",
    ]
    if provider.lower() not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider. Valid providers: {', '.join(valid_providers)}",
        )

    try:
        is_valid, message, error_type = await user_api_key_service.validate_api_key(
            api_key, provider
        )
        if is_valid:
            return {"status": "success", "message": message, "error_type": None}
        else:
            return {"status": "error", "message": message, "error_type": error_type}
    except Exception as e:
        logger.error(f"API key test failed for {provider}: {e}")
        return {
            "status": "error",
            "message": f"Connection test failed: {str(e)}",
            "error_type": "unknown",
        }


@router.post("/{provider}/test-saved")
async def test_saved_user_api_key(
    provider: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Test saved API key connection for a provider"""
    # Validate provider
    valid_providers = [
        "openai",
        "anthropic",
        "google",
        "deepinfra",
        "grok",
        "mistral",
        "cohere",
    ]
    if provider.lower() not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider. Valid providers: {', '.join(valid_providers)}",
        )

    # Get the saved API key
    api_key = user_api_key_service.get_user_api_key(db, current_user.id, provider)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key found for provider {provider}",
        )

    try:
        is_valid, message, error_type = await user_api_key_service.validate_api_key(
            api_key, provider
        )
        if is_valid:
            return {"status": "success", "message": message, "error_type": None}
        else:
            return {"status": "error", "message": message, "error_type": error_type}
    except Exception as e:
        logger.error(f"Saved API key test failed for {provider}: {e}")
        return {
            "status": "error",
            "message": f"Connection test failed: {str(e)}",
            "error_type": "unknown",
        }


@router.get("/available-models")
async def get_available_models_for_user(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get available models based on user's API keys or org keys"""
    # Check if org context should override key resolution
    org_context = request.headers.get("X-Organization-Context")
    org_id = org_context if org_context and org_context != "private" else None

    if org_id:
        from org_api_key_service import org_api_key_service

        available_providers = org_api_key_service.get_available_providers_for_context(
            db, current_user.id, org_id
        )
    else:
        available_providers = user_api_key_service.get_user_available_providers(db, current_user.id)

    # Development debugging
    logger.info(f"🔍 User {current_user.username} requesting available models")
    logger.info(f"📋 Available providers for user: {available_providers}")

    # Get all models from database
    models = db.query(DBLLMModel).filter(DBLLMModel.is_active == True).all()
    logger.info(f"🗃️ Total active models in database: {len(models)}")

    # Filter models based on user's available providers
    available_models = []
    for model in models:
        if model.provider in available_providers:
            logger.info(f"✅ Including model {model.id} ({model.provider}) - user has valid API key")
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
                    "is_active": model.is_active,
                    "created_at": (model.created_at.isoformat() if model.created_at else None),
                    "updated_at": (model.updated_at.isoformat() if model.updated_at else None),
                }
            )
        else:
            logger.info(
                f"❌ Excluding model {model.id} ({model.provider}) - user has no valid API key"
            )

    logger.info(f"✅ Returning {len(available_models)} models to user {current_user.username}")
    if len(available_models) == 0:
        logger.warning(
            f"⚠️ No models available for user {current_user.username}. Check API key configuration."
        )

    return available_models
