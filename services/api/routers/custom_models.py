"""
Custom (bring-your-own-model, BYOM) LLM model endpoints.

Users register OpenAI-compatible endpoints as custom models. The rows live in
the shared ``llm_models`` table with ``is_official = False`` and carry
project-style visibility (private / org-shared via ``model_organizations`` /
public). Sharing a model shares only its endpoint DEFINITION — every user
stores their own credential in ``custom_model_credentials`` before using a
``requires_api_key`` model (see custom_model_credential_service).
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import User, require_user
from database import get_async_db
from models import (
    CustomModelCredential,
    LLMModel,
    ModelOrganization,
    Organization,
)
from models import Generation as DBGeneration
from models import ResponseGeneration as DBResponseGeneration
from models import User as DBUser
from routers.model_access import (
    CustomModelAccess,
    check_user_can_edit_model,
    get_accessible_model_ids_async,
    require_custom_model_access,
)
from services.rate_limiter import rate_limiter

# /shared modules (mounted first on sys.path in the api container)
from custom_model_credential_service import (  # noqa: E402
    delete_credential_async,
    get_credential_async,
    get_credential_model_ids_async,
    has_credential_async,
    set_credential_async,
)
from url_guard import validate_custom_model_url  # noqa: E402
from user_api_key_service import validate_openai_compatible_endpoint  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/custom-models", tags=["custom-models"])

CUSTOM_MODEL_PROVIDER = "Custom"

# Both /test endpoints make outbound requests to user-chosen hosts; keep them
# on a tight per-user budget (existing Redis fixed-window limiter; falls back
# to its in-process store when Redis is down, and skips under TESTING=true).
_TEST_RATE_LIMITS = {"minute": (10, 60)}


async def _enforce_test_rate_limit(request: Request, current_user) -> None:
    error = await rate_limiter.check_rate_limit(
        request, "custom_model_test", _TEST_RATE_LIMITS, user=current_user
    )
    if error:
        raise HTTPException(
            status_code=429,
            detail=error,
            headers={"Retry-After": str(error["retry_after"])},
        )


# ============= Schemas =============


class CustomModelCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    base_url: str
    endpoint_model_name: str = Field(..., min_length=1, max_length=255)
    requires_api_key: bool = True
    model_type: str = "chat"
    capabilities: List[str] = ["text_generation"]
    input_cost_per_million: Optional[float] = Field(None, ge=0)
    output_cost_per_million: Optional[float] = Field(None, ge=0)
    parameter_constraints: Optional[Dict[str, Any]] = None
    default_config: Optional[Dict[str, Any]] = None
    api_key: Optional[str] = None


class CustomModelUpdate(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    endpoint_model_name: Optional[str] = Field(None, min_length=1, max_length=255)
    requires_api_key: Optional[bool] = None
    model_type: Optional[str] = None
    capabilities: Optional[List[str]] = None
    input_cost_per_million: Optional[float] = Field(None, ge=0)
    output_cost_per_million: Optional[float] = Field(None, ge=0)
    parameter_constraints: Optional[Dict[str, Any]] = None
    default_config: Optional[Dict[str, Any]] = None
    base_url: Optional[str] = None


class ModelVisibilityUpdate(BaseModel):
    """Typed body for the visibility endpoint (projects use a raw Dict —
    done properly here). Shapes:

    - ``{"is_private": true}``                          → private
    - ``{"is_private": false, "organization_ids": [..]}`` → org-shared
    - ``{"is_public": true}``                           → public
    """

    is_private: Optional[bool] = None
    is_public: Optional[bool] = None
    organization_ids: Optional[List[str]] = None


class CredentialUpdate(BaseModel):
    api_key: str = Field(..., min_length=1)


class EndpointTestRequest(BaseModel):
    base_url: str
    api_key: Optional[str] = None


class ModelTestRequest(BaseModel):
    api_key: Optional[str] = None
    chat_ping: bool = False


class CustomModelResponse(BaseModel):
    """LLMModelResponse field set + BYOM columns + caller-specific annotations.

    NEVER carries credential material — only the boolean ``has_credential``.
    """

    model_config = {"protected_namespaces": ()}

    id: str
    name: str
    description: Optional[str] = None
    provider: str
    model_type: str
    capabilities: List[str] = []
    config_schema: Optional[Dict[str, Any]] = None
    default_config: Optional[Dict[str, Any]] = None
    input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    parameter_constraints: Optional[Dict[str, Any]] = None
    recommended_parameters: Optional[Dict[str, Any]] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # BYOM columns
    is_official: bool = False
    created_by: Optional[str] = None
    created_by_username: Optional[str] = None
    is_private: bool = True
    is_public: bool = False
    base_url: str
    endpoint_model_name: str
    requires_api_key: bool = True
    # Caller-specific annotations
    organization_ids: List[str] = []
    has_credential: bool = False
    can_edit: bool = False


def _to_response(
    model: LLMModel,
    *,
    organization_ids: List[str],
    has_credential: bool,
    can_edit: bool,
    created_by_username: Optional[str],
) -> CustomModelResponse:
    return CustomModelResponse(
        id=model.id,
        name=model.name,
        description=model.description,
        provider=model.provider,
        model_type=model.model_type,
        capabilities=model.capabilities or [],
        config_schema=model.config_schema,
        default_config=model.default_config,
        input_cost_per_million=model.input_cost_per_million,
        output_cost_per_million=model.output_cost_per_million,
        parameter_constraints=model.parameter_constraints,
        recommended_parameters=model.recommended_parameters,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
        is_official=model.is_official,
        created_by=model.created_by,
        created_by_username=created_by_username,
        is_private=model.is_private,
        is_public=model.is_public,
        base_url=model.base_url,
        endpoint_model_name=model.endpoint_model_name,
        requires_api_key=model.requires_api_key,
        organization_ids=organization_ids,
        has_credential=has_credential,
        can_edit=can_edit,
    )


async def _load_response_annotations(
    db: AsyncSession, model: LLMModel, current_user
) -> CustomModelResponse:
    """Single-model variant of the batch annotation in the list endpoint."""
    org_rows = (
        await db.execute(
            select(ModelOrganization.organization_id).where(
                ModelOrganization.model_id == model.id
            )
        )
    ).all()
    has_cred = await has_credential_async(db, str(current_user.id), model.id)
    username = None
    if model.created_by:
        username = (
            await db.execute(
                select(DBUser.username).where(DBUser.id == model.created_by)
            )
        ).scalar_one_or_none()
    return _to_response(
        model,
        organization_ids=[r[0] for r in org_rows],
        has_credential=has_cred,
        can_edit=check_user_can_edit_model(current_user, model),
        created_by_username=username,
    )


def _validate_base_url_or_400(base_url: str) -> str:
    """SSRF guard; 400 with the human-readable reason on rejection.

    ``allow_private`` stays None so the CUSTOM_MODEL_ALLOW_PRIVATE_URLS env
    flag governs (self-hosters pointing at LAN inference servers).
    """
    try:
        return validate_custom_model_url(base_url, allow_private=None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ============= CRUD =============


@router.post("/", response_model=CustomModelResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_model(
    body: CustomModelCreate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Register a custom OpenAI-compatible model. Starts private."""
    normalized_url = _validate_base_url_or_400(body.base_url)

    model = LLMModel(
        id=f"custom-{uuid.uuid4()}",
        name=body.name,
        description=body.description,
        provider=CUSTOM_MODEL_PROVIDER,
        model_type=body.model_type,
        capabilities=body.capabilities,
        default_config=body.default_config,
        input_cost_per_million=body.input_cost_per_million,
        output_cost_per_million=body.output_cost_per_million,
        parameter_constraints=body.parameter_constraints,
        is_active=True,
        is_official=False,
        created_by=str(current_user.id),
        is_private=True,
        is_public=False,
        base_url=normalized_url,
        endpoint_model_name=body.endpoint_model_name,
        requires_api_key=body.requires_api_key,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)

    has_credential = False
    if body.api_key and body.api_key.strip():
        has_credential = await set_credential_async(
            db, str(current_user.id), model.id, body.api_key
        )

    return _to_response(
        model,
        organization_ids=[],
        has_credential=has_credential,
        can_edit=True,
        created_by_username=current_user.username,
    )


