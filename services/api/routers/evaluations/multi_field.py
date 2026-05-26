"""
Evaluation run endpoints (N:M field mapping).
"""

import hashlib
import json as _stdjson
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.authorization import Permission, auth_service
from auth_module import User, require_user
from database import get_db
from models import EvaluationRun as DBEvaluationRun
from models import Generation as DBLLMResponse
from models import ResponseGeneration as DBResponseGeneration
from project_models import Annotation, Project, Task
from routers.evaluations.helpers import celery_app, resolve_user_org_for_project
from routers.projects.helpers import check_project_accessible, get_org_context_from_request
from services.evaluation.human_eval_runs import (
    get_or_create_human_eval_run,
    is_human_graded_metric,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============= Request/Response Models =============


class EvaluationConfigItem(BaseModel):
    """Single evaluation configuration item"""

    id: str
    metric: str
    display_name: Optional[str] = None
    metric_parameters: Optional[Dict[str, Any]] = None
    prediction_fields: List[str]
    reference_fields: List[str]
    enabled: bool = True


class EvaluationRunRequest(BaseModel):
    """Request model for running evaluation"""

    project_id: str
    evaluation_configs: List[EvaluationConfigItem]
    batch_size: int = 100
    label_config_version: Optional[str] = None
    force_rerun: bool = False  # If True, re-evaluate all; if False, only evaluate missing
    task_ids: Optional[List[str]] = None  # Filter to specific tasks (for single-cell re-evaluation)
    model_ids: Optional[List[str]] = None  # Filter to specific models (for single-cell re-evaluation)
    annotator_user_ids: Optional[List[str]] = None  # Filter annotation-side judge fan-out to specific annotators
    # (H) Top-level seed mirrors GenerationRequest.parameters.seed. When set,
    # every metric_parameters block in this run inherits the seed unless it
    # carries its own metric_parameters.seed (per-config override wins for
    # backward-compat). The worker reads this via the
    # `_top_level_seed` key the trigger threads into eval_metadata at
    # dispatch time.
    seed: Optional[int] = None


class EvaluationRunResponse(BaseModel):
    """Response model for evaluation run"""

    evaluation_id: str
    project_id: str
    status: str
    message: str
    evaluation_configs_count: int
    task_id: Optional[str] = None
    started_at: datetime
    # IDs of human-graded singleton runs that were ensured (created or
    # already existed) as part of this request. Empty when no human-graded
    # metrics were configured.
    human_eval_run_ids: List[str] = []


class AvailableFieldsResponse(BaseModel):
    """Response model for available fields"""

    model_response_fields: List[str]
    human_annotation_fields: List[str]
    reference_fields: List[str]
    all_fields: List[str]


def _resolve_scope_block(
    db: Session,
    eval_metadata: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Surface the scope filters that the run was dispatched with so the
    frontend detail view can render a "Scoped to: …" line. Resolves
    `annotator_user_ids` to display names via the same pseudonym rule
    used by /evaluated-models. Returns None when no scope filter was
    active (the common full-sweep case)."""
    if not eval_metadata:
        return None
    task_ids = eval_metadata.get("task_ids") or []
    model_ids = eval_metadata.get("model_ids") or []
    annotator_user_ids = eval_metadata.get("annotator_user_ids") or []
    if not (task_ids or model_ids or annotator_user_ids):
        return None

    annotators: List[Dict[str, str]] = []
    if annotator_user_ids:
        from models import User as DBUser

        rows = (
            db.query(DBUser.id, DBUser.username, DBUser.name, DBUser.pseudonym, DBUser.use_pseudonym)
            .filter(DBUser.id.in_(annotator_user_ids))
            .all()
        )
        # Preserve the request order so the UI list matches what the user
        # saw in the modal at dispatch time.
        by_id = {row.id: row for row in rows}
        for uid in annotator_user_ids:
            row = by_id.get(uid)
            if row is None:
                annotators.append({"user_id": uid, "display": uid[:8]})
                continue
            display = row.pseudonym if (row.use_pseudonym and row.pseudonym) else (row.name or row.username)
            annotators.append({"user_id": uid, "display": display})

    return {
        "task_ids": list(task_ids) if task_ids else [],
        "model_ids": list(model_ids) if model_ids else [],
        "annotators": annotators,
    }


# ============= Endpoints =============


@router.post("/run", response_model=EvaluationRunResponse)
async def run_evaluation(
    http_request: Request,
    request: EvaluationRunRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Run evaluation with N:M field mapping support.

    Supports multiple prediction fields evaluated against multiple reference fields
    with different metrics per combination.
    """
    try:
        # Verify project exists
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{request.project_id}' not found",
            )

        # Extract organization context for API key resolution (Issue #1180)
        organization_id = resolve_user_org_for_project(current_user, project, db)

        # Check access permissions
        org_context = get_org_context_from_request(http_request)
        if not auth_service.check_project_access(
            current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to run evaluations on this project",
            )

        # Validate evaluation configs
        if not request.evaluation_configs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No evaluation configurations provided",
            )

        enabled_configs = [c for c in request.evaluation_configs if c.enabled]
        if not enabled_configs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No enabled evaluation configurations",
            )

        # Scope-filter validation (issue #69). Reject silent no-ops where the
        # user supplies ids that don't correspond to anything on this project
        # — a silent zero-result run is worse than a 400 because it looks
        # like the worker hung. Same treatment for model_ids (existing gap).
        if request.annotator_user_ids:
            valid_annotator_ids = {
                uid for (uid,) in db.query(Annotation.completed_by)
                .join(Task, Annotation.task_id == Task.id)
                .filter(
                    Task.project_id == request.project_id,
                    Annotation.was_cancelled == False,  # noqa: E712
                )
                .distinct()
            }
            invalid_annotators = [
                uid for uid in request.annotator_user_ids if uid not in valid_annotator_ids
            ]
            if invalid_annotators:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "annotator_user_ids contains ids without annotations on "
                        f"this project: {invalid_annotators}"
                    ),
                )

        if request.model_ids:
            valid_model_ids = {
                mid for (mid,) in db.query(DBLLMResponse.model_id)
                .join(
                    DBResponseGeneration,
                    DBLLMResponse.generation_id == DBResponseGeneration.id,
                )
                .filter(DBResponseGeneration.project_id == request.project_id)
                .distinct()
            }
            invalid_models = [
                mid for mid in request.model_ids if mid not in valid_model_ids
            ]
            if invalid_models:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "model_ids contains ids without generations on "
                        f"this project: {invalid_models}"
                    ),
                )

        # Split configs into human-graded vs LLM-driven. Human-graded
        # metrics (e.g. korrektur_falloesung) have no worker; each writes
        # into a singleton ongoing EvaluationRun per (project, metric).
        # See services.evaluation.human_eval_runs.
        human_configs = [c for c in enabled_configs if is_human_graded_metric(c.metric)]
        llm_configs = [c for c in enabled_configs if not is_human_graded_metric(c.metric)]

        # Ensure the singleton run exists for every distinct human metric in
        # the request. Idempotent — re-clicking Run returns the same row.
        human_run_ids: List[str] = []
        for metric in {c.metric for c in human_configs}:
            human_run = get_or_create_human_eval_run(
                db, request.project_id, metric, current_user.id
            )
            human_run_ids.append(human_run.id)
        if human_run_ids:
            db.commit()

        # All-human request: nothing to dispatch to Celery. Return the
        # singleton's id as the evaluation_id so the frontend can navigate
        # straight to the ongoing human run.
        if not llm_configs:
            primary_human_id = human_run_ids[0]
            return EvaluationRunResponse(
                evaluation_id=primary_human_id,
                project_id=request.project_id,
                status="ongoing",
                message=(
                    "Human grading queue is ongoing "
                    f"({len(human_configs)} human-graded metric(s))"
                ),
                evaluation_configs_count=len(enabled_configs),
                task_id=None,
                started_at=datetime.now(),
                human_eval_run_ids=human_run_ids,
            )

        # Create evaluation record
        # Extract unique metrics from enabled configs as evaluation_type_ids
        evaluation_type_ids = list(set(c.metric for c in llm_configs))

        # Determine the actual model_id from generations in this project
        # Query the most common model_id from generations for this project
        # Join through ResponseGeneration which has direct project_id
        generation_model_query = (
            db.query(DBLLMResponse.model_id, func.count(DBLLMResponse.id).label("count"))
            .join(
                DBResponseGeneration,
                DBLLMResponse.generation_id == DBResponseGeneration.id,
            )
            .filter(DBResponseGeneration.project_id == request.project_id)
            .filter(DBLLMResponse.parse_status == "success")
            .group_by(DBLLMResponse.model_id)
            .order_by(func.count(DBLLMResponse.id).desc())
            .first()
        )

        # Use the most common model_id, or fallback to "unknown" if no generations exist
        evaluated_model_id = generation_model_query[0] if generation_model_query else "unknown"

        # (H) Top-level seed propagation: when the request carries a
        # top-level seed and a config doesn't already pin its own seed in
        # metric_parameters, inject the run-level seed there. Per-config
        # `metric_parameters.seed` wins for backward-compat (override of
        # override). This keeps the worker's _resolve_param tier list
        # unchanged while letting the trigger thread one seed across all
        # judges in the run.
        def _with_run_seed(cfg_dict: dict) -> dict:
            if request.seed is None:
                return cfg_dict
            params = dict(cfg_dict.get("metric_parameters") or {})
            if "seed" not in params:
                params["seed"] = request.seed
                cfg_dict = {**cfg_dict, "metric_parameters": params}
            return cfg_dict

        dispatched_configs = [_with_run_seed(c.dict()) for c in llm_configs]

        # Idempotency guard: if the same user just dispatched an
        # evaluation against this project with the SAME config payload
        # that's still in-flight, return that run's id instead of
        # spawning a duplicate. Without this, a double-click on the
        # "Run" button dispatched two chord-fan-outs that processed
        # every cell twice — at ZJS Fälle scale that silently doubled
        # the LLM bill. 30s window covers the accidental-double-click
        # case without blocking legitimate sequential re-triggers.
        #
        # Hash includes the config payload + scope filters so two
        # legitimate distinct evals on the same project (e.g. BLEU on
        # tasks 1-10 then ROUGE on tasks 11-20) don't collapse into
        # one. Uses sha1 over a stable JSON serialization; hash lands
        # in `eval_metadata.dispatch_hash` for lookup.
        from datetime import timedelta as _td
        dispatch_payload = {
            "configs": dispatched_configs,
            "task_ids": request.task_ids or [],
            "model_ids": request.model_ids or [],
            "annotator_user_ids": request.annotator_user_ids or [],
            "force_rerun": request.force_rerun,
        }
        dispatch_hash = hashlib.sha1(
            _stdjson.dumps(dispatch_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        # `datetime.now(timezone.utc)` matches the timezone-aware
        # `created_at` column (`DateTime(timezone=True)`); a naive
        # `datetime.now()` would compare local-clock-as-if-UTC and
        # silently break the 30s window on any non-UTC host.
        # Filter the hash match in Python rather than SQL: the column
        # is mapped as the generic `JSON` type (not `JSONB`), so the
        # SQLAlchemy `.astext` accessor isn't available. The 30s window
        # bounds the candidate set to a handful of rows per user/project,
        # so a Python-side scan is cheaper than adding a JSON index +
        # custom dialect SQL just for this lookup.
        recent_candidates = (
            db.query(DBEvaluationRun)
            .filter(
                DBEvaluationRun.project_id == request.project_id,
                DBEvaluationRun.created_by == current_user.id,
                DBEvaluationRun.status.in_(("pending", "running")),
                DBEvaluationRun.created_at >= datetime.now(timezone.utc) - _td(seconds=30),
            )
            .order_by(DBEvaluationRun.created_at.desc())
            .all()
        )
        recent_inflight = next(
            (
                r for r in recent_candidates
                if (r.eval_metadata or {}).get("dispatch_hash") == dispatch_hash
            ),
            None,
        )
        if recent_inflight is not None:
            return EvaluationRunResponse(
                evaluation_id=recent_inflight.id,
                project_id=request.project_id,
                status="already_running",
                message=(
                    "An evaluation by this user is already in flight on "
                    f"this project (id {recent_inflight.id}, status "
                    f"{recent_inflight.status}); returning that run instead "
                    "of dispatching a duplicate."
                ),
                evaluation_configs_count=len(enabled_configs),
                task_id=None,
                started_at=recent_inflight.created_at,
                human_eval_run_ids=human_run_ids,
            )

        evaluation = DBEvaluationRun(
            id=str(uuid.uuid4()),
            project_id=request.project_id,
            model_id=evaluated_model_id,
            evaluation_type_ids=evaluation_type_ids,
            metrics={},
            status="pending",
            created_at=datetime.now(timezone.utc),
            created_by=current_user.id,
            samples_evaluated=0,
            eval_metadata={
                "evaluation_type": "evaluation",
                "triggered_by": current_user.id,
                # Stable hash of the dispatch payload — used by the
                # idempotency lookup to distinguish two legitimately
                # different in-flight evals from a double-click on the
                # same one.
                "dispatch_hash": dispatch_hash,
                "evaluation_configs": dispatched_configs,
                "batch_size": request.batch_size,
                "label_config_version": request.label_config_version,
                "evaluated_model_id": evaluated_model_id,  # Track model in metadata
                "force_rerun": request.force_rerun,
                "organization_id": organization_id,
                "task_ids": request.task_ids,
                "model_ids": request.model_ids,
                "annotator_user_ids": request.annotator_user_ids,
                # (H) Run-level seed snapshotted on eval_metadata even when
                # it's None, for unambiguous post-hoc reproducibility.
                "_top_level_seed": request.seed,
                # Side-effect: human-graded singletons that were ensured for
                # this request, for traceability from the LLM run back to
                # the parallel ongoing human runs.
                "human_eval_run_ids": human_run_ids,
            },
        )

        db.add(evaluation)
        db.commit()

        # Dispatch Celery task. Using `kwargs=` instead of `args=` keeps the
        # call site robust to future parameter additions on
        # `tasks.run_evaluation`: a positional list silently mis-binds when
        # the worker signature is reordered, whereas kwargs are matched by
        # name. (D1: previously this was a 10-element positional list.)
        try:
            task = celery_app.send_task(
                "tasks.run_evaluation",
                kwargs={
                    "evaluation_id": evaluation.id,
                    "project_id": request.project_id,
                    "evaluation_configs": dispatched_configs,
                    "batch_size": request.batch_size,
                    "label_config_version": request.label_config_version,
                    "evaluate_missing_only": not request.force_rerun,
                    "organization_id": organization_id,
                    "task_ids": request.task_ids,
                    "model_ids": request.model_ids,
                    "annotator_user_ids": request.annotator_user_ids,
                },
                queue="evaluation",
            )

            # Update evaluation with task ID
            evaluation.eval_metadata["celery_task_id"] = task.id
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(evaluation, "eval_metadata")
            db.commit()

            logger.info(
                f"Dispatched evaluation task {task.id} for project {request.project_id}"
            )

        except Exception as e:
            logger.error(f"Failed to dispatch evaluation task: {str(e)}")
            evaluation.status = "failed"
            evaluation.error_message = f"Failed to dispatch task: {str(e)}"
            db.commit()
            raise

        return EvaluationRunResponse(
            evaluation_id=evaluation.id,
            project_id=request.project_id,
            status="started",
            message=f"Evaluation started with {len(enabled_configs)} configurations",
            evaluation_configs_count=len(enabled_configs),
            task_id=task.id if "task" in locals() else None,
            started_at=evaluation.created_at,
            human_eval_run_ids=human_run_ids,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start evaluation: {str(e)}",
        )


# ============= Cancellation =============
#
# Cancel sets `EvaluationRun.status='cancelled'` and `completed_at=now()`,
# and fails any child `EvaluationJudgeRun` still in `running`. It
# DELIBERATELY does NOT delete `task_evaluations` rows — partial results
# are preserved so a subsequent `force_rerun=False` (missing-only) trigger
# can reuse them. The new orchestrator's preload status filter includes
# `'cancelled'` so this works without extra wiring (see PR #94).
#
# The worker side is already plumbed for cancel: each cell sub-task does
# a parent-status check at entry and short-circuits if terminal; the
# `_bump_evaluation_counters` UPDATE filters out terminal parents so any
# late counter bump no-ops. So flipping status is enough — in-flight
# cells will drain within the duration of the LLM call they're holding.


class CancelEvaluationResponse(BaseModel):
    """Result of cancelling one or many evaluation runs."""

    cancelled_run_ids: List[str]
    failed_child_judge_run_count: int
    preserved_task_evaluation_count: int
    message: str


def _cancel_runs(
    db: Session,
    *,
    run_ids: List[str],
    reason: str,
) -> CancelEvaluationResponse:
    """Cancel-runs helper used by both single and bulk endpoints. SQL
    mirrors the Phase-0 prod cleanup we did pre-deploy (see PR #94
    deploy plan). Uses raw text() so the `json::jsonb` cast survives
    under Postgres 18's FIPS-strict type coercion (eval_metadata is
    typed `json`, not `jsonb`)."""
    from sqlalchemy import text as _text

    if not run_ids:
        return CancelEvaluationResponse(
            cancelled_run_ids=[],
            failed_child_judge_run_count=0,
            preserved_task_evaluation_count=0,
            message="No runs to cancel.",
        )

    cancelled = db.execute(
        _text(
            """
            UPDATE evaluation_runs
               SET status = 'cancelled',
                   completed_at = NOW(),
                   error_message = COALESCE(error_message, :reason),
                   eval_metadata = (
                     jsonb_set(
                       jsonb_set(COALESCE(eval_metadata::jsonb, '{}'::jsonb),
                                 '{cancelled_via_api}', 'true'::jsonb),
                       '{cancel_reason}', to_jsonb(CAST(:reason AS text))
                     )
                   )::json
             WHERE id = ANY(:ids)
               AND status IN ('pending', 'running')
            RETURNING id
            """
        ),
        {"ids": run_ids, "reason": reason},
    )
    actually_cancelled = [row[0] for row in cancelled.fetchall()]

    if not actually_cancelled:
        return CancelEvaluationResponse(
            cancelled_run_ids=[],
            failed_child_judge_run_count=0,
            preserved_task_evaluation_count=0,
            message="No runs in pending/running state to cancel.",
        )

    failed_judge_runs = db.execute(
        _text(
            """
            UPDATE evaluation_judge_runs
               SET status = 'failed',
                   completed_at = NOW(),
                   error_message = COALESCE(error_message, :reason)
             WHERE evaluation_id = ANY(:ids) AND status = 'running'
            """
        ),
        {"ids": actually_cancelled, "reason": "Parent EvaluationRun cancelled"},
    ).rowcount

    preserved = db.execute(
        _text(
            "SELECT count(*) FROM task_evaluations WHERE evaluation_id = ANY(:ids)"
        ),
        {"ids": actually_cancelled},
    ).scalar()

    db.commit()

    return CancelEvaluationResponse(
        cancelled_run_ids=actually_cancelled,
        failed_child_judge_run_count=failed_judge_runs or 0,
        preserved_task_evaluation_count=preserved or 0,
        message=(
            f"Cancelled {len(actually_cancelled)} run(s); "
            f"{failed_judge_runs or 0} in-flight judge_run(s) marked failed; "
            f"{preserved or 0} task_evaluation row(s) preserved for "
            "missing-only re-trigger."
        ),
    )


@router.post(
    "/run/{evaluation_id}/cancel",
    response_model=CancelEvaluationResponse,
)
async def cancel_evaluation_run(
    http_request: Request,
    evaluation_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cancel a single in-flight evaluation run. Partial scores survive."""
    evaluation = (
        db.query(DBEvaluationRun)
        .filter(DBEvaluationRun.id == evaluation_id)
        .first()
    )
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation '{evaluation_id}' not found",
        )

    project = db.query(Project).filter(Project.id == evaluation.project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent project '{evaluation.project_id}' not found",
        )

    org_context = get_org_context_from_request(http_request)
    # Single-run cancel: allow the user who triggered the run to cancel
    # it, OR anyone with project EDIT permission. PROJECT_VIEW is too
    # permissive here (an annotator could cancel an admin's 6940-cell
    # eval); PROJECT_EDIT-only would block the user-cancels-own-run
    # case. The disjunction matches the symmetry users expect: "I can
    # cancel what I started."
    is_owner = evaluation.created_by == current_user.id
    has_edit = auth_service.check_project_access(
        current_user, project, Permission.PROJECT_EDIT, db, org_context=org_context
    )
    if not (is_owner or has_edit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You don't have permission to cancel this evaluation. "
                "Only the user who triggered the run or a user with project "
                "edit permission can cancel."
            ),
        )

    if evaluation.status in ("completed", "failed", "cancelled"):
        return CancelEvaluationResponse(
            cancelled_run_ids=[],
            failed_child_judge_run_count=0,
            preserved_task_evaluation_count=0,
            message=f"Evaluation is already terminal (status='{evaluation.status}'); nothing to cancel.",
        )

    reason = f"Cancelled via API by user {current_user.id}"
    return _cancel_runs(db, run_ids=[evaluation_id], reason=reason)


@router.post(
    "/projects/{project_id}/runs/cancel-all",
    response_model=CancelEvaluationResponse,
)
async def cancel_all_project_evaluations(
    http_request: Request,
    project_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cancel every in-flight (pending or running) evaluation on a project.

    Useful when an operator wants to stop a runaway re-trigger or
    multiple stuck runs at once. Per-run rows are preserved for
    missing-only re-trigger downstream.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    org_context = get_org_context_from_request(http_request)
    # Bulk cancel is strictly PROJECT_EDIT — it nukes every in-flight
    # run on the project regardless of who triggered them, so a
    # read-only viewer must not be able to fire it.
    if not auth_service.check_project_access(
        current_user, project, Permission.PROJECT_EDIT, db, org_context=org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You don't have permission to bulk-cancel evaluations on "
                "this project (requires project edit permission)."
            ),
        )

    in_flight = (
        db.query(DBEvaluationRun.id)
        .filter(
            DBEvaluationRun.project_id == project_id,
            DBEvaluationRun.status.in_(("pending", "running")),
        )
        .all()
    )
    run_ids = [row[0] for row in in_flight]
    reason = (
        f"Bulk-cancelled via API by user {current_user.id} "
        f"(project {project_id})"
    )
    return _cancel_runs(db, run_ids=run_ids, reason=reason)


@router.get("/projects/{project_id}/available-fields", response_model=AvailableFieldsResponse)
async def get_available_fields(
    project_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get available fields for evaluation mapping in a project.

    Returns categorized fields:
    - model_response_fields: Fields from LLM generations
    - human_annotation_fields: Fields from human annotations
    - reference_fields: Ground truth/reference fields
    """
    try:
        from models import Generation

        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        # Verify user has access to the project
        org_context = get_org_context_from_request(request)
        if not auth_service.check_project_access(
            current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this project",
            )

        from label_config_parser import LabelConfigParser

        model_fields = set()
        human_fields = set()
        reference_fields = set()

        # Extract human annotation fields directly from label_config (most reliable source)
        if project.label_config:
            label_config_fields = LabelConfigParser.extract_field_names(project.label_config)
            human_fields.update(label_config_fields)

        # Also check evaluation_config for reference fields (to_name mappings)
        if project.evaluation_config:
            detected_types = project.evaluation_config.get("detected_answer_types", [])
            for answer_type in detected_types:
                to_name = answer_type.get("to_name", "")
                if to_name:
                    reference_fields.add(to_name)

        # Extract distinct model fields from ALL successful generations
        from sqlalchemy import text as sa_text
        try:
            model_field_rows = (
                db.query(
                    func.jsonb_array_elements(Generation.parsed_annotation)
                    .op('->>')(sa_text("'from_name'"))
                    .label("fn")
                )
                .join(Task, Generation.task_id == Task.id)
                .filter(
                    Task.project_id == project_id,
                    Generation.parse_status == "success",
                    Generation.parsed_annotation is not None,  # noqa: E711
                )
                .distinct()
                .all()
            )
            for row in model_field_rows:
                if row.fn:
                    model_fields.add(row.fn)
        except Exception:
            # Fallback: sample a single generation (for DBs without jsonb support)
            sample_gen = (
                db.query(Generation)
                .join(Task, Generation.task_id == Task.id)
                .filter(Task.project_id == project_id, Generation.parse_status == "success")
                .first()
            )
            if sample_gen and sample_gen.parsed_annotation:
                for result in sample_gen.parsed_annotation:
                    from_name = result.get("from_name", "")
                    if from_name:
                        model_fields.add(from_name)

        # Reference fields come from the task data (the project's source rows).
        # Skip internal/system fields that start with underscore.
        #
        # Historically we also walked an existing annotation here to derive
        # `from_name`/`to_name` values, but that propagated stale field names
        # forward when the project's `label_config` was edited (the old field
        # would keep showing up as a selectable option). The label_config is
        # the single source of truth for which annotation fields exist now —
        # we only need it for human_annotation_fields.
        sample_task = db.query(Task).filter(Task.project_id == project_id).first()
        if sample_task and sample_task.data and isinstance(sample_task.data, dict):
            for field_name, field_value in sample_task.data.items():
                if not field_name.startswith("_") and isinstance(field_value, (str, list)):
                    reference_fields.add(field_name)

        all_fields = model_fields | human_fields | reference_fields

        return AvailableFieldsResponse(
            model_response_fields=list(model_fields),
            human_annotation_fields=list(human_fields),
            reference_fields=list(reference_fields),
            all_fields=list(all_fields),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available fields: {str(e)}",
        )


@router.get("/run/results/project/{project_id}")
async def get_project_evaluation_results(
    project_id: str,
    request: Request,
    latest_only: bool = Query(True, description="Return only the most recent evaluation"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get evaluation results for a project.

    Args:
        project_id: The project ID to get results for
        latest_only: If True (default), return only the most recent evaluation.
                     If False, return all historical evaluation runs.

    Returns evaluation runs grouped by evaluation config with status and scores.
    """
    try:
        from models import TaskEvaluation

        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        # Check access permissions
        org_context = get_org_context_from_request(request)
        if not auth_service.check_project_access(
            current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view evaluations for this project",
            )

        # Get all evaluations for this project
        # Note: We identify evaluations by eval_metadata["evaluation_type"]
        # since model_id now contains the actual LLM model used
        all_evaluations = (
            db.query(DBEvaluationRun)
            .filter(DBEvaluationRun.project_id == project_id)
            .order_by(DBEvaluationRun.created_at.desc())
            .all()
        )

        # Filter for evaluation runs by checking eval_metadata
        # Accept legacy "multi_field", standard "evaluation"/"llm_judge", "immediate"
        # (per-task annotation evals), and human-graded singletons (e.g.
        # "korrektur_falloesung") which run forever as the destination for
        # corrector submissions — see services.evaluation.human_eval_runs.
        from services.evaluation.human_eval_runs import HUMAN_GRADED_METRICS
        accepted_eval_types = {
            "multi_field", "evaluation", "llm_judge", "immediate",
            *HUMAN_GRADED_METRICS,
        }
        evaluations = [
            e
            for e in all_evaluations
            if (e.eval_metadata or {}).get("evaluation_type") in accepted_eval_types
        ]

        # If latest_only=True, only return the most recent evaluation
        if latest_only and evaluations:
            evaluations = [evaluations[0]]

        results = []
        for evaluation in evaluations:
            # Parse metrics by field combination
            parsed_results = {}
            for key, value in (evaluation.metrics or {}).items():
                # Key format: config_id|pred_field|ref_field|metric_name
                # Pred_field may contain : (e.g., human:loesung), so | is the structural separator
                parts = key.split("|")
                if len(parts) >= 4:
                    config_id = parts[0]
                    pred_field = parts[1]
                    ref_field = parts[2]
                    metric_name = "|".join(parts[3:])
                elif len(parts) == 1 and ":" in key:
                    # Backward compat: old format used : as separator
                    old_parts = key.split(":")
                    if len(old_parts) >= 4:
                        config_id = old_parts[0]
                        pred_field = old_parts[1]
                        ref_field = old_parts[2]
                        metric_name = ":".join(old_parts[3:])
                    else:
                        continue
                else:
                    continue

                if config_id not in parsed_results:
                    parsed_results[config_id] = {"field_results": [], "aggregate_score": None}

                # Find or create field result entry
                combo_key = f"{pred_field}_vs_{ref_field}"
                existing = next(
                    (
                        r
                        for r in parsed_results[config_id]["field_results"]
                        if r.get("combo_key") == combo_key
                    ),
                    None,
                )
                if not existing:
                    existing = {
                        "combo_key": combo_key,
                        "prediction_field": pred_field,
                        "reference_field": ref_field,
                        "scores": {},
                    }
                    parsed_results[config_id]["field_results"].append(existing)
                existing["scores"][metric_name] = value

            # Calculate aggregate scores per config
            for config_id, config_data in parsed_results.items():
                if config_data["field_results"]:
                    all_scores = []
                    for fr in config_data["field_results"]:
                        for score_name, score_val in fr["scores"].items():
                            if isinstance(score_val, (int, float)):
                                all_scores.append(score_val)
                    if all_scores:
                        config_data["aggregate_score"] = sum(all_scores) / len(all_scores)

            # Get sample results count for this evaluation
            sample_results_count = 0
            try:
                sample_results_count = (
                    db.query(TaskEvaluation)
                    .filter(TaskEvaluation.evaluation_id == evaluation.id)
                    .count()
                )
            except Exception:
                pass  # Table might not exist in some configurations

            eval_configs = (
                (evaluation.eval_metadata.get("evaluation_configs")
                 or evaluation.eval_metadata.get("configs", []))
                if evaluation.eval_metadata
                else []
            )

            # Mark the singleton human-graded runs so the frontend can render
            # an "ongoing" badge instead of "completed". Keep `status` at the
            # raw DB value so existing filters (e.g. `status === 'completed'`
            # in EvaluationResults.tsx) still see the run.
            eval_type = (evaluation.eval_metadata or {}).get("evaluation_type")
            is_human_ongoing = (
                evaluation.model_id == "human" and eval_type in HUMAN_GRADED_METRICS
            )

            results.append(
                {
                    "evaluation_id": evaluation.id,
                    "model_id": evaluation.model_id,
                    "status": evaluation.status,
                    "is_human_ongoing": is_human_ongoing,
                    "created_at": evaluation.created_at.isoformat()
                    if evaluation.created_at
                    else None,
                    "completed_at": evaluation.completed_at.isoformat()
                    if evaluation.completed_at
                    else None,
                    # Human singleton runs don't maintain samples_evaluated
                    # (see services.evaluation.human_eval_runs); fall back to
                    # the live row-count so the dropdown badge reflects the
                    # actual number of grades collected.
                    "samples_evaluated": (
                        sample_results_count
                        if is_human_ongoing
                        else (evaluation.samples_evaluated or 0)
                    ),
                    "sample_results_count": sample_results_count,
                    "error_message": evaluation.error_message,
                    "evaluation_configs": eval_configs,
                    "results_by_config": parsed_results,
                    "progress": {
                        "samples_passed": evaluation.eval_metadata.get("samples_passed", 0)
                        if evaluation.eval_metadata
                        else 0,
                        "samples_failed": evaluation.eval_metadata.get("samples_failed", 0)
                        if evaluation.eval_metadata
                        else 0,
                        "samples_skipped": evaluation.eval_metadata.get("samples_skipped", 0)
                        if evaluation.eval_metadata
                        else 0,
                    },
                }
            )

        return {
            "project_id": project_id,
            "evaluations": results,
            "total_count": len(results),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get project evaluation results: {str(e)}",
        )


@router.get("/run/results/{evaluation_id}")
async def get_evaluation_run_results(
    evaluation_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get detailed evaluation results.

    Returns per-field-combination scores grouped by evaluation config.
    """
    try:
        evaluation = db.query(DBEvaluationRun).filter(DBEvaluationRun.id == evaluation_id).first()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        # Check project access
        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, evaluation.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this evaluation's project",
            )

        # Verify it's an evaluation run (accept both legacy "multi_field" and new "evaluation")
        if (
            not evaluation.eval_metadata
            or evaluation.eval_metadata.get("evaluation_type") not in ("multi_field", "evaluation")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This is not an evaluation run",
            )

        # Parse metrics by field combination
        parsed_results = {}
        for key, value in (evaluation.metrics or {}).items():
            # Key format: config_id|pred_field|ref_field|metric_name
            parts = key.split("|")
            if len(parts) >= 4:
                config_id = parts[0]
                pred_field = parts[1]
                ref_field = parts[2]
                metric_name = "|".join(parts[3:])
            elif len(parts) == 1 and ":" in key:
                # Backward compat: old format used : as separator
                old_parts = key.split(":")
                if len(old_parts) >= 4:
                    config_id = old_parts[0]
                    pred_field = old_parts[1]
                    ref_field = old_parts[2]
                    metric_name = ":".join(old_parts[3:])
                else:
                    continue
            else:
                continue
            if config_id not in parsed_results:
                parsed_results[config_id] = {}
            combo_key = f"{pred_field}_vs_{ref_field}"
            if combo_key not in parsed_results[config_id]:
                parsed_results[config_id][combo_key] = {}
            parsed_results[config_id][combo_key][metric_name] = value

        # Enrich eval_metadata.judges_by_config with SQL-computed sample
        # counts so older evals (whose worker didn't write samples_evaluated
        # to the blob) still show real numbers in PerRunBreakdown. Skip the
        # query entirely when there's no judges_by_config to enrich — keeps
        # this branch out of the path for non-judge evals (and keeps mock-
        # heavy unit tests from having to wire a third query chain).
        eval_metadata = dict(evaluation.eval_metadata or {})
        judges_by_cfg = eval_metadata.get("judges_by_config")
        per_judge_counts: Dict[str, int] = {}
        if isinstance(judges_by_cfg, dict) and judges_by_cfg:
            from models import EvaluationJudgeRun, TaskEvaluation
            from sqlalchemy import func as _sa_func

            try:
                rows = (
                    db.query(
                        EvaluationJudgeRun.id,
                        _sa_func.count(TaskEvaluation.id).label("n"),
                    )
                    .outerjoin(TaskEvaluation, TaskEvaluation.judge_run_id == EvaluationJudgeRun.id)
                    .filter(EvaluationJudgeRun.evaluation_id == evaluation.id)
                    .group_by(EvaluationJudgeRun.id)
                    .all()
                )
                per_judge_counts = {jr_id: int(n) for jr_id, n in rows}
            except Exception:
                # Non-fatal: the UI shows "—" if the lookup failed.
                per_judge_counts = {}

        if isinstance(judges_by_cfg, dict) and per_judge_counts:
            patched_jbc: Dict[str, list] = {}
            for cid, entries in judges_by_cfg.items():
                if not isinstance(entries, list):
                    patched_jbc[cid] = entries
                    continue
                patched: list = []
                for entry in entries:
                    if not isinstance(entry, dict):
                        patched.append(entry)
                        continue
                    jr_id = entry.get("judge_run_id")
                    sql_count = per_judge_counts.get(jr_id) if jr_id else None
                    # Prefer the worker-time count when present; fall back to SQL.
                    if entry.get("samples_evaluated") in (None, 0) and sql_count is not None:
                        patched.append({**entry, "samples_evaluated": sql_count})
                    else:
                        patched.append(entry)
                patched_jbc[cid] = patched
            eval_metadata["judges_by_config"] = patched_jbc

        # Defensive coercion: has_sample_results / model_id are accessed via
        # getattr because not every legacy EvaluationRun row carries them, and
        # serializer must produce JSON-safe values (bool / str / None) — never
        # raw ORM objects.
        _has_samples = getattr(evaluation, "has_sample_results", False)
        _model_id = getattr(evaluation, "model_id", None)
        return {
            "evaluation_id": evaluation.id,
            "project_id": evaluation.project_id,
            "model_id": _model_id if isinstance(_model_id, (str, type(None))) else None,
            "status": evaluation.status,
            "evaluation_configs": evaluation.eval_metadata.get("evaluation_configs", []),
            "results_by_config": parsed_results,
            "aggregated_metrics": evaluation.metrics,
            "metrics": evaluation.metrics,
            "samples_evaluated": evaluation.samples_evaluated,
            "samples_passed": evaluation.eval_metadata.get("samples_passed", 0),
            "samples_failed": evaluation.eval_metadata.get("samples_failed", 0),
            "samples_skipped": evaluation.eval_metadata.get("samples_skipped", 0),
            "has_sample_results": bool(_has_samples) if isinstance(_has_samples, (bool, int)) else False,
            # Multi-run / multi-judge bookkeeping (migration 042). The frontend
            # uses `eval_metadata.judges_by_config` to render the Judges & Läufe
            # tab without an extra round-trip. Surfacing the whole eval_metadata
            # also unblocks any future overlay (judge_seeds, custom flags)
            # without a schema change.
            "eval_metadata": eval_metadata,
            # Scope filters resolved to display-friendly form (issue #69).
            # null when the run was a full sweep; otherwise carries the
            # task_ids / model_ids / annotator user_ids+displays that the
            # modal narrowed the run to.
            "scope": _resolve_scope_block(db, eval_metadata),
            "created_at": evaluation.created_at,
            "completed_at": evaluation.completed_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evaluation results: {str(e)}",
        )
