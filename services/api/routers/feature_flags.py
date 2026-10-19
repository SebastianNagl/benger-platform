"""Feature flags API (platform, core 2.41).

Mounted at ``/api/feature-flags`` (:data:`router`) and, for one release, at
the pre-2.41 path ``/api/ext/feature-flags`` (:data:`legacy_router`, the
extended edition's old mount; the platform's copy is included first, so it
wins over an older overlay's).

- GET    /me                         -> ``{"flags": {name: bool},
                                          "extensions": {EXTENSION_ID: bool}}``
                                        for the caller, anonymous callers
                                        included (legacy path: flat
                                        ``{name: bool}``, login required)
- GET    ""                          -> every flag (superadmin): registered
                                        ones in registry order, then rows no
                                        loaded package registers
                                        (``registered: false``)
- PUT    /{name}                     -> ``{"state": "off"|"everyone"|"allowlist"}`` (superadmin)
- POST   /{name}/targets             -> ``{"user_id"}`` or ``{"organization_id"}`` (superadmin)
- DELETE /{name}/targets/{target_id} -> remove one allowlist entry (superadmin)
- DELETE /{name}                     -> delete an unregistered row and its
                                        allowlist (superadmin); 409
                                        ``flag_registered`` for a registered flag

Errors: an unregistered flag name is 404 ``unknown_flag`` (PUT/targets) ;
an invalid state or a target body that does not name exactly one of
user/organization is 422; an allowlist entry that already exists is 409
``target_exists``; a target naming a user or organization that does not
exist is 404 ``user_not_found`` / ``organization_not_found``. Every write
drops the cached snapshot.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from auth_module.dependencies import optional_user, require_superadmin
from database import get_async_db
from feature_flags import service
from feature_flags.registry import (
    FlagDefinition,
    all_flags,
    flag,
    flag_owner,
    is_master,
)

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}

State = Literal["off", "everyone", "allowlist"]


class FlagTargetOut(BaseModel):
    id: str
    kind: Literal["user", "organization"]
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    #: User: the real name; organization: its display name.
    name: Optional[str] = None
    pseudonym: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None


class FlagOut(BaseModel):
    name: str
    description: str
    #: The package that registered the flag (``platform``,
    #: ``benger_extended``, ...); None for an unregistered row.
    owner: Optional[str] = None
    state: State
    #: None for an unregistered row.
    default_state: Optional[State] = None
    updated_at: Optional[datetime] = None
    targets: List[FlagTargetOut] = []
    #: False for a row no loaded package registers (deletable).
    registered: bool = True
    #: True for a package's master flag (``extension.<EXTENSION_ID>``).
    is_master: bool = False


class MyFlagsOut(BaseModel):
    flags: Dict[str, bool]
    extensions: Dict[str, bool]


class FlagStateUpdate(BaseModel):
    state: State


class FlagTargetCreate(BaseModel):
    user_id: Optional[str] = None
    organization_id: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one(self):
        if bool(self.user_id) == bool(self.organization_id):
            raise ValueError("Pass exactly one of user_id and organization_id.")
        return self


def _no_store(response: Response) -> None:
    for key, value in NO_CACHE_HEADERS.items():
        response.headers[key] = value


def _unknown_flag(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "unknown_flag", "flag": name})


def _definition_or_404(name: str) -> FlagDefinition:
    definition = flag(name)
    if definition is None:
        raise _unknown_flag(name)
    return definition


async def _ensure_row(db: AsyncSession, definition: FlagDefinition):
    """The flag's row, inserted with its default if a sync has not run yet."""
    from models import FeatureFlag

    await db.execute(
        pg_insert(FeatureFlag)
        .values(
            id=str(uuid.uuid4()),
            name=definition.name,
            description=definition.description,
            state=definition.default_state,
        )
        .on_conflict_do_nothing(index_elements=["name"])
    )
    return (
        await db.execute(select(FeatureFlag).where(FeatureFlag.name == definition.name))
    ).scalar_one()


