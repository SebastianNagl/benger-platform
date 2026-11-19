"""
Label Config Version Management Endpoints

Provides API endpoints for retrieving, comparing, and analyzing label_config
schema versions, the config in the expanded form Label Studio reads, and the
slot map of a task (which control names hold which item's answers).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Permission, auth_service
from auth_module import require_user
from auth_module.models import User
from database import get_async_db
from feature_flags.deps import require_variant_experiments
from label_config_repeater import derive_slot_map, has_repeater
from services.label_config.project_expansion import expanded_project_label_config_async
from services.label_config.version_service import LabelConfigVersionService
from models import Generation as DBGeneration
from project_models import Project, Task

router = APIRouter()


async def _viewable_project(project_id: str, db: AsyncSession, current_user: User) -> Project:
    """The project, or 404 / 403 as the version routes answer."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_VIEW, db
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this project",
        )
    return project


# Per-item answers (variant_experiments, core 2.71): 404 feature_disabled while off.
@router.get(
    "/{project_id}/label-config/label-studio",
    dependencies=[Depends(require_variant_experiments)],
)
async def get_label_config_for_label_studio(
    project_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
):
    """The project's label config in the form to paste into Label Studio.

    Every ``<Repeater>`` is expanded to plain indexed controls (``risk_0``,
    ``risk_1``, ...), as Label Studio itself expands it, to the longest array
    any task of the project holds. Label Studio has marked the Repeater tag
    for deprecation, so the expanded form keeps an exported project readable
    by every Label Studio version; the stored results use the same names.
    A config without a Repeater comes back unchanged.
    """
    project = await _viewable_project(project_id, db, current_user)
    expanded, counts = await expanded_project_label_config_async(
        db, project_id, project.label_config
    )
    return {
        "project_id": project_id,
        "label_config": expanded,
        "expanded": has_repeater(project.label_config),
        "item_counts": counts,
    }


@router.get(
    "/{project_id}/label-config/slots",
    dependencies=[Depends(require_variant_experiments)],
)
async def get_label_config_slot_map(
    project_id: str,
    task_id: str = Query(..., description="The task whose item counts expand the config"),
    pattern: Optional[List[str]] = Query(
        None,
        description=(
            "Slot-name patterns for hand-written indexed controls, with {idx} where "
            "the slot number stands, e.g. credibility_{idx}"
        ),
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
):
    """Which control names hold which slot's answers in one task.

    One group per ``<Repeater>`` (slot index = Label Studio's 0-based item
    index) and, with ``pattern``, one group for the hand-written indexed
    controls the patterns match (slot index = the number in the name).
    """
    project = await _viewable_project(project_id, db, current_user)
    task = (
        await db.execute(select(Task).where(Task.id == task_id, Task.project_id == project_id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found in project {project_id}",
        )
    try:
        groups = derive_slot_map(project.label_config, task.data or {}, patterns=pattern)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {"project_id": project_id, "task_id": task_id, "groups": groups}


@router.get("/{project_id}/label-config/versions")
async def get_label_config_versions(
    project_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
):
    """
    List all label_config versions for a project.

    Returns metadata for each version including creation date, author, and description.
    """
    # Check project access
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Verify user has permission to view project
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_VIEW, db
    ):
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
):
    """
    Get the label_config schema for a specific version.

    Returns the full XML/JSON schema definition for that version.
    """
    # Check project access
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Verify user has permission
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_VIEW, db
    ):
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
):
    """
    Compare two label_config versions.

    Returns a diff showing fields added, removed, and kept between versions.
    """
    # Check project access
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Verify user has permission
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_VIEW, db
    ):
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
):
    """
    Get the distribution of generations across label_config versions.

    Returns count of generations for each schema version, useful for understanding
    which versions have the most data.
    """
    # Check project access
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Verify user has permission
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_VIEW, db
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this project",
        )

    # Query generation counts grouped by version
    from sqlalchemy import func

    results = (
        await db.execute(
            select(DBGeneration.label_config_version, func.count(DBGeneration.id).label('count'))
            .where(DBGeneration.project_id == project_id)
            .where(DBGeneration.label_config_version.isnot(None))
            .group_by(DBGeneration.label_config_version)
        )
    ).all()

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
