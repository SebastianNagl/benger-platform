"""
Evaluation run endpoints (N:M field mapping).
"""

import logging
import uuid
from datetime import datetime
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


class EvaluationRunResponse(BaseModel):
    """Response model for evaluation run"""

    evaluation_id: str
    project_id: str
    status: str
    message: str
    evaluation_configs_count: int
    task_id: Optional[str] = None
    started_at: datetime


class AvailableFieldsResponse(BaseModel):
    """Response model for available fields"""

    model_response_fields: List[str]
    human_annotation_fields: List[str]
    reference_fields: List[str]
    all_fields: List[str]


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

        # Create evaluation record
        # Extract unique metrics from enabled configs as evaluation_type_ids
        evaluation_type_ids = list(set(c.metric for c in enabled_configs))

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

        evaluation = DBEvaluationRun(
            id=str(uuid.uuid4()),
            project_id=request.project_id,
            model_id=evaluated_model_id,
            evaluation_type_ids=evaluation_type_ids,
            metrics={},
            status="pending",
            created_at=datetime.now(),
            created_by=current_user.id,
            samples_evaluated=0,
            eval_metadata={
                "evaluation_type": "evaluation",
                "triggered_by": current_user.id,
                "evaluation_configs": [c.dict() for c in request.evaluation_configs],
                "batch_size": request.batch_size,
                "label_config_version": request.label_config_version,
                "evaluated_model_id": evaluated_model_id,  # Track model in metadata
                "force_rerun": request.force_rerun,
                "organization_id": organization_id,
                "task_ids": request.task_ids,
                "model_ids": request.model_ids,
            },
        )

        db.add(evaluation)
        db.commit()

        # Dispatch Celery task
        try:
            task = celery_app.send_task(
                "tasks.run_evaluation",
                args=[
                    evaluation.id,
                    request.project_id,
                    [c.dict() for c in request.evaluation_configs],
                    request.batch_size,
                    request.label_config_version,
                    not request.force_rerun,  # evaluate_missing_only: inverse of force_rerun
                    organization_id,
                    request.task_ids,
                    request.model_ids,
                ],
                queue="celery",
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
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start evaluation: {str(e)}",
        )


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
                    Generation.parsed_annotation != None,  # noqa: E711
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
        # Accept legacy "multi_field", standard "evaluation"/"llm_judge", and "immediate" (per-task annotation evals)
        evaluations = [
            e
            for e in all_evaluations
            if (e.eval_metadata or {}).get("evaluation_type") in ("multi_field", "evaluation", "llm_judge", "immediate")
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

            results.append(
                {
                    "evaluation_id": evaluation.id,
                    "model_id": evaluation.model_id,
                    "status": evaluation.status,
                    "created_at": evaluation.created_at.isoformat()
                    if evaluation.created_at
                    else None,
                    "completed_at": evaluation.completed_at.isoformat()
                    if evaluation.completed_at
                    else None,
                    "samples_evaluated": evaluation.samples_evaluated or 0,
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

        return {
            "evaluation_id": evaluation.id,
            "project_id": evaluation.project_id,
            "status": evaluation.status,
            "evaluation_configs": evaluation.eval_metadata.get("evaluation_configs", []),
            "results_by_config": parsed_results,
            "aggregated_metrics": evaluation.metrics,
            "samples_evaluated": evaluation.samples_evaluated,
            "samples_passed": evaluation.eval_metadata.get("samples_passed", 0),
            "samples_failed": evaluation.eval_metadata.get("samples_failed", 0),
            "samples_skipped": evaluation.eval_metadata.get("samples_skipped", 0),
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
