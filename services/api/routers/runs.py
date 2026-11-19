"""Single-run inventory endpoint.

`/api/runs` returns a paginated list of individual generation, evaluation
and analysis runs (NOT the cell-by-cell aggregates that
`/evaluations/results/*` and `/generation-tasks/*/task-status` already
serve). The frontend `/runs` page is the canonical "find a run" inventory;
clicking a row deep-links into `/evaluations/{id}`, `/generations/{id}` or
the analysis run page.

Notification routing also points here — when an `evaluation_completed` /
`llm_generation_completed` notification fires, the dropdown navigates to
the per-run detail page surfaced by this listing.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, load_only

from auth_module import User, require_user
from database import get_async_db
from feature_flags.deps import (
    feature_disabled_error,
    flag_on,
    require_variant_experiments,
)
from feature_flags.registry import VARIANT_EXPERIMENTS
from evaluation_run_models import run_evaluated_model_ids
from models import AnalysisRun, EvaluationRun, ResponseGeneration
from project_models import Project
from routers.projects.helpers import (
    check_project_accessible_async,
    get_accessible_project_ids_async,
)


router = APIRouter(prefix="/api/runs", tags=["Runs"])


class RunSummary(BaseModel):
    """Per-run summary surfaced by GET /api/runs.

    Common shape across generation + evaluation runs so the inventory page
    can render both in the same table layout. Type-specific fields use
    Optional so the response stays self-describing.
    """

    id: str
    type: Literal["generation", "evaluation", "analysis"]
    project_id: Optional[str] = None
    project_title: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    error_message: Optional[str] = None

    # Generation-specific
    model_id: Optional[str] = None
    structure_key: Optional[str] = None
    runs_requested: Optional[int] = None
    runs_completed: Optional[int] = None
    runs_failed: Optional[int] = None
    task_id: Optional[str] = None

    # Evaluation-specific. ``model_id`` is the run's label: the one model it
    # graded, or "unknown" for a run over several models (or over submitted
    # answers only); ``evaluated_model_ids`` names every model it graded.
    evaluated_model_ids: Optional[List[str]] = None
    judge_models: Optional[List[str]] = None
    samples_evaluated: Optional[int] = None
    metrics: Optional[List[str]] = None

    # Analysis-specific: the run's name, the rows of the frame it read, the
    # estimates it stored, the hash of its normalized spec and the engine
    # version (the full run is GET /api/analysis-runs/{id}).
    name: Optional[str] = None
    frame_rows: Optional[int] = None
    estimates_count: Optional[int] = None
    spec_hash: Optional[str] = None
    engine_version: Optional[str] = None


class PaginatedRunsResponse(BaseModel):
    items: List[RunSummary]
    total: int
    page: int
    page_size: int


async def _project_titles_map(db: AsyncSession, project_ids: List[str]) -> Dict[str, str]:
    """Single batched lookup for project titles — avoids N+1 over the
    response page. An empty input returns an empty map."""
    if not project_ids:
        return {}
    result = await db.execute(
        select(Project.id, Project.title).where(Project.id.in_(project_ids))
    )
    return {row.id: row.title for row in result.all()}


def _extract_judge_models(eval_metadata: Optional[Dict[str, Any]]) -> List[str]:
    """Pull judge model ids from eval_metadata. Migration 042 stores them as
    `metric_parameters.judges = [{judge_model_id, runs}, ...]`; legacy single-
    judge runs surface `judge_model` directly. Returns deduped, ordered list."""
    if not eval_metadata:
        return []
    seen: List[str] = []
    configs = eval_metadata.get("evaluation_configs") or []
    for cfg in configs:
        params = (cfg or {}).get("metric_parameters") or {}
        judges = params.get("judges")
        if isinstance(judges, list):
            for j in judges:
                jid = (j or {}).get("judge_model_id")
                if jid and jid not in seen:
                    seen.append(jid)
        elif params.get("judge_model"):
            jm = params["judge_model"]
            if jm not in seen:
                seen.append(jm)
    return seen


def _extract_metric_names(eval_metadata: Optional[Dict[str, Any]]) -> List[str]:
    """Surface the configured metric names so the inventory shows what was
    being evaluated without the user having to open each row."""
    if not eval_metadata:
        return []
    configs = eval_metadata.get("evaluation_configs") or []
    out: List[str] = []
    for cfg in configs:
        m = (cfg or {}).get("metric")
        if m and m not in out:
            out.append(m)
    return out


def _generation_to_summary(row: ResponseGeneration, project_titles: Dict[str, str]) -> RunSummary:
    return RunSummary(
        id=row.id,
        type="generation",
        project_id=row.project_id,
        project_title=project_titles.get(row.project_id or ""),
        status=row.status,
        created_at=row.created_at,
        completed_at=row.completed_at,
        created_by=row.created_by,
        error_message=row.error_message,
        model_id=row.model_id,
        structure_key=row.structure_key,
        runs_requested=row.runs_requested,
        runs_completed=row.runs_completed,
        runs_failed=row.runs_failed,
        task_id=row.task_id,
    )


def _evaluation_to_summary(row: EvaluationRun, project_titles: Dict[str, str]) -> RunSummary:
    return RunSummary(
        id=row.id,
        type="evaluation",
        project_id=row.project_id,
        project_title=project_titles.get(row.project_id or ""),
        status=row.status,
        created_at=row.created_at,
        completed_at=row.completed_at,
        created_by=row.created_by,
        error_message=row.error_message,
        model_id=row.model_id,
        evaluated_model_ids=run_evaluated_model_ids(row.model_id, row.eval_metadata),
        samples_evaluated=row.samples_evaluated,
        judge_models=_extract_judge_models(row.eval_metadata),
        metrics=_extract_metric_names(row.eval_metadata),
    )


def _analysis_to_summary(row: AnalysisRun, project_titles: Dict[str, str]) -> RunSummary:
    return RunSummary(
        id=row.id,
        type="analysis",
        project_id=row.project_id,
        project_title=project_titles.get(row.project_id or ""),
        status=row.status,
        created_at=row.created_at,
        completed_at=row.completed_at,
        created_by=row.created_by,
        error_message=row.error_message,
        name=row.name,
        frame_rows=row.frame_rows,
        estimates_count=row.estimates_count,
        spec_hash=row.spec_hash,
        engine_version=row.engine_version,
    )


# The columns an analysis row of the inventory reads: the specs, fits,
# warnings and timings of a run can be large and stay unloaded.
_ANALYSIS_SUMMARY_COLUMNS = (
    AnalysisRun.id,
    AnalysisRun.project_id,
    AnalysisRun.name,
    AnalysisRun.status,
    AnalysisRun.created_at,
    AnalysisRun.completed_at,
    AnalysisRun.created_by,
    AnalysisRun.error_message,
    AnalysisRun.frame_rows,
    AnalysisRun.estimates_count,
    AnalysisRun.spec_hash,
    AnalysisRun.engine_version,
)


class ChildGeneration(BaseModel):
    """One trial under a ResponseGeneration parent (multi-run feature)."""

    id: str
    run_index: int
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    has_response: bool = False
    response_preview: Optional[str] = None
    # What the provider client sent for this trial (migration 143): the
    # record itself is read per trial from /trials/{id}/request.
    has_request_record: bool = False
    request_sha256: Optional[str] = None
    retried: bool = False
    first_response_preview: Optional[str] = None


class TrialRequest(BaseModel):
    """What the provider client sent for one trial: the messages, response
    format, parameters and model id of the first request, and every request
    verbatim (a format retry included)."""

    id: str
    run_index: int
    request_record: Optional[Dict[str, Any]] = None
    request_sha256: Optional[str] = None


class LinkedEvaluation(BaseModel):
    """Reference to an EvaluationRun whose TaskEvaluations scored this
    generation's child rows. Surfaced on the generation-detail page so the
    user can hop directly to the eval results."""

    evaluation_id: str
    metric: Optional[str] = None
    status: Optional[str] = None
    completed_at: Optional[datetime] = None
    samples_evaluated: Optional[int] = None


class GenerationRunDetail(BaseModel):
    """Detailed shape for the /runs/generations/{id} detail page."""

    id: str
    project_id: Optional[str] = None
    project_title: Optional[str] = None
    task_id: Optional[str] = None
    model_id: Optional[str] = None
    structure_key: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    error_message: Optional[str] = None
    runs_requested: Optional[int] = None
    runs_completed: Optional[int] = None
    runs_failed: Optional[int] = None
    parameters: Optional[Dict[str, Any]] = None
    prompt_used: Optional[str] = None
    children: List[ChildGeneration] = []
    linked_evaluations: List[LinkedEvaluation] = []


async def _accessible_generation(
    db: AsyncSession, current_user: User, generation_id: str
) -> ResponseGeneration:
    """The ResponseGeneration parent, 404 when missing, 403 when its project
    is not accessible to the user."""
    parent_result = await db.execute(
        select(ResponseGeneration).where(ResponseGeneration.id == generation_id)
    )
    parent = parent_result.scalar_one_or_none()
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generation '{generation_id}' not found",
        )

    if parent.project_id and not await check_project_accessible_async(
        db, current_user, parent.project_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this project",
        )
    return parent


@router.get(
    "/generations/{generation_id}/trials/{trial_id}/request",
    response_model=TrialRequest,
    # The request record belongs to variant_experiments (core 2.69).
    dependencies=[Depends(require_variant_experiments)],
)
async def get_generation_trial_request(
    generation_id: str,
    trial_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
) -> TrialRequest:
    """What the provider client sent for one trial of a generation run."""
    from models import Generation as DBGeneration

    await _accessible_generation(db, current_user, generation_id)
    trial = (
        await db.execute(
            select(DBGeneration).where(
                DBGeneration.id == trial_id,
                DBGeneration.generation_id == generation_id,
            )
        )
    ).scalar_one_or_none()
    if not trial:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trial '{trial_id}' not found in generation '{generation_id}'",
        )
    return TrialRequest(
        id=str(trial.id),
        run_index=trial.run_index or 0,
        request_record=trial.request_record if isinstance(trial.request_record, dict) else None,
        request_sha256=trial.request_sha256,
    )


@router.get("/generations/{generation_id}", response_model=GenerationRunDetail)
async def get_generation_run(
    generation_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
) -> GenerationRunDetail:
    """Single-run detail for the /runs page deep link.

    Returns the ResponseGeneration parent plus every child Generation row
    (one per run_index trial) so the frontend can render the per-trial
    breakdown a multi-run experiment produced — including which trials
    succeeded vs failed and a content preview.
    """
    from models import Generation as DBGeneration

    parent = await _accessible_generation(db, current_user, generation_id)
    # The request record fields of the trials (variant_experiments): with the
    # flag off they keep their neutral defaults, as before the record existed.
    show_record = await flag_on(db, current_user, VARIANT_EXPERIMENTS)

    children_result = await db.execute(
        select(
            DBGeneration,
            (func.jsonb_typeof(DBGeneration.request_record) == "object").label("has_record"),
        )
        .options(defer(DBGeneration.request_record))
        .where(DBGeneration.generation_id == generation_id)
        .order_by(DBGeneration.run_index.asc())
    )
    children_with_flag = children_result.all()
    children_rows = [c for c, _ in children_with_flag]

    def _preview(content: Any) -> Optional[str]:
        if content is None:
            return None
        text = content if isinstance(content, str) else str(content)
        return text[:200] + ("…" if len(text) > 200 else "")

    children = [
        ChildGeneration(
            id=str(c.id),
            run_index=c.run_index or 0,
            status=getattr(c, "status", None),
            created_at=getattr(c, "created_at", None),
            completed_at=getattr(c, "completed_at", None),
            error_message=getattr(c, "error_message", None),
            has_response=bool(getattr(c, "response_content", None)),
            response_preview=_preview(getattr(c, "response_content", None)),
            has_request_record=show_record and bool(has_record),
            request_sha256=getattr(c, "request_sha256", None) if show_record else None,
            retried=show_record and bool(getattr(c, "retried", False)),
            first_response_preview=(
                _preview(getattr(c, "first_response_content", None)) if show_record else None
            ),
        )
        for c, has_record in children_with_flag
    ]

    titles = await _project_titles_map(
        db, [parent.project_id] if parent.project_id else []
    )

    # Linked evaluations: any EvaluationRun whose TaskEvaluation rows reference
    # one of this generation's children. Lets the user jump from a generation
    # to the evals that scored it. One row per evaluation_run; samples_evaluated
    # is the count of child task_evals that came from THIS generation.
    from models import TaskEvaluation as DBTaskEvaluation

    child_ids = [c.id for c in children_rows]
    linked: List[LinkedEvaluation] = []
    if child_ids:
        eval_id_col = DBTaskEvaluation.evaluation_id
        rows_result = await db.execute(
            select(
                eval_id_col.label("eval_id"),
                func.count(DBTaskEvaluation.id).label("n"),
            )
            .where(DBTaskEvaluation.generation_id.in_(child_ids))
            .group_by(eval_id_col)
        )
        rows = rows_result.all()
        if rows:
            from models import EvaluationRun as DBEvaluationRun

            eval_ids = [r.eval_id for r in rows if r.eval_id]
            sample_counts = {r.eval_id: int(r.n) for r in rows if r.eval_id}
            eval_rows_result = await db.execute(
                select(DBEvaluationRun).where(DBEvaluationRun.id.in_(eval_ids))
            )
            eval_rows = eval_rows_result.scalars().all()
            for er in eval_rows:
                # Pull the first evaluation_configs[*].metric as a label.
                metric_name: Optional[str] = None
                if er.eval_metadata:
                    cfgs = er.eval_metadata.get("evaluation_configs") or []
                    for c in cfgs:
                        m = (c or {}).get("metric")
                        if m:
                            metric_name = m
                            break
                linked.append(
                    LinkedEvaluation(
                        evaluation_id=er.id,
                        metric=metric_name,
                        status=er.status,
                        completed_at=er.completed_at,
                        samples_evaluated=sample_counts.get(er.id),
                    )
                )
            # Sort newest first, matching the /runs inventory ordering.
            # Use a tz-aware sentinel so completed_at (which is timestamptz)
            # doesn't trip "can't compare offset-naive and offset-aware".
            from datetime import timezone as _tz

            _epoch = datetime(1970, 1, 1, tzinfo=_tz.utc)
            linked.sort(
                key=lambda x: (x.completed_at or _epoch), reverse=True
            )

    return GenerationRunDetail(
        id=parent.id,
        project_id=parent.project_id,
        project_title=titles.get(parent.project_id or ""),
        task_id=parent.task_id,
        model_id=parent.model_id,
        structure_key=parent.structure_key,
        status=parent.status,
        created_at=parent.created_at,
        started_at=parent.started_at,
        completed_at=parent.completed_at,
        created_by=parent.created_by,
        error_message=parent.error_message,
        runs_requested=parent.runs_requested,
        runs_completed=parent.runs_completed,
        runs_failed=parent.runs_failed,
        parameters=parent.parameters if isinstance(parent.parameters, dict) else None,
        prompt_used=parent.prompt_used,
        children=children,
        linked_evaluations=linked,
    )


async def _readable_project_ids(
    db: AsyncSession, user: User, model, where: list
) -> Optional[List[str]]:
    """The projects among the runs matching ``where`` whose runs ``user``
    may list (:func:`check_project_accessible_async`, as the run detail
    pages decide), or None for a superadmin, who may list every run.

    The check runs once per project that has such runs and that the user's
    project list, their own projects or the public ones hold (every project
    the check may pass), so the filter goes into the SQL and the total and
    the pages count only the runs the user sees."""
    if user.is_superadmin:
        return None
    accessible = await get_accessible_project_ids_async(db, user) or []
    pids = (
        await db.execute(
            select(model.project_id)
            .join(Project, Project.id == model.project_id)
            .where(
                *where,
                or_(
                    Project.id.in_(accessible),
                    Project.created_by == str(user.id),
                    Project.is_public == True,  # noqa: E712
                ),
            )
            .distinct()
        )
    ).scalars().all()
    return [pid for pid in pids if await check_project_accessible_async(db, user, pid)]


async def _hidden_analysis_runs_filter(db: AsyncSession, user: User, where: list, principal=None):
    """SQL condition that leaves out the analysis runs matching ``where``
    that read a further project the user may not read (the condition the
    per-project run list applies, ``routers.analysis.hidden_runs_filter``,
    over every project of the inventory); None when there is none."""
    from routers.analysis import may_read_project

    spec = AnalysisRun.normalized_spec
    reads = (
        await db.execute(
            select(AnalysisRun.project_id, spec["inputs"]["projects"], spec["lookups"])
            .where(*where)
            .where(or_(spec["inputs"]["projects"].isnot(None), spec["lookups"].isnot(None)))
        )
    ).all()
    further = {
        pid: None
        for project_id, projects, lookups in reads
        for pid in AnalysisRun.input_projects(
            {"inputs": {"projects": projects}, "lookups": lookups}, project_id
        )
    }
    hidden = [pid for pid in further if not await may_read_project(db, user, pid, principal)]
    if not hidden:
        return None
    return ~or_(*[AnalysisRun.reads_project(pid) for pid in hidden])


@router.get("", response_model=PaginatedRunsResponse)
async def list_runs(
    request: Request,
    type: Literal["generation", "evaluation", "analysis"] = Query(
        ...,
        description="Run type to list. The types have different shapes; pick one tab at a time.",
    ),
    project_id: Optional[str] = Query(None, description="Filter to a single project"),
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status (pending, running, completed, failed)",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
) -> PaginatedRunsResponse:
    """Paginated inventory of single runs (generation, evaluation or analysis).

    The user sees only the runs of projects they can access, and analysis
    runs only when they may also read every further project the run reads
    (as on the run page). Both conditions are part of the query, so
    ``total`` and the pages count exactly the listed runs. Sorted
    newest-first by ``created_at``.
    """

    if type == "generation":
        model = ResponseGeneration
        to_summary = _generation_to_summary
    elif type == "evaluation":
        model = EvaluationRun
        to_summary = _evaluation_to_summary
    else:  # type == "analysis"
        # Analysis runs belong to variant_experiments (core 2.69).
        if not await flag_on(db, current_user, VARIANT_EXPERIMENTS, request):
            raise feature_disabled_error(VARIANT_EXPERIMENTS)
        model = AnalysisRun
        to_summary = _analysis_to_summary

    where = [model.project_id.isnot(None)]
    if project_id:
        where.append(model.project_id == project_id)
    if status_filter:
        where.append(model.status == status_filter)

    readable = await _readable_project_ids(db, current_user, model, where)
    if readable is not None:
        where.append(model.project_id.in_(readable))
    if type == "analysis":
        hidden = await _hidden_analysis_runs_filter(
            db, current_user, where, getattr(request.state, "principal", None)
        )
        if hidden is not None:
            where.append(hidden)

    condition = and_(*where)
    total = int(
        (await db.execute(select(func.count()).select_from(model).where(condition))).scalar()
        or 0
    )
    stmt = select(model).where(condition)
    if type == "analysis":
        stmt = stmt.options(load_only(*_ANALYSIS_SUMMARY_COLUMNS))
    stmt = stmt.order_by(model.created_at.desc(), model.id.desc())
    rows = (
        await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()

    titles = await _project_titles_map(db, list({r.project_id for r in rows}))
    items = [to_summary(r, titles) for r in rows]
    return PaginatedRunsResponse(items=items, total=total, page=page, page_size=page_size)