def _target_out(target, user, org) -> FlagTargetOut:
    if target.user_id:
        return FlagTargetOut(
            id=target.id,
            kind="user",
            user_id=target.user_id,
            name=getattr(user, "name", None),
            pseudonym=getattr(user, "pseudonym", None),
            email=getattr(user, "email", None),
            username=getattr(user, "username", None),
        )
    return FlagTargetOut(
        id=target.id,
        kind="organization",
        organization_id=target.organization_id,
        name=(getattr(org, "display_name", None) or getattr(org, "name", None)),
    )


async def _targets_by_flag(db: AsyncSession, flag_ids: List[str]) -> Dict[str, List[FlagTargetOut]]:
    from models import FeatureFlagTarget, Organization, User

    if not flag_ids:
        return {}
    rows = (
        await db.execute(
            select(FeatureFlagTarget, User, Organization)
            .outerjoin(User, User.id == FeatureFlagTarget.user_id)
            .outerjoin(Organization, Organization.id == FeatureFlagTarget.organization_id)
            .where(FeatureFlagTarget.flag_id.in_(flag_ids))
            .order_by(FeatureFlagTarget.created_at, FeatureFlagTarget.id)
        )
    ).all()
    out: Dict[str, List[FlagTargetOut]] = {}
    for target, user, org in rows:
        out.setdefault(target.flag_id, []).append(_target_out(target, user, org))
    return out


def _flag_out(definition: FlagDefinition, row, targets: List[FlagTargetOut]) -> FlagOut:
    return FlagOut(
        name=definition.name,
        description=definition.description,
        owner=flag_owner(definition.name),
        state=getattr(row, "state", None) or definition.default_state,
        default_state=definition.default_state,
        updated_at=getattr(row, "updated_at", None) or getattr(row, "created_at", None),
        targets=targets if row is not None else [],
        registered=True,
        is_master=is_master(definition.name),
    )


def _unregistered_out(row, targets: List[FlagTargetOut]) -> FlagOut:
    state = row.state if row.state in ("off", "everyone", "allowlist") else "off"
    return FlagOut(
        name=row.name,
        description=row.description or "",
        owner=None,
        state=state,
        default_state=None,
        updated_at=getattr(row, "updated_at", None) or getattr(row, "created_at", None),
        targets=targets,
        registered=False,
        is_master=row.name.startswith("extension."),
    )


async def _flag_payload(db: AsyncSession, definition: FlagDefinition, row) -> FlagOut:
    targets = (await _targets_by_flag(db, [row.id])).get(row.id, [])
    return _flag_out(definition, row, targets)


# --------------------------------------------------------------------------- #
# Handlers (shared by both mounts)
# --------------------------------------------------------------------------- #
async def my_feature_flags(
    response: Response,
    current_user=Depends(optional_user),
    db: AsyncSession = Depends(get_async_db),
) -> MyFlagsOut:
    """Every registered flag and every package's master flag for the
    caller. Anonymous callers get ``everyone`` flags only."""
    _no_store(response)
    flags = await service.evaluate_all_for(db, current_user)
    return MyFlagsOut(flags=flags, extensions=service.extensions_view(flags))


async def my_feature_flags_legacy(
    response: Response,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, bool]:
    """Pre-2.41 shape: flat ``{name: bool}``, login required."""
    _no_store(response)
    return await service.evaluate_all_for(db, current_user)


async def list_feature_flags(
    response: Response,
    _admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
) -> List[FlagOut]:
    from models import FeatureFlag

    _no_store(response)
    # Make sure the table holds every registered flag before showing it.
    await service.load_snapshot(db)
    registered = all_flags()
    registered_names = {d.name for d in registered}
    all_rows = list((await db.execute(select(FeatureFlag))).scalars())
    rows = {row.name: row for row in all_rows}
    targets = await _targets_by_flag(db, [r.id for r in all_rows])
    out = [
        _flag_out(
            definition,
            rows.get(definition.name),
            targets.get(getattr(rows.get(definition.name), "id", None), []),
        )
        for definition in registered
    ]
    out.extend(
        _unregistered_out(row, targets.get(row.id, []))
        for row in sorted(all_rows, key=lambda r: r.name)
        if row.name not in registered_names
    )
    return out


