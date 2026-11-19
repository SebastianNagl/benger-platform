"""Analysis runs of variant experiments (the full API).

A project whose tasks carry ``meta.benger_variant`` can be analysed as a factorial
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
  order with their row ids, filterable by estimand, contrast, scope, family and
  status.
* ``GET /api/analysis-runs/{analysis_run_id}/frame``: the frame snapshot (Parquet) as a
  short-lived download URL; needs full read access to task content, because
  the frame carries task data paths (gold) and parsed answers.
* ``POST /api/projects/{project_id}/analysis-lookups``: store the next
  version of a named lookup table (edit rights); ``GET`` lists the project's
  tables (newest version first), ``GET .../analysis-lookups/{name}/versions/
  {version}`` returns one with its rows.

Reads need full (non-participant) access to the project; participants of an
exam never see analyses. A run whose frame reads further projects
(``inputs.projects`` and the owners of the stored lookup tables it joins)
needs, at start, the ORG_ADMIN or CONTRIBUTOR role on each of those projects
(their task content enters the frame); its frame download needs the same.
Reading such a run (detail, estimates, the run lists) needs read access to
each of those projects as well; without it the run is 404 and left out of
the lists. A purged input project no longer counts for reads, so the run
stays readable with the warning that its frame was deleted.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from celery_client import send_task_safe
from database import get_async_db
from feature_flags.deps import require_variant_experiments
from models import AnalysisEstimate, AnalysisLookupTable, AnalysisRun
from project_models import Project
from routers.projects.deps import ProjectAccess, require_project_access
from routers.projects.helpers import (
    can_read_all_task_content_async,
    check_project_accessible_async,
)

logger = logging.getLogger(__name__)

# Behind the variant_experiments flag (core 2.75): 404 feature_disabled while off.
router = APIRouter(tags=["analysis"], dependencies=[Depends(require_variant_experiments)])

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
            resolved_inputs=run.resolved_inputs,
            library_versions=run.library_versions,
            lockfile_sha256=run.lockfile_sha256,
            seed=run.seed,
            fits=run.fits,
            codes=run.codes,
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


def serialize_estimate(row: AnalysisEstimate, *, with_id: bool = True) -> Dict[str, Any]:
    """An estimate with the engine's fields and, for the full API, its row
    ``id`` (what a compliance finding's ``analysis_estimate_id`` cites). The
    v1 schema (``AnalysisEstimateOut``) has no id, so v1 passes
    ``with_id=False``."""
    out = {name: getattr(row, name) for name in ESTIMATE_FIELDS}
    return {"id": row.id, **out} if with_id else out


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
    from analysis.codes import CODE_IDENTITY_VERSION
    from analysis.coding import CODING_VERSION
    from analysis.expression import FUNCTIONS
    from analysis.list_measures import STATISTICS
    from analysis.spec import DEFAULT_CONVENTIONS, ESTIMATOR_CONVENTIONS, spec_schema
    from analysis.text_patterns import TEXT_PATTERN_FORMAT_VERSION, pattern_set_schema
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
        "estimators": [
            "fe_ols", "mean_rate", "paired_within", "logit", "mixedlm", "bradley_terry",
            "plackett_luce", "clogit_rank1", "spearman",
        ],
        "estimator_conventions": {k: dict(v) for k, v in ESTIMATOR_CONVENTIONS.items()},
        "contrast_kinds": ["linear", "ratio", "ame"],
        "joint_tests": ["contrasts", "parameters", "rows"],
        "frame_units": ["generation", "slot"],
        "variance_estimators": ["iid", "hc1", "cluster"],
        "small_sample_corrections": ["statsmodels", "fixest", "none"],
        "inference": ["normal", "t"],
        "adjustments": ["holm", "bonferroni", "bh"],
        "measure_kinds": [
            "field",
            "expression",
            "gold",
            "slot_factor",
            "slot_aggregate",
            "list",
            "text_pattern",
            "coder",
            "judge_code",
        ],
        "list_statistics": list(STATISTICS),
        "expression_functions": sorted(FUNCTIONS),
        "default_conventions": dict(DEFAULT_CONVENTIONS),
        "spec_schema": spec_schema(),
        "text_pattern_format_version": TEXT_PATTERN_FORMAT_VERSION,
        "text_pattern_set_schema": pattern_set_schema(),
        "code_identity_version": CODE_IDENTITY_VERSION,
        "coding_version": CODING_VERSION,
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


async def _content_project_or_403(db: AsyncSession, user, project_id: str, what: str, principal=None) -> Project:
    """A further project a run reads: it must exist (not deleted), the user
    must be allowed to read all of its task content and an access key that
    is limited to some projects must include it; 403 otherwise (without
    saying which failed)."""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    allowed = (
        project is not None
        and project.deleted_at is None
        and await check_project_accessible_async(db, user, project.id, project=project)
        and await can_read_all_task_content_async(db, user, project)
    )
    if allowed and principal is not None:
        from routers.v1._deps import key_may_see_project

        allowed = await key_may_see_project(db, principal, project)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "analysis_input_forbidden",
                "message": f"{what} {project_id} needs the ORG_ADMIN or CONTRIBUTOR role on that project",
            },
        )
    return project


async def check_run_inputs(
    db: AsyncSession, project: Project, user, normalized: Dict[str, Any], principal=None
) -> None:
    """Access to every further project of the spec and existence of every
    stored lookup table it names (422 ``invalid_analysis_spec`` for a
    missing table or a content hash that differs)."""
    for other in AnalysisRun.input_projects(normalized, project.id):
        await _content_project_or_403(db, user, other, "The input project", principal)
    errors: List[str] = []
    for i, lk in enumerate(normalized.get("lookups") or []):
        ref = lk.get("table")
        if not ref:
            continue
        owner = ref.get("project_id") or project.id
        row = (
            await db.execute(
                select(AnalysisLookupTable)
                .where(AnalysisLookupTable.project_id == owner)
                .where(AnalysisLookupTable.name == ref["name"])
                .where(AnalysisLookupTable.version == int(ref["version"]))
            )
        ).scalar_one_or_none()
        if row is None:
            errors.append(f"/lookups/{i}/table: {ref['name']!r} version {ref['version']} does not exist")
        elif ref.get("content_hash") and ref["content_hash"] != row.content_hash:
            errors.append(f"/lookups/{i}/table/content_hash: the stored version has {row.content_hash}")
        else:
            wanted = set(lk["keys"].values()) | set(lk["columns"].values())
            missing = sorted(wanted - set(row.columns))
            if missing:
                errors.append(f"/lookups/{i}: the table has no column(s) {', '.join(missing)}")
    if errors:
        raise _spec_error(errors)


async def create_run(
    db: AsyncSession, project: Project, user, spec: Any, name: Optional[str], principal=None
) -> AnalysisRun:
    """Validate ``spec`` and its inputs, insert a pending run and queue it.
    ``principal`` is the access key of a key-authenticated request."""
    from analysis.spec import spec_hash
    from analysis.version import ENGINE_VERSION, SPEC_VERSION

    normalized = normalize_or_422(spec)
    await check_run_inputs(db, project, user, normalized, principal)
    from routers.coding import check_spec_code_references

    problems = await check_spec_code_references(db, user, project.id, normalized)
    if problems:
        raise _spec_error(problems)
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
    request: Request,
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
    principal = getattr(request.state, "principal", None)
    run = await create_run(db, access.project, access.user, body["spec"], name, principal)
    return JSONResponse(
        status_code=202,
        content=serialize_run(run, detail=True),
        headers={"Location": f"/api/analysis-runs/{run.id}"},
    )


async def may_read_project(db: AsyncSession, user, project_id: str, principal=None) -> bool:
    """Read access to a further project of a run: a purged project (no row
    any more) no longer counts; otherwise a deleted one only for a
    superadmin, the user may access it and an access key limited to some
    projects may see it."""
    from routers.v1._deps import key_may_see_project

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        return True
    if project.deleted_at is not None and not user.is_superadmin:
        return False
    if not await check_project_accessible_async(db, user, project.id, project=project):
        return False
    return await key_may_see_project(db, principal, project)


async def hidden_runs_filter(db: AsyncSession, user, project_id: str, principal=None):
    """SQL condition that leaves out the project's runs reading a further
    project the user may not read; None when there is none."""
    spec = AnalysisRun.normalized_spec
    reads = (
        await db.execute(
            select(spec["inputs"]["projects"], spec["lookups"])
            .where(AnalysisRun.project_id == project_id)
            .where(or_(spec["inputs"]["projects"].isnot(None), spec["lookups"].isnot(None)))
        )
    ).all()
    further = dict.fromkeys(
        pid
        for projects, lookups in reads
        for pid in AnalysisRun.input_projects({"inputs": {"projects": projects}, "lookups": lookups}, project_id)
    )
    hidden = [pid for pid in further if not await may_read_project(db, user, pid, principal)]
    if not hidden:
        return None
    return ~or_(*[AnalysisRun.reads_project(pid) for pid in hidden])


def _build_select_runs(project_id: str, limit: int, offset: int, hidden=None):
    stmt = select(AnalysisRun).where(AnalysisRun.project_id == project_id)
    if hidden is not None:
        stmt = stmt.where(hidden)
    return stmt.order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc()).limit(limit).offset(offset)


@router.get("/api/projects/{project_id}/analysis-runs")
async def list_analysis_runs(
    project_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    access: ProjectAccess = Depends(require_project_access()),
    db: AsyncSession = Depends(get_async_db),
):
    hidden = await hidden_runs_filter(db, access.user, project_id, getattr(request.state, "principal", None))
    count = select(func.count()).select_from(AnalysisRun).where(AnalysisRun.project_id == project_id)
    if hidden is not None:
        count = count.where(hidden)
    total = (await db.execute(count)).scalar_one()
    rows = (await db.execute(_build_select_runs(project_id, limit, offset, hidden))).scalars().all()
    return {"items": [serialize_run(r, detail=False) for r in rows], "total": total}


async def may_read_run_inputs(db: AsyncSession, user, run: AnalysisRun, principal=None) -> bool:
    """Read access to every further project the run reads."""
    for pid in AnalysisRun.input_projects(run.normalized_spec, run.project_id):
        if not await may_read_project(db, user, pid, principal):
            return False
    return True


async def load_run_for_read(db: AsyncSession, user, run_id: str, principal=None) -> AnalysisRun:
    """The run if the user has full read access to its project and read
    access to every further project it reads; 404 otherwise, so run ids
    cannot be probed."""
    run = (await db.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    project = (await db.execute(select(Project).where(Project.id == run.project_id))).scalar_one_or_none()
    if project is None or (project.deleted_at is not None and not user.is_superadmin):
        raise HTTPException(status_code=404, detail="Analysis run not found")
    if not await check_project_accessible_async(db, user, project.id, project=project):
        raise HTTPException(status_code=404, detail="Analysis run not found")
    if not await may_read_run_inputs(db, user, run, principal):
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return run


@router.get("/api/analysis-runs/{analysis_run_id}")
async def get_analysis_run(
    analysis_run_id: str,
    request: Request,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    principal = getattr(request.state, "principal", None)
    return serialize_run(await load_run_for_read(db, current_user, analysis_run_id, principal))


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
    request: Request,
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
    run = await load_run_for_read(db, current_user, analysis_run_id, getattr(request.state, "principal", None))
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
    principal = getattr(request.state, "principal", None)
    run = await load_run_for_read(db, current_user, analysis_run_id, principal)
    project = (await db.execute(select(Project).where(Project.id == run.project_id))).scalar_one()
    if not await can_read_all_task_content_async(db, current_user, project):
        raise HTTPException(
            status_code=403,
            detail="The frame needs the ORG_ADMIN or CONTRIBUTOR role on the project",
        )
    for other in AnalysisRun.input_projects(run.normalized_spec, project.id):
        await _content_project_or_403(db, current_user, other, "The frame reads project", principal)
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


# --------------------------------------------------------------------------
# Lookup tables
# --------------------------------------------------------------------------


def serialize_lookup(row: AnalysisLookupTable, *, rows: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "version": row.version,
        "description": row.description,
        "columns": row.columns,
        "row_count": row.row_count,
        "content_hash": row.content_hash,
        "created_by": row.created_by,
        "created_at": _iso(row.created_at),
    }
    if rows:
        out["rows"] = row.rows
    return out


@router.post("/api/projects/{project_id}/analysis-lookups", status_code=201)
async def create_lookup_table(
    project_id: str,
    body: Dict[str, Any] = Body(...),
    access: ProjectAccess = Depends(require_project_access(min_role="edit")),
    db: AsyncSession = Depends(get_async_db),
):
    """Store ``{"name", "columns", "rows", "description"?}`` as the next
    version of the named table (201). Rows are lists in column order or
    objects by column name. Versions are immutable."""
    from sqlalchemy.exc import IntegrityError

    from analysis.lookups import LookupTableError, validate_table

    try:
        table = validate_table(body)
    except LookupTableError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_lookup_table", "message": "The lookup table is invalid", "errors": exc.errors},
        )
    for _ in range(3):
        latest = (
            await db.execute(
                select(func.max(AnalysisLookupTable.version))
                .where(AnalysisLookupTable.project_id == project_id)
                .where(AnalysisLookupTable.name == table["name"])
            )
        ).scalar_one()
        row = AnalysisLookupTable(
            project_id=project_id,
            name=table["name"],
            version=(latest or 0) + 1,
            description=table["description"],
            columns=table["columns"],
            rows=table["rows"],
            row_count=table["row_count"],
            content_hash=table["content_hash"],
            created_by=access.user.id,
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:  # a concurrent upload took this version
            await db.rollback()
            continue
        await db.refresh(row)
        return JSONResponse(
            status_code=201,
            content=serialize_lookup(row),
            headers={"Location": f"/api/projects/{project_id}/analysis-lookups/{row.name}/versions/{row.version}"},
        )
    raise HTTPException(status_code=409, detail="Concurrent uploads of this table; try again")


@router.get("/api/projects/{project_id}/analysis-lookups")
async def list_lookup_tables(
    project_id: str,
    name: Optional[str] = Query(None, max_length=100),
    access: ProjectAccess = Depends(require_project_access()),
    db: AsyncSession = Depends(get_async_db),
):
    """The project's lookup tables without their rows, by name and newest
    version first."""
    stmt = select(AnalysisLookupTable).where(AnalysisLookupTable.project_id == project_id)
    if name is not None:
        stmt = stmt.where(AnalysisLookupTable.name == name)
    stmt = stmt.order_by(AnalysisLookupTable.name, AnalysisLookupTable.version.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [serialize_lookup(r) for r in rows]}


@router.get("/api/projects/{project_id}/analysis-lookups/{name}/versions/{version}")
async def get_lookup_table(
    project_id: str,
    name: str,
    version: int,
    access: ProjectAccess = Depends(require_project_access()),
    db: AsyncSession = Depends(get_async_db),
):
    row = (
        await db.execute(
            select(AnalysisLookupTable)
            .where(AnalysisLookupTable.project_id == project_id)
            .where(AnalysisLookupTable.name == name)
            .where(AnalysisLookupTable.version == version)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Lookup table not found")
    return serialize_lookup(row, rows=True)
