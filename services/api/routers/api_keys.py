"""
API endpoints for user API key management
"""

import logging
import sys
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_async_db, get_db, release_db_sessions
from models import LLMModel as DBLLMModel

# Add shared services to path
sys.path.append('/shared')

from encryption_service import encryption_service  # noqa: E402
from services.user_api_key_service import create_user_api_key_service  # noqa: E402

# Create service instance with dependency
user_api_key_service = create_user_api_key_service(encryption_service)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users/api-keys", tags=["User API Keys"])

# validate_api_key error_types meaning the provider refused the key itself.
# Anything else (timeout, connection_error, network, api_error, unknown) means
# the provider could not be asked; the key is stored and can be re-checked via
# the test-saved endpoint.
_REJECTED_KEY_ERROR_TYPES = frozenset({"auth", "invalid_key", "invalid_format"})


@router.post("/{provider}")
async def set_user_api_key(
    provider: str,
    request: Dict[str, str],
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    request_db: Session = Depends(get_db),
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

    # The provider round-trip can be slow: don't hold the auth lookup's
    # transaction open across it (Postgres kills idle-in-transaction backends).
    # The async session is untouched until the write below, so leave it be.
    await release_db_sessions(request_db)

    # Validate the key against the provider (returns (is_valid, message,
    # error_type)). Reject only when the provider refused the key; if the
    # provider could not be reached, store it anyway and log a warning.
    try:
        is_valid, message, error_type = await user_api_key_service.validate_api_key(
            api_key, provider
        )
    except Exception as e:
        logger.warning(f"API key validation failed, but proceeding with storage: {e}")
    else:
        if not is_valid:
            if error_type in _REJECTED_KEY_ERROR_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid API key - unable to authenticate with provider: {message}",
                )
            logger.warning(
                f"Could not verify {provider} API key ({error_type}: {message}), "
                "proceeding with storage"
            )

    # Store the API key
    success = await user_api_key_service.set_user_api_key_async(
        db, current_user.id, provider, api_key
    )

    if success:
        return {"message": f"API key for {provider} set successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set API key",
        )


@router.get("/status")
async def get_user_api_key_status(
    current_user: User = Depends(require_user), db: AsyncSession = Depends(get_async_db)
):
    """Get status of user's API keys"""
    status_data = await user_api_key_service.get_user_api_key_status_async(db, current_user.id)
    available_providers = await user_api_key_service.get_user_available_providers_async(
        db, current_user.id
    )

    return {"api_key_status": status_data, "available_providers": available_providers}


