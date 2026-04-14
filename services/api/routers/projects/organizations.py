"""Organization management endpoints for projects."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from models import Organization
from project_models import Project, ProjectOrganization
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

router = APIRouter()


@router.get("/{project_id}/organizations")
async def list_project_organizations(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List all organizations assigned to a project"""

    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access - user must have access to at least one of the project's organizations
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get all organizations for this project
    project_orgs = (
        db.query(ProjectOrganization)
        .options(joinedload(ProjectOrganization.organization))
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    )

    return [
        {
            "organization_id": po.organization_id,
            "organization_name": po.organization.name if po.organization else "Unknown",
            "assigned_by": po.assigned_by,
            "assigned_at": po.created_at.isoformat() if po.created_at else None,
        }
        for po in project_orgs
    ]


@router.post("/{project_id}/organizations/{organization_id}")
async def add_project_organization(
    project_id: str,
    organization_id: str,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Add an organization to a project (superadmin only)"""

    # Only superadmins can manage project organizations
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=403, detail="Only superadmins can manage project organizations"
        )

    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify organization exists
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check if already assigned
    existing = (
        db.query(ProjectOrganization)
        .filter(
            ProjectOrganization.project_id == project_id,
            ProjectOrganization.organization_id == organization_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Organization already assigned to project")

    # Create assignment
    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project_id,
        organization_id=organization_id,
        assigned_by=current_user.id,
    )

    db.add(project_org)

    # Update cached organization_ids
    project_orgs = (
        db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    )
    project.organization_ids = [org[0] for org in project_orgs]

    db.commit()

    return {
        "message": "Organization added to project successfully",
        "organization_id": organization_id,
        "organization_name": organization.name,
    }


@router.delete("/{project_id}/organizations/{organization_id}")
async def remove_project_organization(
    project_id: str,
    organization_id: str,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Remove an organization from a project (superadmin only)"""

    # Only superadmins can manage project organizations
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=403, detail="Only superadmins can manage project organizations"
        )

    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Ensure at least one organization remains
    org_count = (
        db.query(ProjectOrganization).filter(ProjectOrganization.project_id == project_id).count()
    )
    if org_count <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove last organization from project")

    # Remove assignment
    result = (
        db.query(ProjectOrganization)
        .filter(
            ProjectOrganization.project_id == project_id,
            ProjectOrganization.organization_id == organization_id,
        )
        .delete()
    )

    if result == 0:
        raise HTTPException(status_code=404, detail="Organization not assigned to project")

    # Update cached organization_ids
    project_orgs = (
        db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    )
    project.organization_ids = [org[0] for org in project_orgs]

    db.commit()

    return {"message": "Organization removed from project successfully"}
