"""``/api/v1`` analysis runs: read-only access to analyses of variant experiments.

Runs are started in the browser or through the full API
(``POST /api/projects/{project_id}/analysis-runs``); the public API reads
them back. Every route needs ``results:read`` and full (non-participant)
access to the run's project; keys get 404 for runs of projects they may not
see, so run ids cannot be probed. A run that reads further projects (its
input projects and the owners of the lookup tables it joins) also needs
read access to each of them; otherwise it is 404 and left out of the run
list. The frame snapshot is not served here
(it carries task data); use the full API's frame route with a full-data
role.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from auth_module.principal import get_principal
from database import get_async_db
from feature_flags.deps import require_variant_experiments
from models import AnalysisRun
from project_models import Project
from routers.analysis import (
    build_select_estimates,
    hidden_runs_filter,
    may_read_run_inputs,
    serialize_estimate,
    serialize_run,
)
from routers.projects.deps import ProjectAccess
from routers.projects.helpers import check_project_accessible_async
from routers.v1._deps import key_may_see_project, require_scope, v1_project_access
from routers.v1._errors import V1Error
from routers.v1._pagination import cursor_param, decode_cursor, limit_param, page
from routers.v1._schemas import (
    ERROR_RESPONSES,
    AnalysisEstimateOut,
    AnalysisRunDetailOut,
    AnalysisRunOut,
    Page,
)

# Behind the variant_experiments flag (core 2.73); an organization key counts
# for its organization.
router = APIRouter(tags=["analysis"], dependencies=[Depends(require_variant_experiments)])

_RUNS_KIND = "analysis_runs"
_ESTIMATES_KIND = "analysis_estimates"
SCOPE = "results:read"

_RUN_FIELDS = set(AnalysisRunOut.model_fields)
_DETAIL_FIELDS = set(AnalysisRunDetailOut.model_fields)


def _run_out(run: AnalysisRun, detail: bool) -> Dict[str, Any]:
    full = serialize_run(run, detail=True)
    keep = _DETAIL_FIELDS if detail else _RUN_FIELDS
    return {k: v for k, v in full.items() if k in keep}


def _not_found() -> V1Error:
    return V1Error(404, "analysis_run_not_found", "Analysis run not found")


async def _load_run(db: AsyncSession, request: Request, user, run_id: str) -> AnalysisRun:
    run = (await db.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise _not_found()
    project = (await db.execute(select(Project).where(Project.id == run.project_id))).scalar_one_or_none()
    if project is None or (project.deleted_at is not None and not user.is_superadmin):
        raise _not_found()
    principal = get_principal(request)
    if not await key_may_see_project(db, principal, project):
        raise _not_found()
    if not await check_project_accessible_async(db, user, project.id, project=project):
        raise _not_found()
    if not await may_read_run_inputs(db, user, run, principal):
        raise _not_found()
    return run


def _build_select_runs(project_id: str, after: Optional[Dict[str, Any]], limit: int, hidden=None):
    stmt = select(AnalysisRun).where(AnalysisRun.project_id == project_id)
    if hidden is not None:
        stmt = stmt.where(hidden)
    if after:
        from datetime import datetime

        created = datetime.fromisoformat(after["c"])
        stmt = stmt.where(
            or_(
                AnalysisRun.created_at < created,
                and_(AnalysisRun.created_at == created, AnalysisRun.id < after["id"]),
            )
        )
    return stmt.order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc()).limit(limit + 1)


@router.get(
    "/projects/{project_id}/analysis-runs",
    response_model=Page[AnalysisRunOut],
    responses={**ERROR_RESPONSES, 404: {"description": "Project not found"}},
    summary="List a project's analysis runs",
)
async def list_runs(
    project_id: str,
    request: Request,
    limit: int = limit_param(),
    cursor: Optional[str] = cursor_param(),
    access: ProjectAccess = Depends(v1_project_access(SCOPE, allow_participant=False)),
    db: AsyncSession = Depends(get_async_db),
):
    """Newest first."""
    position = decode_cursor(_RUNS_KIND, cursor)
    if position is not None and not (isinstance(position.get("c"), str) and isinstance(position.get("id"), str)):
        raise V1Error(400, "invalid_cursor", "The cursor is malformed")
    hidden = await hidden_runs_filter(db, access.user, project_id, get_principal(request))
    try:
        rows = (await db.execute(_build_select_runs(project_id, position, limit, hidden))).scalars().all()
    except ValueError:
        raise V1Error(400, "invalid_cursor", "The cursor is malformed")
    items, next_cursor = page(
        _RUNS_KIND, rows, limit, lambda r: {"c": r.created_at.isoformat(), "id": r.id}
    )
    return {"items": [_run_out(r, detail=False) for r in items], "next_cursor": next_cursor}


@router.get(
    "/analysis-runs/{analysis_run_id}",
    response_model=AnalysisRunDetailOut,
    responses={**ERROR_RESPONSES, 404: {"description": "Analysis run not found"}},
    summary="Read an analysis run",
)
async def get_run(
    analysis_run_id: str,
    request: Request,
    _principal=Depends(require_scope(SCOPE)),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    return _run_out(await _load_run(db, request, user, analysis_run_id), detail=True)


@router.get(
    "/analysis-runs/{analysis_run_id}/estimates",
    response_model=Page[AnalysisEstimateOut],
    responses={**ERROR_RESPONSES, 404: {"description": "Analysis run not found"}},
    summary="List an analysis run's estimates",
)
async def list_estimates(
    analysis_run_id: str,
    request: Request,
    estimand_id: Optional[str] = Query(None, max_length=200),
    contrast_id: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    family: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = Query(None, max_length=32),
    limit: int = limit_param(),
    cursor: Optional[str] = cursor_param(),
    _principal=Depends(require_scope(SCOPE)),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """In the engine's output order (``position``)."""
    run = await _load_run(db, request, user, analysis_run_id)
    position = decode_cursor(_ESTIMATES_KIND, cursor)
    after = None
    if position is not None:
        after = position.get("p")
        if not isinstance(after, int) or isinstance(after, bool):
            raise V1Error(400, "invalid_cursor", "The cursor is malformed")
    rows = (
        await db.execute(
            build_select_estimates(
                run.id,
                estimand_id=estimand_id,
                contrast_id=contrast_id,
                scope=scope,
                family=family,
                status=status,
                after_position=after,
                limit=limit + 1,
            )
        )
    ).scalars().all()
    items, next_cursor = page(_ESTIMATES_KIND, rows, limit, lambda r: {"p": r.position})
    out: List[Dict[str, Any]] = [serialize_estimate(r, with_id=False) for r in items]
    return {"items": out, "next_cursor": next_cursor}
