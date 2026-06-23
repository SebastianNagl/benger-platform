"""Member management endpoints for projects."""


from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_async_db
from models import OrganizationMembership, User
from project_models import Annotation, ProjectMember, ProjectOrganization
from routers.projects.deps import ProjectAccess, require_project_access

router = APIRouter()


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    _access: ProjectAccess = Depends(require_project_access()),
):
    """List all members of a project"""

    # Project existence + read access enforced by require_project_access
    # (404 "Project not found" / 403 "Access denied").

    # Get direct project members
    direct_result = await db.execute(
        select(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .where(ProjectMember.project_id == project_id, ProjectMember.is_active == True)  # noqa: E712
    )
    direct_members = direct_result.scalars().unique().all()

    # Get organization IDs assigned to the project
    org_ids_result = await db.execute(
        select(ProjectOrganization.organization_id).where(
            ProjectOrganization.project_id == project_id
        )
    )
    project_org_ids = [row[0] for row in org_ids_result.all()]

    # Get members from project organizations only
    org_members = []
    if project_org_ids:
        org_result = await db.execute(
            select(OrganizationMembership)
            .options(
                joinedload(OrganizationMembership.user),
                joinedload(OrganizationMembership.organization),
            )
            .where(
                OrganizationMembership.organization_id.in_(project_org_ids),
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
        org_members = org_result.scalars().unique().all()

    # Combine results
    members = []

    # Add direct members
    for pm in direct_members:
        members.append(
            {
                "id": pm.id,
                "user_id": pm.user_id,
                "name": pm.user.name if pm.user else "Unknown",
                "email": pm.user.email if pm.user else "",
                "role": pm.role,
                "is_direct_member": True,
                "organization_id": None,
                "organization_name": None,
                "added_at": pm.created_at.isoformat() if pm.created_at else None,
            }
        )

    # Add organization members (avoiding duplicates by user_id)
    seen_user_ids = {pm.user_id for pm in direct_members}
    for om in org_members:
        if om.user_id not in seen_user_ids:
            seen_user_ids.add(om.user_id)
            members.append(
                {
                    "id": f"org-{om.id}",
                    "user_id": om.user_id,
                    "name": om.user.name if om.user else "Unknown",
                    "email": om.user.email if om.user else "",
                    "role": om.role,
                    "is_direct_member": False,
                    "organization_id": om.organization_id,
                    "organization_name": (om.organization.name if om.organization else "Unknown"),
                    "added_at": om.joined_at.isoformat() if om.joined_at else None,
                }
            )

    return members


@router.get("/{project_id}/annotators")
async def get_project_annotators(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    _access: ProjectAccess = Depends(require_project_access()),
):
    """Get users who have actually annotated this project.

    Returns users who have created at least one non-cancelled annotation
    in this project, along with their annotation count.
    """
    # Project existence + read access enforced by require_project_access
    # (404 "Project not found" / 403 "Access denied").

    # Query users who have annotated this project
    stmt = (
        select(
            User.id.label("user_id"),
            User.name,
            User.pseudonym,
            User.use_pseudonym,
            func.count(Annotation.id).label("annotation_count"),
        )
        .join(Annotation, Annotation.completed_by == User.id)
        .where(
            Annotation.project_id == project_id,
            Annotation.was_cancelled == False,  # noqa: E712
        )
        .group_by(User.id, User.name, User.pseudonym, User.use_pseudonym)
        .order_by(func.count(Annotation.id).desc())
    )

    results = (await db.execute(stmt)).all()

    annotators = []
    for r in results:
        display_name = r.pseudonym if r.use_pseudonym and r.pseudonym else r.name
        annotators.append(
            {
                "id": r.user_id,
                "name": display_name or "Unknown",
                "count": r.annotation_count,
            }
        )

    return {"annotators": annotators}
