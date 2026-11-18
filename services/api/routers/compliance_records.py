"""Compliance records: generic CRUD over assessments, suite runs and findings.

Platform-owned persistence (migration 145, core 2.57) for the compliance
overlay: ``/api/compliance/assessments``, ``/api/compliance/suite-runs`` and
``/api/compliance/findings``. The routes store and return rows and enforce
only the generic rules of ``compliance_records``:

- Access is per organization: active ORG_ADMIN or CONTRIBUTOR members of the
  assessment's (active) organization read and write; deleting needs
  ORG_ADMIN; superadmins see everything. Anyone else gets 404, so the
  existence of another organization's assessment does not leak.
- New assessments start as ``draft``. Status changes are not a CRUD write:
  the workflow that owns the meaning of each status (the overlay) moves
  assessments with ``compliance_records.transition_assessment``. Suite runs
  move along the static table of ``compliance_records.SUITE_RUN_TRANSITIONS``.
- Registered assessments keep their catalog version, suites, thresholds and
  target; terminal assessments and finished suite runs are read-only (409
  with ``{"code", "message"}``). Only drafts and their suite runs can be
  deleted.
- Referenced ids are checked where their table exists (system model, project,
  superseded assessment). Analysis run and estimate ids are stored as given,
  because the analysis tables are not part of this migration.

Access keys stay out (``app/core/key_routes``): key access to compliance
data is the overlay's ``/api/v1`` surface.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import compliance_records as records
from auth_module.dependencies import require_user
from database import get_async_db
from models import (
    ComplianceAssessment,
    ComplianceFinding,
    ComplianceSuiteRun,
    LLMModel,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)
from project_models import Project

router = APIRouter(prefix="/api/compliance", tags=["compliance-records"])

EDITOR_ROLES = (OrganizationRole.ORG_ADMIN, OrganizationRole.CONTRIBUTOR)

#: Size caps (bytes of compact JSON) for the free-form JSON fields.
MAX_SPEC_JSON = 256 * 1024
MAX_FINDING_JSON = 64 * 1024
MAX_ID_LIST = 1000
MAX_FINDINGS_PER_REQUEST = 2000
MAX_PAGE = 1000
MAX_INT4 = 2**31 - 1
MAX_INT8 = 2**63 - 1

Verdict = Literal["pass", "fail", "inconclusive", "informative", "not_applicable"]
SuiteRunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
AssessmentStatus = Literal[
    "draft",
    "registered",
    "collecting",
    "scoring",
    "review",
    "attested",
    "superseded",
    "withdrawn",
]


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


def _json_size(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _cap_json(value: Any, limit: int, name: str) -> Any:
    if value is not None and _json_size(value) > limit:
        raise ValueError(f"{name} is larger than {limit // 1024} KB")
    return value


FiniteFloat = Optional[float]
IdList = List[str]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssessmentCreate(_Strict):
    organization_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=300)
    catalog_version: Optional[str] = Field(None, max_length=64)
    suites: List[Union[str, Dict[str, Any]]] = Field(default_factory=list, max_length=200)
    thresholds: Dict[str, Any] = Field(default_factory=dict)
    system_model_id: Optional[str] = None
    project_id: Optional[str] = None
    release_id: Optional[str] = Field(None, max_length=255)
    supersedes_id: Optional[str] = None
    limitations_text: Optional[str] = Field(None, max_length=20000)

    @model_validator(mode="after")
    def _sizes(self):
        _cap_json(self.suites, MAX_SPEC_JSON, "suites")
        _cap_json(self.thresholds, MAX_SPEC_JSON, "thresholds")
        return self


class AssessmentUpdate(_Strict):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    catalog_version: Optional[str] = Field(None, max_length=64)
    suites: Optional[List[Union[str, Dict[str, Any]]]] = Field(None, max_length=200)
    thresholds: Optional[Dict[str, Any]] = None
    system_model_id: Optional[str] = None
    project_id: Optional[str] = None
    release_id: Optional[str] = Field(None, max_length=255)
    limitations_text: Optional[str] = Field(None, max_length=20000)

    @model_validator(mode="after")
    def _sizes(self):
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        for name in ("suites", "thresholds"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        _cap_json(self.suites, MAX_SPEC_JSON, "suites")
        _cap_json(self.thresholds, MAX_SPEC_JSON, "thresholds")
        return self


class _SuiteRunFields(_Strict):
    parameters: Optional[Dict[str, Any]] = None
    submission_ids: Optional[IdList] = Field(None, max_length=MAX_ID_LIST)
    evaluation_run_ids: Optional[IdList] = Field(None, max_length=MAX_ID_LIST)
    analysis_run_ids: Optional[IdList] = Field(None, max_length=MAX_ID_LIST)
    inputs_hash: Optional[str] = Field(None, max_length=128)
    judge_config_hash: Optional[str] = Field(None, max_length=128)
    code_version: Optional[str] = Field(None, max_length=128)
    celery_task_id: Optional[str] = Field(None, max_length=255)
    log_object_key: Optional[str] = Field(None, max_length=1024)

    @model_validator(mode="after")
    def _sizes(self):
        for name in ("parameters", "submission_ids", "evaluation_run_ids", "analysis_run_ids"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        _cap_json(self.parameters, MAX_SPEC_JSON, "parameters")
        return self


class SuiteRunCreate(_SuiteRunFields):
    suite_id: str = Field(min_length=1, max_length=100)
    suite_version: Optional[str] = Field(None, max_length=64)


class SuiteRunUpdate(_SuiteRunFields):
    status: Optional[SuiteRunStatus] = None
    error: Optional[str] = Field(None, max_length=20000)


class _FindingFields(_Strict):
    system_key: Optional[str] = Field(None, max_length=255)
    scope: Optional[Dict[str, Any]] = None
    n_tasks: Optional[int] = Field(None, ge=0, le=MAX_INT4)
    n_runs: Optional[int] = Field(None, ge=0, le=MAX_INT4)
    value: FiniteFloat = Field(None, allow_inf_nan=False)
    ci_low: FiniteFloat = Field(None, allow_inf_nan=False)
    ci_high: FiniteFloat = Field(None, allow_inf_nan=False)
    ci_level: FiniteFloat = Field(None, gt=0, lt=1, allow_inf_nan=False)
    ci_method: Optional[str] = Field(None, max_length=64)
    threshold: Optional[Dict[str, Any]] = None
    baseline: Optional[Dict[str, Any]] = None
    details: Optional[Dict[str, Any]] = None
    analysis_run_id: Optional[str] = Field(None, max_length=255)
    analysis_estimate_id: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def _shape(self):
        if "scope" in self.model_fields_set and self.scope is None:
            raise ValueError("scope cannot be null")
        for name in ("scope", "threshold", "baseline", "details"):
            _cap_json(getattr(self, name), MAX_FINDING_JSON, name)
        return self


class FindingCreate(_FindingFields):
    requirement_ref: str = Field(min_length=1, max_length=200)
    metric: str = Field(min_length=1, max_length=200)
    verdict: Verdict

    @model_validator(mode="after")
    def _interval(self):
        _check_interval(self.ci_low, self.ci_high)
        return self


class FindingUpdate(_FindingFields):
    requirement_ref: Optional[str] = Field(None, min_length=1, max_length=200)
    metric: Optional[str] = Field(None, min_length=1, max_length=200)
    verdict: Optional[Verdict] = None

    @model_validator(mode="after")
    def _required(self):
        for name in ("requirement_ref", "metric", "verdict"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class FindingsCreate(_Strict):
    findings: List[FindingCreate] = Field(min_length=1, max_length=MAX_FINDINGS_PER_REQUEST)


def _check_interval(low: Optional[float], high: Optional[float]) -> None:
    if low is not None and high is not None and low > high:
        raise ValueError("ci_low must not be greater than ci_high")


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def assessment_dict(row: ComplianceAssessment) -> dict:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "title": row.title,
        "status": row.status,
        "catalog_version": row.catalog_version,
        "suites": row.suites or [],
        "thresholds": row.thresholds or {},
        "thresholds_hash": row.thresholds_hash,
        "system_model_id": row.system_model_id,
        "project_id": row.project_id,
        "release_id": row.release_id,
        "supersedes_id": row.supersedes_id,
        "contamination_suspected": bool(row.contamination_suspected),
        "limitations_text": row.limitations_text,
        "registered_at": _iso(row.registered_at),
        "attested_at": _iso(row.attested_at),
        "created_by": row.created_by,
        "created_by_key_id": row.created_by_key_id,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def suite_run_dict(row: ComplianceSuiteRun) -> dict:
    return {
        "id": row.id,
        "assessment_id": row.assessment_id,
        "suite_id": row.suite_id,
        "suite_version": row.suite_version,
        "status": row.status,
        "parameters": row.parameters or {},
        "submission_ids": row.submission_ids or [],
        "evaluation_run_ids": row.evaluation_run_ids or [],
        "analysis_run_ids": row.analysis_run_ids or [],
        "inputs_hash": row.inputs_hash,
        "judge_config_hash": row.judge_config_hash,
        "code_version": row.code_version,
        "celery_task_id": row.celery_task_id,
        "log_object_key": row.log_object_key,
        "error": row.error,
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "created_by": row.created_by,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def finding_dict(row: ComplianceFinding) -> dict:
    return {
        "id": row.id,
        "suite_run_id": row.suite_run_id,
        "assessment_id": row.assessment_id,
        "requirement_ref": row.requirement_ref,
        "metric": row.metric,
        "system_key": row.system_key,
        "scope": row.scope or {},
        "n_tasks": row.n_tasks,
        "n_runs": row.n_runs,
        "value": row.value,
        "ci_low": row.ci_low,
        "ci_high": row.ci_high,
        "ci_level": row.ci_level,
        "ci_method": row.ci_method,
        "threshold": row.threshold,
        "verdict": row.verdict,
        "baseline": row.baseline,
        "details": row.details,
        "analysis_run_id": row.analysis_run_id,
        "analysis_estimate_id": row.analysis_estimate_id,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _page(items: list, total: int, limit: int, offset: int) -> dict:
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# --------------------------------------------------------------------------- #
# Access
# --------------------------------------------------------------------------- #


def _conflict(exc: records.ComplianceRecordConflict) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": exc.code, "message": exc.detail})


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} not found")


def _editor_org_ids(user: User):
    """Select of the organizations ``user`` may read and write records of."""
    return (
        select(OrganizationMembership.organization_id)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.role.in_(EDITOR_ROLES),
            OrganizationMembership.is_active == True,  # noqa: E712
            Organization.is_active == True,  # noqa: E712
        )
    )


async def _org_role(db: AsyncSession, user: User, org_id: str) -> Optional[OrganizationRole]:
    """The caller's editor role in ``org_id`` (ORG_ADMIN for superadmins),
    or None."""
    if user.is_superadmin:
        exists = await db.scalar(select(Organization.id).where(Organization.id == org_id))
        return OrganizationRole.ORG_ADMIN if exists is not None else None
    result = await db.execute(
        select(OrganizationMembership.role)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.role.in_(EDITOR_ROLES),
            OrganizationMembership.is_active == True,  # noqa: E712
            Organization.is_active == True,  # noqa: E712
        )
    )
    return result.scalars().first()


async def _require_org(
    db: AsyncSession, user: User, org_id: str, *, admin: bool = False, what: str
) -> None:
    role = await _org_role(db, user, org_id)
    if role is None:
        raise _not_found(what)
    if admin and role != OrganizationRole.ORG_ADMIN:
        raise HTTPException(
            status_code=403, detail="Organization admin access required to delete this record"
        )


async def _load_assessment(
    db: AsyncSession, user: User, assessment_id: str, *, lock: bool = False, admin: bool = False
) -> ComplianceAssessment:
    stmt = select(ComplianceAssessment).where(ComplianceAssessment.id == assessment_id)
    if lock:
        stmt = stmt.with_for_update()
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _not_found("Assessment")
    await _require_org(db, user, row.organization_id, admin=admin, what="Assessment")
    return row


async def _load_suite_run(
    db: AsyncSession, user: User, suite_run_id: str, *, lock: bool = False, admin: bool = False
):
    """``(assessment, suite_run)``; with ``lock`` both rows are locked,
    assessment first."""
    run = (
        await db.execute(select(ComplianceSuiteRun).where(ComplianceSuiteRun.id == suite_run_id))
    ).scalar_one_or_none()
    if run is None:
        raise _not_found("Suite run")
    try:
        assessment = await _load_assessment(
            db, user, run.assessment_id, lock=lock, admin=admin
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            raise _not_found("Suite run")
        raise
    if lock:
        run = (
            await db.execute(
                select(ComplianceSuiteRun)
                .where(ComplianceSuiteRun.id == suite_run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if run is None:
            raise _not_found("Suite run")
    return assessment, run


async def _load_finding(
    db: AsyncSession, user: User, finding_id: str, *, lock: bool = False, admin: bool = False
):
    """``(assessment, suite_run, finding)``; with ``lock`` all three rows are
    locked in that order and the finding is read again under the locks."""
    stmt = select(ComplianceFinding).where(ComplianceFinding.id == finding_id)
    finding = (await db.execute(stmt)).scalar_one_or_none()
    if finding is None:
        raise _not_found("Finding")
    try:
        assessment, run = await _load_suite_run(
            db, user, finding.suite_run_id, lock=lock, admin=admin
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            raise _not_found("Finding")
        raise
    if lock:
        finding = (
            await db.execute(stmt.with_for_update().execution_options(populate_existing=True))
        ).scalar_one_or_none()
        if finding is None:
            raise _not_found("Finding")
    return assessment, run, finding


async def _check_targets(
    db: AsyncSession,
    user: User,
    *,
    organization_id: str,
    fields: Dict[str, Any],
) -> None:
    """Referenced rows must exist and be usable by the caller (422)."""
    model_id = fields.get("system_model_id")
    if model_id:
        from routers.model_access import check_model_accessible_async

        model = (
            await db.execute(select(LLMModel).where(LLMModel.id == model_id))
        ).scalar_one_or_none()
        if model is None or not await check_model_accessible_async(db, user, model):
            raise HTTPException(status_code=422, detail="system_model_id: unknown model")
    project_id = fields.get("project_id")
    if project_id:
        from routers.projects.helpers import (
            check_project_accessible_async,
            get_effective_project_role_async,
        )

        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if (
            project is None
            or not await check_project_accessible_async(db, user, project_id, project)
            or await get_effective_project_role_async(db, user, project)
            not in ("ORG_ADMIN", "CONTRIBUTOR")
        ):
            raise HTTPException(
                status_code=422,
                detail="project_id: unknown project, or you may not assess it",
            )
    supersedes_id = fields.get("supersedes_id")
    if supersedes_id:
        other = (
            await db.execute(
                select(ComplianceAssessment).where(ComplianceAssessment.id == supersedes_id)
            )
        ).scalar_one_or_none()
        if other is None or other.organization_id != organization_id:
            raise HTTPException(
                status_code=422,
                detail="supersedes_id: unknown assessment of this organization",
            )


# --------------------------------------------------------------------------- #
# Assessments
# --------------------------------------------------------------------------- #


@router.get("/assessments")
async def list_assessments(
    organization_id: Optional[str] = None,
    status: Optional[AssessmentStatus] = None,
    project_id: Optional[str] = None,
    system_model_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0, le=MAX_INT8),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Assessments of the caller's organizations, newest first."""
    clauses = []
    if not user.is_superadmin:
        clauses.append(ComplianceAssessment.organization_id.in_(_editor_org_ids(user)))
    if organization_id:
        clauses.append(ComplianceAssessment.organization_id == organization_id)
    if status:
        clauses.append(ComplianceAssessment.status == status)
    if project_id:
        clauses.append(ComplianceAssessment.project_id == project_id)
    if system_model_id:
        clauses.append(ComplianceAssessment.system_model_id == system_model_id)
    total = (
        await db.execute(select(func.count(ComplianceAssessment.id)).where(*clauses))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(ComplianceAssessment)
                .where(*clauses)
                .order_by(ComplianceAssessment.created_at.desc(), ComplianceAssessment.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return _page([assessment_dict(r) for r in rows], total, limit, offset)


@router.post("/assessments", status_code=201)
async def create_assessment(
    body: AssessmentCreate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a draft assessment in an organization the caller edits."""
    await _require_org(db, user, body.organization_id, what="Organization")
    fields = body.model_dump()
    await _check_targets(db, user, organization_id=body.organization_id, fields=fields)
    row = ComplianceAssessment(
        id=str(uuid.uuid4()),
        status=records.ASSESSMENT_DRAFT,
        created_by=user.id,
        **fields,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return assessment_dict(row)


@router.get("/assessments/{assessment_id}")
async def get_assessment(
    assessment_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    return assessment_dict(await _load_assessment(db, user, assessment_id))


@router.patch("/assessments/{assessment_id}")
async def update_assessment(
    assessment_id: str,
    body: AssessmentUpdate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Change an open assessment. The registration fixes the catalog
    version, suites, thresholds and target (409 ``assessment_registered``);
    a terminal assessment refuses every change (409 ``assessment_closed``).
    Sending a fixed field with its stored value is not a change."""
    row = await _load_assessment(db, user, assessment_id, lock=True)
    changes = {
        name: value
        for name, value in body.model_dump(exclude_unset=True).items()
        if getattr(row, name) != value
    }
    try:
        records.check_assessment_editable(row, changes)
    except records.ComplianceRecordConflict as exc:
        raise _conflict(exc)
    await _check_targets(db, user, organization_id=row.organization_id, fields=changes)
    for name, value in changes.items():
        setattr(row, name, value)
    await db.commit()
    await db.refresh(row)
    return assessment_dict(row)


@router.delete("/assessments/{assessment_id}", status_code=204)
async def delete_assessment(
    assessment_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a draft assessment with its suite runs and findings (ORG_ADMIN)."""
    row = await _load_assessment(db, user, assessment_id, lock=True, admin=True)
    try:
        records.check_assessment_deletable(row)
    except records.ComplianceRecordConflict as exc:
        raise _conflict(exc)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Suite runs
# --------------------------------------------------------------------------- #


@router.get("/assessments/{assessment_id}/suite-runs")
async def list_suite_runs(
    assessment_id: str,
    suite_id: Optional[str] = None,
    status: Optional[SuiteRunStatus] = None,
    limit: int = Query(100, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0, le=MAX_INT8),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The assessment's suite runs, oldest first."""
    await _load_assessment(db, user, assessment_id)
    clauses = [ComplianceSuiteRun.assessment_id == assessment_id]
    if suite_id:
        clauses.append(ComplianceSuiteRun.suite_id == suite_id)
    if status:
        clauses.append(ComplianceSuiteRun.status == status)
    count = select(func.count(ComplianceSuiteRun.id)).where(*clauses)
    total = (await db.execute(count)).scalar_one()
    rows = (
        (
            await db.execute(
                select(ComplianceSuiteRun)
                .where(*clauses)
                .order_by(ComplianceSuiteRun.created_at, ComplianceSuiteRun.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return _page([suite_run_dict(r) for r in rows], total, limit, offset)


@router.post("/assessments/{assessment_id}/suite-runs", status_code=201)
async def create_suite_run(
    assessment_id: str,
    body: SuiteRunCreate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Record a new (queued) suite run of an open assessment."""
    assessment = await _load_assessment(db, user, assessment_id, lock=True)
    try:
        records.check_assessment_accepts_suite_runs(assessment)
    except records.ComplianceRecordConflict as exc:
        raise _conflict(exc)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    row = ComplianceSuiteRun(
        id=str(uuid.uuid4()),
        assessment_id=assessment.id,
        status=records.SUITE_RUN_QUEUED,
        created_by=user.id,
        **fields,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return suite_run_dict(row)


@router.get("/suite-runs/{suite_run_id}")
async def get_suite_run(
    suite_run_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    _, run = await _load_suite_run(db, user, suite_run_id)
    return suite_run_dict(run)


@router.patch("/suite-runs/{suite_run_id}")
async def update_suite_run(
    suite_run_id: str,
    body: SuiteRunUpdate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Change an open suite run; ``status`` follows the static transition
    table and stamps ``started_at`` / ``finished_at``. A finished run is
    read-only (409 ``suite_run_finished``)."""
    assessment, run = await _load_suite_run(db, user, suite_run_id, lock=True)
    try:
        records.check_findings_writable(assessment, run)
        changes = body.model_dump(exclude_unset=True)
        status = changes.pop("status", None)
        for name, value in changes.items():
            setattr(run, name, value)
        if status is not None:
            records.transition_suite_run(run, status)
    except records.ComplianceRecordConflict as exc:
        await db.rollback()
        raise _conflict(exc)
    await db.commit()
    await db.refresh(run)
    return suite_run_dict(run)


@router.delete("/suite-runs/{suite_run_id}", status_code=204)
async def delete_suite_run(
    suite_run_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a suite run of a draft assessment with its findings (ORG_ADMIN)."""
    assessment, run = await _load_suite_run(db, user, suite_run_id, lock=True, admin=True)
    try:
        records.check_suite_run_deletable(assessment, run)
    except records.ComplianceRecordConflict as exc:
        raise _conflict(exc)
    await db.delete(run)
    await db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #

_FINDING_ORDER = (
    ComplianceFinding.requirement_ref,
    ComplianceFinding.metric,
    ComplianceFinding.system_key.nulls_first(),
    ComplianceFinding.created_at,
    ComplianceFinding.id,
)


def _finding_filters(
    *,
    verdict: Optional[str],
    system_key: Optional[str],
    requirement_ref: Optional[str],
    metric: Optional[str],
) -> list:
    clauses = []
    if verdict:
        clauses.append(ComplianceFinding.verdict == verdict)
    if system_key:
        clauses.append(ComplianceFinding.system_key == system_key)
    if requirement_ref:
        clauses.append(ComplianceFinding.requirement_ref == requirement_ref)
    if metric:
        clauses.append(ComplianceFinding.metric == metric)
    return clauses


async def _finding_page(db: AsyncSession, clauses: list, limit: int, offset: int) -> dict:
    count = select(func.count(ComplianceFinding.id)).where(*clauses)
    total = (await db.execute(count)).scalar_one()
    rows = (
        (
            await db.execute(
                select(ComplianceFinding)
                .where(*clauses)
                .order_by(*_FINDING_ORDER)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return _page([finding_dict(r) for r in rows], total, limit, offset)


@router.get("/suite-runs/{suite_run_id}/findings")
async def list_suite_run_findings(
    suite_run_id: str,
    verdict: Optional[Verdict] = None,
    system_key: Optional[str] = None,
    requirement_ref: Optional[str] = None,
    metric: Optional[str] = None,
    limit: int = Query(MAX_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0, le=MAX_INT8),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The suite run's findings, ordered by requirement, metric and system."""
    await _load_suite_run(db, user, suite_run_id)
    clauses = [ComplianceFinding.suite_run_id == suite_run_id] + _finding_filters(
        verdict=verdict, system_key=system_key, requirement_ref=requirement_ref, metric=metric
    )
    return await _finding_page(db, clauses, limit, offset)


@router.post("/suite-runs/{suite_run_id}/findings", status_code=201)
async def create_findings(
    suite_run_id: str,
    body: FindingsCreate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Add findings to an open suite run (all or none)."""
    assessment, run = await _load_suite_run(db, user, suite_run_id, lock=True)
    try:
        records.check_findings_writable(assessment, run)
    except records.ComplianceRecordConflict as exc:
        raise _conflict(exc)
    rows = [
        ComplianceFinding(
            id=str(uuid.uuid4()),
            suite_run_id=run.id,
            assessment_id=assessment.id,
            **{k: v for k, v in item.model_dump().items() if not (k == "scope" and v is None)},
        )
        for item in body.findings
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return {"items": [finding_dict(r) for r in rows]}


@router.get("/findings")
async def list_findings(
    assessment_id: Optional[str] = None,
    suite_run_id: Optional[str] = None,
    analysis_run_id: Optional[str] = None,
    analysis_estimate_id: Optional[str] = None,
    verdict: Optional[Verdict] = None,
    system_key: Optional[str] = None,
    requirement_ref: Optional[str] = None,
    metric: Optional[str] = None,
    limit: int = Query(MAX_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0, le=MAX_INT8),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Findings by assessment, suite run, analysis run or analysis estimate
    (at least one of them), limited to the caller's organizations."""
    if not any((assessment_id, suite_run_id, analysis_run_id, analysis_estimate_id)):
        raise HTTPException(
            status_code=422,
            detail="Name assessment_id, suite_run_id, analysis_run_id or analysis_estimate_id",
        )
    clauses = _finding_filters(
        verdict=verdict, system_key=system_key, requirement_ref=requirement_ref, metric=metric
    )
    for column, value in (
        (ComplianceFinding.assessment_id, assessment_id),
        (ComplianceFinding.suite_run_id, suite_run_id),
        (ComplianceFinding.analysis_run_id, analysis_run_id),
        (ComplianceFinding.analysis_estimate_id, analysis_estimate_id),
    ):
        if value:
            clauses.append(column == value)
    if not user.is_superadmin:
        clauses.append(
            ComplianceFinding.assessment_id.in_(
                select(ComplianceAssessment.id).where(
                    ComplianceAssessment.organization_id.in_(_editor_org_ids(user))
                )
            )
        )
    return await _finding_page(db, clauses, limit, offset)


@router.get("/findings/{finding_id}")
async def get_finding(
    finding_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    _, _, finding = await _load_finding(db, user, finding_id)
    return finding_dict(finding)


@router.patch("/findings/{finding_id}")
async def update_finding(
    finding_id: str,
    body: FindingUpdate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Change a finding of an open suite run."""
    assessment, run, finding = await _load_finding(db, user, finding_id, lock=True)
    try:
        records.check_findings_writable(assessment, run)
    except records.ComplianceRecordConflict as exc:
        raise _conflict(exc)
    changes = body.model_dump(exclude_unset=True)
    try:
        _check_interval(
            changes.get("ci_low", finding.ci_low), changes.get("ci_high", finding.ci_high)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    for name, value in changes.items():
        setattr(finding, name, value)
    await db.commit()
    await db.refresh(finding)
    return finding_dict(finding)


@router.delete("/findings/{finding_id}", status_code=204)
async def delete_finding(
    finding_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a finding of an open suite run (organization admins only)."""
    assessment, run, finding = await _load_finding(db, user, finding_id, lock=True, admin=True)
    try:
        records.check_findings_writable(assessment, run)
    except records.ComplianceRecordConflict as exc:
        raise _conflict(exc)
    await db.delete(finding)
    await db.commit()
    return Response(status_code=204)
