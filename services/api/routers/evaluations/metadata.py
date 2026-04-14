"""
Evaluation metadata, statistics, and significance endpoints.
"""

import logging
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
from project_models import Annotation, Project, Task
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

logger = logging.getLogger(__name__)

router = APIRouter()


# ============= Statistics Models =============


class StatisticsRequest(BaseModel):
    """Request model for comprehensive statistics computation"""

    metrics: List[str]
    aggregation: str = "model"  # sample, model, field, overall
    methods: List[str] = ["ci"]  # ci, ttest, bootstrap, cohens_d, cliffs_delta, correlation
    compare_models: Optional[List[str]] = None


class MetricStatistics(BaseModel):
    """Statistics for a single metric"""

    mean: float
    median: Optional[float] = None
    std: float
    se: Optional[float] = None  # Standard Error = std / sqrt(n)
    min: Optional[float] = None
    max: Optional[float] = None
    ci_lower: float
    ci_upper: float
    n: int


class PairwiseComparison(BaseModel):
    """Pairwise comparison between two models"""

    model_a: str
    model_b: str
    metric: str
    ttest_p: Optional[float] = None
    ttest_significant: Optional[bool] = None
    bootstrap_p: Optional[float] = None
    bootstrap_significant: Optional[bool] = None
    cohens_d: Optional[float] = None
    cohens_d_interpretation: Optional[str] = None
    cliffs_delta: Optional[float] = None
    cliffs_delta_interpretation: Optional[str] = None
    significant: bool = False


class ModelStatistics(BaseModel):
    """Statistics for a single model across metrics"""

    model_id: str
    model_name: Optional[str] = None
    metrics: Dict[str, MetricStatistics]
    sample_count: int


class FieldStatistics(BaseModel):
    """Statistics for a single field across metrics"""

    field_name: str
    metrics: Dict[str, MetricStatistics]
    sample_count: int


class RawScore(BaseModel):
    """Raw score for a single sample (for box plots)"""

    task_id: Optional[str] = None
    model_id: str
    field_name: Optional[str] = None
    metric: str
    value: float


class StatisticsResponse(BaseModel):
    """Response model for statistics computation"""

    aggregation: str
    metrics: Dict[str, MetricStatistics]
    # Aggregation-specific data
    by_model: Optional[Dict[str, ModelStatistics]] = None  # For 'model' aggregation
    by_field: Optional[Dict[str, FieldStatistics]] = None  # For 'field' aggregation
    raw_scores: Optional[List[RawScore]] = None  # For 'sample' aggregation (box plots)
    # Comparisons and correlations
    pairwise_comparisons: Optional[List[PairwiseComparison]] = None
    correlations: Optional[Dict[str, Dict[str, Optional[float]]]] = None
    # Warnings about data quality or limitations
    warnings: Optional[List[str]] = None


# ============= Endpoints =============


