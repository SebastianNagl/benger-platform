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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from auth_module import User, require_user
from database import get_db
from models import OrganizationMembership
from project_models import Project, ProjectOrganization
from report_models import ProjectReport
from report_service import (
    can_publish_report,
    create_or_update_report_from_existing_data,
    get_evaluation_charts_data,
    get_report_models,
    get_report_participants,
    get_report_statistics,
)

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


class ReportResponse(BaseModel):
    """Response model for a report"""

    id: str
    project_id: str
    project_title: str
    content: ReportContent
    is_published: bool
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


class PublishedReportListItem(BaseModel):
    """List item for published reports"""

    id: str
    project_id: str
    project_title: str
    published_at: datetime
    task_count: int
    annotation_count: int
    model_count: int
    organizations: List[Dict[str, str]]


class ReportDataResponse(BaseModel):
    """Response model for report data with statistics and charts"""

    report: ReportResponse
    statistics: Dict[str, int]
    participants: List[Dict[str, Any]]
    models: List[str]
    evaluation_charts: Dict[str, Any]


# ============= Helper Functions =============


def check_report_access(
    db: Session, project_id: str, user: User, require_edit: bool = False
) -> bool:
    """
    Check if user has access to a report

    Args:
        db: Database session
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

    # For non-superadmins, check if they're in an organization that has access to the project
    if not require_edit:
        user_org_ids = [
            m.organization_id
            for m in db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user.id, OrganizationMembership.is_active == True
            )
            .all()
        ]

        project_org_ids = [
            po.organization_id
            for po in db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        ]

        # Check if user has any overlapping organizations
        if any(org_id in project_org_ids for org_id in user_org_ids):
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
    db: Session = Depends(get_db),
):
    """
    Get report for a project

    - Superadmins: Can view draft or published reports
    - Org members: Can view only published reports

    If report doesn't exist, it will be auto-created for superadmins with all existing project data
    """
    # Check if project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Get report - create if it doesn't exist (retroactive for existing projects)
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        # Auto-create report for existing projects with all current data
        # This allows existing projects to get reports retroactively
        if current_user.is_superadmin:
            logger.info(
                f"Auto-creating report for existing project {project_id} with all current data"
            )
            report = create_or_update_report_from_existing_data(db, project_id, current_user.id)
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
        check_report_access(db, project_id, current_user, require_edit=False)

    # Check if report can be published
    can_publish, reason = can_publish_report(db, project_id)

    return ReportResponse(
        id=report.id,
        project_id=report.project_id,
        project_title=project.title,
        content=ReportContent(**report.content),
        is_published=report.is_published,
        published_at=report.published_at,
        published_by=report.published_by,
        created_by=report.created_by,
        created_at=report.created_at,
        updated_at=report.updated_at,
        can_publish=can_publish,
        can_publish_reason=reason,
    )


@router.post("/projects/{project_id}/report", response_model=ReportResponse)
async def update_project_report(
    project_id: str,
    update_request: ReportUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
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
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Get report
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found for project {project_id}",
        )

    # Update content
    report.content = update_request.content.model_dump()
    report.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(report)

    # Check if report can be published
    can_publish, reason = can_publish_report(db, project_id)

    return ReportResponse(
        id=report.id,
        project_id=report.project_id,
        project_title=project.title,
        content=ReportContent(**report.content),
        is_published=report.is_published,
        published_at=report.published_at,
        published_by=report.published_by,
        created_by=report.created_by,
        created_at=report.created_at,
        updated_at=report.updated_at,
        can_publish=can_publish,
        can_publish_reason=reason,
    )


@router.put("/projects/{project_id}/report/publish", response_model=ReportResponse)
async def publish_report(
    project_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Publish a report (superadmin only)

    Validates that all requirements are met before publishing
    """
    # Only superadmins can publish reports
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmins can publish reports"
        )

    # Check if project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Get report
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found for project {project_id}",
        )

    # Check if report can be published
    can_publish, reason = can_publish_report(db, project_id)
    if not can_publish:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot publish report: {reason}"
        )

    # Publish the report
    report.is_published = True
    report.published_at = datetime.utcnow()
    report.published_by = current_user.id

    db.commit()
    db.refresh(report)

    return ReportResponse(
        id=report.id,
        project_id=report.project_id,
        project_title=project.title,
        content=ReportContent(**report.content),
        is_published=report.is_published,
        published_at=report.published_at,
        published_by=report.published_by,
        created_by=report.created_by,
        created_at=report.created_at,
        updated_at=report.updated_at,
        can_publish=can_publish,
        can_publish_reason=reason,
    )


