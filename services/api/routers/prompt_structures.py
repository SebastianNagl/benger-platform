"""
Prompt Structures endpoints for Issue #762.
Provides CRUD operations for managing multiple prompt structures per project.
"""

import logging
import re
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Permission, auth_service
from auth_module import User, require_user
from database import get_async_db
from project_models import Project
from project_schemas import PromptStructureCreate, PromptStructureResponse
from routers.projects.helpers import get_org_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/generation-config/structures",
    tags=["prompt-structures"],
)

# Valid key pattern: alphanumeric, underscore, hyphen
KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_structure_key(key: str) -> None:
    """Validate that structure key meets requirements"""
    if not key or len(key) < 1 or len(key) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Structure key must be 1-50 characters long",
        )
    if not KEY_PATTERN.match(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Structure key can only contain alphanumeric characters, underscores, and hyphens",
        )


async def get_project_or_403(
    project_id: str, current_user: User, db: AsyncSession, org_context: Optional[str] = None
) -> Project:
    """Get project and verify user has edit permissions"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Check edit permissions
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_EDIT, db, org_context=org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this project",
        )

    return project


def _normalize_prompt_structures(value) -> Dict[str, dict]:
    """Coerce legacy/imported prompt_structures values into the dict shape.

    Old exports stored a list of structure objects; anything non-dict-shaped
    would previously crash every reader with AttributeError (issue #292).
    List entries are keyed by their "key"/"name" field (position as fallback);
    non-dict entries are dropped.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        if value is not None:
            logger.warning(
                "Discarding prompt_structures of unexpected type %s", type(value).__name__
            )
        return {}
    normalized: Dict[str, dict] = {}
    for i, entry in enumerate(value):
        if not isinstance(entry, dict):
            logger.warning("Dropping non-dict prompt structure entry at index %d", i)
            continue
        key = str(entry.get("key") or entry.get("name") or i)
        normalized[key] = {k: v for k, v in entry.items() if k != "key"}
    return normalized


def ensure_generation_config_structure(project: Project) -> None:
    """Ensure generation_config has the correct structure"""
    if project.generation_config == None:  # noqa: E711
        project.generation_config = {}

    if "selected_configuration" not in project.generation_config:
        project.generation_config["selected_configuration"] = {
            "models": [],
            "active_structures": [],
        }

    structures = project.generation_config.get("prompt_structures")
    if not isinstance(structures, dict):
        project.generation_config["prompt_structures"] = _normalize_prompt_structures(structures)


@router.put("/{key}", response_model=PromptStructureResponse)
async def create_or_update_structure(
    project_id: str,
    key: str,
    structure: PromptStructureCreate,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create or update a prompt structure for a project.

    - **key**: Unique identifier for this structure (alphanumeric, underscore, hyphen)
    - **structure**: Prompt structure definition
    """
    validate_structure_key(key)
    org_context = get_org_context_from_request(request)
    project = await get_project_or_403(project_id, current_user, db, org_context=org_context)
    ensure_generation_config_structure(project)

    # Add or update the structure
    project.generation_config["prompt_structures"][key] = structure.model_dump()

    # Mark as modified for SQLAlchemy
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(project, "generation_config")

    await db.commit()
    await db.refresh(project)

    logger.info(
        f"User {current_user.id} created/updated prompt structure '{key}' "
        f"for project {project_id}"
    )

    # Return the structure with key included
    response_data = structure.model_dump()
    response_data["key"] = key
    return PromptStructureResponse(**response_data)


@router.delete("/{key}")
async def delete_structure(
    project_id: str,
    key: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Delete a prompt structure from a project.

    - **key**: Structure key to delete
    """
    validate_structure_key(key)
    org_context = get_org_context_from_request(request)
    project = await get_project_or_403(project_id, current_user, db, org_context=org_context)
    ensure_generation_config_structure(project)

    # Check if structure exists
    if key not in project.generation_config.get("prompt_structures", {}):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt structure '{key}' not found",
        )

    # Remove from structures
    del project.generation_config["prompt_structures"][key]

    # Remove from active_structures if present
    active_structures = project.generation_config.get("selected_configuration", {}).get(
        "active_structures", []
    )
    if key in active_structures:
        active_structures.remove(key)
        project.generation_config["selected_configuration"]["active_structures"] = active_structures

    # Mark as modified
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(project, "generation_config")

    await db.commit()

    logger.info(
        f"User {current_user.id} deleted prompt structure '{key}' from project {project_id}"
    )

    return {"message": f"Prompt structure '{key}' deleted successfully"}


@router.put("", status_code=status.HTTP_200_OK)
async def set_active_structures(
    project_id: str,
    structure_keys: List[str],
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Set the list of active prompt structures for a project.

    - **structure_keys**: List of structure keys to set as active
    """
    org_context = get_org_context_from_request(request)
    project = await get_project_or_403(project_id, current_user, db, org_context=org_context)
    ensure_generation_config_structure(project)

    # Validate all keys exist
    available_structures = project.generation_config.get("prompt_structures", {})
    for key in structure_keys:
        validate_structure_key(key)
        if key not in available_structures:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prompt structure '{key}' does not exist in project",
            )

    # Update active structures
    project.generation_config["selected_configuration"]["active_structures"] = structure_keys

    # Mark as modified
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(project, "generation_config")

    await db.commit()

    logger.info(
        f"User {current_user.id} set active structures for project {project_id}: {structure_keys}"
    )

    return {
        "message": "Active structures updated successfully",
        "active_structures": structure_keys,
    }


@router.get("", response_model=Dict[str, PromptStructureResponse])
async def list_structures(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List all prompt structures for a project.

    Returns a dictionary mapping structure keys to their definitions.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Check read permissions (can view if can access project)
    org_context = get_org_context_from_request(request)
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this project",
        )

    ensure_generation_config_structure(project)

    # Get all structures
    structures = project.generation_config.get("prompt_structures", {})

    # Convert to response format with keys included
    response = {}
    for key, structure_data in structures.items():
        if not isinstance(structure_data, dict):
            logger.warning(
                "Skipping non-dict prompt structure '%s' in project %s", key, project_id
            )
            continue
        try:
            # Create a copy to avoid mutating the database object
            response[key] = PromptStructureResponse(**{**structure_data, "key": key})
        except ValidationError:
            # Legacy/imported entries may predate the schema — a broken entry
            # must not take down the whole listing (issue #292)
            logger.warning(
                "Skipping prompt structure '%s' in project %s: does not match schema",
                key,
                project_id,
            )

    return response


@router.get("/{key}", response_model=PromptStructureResponse)
async def get_structure(
    project_id: str,
    key: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get a specific prompt structure by key.

    - **key**: Structure key to retrieve
    """
    validate_structure_key(key)

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Check read permissions
    org_context = get_org_context_from_request(request)
    if not await auth_service.check_project_access_async(
        current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this project",
        )

    ensure_generation_config_structure(project)

    # Get structure
    structure_data = project.generation_config.get("prompt_structures", {}).get(key)

    if not isinstance(structure_data, dict) or not structure_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt structure '{key}' not found",
        )

    try:
        # Create a copy to avoid mutating the database object
        return PromptStructureResponse(**{**structure_data, "key": key})
    except ValidationError:
        # Malformed legacy entry — invisible in the listing, so absent here too
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt structure '{key}' not found",
        )