@router.get("/projects/{project_id}/evaluated-models")
async def get_evaluated_models(
    request: Request,
    project_id: str,
    include_configured: bool = Query(
        False, description="Include all configured models from generation_config"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
) -> List[dict]:
    """
    Get all models that have been evaluated for this project.
    Returns list of models with: model_id, model_name, provider, evaluation_count,
    total_samples, last_evaluated, average_score, ci_lower, ci_upper.

    When include_configured=True, also includes models configured in generation_config
    that may not have results yet, with is_configured, has_generations, has_results flags.
    """
    try:
        from models import TaskEvaluation, Generation
        from routers.leaderboards import (
            calculate_confidence_interval,
            detect_provider_from_model_id,
        )

        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get configured models from generation_config
        configured_models = set()
        if include_configured and project.generation_config:
            selected_config = project.generation_config.get("selected_configuration", {})
            configured_models = set(selected_config.get("models", []))

        # Query all generations for tasks in this project
        generations_query = (
            db.query(Generation.model_id)
            .join(Task, Generation.task_id == Task.id)
            .filter(Task.project_id == project_id)
            .filter(Generation.parse_status == "success")
            .distinct()
        )

        models_with_generations = {g.model_id for g in generations_query.all()}

        # Get models with actual evaluation results from TaskEvaluation
        # This correctly handles evaluations where Evaluation.model_id = "unknown"
        # by tracing through generation_id to get the real model_id
        models_from_sample_results = (
            db.query(Generation.model_id)
            .distinct()
            .join(
                TaskEvaluation,
                TaskEvaluation.generation_id == Generation.id,
            )
            .join(
                DBEvaluationRun,
                TaskEvaluation.evaluation_id == DBEvaluationRun.id,
            )
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status == "completed",
            )
        )
        models_with_evaluation_results = {m[0] for m in models_from_sample_results.all()}

        # Also include model IDs from direct evaluations
        # Filter out "unknown" as it's a legacy artifact
        models_from_evaluations = (
            db.query(DBEvaluationRun.model_id)
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status == "completed",
                DBEvaluationRun.model_id != "unknown",  # Filter out legacy artifact
            )
            .distinct()
        )
        models_with_evaluations = {e.model_id for e in models_from_evaluations.all()}

        # Discover annotator-based models from annotation evaluations
        from models import User as DBUser
        annotator_models = {}  # synthetic_id -> display_name
        annotation_evals = (
            db.query(DBUser.username)
            .distinct()
            .join(Annotation, Annotation.completed_by == DBUser.id)
            .join(TaskEvaluation, TaskEvaluation.annotation_id == Annotation.id)
            .join(DBEvaluationRun, TaskEvaluation.evaluation_id == DBEvaluationRun.id)
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status == "completed",
                TaskEvaluation.generation_id == None,  # noqa: E711
            )
        )
        for (username,) in annotation_evals.all():
            synthetic_id = f"annotator:{username}"
            annotator_models[synthetic_id] = f"Annotator: {username}"

        # Combine all model sources when include_configured is True
        # Include models from sample results and direct evaluations
        if include_configured:
            all_model_ids = list(
                configured_models
                | models_with_generations
                | models_with_evaluations
                | models_with_evaluation_results
            )
        else:
            all_model_ids = list(
                models_with_generations | models_with_evaluations | models_with_evaluation_results
            )

        # Add annotator synthetic models
        all_model_ids = all_model_ids + list(annotator_models.keys())

        # Filter out artifacts: "unknown" (legacy) and "immediate" (replaced by annotator entries)
        all_model_ids = [m for m in all_model_ids if m not in ("unknown", "immediate")]

        if not all_model_ids:
            return []

        # Get evaluations for these models in this project
        evaluations = (
            db.query(DBEvaluationRun)
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.model_id.in_(all_model_ids),
                DBEvaluationRun.status == "completed",
            )
            .all()
        )

        # Build evaluation data map
        eval_data = {}
        for model_id in all_model_ids:
            eval_data[model_id] = {
                "evaluation_count": 0,
                "total_samples": 0,
                "last_evaluated": None,
                "all_scores": [],
            }

        # Process evaluations
        for eval in evaluations:
            model_id = eval.model_id
            if model_id not in eval_data:
                continue

            eval_data[model_id]["evaluation_count"] += 1
            eval_data[model_id]["total_samples"] += eval.samples_evaluated or 0

            # Track last evaluated
            if eval.completed_at:
                last = eval_data[model_id]["last_evaluated"]
                if last is None or eval.completed_at > last:
                    eval_data[model_id]["last_evaluated"] = eval.completed_at

            # Collect all metric scores for CI calculation
            if eval.metrics:
                for metric_name, value in eval.metrics.items():
                    if value is not None and isinstance(value, (int, float)):
                        eval_data[model_id]["all_scores"].append(float(value))

        # Build result list
        results = []
        for model_id in all_model_ids:
            data = eval_data[model_id]

            # Calculate average score
            if data["all_scores"]:
                average_score = sum(data["all_scores"]) / len(data["all_scores"])
            else:
                average_score = None if include_configured else 0.0

            # Calculate confidence interval
            ci_lower, ci_upper, _ = calculate_confidence_interval(data["all_scores"])

            # Detect provider
            provider = detect_provider_from_model_id(model_id)

            # Use display name for annotator models
            is_annotator = model_id in annotator_models
            display_name = annotator_models.get(model_id, model_id)

            result = {
                "model_id": model_id,
                "model_name": display_name,
                "provider": "Annotator" if is_annotator else provider,
                "evaluation_count": data["evaluation_count"] or (1 if is_annotator else 0),
                "total_samples": data["total_samples"],
                "last_evaluated": (
                    data["last_evaluated"].isoformat() if data["last_evaluated"] else None
                ),
                "average_score": round(average_score, 4) if average_score is not None else None,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
            }

            # Add status flags when include_configured is True
            if include_configured:
                result["is_configured"] = model_id in configured_models
                result["has_generations"] = model_id in models_with_generations
                # Check both direct evaluations and sample-level evaluation results
                result["has_results"] = (
                    data["evaluation_count"] > 0
                    or model_id in models_with_evaluation_results
                    or is_annotator
                )

            results.append(result)

        # Sort: configured models first, then by average score descending
        if include_configured:
            results.sort(
                key=lambda x: (
                    not x.get("is_configured", False),  # Configured first
                    not x.get("has_results", False),  # With results first
                    -(x["average_score"] or 0),  # Higher score first
                )
            )
        else:
            results.sort(key=lambda x: x["average_score"] or 0, reverse=True)

        return results

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evaluated models: {str(e)}",
        )


