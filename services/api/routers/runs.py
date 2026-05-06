"""Single-run inventory endpoint.

`/api/runs` returns a paginated list of individual generation and evaluation
runs (NOT the cell-by-cell aggregates that `/evaluations/results/*` and
`/generation-tasks/*/task-status` already serve). The frontend `/runs` page
is the canonical "find a run" inventory; clicking a row deep-links into
`/evaluations/{id}` or `/generations/{id}`.

Notification routing also points here — when an `evaluation_completed` /
`llm_generation_completed` notification fires, the dropdown navigates to
the per-run detail page surfaced by this listing.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from models import EvaluationRun, ResponseGeneration
from project_models import Project
from routers.projects.helpers import check_project_accessible, get_org_context_from_request


router = APIRouter(prefix="/api/runs", tags=["Runs"])


class RunSummary(BaseModel):
    """Per-run summary surfaced by GET /api/runs.

    Common shape across generation + evaluation runs so the inventory page
    can render both in the same table layout. Type-specific fields use
    Optional so the response stays self-describing.
    """

    id: str
    type: Literal["generation", "evaluation"]
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

    # Evaluation-specific
    judge_models: Optional[List[str]] = None
    samples_evaluated: Optional[int] = None
    metrics: Optional[List[str]] = None


class PaginatedRunsResponse(BaseModel):
    items: List[RunSummary]
    total: int
    page: int
    page_size: int


def _project_titles_map(db: Session, project_ids: List[str]) -> Dict[str, str]:
    """Single batched lookup for project titles — avoids N+1 over the
    response page. An empty input returns an empty map."""
    if not project_ids:
        return {}
    rows = (
        db.query(Project.id, Project.title)
        .filter(Project.id.in_(project_ids))
        .all()
    )
    return {row.id: row.title for row in rows}


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
        samples_evaluated=row.samples_evaluated,
        judge_models=_extract_judge_models(row.eval_metadata),
        metrics=_extract_metric_names(row.eval_metadata),
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


@router.get("/generations/{generation_id}", response_model=GenerationRunDetail)
async def get_generation_run(
    generation_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> GenerationRunDetail:
    """Single-run detail for the /runs page deep link.

    Returns the ResponseGeneration parent plus every child Generation row
    (one per run_index trial) so the frontend can render the per-trial
    breakdown a multi-run experiment produced — including which trials
    succeeded vs failed and a content preview.
    """
    from models import Generation as DBGeneration

    parent = (
        db.query(ResponseGeneration)
        .filter(ResponseGeneration.id == generation_id)
        .first()
    )
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generation '{generation_id}' not found",
        )

    org_context = get_org_context_from_request(request)
    if parent.project_id and not check_project_accessible(
        db, current_user, parent.project_id, org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this project",
        )

    children_rows = (
        db.query(DBGeneration)
        .filter(DBGeneration.generation_id == generation_id)
        .order_by(DBGeneration.run_index.asc())
        .all()
    )

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
        )
        for c in children_rows
    ]

    titles = _project_titles_map(db, [parent.project_id] if parent.project_id else [])

    # Linked evaluations: any EvaluationRun whose TaskEvaluation rows reference
    # one of this generation's children. Lets the user jump from a generation
    # to the evals that scored it. One row per evaluation_run; samples_evaluated
    # is the count of child task_evals that came from THIS generation.
    from models import TaskEvaluation as DBTaskEvaluation
    from sqlalchemy import func as _sa_func

    child_ids = [c.id for c in children_rows]
    linked: List[LinkedEvaluation] = []
    if child_ids:
        eval_id_col = DBTaskEvaluation.evaluation_id
        rows = (
            db.query(
                eval_id_col.label("eval_id"),
                _sa_func.count(DBTaskEvaluation.id).label("n"),
            )
            .filter(DBTaskEvaluation.generation_id.in_(child_ids))
            .group_by(eval_id_col)
            .all()
        )
        if rows:
            from models import EvaluationRun as DBEvaluationRun

            eval_ids = [r.eval_id for r in rows if r.eval_id]
            sample_counts = {r.eval_id: int(r.n) for r in rows if r.eval_id}
            eval_rows = (
                db.query(DBEvaluationRun)
                .filter(DBEvaluationRun.id.in_(eval_ids))
                .all()
            )
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


@router.get("", response_model=PaginatedRunsResponse)
async def list_runs(
    request: Request,
    type: Literal["generation", "evaluation"] = Query(
        ...,
        description="Run type to list. The two types have different shapes; pick one tab at a time.",
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
    db: Session = Depends(get_db),
) -> PaginatedRunsResponse:
    """Paginated inventory of single runs (generation or evaluation).

    Accessible-project filter is applied per-row: the user only sees runs in
    projects they can access. Sorted newest-first by `created_at`.
    """
    org_context = get_org_context_from_request(request)

    if type == "generation":
        q = db.query(ResponseGeneration)
        if project_id:
            q = q.filter(ResponseGeneration.project_id == project_id)
        if status_filter:
            q = q.filter(ResponseGeneration.status == status_filter)
        q = q.order_by(ResponseGeneration.created_at.desc())
        total = q.count()
        rows = q.offset((page - 1) * page_size).limit(page_size).all()
        # Permission filter: keep only rows whose project the user can see.
        # Done after fetch since check_project_accessible takes one project
        # at a time; for typical inventory page sizes (≤200) the overhead is
        # negligible compared to the upstream query.
        accessible_ids = {
            pid for pid in {row.project_id for row in rows if row.project_id}
            if check_project_accessible(db, current_user, pid, org_context)
        }
        rows = [r for r in rows if r.project_id in accessible_ids]
        titles = _project_titles_map(db, list(accessible_ids))
        items = [_generation_to_summary(r, titles) for r in rows]
        return PaginatedRunsResponse(items=items, total=total, page=page, page_size=page_size)

    # type == "evaluation"
    q = db.query(EvaluationRun)
    if project_id:
        q = q.filter(EvaluationRun.project_id == project_id)
    if status_filter:
        q = q.filter(EvaluationRun.status == status_filter)
    q = q.order_by(EvaluationRun.created_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    accessible_ids = {
        pid for pid in {row.project_id for row in rows if row.project_id}
        if check_project_accessible(db, current_user, pid, org_context)
    }
    rows = [r for r in rows if r.project_id in accessible_ids]
    titles = _project_titles_map(db, list(accessible_ids))
    items = [_evaluation_to_summary(r, titles) for r in rows]
    return PaginatedRunsResponse(items=items, total=total, page=page, page_size=page_size)
