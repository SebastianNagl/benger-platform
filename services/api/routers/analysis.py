"""Analysis runs of variant experiments (the full API).

A project whose tasks carry ``meta.variant`` can be analysed as a factorial
experiment: a spec (``services/shared/analysis/schemas/analysis_spec.schema.json``)
names designs, measures, estimands, contrasts, equivalence bounds and
multiplicity families, and an analysis run computes it on the ``analysis``
worker queue. The engine itself runs in the workers; this router validates
specs, starts runs and reads them back.

Routes:

* ``GET /api/analysis/engine``: engine, spec and grammar versions, the
  default conventions and the spec schema.
* ``POST /api/analysis/specs/validate``: validate a spec and return its
  normalized form and hash (no project needed).
* ``POST /api/projects/{project_id}/analysis-runs``: start a run (edit rights
  on the project); 202 with the run.
* ``GET /api/projects/{project_id}/analysis-runs``: the project's runs, newest
  first.
* ``GET /api/analysis-runs/{analysis_run_id}``: one run with its normalized spec,
  hashes, versions, counts, fits, warnings and timings.
* ``GET /api/analysis-runs/{analysis_run_id}/estimates``: its estimates in engine
  order, filterable by estimand, contrast, scope, family and status.
* ``GET /api/analysis-runs/{analysis_run_id}/frame``: the frame snapshot (Parquet) as a
  short-lived download URL; needs full read access to task content, because
  the frame carries task data paths (gold) and parsed answers.

Reads need full (non-participant) access to the project; participants of an
exam never see analyses.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from celery_client import send_task_safe
from database import get_async_db
from models import AnalysisEstimate, AnalysisRun
from project_models import Project
from routers.projects.deps import ProjectAccess, require_project_access
from routers.projects.helpers import (
    can_read_all_task_content_async,
    check_project_accessible_async,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])

FRAME_DOWNLOAD_URL_TTL = 300
MAX_ESTIMATES_PAGE = 5000


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def serialize_run(run: AnalysisRun, *, detail: bool = True) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": run.id,
        "project_id": run.project_id,
        "name": run.name,
        "status": run.status,
        "spec_hash": run.spec_hash,
        "spec_version": run.spec_version,
        "engine_version": run.engine_version,
        "frame_hash": run.frame_hash,
        "frame_rows": run.frame_rows,
        "estimates_count": run.estimates_count,
        "error_message": run.error_message,
        "created_by": run.created_by,
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
    }
    if detail:
        out.update(
            spec=run.spec,
            normalized_spec=run.normalized_spec,
            frame_sha256=run.frame_sha256,
            frame_bytes=run.frame_bytes,
            frame_counts=run.frame_counts,
            library_versions=run.library_versions,
            lockfile_sha256=run.lockfile_sha256,
            seed=run.seed,
            fits=run.fits,
            warnings=run.warnings,
            timings=run.timings,
            frame_available=bool(run.frame_object_key),
        )
    return out


ESTIMATE_FIELDS = (
    "position", "estimand_id", "contrast_id", "estimator", "kind", "outcome", "scope",
    "scope_values", "status", "message", "estimate", "std_error", "statistic", "df",
    "p_value", "null_value", "ci_level", "ci_lower", "ci_upper", "equivalent", "tost",
    "mde", "ratio", "family", "p_adjusted", "adjustments", "n_obs", "n_clusters",
    "k_params", "conventions",
)


def serialize_estimate(row: AnalysisEstimate) -> Dict[str, Any]:
    return {name: getattr(row, name) for name in ESTIMATE_FIELDS}


def _spec_error(errors: List[str]) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "invalid_analysis_spec", "message": "The analysis spec is invalid", "errors": errors},
    )


def normalize_or_422(spec: Any) -> Dict[str, Any]:
    from analysis.spec import SpecError, normalize_spec

    try:
        return normalize_spec(spec)
    except SpecError as exc:
        raise _spec_error(exc.errors)


def engine_info() -> Dict[str, Any]:
    from analysis.expression import FUNCTIONS
    from analysis.spec import DEFAULT_CONVENTIONS, spec_schema
    from analysis.version import (
        ENGINE_VERSION,
        EXPRESSION_GRAMMAR_VERSION,
        FRAME_FORMAT_VERSION,
        SPEC_VERSION,
    )

    return {
        "engine_version": ENGINE_VERSION,
        "spec_version": SPEC_VERSION,
        "expression_grammar_version": EXPRESSION_GRAMMAR_VERSION,
        "frame_format_version": FRAME_FORMAT_VERSION,
        "estimators": ["fe_ols", "mean_rate", "paired_within"],
        "variance_estimators": ["iid", "hc1", "cluster"],
        "small_sample_corrections": ["statsmodels", "fixest", "none"],
        "inference": ["normal", "t"],
        "adjustments": ["holm", "bonferroni", "bh"],
        "measure_kinds": ["field", "expression", "gold"],
        "expression_functions": sorted(FUNCTIONS),
        "default_conventions": dict(DEFAULT_CONVENTIONS),
        "spec_schema": spec_schema(),
    }


@router.get("/api/analysis/engine")
async def get_engine(current_user=Depends(require_user)):
    """The engine's versions, catalogue and spec schema."""
    return engine_info()