@router.get("/projects/{project_id}/configured-methods")
async def get_configured_methods(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
) -> dict:
    """
    Get all configured evaluation methods for this project with their result status.
    Returns methods from evaluation_config.selected_methods with flags indicating
    whether each method has actual results.
    """
    try:
        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        if not project.evaluation_config:
            return {"project_id": project_id, "fields": []}

        eval_config = project.evaluation_config
        selected_methods = eval_config.get("selected_methods", {})
        available_methods = eval_config.get("available_methods", {})

        if not selected_methods:
            return {"project_id": project_id, "fields": []}

        # Get all completed evaluations for this project to check results
        evaluations = (
            db.query(DBEvaluationRun)
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status == "completed",
            )
            .all()
        )

        # Build method result map: method_name -> {count, last_run}
        method_results = {}
        for eval in evaluations:
            if eval.metrics:
                for metric_name in eval.metrics.keys():
                    if metric_name not in method_results:
                        method_results[metric_name] = {"count": 0, "last_run": None}
                    method_results[metric_name]["count"] += 1
                    if eval.completed_at and (
                        method_results[metric_name]["last_run"] is None
                        or eval.completed_at > method_results[metric_name]["last_run"]
                    ):
                        method_results[metric_name]["last_run"] = eval.completed_at

        # Build response
        fields = []
        for field_name, selections in selected_methods.items():
            field_info = available_methods.get(field_name, {})

            # Process automated methods
            automated_methods = []
            for method in selections.get("automated", []):
                method_name = method if isinstance(method, str) else method.get("name", "")
                params = method.get("parameters") if isinstance(method, dict) else None

                method_type = "llm-judge" if method_name.startswith("llm_judge_") else "automated"
                result_info = method_results.get(method_name, {"count": 0, "last_run": None})

                automated_methods.append(
                    {
                        "method_name": method_name,
                        "method_type": method_type,
                        "display_name": method_name.replace("_", " ").title(),
                        "is_configured": True,
                        "has_results": result_info["count"] > 0,
                        "result_count": result_info["count"],
                        "last_run": (
                            result_info["last_run"].isoformat() if result_info["last_run"] else None
                        ),
                        "parameters": params,
                        "field_mapping": selections.get("field_mapping"),
                    }
                )

            # Process human methods
            human_methods = []
            for method in selections.get("human", []):
                method_name = method if isinstance(method, str) else method.get("name", "")
                result_info = method_results.get(method_name, {"count": 0, "last_run": None})

                human_methods.append(
                    {
                        "method_name": method_name,
                        "method_type": "human",
                        "display_name": method_name.replace("_", " ").title(),
                        "is_configured": True,
                        "has_results": result_info["count"] > 0,
                        "result_count": result_info["count"],
                        "last_run": (
                            result_info["last_run"].isoformat() if result_info["last_run"] else None
                        ),
                    }
                )

            fields.append(
                {
                    "field_name": field_name,
                    "field_type": field_info.get("type", "unknown"),
                    "to_name": field_info.get("to_name", ""),
                    "automated_methods": automated_methods,
                    "human_methods": human_methods,
                }
            )

        return {"project_id": project_id, "fields": fields}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get configured methods: {str(e)}",
        )