@router.delete("/{provider}")
async def remove_user_api_key(
    provider: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Remove API key for a provider"""
    success = await user_api_key_service.remove_user_api_key_async(db, current_user.id, provider)

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
    request_db: Session = Depends(get_db),
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

    # End the auth lookup's transaction before the provider round-trip.
    await release_db_sessions(request_db)

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
    db: AsyncSession = Depends(get_async_db),
    request_db: Session = Depends(get_db),
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
    api_key = await user_api_key_service.get_user_api_key_async(db, current_user.id, provider)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key found for provider {provider}",
        )

    # End both read transactions before the provider round-trip.
    await release_db_sessions(request_db, db)

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


async def _resolve_model_scope_org(
    db: AsyncSession, current_user: User, project_id: Optional[str], organization_id: Optional[str]
) -> Optional[str]:
    """The organization whose keys a run in this scope would spend.

    ``project_id``: the org a generation or evaluation on that project
    dispatches with (``org_resolution``, membership-validated), so the
    picker lists exactly what the worker can run. ``organization_id``: the
    creation target of the project wizard, an active membership required.
    Neither: the user's personal keys.
    """
    if project_id:
        from routers.projects.helpers import check_project_accessible_async
        from org_resolution import resolve_dispatch_org_for_project_async

        if not await check_project_accessible_async(db, current_user, project_id, None):
            raise HTTPException(status_code=403, detail="Access denied")
        return await resolve_dispatch_org_for_project_async(db, current_user, project_id)
    if organization_id:
        from models import OrganizationMembership

        if not current_user.is_superadmin:
            member = (
                await db.execute(
                    select(OrganizationMembership.id).where(
                        OrganizationMembership.user_id == str(current_user.id),
                        OrganizationMembership.organization_id == str(organization_id),
                        OrganizationMembership.is_active.is_(True),
                    )
                )
            ).first()
            if member is None:
                raise HTTPException(
                    status_code=403, detail="Not a member of this organization"
                )
        return str(organization_id)
    return None


@router.get("/available-models")
async def get_available_models_for_user(
    request: Request,
    project_id: Optional[str] = Query(
        None, description="List the models a run on this project can use."
    ),
    organization_id: Optional[str] = Query(
        None, description="List the models a project created in this organization can use."
    ),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Models the caller can run in a scope: a project (its dispatch org),
    an organization (the wizard's creation target) or, without either, the
    personal keys. The selected organization of the client
    (``X-Organization-Context``) is not consulted."""
    org_id = await _resolve_model_scope_org(db, current_user, project_id, organization_id)

    if org_id:
        from services.org_api_key_service import org_api_key_service

        available_providers = await org_api_key_service.get_available_providers_for_context_async(
            db, current_user.id, org_id
        )
    else:
        available_providers = await user_api_key_service.get_user_available_providers_async(
            db, current_user.id
        )

    # Development debugging
    logger.info(f"🔍 User {current_user.id} requesting available models")
    logger.info(f"📋 Available providers for user: {available_providers}")

    # Get all OFFICIAL catalog models from database. Custom (BYOM) rows are
    # appended by the separate pass below with per-model visibility and
    # per-user credential rules instead of the provider-key filter.
    result = await db.execute(
        select(DBLLMModel).where(
            DBLLMModel.is_active == True,  # noqa: E712
            DBLLMModel.is_official.is_(True),
        )
    )
    models = result.scalars().all()
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
                    "recommended_parameters": model.recommended_parameters,
                    "is_active": model.is_active,
                    "is_official": True,
                    "created_at": (model.created_at.isoformat() if model.created_at else None),
                    "updated_at": (model.updated_at.isoformat() if model.updated_at else None),
                }
            )
        else:
            logger.info(
                f"❌ Excluding model {model.id} ({model.provider}) - user has no valid API key"
            )

    # Custom (BYOM) pass. Every custom model the caller can SEE is returned,
    # annotated with has_credential so the picker can render a keyed-but-
    # keyless model disabled with an "add your key" prompt
    # (GenerationControlModal) rather than silently dropping it — a project
    # configured to use a shared model must still show it. Running one
    # without a credential is prevented downstream: start_generation checks
    # accessibility and the worker fails a requires_api_key model that has no
    # usable credential.
    #
    # Org context is honored here for the SHARED-credential case only: when
    # the org runs shared-billing mode (require_private_keys False) and has
    # provisioned a shared key for the model, that satisfies has_credential
    # even when the user has none — mirroring the dispatch precedence in
    # user_aware_ai_service.get_ai_service_for_model_row. The user's own key
    # always wins (credential_source "user"). The resolution helper also
    # requires an ACTIVE membership in the caller-supplied context org (the
    # header is unvalidated) and a LIVE ModelOrganization share — a
    # non-member can't probe another org's provisioning, and an unshared
    # model's leftover org key doesn't annotate as usable.
    from custom_model_key_resolution import resolve_custom_model_credentials_async
    from routers.model_access import get_accessible_model_ids_async

    accessible_custom_ids = await get_accessible_model_ids_async(db, current_user)
    if accessible_custom_ids:
        custom_result = await db.execute(
            select(DBLLMModel).where(
                DBLLMModel.id.in_(accessible_custom_ids),
                DBLLMModel.is_official.is_(False),
                DBLLMModel.is_active == True,  # noqa: E712
            )
        )
        custom_models = custom_result.scalars().all()
        resolutions = await resolve_custom_model_credentials_async(
            db, current_user.id, custom_models, organization_id=org_id
        )

        for model in custom_models:
            resolution = resolutions[model.id]
            has_credential = resolution.has_credential
            credential_source = resolution.source
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
                    "is_official": False,
                    "requires_api_key": model.requires_api_key,
                    "has_credential": has_credential,
                    "credential_source": credential_source,
                    "base_url": model.base_url,
                    "created_by": model.created_by,
                    "created_at": (model.created_at.isoformat() if model.created_at else None),
                    "updated_at": (model.updated_at.isoformat() if model.updated_at else None),
                }
            )

    logger.info(f"✅ Returning {len(available_models)} models to user {current_user.id}")
    if len(available_models) == 0:
        logger.warning(
            f"⚠️ No models available for user {current_user.id}. Check API key configuration."
        )

    return available_models
