"""``/api/v1/projects``: the projects a credential may read.

The list is the caller's accessible projects
(``get_accessible_project_ids_async``: public projects, own private ones and
those reached through organization memberships) narrowed, for keys, by the
key's project allowlist and group restriction, without Safe Exam Browser
projects. Participant-tier projects (student enrollments, shares) are not
listed but can be read by id when the caller holds that tier.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth_module import require_user
from auth_module.principal import Principal
from database import get_async_db
from project_models import Project, ProjectOrganization, Task
from routers.projects.deps import ProjectAccess
from routers.projects.helpers import (
    get_accessible_project_ids_async,
    get_effective_project_role_async,
    resolve_project_roles_batch_async,
)
from routers.v1._deps import require_scope, v1_project_access
from routers.v1._pagination import cursor_param, decode_cursor, limit_param, page
from routers.v1._schemas import ERROR_RESPONSES, Page, ProjectOut
from routers.v1.tasks import v1_bound_fields

router = APIRouter(tags=["projects"])

_CURSOR_KIND = "projects"


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def answer_fields_of(label_config: Optional[str]) -> List[Dict[str, Any]]:
    """Fields of the label config that take an answer (they point at a
    data field through ``toName``)."""
    from services.label_config.parser import LabelConfigParser

    out: List[Dict[str, Any]] = []
    for field in LabelConfigParser.extract_fields(label_config or ""):
        to_name = field.get("toName")
        if not to_name:
            continue
        entry: Dict[str, Any] = {
            "name": field["name"],
            "type": field["type"],
            "to_name": to_name,
            "options": None,
        }
        if isinstance(field.get("options"), list):
            entry["options"] = [str(o) for o in field["options"]]
        out.append(entry)
    return out


def serialize_project_public(
    project: Project,
    *,
    task_count: int,
    tier: str,
    effective_role: Optional[str],
    blinded: bool,
) -> Dict[str, Any]:
    """The public view of a project: no configuration internals, no member
    data, only what a client needs to read and answer its tasks."""
    from services.label_config.parser import LabelConfigParser

    return {
        "id": str(project.id),
        "title": project.title,
        "description": project.description,
        "kind": project.kind,
        "task_count": int(task_count or 0),
        "bound_fields": sorted(LabelConfigParser.bound_data_fields(project.label_config)),
        "answer_fields": answer_fields_of(project.label_config),
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at or project.created_at),
        "access": {"tier": tier, "effective_role": effective_role, "blinded": blinded},
    }


def _build_select_task_counts(project_ids: List[str]):
    return (
        select(Task.project_id, func.count(Task.id))
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    )


async def task_counts(db: AsyncSession, project_ids: List[str]) -> Dict[str, int]:
    if not project_ids:
        return {}
    rows = (await db.execute(_build_select_task_counts(project_ids))).all()
    return {str(pid): int(n) for pid, n in rows}


def _build_select_visible_projects(
    ids: List[str], principal: Principal, after_id: Optional[str], limit: int
):
    stmt = (
        select(Project)
        .options(selectinload(Project.project_organizations))
        .where(Project.id.in_(ids), Project.deleted_at.is_(None))
    )
    if principal.is_api_key:
        stmt = stmt.where(Project.seb_required.is_not(True))
        if principal.group_id is not None:
            stmt = stmt.where(
                Project.id.in_(
                    select(ProjectOrganization.project_id).where(
                        ProjectOrganization.organization_id == principal.organization_id,
                        ProjectOrganization.group_id == principal.group_id,
                    )
                )
            )
    if after_id is not None:
        stmt = stmt.where(Project.id > after_id)
    return stmt.order_by(Project.id.asc()).limit(limit + 1)


@router.get(
    "/projects",
    response_model=Page[ProjectOut],
    responses=ERROR_RESPONSES,
    summary="List readable projects",
)
async def list_projects(
    request: Request,
    limit: int = limit_param(),
    cursor: Optional[str] = cursor_param(),
    principal: Principal = Depends(require_scope("projects:read")),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    position = decode_cursor(_CURSOR_KIND, cursor)
    after_id = str(position.get("id")) if position and position.get("id") else None
    ids = await get_accessible_project_ids_async(db, user) or []
    if principal.is_api_key and principal.project_ids is not None:
        ids = [pid for pid in ids if str(pid) in principal.project_ids]
    if not ids:
        return {"items": [], "next_cursor": None}
    rows = (
        (await db.execute(_build_select_visible_projects(ids, principal, after_id, limit)))
        .scalars()
        .all()
    )
    items, next_cursor = page(_CURSOR_KIND, rows, limit, lambda p: {"id": str(p.id)})
    roles = await resolve_project_roles_batch_async(db, user, items)
    counts = await task_counts(db, [str(p.id) for p in items])
    out = []
    for project in items:
        role = roles.get(str(project.id), (None, False))[0]
        out.append(
            serialize_project_public(
                project,
                task_count=counts.get(str(project.id), 0),
                tier="full",
                effective_role=role,
                blinded=v1_bound_fields(principal, role, project) is not None,
            )
        )
    return {"items": out, "next_cursor": next_cursor}


@router.get(
    "/projects/{project_id}",
    response_model=ProjectOut,
    responses={**ERROR_RESPONSES, 404: {"description": "Project not found"}},
    summary="Read one project",
)
async def get_project(
    request: Request,
    access: ProjectAccess = Depends(v1_project_access("projects:read")),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    from auth_module.principal import get_principal, session_principal

    project = access.project
    principal = get_principal(request) or session_principal(user.id)
    role = await get_effective_project_role_async(db, user, project)
    counts = await task_counts(db, [str(project.id)])
    return serialize_project_public(
        project,
        task_count=counts.get(str(project.id), 0),
        tier=access.tier,
        effective_role=role,
        blinded=v1_bound_fields(principal, role, project) is not None,
    )