@router.get("/", response_model=List[CustomModelResponse])
async def list_custom_models(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """All custom models visible to the caller.

    Active rows only, EXCEPT the caller's own soft-deleted rows (and, for
    superadmins, every soft-deleted row) — these are included with
    ``is_active: false`` so the UI can flag them.
    """
    accessible_ids = await get_accessible_model_ids_async(db, current_user)
    if not accessible_ids:
        return []

    stmt = select(LLMModel).where(
        LLMModel.id.in_(accessible_ids),
        LLMModel.is_official.is_(False),
    )
    if not current_user.is_superadmin:
        stmt = stmt.where(
            or_(
                LLMModel.is_active.is_(True),
                LLMModel.created_by == str(current_user.id),
            )
        )
    models = (
        (await db.execute(stmt.order_by(LLMModel.created_at.desc())))
        .scalars()
        .all()
    )
    if not models:
        return []

    model_ids = [m.id for m in models]

    # Batch-load org links, the caller's credential set, and creator usernames.
    org_rows = (
        await db.execute(
            select(ModelOrganization.model_id, ModelOrganization.organization_id).where(
                ModelOrganization.model_id.in_(model_ids)
            )
        )
    ).all()
    orgs_by_model: Dict[str, List[str]] = {}
    for mid, oid in org_rows:
        orgs_by_model.setdefault(mid, []).append(oid)

    credential_ids = await get_credential_model_ids_async(db, str(current_user.id))

    creator_ids = {m.created_by for m in models if m.created_by}
    usernames: Dict[str, str] = {}
    if creator_ids:
        rows = (
            await db.execute(
                select(DBUser.id, DBUser.username).where(DBUser.id.in_(creator_ids))
            )
        ).all()
        usernames = {uid: uname for uid, uname in rows}

    return [
        _to_response(
            m,
            organization_ids=orgs_by_model.get(m.id, []),
            has_credential=m.id in credential_ids,
            can_edit=check_user_can_edit_model(current_user, m),
            created_by_username=usernames.get(m.created_by),
        )
        for m in models
    ]


@router.get("/{model_id}", response_model=CustomModelResponse)
async def get_custom_model(
    access: CustomModelAccess = Depends(require_custom_model_access("view")),
    db: AsyncSession = Depends(get_async_db),
):
    return await _load_response_annotations(db, access.model, access.user)


@router.patch("/{model_id}", response_model=CustomModelResponse)
async def update_custom_model(
    body: CustomModelUpdate,
    access: CustomModelAccess = Depends(require_custom_model_access("edit")),
    db: AsyncSession = Depends(get_async_db),
):
    model = access.model
    updates = body.model_dump(exclude_unset=True)

    new_base_url = updates.pop("base_url", None)
    if new_base_url is not None:
        normalized_url = _validate_base_url_or_400(new_base_url)
        if normalized_url != model.base_url:
            model.base_url = normalized_url
            # Key-redirect hardening: a changed base_url would silently start
            # sending every other user's stored bearer credential to the NEW
            # host on their next generation. Wipe all credentials except the
            # editor's own so each user must re-enter (re-consent) their key
            # for the new endpoint.
            await db.execute(
                CustomModelCredential.__table__.delete().where(
                    CustomModelCredential.model_id == model.id,
                    CustomModelCredential.user_id != str(access.user.id),
                )
            )

    for field, value in updates.items():
        setattr(model, field, value)

    await db.commit()
    await db.refresh(model)
    return await _load_response_annotations(db, model, access.user)


@router.delete("/{model_id}")
async def delete_custom_model(
    access: CustomModelAccess = Depends(require_custom_model_access("edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a custom model.

    Soft-delete (deactivate + make private + unshare) when any generation
    data references the id — historical generations/evaluations must keep
    resolving it. Hard delete otherwise; the FK cascades then clean up
    credentials and org links.
    """
    model = access.model

    referenced = (
        await db.execute(
            select(DBGeneration.id).where(DBGeneration.model_id == model.id).limit(1)
        )
    ).scalar_one_or_none()
    if referenced is None:
        referenced = (
            await db.execute(
                select(DBResponseGeneration.id)
                .where(DBResponseGeneration.model_id == model.id)
                .limit(1)
            )
        ).scalar_one_or_none()

    if referenced is not None:
        model.is_active = False
        model.is_public = False
        model.is_private = True
        await db.execute(
            ModelOrganization.__table__.delete().where(
                ModelOrganization.model_id == model.id
            )
        )
        # Credentials rows are kept on soft-delete — only a hard delete
        # cascades them away.
        await db.commit()
        return {"deleted": "soft"}

    await db.delete(model)
    await db.commit()
    return {"deleted": "hard"}


@router.patch("/{model_id}/visibility", response_model=CustomModelResponse)
async def update_custom_model_visibility(
    body: ModelVisibilityUpdate,
    access: CustomModelAccess = Depends(require_custom_model_access("edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Change model visibility (creator or superadmin).

    Clone of update_project_visibility semantics MINUS public_role — models
    have no role concept, a visible model is simply usable.
    """
    model = access.model

    make_private = bool(body.is_private)
    make_public = bool(body.is_public)

    if make_private and make_public:
        raise HTTPException(
            status_code=400, detail="A model cannot be both private and public"
        )

    if make_public:
        await db.execute(
            ModelOrganization.__table__.delete().where(
                ModelOrganization.model_id == model.id
            )
        )
        model.is_private = False
        model.is_public = True

    elif make_private:
        await db.execute(
            ModelOrganization.__table__.delete().where(
                ModelOrganization.model_id == model.id
            )
        )
        model.is_private = True
        model.is_public = False

    else:
        organization_ids = body.organization_ids or []
        if not organization_ids:
            raise HTTPException(
                status_code=400,
                detail="At least one organization_id is required for org-shared models",
            )

        for org_id in organization_ids:
            org = (
                await db.execute(select(Organization).where(Organization.id == org_id))
            ).scalar_one_or_none()
            if not org:
                raise HTTPException(
                    status_code=404, detail=f"Organization {org_id} not found"
                )

        await db.execute(
            ModelOrganization.__table__.delete().where(
                ModelOrganization.model_id == model.id
            )
        )
        for org_id in organization_ids:
            db.add(
                ModelOrganization(
                    id=str(uuid.uuid4()),
                    model_id=model.id,
                    organization_id=org_id,
                    assigned_by=str(access.user.id),
                )
            )

        model.is_private = False
        model.is_public = False

    await db.commit()
    await db.refresh(model)
    return await _load_response_annotations(db, model, access.user)


# ============= Credentials =============
#
# Access bar is "view", not "edit": sharing a model shares only its endpoint
# definition — every allowed user brings (and manages) their OWN key.


@router.put("/{model_id}/credential")
async def set_custom_model_credential(
    body: CredentialUpdate,
    access: CustomModelAccess = Depends(require_custom_model_access("view")),
    db: AsyncSession = Depends(get_async_db),
):
    ok = await set_credential_async(
        db, str(access.user.id), access.model.id, body.api_key
    )
    if not ok:
        raise HTTPException(status_code=400, detail="API key could not be stored")
    return {"has_credential": True}


@router.delete("/{model_id}/credential")
async def delete_custom_model_credential(
    access: CustomModelAccess = Depends(require_custom_model_access("view")),
    db: AsyncSession = Depends(get_async_db),
):
    deleted = await delete_credential_async(db, str(access.user.id), access.model.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No credential stored for this model")
    return {"has_credential": False}


@router.get("/{model_id}/credential")
async def get_custom_model_credential_status(
    access: CustomModelAccess = Depends(require_custom_model_access("view")),
    db: AsyncSession = Depends(get_async_db),
):
    """Credential STATUS only — the key itself is never serialized."""
    row = (
        await db.execute(
            select(CustomModelCredential).where(
                CustomModelCredential.user_id == str(access.user.id),
                CustomModelCredential.model_id == access.model.id,
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


# ============= Connectivity tests =============


async def _chat_ping(
    base_url: str, endpoint_model_name: str, api_key: Optional[str]
) -> Dict[str, Any]:
    """POST a 1-message ping to {base_url}/chat/completions, report latency.

    Same generic-error discipline as validate_openai_compatible_endpoint —
    no upstream bodies/status codes are echoed.

    DNS-rebinding immunity: re-resolves + validates base_url at call time
    and PINS the outbound connection to the exact validated IPs, so a TTL-0
    rebind between the guard check and aiohttp's own lookup cannot reach an
    internal address. A rebinding rejection (ValueError) collapses into the
    generic "unreachable" outcome below — never an oracle.
    """
    import aiohttp

    from url_guard import pinned_connector, resolve_and_validate

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    started = time.monotonic()
    try:
        _normalized_url, validated_ips = resolve_and_validate(base_url)
        async with aiohttp.ClientSession(
            connector=pinned_connector(validated_ips)
        ) as session:
            async with session.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": endpoint_model_name,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 16,
                },
                timeout=aiohttp.ClientTimeout(total=30),
                # SECURITY: never follow redirects — a 3xx to an internal
                # host would be replayed (307/308 preserve method + body),
                # bypassing the url_guard the caller ran on base_url only.
                allow_redirects=False,
            ) as response:
                latency_ms = int((time.monotonic() - started) * 1000)
                if 300 <= response.status < 400:
                    return {
                        "status": "error",
                        "message": "Chat ping failed: unexpected response",
                        "error_type": "invalid_response",
                        "latency_ms": latency_ms,
                    }
                if response.status in (401, 403):
                    return {
                        "status": "error",
                        "message": "Chat ping failed: authentication failed",
                        "error_type": "auth",
                        "latency_ms": latency_ms,
                    }
                if response.status != 200:
                    return {
                        "status": "error",
                        "message": "Chat ping failed: unexpected response",
                        "error_type": "invalid_response",
                        "latency_ms": latency_ms,
                    }
                try:
                    await response.json()
                except Exception:
                    return {
                        "status": "error",
                        "message": "Chat ping failed: unexpected response",
                        "error_type": "invalid_response",
                        "latency_ms": latency_ms,
                    }
                return {
                    "status": "success",
                    "message": "Chat completion succeeded",
                    "error_type": None,
                    "latency_ms": latency_ms,
                }
    except Exception:
        return {
            "status": "error",
            "message": "Chat ping failed: endpoint could not be reached",
            "error_type": "unreachable",
            "latency_ms": None,
        }


@router.post("/test")
async def test_custom_endpoint(
    body: EndpointTestRequest,
    request: Request,
    current_user: User = Depends(require_user),
):
    """Probe an (unsaved) OpenAI-compatible endpoint.

    url_guard runs FIRST — a rejected URL is never contacted, and the
    guard's rejection reason is the only URL-specific detail returned. The
    probe itself collapses upstream errors to generic auth/unreachable/
    invalid-response outcomes so this cannot be used as a port-scan oracle.
    """
    await _enforce_test_rate_limit(request, current_user)
    normalized_url = _validate_base_url_or_400(body.base_url)

    ok, message, error_type = await validate_openai_compatible_endpoint(
        normalized_url, api_key=body.api_key
    )
    if ok:
        return {"status": "success", "message": message, "error_type": None}
    return {"status": "error", "message": message, "error_type": error_type}


@router.post("/{model_id}/test")
async def test_custom_model(
    body: ModelTestRequest,
    request: Request,
    access: CustomModelAccess = Depends(require_custom_model_access("view")),
    db: AsyncSession = Depends(get_async_db),
):
    """Probe a saved custom model with the caller's key.

    Key precedence: explicit body ``api_key``, else the caller's stored
    credential. With ``chat_ping: true``, additionally sends a 1-message
    chat completion and reports latency.
    """
    await _enforce_test_rate_limit(request, access.user)

    # Re-validate the stored URL at call time (env flags / DNS may have
    # changed since save — see url_guard's DNS-rebinding caveat).
    normalized_url = _validate_base_url_or_400(access.model.base_url)

    api_key = body.api_key
    if not api_key:
        api_key = await get_credential_async(
            db, str(access.user.id), access.model.id
        )

    ok, message, error_type = await validate_openai_compatible_endpoint(
        normalized_url, api_key=api_key
    )
    result: Dict[str, Any] = {
        "status": "success" if ok else "error",
        "message": message,
        "error_type": None if ok else error_type,
    }

    if body.chat_ping:
        result["chat_ping"] = await _chat_ping(
            normalized_url, access.model.endpoint_model_name, api_key
        )

    return result