@router.put("/projects/{project_id}/report/unpublish", response_model=ReportResponse)
async def unpublish_report(
    project_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
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
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found"
        )

    # Get report
    report = db.query(ProjectReport).filter(ProjectReport.project_id == project_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report not found for project {project_id}",
        )

    # Unpublish the report
    report.is_published = False
    report.published_at = None
    report.published_by = None

    db.commit()
    db.refresh(report)

    # Check if report can be published
    can_publish, reason = can_publish_report(db, project_id)

    return ReportResponse(
        id=report.id,
        project_id=report.project_id,
        project_title=project.title,
        content=ReportContent(**report.content),
        is_published=report.is_published,
        published_at=report.published_at,
        published_by=report.published_by,
        created_by=report.created_by,
        created_at=report.created_at,
        updated_at=report.updated_at,
        can_publish=can_publish,
        can_publish_reason=reason,
    )


@router.get("/reports", response_model=List[PublishedReportListItem])
async def list_published_reports(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    List all published reports

    - Superadmins: See all published reports
    - Org members: See published reports from their organizations
    """
    # Get user's organization IDs
    user_org_ids = []
    if not current_user.is_superadmin:
        user_org_ids = [
            m.organization_id
            for m in db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.is_active == True,
            )
            .all()
        ]

    # Query published reports
    query = (
        db.query(ProjectReport)
        .options(joinedload(ProjectReport.project))
        .filter(ProjectReport.is_published == True)
    )

    # Filter by organization for non-superadmins
    if not current_user.is_superadmin and user_org_ids:
        project_ids = [
            po.project_id
            for po in db.query(ProjectOrganization)
            .filter(ProjectOrganization.organization_id.in_(user_org_ids))
            .all()
        ]
        query = query.filter(ProjectReport.project_id.in_(project_ids))

    reports = query.order_by(ProjectReport.published_at.desc()).all()

    # Build response
    result = []
    for report in reports:
        # Get statistics
        stats = get_report_statistics(db, report.project_id)

        # Get organizations
        orgs = (
            db.query(ProjectOrganization)
            .options(joinedload(ProjectOrganization.organization))
            .filter(ProjectOrganization.project_id == report.project_id)
            .all()
        )

        organizations = [{"id": po.organization.id, "name": po.organization.name} for po in orgs]

        result.append(
            PublishedReportListItem(
                id=report.id,
                project_id=report.project_id,
                project_title=report.project.title,
                published_at=report.published_at,
                task_count=stats["task_count"],
                annotation_count=stats["annotation_count"],
                model_count=stats["model_count"],
                organizations=organizations,
            )
        )

    return result


@router.get("/reports/{report_id}/data", response_model=ReportDataResponse)
async def get_report_data(
    report_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get complete report data including statistics and charts

    Only accessible for published reports (or superadmins for drafts)
    """
    # Get report
    report = (
        db.query(ProjectReport)
        .options(joinedload(ProjectReport.project))
        .filter(ProjectReport.id == report_id)
        .first()
    )

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found"
        )

    # Check access
    if not report.is_published and not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This report is not published yet"
        )

    if report.is_published and not current_user.is_superadmin:
        check_report_access(db, report.project_id, current_user, require_edit=False)

    # Get all data
    statistics = get_report_statistics(db, report.project_id)
    participants = get_report_participants(db, report.project_id)
    models = get_report_models(db, report.project_id)
    evaluation_charts = get_evaluation_charts_data(db, report.project_id)

    # Check if report can be published
    can_publish, reason = can_publish_report(db, report.project_id)

    return ReportDataResponse(
        report=ReportResponse(
            id=report.id,
            project_id=report.project_id,
            project_title=report.project.title,
            content=ReportContent(**report.content),
            is_published=report.is_published,
            published_at=report.published_at,
            published_by=report.published_by,
            created_by=report.created_by,
            created_at=report.created_at,
            updated_at=report.updated_at,
            can_publish=can_publish,
            can_publish_reason=reason,
        ),
        statistics=statistics,
        participants=participants,
        models=models,
        evaluation_charts=evaluation_charts,
    )
