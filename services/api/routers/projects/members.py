"""Member management endpoints for projects."""


from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from models import OrganizationMembership, User
from project_models import Annotation, Project, ProjectMember, ProjectOrganization
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

router = APIRouter()


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List all members of a project"""

    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get direct project members
    direct_members = (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.project_id == project_id, ProjectMember.is_active == True)
        .all()
    )

    # Get organization IDs assigned to the project
    project_org_ids = [
        org_id[0]
        for org_id in db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    ]

    # Get members from project organizations only
    org_members = []
    if project_org_ids:
        org_members = (
            db.query(OrganizationMembership)
            .options(
                joinedload(OrganizationMembership.user),
                joinedload(OrganizationMembership.organization),
            )
            .filter(
                OrganizationMembership.organization_id.in_(project_org_ids),
                OrganizationMembership.is_active == True,
            )
            .all()
        )

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
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get users who have actually annotated this project.

    Returns users who have created at least one non-cancelled annotation
    in this project, along with their annotation count.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Query users who have annotated this project
    query = (
        db.query(
            User.id.label("user_id"),
            User.name,
            User.pseudonym,
            User.use_pseudonym,
            func.count(Annotation.id).label("annotation_count"),
        )
        .join(Annotation, Annotation.completed_by == User.id)
        .filter(
            Annotation.project_id == project_id,
            Annotation.was_cancelled == False,
        )
        .group_by(User.id, User.name, User.pseudonym, User.use_pseudonym)
        .order_by(func.count(Annotation.id).desc())
    )

    results = query.all()

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