@router.post("/api/analysis/specs/validate")
async def validate_analysis_spec(
    body: Dict[str, Any] = Body(...),
    current_user=Depends(require_user),
):
    """Validate ``{"spec": {...}}``: 200 with the normalized spec and its
    hash, or 422 ``invalid_analysis_spec`` with every problem found."""
    from analysis.spec import spec_hash
    from analysis.version import ENGINE_VERSION

    if "spec" not in body:
        raise _spec_error(["/: the body needs a 'spec' object"])
    normalized = normalize_or_422(body["spec"])
    return {
        "valid": True,
        "normalized_spec": normalized,
        "spec_hash": spec_hash(normalized),
        "engine_version": ENGINE_VERSION,
    }


async def create_run(db: AsyncSession, project: Project, user, spec: Any, name: Optional[str]) -> AnalysisRun:
    """Validate ``spec``, insert a pending run and queue it."""
    from analysis.spec import spec_hash
    from analysis.version import ENGINE_VERSION, SPEC_VERSION

    normalized = normalize_or_422(spec)
    run = AnalysisRun(
        project_id=project.id,
        created_by=user.id,
        name=(name or normalized["name"])[:200],
        status="pending",
        spec=spec,
        normalized_spec=normalized,
        spec_hash=spec_hash(normalized),
        spec_version=SPEC_VERSION,
        engine_version=ENGINE_VERSION,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    try:
        result = send_task_safe("tasks.run_analysis", args=[run.id])
        run.celery_task_id = getattr(result, "id", None)
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - the broker is unreachable
        logger.error("analysis run %s could not be queued: %s", run.id, exc)
        run.status = "failed"
        run.error_message = "The analysis queue is unavailable; start the run again."
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail={"code": "analysis_queue_unavailable", "message": run.error_message},
        )
    await db.refresh(run)
    return run


