"""
Reusable access helpers for custom (BYOM) LLM models.

Mirrors the project-access helpers (``routers/projects/helpers.py``
``get_accessible_project_ids_async`` and ``routers/projects/deps.py``
``require_project_access``), simplified for models: there is no org-context
tabbing and no ``public_role`` — a custom model is either private (creator
only), org-shared via ``model_organizations``, or public.

Deliberate deviation from projects: models aren't tabbed per-org in the
pickers, so visibility is the UNION across all of the user's active
organizations rather than being scoped to a selected org context.
"""

import logging
from typing import List, Optional

from fastapi import Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from database import get_async_db
from models import LLMModel, ModelOrganization, OrganizationMembership

logger = logging.getLogger(__name__)


def _dedup_preserve_order(ids) -> List[str]:
    seen = set()
    result = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result


async def _get_active_org_ids_async(db: AsyncSession, user) -> List[str]:
    """Organization ids of the user's ACTIVE memberships."""
    rows = (
        await db.execute(
            select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == str(user.id),
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
    ).all()
    return [r[0] for r in rows]


async def get_accessible_model_ids_async(db: AsyncSession, user) -> List[str]:
    """Ids of CUSTOM (``is_official == False``) models visible to ``user``.

    Superadmin sees every custom model. Everyone else sees the union of:
    models they created, public models, and models shared with any of their
    ACTIVE organization memberships.

    Deliberate deviation from ``get_accessible_project_ids_async``: models
    aren't tabbed per-org in pickers, so visibility is the union across all
    the user's orgs instead of one selected org context.

    No ``is_active`` filter here — callers decide whether soft-deleted rows
    are relevant (e.g. the list endpoint shows a creator their own inactive
    rows).
    """
    if user.is_superadmin:
        rows = (
            await db.execute(
                select(LLMModel.id).where(LLMModel.is_official.is_(False))
            )
        ).all()
        return _dedup_preserve_order([r[0] for r in rows])

    own_or_public_rows = (
        await db.execute(
            select(LLMModel.id).where(
                LLMModel.is_official.is_(False),
                or_(
                    LLMModel.created_by == str(user.id),
                    LLMModel.is_public.is_(True),
                ),
            )
        )
    ).all()
    ids = [r[0] for r in own_or_public_rows]

    user_org_ids = await _get_active_org_ids_async(db, user)
    if user_org_ids:
        # Join through llm_models so a (theoretical) org link on an official
        # row can never leak an official id out of this custom-only helper.
        shared_rows = (
            await db.execute(
                select(ModelOrganization.model_id)
                .join(LLMModel, LLMModel.id == ModelOrganization.model_id)
                .where(
                    LLMModel.is_official.is_(False),
                    ModelOrganization.organization_id.in_(user_org_ids),
                )
            )
        ).all()
        ids.extend(r[0] for r in shared_rows)

    return _dedup_preserve_order(ids)


async def check_model_accessible_async(db: AsyncSession, user, model) -> bool:
    """Can ``user`` see/use ``model``?

    Official catalog models are visible to everyone. Custom models are
    visible to their creator, superadmins, everyone when public, and members
    of any org the model is shared with (active memberships only).
    """
    if model.is_official:
        return True
    if user.is_superadmin:
        return True
    if model.created_by is not None and str(model.created_by) == str(user.id):
        return True
    if model.is_public:
        return True

    model_org_rows = (
        await db.execute(
            select(ModelOrganization.organization_id).where(
                ModelOrganization.model_id == model.id
            )
        )
    ).all()
    model_org_ids = {r[0] for r in model_org_rows}
    if not model_org_ids:
        return False

    user_org_ids = set(await _get_active_org_ids_async(db, user))
    return bool(model_org_ids & user_org_ids)


def check_user_can_edit_model(user, model) -> bool:
    """Only the creator or a superadmin may edit a custom model.

    Org sharing NEVER grants edit rights — security reason: an editor can
    change ``base_url``, which would silently redirect every other user's
    stored credential (sent as a bearer token on generation calls) to an
    attacker-controlled endpoint. A ``created_by`` of None (creator deleted,
    FK SET NULL) leaves the model editable by superadmins only.
    """
    if user.is_superadmin:
        return True
    return model.created_by is not None and str(model.created_by) == str(user.id)


class CustomModelAccess:
    """Resolved custom-model access context from ``require_custom_model_access``."""

    __slots__ = ("model", "user")

    def __init__(self, model: LLMModel, user):
        self.model = model
        self.user = user


def require_custom_model_access(min_role: str = "view"):
    """Build a FastAPI dependency enforcing access to a CUSTOM model.

    Mirrors ``require_project_access`` (routers/projects/deps.py), minus org
    context. Semantics:

    - 404 when the row is missing, or when it is an OFFICIAL catalog row —
      the custom-model endpoints operate on custom rows only.
    - 404 (not 403, to avoid existence leaks) when the row is soft-deleted
      (``is_active == False``) and the caller is neither the creator nor a
      superadmin — soft-deleted rows stay readable by creator/superadmin only
      so they can inspect / clean up.
    - 403 when the caller can't view the model (``min_role="view"``), or
      can't edit it (``min_role="edit"`` — creator/superadmin only, see
      :func:`check_user_can_edit_model`).
    """

    async def _dependency(
        model_id: str,
        current_user=Depends(require_user),
        db: AsyncSession = Depends(get_async_db),
    ) -> CustomModelAccess:
        result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
        model: Optional[LLMModel] = result.scalar_one_or_none()
        if not model or model.is_official:
            raise HTTPException(status_code=404, detail="Custom model not found")

        is_creator_or_admin = current_user.is_superadmin or (
            model.created_by is not None
            and str(model.created_by) == str(current_user.id)
        )
        if not model.is_active and not is_creator_or_admin:
            raise HTTPException(status_code=404, detail="Custom model not found")

        if not await check_model_accessible_async(db, current_user, model):
            raise HTTPException(status_code=403, detail="Access denied")

        if min_role == "edit" and not check_user_can_edit_model(current_user, model):
            raise HTTPException(
                status_code=403,
                detail="Only the model creator or a superadmin can modify this model",
            )

        return CustomModelAccess(model=model, user=current_user)

    return _dependency
