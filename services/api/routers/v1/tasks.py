"""``/api/v1/projects/{project_id}/tasks``: blinded task reads.

Blinding (``routers/projects/tasks/blinding.py``) decides what a caller sees
of ``task.data`` and ``task.meta``:

* Sessions get exactly what the browser API serves them: full data for the
  full-data roles (ORG_ADMIN, CONTRIBUTOR, superadmin, creator), the
  label-config-bound keys otherwise, plus the post-submit reveal.
* Keys are blinded unless they hold ``tasks:read_reference`` AND the
  effective role of the key's user on the project is a full-data role. A
  personal key of an annotator stays blinded whatever scopes it holds, and
  the post-submit reveal never applies to keys.

Lists are ordered by ``inner_id`` and paginated by cursor. Responses carry a
weak ``ETag`` and ``Last-Modified``; ``If-None-Match`` answers 304.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from email.utils import format_datetime
from typing import Any, Dict, Iterable, Optional, Set

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scopes import scopes_satisfied
from auth_module import require_user
from auth_module.principal import Principal, get_principal, session_principal
from database import get_async_db
from project_models import Project, Task, TaskAssignment
from routers.projects.deps import ProjectAccess
from routers.projects.helpers import (
    TIER_ATTEMPTED,
    check_task_assigned_to_user_async,
    enforce_project_read_window_async,
    enforce_seb_async,
    get_effective_project_role_async,
    get_user_with_memberships_async,
    own_active_annotation_exists,
    seb_request_allowed_async,
    user_attempted_task_async,
)
from routers.projects.tasks.blinding import (
    blind_task_data,
    blind_task_meta,
    bound_fields_for_role,
    revealed_task_ids_async,
)
from routers.v1._deps import v1_project_access
from routers.v1._errors import V1Error
from routers.v1._pagination import cursor_param, decode_cursor, limit_param, page
from routers.v1._schemas import ERROR_RESPONSES, Page, TaskOut

router = APIRouter(tags=["tasks"])

REFERENCE_SCOPE = "tasks:read_reference"
_CURSOR_KIND = "tasks"


def v1_bound_fields(
    principal: Optional[Principal], role: Optional[str], project: Project
) -> Optional[Set[str]]:
    """The blinding decision for a v1 caller: ``None`` serves full data, a
    set reduces ``task.data`` to those bound keys.

    Keys see full data only with ``tasks:read_reference`` on top of a
    full-data role; sessions follow ``bound_fields_for_role``.
    """
    bound = bound_fields_for_role(role, project)
    if principal is not None and principal.is_api_key and bound is None:
        if scopes_satisfied(principal.scopes, {REFERENCE_SCOPE}):
            return None
        from services.label_config.parser import LabelConfigParser

        return LabelConfigParser.bound_data_fields(project.label_config)
    return bound


async def v1_task_blinding(
    db: AsyncSession, request: Request, user, project: Project
) -> Optional[Set[str]]:
    principal = get_principal(request) or session_principal(user.id)
    role = await get_effective_project_role_async(db, user, project)
    return v1_bound_fields(principal, role, project)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def serialize_task_public(
    task: Task, bound: Optional[Set[str]], revealed: Iterable[str] = ()
) -> Dict[str, Any]:
    full = bound is None or task.id in set(revealed)
    meta = blind_task_meta(task.meta, bound)
    return {
        "id": task.id,
        "inner_id": task.inner_id,
        "data": task.data if full else blind_task_data(task.data, bound),
        "meta": meta if meta is not None else {},
        "updated_at": _iso(task.updated_at or task.created_at),
    }


async def _listing_role(db: AsyncSession, user, project: Project) -> Optional[str]:
    """The org role the session task listing narrows by (lockstep with
    ``routers.projects.tasks.listing``)."""
    if user.is_superadmin:
        return "superadmin"
    from org_groups import get_attachment_group_map_async, get_user_group_context_async
    from routers.projects.tasks.listing import listing_org_role

    with_memberships = await get_user_with_memberships_async(db, str(user.id))
    if not with_memberships or not with_memberships.organization_memberships:
        return None
    return listing_org_role(
        with_memberships.organization_memberships,
        await get_attachment_group_map_async(db, str(project.id)),
        await get_user_group_context_async(db, str(user.id)),
    )


async def _visible_tasks_filter(
    db: AsyncSession, request: Request, user, project: Project, tier: str
):
    """Row filters the session listing applies: the attempted tier (and a
    Safe Exam Browser exam outside SEB) sees only own submissions, org
    annotators in manual/auto assignment mode only their open assignments."""
    from routers.projects.tasks.listing import annotator_sees_assigned_only

    seb_ok = await seb_request_allowed_async(db, user, project, request, tier=tier)
    if tier == TIER_ATTEMPTED or not seb_ok:
        return own_active_annotation_exists(user.id), False
    if annotator_sees_assigned_only(await _listing_role(db, user, project), project):
        return None, True
    return None, False


def _base_query(project_id: str, clause, assigned_only: bool, user_id: str):
    stmt = select(Task).where(Task.project_id == project_id)
    if clause is not None:
        stmt = stmt.where(clause)
    if assigned_only:
        stmt = stmt.join(
            TaskAssignment,
            and_(
                TaskAssignment.task_id == Task.id,
                TaskAssignment.user_id == str(user_id),
                TaskAssignment.status != "completed",
            ),
        )
    return stmt


def _http_date(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    try:
        return format_datetime(value, usegmt=True)
    except Exception:  # naive datetimes from odd rows
        return None


def weak_etag(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(repr(p) for p in parts).encode("utf-8")).hexdigest()
    return f'W/"{digest[:32]}"'


def etag_matches(request: Request, etag: str) -> bool:
    header = request.headers.get("if-none-match")
    if not header:
        return False
    if header.strip() == "*":
        return True
    wanted = etag[2:] if etag.startswith("W/") else etag
    for candidate in header.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == wanted:
            return True
    return False


def conditional_response(
    request: Request, content: Any, etag: str, last_modified: Optional[datetime]
) -> Response:
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    lm = _http_date(last_modified)
    if lm:
        headers["Last-Modified"] = lm
    if etag_matches(request, etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=content, headers=headers)


def _latest(*values: Optional[datetime]) -> Optional[datetime]:
    present = [v for v in values if v is not None]
    return max(present) if present else None


@router.get(
    "/projects/{project_id}/tasks",
    response_model=Page[TaskOut],
    responses={**ERROR_RESPONSES, 304: {"description": "Not modified (If-None-Match)"}},
    summary="List the tasks of a project",
)
async def list_tasks(
    request: Request,
    limit: int = limit_param(),
    cursor: Optional[str] = cursor_param(),
    access: ProjectAccess = Depends(v1_project_access("tasks:read")),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Tasks ordered by ``inner_id``. ``data`` and ``meta`` are blinded as
    described for the project's ``access.blinded``."""
    project = access.project
    await enforce_project_read_window_async(db, user, project, tier=access.tier)
    clause, assigned_only = await _visible_tasks_filter(db, request, user, project, access.tier)
    position = decode_cursor(_CURSOR_KIND, cursor)
    bound = await v1_task_blinding(db, request, user, project)
    blinded = bound is not None

    base = _base_query(project.id, clause, assigned_only, user.id).subquery()
    # The id fingerprint changes when the visible set changes without any
    # task changing (an assignment moved, a submission made). hashtext, not
    # md5: the production Postgres runs in FIPS mode.
    stats = (
        await db.execute(
            select(
                func.count(),
                func.max(func.coalesce(base.c.updated_at, base.c.created_at)),
                func.sum(func.hashtext(base.c.id)),
            ).select_from(base)
        )
    ).one()
    count, newest, fingerprint = int(stats[0] or 0), stats[1], stats[2]
    last_modified = _latest(project.updated_at, project.created_at, newest)
    etag = weak_etag(
        "tasks", project.id, project.updated_at, count, newest, fingerprint, cursor, limit,
        blinded, sorted(bound) if bound is not None else None,
    )
    if etag_matches(request, etag):
        return conditional_response(request, None, etag, last_modified)

    stmt = _base_query(project.id, clause, assigned_only, user.id)
    if position is not None:
        try:
            after_inner = int(position["inner_id"])
            after_id = str(position["id"])
        except (KeyError, TypeError, ValueError):
            raise V1Error(400, "invalid_cursor", "The cursor is malformed")
        stmt = stmt.where(
            or_(
                Task.inner_id > after_inner,
                and_(Task.inner_id == after_inner, Task.id > after_id),
            )
        )
    rows = (
        (await db.execute(stmt.order_by(Task.inner_id.asc(), Task.id.asc()).limit(limit + 1)))
        .scalars()
        .all()
    )
    items, next_cursor = page(
        _CURSOR_KIND, rows, limit, lambda t: {"inner_id": t.inner_id, "id": t.id}
    )
    principal = get_principal(request)
    revealed: Set[str] = set()
    if blinded and (principal is None or not principal.is_api_key):
        revealed = await revealed_task_ids_async(db, user, project, [t.id for t in items])
    content = {
        "items": [serialize_task_public(t, bound, revealed) for t in items],
        "next_cursor": next_cursor,
    }
    return conditional_response(request, content, etag, last_modified)