@router.get("/projects/{project_id}/evaluation-history")
async def get_evaluation_history(
    request: Request,
    project_id: str,
    model_ids: List[str] = Query(..., description="List of model IDs to get history for"),
    metric: str = Query(..., description="Metric name to get history for"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
) -> dict:
    """
    Get historical evaluation data for trend charts.
    Returns time-series data with values and confidence intervals.
    """
    try:
        pass

        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        # Build date filters
        date_filters = []
        if start_date:
            date_filters.append(DBEvaluationRun.created_at >= datetime.fromisoformat(start_date))
        if end_date:
            date_filters.append(DBEvaluationRun.created_at <= datetime.fromisoformat(end_date))

        # Query evaluations for the specified models
        evaluations = (
            db.query(DBEvaluationRun)
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.model_id.in_(model_ids),
                DBEvaluationRun.status == "completed",
                *date_filters,
            )
            .order_by(DBEvaluationRun.created_at)
            .all()
        )

        # Build time-series data
        data_points = []
        for eval in evaluations:
            if not eval.metrics or metric not in eval.metrics:
                continue

            value = eval.metrics.get(metric)
            if value is None or not isinstance(value, (int, float)):
                continue

            # Get CI from metadata if available
            ci_lower, ci_upper = None, None
            if eval.eval_metadata and "confidence_intervals" in eval.eval_metadata:
                ci_data = eval.eval_metadata["confidence_intervals"].get(metric, {})
                ci_lower = ci_data.get("lower")
                ci_upper = ci_data.get("upper")

            data_points.append(
                {
                    "date": eval.created_at.isoformat() if eval.created_at else None,
                    "model_id": eval.model_id,
                    "value": round(float(value), 4),
                    "ci_lower": round(ci_lower, 4) if ci_lower else None,
                    "ci_upper": round(ci_upper, 4) if ci_upper else None,
                    "sample_count": eval.samples_evaluated or 0,
                }
            )

        return {
            "metric": metric,
            "data": data_points,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evaluation history: {str(e)}",
        )


@router.get("/significance/{project_id}")
async def get_significance_tests(
    request: Request,
    project_id: str,
    model_ids: List[str] = Query(..., description="List of model IDs to compare"),
    metrics: List[str] = Query(..., description="List of metrics to compare"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
) -> dict:
    """
    Get pairwise significance tests between models.
    Uses Welch's t-test for statistical comparison.

    Supports both:
    - Direct evaluations (Evaluation.model_id = actual model)
    - Multi-field evaluations (Evaluation.model_id = "unknown", real model in Generation)
    """
    try:
        from models import TaskEvaluation, Generation
        from routers.leaderboards import STATS_AVAILABLE, calculate_significance

        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        if not STATS_AVAILABLE:
            return {
                "comparisons": [],
                "message": "Statistical testing not available (scipy not installed)",
            }

        # Organize scores by model and metric
        model_metric_scores: Dict[str, Dict[str, List[float]]] = {}
        for model_id in model_ids:
            model_metric_scores[model_id] = {metric: [] for metric in metrics}

        # Query scores from TaskEvaluation (handles N:M field evaluations)
        # This joins through Generation to get the actual model_id
        sample_results = (
            db.query(
                Generation.model_id,
                TaskEvaluation.metrics,
            )
            .join(
                TaskEvaluation,
                TaskEvaluation.generation_id == Generation.id,
            )
            .join(
                DBEvaluationRun,
                TaskEvaluation.evaluation_id == DBEvaluationRun.id,
            )
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status == "completed",
                Generation.model_id.in_(model_ids),
            )
            .all()
        )

        # Collect scores from sample results
        for result in sample_results:
            model_id = result.model_id
            if model_id not in model_metric_scores:
                continue
            if not result.metrics:
                continue

            for metric in metrics:
                if metric in result.metrics:
                    value = result.metrics[metric]
                    if value is not None and isinstance(value, (int, float)):
                        model_metric_scores[model_id][metric].append(float(value))

        # Also check direct evaluations for backwards compatibility
        direct_evaluations = (
            db.query(DBEvaluationRun)
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.model_id.in_(model_ids),
                DBEvaluationRun.model_id != "unknown",  # Exclude legacy artifacts
                DBEvaluationRun.status == "completed",
            )
            .all()
        )

        for eval in direct_evaluations:
            if eval.model_id not in model_metric_scores:
                continue
            if not eval.metrics:
                continue

            for metric in metrics:
                if metric in eval.metrics:
                    value = eval.metrics[metric]
                    if value is not None and isinstance(value, (int, float)):
                        model_metric_scores[eval.model_id][metric].append(float(value))

        # Perform pairwise comparisons
        comparisons = []
        for i, model_a in enumerate(model_ids):
            for model_b in model_ids[i + 1 :]:
                for metric in metrics:
                    scores_a = model_metric_scores[model_a][metric]
                    scores_b = model_metric_scores[model_b][metric]

                    # Need at least 2 scores per model for comparison
                    if len(scores_a) < 2 or len(scores_b) < 2:
                        comparisons.append(
                            {
                                "model_a": model_a,
                                "model_b": model_b,
                                "metric": metric,
                                "p_value": 1.0,
                                "significant": False,
                                "effect_size": 0.0,
                                "stars": "",
                            }
                        )
                        continue

                    # Calculate significance
                    result = calculate_significance(scores_a, scores_b)

                    comparisons.append(
                        {
                            "model_a": model_a,
                            "model_b": model_b,
                            "metric": metric,
                            "p_value": result["p_value"],
                            "significant": result["significant"],
                            "effect_size": result["effect_size"],
                            "stars": result["stars"],
                        }
                    )

        return {"comparisons": comparisons}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get significance tests: {str(e)}",
        )