async def set_feature_flag_state(
    name: str,
    body: FlagStateUpdate,
    _admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
) -> FlagOut:
    definition = _definition_or_404(name)
    row = await _ensure_row(db, definition)
    row.state = body.state
    await db.commit()
    service.invalidate_cache()
    await db.refresh(row)
    return await _flag_payload(db, definition, row)


async def add_feature_flag_target(
    name: str,
    body: FlagTargetCreate,
    admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
) -> FlagTargetOut:
    from models import FeatureFlagTarget, Organization, User

    definition = _definition_or_404(name)
    user = org = None
    if body.user_id:
        user = await db.get(User, body.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail={"code": "user_not_found"})
    else:
        org = await db.get(Organization, body.organization_id)
        if org is None:
            raise HTTPException(status_code=404, detail={"code": "organization_not_found"})
    row = await _ensure_row(db, definition)
    existing_filter = (
        FeatureFlagTarget.user_id == body.user_id
        if body.user_id
        else FeatureFlagTarget.organization_id == body.organization_id
    )
    duplicate = (
        await db.execute(
            select(FeatureFlagTarget.id).where(
                FeatureFlagTarget.flag_id == row.id, existing_filter
            )
        )
    ).first()
    target_exists = HTTPException(status_code=409, detail={"code": "target_exists"})
    if duplicate is not None:
        raise target_exists
    target = FeatureFlagTarget(
        id=str(uuid.uuid4()),
        flag_id=row.id,
        user_id=body.user_id or None,
        organization_id=body.organization_id or None,
        created_by=str(admin.id),
    )
    db.add(target)
    try:
        await db.commit()
    except IntegrityError as exc:
        # A concurrent add of the same entry won the unique constraint.
        await db.rollback()
        raise target_exists from exc
    service.invalidate_cache()
    return _target_out(target, user, org)


async def remove_feature_flag_target(
    name: str,
    target_id: str,
    _admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    from models import FeatureFlag, FeatureFlagTarget

    _definition_or_404(name)
    target = (
        await db.execute(
            select(FeatureFlagTarget)
            .join(FeatureFlag, FeatureFlag.id == FeatureFlagTarget.flag_id)
            .where(FeatureFlagTarget.id == target_id, FeatureFlag.name == name)
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "target_not_found"})
    await db.delete(target)
    await db.commit()
    service.invalidate_cache()
    return Response(status_code=204)


async def delete_feature_flag(
    name: str,
    _admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a row no loaded package registers (its targets go with it via
    the FK cascade). A registered flag cannot be deleted: 409."""
    from models import FeatureFlag

    if flag(name) is not None:
        raise HTTPException(status_code=409, detail={"code": "flag_registered", "flag": name})
    row = (
        await db.execute(select(FeatureFlag).where(FeatureFlag.name == name))
    ).scalar_one_or_none()
    if row is None:
        raise _unknown_flag(name)
    await db.delete(row)
    await db.commit()
    service.invalidate_cache()
    return Response(status_code=204)


def _build_router(*, legacy: bool) -> APIRouter:
    router = APIRouter()
    if legacy:
        router.add_api_route("/me", my_feature_flags_legacy, methods=["GET"])
    else:
        router.add_api_route(
            "/me", my_feature_flags, methods=["GET"], response_model=MyFlagsOut
        )
    router.add_api_route(
        "", list_feature_flags, methods=["GET"], response_model=List[FlagOut]
    )
    router.add_api_route(
        "/{name}", set_feature_flag_state, methods=["PUT"], response_model=FlagOut
    )
    router.add_api_route(
        "/{name}", delete_feature_flag, methods=["DELETE"], status_code=204
    )
    router.add_api_route(
        "/{name}/targets",
        add_feature_flag_target,
        methods=["POST"],
        response_model=FlagTargetOut,
        status_code=201,
    )
    router.add_api_route(
        "/{name}/targets/{target_id}",
        remove_feature_flag_target,
        methods=["DELETE"],
        status_code=204,
    )
    return router


router = _build_router(legacy=False)
legacy_router = _build_router(legacy=True)

PREFIX = "/api/feature-flags"
LEGACY_PREFIX = "/api/ext/feature-flags"
