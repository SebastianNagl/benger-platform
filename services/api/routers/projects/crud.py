"""Project CRUD operations."""

import logging
import math
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified

from auth_module import require_user
from auth_module.dependencies import get_current_user
from auth_module.models import User as AuthUser
from database import SessionLocal, get_async_db
from services.label_config.validator import LabelConfigValidator
from services.label_config.version_service import LabelConfigVersionService
from models import Organization, User
from notification_service import notify_project_created, notify_project_deleted
from project_models import Project, ProjectMember, ProjectOrganization, Task
from project_schemas import PaginatedResponse, ProjectCreate, ProjectResponse, ProjectUpdate
from routers.projects.deps import ProjectAccess, require_project_access
from routers.projects.helpers import (
    apply_generation_stats,
    apply_mixed_progress,
    calculate_generation_stats_async,
    calculate_generation_stats_batch,
    calculate_project_stats_async,
    calculate_project_stats_batch,
    check_project_accessible_async,
    check_user_can_edit_project_async,
    get_accessible_project_ids_async,
    get_org_context_from_request,
    get_org_membership_role_async,
    get_user_with_memberships_async,
)

logger = logging.getLogger(__name__)


def _notify_project_created_sync(**kwargs) -> None:
    """Run the sync ``notify_project_created`` on a fresh short-lived sync
    session so the async handler never passes its ``AsyncSession`` into the
    sync notification path (which queries + commits on ``db``)."""
    sync_db = SessionLocal()
    try:
        notify_project_created(db=sync_db, **kwargs)
    finally:
        sync_db.close()


def _notify_project_deleted_sync(**kwargs) -> None:
    """Run the sync ``notify_project_deleted`` on a fresh short-lived sync
    session (see :func:`_notify_project_created_sync`)."""
    sync_db = SessionLocal()
    try:
        notify_project_deleted(db=sync_db, **kwargs)
    finally:
        sync_db.close()


def _create_initial_report_draft_sync(project_id: str, user_id: str) -> None:
    """Run the sync ``create_initial_report_draft`` on a fresh short-lived sync
    session (the report service is sync-only and lives in /shared)."""
    from report_service import create_initial_report_draft

    sync_db = SessionLocal()
    try:
        create_initial_report_draft(sync_db, project_id, user_id)
    finally:
        sync_db.close()


def _calculate_project_stats_batch_sync(project_ids):
    """Run the sync batch stats helper on a fresh short-lived sync session.

    ``calculate_project_stats_batch`` reads from ``project_summaries`` (with a
    live fallback) and has no async twin — it stays sync and runs off the event
    loop via ``run_in_threadpool``. Only primitive ids cross the boundary.
    """
    sync_db = SessionLocal()
    try:
        return calculate_project_stats_batch(sync_db, project_ids)
    finally:
        sync_db.close()


