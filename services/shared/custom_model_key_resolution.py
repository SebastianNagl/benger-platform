"""Unified "can this user invoke this custom model, and with which key" answer.

Single source of truth for the API lane's credential annotations and probe
fallbacks, mirroring the dispatch precedence the worker lane applies in
``user_aware_ai_service.get_ai_service_for_model_row``:

===========================  ==================================================
Route                        Conditions
===========================  ==================================================
``source="user"``            the invoking user stored a personal credential
                             (always wins)
``source="org"``             no personal credential AND a live
                             ``ModelOrganization`` share AND the user is an
                             ACTIVE member of that org AND the org runs
                             shared-billing mode (``require_private_keys``
                             falsy) AND an org shared credential exists
``source=None``              no usable key; ``can_invoke`` is then
                             ``not requires_api_key``
===========================  ==================================================

Org scoping: pass ``organization_id`` to resolve against ONE org context (the
available-models lane, where the caller supplies the org header), or
``search_user_orgs=True`` to consider every org the user actively belongs to
(context-free lanes: the /test probe, response annotations). With neither, the
resolution is personal-only — matching generation without org context. When
several orgs could supply a shared key, the lowest org id wins so the answer
is deterministic; it means "at least one usable route exists", not billing
attribution.

Callers must have already established VIEW access to the models (the routers
gate via ``require_custom_model_access`` / ``get_accessible_model_ids_async``).
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from custom_model_credential_service import (
    get_credential_async,
    get_credential_model_ids_async,
)
from custom_model_org_credential_service import get_org_credential_async

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CustomModelCredentialResolution:
    can_invoke: bool
    source: Optional[str]  # "user" | "org" | None
    organization_id: Optional[str]  # org whose shared key would be used
    api_key: Optional[str] = None  # decrypted, only when include_key=True

    @property
    def has_credential(self) -> bool:
        return self.source is not None


async def resolve_custom_model_credentials_async(
    db: AsyncSession,
    user_id: str,
    models: Sequence[Any],
    *,
    organization_id: Optional[str] = None,
    search_user_orgs: bool = False,
) -> Dict[str, CustomModelCredentialResolution]:
    """Batch resolution for ``models`` (rows with ``id``/``requires_api_key``).

    At most 4 queries regardless of model count.
    """
    from models import (
        CustomModelOrgCredential,
        ModelOrganization,
        Organization,
        OrganizationMembership,
    )

    model_ids = [m.id for m in models]
    if not model_ids:
        return {}

    personal_ids = await get_credential_model_ids_async(db, user_id)

    # Candidate org routes: live share x the user's ACTIVE memberships.
    org_route_candidates: List = []
    if organization_id or search_user_orgs:
        stmt = (
            select(ModelOrganization.model_id, ModelOrganization.organization_id)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id
                == ModelOrganization.organization_id,
            )
            .where(
                ModelOrganization.model_id.in_(model_ids),
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        if organization_id:
            stmt = stmt.where(ModelOrganization.organization_id == organization_id)
        org_route_candidates = (await db.execute(stmt)).all()

    paying_org_ids: set = set()
    org_cred_pairs: set = set()
    candidate_org_ids = {oid for _, oid in org_route_candidates}
    if candidate_org_ids:
        # Shared-billing orgs only (require_private_keys defaults to True) —
        # same read as custom_model_org_credential_service.org_requires_private_keys.
        org_rows = (
            await db.execute(
                select(Organization.id, Organization.settings).where(
                    Organization.id.in_(candidate_org_ids)
                )
            )
        ).all()
        paying_org_ids = {
            oid
            for oid, settings in org_rows
            if not (settings or {}).get("require_private_keys", True)
        }
    if paying_org_ids:
        cred_rows = (
            await db.execute(
                select(
                    CustomModelOrgCredential.model_id,
                    CustomModelOrgCredential.organization_id,
                ).where(
                    CustomModelOrgCredential.model_id.in_(model_ids),
                    CustomModelOrgCredential.organization_id.in_(paying_org_ids),
                )
            )
        ).all()
        org_cred_pairs = {(mid, oid) for mid, oid in cred_rows}

    usable_orgs_by_model: Dict[str, List[str]] = {}
    for mid, oid in org_route_candidates:
        if oid in paying_org_ids and (mid, oid) in org_cred_pairs:
            usable_orgs_by_model.setdefault(mid, []).append(oid)

    resolutions: Dict[str, CustomModelCredentialResolution] = {}
    for model in models:
        if model.id in personal_ids:
            resolutions[model.id] = CustomModelCredentialResolution(
                can_invoke=True, source="user", organization_id=None
            )
        elif usable_orgs_by_model.get(model.id):
            org_id = sorted(usable_orgs_by_model[model.id])[0]
            resolutions[model.id] = CustomModelCredentialResolution(
                can_invoke=True, source="org", organization_id=org_id
            )
        else:
            resolutions[model.id] = CustomModelCredentialResolution(
                can_invoke=not model.requires_api_key,
                source=None,
                organization_id=None,
            )
    return resolutions


async def resolve_custom_model_credential_async(
    db: AsyncSession,
    user_id: str,
    model: Any,
    *,
    organization_id: Optional[str] = None,
    search_user_orgs: bool = False,
    include_key: bool = False,
) -> CustomModelCredentialResolution:
    """Single-model wrapper; ``include_key=True`` additionally decrypts the
    winning lane's key (``api_key`` stays None on decrypt failure, matching
    the credential services' degradation)."""
    resolution = (
        await resolve_custom_model_credentials_async(
            db,
            user_id,
            [model],
            organization_id=organization_id,
            search_user_orgs=search_user_orgs,
        )
    )[model.id]

    if not include_key or resolution.source is None:
        return resolution

    if resolution.source == "user":
        api_key = await get_credential_async(db, user_id, model.id)
    else:
        api_key = await get_org_credential_async(
            db, resolution.organization_id, model.id
        )
    return CustomModelCredentialResolution(
        can_invoke=resolution.can_invoke,
        source=resolution.source,
        organization_id=resolution.organization_id,
        api_key=api_key,
    )
