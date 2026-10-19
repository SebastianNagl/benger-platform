"""FastAPI dependencies that close endpoints while a flag is off (core 2.42).

``require_feature_flag(name)``
    ``Depends(require_feature_flag(RUBRIC_GENERATION))``: a signed-in caller
    for whom the flag is off gets ``404 {"detail": {"code":
    "feature_disabled", "flag": "<name>"}}``. Unauthenticated requests get
    the usual 401 from ``require_user`` first.

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


def require_feature_flag(name: str):
    """Dependency factory: 404 ``feature_disabled`` unless ``name`` is on."""

    async def _require_feature_flag(
        current_user=Depends(require_user),
        db: AsyncSession = Depends(get_async_db),
    ):
        if not await service.is_enabled_for(db, current_user, name):
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