@router.post("/api/projects/{project_id}/analysis-runs", status_code=202)
async def start_analysis_run(
    project_id: str,
    body: Dict[str, Any] = Body(...),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Start an analysis run: ``{"spec": {...}, "name": "optional"}``."""
    if "spec" not in body:
        raise _spec_error(["/: the body needs a 'spec' object"])
    name = body.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise HTTPException(status_code=422, detail="name must be a non-empty string")
    run = await create_run(db, access.project, access.user, body["spec"], name)
    return JSONResponse(
        status_code=202,
        content=serialize_run(run, detail=True),
        headers={"Location": f"/api/analysis-runs/{run.id}"},
    )


def _build_select_runs(project_id: str, limit: int, offset: int):
    return (
        select(AnalysisRun)
        .where(AnalysisRun.project_id == project_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(limit)
        .offset(offset)
    )


@router.get("/api/projects/{project_id}/analysis-runs")
async def list_analysis_runs(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    access: ProjectAccess = Depends(require_project_access()),
    db: AsyncSession = Depends(get_async_db),
):
    total = (
        await db.execute(
            select(func.count()).select_from(AnalysisRun).where(AnalysisRun.project_id == project_id)
        )
    ).scalar_one()
    rows = (await db.execute(_build_select_runs(project_id, limit, offset))).scalars().all()
    return {"items": [serialize_run(r, detail=False) for r in rows], "total": total}


async def load_run_for_read(db: AsyncSession, user, run_id: str) -> AnalysisRun:
    """The run if the user has full read access to its project; 404
    otherwise, so run ids cannot be probed."""
    run = (await db.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    project = (await db.execute(select(Project).where(Project.id == run.project_id))).scalar_one_or_none()
    if project is None or (project.deleted_at is not None and not user.is_superadmin):
        raise HTTPException(status_code=404, detail="Analysis run not found")
    if not await check_project_accessible_async(db, user, project.id, project=project):
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return run


@router.get("/api/analysis-runs/{analysis_run_id}")
async def get_analysis_run(
    analysis_run_id: str,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    return serialize_run(await load_run_for_read(db, current_user, analysis_run_id))


def build_select_estimates(
    run_id: str,
    *,
    estimand_id: Optional[str] = None,
    contrast_id: Optional[str] = None,
    scope: Optional[str] = None,
    family: Optional[str] = None,
    status: Optional[str] = None,
    after_position: Optional[int] = None,
    limit: Optional[int] = None,
    offset: int = 0,
):
    stmt = select(AnalysisEstimate).where(AnalysisEstimate.run_id == run_id)
    if estimand_id is not None:
        stmt = stmt.where(AnalysisEstimate.estimand_id == estimand_id)
    if contrast_id is not None:
        stmt = stmt.where(AnalysisEstimate.contrast_id == contrast_id)
    if scope is not None:
        stmt = stmt.where(AnalysisEstimate.scope == scope)
    if family is not None:
        stmt = stmt.where(AnalysisEstimate.family == family)
    if status is not None:
        stmt = stmt.where(AnalysisEstimate.status == status)
    if after_position is not None:
        stmt = stmt.where(AnalysisEstimate.position > after_position)
    stmt = stmt.order_by(AnalysisEstimate.position)
    if limit is not None:
        stmt = stmt.limit(limit)
    if offset:
        stmt = stmt.offset(offset)
    return stmt


@router.get("/api/analysis-runs/{analysis_run_id}/estimates")
async def list_analysis_estimates(
    analysis_run_id: str,
    estimand_id: Optional[str] = Query(None, max_length=200),
    contrast_id: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    family: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = Query(None, max_length=32),
    limit: int = Query(1000, ge=1, le=MAX_ESTIMATES_PAGE),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    run = await load_run_for_read(db, current_user, analysis_run_id)
    filters = dict(estimand_id=estimand_id, contrast_id=contrast_id, scope=scope, family=family, status=status)
    rows = (
        await db.execute(build_select_estimates(run.id, limit=limit, offset=offset, **filters))
    ).scalars().all()
    return {"run_id": run.id, "status": run.status, "items": [serialize_estimate(r) for r in rows]}


@router.get("/api/analysis-runs/{analysis_run_id}/frame")
async def download_analysis_frame(
    analysis_run_id: str,
    request: Request,
    json: bool = Query(False),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Redirect to a short-lived download URL of the run's frame snapshot
    (``?json=1`` returns the URL in the body). 404 until the frame exists;
    403 without full read access to the project's task content."""
    run = await load_run_for_read(db, current_user, analysis_run_id)
    project = (await db.execute(select(Project).where(Project.id == run.project_id))).scalar_one()
    if not await can_read_all_task_content_async(db, current_user, project):
        raise HTTPException(
            status_code=403,
            detail="The frame needs the ORG_ADMIN or CONTRIBUTOR role on the project",
        )
    if not run.frame_object_key:
        raise HTTPException(status_code=404, detail="The frame of this run is not stored (yet)")
    from storage.object_storage import object_storage

    url = object_storage.get_download_url(
        run.frame_object_key,
        expires_in=FRAME_DOWNLOAD_URL_TTL,
        response_content_type="application/vnd.apache.parquet",
        response_content_disposition=f'attachment; filename="analysis-frame-{run.id}.parquet"',
    )
    if json:
        return {"url": url, "frame_hash": run.frame_hash, "frame_sha256": run.frame_sha256}
    return RedirectResponse(url=url, status_code=302)