@router.post("/projects/{project_id}/statistics", response_model=StatisticsResponse)
async def compute_project_statistics(
    http_request: Request,
    project_id: str,
    request: StatisticsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """
    Compute comprehensive statistics for evaluation results.

    Supports multiple aggregation levels:
    - 'sample': Per-sample raw scores (for box plots and distributions)
    - 'model': Statistics aggregated per model (default, for model comparison)
    - 'field': Statistics aggregated per evaluated field
    - 'overall': Single aggregate across all data

    Statistical methods: CI, t-test, bootstrap, effect sizes, correlation.
    """
    try:
        # Import statistics functions from leaderboards (scipy-based)
        # Additional statistical functions using numpy/scipy
        import numpy as np

        from models import TaskEvaluation, Generation
        from routers.leaderboards import (
            STATS_AVAILABLE,
            calculate_confidence_interval,
            calculate_significance,
        )

        if STATS_AVAILABLE:
            from scipy import stats as scipy_stats

        def compute_cohens_d(values_a: List[float], values_b: List[float]) -> dict:
            """Compute Cohen's d effect size"""
            if not STATS_AVAILABLE or len(values_a) < 2 or len(values_b) < 2:
                return {"cohens_d": None, "interpretation": None}

            mean_diff = np.mean(values_a) - np.mean(values_b)
            pooled_std = np.sqrt(
                (
                    (len(values_a) - 1) * np.var(values_a, ddof=1)
                    + (len(values_b) - 1) * np.var(values_b, ddof=1)
                )
                / (len(values_a) + len(values_b) - 2)
            )

            if pooled_std == 0:
                return {"cohens_d": 0.0, "interpretation": "negligible"}

            d = float(mean_diff / pooled_std)
            abs_d = abs(d)

            if abs_d >= 0.8:
                interpretation = "large"
            elif abs_d >= 0.5:
                interpretation = "medium"
            elif abs_d >= 0.2:
                interpretation = "small"
            else:
                interpretation = "negligible"

            return {"cohens_d": round(d, 4), "interpretation": interpretation}

        def compute_cliffs_delta(values_a: List[float], values_b: List[float]) -> dict:
            """Compute Cliff's delta (non-parametric effect size)"""
            if len(values_a) < 1 or len(values_b) < 1:
                return {"cliffs_delta": None, "interpretation": None}

            # Count dominance
            greater = sum(1 for a in values_a for b in values_b if a > b)
            less = sum(1 for a in values_a for b in values_b if a < b)
            n = len(values_a) * len(values_b)

            if n == 0:
                return {"cliffs_delta": None, "interpretation": None}

            delta = float((greater - less) / n)
            abs_delta = abs(delta)

            if abs_delta >= 0.474:
                interpretation = "large"
            elif abs_delta >= 0.33:
                interpretation = "medium"
            elif abs_delta >= 0.147:
                interpretation = "small"
            else:
                interpretation = "negligible"

            return {"cliffs_delta": round(delta, 4), "interpretation": interpretation}

        def compute_correlation(
            metric_values: Dict[str, List[float]]
        ) -> Dict[str, Dict[str, Optional[float]]]:
            """Compute correlation matrix between metrics (Pearson correlation)"""
            if not STATS_AVAILABLE:
                return {}

            metrics = list(metric_values.keys())
            result: Dict[str, Dict[str, Optional[float]]] = {}

            for m1 in metrics:
                result[m1] = {}
                for m2 in metrics:
                    if m1 == m2:
                        result[m1][m2] = 1.0
                    else:
                        v1, v2 = metric_values[m1], metric_values[m2]
                        if len(v1) >= 3 and len(v2) >= 3 and len(v1) == len(v2):
                            try:
                                r, _ = scipy_stats.pearsonr(v1, v2)
                                result[m1][m2] = round(float(r), 4) if not np.isnan(r) else None
                            except Exception:
                                result[m1][m2] = None
                        else:
                            result[m1][m2] = None

            return result

        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(http_request)
        if not check_project_accessible(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        warnings: List[str] = []

        # Get all completed evaluations for the project
        evaluations = (
            db.query(DBEvaluationRun)
            .filter(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status == "completed",
            )
            .all()
        )

        if not evaluations:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No completed evaluations found for this project",
            )

        evaluation_ids = [e.id for e in evaluations]

        # Query sample results with model information (handles N:M field evaluations)
        # This is the authoritative data source for per-sample, per-model scores
        generation_sample_results = (
            db.query(
                TaskEvaluation.task_id,
                TaskEvaluation.field_name,
                TaskEvaluation.metrics,
                Generation.model_id,
            )
            .join(
                Generation,
                TaskEvaluation.generation_id == Generation.id,
            )
            .filter(
                TaskEvaluation.evaluation_id.in_(evaluation_ids),
            )
            .all()
        )

        # Query annotation-based evaluation results
        from auth_module import User as DBUser
        from types import SimpleNamespace

        annotation_eval_results = (
            db.query(
                TaskEvaluation.task_id,
                TaskEvaluation.field_name,
                TaskEvaluation.metrics,
                TaskEvaluation.annotation_id,
            )
            .filter(
                TaskEvaluation.evaluation_id.in_(evaluation_ids),
                TaskEvaluation.generation_id == None,  # noqa: E711
                TaskEvaluation.annotation_id != None,  # noqa: E711
            )
            .all()
        )

        # Build annotator name map and merge results
        sample_results = list(generation_sample_results)
        if annotation_eval_results:
            annotation_ids = list(set(r.annotation_id for r in annotation_eval_results if r.annotation_id))
            if annotation_ids:
                annotations_with_users = (
                    db.query(Annotation.id, DBUser.username)
                    .join(DBUser, Annotation.completed_by == DBUser.id)
                    .filter(Annotation.id.in_(annotation_ids))
                    .all()
                )
                annotator_name_map = {a.id: a.username for a in annotations_with_users}

                for r in annotation_eval_results:
                    username = annotator_name_map.get(r.annotation_id, "Unknown")
                    sample_results.append(SimpleNamespace(
                        task_id=r.task_id,
                        field_name=r.field_name,
                        metrics=r.metrics,
                        model_id=f"annotator:{username}",
                    ))

        # Filter by compare_models if specified
        original_count = len(sample_results)
        if request.compare_models:
            sample_results = [r for r in sample_results if r.model_id in request.compare_models]
            if original_count > 0 and len(sample_results) == 0:
                warnings.append(
                    f"No data found for specified models: {', '.join(request.compare_models)}"
                )
            elif len(sample_results) < original_count:
                # Inform about filtered data
                found_models = list(set(r.model_id for r in sample_results))
                missing = [m for m in request.compare_models if m not in found_models]
                if missing:
                    warnings.append(f"No data found for models: {', '.join(missing)}")

        if not sample_results:
            # Fall back to checking if there are direct evaluations
            warnings.append("No sample-level results found; using evaluation-level metrics")

        # Helper function to compute statistics for a list of values
        def compute_metric_stats(
            values: List[float], metric_name: str
        ) -> Optional[MetricStatistics]:
            if not values:
                return None

            n = len(values)
            mean_val = float(np.mean(values))
            std_dev = float(np.std(values, ddof=1)) if n > 1 else 0.0
            std_error = std_dev / np.sqrt(n) if n > 0 else 0.0
            sorted_values = sorted(values)

            # Use t-distribution confidence interval from leaderboards
            ci_lower, ci_upper, _ = calculate_confidence_interval(values, confidence=0.95)

            return MetricStatistics(
                mean=round(mean_val, 6),
                median=float(sorted_values[n // 2]),
                std=round(std_dev, 6),
                se=round(std_error, 6),
                min=float(min(values)),
                max=float(max(values)),
                ci_lower=ci_lower
                if ci_lower is not None
                else round(mean_val - 1.96 * std_error, 6),
                ci_upper=ci_upper
                if ci_upper is not None
                else round(mean_val + 1.96 * std_error, 6),
                n=n,
            )

        # Organize data based on aggregation level
        overall_metric_values: Dict[str, List[float]] = {m: [] for m in request.metrics}
        model_metric_values: Dict[str, Dict[str, List[float]]] = {}
        field_metric_values: Dict[str, Dict[str, List[float]]] = {}
        raw_scores: List[RawScore] = []

        for result in sample_results:
            if not result.metrics:
                continue

            model_id = result.model_id
            field_name = result.field_name or "default"

            # Initialize nested dicts if needed
            if model_id not in model_metric_values:
                model_metric_values[model_id] = {m: [] for m in request.metrics}
            if field_name not in field_metric_values:
                field_metric_values[field_name] = {m: [] for m in request.metrics}

            for metric in request.metrics:
                if metric in result.metrics:
                    value = result.metrics[metric]
                    if value is not None and isinstance(value, (int, float)):
                        float_value = float(value)

                        # Collect for all aggregation types
                        overall_metric_values[metric].append(float_value)
                        model_metric_values[model_id][metric].append(float_value)
                        field_metric_values[field_name][metric].append(float_value)

                        # For sample aggregation, store raw scores
                        if request.aggregation == "sample":
                            raw_scores.append(
                                RawScore(
                                    task_id=str(result.task_id) if result.task_id else None,
                                    model_id=model_id,
                                    field_name=field_name if field_name != "default" else None,
                                    metric=metric,
                                    value=float_value,
                                )
                            )

        # If no sample results, fall back to evaluation-level metrics
        if not any(overall_metric_values.values()):
            for eval in evaluations:
                if not eval.metrics:
                    continue

                model_id = eval.model_id if eval.model_id != "unknown" else "aggregated"

                if model_id not in model_metric_values:
                    model_metric_values[model_id] = {m: [] for m in request.metrics}

                for metric in request.metrics:
                    if metric in eval.metrics:
                        value = eval.metrics[metric]
                        if value is not None and isinstance(value, (int, float)):
                            float_value = float(value)
                            overall_metric_values[metric].append(float_value)
                            model_metric_values[model_id][metric].append(float_value)

        # Compute overall statistics (always computed)
        metrics_stats: Dict[str, MetricStatistics] = {}
        for metric, values in overall_metric_values.items():
            stats = compute_metric_stats(values, metric)
            if stats:
                metrics_stats[metric] = stats
            else:
                warnings.append(f"No valid data found for metric '{metric}'")

        # Add warning if requested metrics have no data
        missing_metrics = [m for m in request.metrics if m not in metrics_stats]
        if missing_metrics and len(missing_metrics) < len(request.metrics):
            # Only warn if some metrics have data and others don't
            pass  # Already warned above per-metric

        if not metrics_stats:
            warnings.append("No valid evaluation data found for the requested metrics")

        # Aggregation-specific response data
        by_model: Optional[Dict[str, ModelStatistics]] = None
        by_field: Optional[Dict[str, FieldStatistics]] = None
        raw_scores_response: Optional[List[RawScore]] = None

        if request.aggregation == "model":
            # Compute per-model statistics
            by_model = {}
            for model_id, metric_data in model_metric_values.items():
                model_metrics: Dict[str, MetricStatistics] = {}
                sample_count = 0
                for metric, values in metric_data.items():
                    stats = compute_metric_stats(values, metric)
                    if stats:
                        model_metrics[metric] = stats
                        sample_count = max(sample_count, stats.n)

                if model_metrics:
                    by_model[model_id] = ModelStatistics(
                        model_id=model_id,
                        model_name=model_id,  # Could be enhanced with lookup
                        metrics=model_metrics,
                        sample_count=sample_count,
                    )

            if len(by_model) == 0:
                warnings.append("No per-model data available")
            elif len(by_model) == 1:
                warnings.append("Only one model has data; pairwise comparisons not possible")

        elif request.aggregation == "field":
            # Compute per-field statistics
            by_field = {}
            for field_name, metric_data in field_metric_values.items():
                field_metrics: Dict[str, MetricStatistics] = {}
                sample_count = 0
                for metric, values in metric_data.items():
                    stats = compute_metric_stats(values, metric)
                    if stats:
                        field_metrics[metric] = stats
                        sample_count = max(sample_count, stats.n)

                if field_metrics:
                    by_field[field_name] = FieldStatistics(
                        field_name=field_name,
                        metrics=field_metrics,
                        sample_count=sample_count,
                    )

            if len(by_field) == 0:
                warnings.append("No per-field data available")

        elif request.aggregation == "sample":
            # Return raw scores for box plots
            raw_scores_response = raw_scores
            if not raw_scores:
                warnings.append("No sample-level scores available for distribution analysis")

        # Pairwise comparisons (for model aggregation or when compare_models specified)
        pairwise_comparisons: List[PairwiseComparison] = []
        model_ids = list(model_metric_values.keys())

        # Filter out "unknown" and "aggregated" pseudo-models
        model_ids = [m for m in model_ids if m not in ("unknown", "aggregated")]

        if len(model_ids) > 1 and any(
            m in request.methods for m in ["ttest", "bootstrap", "cohens_d", "cliffs_delta"]
        ):
            for i, model_a in enumerate(model_ids):
                for model_b in model_ids[i + 1 :]:
                    for metric in request.metrics:
                        scores_a = model_metric_values.get(model_a, {}).get(metric, [])
                        scores_b = model_metric_values.get(model_b, {}).get(metric, [])

                        if len(scores_a) < 2 or len(scores_b) < 2:
                            continue

                        comparison = PairwiseComparison(
                            model_a=model_a,
                            model_b=model_b,
                            metric=metric,
                        )

                        # T-test (using Welch's t-test from leaderboards)
                        if "ttest" in request.methods:
                            ttest_result = calculate_significance(scores_a, scores_b)
                            if ttest_result.get("p_value") is not None:
                                comparison.ttest_p = ttest_result["p_value"]
                                comparison.ttest_significant = ttest_result.get(
                                    "significant", False
                                )
                                if comparison.ttest_significant:
                                    comparison.significant = True

                        # Bootstrap significance test (permutation-based)
                        if "bootstrap" in request.methods and STATS_AVAILABLE:
                            # Permutation test for significance
                            observed_diff = abs(np.mean(scores_a) - np.mean(scores_b))
                            combined = scores_a + scores_b
                            n_a = len(scores_a)
                            n_permutations = 1000
                            count_extreme = 0

                            for _ in range(n_permutations):
                                np.random.shuffle(combined)
                                perm_diff = abs(np.mean(combined[:n_a]) - np.mean(combined[n_a:]))
                                if perm_diff >= observed_diff:
                                    count_extreme += 1

                            bootstrap_p = count_extreme / n_permutations
                            comparison.bootstrap_p = float(round(bootstrap_p, 4))
                            comparison.bootstrap_significant = bootstrap_p < 0.05
                            if comparison.bootstrap_significant:
                                comparison.significant = True

                        # Cohen's d
                        if "cohens_d" in request.methods:
                            d_result = compute_cohens_d(scores_a, scores_b)
                            comparison.cohens_d = (
                                float(d_result["cohens_d"])
                                if d_result.get("cohens_d") is not None
                                else None
                            )
                            comparison.cohens_d_interpretation = d_result.get("interpretation")

                        # Cliff's delta
                        if "cliffs_delta" in request.methods:
                            delta_result = compute_cliffs_delta(scores_a, scores_b)
                            comparison.cliffs_delta = (
                                float(delta_result["cliffs_delta"])
                                if delta_result.get("cliffs_delta") is not None
                                else None
                            )
                            comparison.cliffs_delta_interpretation = delta_result.get(
                                "interpretation"
                            )

                        pairwise_comparisons.append(comparison)

        # Correlation matrix
        correlations: Optional[Dict[str, Dict[str, Optional[float]]]] = None
        if "correlation" in request.methods and len(request.metrics) > 1:
            # Only compute if we have values for multiple metrics
            metrics_with_values = {m: v for m, v in overall_metric_values.items() if len(v) >= 3}
            if len(metrics_with_values) > 1:
                correlations = compute_correlation(metrics_with_values)
            elif len(request.metrics) > 1:
                warnings.append(
                    "Insufficient data for correlation matrix (need >=3 samples per metric)"
                )

        return StatisticsResponse(
            aggregation=request.aggregation,
            metrics=metrics_stats,
            by_model=by_model,
            by_field=by_field,
            raw_scores=raw_scores_response,
            pairwise_comparisons=pairwise_comparisons if pairwise_comparisons else None,
            correlations=correlations,
            warnings=warnings if warnings else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to compute statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute statistics: {str(e)}",
        )