def _calculate_generation_stats_batch_sync(projects):
    """Run the sync batch generation-stats helper on a fresh sync session.

    The helper only reads each project's ``id`` (already loaded on the
    async-fetched objects) to scope its own ``project_summaries`` query, so
    handing it the async-loaded Project objects is safe — no relationship is
    lazily traversed inside the sync session.
    """
    sync_db = SessionLocal()
    try:
        return calculate_generation_stats_batch(sync_db, projects)
    finally:
        sync_db.close()


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
    kind: Optional[str] = Query(
        None,
        description=(
            'Filter by project kind, e.g. "exam" or "flashcard_deck" (extended '
            "student experience). Omit to include every kind."
        ),
    ),
    origin: Optional[str] = Query(
        None,
        description=(
            'Filter by project origin, e.g. "student". Omit to include every '
            "origin (the expert view stays able to surface student datasets)."
        ),
    ),
    include_all_private: bool = Query(
        False,
        description=(
            "Superadmin-only: include other users' private projects in the "
            "response. Defaults to False so a superadmin's projects browser "
            "behaves like a regular user's (own private + public + org-scoped). "
            "Ignored for non-superadmins."
        ),
    ),
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List projects based on organization context.

    The X-Organization-Context header determines which projects are shown:
    - "private" or absent: Show only private projects created by the user
    - org ID: Show only projects assigned to that organization

    Superadmins are scoped the same way by default; pass
    include_all_private=true to surface every project in the system.
    """

    try:
        # Read organization context from header
        org_context = request.headers.get("X-Organization-Context")

        # Use shared helper for consistent org-context filtering
        accessible_ids = await get_accessible_project_ids_async(
            db, current_user, org_context, include_all_private=include_all_private
        )

        # Eager-load every relationship the response reads (creator + the two
        # organization paths) so the async engine never lazy-loads during
        # from_orm serialization (MissingGreenlet). The two collection loads
        # require .unique() before .scalars().all().
        base_filters = []
        if accessible_ids is not None:
            base_filters.append(Project.id.in_(accessible_ids))
        if search:
            base_filters.append(
                Project.title.ilike(f"%{search}%") | Project.description.ilike(f"%{search}%")
            )

        # Archive filter runs in SQL (the column exists and is indexed) so it
        # is applied before LIMIT/OFFSET — pagination counts stay correct and no
        # archived row ever reaches the response (the old post-pagination Python
        # filter both broke the totals and let archived rows leak on page
        # boundaries / when the param was dropped by a caller).
        if is_archived is not None:
            base_filters.append(Project.is_archived.is_(is_archived))

        # Student-experience tag filters (extended). Plain equality on the
        # indexed columns; both default to None so existing callers are
        # unaffected and the expert/benchmark view can still list everything.
        if kind is not None:
            base_filters.append(Project.kind == kind)
        if origin is not None:
            base_filters.append(Project.origin == origin)

        # Annotators never see archived projects in an org context: mirror the
        # annotator block in check_project_accessible_async so this list endpoint
        # can't surface archived rows the detail endpoint would refuse. The
        # project creator keeps their own archived projects (a creator resolves
        # to ORG_ADMIN in the role model, so the block doesn't apply to them).
        if not current_user.is_superadmin and org_context and org_context != "private":
            membership_role = await get_org_membership_role_async(
                db, current_user, org_context
            )
            if membership_role == "ANNOTATOR":
                base_filters.append(
                    or_(
                        Project.is_archived.is_(False),
                        Project.created_by == str(current_user.id),
                    )
                )

        # Pagination
        count_stmt = select(func.count()).select_from(Project)
        for f in base_filters:
            count_stmt = count_stmt.where(f)
        total_count = (await db.execute(count_stmt)).scalar() or 0

        list_stmt = (
            select(Project)
            .options(
                joinedload(Project.creator),
                selectinload(Project.organizations),  # Load organizations directly
                selectinload(Project.project_organizations).joinedload(
                    ProjectOrganization.organization
                ),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        for f in base_filters:
            list_stmt = list_stmt.where(f)
        projects = (await db.execute(list_stmt)).scalars().unique().all()

        # Build enriched responses

        # Batch fetch statistics for all projects (avoids N+1 query problem)
        project_ids = [project.id for project in projects]
        stats_map = await run_in_threadpool(_calculate_project_stats_batch_sync, project_ids)
        gen_stats_map = await run_in_threadpool(
            _calculate_generation_stats_batch_sync, projects
        )

        enriched_projects = []
        for project in projects:
            response = ProjectResponse.from_orm(project)
            response.created_by_name = project.creator.name if project.creator else None

            # Apply pre-fetched statistics
            stats = stats_map.get(
                project.id,
                {
                    'task_count': 0,
                    'completed_tasks_count': 0,
                    'annotation_count': 0,
                    'evaluation_count': 0,
                    'evaluations_completed_count': 0,
                },
            )
            response.task_count = stats['task_count']
            response.completed_tasks_count = stats['completed_tasks_count']
            response.annotation_count = stats['annotation_count']
            response.evaluation_count = stats['evaluation_count']
            response.evaluations_completed_count = stats['evaluations_completed_count']
            # Mirror to legacy aliases (see calculate_project_stats note).
            response.num_tasks = response.task_count
            response.num_annotations = response.annotation_count

            # Apply pre-fetched generation statistics (no DB query per project)
            gen_stats = gen_stats_map.get(
                project.id, {"generation_count": 0, "completed_generations": 0}
            )
            apply_generation_stats(project, response, gen_stats)

            # Progress: weighted mix across enabled stages. Uses the
            # already-fetched generation completion count to stay query-free.
            apply_mixed_progress(project, response, gen_stats.get("completed_generations", 0))

            # Note: organizations are already handled in from_orm method
            # Don't need to set them again here

            # Note: organization and organization_id fields removed from schema
            # These were legacy fields that no longer exist in ProjectResponse

            enriched_projects.append(response)

        # is_archived (and the annotator carve-out) are applied in SQL above, so
        # total_count already reflects the filtered set — no post-pagination
        # filtering needed.
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

        return PaginatedResponse(
            items=enriched_projects,
            total=total_count,
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
    db: AsyncSession = Depends(get_async_db),
):
    """Create a new project.

    When X-Organization-Context is "private" or absent, creates a private project.
    When X-Organization-Context is an org ID, creates an org-assigned project.
    When payload.is_public=True, creates a public project (visible to all
    authenticated users); public_role defaults to ANNOTATOR if omitted.
    """

    # Generate unique ID
    project_id = str(uuid.uuid4())

    # Read organization context from header
    org_context = request.headers.get("X-Organization-Context")

    is_public = bool(project.is_public)
    if is_public and project.is_private:
        raise HTTPException(
            status_code=400, detail="A project cannot be both private and public"
        )
    public_role = project.public_role if is_public else None
    if is_public and public_role not in ("ANNOTATOR", "CONTRIBUTOR"):
        public_role = "ANNOTATOR"

    is_private = (
        not is_public
        and (not org_context or org_context == "private" or project.is_private)
    )

    primary_membership = None

    if not is_private and not is_public:
        # Organization mode: validate org membership and role
        user_with_memberships = await get_user_with_memberships_async(db, current_user.id)
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
    if project.label_config != None:  # noqa: E711
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
        is_public=is_public,
        public_role=public_role,
        # Write-once student-experience tags (extended). Plain string passthrough
        # — there is no ProjectUpdate counterpart, so these can only ever be set
        # here at creation.
        kind=project.kind,
        origin=project.origin,
    )

    db.add(db_project)

    # Create organization assignment only for org-scoped projects
    if not is_private and not is_public:
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

    await db.commit()
    await db.refresh(db_project)

    # Auto-create report draft for progressive building (Issue #770). The
    # report service is sync-only (lives in /shared); run it on a short-lived
    # sync session off the event loop so it never touches the AsyncSession.
    try:
        await run_in_threadpool(
            _create_initial_report_draft_sync, project_id, current_user.id
        )
    except Exception as e:
        logger.error(f"Failed to create initial report draft: {e}")

    # Load relationships for enriched response. from_orm reads project.creator
    # and project.organizations, so eager-load both (plus project_organizations
    # → organization, preserving the original sync options).
    result = await db.execute(
        select(Project)
        .options(
            joinedload(Project.creator),
            selectinload(Project.organizations),
            selectinload(Project.project_organizations).joinedload(
                ProjectOrganization.organization
            ),
        )
        .where(Project.id == project_id)
    )
    db_project = result.scalars().unique().one_or_none()

    # Send notification about project creation (only for org projects). The
    # notification path is sync-only (queries + commits); run it on a fresh
    # sync session off the event loop. Failures are swallowed by design.
    if not is_private and not is_public and primary_membership:
        try:
            await run_in_threadpool(
                _notify_project_created_sync,
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

    if not is_private and not is_public and primary_membership:
        # primary_membership.organization is NOT eager-loaded on the async
        # memberships fetch, so resolve the org name by id to avoid a
        # MissingGreenlet lazy load.
        org_row = (
            await db.execute(
                select(Organization.name).where(
                    Organization.id == primary_membership.organization_id
                )
            )
        ).scalar_one_or_none()
        org_name = org_row or "Unknown"
        response.organizations = [{"id": primary_membership.organization_id, "name": org_name}]
    else:
        response.organizations = []

    return response


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get project details

    Returns enriched project data including:
    - created_by_name: The name of the user who created the project
    - organization: Object with organization id and name
    """

    result = await db.execute(
        select(Project)
        .options(
            joinedload(Project.creator),
            selectinload(Project.organizations),  # Load organizations directly
            selectinload(Project.project_organizations).joinedload(
                ProjectOrganization.organization
            ),
        )
        .where(Project.id == project_id)
    )
    project = result.scalars().unique().one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check access using shared helper. Pass the already-loaded project so the
    # async helper doesn't re-query it.
    org_context = get_org_context_from_request(request)
    if not await check_project_accessible_async(
        db, current_user, project_id, org_context, project=project
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    # Build response with enriched fields
    response = ProjectResponse.from_orm(project)
    response.created_by_name = project.creator.name if project.creator else None

    # Calculate statistics
    await calculate_project_stats_async(db, project.id, response, project=project)
    await calculate_generation_stats_async(db, project, response)

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
    db: AsyncSession = Depends(get_async_db),
):
    """Update project configuration"""

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check permission - project creator, superadmin, org admin, or contributor
    if not await check_user_can_edit_project_async(db, current_user, project_id):
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

    await db.commit()

    # Note: Progress is recalculated automatically when fetching the project
    # via the schema's from_orm method

    await db.refresh(project)

    # Reload with relationships for enriched response. from_orm reads
    # project.creator and project.organizations, so eager-load both (plus the
    # project_organizations → organization chain from the original options).
    result = await db.execute(
        select(Project)
        .options(
            joinedload(Project.creator),
            selectinload(Project.organizations),
            selectinload(Project.project_organizations).joinedload(
                ProjectOrganization.organization
            ),
        )
        .where(Project.id == project_id)
    )
    project = result.scalars().unique().one_or_none()

    # Build response with enriched fields
    response = ProjectResponse.from_orm(project)
    response.created_by_name = project.creator.name if project.creator else None

    # Calculate statistics including generation_models_count
    await calculate_project_stats_async(db, project.id, response, project=project)
    await calculate_generation_stats_async(db, project, response)

    # Note: organizations are already handled in from_orm method
    # Don't need to set them again here

    # Note: organization and organization_id fields removed from schema
    # These were legacy fields that no longer exist in ProjectResponse

    return response


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a project and all its associated data"""

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
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

    # Capture the title before deletion (used in the notification below; reading
    # it after the row is deleted/expired would re-trigger a load).
    project_title = project.title

    # Read the first org assignment for the notification BEFORE deleting the
    # ProjectOrganization rows.
    first_org_id = (
        await db.execute(
            select(ProjectOrganization.organization_id)
            .where(ProjectOrganization.project_id == project_id)
            .limit(1)
        )
    ).scalar_one_or_none()

    # Delete all associated data to avoid foreign key constraint violations.

    # Delete project organizations
    await db.execute(
        ProjectOrganization.__table__.delete().where(
            ProjectOrganization.project_id == project_id
        )
    )

    # Delete project members
    await db.execute(
        ProjectMember.__table__.delete().where(ProjectMember.project_id == project_id)
    )

    # Annotations (annotations table) are removed automatically by the DB: their
    # task_id and project_id FKs both carry ON DELETE CASCADE (migration
    # 001_complete_baseline), so the tasks DELETE below and the project delete
    # cascade to annotations. No explicit annotation delete is needed.

    # Delete tasks
    await db.execute(Task.__table__.delete().where(Task.project_id == project_id))

    # Delete the project
    await db.delete(project)
    await db.commit()

    # Send notification (sync-only path; run on a short-lived sync session off
    # the event loop). Failures must not fail the deletion.
    try:
        await run_in_threadpool(
            _notify_project_deleted_sync,
            project_id=project_id,
            project_title=project_title,
            deleted_by_user_id=current_user.id,
            deleted_by_username=current_user.name,
            organization_id=first_org_id,
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
    db: AsyncSession = Depends(get_async_db),
):
    """Change project visibility (creator or superadmin).

    Request body shapes:
    - Make private: {"is_private": true, "owner_user_id": "user-uuid"}
    - Make org-assigned: {"is_private": false, "organization_ids": ["org1", "org2"]}
    - Make public: {"is_public": true, "public_role": "ANNOTATOR" | "CONTRIBUTOR"}
    - Flip public_role on already-public project: {"public_role": "CONTRIBUTOR"}
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not current_user.is_superadmin and str(project.created_by) != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="Only the project creator or a superadmin can change project visibility",
        )

    make_private = visibility.get("is_private", False)
    make_public = visibility.get("is_public", False)

    if make_private and make_public:
        raise HTTPException(
            status_code=400, detail="A project cannot be both private and public"
        )

    # Standalone public_role flip on an already-public project
    if (
        not make_private
        and not make_public
        and "public_role" in visibility
        and "is_private" not in visibility
        and "is_public" not in visibility
        and "organization_ids" not in visibility
    ):
        if not project.is_public:
            raise HTTPException(
                status_code=400,
                detail="public_role can only be set on a public project",
            )
        new_role = visibility.get("public_role")
        if new_role not in ("ANNOTATOR", "CONTRIBUTOR"):
            raise HTTPException(
                status_code=400,
                detail="public_role must be 'ANNOTATOR' or 'CONTRIBUTOR'",
            )
        project.public_role = new_role

    elif make_public:
        public_role = visibility.get("public_role", "ANNOTATOR")
        if public_role not in ("ANNOTATOR", "CONTRIBUTOR"):
            raise HTTPException(
                status_code=400,
                detail="public_role must be 'ANNOTATOR' or 'CONTRIBUTOR'",
            )
        # Remove all org assignments
        await db.execute(
            ProjectOrganization.__table__.delete().where(
                ProjectOrganization.project_id == project_id
            )
        )
        project.is_private = False
        project.is_public = True
        project.public_role = public_role

    elif make_private:
        # Make project private
        owner_user_id = visibility.get("owner_user_id")
        if owner_user_id:
            # Verify user exists
            owner = (
                await db.execute(select(User).where(User.id == owner_user_id))
            ).scalar_one_or_none()
            if not owner:
                raise HTTPException(status_code=404, detail="Owner user not found")
            project.created_by = owner_user_id

        # Remove all org assignments
        await db.execute(
            ProjectOrganization.__table__.delete().where(
                ProjectOrganization.project_id == project_id
            )
        )

        project.is_private = True
        project.is_public = False
        project.public_role = None

    else:
        # Make project org-assigned
        organization_ids = visibility.get("organization_ids", [])
        if not organization_ids:
            raise HTTPException(
                status_code=400,
                detail="At least one organization_id is required for non-private projects",
            )

        # Verify all orgs exist
        for org_id in organization_ids:
            org = (
                await db.execute(select(Organization).where(Organization.id == org_id))
            ).scalar_one_or_none()
            if not org:
                raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")

        # Remove existing org assignments
        await db.execute(
            ProjectOrganization.__table__.delete().where(
                ProjectOrganization.project_id == project_id
            )
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
        project.is_public = False
        project.public_role = None

    await db.commit()
    await db.refresh(project)

    # Load relationships for response. from_orm reads project.creator and
    # project.organizations, so eager-load both (plus project_organizations →
    # organization from the original options).
    result = await db.execute(
        select(Project)
        .options(
            joinedload(Project.creator),
            selectinload(Project.organizations),
            selectinload(Project.project_organizations).joinedload(
                ProjectOrganization.organization
            ),
        )
        .where(Project.id == project_id)
    )
    project = result.scalars().unique().one_or_none()

    response = ProjectResponse.from_orm(project)
    response.created_by_name = project.creator.name if project.creator else None
    await calculate_project_stats_async(db, project.id, response, project=project)
    await calculate_generation_stats_async(db, project, response)

    return response


@router.post("/{project_id}/recalculate-stats")
async def recalculate_project_statistics(
    project_id: str,
    db: AsyncSession = Depends(get_async_db),
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

    # Check if project exists. from_orm reads project.organizations, so
    # eager-load it to avoid a lazy load under the async engine.
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.organizations))
        .where(Project.id == project_id)
    )
    project = result.scalars().unique().one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create a temporary response object to hold the stats
    from project_schemas import ProjectResponse

    temp_response = ProjectResponse.from_orm(project)

    # Calculate statistics using our helper function
    await calculate_project_stats_async(db, project_id, temp_response, project=project)

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
    current_user: AuthUser = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
    _access: ProjectAccess = Depends(require_project_access()),
):
    """
    Get task completion statistics for a project.

    Returns:
        - completed: Number of labeled/completed tasks
        - total: Total number of tasks
        - completion_rate: Percentage of tasks completed (0-100)
    """
    # Project existence + read access are enforced by require_project_access
    # (404 "Project not found" / 403 "Access denied"), identical to the inline
    # preamble this replaced. The loaded project is unused below.

    # Get task counts
    total_tasks = (
        await db.execute(
            select(func.count()).select_from(Task).where(Task.project_id == project_id)
        )
    ).scalar() or 0
    completed_tasks = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(Task.project_id == project_id, Task.is_labeled == True)  # noqa: E712
        )
    ).scalar() or 0

    # Calculate completion rate
    completion_rate = 0.0
    if total_tasks > 0:
        completion_rate = min(100.0, (completed_tasks / total_tasks) * 100)

    return {
        "completed": completed_tasks,
        "total": total_tasks,
        "completion_rate": completion_rate,
    }
