"""
Report endpoints for progressive report building and publishing

Provides endpoints for:
- Creating and updating report drafts
- Publishing/unpublishing reports
- Listing published reports (filtered by organization)
- Retrieving report data and statistics
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from auth_module import User, require_user
from auth_module.dependencies import optional_user
from database import get_async_db
from models import OrganizationMembership
from org_groups import attachment_group_clause
from project_models import Project, ProjectOrganization
from report_models import ProjectReport
from report_service import (
    can_publish_report,
    create_or_update_report_from_existing_data,
    get_report_statistics_batch,
)
from report_snapshot import build_report_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["reports"])


# ============= Response Models =============


class ReportSection(BaseModel):
    """Model for a report section"""

    status: str  # "pending" | "completed"
    editable: bool = True
    visible: bool = True


class ProjectInfoSection(ReportSection):
    """Project information section"""

    title: str
    description: str
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None


class DataSection(ReportSection):
    """Data section"""

    task_count: Optional[int] = None
    custom_text: Optional[str] = None
    show_count: bool = True


class AnnotationsSection(ReportSection):
    """Annotations section"""

    annotation_count: Optional[int] = None
    participants: Optional[List[Dict[str, Any]]] = None
    custom_text: Optional[str] = None
    show_count: bool = True
    show_participants: bool = True
    acknowledgment_text: Optional[str] = None


class GenerationSection(ReportSection):
    """Generation section"""

    models: Optional[List[str]] = None
    custom_text: Optional[str] = None
    show_models: bool = True
    show_config: bool = False


class EvaluationSection(ReportSection):
    """Evaluation section"""

    methods: Optional[List[str]] = None
    metrics: Optional[Dict[str, Any]] = None
    charts_config: Optional[Dict[str, Any]] = None
    custom_interpretation: Optional[str] = None
    conclusions: Optional[str] = None


class ReportContent(BaseModel):
    """Complete report content structure"""

    sections: Dict[str, Any]
    metadata: Dict[str, Any]
    # Computed report numbers (see report_snapshot.build_report_snapshot);
    # written on publish/refresh, rendered verbatim by the viewer.
    snapshot: Optional[Dict[str, Any]] = None


class ReportResponse(BaseModel):
    """Response model for a report"""

    id: str
    project_id: str
    project_title: str
    content: ReportContent
    is_published: bool
    is_public: bool = False
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    can_publish: bool
    can_publish_reason: str


class ReportUpdateRequest(BaseModel):
    """Request model for updating report content"""

    content: ReportContent


class PublishRequest(BaseModel):
    """Optional publish body: whether the report is public (anonymous readable)."""

    is_public: bool = False


class VisibilityRequest(BaseModel):
    is_public: bool


class PublishedReportListItem(BaseModel):
    """List item for published reports"""

    id: str
    project_id: str
    project_title: str
    published_at: Optional[datetime] = None
    task_count: int
    annotation_count: int
    model_count: int
    organizations: List[Dict[str, str]]
    is_public: bool = False
    # 'public' (anyone) or 'organizations' (members of the project's orgs)
    visibility: str = "organizations"


class ReportDataResponse(BaseModel):
    """Response model for the viewer: the report row plus its snapshot."""

    report: ReportResponse
    snapshot: Optional[Dict[str, Any]] = None


def _report_response(
    report: ProjectReport, project_title: str, can_publish: bool, reason: str
) -> "ReportResponse":
    return ReportResponse(
        id=report.id,
        project_id=report.project_id,
        project_title=project_title,
        content=ReportContent(**report.content),
        is_published=report.is_published,
        is_public=bool(getattr(report, "is_public", False)),
        published_at=report.published_at,
        published_by=report.published_by,
        created_by=report.created_by,
        created_at=report.created_at,
        updated_at=report.updated_at,
        can_publish=can_publish,
        can_publish_reason=reason,
    )


# ============= Sync-service bridges =============
#
# The report aggregation helpers in `report_service` (and
# `create_or_update_report_from_existing_data`) live in /shared and are
# sync-only — they run complex joins, `.has()` subqueries and distinct counts
# against a sync `Session`, and have no async twin. The handlers below are
# async (their direct DB reads use `get_async_db`), so they bridge these sync
# helpers onto a sync `Session` bound to THIS async session's connection via
# `await db.run_sync(...)` — the helper runs inside the same transaction
# without opening a second connection (matches the dashboard/leaderboards
# `db.run_sync` bridge pattern). The thin sync wrappers below take that bridged
# `sync_db` as their first argument.


def _can_publish_report_sync(sync_db, project_id: str):
    return can_publish_report(sync_db, project_id)


def _create_or_update_report_sync(sync_db, project_id: str, user_id: str):
    """Run the sync report autocreate and return the new row's id (the only
    field the async handler needs — it re-reads via the async session)."""
    report = create_or_update_report_from_existing_data(sync_db, project_id, user_id)
    return report.id


def _build_snapshot_sync(sync_db, project_id: str):
    """Compute the report snapshot on the bridged sync session (SQL
    aggregation only — see report_snapshot)."""
    return build_report_snapshot(sync_db, project_id)


def _report_statistics_batch_sync(sync_db, project_ids: List[str]):
    return get_report_statistics_batch(sync_db, project_ids)


# ============= Helper Functions =============


async def check_report_access(
    db: AsyncSession, project_id: str, user: User, require_edit: bool = False
) -> bool:
    """
    Check if user has access to a report

    Args:
        db: Async database session
        project_id: Project ID
        user: Current user
        require_edit: If True, requires superadmin access

    Returns:
        bool: True if user has access

    Raises:
        HTTPException: If user doesn't have access
    """
    # Superadmins have full access
    if user.is_superadmin:
        return True

    # Soft-deleted project (093): its reports are gone for non-superadmins.
    deleted = (
        await db.execute(select(Project.deleted_at).where(Project.id == project_id))
    ).scalar_one_or_none()
    if deleted is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )

    # For non-superadmins, check if they're in an organization that has access
    # to the project — through an ELIGIBLE attachment (grouped attachments
    # count only for the group's members / the org's ORG_ADMINs).
    if not require_edit:
        eligible = await db.execute(
            select(OrganizationMembership.id)
            .join(
                ProjectOrganization,
                ProjectOrganization.organization_id
                == OrganizationMembership.organization_id,
            )
            .where(
                ProjectOrganization.project_id == project_id,
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.is_active == True,  # noqa: E712
                attachment_group_clause(
                    ProjectOrganization,
                    str(user.id),
                    membership=OrganizationMembership,
                ),
            )
            .limit(1)
        )
        if eligible.first() is not None:
            return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to access this report",
    )


# ============= Endpoints =============


@router.get("/projects/{project_id}/report", response_model=ReportResponse)
async def get_project_report(
    project_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get report for a project

    - Superadmins: Can view draft or published reports
    - Org members: Can view only published reports

    If report doesn't exist, it will be auto-created for superadmins with all existing project data
    """
    # Check if project exists
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Get report - create if it doesn't exist (retroactive for existing projects)
    report = (
        await db.execute(
            select(ProjectReport).where(ProjectReport.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not report:
        # Auto-create report for existing projects with all current data
        # This allows existing projects to get reports retroactively
        if current_user.is_superadmin:
            logger.info(
                f"Auto-creating report for existing project {project_id} with all current data"
            )
            # report_service is sync-only — create on a short-lived sync
            # session, then re-read through the async session.
            new_report_id = await db.run_sync(
                _create_or_update_report_sync, project_id, current_user.id
            )
            # The sync helper now flush()es rather than commit()s (so it can't
            # commit this async request's outer transaction); persist it here.
            await db.commit()
            report = await db.get(ProjectReport, new_report_id)
        else:
            # Non-superadmins can't trigger report creation
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report not found for project {project_id}",
            )

    # Check if user can view this report
    if not report.is_published:
        # Only superadmins can view unpublished reports
        if not current_user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="This report is not published yet"
            )

    # For published reports, check organization access
    if report.is_published and not current_user.is_superadmin:
        await check_report_access(db, project_id, current_user, require_edit=False)

    # Check if report can be published
    can_publish, reason = await db.run_sync(_can_publish_report_sync, project_id)

    return _report_response(report, project.title, can_publish, reason)


@router.post("/projects/{project_id}/report", response_model=ReportResponse)
async def update_project_report(
    project_id: str,
    update_request: ReportUpdateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update report content (superadmin only)

    Allows editing report sections while preserving auto-populated data
    """
    # Only superadmins can edit reports
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmins can edit reports"
        )

    # Check if project exists
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Get report
    report = (
        await db.execute(
            select(ProjectReport).where(ProjectReport.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found for project {project_id}",
        )

    # Update content. The editor round-trips prose and presentation settings;
    # the computed snapshot is server-owned and survives a body that omits it.
    new_content = update_request.content.model_dump()
    existing = report.content if isinstance(report.content, dict) else {}
    if new_content.get("snapshot") is None and existing.get("snapshot"):
        new_content["snapshot"] = existing["snapshot"]
    report.content = new_content
    report.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(report)

    # Check if report can be published
    can_publish, reason = await db.run_sync(_can_publish_report_sync, project_id)

    return _report_response(report, project.title, can_publish, reason)


@router.put("/projects/{project_id}/report/publish", response_model=ReportResponse)
async def publish_report(
    project_id: str,
    body: Optional[PublishRequest] = Body(default=None),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Publish a report (superadmin only)

    Validates that all requirements are met, computes the report snapshot
    (the numbers a published report shows, frozen at this point) and sets
    the visibility: organizations only (default) or public.
    """
    # Only superadmins can publish reports
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmins can publish reports"
        )

    # Check if project exists
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Get report
    report = (
        await db.execute(
            select(ProjectReport).where(ProjectReport.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found for project {project_id}",
        )

    # Check if report can be published
    can_publish, reason = await db.run_sync(_can_publish_report_sync, project_id)
    if not can_publish:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot publish report: {reason}"
        )

    # Freeze the numbers, then publish
    snapshot = await db.run_sync(_build_snapshot_sync, project_id)
    report.content = {**(report.content or {}), "snapshot": snapshot}
    report.is_published = True
    report.is_public = bool(body.is_public) if body else False
    report.published_at = datetime.utcnow()
    report.published_by = current_user.id

    await db.commit()
    await db.refresh(report)

    return _report_response(report, project.title, can_publish, reason)


@router.put("/projects/{project_id}/report/unpublish", response_model=ReportResponse)
async def unpublish_report(
    project_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Unpublish a report (superadmin only)
    """
    # Only superadmins can unpublish reports
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmins can unpublish reports"
        )

    # Check if project exists
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Get report
    report = (
        await db.execute(
            select(ProjectReport).where(ProjectReport.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found for project {project_id}",
        )

    # Unpublish the report
    report.is_published = False
    report.is_public = False
    report.published_at = None
    report.published_by = None

    await db.commit()
    await db.refresh(report)

    # Check if report can be published
    can_publish, reason = await db.run_sync(_can_publish_report_sync, project_id)

    return _report_response(report, project.title, can_publish, reason)


async def _load_project_and_report(db: AsyncSession, project_id: str):
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )
    report = (
        await db.execute(
            select(ProjectReport).where(ProjectReport.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found for project {project_id}",
        )
    return project, report


@router.put("/projects/{project_id}/report/visibility", response_model=ReportResponse)
async def set_report_visibility(
    project_id: str,
    body: VisibilityRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Switch a published report between organizations-only and public (superadmin)."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmins can change report visibility"
        )
    project, report = await _load_project_and_report(db, project_id)
    if not report.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Publish the report before changing its visibility",
        )
    report.is_public = bool(body.is_public)
    report.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(report)
    can_publish, reason = await db.run_sync(_can_publish_report_sync, project_id)
    return _report_response(report, project.title, can_publish, reason)


@router.post("/projects/{project_id}/report/refresh", response_model=ReportResponse)
async def refresh_report_snapshot(
    project_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Recompute the report snapshot from current data (superadmin).

    Published reports keep their numbers until this is called explicitly, so
    a benchmark report never changes underneath its readers.
    """
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmins can refresh reports"
        )
    project, report = await _load_project_and_report(db, project_id)
    snapshot = await db.run_sync(_build_snapshot_sync, project_id)
    report.content = {**(report.content or {}), "snapshot": snapshot}
    report.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(report)
    can_publish, reason = await db.run_sync(_can_publish_report_sync, project_id)
    return _report_response(report, project.title, can_publish, reason)


@router.get("/reports", response_model=List[PublishedReportListItem])
async def list_published_reports(
    current_user: Optional[User] = Depends(optional_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    List published reports

    - Anonymous visitors: public reports only
    - Signed-in users: public reports plus published reports of their organizations
    - Superadmins: every published report
    """
    # Query published reports. Eager-load `.project` (accessed below for the
    # title) via joinedload so the async session never lazy-loads it.
    stmt = (
        select(ProjectReport)
        .options(joinedload(ProjectReport.project))
        .join(Project, Project.id == ProjectReport.project_id)
        .where(
            ProjectReport.is_published == True,  # noqa: E712
            Project.deleted_at.is_(None),
        )
    )

    # Filter by organization for non-superadmins (grouped attachments count
    # only through the caller's groups / ORG_ADMIN memberships). Applied
    # even when the caller has NO orgs: the old `and user_org_ids` guard
    # skipped the filter entirely for org-less users, listing every
    # published report they could never open (the per-report gate denies
    # them) — docstring says org members see their orgs' reports.
    if current_user is None:
        stmt = stmt.where(ProjectReport.is_public == True)  # noqa: E712
    elif not current_user.is_superadmin:
        proj_id_rows = await db.execute(
            select(ProjectOrganization.project_id)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id
                == ProjectOrganization.organization_id,
            )
            .where(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.is_active == True,  # noqa: E712
                attachment_group_clause(
                    ProjectOrganization,
                    str(current_user.id),
                    membership=OrganizationMembership,
                ),
            )
        )
        project_ids = [row[0] for row in proj_id_rows.all()]
        stmt = stmt.where(
            or_(
                ProjectReport.is_public == True,  # noqa: E712
                ProjectReport.project_id.in_(project_ids),
            )
        )

    stmt = stmt.order_by(ProjectReport.published_at.desc())
    reports = (await db.execute(stmt)).scalars().all()

    # Batch-fetch statistics + org memberships for all reports in 5 queries
    # total (4 grouped stats + 1 joined orgs) instead of 5 × N round-trips.
    # The batch stats helper is sync-only — run it on a short-lived sync
    # session off the event loop.
    report_project_ids = [r.project_id for r in reports]
    stats_map = await db.run_sync(_report_statistics_batch_sync, report_project_ids)

    orgs_by_project: Dict[str, list] = {pid: [] for pid in report_project_ids}
    if report_project_ids:
        # Eager-load `.organization` (accessed below) via joinedload.
        org_rows = (
            await db.execute(
                select(ProjectOrganization)
                .options(joinedload(ProjectOrganization.organization))
                .where(ProjectOrganization.project_id.in_(report_project_ids))
            )
        ).scalars().all()
        for po in org_rows:
            orgs_by_project.setdefault(po.project_id, []).append(
                {"id": po.organization.id, "name": po.organization.name}
            )

    result = []
    for report in reports:
        stats = dict(stats_map.get(
            report.project_id,
            {"task_count": 0, "annotation_count": 0, "participant_count": 0, "model_count": 0},
        ))
        # A published report shows its frozen snapshot, so the card must count
        # the same way (hidden private models excluded, numbers as of the
        # snapshot) — otherwise the list says "22 models" and the page "21".
        content = report.content if isinstance(report.content, dict) else {}
        snapshot = content.get("snapshot") if isinstance(content.get("snapshot"), dict) else None
        if snapshot:
            snap_stats = snapshot.get("statistics") or {}
            for key in ("task_count", "annotation_count", "model_count"):
                if isinstance(snap_stats.get(key), int):
                    stats[key] = snap_stats[key]
        result.append(
            PublishedReportListItem(
                id=report.id,
                project_id=report.project_id,
                project_title=report.project.title,
                published_at=report.published_at or report.updated_at or report.created_at,
                task_count=stats["task_count"],
                annotation_count=stats["annotation_count"],
                model_count=stats["model_count"],
                organizations=orgs_by_project.get(report.project_id, []),
                is_public=bool(report.is_public),
                visibility="public" if report.is_public else "organizations",
            )
        )

    return result


@router.get("/reports/{report_id}/data", response_model=ReportDataResponse)
async def get_report_data(
    report_id: str,
    current_user: Optional[User] = Depends(optional_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Report row plus its snapshot for the viewer.

    - Public reports: anyone, signed in or not
    - Published organization reports: members of the project's organizations
    - Drafts: superadmins only (the snapshot is computed on first view)
    """
    report = (
        await db.execute(
            select(ProjectReport)
            .options(joinedload(ProjectReport.project))
            .where(ProjectReport.id == report_id)
        )
    ).scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found"
        )

    is_superadmin = bool(current_user and current_user.is_superadmin)
    if not report.is_published:
        if not is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN if current_user else status.HTTP_401_UNAUTHORIZED,
                detail="This report is not published yet",
            )
    elif not report.is_public and not is_superadmin:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sign in to view this report",
            )
        await check_report_access(db, report.project_id, current_user, require_edit=False)

    content = report.content if isinstance(report.content, dict) else {}
    snapshot = content.get("snapshot")
    if snapshot is None and is_superadmin:
        # Draft preview: compute once and keep it so the editor sees stable numbers.
        snapshot = await db.run_sync(_build_snapshot_sync, report.project_id)
        report.content = {**content, "snapshot": snapshot}
        await db.commit()
        await db.refresh(report)

    can_publish, reason = (
        await db.run_sync(_can_publish_report_sync, report.project_id)
        if is_superadmin
        else (report.is_published, "published")
    )

    return ReportDataResponse(
        report=_report_response(report, report.project.title, can_publish, reason),
        snapshot=snapshot,
    )
