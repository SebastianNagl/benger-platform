"""FastAPI dependencies that close endpoints while a flag is off (core 2.42).

``require_feature_flag(name, key_organization=False)``
    ``Depends(require_feature_flag(RUBRIC_GENERATION))``: a signed-in caller
    for whom the flag is off gets ``404 {"detail": {"code":
    "feature_disabled", "flag": "<name>"}}``. Unauthenticated requests get
    the usual 401 from ``require_user`` first. ``key_organization=True``
    lets an organization key's organization count (platform flags on routes
    keys reach).

``require_extension_active(package, ungated=())``
    The gate the platform puts on every router of an extension package
    (``extensions.include_extension_routers``): 404 ``feature_disabled``
    with ``flag: "extension.<EXTENSION_ID>"`` unless the package is active
    in the request's context. Routes listed in ``ungated`` (``(METHOD, full
    path template)``) pass whenever the package is loaded. It needs no
    login: the context carries the session user from the JWT, anonymous
    callers count only ``everyone``.

``require_extension_active_v1(package)``
    The same for ``/api/v1`` overlay routers, keyed to the access key's
    organization. It depends on ``require_user``, so FastAPI's dependency
    cache resolves the key once per request.

404 rather than 403 because for that caller the feature does not exist.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Set, Tuple

from fastapi import Depends, HTTPException, Request
from starlette.requests import HTTPConnection
from sqlalchemy.ext.asyncio import AsyncSession

import extension_activation as activation
from auth_module import require_user
from database import get_async_db
from feature_flags import registry, service
from feature_flags.registry import FEATURE_DISABLED


def feature_disabled_detail(name: str) -> Dict[str, str]:
    return {"code": FEATURE_DISABLED, "flag": name}


def feature_disabled_error(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=feature_disabled_detail(name))


def require_feature_flag(name: str, *, key_organization: bool = False):
    """Dependency factory: 404 ``feature_disabled`` unless ``name`` is on.

    ``key_organization=True``: for an organization access key, the key's
    organization counts like a membership of the caller (the rule
    ``public_api`` follows), so allowlisting an organization opens the
    feature to its keys too."""

    async def _require_feature_flag(
        request: Request,
        current_user=Depends(require_user),
        db: AsyncSession = Depends(get_async_db),
    ):
        organization_id = None
        if key_organization:
            from auth_module.principal import get_principal

            principal = get_principal(request)
            if principal is not None and principal.is_api_key:
                organization_id = principal.organization_id
        if not await service.is_enabled_for_caller(
            db, current_user, name, organization_id=organization_id
        ):
            raise feature_disabled_error(name)
        return current_user

    _require_feature_flag.__name__ = f"require_feature_flag_{name}"
    return _require_feature_flag


def route_key(conn: HTTPConnection) -> Optional[Tuple[str, str]]:
    """``(METHOD, full path template)`` of the matched route; WebSocket
    routes use ``*`` like ``extensions._route_signatures``."""
    from middleware.api_usage import route_template

    template = route_template(conn.scope)
    if not template:
        return None
    return (str(conn.scope.get("method") or "*").upper(), template)


def _master_name(package: str) -> str:
    return registry.master_for_owner(package) or f"{registry.MASTER_PREFIX}{package}"


async def _prime(db: AsyncSession) -> None:
    """Load the snapshot through the request's async session once, so the
    synchronous activation check never opens a second connection."""
    ctx = activation.current_context()
    if "snapshot" in ctx.memo:
        return
    try:
        activation.prime_snapshot(await service.load_snapshot(db, sync=False), ctx)
    except Exception:
        # The synchronous lane retries and falls back to the defaults.
        pass


def require_extension_active(package: str, ungated: Iterable[Tuple[str, str]] = ()):
    """Dependency factory for an extension package's routers."""
    ungated_set: Set[Tuple[str, str]] = {(m.upper(), p) for m, p in ungated}

    async def _require_extension_active(
        conn: HTTPConnection, db: AsyncSession = Depends(get_async_db)
    ) -> None:
        if ungated_set and route_key(conn) in ungated_set:
            return
        if registry.master_for_owner(package) is None:
            return
        await _prime(db)
        if not activation.package_active(package, activation.GATED):
            raise feature_disabled_error(_master_name(package))

    _require_extension_active.__name__ = f"require_extension_active_{package}"
    return _require_extension_active


def require_extension_active_v1(package: str):
    """Dependency factory for an extension package's ``/api/v1`` routers."""

    async def _require_extension_active_v1(
        request: Request,
        user=Depends(require_user),
        db: AsyncSession = Depends(get_async_db),
    ) -> None:
        if registry.master_for_owner(package) is None:
            return
        from auth_module.principal import get_principal

        principal = get_principal(request)
        org_ids = None
        if principal is not None and principal.is_api_key and principal.organization_id:
            org_ids = [principal.organization_id]
        await _prime(db)
        user_id = getattr(user, "id", None)
        with activation.use_context(user_id=user_id, org_ids=org_ids):
            active = activation.package_active(package, activation.GATED)
        if not active:
            raise feature_disabled_error(_master_name(package))

    _require_extension_active_v1.__name__ = f"require_extension_active_v1_{package}"
    return _require_extension_active_v1


# ---------------------------------------------------------------------------
# Platform flags of the experiment features (core 2.71)
# ---------------------------------------------------------------------------


def key_organization_of(request: Optional[Request]) -> Optional[str]:
    """The organization of the request's organization access key, else None."""
    if request is None:
        return None
    from auth_module.principal import get_principal

    try:
        principal = get_principal(request)
    except Exception:
        return None
    if principal is not None and principal.is_api_key:
        return principal.organization_id
    return None


async def flag_on(db: AsyncSession, user, name: str, request: Optional[Request] = None) -> bool:
    """Whether ``name`` is on for this caller (an organization key's
    organization counts), for handlers whose behaviour changes with a flag."""
    return await service.is_enabled_for_caller(
        db, user, name, organization_id=key_organization_of(request)
    )


def flag_on_sync(db, user, name: str, request: Optional[Request] = None) -> bool:
    """Sync twin of :func:`flag_on`."""
    return service.is_enabled_for_caller_sync(
        db, user, name, organization_id=key_organization_of(request)
    )


#: Router gate of everything ``variant_experiments`` covers. One callable, so
#: FastAPI resolves it once per request however many routers carry it.
require_variant_experiments = require_feature_flag(
    registry.VARIANT_EXPERIMENTS, key_organization=True
)

#: Router gate of the compliance records and their routes.
require_compliance_records = require_feature_flag(registry.COMPLIANCE_RECORDS)


async def context_flag_on(db: AsyncSession, name: str) -> bool:
    """``name`` for the current request's caller when the handler code at
    hand has no user of its own (shared helpers called from several routes):
    an answer a ``feature_flags.scope`` holds, else the request context's
    user (``extension_activation``; the API middleware sets it from the
    session)."""
    from feature_flags.scope import scoped_answer

    answer = scoped_answer(name)
    if answer is not None:
        return answer
    user_id = activation.current_context().user_id
    return await service.is_enabled_for(db, user_id, name)
