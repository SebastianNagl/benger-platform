"""
Label Config Version Management Endpoints

Provides API endpoints for retrieving, comparing, and analyzing label_config schema versions.
"""


from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.authorization import Permission, auth_service
from auth_module import require_user
from auth_module.models import User
from database import get_db
from label_config_version_service import LabelConfigVersionService
from models import Generation as DBGeneration
from project_models import Project
from routers.projects.helpers import get_org_context_from_request

router = APIRouter()


@router.get("/{project_id}/label-config/versions")
async def get_label_config_versions(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """
    List all label_config versions for a project.

    Returns metadata for each version including creation date, author, and description.
    """
    # Check project access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Verify user has permission to view project
    org_context = get_org_context_from_request(request)
    if not auth_service.check_project_access(current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this project",
        )

    versions = LabelConfigVersionService.list_versions(project)

    return {
        "project_id": project_id,
        "current_version": project.label_config_version,
        "total_versions": len(versions),
        "versions": versions,
    }


@router.get("/{project_id}/label-config/versions/{version}")
async def get_label_config_version(
    project_id: str,
    version: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """
    Get the label_config schema for a specific version.

    Returns the full XML/JSON schema definition for that version.
    """
    # Check project access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Verify user has permission
    org_context = get_org_context_from_request(request)
    if not auth_service.check_project_access(current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this project",
        )

    schema = LabelConfigVersionService.get_version_schema(project, version)

    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version} not found for project {project_id}",
        )

    return {
        "project_id": project_id,
        "version": version,
        "schema": schema,
        "is_current": version == project.label_config_version,
    }


@router.get("/{project_id}/label-config/compare/{version1}/{version2}")
async def compare_label_config_versions(
    project_id: str,
    version1: str,
    version2: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """
    Compare two label_config versions.

    Returns a diff showing fields added, removed, and kept between versions.
    """
    # Check project access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Verify user has permission
    org_context = get_org_context_from_request(request)
    if not auth_service.check_project_access(current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this project",
        )

    comparison = LabelConfigVersionService.compare_versions(project, version1, version2)

    if "error" in comparison:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=comparison["error"])

    return {"project_id": project_id, **comparison}


@router.get("/{project_id}/generations/version-distribution")
async def get_generation_version_distribution(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """
    Get the distribution of generations across label_config versions.

    Returns count of generations for each schema version, useful for understanding
    which versions have the most data.
    """
    # Check project access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Verify user has permission
    org_context = get_org_context_from_request(request)
    if not auth_service.check_project_access(current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this project",
        )

    # Query generation counts grouped by version
    from sqlalchemy import func

    results = (
        db.query(DBGeneration.label_config_version, func.count(DBGeneration.id).label('count'))
        .filter(DBGeneration.project_id == project_id)
        .filter(DBGeneration.label_config_version.isnot(None))
        .group_by(DBGeneration.label_config_version)
        .all()
    )

    distribution = {version: count for version, count in results}

    # Calculate totals
    total_generations = sum(distribution.values())

    return {
        "project_id": project_id,
        "current_version": project.label_config_version,
        "total_generations": total_generations,
        "distribution": distribution,
        "distribution_percentages": {
            version: (count / total_generations * 100) if total_generations > 0 else 0
            for version, count in distribution.items()
        },
    }