@router.get(
    "/projects/{project_id}/tasks/{task_id}",
    response_model=TaskOut,
    responses={
        **ERROR_RESPONSES,
        304: {"description": "Not modified (If-None-Match)"},
        404: {"description": "Project or task not found"},
    },
    summary="Read one task",
)
async def get_task(
    task_id: str,
    request: Request,
    access: ProjectAccess = Depends(v1_project_access("tasks:read")),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    project = access.project
    task = (
        await db.execute(select(Task).where(Task.id == task_id, Task.project_id == project.id))
    ).scalar_one_or_none()
    if task is None:
        raise V1Error(404, "task_not_found", "Task not found")
    if access.tier == TIER_ATTEMPTED and not await user_attempted_task_async(
        db, user.id, task_id
    ):
        raise V1Error(404, "task_not_found", "Task not found")
    if not await check_task_assigned_to_user_async(db, user, task_id, project):
        raise V1Error(404, "task_not_found", "Task not found")
    await enforce_project_read_window_async(db, user, project, tier=access.tier)
    await enforce_seb_async(db, user, project, request, tier=access.tier, read_task_id=task_id)

    bound = await v1_task_blinding(db, request, user, project)
    principal = get_principal(request)
    revealed: Set[str] = set()
    if bound is not None and (principal is None or not principal.is_api_key):
        revealed = await revealed_task_ids_async(db, user, project, [task.id])
    updated = task.updated_at or task.created_at
    etag = weak_etag(
        "task", task.id, updated, bound is None or task.id in revealed,
        sorted(bound) if bound is not None else None,
    )
    return conditional_response(
        request, serialize_task_public(task, bound, revealed), etag, updated
    )
