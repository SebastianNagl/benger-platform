"""Shared dependencies of the ``/api/v1`` routes.

* :func:`require_scope` resolves the caller (session or access key), checks
  a key's scopes (403 ``insufficient_scope``) and counts the request against
  the key's rate limit. Sessions pass every scope check and are not
  limited here.
* :func:`v1_project_access` adds project access on top: the usual
  membership/tier rules (``routers.projects.helpers``) plus, for keys, the
  key's project allowlist, its group restriction and the SEB lock. Keys get
  404 for every project they may not see, so a key cannot probe for
  project ids.
* :func:`assert_v1_routes_scoped` fails startup when a ``/api/v1`` route
  declares no scope dependency (deny by default).
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.routing import APIRoute, APIWebSocketRoute
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scopes import scopes_satisfied
from auth_module import require_user
from auth_module.principal import Principal, get_principal, session_principal
from database import get_async_db
from project_models import Project, ProjectOrganization
from routers.projects.deps import ProjectAccess
from services.rate_limiter import enforce_key_rate_limit

V1_PREFIX = "/api/v1"
SCOPES_ATTR = "__benger_scopes__"


def _insufficient_scope(needed: Iterable[str]) -> HTTPException:
    wanted = " ".join(sorted(needed))
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "insufficient_scope",
            "message": f"This API key lacks the scope(s): {wanted}",
            "required_scopes": sorted(needed),
        },
        headers={"WWW-Authenticate": f'Bearer error="insufficient_scope", scope="{wanted}"'},
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "not_found", "message": "Project not found"},
    )


async def _resolve_principal(request: Request, user, needed: frozenset) -> Principal:
    principal = get_principal(request) or session_principal(user.id)
    if principal.is_api_key:
        if not scopes_satisfied(principal.scopes, needed):
            raise _insufficient_scope(needed)
        await enforce_key_rate_limit(request, principal)
        try:
            request.state.scope_used = " ".join(sorted(needed))[:64] or None
        except Exception:  # pragma: no cover
            pass
    return principal


def require_scope(*scopes: str):
    """Dependency for a v1 route needing ``scopes`` (all of them). An empty
    call (``require_scope()``) marks a route that needs authentication but no
    scope, such as ``/api/v1/me``."""
    needed = frozenset(scopes)

    async def _require_scope(request: Request, user=Depends(require_user)) -> Principal:
        return await _resolve_principal(request, user, needed)

    setattr(_require_scope, SCOPES_ATTR, needed)
    return _require_scope


def _build_select_group_attachment(project_id: str, org_id: str, group_id: str):
    return select(ProjectOrganization.id).where(
        ProjectOrganization.project_id == project_id,
        ProjectOrganization.organization_id == org_id,
        ProjectOrganization.group_id == group_id,
    )


async def key_may_see_project(
    db: AsyncSession, principal: Optional[Principal], project: Project
) -> bool:
    """Key-specific narrowing on top of the membership rules. Sessions are
    unaffected."""
    if principal is None or not principal.is_api_key:
        return True
    if principal.project_ids is not None and str(project.id) not in principal.project_ids:
        return False
    if getattr(project, "seb_required", False) is True:
        return False
    if principal.group_id is not None:
        row = (
            await db.execute(
                _build_select_group_attachment(
                    str(project.id), principal.organization_id, principal.group_id
                )
            )
        ).first()
        if row is None:
            return False
    return True


def v1_project_access(scope: str, *, min_role: str = "view", allow_participant: bool = True):
    """Scope check plus project access for ``{project_id}`` routes.

    Sessions get the same answers as ``require_project_access`` (404 for a
    missing project, 403 without access). Keys get 404 for every project they
    may not see.
    """
    from routers.projects.helpers import (
        check_project_accessible_async,
        check_user_can_edit_project_async,
        get_project_access_tier_async,
    )

    needed = frozenset({scope})

    async def _v1_project_access(
        project_id: str,
        request: Request,
        user=Depends(require_user),
        db: AsyncSession = Depends(get_async_db),
    ) -> ProjectAccess:
        principal = await _resolve_principal(request, user, needed)
        is_key = principal.is_api_key
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if project is None:
            raise _not_found()
        if getattr(project, "deleted_at", None) is not None and not user.is_superadmin:
            raise _not_found()
        if not await key_may_see_project(db, principal, project):
            raise _not_found()

        denied = _not_found() if is_key else HTTPException(status_code=403, detail="Access denied")
        tier = "full"
        if allow_participant and min_role != "edit":
            tier = await get_project_access_tier_async(db, user, project_id, project=project)
            if tier is None:
                raise denied
        elif not await check_project_accessible_async(db, user, project_id, project=project):
            raise denied
        if min_role == "edit" and not await check_user_can_edit_project_async(
            db, user, project_id
        ):
            raise HTTPException(
                status_code=403,
                detail={"code": "forbidden", "message": "Edit rights required"},
            )
        return ProjectAccess(project=project, user=user, tier=tier)

    setattr(_v1_project_access, SCOPES_ATTR, needed)
    return _v1_project_access


def _declared_scopes(dependant) -> Optional[frozenset]:
    """The first scope marker found in a dependency tree, or None."""
    stack = [dependant]
    while stack:
        node = stack.pop()
        marker = getattr(getattr(node, "call", None), SCOPES_ATTR, None)
        if marker is not None:
            return marker
        stack.extend(getattr(node, "dependencies", []) or [])
    return None


def _effective_routes(app: FastAPI):
    """``(original_route, effective_route)`` of every route, routers added
    with ``include_router`` flattened. FastAPI >= 0.140 keeps an include as
    one wrapper entry in ``app.routes``; the effective route carries the
    prefixed path and the dependencies of every enclosing router."""
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # pragma: no cover - older FastAPI flattens itself
        for route in app.routes:
            yield route, route
        return
    for context in iter_route_contexts(app.routes):
        yield context.original_route, context


def unscoped_v1_routes(app: FastAPI) -> List[str]:
    """``METHOD path`` of every /api/v1 route without a scope marker."""
    offenders: List[str] = []
    for original, route in _effective_routes(app):
        path = getattr(route, "path", None) or ""
        if not (path == V1_PREFIX or path.startswith(V1_PREFIX + "/")):
            continue
        if isinstance(original, APIWebSocketRoute):
            offenders.append(f"WS {path}")
            continue
        if not isinstance(original, APIRoute):
            # FastAPI's own docs routes (if ever mounted under /api/v1).
            continue
        if _declared_scopes(route.dependant) is None:
            methods = ",".join(sorted(route.methods or ()))
            offenders.append(f"{methods} {path}")
    return offenders


def assert_v1_routes_scoped(app: FastAPI) -> None:
    """Raise when any /api/v1 route lacks ``require_scope``. Called at
    startup so an unscoped public route never ships."""
    offenders = unscoped_v1_routes(app)
    if offenders:
        raise RuntimeError(
            "These /api/v1 routes declare no scope (use routers.v1._deps."
            "require_scope or v1_project_access): " + "; ".join(offenders)
        )
