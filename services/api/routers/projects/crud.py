"""Project CRUD operations."""

import logging
import math
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from auth_module import require_user
from auth_module.dependencies import get_current_user
from auth_module.models import User as AuthUser
from database import get_db
from label_config_validator import LabelConfigValidator
from label_config_version_service import LabelConfigVersionService
from models import User
from notification_service import notify_project_created, notify_project_deleted
from project_models import Project, ProjectOrganization, Task
from project_schemas import PaginatedResponse, ProjectCreate, ProjectResponse, ProjectUpdate
from routers.projects.helpers import (
    calculate_generation_stats,
    calculate_project_stats,
    calculate_project_stats_batch,
    check_project_accessible,
    check_user_can_edit_project,
    get_accessible_project_ids,
    get_org_context_from_request,
    get_user_with_memberships,
)

logger = logging.getLogger(__name__)


def deep_merge_dicts(
    base: Optional[Dict[str, Any]], update: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Deep merge two dictionaries, preserving nested structures.

    Issue #818: Prevent generation_config updates from overwriting unrelated fields

    Merging rules:
    - Nested dicts are merged recursively
    - Lists are replaced (not concatenated)
    - None values in update remove the key from base
    - If base or update is None/empty, handles gracefully
    """
    # Handle None/empty cases
    if base is None or base == {}:
        return update.copy() if update else {}
    if update is None or update == {}:
        return base.copy()

    # Create a copy to avoid modifying the input
    result = base.copy()

    for key, value in update.items():
        if value is None:
            # None values remove the key
            result.pop(key, None)
        elif key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dicts
            result[key] = deep_merge_dicts(result[key], value)
        else:
            # Replace value (includes primitives, lists, and new keys)
            result[key] = value

    return result


# XSS Prevention (Issue #798):
# - label_config is validated at input (label_config_validator.py)
# - Field metadata is sanitized at output (label_config_parser.py + label_config_sanitizer.py)
# - See tests: test_label_config_sanitizer.py, test_label_config_parser_sanitization.py

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),  # Default 100 like Label Studio
    search: Optional[str] = None,
    is_archived: Optional[bool] = None,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    List projects based on organization context.

    The X-Organization-Context header determines which projects are shown:
    - "private" or absent: Show only private projects created by the user
    - org ID: Show only projects assigned to that organization
    - Superadmins always see all projects regardless of context
    """

    try:
        # Read organization context from header
        org_context = request.headers.get("X-Organization-Context")

        # Use shared helper for consistent org-context filtering
        accessible_ids = get_accessible_project_ids(db, current_user, org_context)

        query = db.query(Project)
        if accessible_ids is not None:
            query = query.filter(Project.id.in_(accessible_ids))

        # Apply filters
        if search:
            query = query.filter(
                Project.title.ilike(f"%{search}%") | Project.description.ilike(f"%{search}%")
            )

        # Note: is_archived is a virtual field, handled at response level
        # Removed database filtering since column doesn't exist

        # Pagination
        total_count = query.count()
        projects = (
            query.options(
                joinedload(Project.creator),
                joinedload(Project.organizations),  # Load organizations directly
                joinedload(Project.project_organizations).joinedload(
                    ProjectOrganization.organization
                ),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # Build enriched responses

        # Batch fetch statistics for all projects (avoids N+1 query problem)
        project_ids = [project.id for project in projects]
        stats_map = calculate_project_stats_batch(db, project_ids)

        enriched_projects = []
        for project in projects:
            response = ProjectResponse.from_orm(project)
            response.created_by_name = project.creator.name if project.creator else None

            # Apply pre-fetched statistics
            stats = stats_map.get(
                project.id, {'task_count': 0, 'completed_tasks_count': 0, 'annotation_count': 0}
            )
            response.task_count = stats['task_count']
            response.completed_tasks_count = stats['completed_tasks_count']
            response.annotation_count = stats['annotation_count']

            # Calculate progress based on Label Studio approach
            if response.task_count > 0:
                response.progress_percentage = min(
                    100.0, (response.completed_tasks_count / response.task_count) * 100
                )
            else:
                response.progress_percentage = 0.0

            # Calculate generation-related statistics
            calculate_generation_stats(db, project, response)

            # Note: organizations are already handled in from_orm method
            # Don't need to set them again here

            # Note: organization and organization_id fields removed from schema
            # These were legacy fields that no longer exist in ProjectResponse

            enriched_projects.append(response)

        # Filter by is_archived if specified
        if is_archived is not None:
            enriched_projects = [p for p in enriched_projects if p.is_archived == is_archived]
            filtered_total = len(enriched_projects)
        else:
            filtered_total = total_count

        total_pages = math.ceil(filtered_total / page_size) if filtered_total > 0 else 0

        return PaginatedResponse(
            items=enriched_projects,
            total=filtered_total,
            page=page,
            page_size=page_size,
            pages=total_pages,
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        logger.error(f"Error fetching projects for user {current_user.id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch projects. Please contact support if the issue persists.",
        )


@router.post("/", response_model=ProjectResponse)
async def create_project(
    project: ProjectCreate,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create a new project.

    When X-Organization-Context is "private" or absent, creates a private project.
    When X-Organization-Context is an org ID, creates an org-assigned project.
    """

    # Generate unique ID
    project_id = str(uuid.uuid4())

    # Read organization context from header
    org_context = request.headers.get("X-Organization-Context")
    is_private = not org_context or org_context == "private" or project.is_private

    primary_membership = None

    if not is_private:
        # Organization mode: validate org membership and role
        user_with_memberships = get_user_with_memberships(db, current_user.id)
        if not user_with_memberships or not user_with_memberships.organization_memberships:
            raise HTTPException(status_code=400, detail="User must belong to an organization")

        # Find membership for the specified org
        primary_membership = next(
            (
                m
                for m in user_with_memberships.organization_memberships
                if m.is_active and m.organization_id == org_context
            ),
            None,
        )
        if not primary_membership and not current_user.is_superadmin:
            # Fallback to first active membership
            primary_membership = next(
                (m for m in user_with_memberships.organization_memberships if m.is_active), None
            )
        if not primary_membership and not current_user.is_superadmin:
            raise HTTPException(
                status_code=400, detail="User must have an active organization membership"
            )

        # Check if user has permission to create projects
        if not current_user.is_superadmin and primary_membership:
            if primary_membership.role not in ["ORG_ADMIN", "CONTRIBUTOR"]:
                raise HTTPException(
                    status_code=403,
                    detail=f"User with role {primary_membership.role} is not authorized to create projects. Only ORG_ADMIN and CONTRIBUTOR roles can create projects.",
                )

    # Validate label_config if provided (including empty strings)
    if project.label_config is not None:
        is_valid, errors = LabelConfigValidator.validate(project.label_config)
        if not is_valid:
            raise HTTPException(
                status_code=422, detail={"message": "Invalid label configuration", "errors": errors}
            )

    db_project = Project(
        id=project_id,
        title=project.title,
        description=project.description,
        created_by=current_user.id,
        label_config=project.label_config,
        expert_instruction=project.expert_instruction,
        show_instruction=project.show_instruction,
        show_skip_button=project.show_skip_button,
        enable_empty_annotation=project.enable_empty_annotation,
        is_private=is_private,
    )

    db.add(db_project)

    # Create organization assignment only for non-private projects
    if not is_private:
        target_org_id = (
            org_context
            if org_context and org_context != "private"
            else (primary_membership.organization_id if primary_membership else None)
        )
        if target_org_id:
            project_org = ProjectOrganization(
                id=str(uuid.uuid4()),
                project_id=project_id,
                organization_id=target_org_id,
                assigned_by=current_user.id,
            )
            db.add(project_org)

    db.commit()
    db.refresh(db_project)

    # Auto-create report draft for progressive building (Issue #770)
    try:
        from report_service import create_initial_report_draft

        create_initial_report_draft(db, project_id, current_user.id)
    except Exception as e:
        logger.error(f"Failed to create initial report draft: {e}")

    # Load relationships for enriched response
    db_project = (
        db.query(Project)
        .options(
            joinedload(Project.creator),
            joinedload(Project.project_organizations).joinedload(ProjectOrganization.organization),
        )
        .filter(Project.id == project_id)
        .first()
    )

    # Send notification about project creation (only for org projects)
    if not is_private and primary_membership:
        try:
            notify_project_created(
                db=db,
                project_id=str(db_project.id),
                project_title=str(db_project.title),
                creator_name=str(current_user.name),
                organization_id=str(primary_membership.organization_id),
            )
        except Exception as e:
            import traceback

            logger.error(f"Failed to send project creation notification: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")

    # Build response with enriched fields
    response = ProjectResponse.from_orm(db_project)
    response.created_by_name = current_user.name

    if not is_private and primary_membership:
        org_name = (
            primary_membership.organization.name if primary_membership.organization else "Unknown"
        )
        response.organizations = [{"id": primary_membership.organization_id, "name": org_name}]
    else:
        response.organizations = []

    return response


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get project details

    Returns enriched project data including:
    - created_by_name: The name of the user who created the project
    - organization: Object with organization id and name
    """

    project = (
        db.query(Project)
        .options(
            joinedload(Project.creator),
            joinedload(Project.organizations),  # Load organizations directly
            joinedload(Project.project_organizations).joinedload(ProjectOrganization.organization),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access using shared helper
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Build response with enriched fields
    response = ProjectResponse.from_orm(project)
    response.created_by_name = project.creator.name if project.creator else None

    # Calculate statistics
    calculate_project_stats(db, project.id, response)
    calculate_generation_stats(db, project, response)

    # Note: organizations are already handled in from_orm method
    # Don't need to set them again here

    # Note: organization and organization_id fields removed from schema
    # These were legacy fields that no longer exist in ProjectResponse

    return response


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    update: ProjectUpdate,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Update project configuration"""

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check permission - project creator, superadmin, org admin, or contributor
    if not check_user_can_edit_project(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Update fields
    update_data = update.dict(exclude_unset=True)

    # Handle field mappings
    if "instructions" in update_data:
        # Map frontend 'instructions' to database 'expert_instruction'
        update_data["expert_instruction"] = update_data.pop("instructions")

    # Handle backward compatibility for llm_model_ids
    # If llm_model_ids is provided, also update generation_config for consistency
    if "llm_model_ids" in update_data:
        import logging

        logging.warning(
            f"Project {project_id}: llm_model_ids is deprecated. "
            "Automatically migrating to generation_config.selected_configuration.models"
        )

        # Get or create generation_config structure
        generation_config = project.generation_config or {}
        if "selected_configuration" not in generation_config:
            generation_config["selected_configuration"] = {}

        # Update models in generation_config
        generation_config["selected_configuration"]["models"] = update_data["llm_model_ids"]
        update_data["generation_config"] = generation_config

    # Check if min_annotations_per_task is being updated
    "min_annotations_per_task" in update_data

    # Handle label_config versioning
    if "label_config" in update_data:
        new_schema = update_data["label_config"]

        # Validate new schema before updating
        if new_schema:
            is_valid, errors = LabelConfigValidator.validate(new_schema)
            if not is_valid:
                raise HTTPException(
                    status_code=422,
                    detail={"message": "Invalid label configuration", "errors": errors},
                )

        # Check if schema actually changed
        if LabelConfigVersionService.has_schema_changed(project, new_schema):
            import logging

            old_version = project.label_config_version or "v1"

            # Update version and store history
            new_version = LabelConfigVersionService.update_version_history(
                project=project,
                new_label_config=new_schema,
                description=update_data.get("version_description", "Schema updated via API"),
                user_id=current_user.id,
            )

            logging.info(
                f"Project {project_id}: Label config schema updated from {old_version} to {new_version}"
            )

            # Remove label_config from update_data since it was already set by update_version_history
            update_data.pop("label_config")
            # Remove version_description if present (not a model field)
            update_data.pop("version_description", None)

    for field, value in update_data.items():
        if hasattr(project, field):
            # Special handling for generation_config to preserve nested fields (Issue #818)
            # Deep merge prevents loss of data when updating models vs. prompt structures independently
            if field == "generation_config":
                current_config = project.generation_config or {}
                merged_config = deep_merge_dicts(current_config, value)
                setattr(project, field, merged_config)

                # Ensure SQLAlchemy tracks the JSONB field change
                flag_modified(project, "generation_config")
                logger.info(f"Project {project_id}: Deep merged generation_config update")
            elif field == "evaluation_config":
                current_config = project.evaluation_config or {}
                merged_config = deep_merge_dicts(current_config, value)
                setattr(project, field, merged_config)

                flag_modified(project, "evaluation_config")
                logger.info(f"Project {project_id}: Deep merged evaluation_config update")
            else:
                setattr(project, field, value)

    db.commit()

    # Note: Progress is recalculated automatically when fetching the project
    # via the schema's from_orm method

    db.refresh(project)

    # Reload with relationships for enriched response
    project = (
        db.query(Project)
        .options(
            joinedload(Project.creator),
            joinedload(Project.project_organizations).joinedload(ProjectOrganization.organization),
        )
        .filter(Project.id == project_id)
        .first()
    )

    # Build response with enriched fields
    response = ProjectResponse.from_orm(project)
    response.created_by_name = project.creator.name if project.creator else None

    # Calculate statistics including generation_models_count
    calculate_project_stats(db, project.id, response)
    calculate_generation_stats(db, project, response)

    # Note: organizations are already handled in from_orm method
    # Don't need to set them again here

    # Note: organization and organization_id fields removed from schema
    # These were legacy fields that no longer exist in ProjectResponse

    return response


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Delete a project and all its associated data"""

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check permission - superadmins can delete any project,
    # private project creators can delete their own
    if not current_user.is_superadmin:
        if not (project.is_private and str(project.created_by) == str(current_user.id)):
            raise HTTPException(
                status_code=403,
                detail="Only superadmins can delete projects (or creators of private projects)",
            )

    # Delete all associated data to avoid foreign key constraint violations
    from project_models import ProjectMember, ProjectOrganization

    # Delete project organizations
    db.query(ProjectOrganization).filter(ProjectOrganization.project_id == project_id).delete(
        synchronize_session=False
    )

    # Delete project members
    db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete(
        synchronize_session=False
    )

    # Delete annotations first (foreign key to tasks)
    # NOTE: Annotation table doesn't exist yet - commented out
    # db.query(Annotation).filter(Annotation.project_id == project_id).delete(
    #     synchronize_session=False
    # )

    # Delete tasks
    db.query(Task).filter(Task.project_id == project_id).delete(synchronize_session=False)

    # Delete the project
    db.delete(project)
    db.commit()

    # Send notification
    try:
        # Get first organization for notification (backward compatibility)
        project_orgs = (
            db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project_id)
            .first()
        )
        org_id = project_orgs.organization_id if project_orgs else None

        notify_project_deleted(
            db=db,
            project_id=project_id,
            project_title=project.title,
            deleted_by_user_id=current_user.id,
            deleted_by_username=current_user.name,
            organization_id=org_id,
        )
    except Exception as e:
        # Don't fail the deletion if notification fails
        print(f"Failed to send project deletion notification: {e}")

    return {"message": "Project deleted successfully"}


@router.patch("/{project_id}/visibility")
async def update_project_visibility(
    project_id: str,
    visibility: Dict[str, Any],
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Change project between private and org-assigned modes (superadmin only).

    Request body:
    - Make private: {"is_private": true, "owner_user_id": "user-uuid"}
    - Make org-assigned: {"is_private": false, "organization_ids": ["org1", "org2"]}
    """
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=403, detail="Only superadmins can change project visibility"
        )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    make_private = visibility.get("is_private", False)

    if make_private:
        # Make project private
        owner_user_id = visibility.get("owner_user_id")
        if owner_user_id:
            # Verify user exists
            owner = db.query(User).filter(User.id == owner_user_id).first()
            if not owner:
                raise HTTPException(status_code=404, detail="Owner user not found")
            project.created_by = owner_user_id

        # Remove all org assignments
        db.query(ProjectOrganization).filter(ProjectOrganization.project_id == project_id).delete(
            synchronize_session=False
        )

        project.is_private = True

    else:
        # Make project org-assigned
        organization_ids = visibility.get("organization_ids", [])
        if not organization_ids:
            raise HTTPException(
                status_code=400,
                detail="At least one organization_id is required for non-private projects",
            )

        # Verify all orgs exist
        from models import Organization

        for org_id in organization_ids:
            org = db.query(Organization).filter(Organization.id == org_id).first()
            if not org:
                raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")

        # Remove existing org assignments
        db.query(ProjectOrganization).filter(ProjectOrganization.project_id == project_id).delete(
            synchronize_session=False
        )

        # Create new org assignments
        for org_id in organization_ids:
            project_org = ProjectOrganization(
                id=str(uuid.uuid4()),
                project_id=project_id,
                organization_id=org_id,
                assigned_by=current_user.id,
            )
            db.add(project_org)

        project.is_private = False

    db.commit()
    db.refresh(project)

    # Load relationships for response
    project = (
        db.query(Project)
        .options(
            joinedload(Project.creator),
            joinedload(Project.project_organizations).joinedload(ProjectOrganization.organization),
        )
        .filter(Project.id == project_id)
        .first()
    )

    response = ProjectResponse.from_orm(project)
    response.created_by_name = project.creator.name if project.creator else None
    calculate_project_stats(db, project.id, response)
    calculate_generation_stats(db, project, response)

    return response


@router.post("/{project_id}/recalculate-stats")
def recalculate_project_statistics(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recalculate project statistics to fix annotation counts.
    This excludes cancelled/skipped annotations from the total count.

    Admin only endpoint.
    """
    # Check if user is admin
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can recalculate project statistics",
        )

    # Check if project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create a temporary response object to hold the stats
    from project_schemas import ProjectResponse

    temp_response = ProjectResponse.from_orm(project)

    # Calculate statistics using our helper function
    calculate_project_stats(db, project_id, temp_response)

    return {
        "message": "Project statistics recalculated successfully",
        "project_id": project_id,
        "task_count": temp_response.task_count,
        "annotation_count": temp_response.annotation_count,
        "completed_tasks_count": temp_response.completed_tasks_count,
        "progress_percentage": temp_response.progress_percentage,
    }


@router.get("/{project_id}/completion-stats")
async def get_project_completion_stats(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get task completion statistics for a project.

    Returns:
        - completed: Number of labeled/completed tasks
        - total: Total number of tasks
        - completion_rate: Percentage of tasks completed (0-100)
    """
    # Check if project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access using shared helper
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get task counts
    total_tasks = db.query(Task).filter(Task.project_id == project_id).count()
    completed_tasks = (
        db.query(Task).filter(Task.project_id == project_id, Task.is_labeled == True).count()
    )

    # Calculate completion rate
    completion_rate = 0.0
    if total_tasks > 0:
        completion_rate = min(100.0, (completed_tasks / total_tasks) * 100)

    return {
        "completed": completed_tasks,
        "total": total_tasks,
        "completion_rate": completion_rate,
    }
