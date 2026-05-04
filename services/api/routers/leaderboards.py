"""
Leaderboard API endpoints for LLM model performance tracking.

Provides LLM model leaderboards based on evaluation metrics.
Supports filtering by project and time period.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth_module.dependencies import get_current_user
from database import get_db
from models import EvaluationRun, TaskEvaluation, Generation, LLMModel, User
from project_models import Annotation
from routers.projects.helpers import check_project_accessible, get_org_context_from_request

# Statistical imports for confidence intervals
try:
    import numpy as np
    from scipy import stats

    STATS_AVAILABLE = True
except ImportError:
    STATS_AVAILABLE = False

router = APIRouter(prefix="/api/leaderboards", tags=["leaderboards"])


def _filter_accessible_project_ids(
    db: Session, user, project_ids: Optional[List[str]], org_context: Optional[str] = None
) -> Optional[List[str]]:
    """Filter project_ids to only include those the user can access."""
    if not project_ids:
        return project_ids
    if user.is_superadmin:
        return project_ids
    return [pid for pid in project_ids if check_project_accessible(db, user, pid, org_context)]


def detect_provider_from_model_id(model_id: str) -> str:
    """
    Detect LLM provider from model_id string patterns.

    Used as fallback when model is not in the LLMModel database table.
    """
    model_lower = model_id.lower()

    if model_lower.startswith("gpt-") or model_lower.startswith("o1-"):
        return "OpenAI"
    elif model_lower.startswith("claude-"):
        return "Anthropic"
    elif model_lower.startswith("gemini-"):
        return "Google"
    elif "llama" in model_lower:
        return "Meta"
    elif "mistral" in model_lower or "mixtral" in model_lower:
        return "Mistral"
    elif "qwen" in model_lower:
        return "Alibaba"
    elif "deepseek" in model_lower:
        return "DeepSeek"
    elif "command" in model_lower:
        return "Cohere"
    elif model_lower == "unknown":
        return "Unknown"

    return "Other"


def calculate_confidence_interval(
    values: List[float], confidence: float = 0.95
) -> Tuple[Optional[float], Optional[float], int]:
    """
    Calculate confidence interval using t-distribution.

    Args:
        values: List of metric values
        confidence: Confidence level (default 95%)

    Returns:
        Tuple of (lower_bound, upper_bound, sample_count)
        Returns (None, None, n) if insufficient data
    """
    if not STATS_AVAILABLE:
        return (None, None, len(values))

    n = len(values)
    if n < 2:
        return (None, None, n)

    mean = np.mean(values)
    se = stats.sem(values)  # Standard error of the mean

    # t-distribution critical value
    alpha = 1 - confidence
    t_critical = stats.t.ppf(1 - alpha / 2, n - 1)

    margin = t_critical * se
    return (round(mean - margin, 4), round(mean + margin, 4), n)


def calculate_significance(values_a: List[float], values_b: List[float]) -> Dict[str, Any]:
    """
    Calculate statistical significance between two sets of values.

    Uses independent t-test (Welch's t-test for unequal variances).

    Args:
        values_a: Values from model A
        values_b: Values from model B

    Returns:
        Dict with significance info:
        - significant: bool indicating if difference is significant at p<0.05
        - p_value: The p-value (None if insufficient data)
        - stars: Significance stars (* p<0.05, ** p<0.01, *** p<0.001)
        - effect_size: Cohen's d effect size
    """
    if not STATS_AVAILABLE:
        return {"significant": None, "p_value": None, "stars": "", "effect_size": None}

    if len(values_a) < 2 or len(values_b) < 2:
        return {"significant": None, "p_value": None, "stars": "", "effect_size": None}

    # Welch's t-test (doesn't assume equal variances)
    t_stat, p_value = stats.ttest_ind(values_a, values_b, equal_var=False)

    # Determine significance stars
    if p_value < 0.001:
        stars = "***"
    elif p_value < 0.01:
        stars = "**"
    elif p_value < 0.05:
        stars = "*"
    else:
        stars = ""

    # Calculate Cohen's d effect size
    pooled_std = np.sqrt(
        (
            (len(values_a) - 1) * np.var(values_a, ddof=1)
            + (len(values_b) - 1) * np.var(values_b, ddof=1)
        )
        / (len(values_a) + len(values_b) - 2)
    )
    effect_size = None
    if pooled_std > 0:
        effect_size = round((np.mean(values_a) - np.mean(values_b)) / pooled_std, 4)

    return {
        "significant": bool(p_value < 0.05),
        "p_value": float(round(p_value, 4)),
        "stars": stars,
        "effect_size": float(effect_size) if effect_size is not None else None,
    }


# LLM Leaderboard Response Models
class MetricWithCI(BaseModel):
    """Metric value with confidence interval"""

    value: float
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    sample_count: int = 1


class LLMLeaderboardEntry(BaseModel):
    rank: int
    model_id: str
    model_name: str
    provider: str
    evaluation_count: int
    samples_evaluated: int
    metrics: Dict[str, Optional[float]]
    average_score: Optional[float]  # None for models without evaluations
    # Confidence interval for average score (95% CI)
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    last_evaluated: Optional[str]


class LLMLeaderboardResponse(BaseModel):
    leaderboard: List[LLMLeaderboardEntry]
    total_models: int
    available_metrics: List[str]
    available_evaluation_types: List[str] = []  # List of evaluation types in the data
    filters: Dict[str, Any]
    # Indicate if CI calculations are available
    confidence_intervals_available: bool = STATS_AVAILABLE


@router.get("/statistics")
async def get_leaderboard_statistics(
    request: Request,
    project_ids: Optional[List[str]] = Query(None),
    period: str = Query("overall", regex="^(overall|monthly|weekly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get aggregate statistics for the leaderboard.

    **Returns**:
    - total_annotations: Total number of annotations in scope
    - total_annotators: Number of unique annotators (with at least 1 annotation)
    - total_users: Total number of active users in the system
    - average_annotations: Average annotations per annotator
    """
    # Filter project_ids to only include accessible ones
    org_context = get_org_context_from_request(request)
    project_ids = _filter_accessible_project_ids(db, current_user, project_ids, org_context)

    # Build query for annotation counts
    query = db.query(
        func.count(Annotation.id).label('total'),
        func.count(func.distinct(Annotation.completed_by)).label('unique_users'),
    ).filter(
        Annotation.was_cancelled == False,  # noqa: E712
        func.jsonb_array_length(Annotation.result) > 0,
    )

    # Apply filters
    if project_ids:
        query = query.filter(Annotation.project_id.in_(project_ids))

    now = datetime.utcnow()
    if period == "monthly":
        query = query.filter(Annotation.created_at >= now - timedelta(days=30))
    elif period == "weekly":
        query = query.filter(Annotation.created_at >= now - timedelta(days=7))

    result = query.first()
    total_annotations = result.total or 0
    total_annotators = result.unique_users or 0

    # Get total active users count (regardless of annotations)
    total_users = (
        db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0
    )  # noqa: E712

    # Calculate average
    average = total_annotations / total_annotators if total_annotators > 0 else 0

    return {
        "total_annotations": total_annotations,
        "total_annotators": total_annotators,
        "total_users": total_users,
        "average_annotations_per_user": round(average, 2),
        "filters": {"project_ids": project_ids or [], "period": period},
    }


# ============================================================================
# LLM MODEL LEADERBOARD ENDPOINTS
# ============================================================================


@router.get("/llm-models", response_model=LLMLeaderboardResponse)
async def get_llm_leaderboard(
    request: Request,
    project_ids: Optional[List[str]] = Query(
        None, description="Filter by specific projects (empty = all projects)"
    ),
    period: str = Query(
        "overall", regex="^(overall|monthly|weekly)$", description="Time period filter"
    ),
    metric: str = Query(
        "average", description="Metric to rank by (average, accuracy, f1, bleu, etc.)"
    ),
    evaluation_types: Optional[List[str]] = Query(
        None, description="Filter by evaluation types (e.g., accuracy, f1, llm_judge)"
    ),
    include_all_models: bool = Query(False, description="Include models with no evaluations"),
    aggregation: str = Query(
        "average", regex="^(average|sum)$", description="Aggregation mode: average or sum"
    ),
    limit: int = Query(50, le=200, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get LLM model leaderboard rankings based on evaluation metrics.

    Returns a ranked list of LLM models with their evaluation metrics,
    ordered by the specified metric.

    **Ranking Metrics**:
    - average: Average of all available metrics
    - accuracy, f1, precision, recall: Classification metrics
    - bleu, rouge, meteor, chrf: Text generation metrics
    - semantic_similarity, bertscore: Semantic metrics
    - llm_judge_*: LLM-as-Judge metrics

    **Filters**:
    - project_ids: Filter to specific projects (default: all projects)
    - period: Time period (overall, monthly, weekly)
    - metric: Metric to rank by (default: average)
    - limit: Maximum number of results (default: 50, max: 100)

    **Returns**:
    - leaderboard: List of ranked models with metrics
    - total_models: Total number of models evaluated
    - available_metrics: List of metrics with data
    """
    # Filter project_ids to only include accessible ones
    org_context = get_org_context_from_request(request)
    project_ids = _filter_accessible_project_ids(db, current_user, project_ids, org_context)

    # Build base query for evaluations
    query = db.query(EvaluationRun).filter(EvaluationRun.status == "completed")

    # Apply project filter
    if project_ids:
        query = query.filter(EvaluationRun.project_id.in_(project_ids))

    # Apply time period filter
    now = datetime.utcnow()
    if period == "monthly":
        cutoff = now - timedelta(days=30)
        query = query.filter(EvaluationRun.created_at >= cutoff)
    elif period == "weekly":
        cutoff = now - timedelta(days=7)
        query = query.filter(EvaluationRun.created_at >= cutoff)

    # Apply evaluation type filter
    # evaluation_type_ids is a JSON array, filter evaluations containing any of the specified types
    if evaluation_types:
        from sqlalchemy import or_, text

        # Use PostgreSQL JSON containment operator for each type
        type_filters = []
        for eval_type in evaluation_types:
            type_filters.append(
                text("evaluation_type_ids::jsonb @> :type").bindparams(type=f'["{eval_type}"]')
            )
        if type_filters:
            query = query.filter(or_(*type_filters))

    # Collect all evaluation types for the response
    all_evaluation_types_seen = set()

    # Get all evaluations
    evaluations = query.all()

    # Collect evaluation types from all evaluations
    for eval in evaluations:
        if eval.evaluation_type_ids:
            for eval_type in eval.evaluation_type_ids:
                all_evaluation_types_seen.add(eval_type)

    # Get evaluation IDs for filtering sample results
    eval_ids = [e.id for e in evaluations]

    # Aggregate by model directly from sample results
    # This handles multi-model evaluations where one evaluation contains results for many models
    model_data: Dict[str, Dict[str, Any]] = {}
    all_metrics_seen = set()

    if eval_ids:
        # Query sample results grouped by model_id
        # This gives us per-model metrics from all evaluations
        sample_results_query = (
            db.query(
                Generation.model_id,
                TaskEvaluation.metrics,
                TaskEvaluation.evaluation_id,
                EvaluationRun.completed_at,
            )
            .join(Generation, TaskEvaluation.generation_id == Generation.id)
            .join(EvaluationRun, TaskEvaluation.evaluation_id == EvaluationRun.id)
            .filter(TaskEvaluation.evaluation_id.in_(eval_ids))
            .filter(TaskEvaluation.generation_id.isnot(None))
            .all()
        )

        # Track unique evaluations per model for counting
        model_evaluations: Dict[str, set] = {}

        for model_id, metrics, eval_id, completed_at in sample_results_query:
            if model_id not in model_data:
                model_data[model_id] = {
                    "evaluation_count": 0,
                    "samples_evaluated": 0,
                    "metrics_raw": {},
                    "last_evaluated": None,
                }
                model_evaluations[model_id] = set()

            # Track unique evaluations for this model
            model_evaluations[model_id].add(eval_id)

            # Count samples
            model_data[model_id]["samples_evaluated"] += 1

            # Update last evaluated
            if completed_at:
                last = model_data[model_id]["last_evaluated"]
                if last is None or completed_at > datetime.fromisoformat(last):
                    model_data[model_id]["last_evaluated"] = completed_at.isoformat()

            # Aggregate metrics from sample results
            # When evaluation_types filter is applied, only aggregate metrics that match
            # the filtered types (otherwise unrelated metrics like raw_score get mixed in)
            if metrics:
                for metric_name, value in metrics.items():
                    if value is not None and isinstance(value, (int, float)):
                        # Skip metrics that don't match the filter when filtering by type
                        if evaluation_types and metric_name not in evaluation_types:
                            continue
                        all_metrics_seen.add(metric_name)
                        if metric_name not in model_data[model_id]["metrics_raw"]:
                            model_data[model_id]["metrics_raw"][metric_name] = []
                        model_data[model_id]["metrics_raw"][metric_name].append(float(value))

        # Set evaluation counts from unique evaluation IDs
        for model_id, eval_set in model_evaluations.items():
            model_data[model_id]["evaluation_count"] = len(eval_set)

    # Calculate average metrics and confidence intervals per model
    for model_id, data in model_data.items():
        averaged_metrics = {}
        all_score_values = []  # Collect all values for overall CI

        for metric_name, values in data["metrics_raw"].items():
            if values:
                if aggregation == "sum":
                    agg = sum(values)
                else:
                    agg = sum(values) / len(values)
                averaged_metrics[metric_name] = round(agg, 4)
                all_score_values.extend(values)

        data["metrics"] = averaged_metrics

        # Calculate CI for average score across all metrics (skip for sum mode)
        if aggregation == "average" and all_score_values:
            ci_lower, ci_upper, _ = calculate_confidence_interval(all_score_values)
            data["ci_lower"] = ci_lower
            data["ci_upper"] = ci_upper
        else:
            data["ci_lower"] = None
            data["ci_upper"] = None

    # Get model metadata
    model_info = {}
    if model_data:
        models = db.query(LLMModel).filter(LLMModel.id.in_(model_data.keys())).all()
        for m in models:
            model_info[m.id] = {"name": m.name, "provider": m.provider}

    # Calculate ranking score for each model
    for model_id, data in model_data.items():
        if data["metrics"]:
            if metric == "average":
                valid_values = [v for v in data["metrics"].values() if v is not None]
                if valid_values:
                    if aggregation == "sum":
                        data["average_score"] = round(sum(valid_values), 4)
                    else:
                        data["average_score"] = round(sum(valid_values) / len(valid_values), 4)
                else:
                    data["average_score"] = None
            elif metric in data["metrics"]:
                data["average_score"] = data["metrics"][metric]
            else:
                data["average_score"] = None
        else:
            data["average_score"] = None

    # Optionally include all active models (even those without evaluations)
    if include_all_models:
        all_active_models = db.query(LLMModel).filter(LLMModel.is_active == True).all()
        for model in all_active_models:
            if model.id not in model_data:
                model_data[model.id] = {
                    "evaluation_count": 0,
                    "samples_evaluated": 0,
                    "metrics_raw": {},
                    "metrics": {},
                    "average_score": None,
                    "last_evaluated": None,
                    "ci_lower": None,
                    "ci_upper": None,
                }
            # Add to model_info for name/provider lookup
            if model.id not in model_info:
                model_info[model.id] = {"name": model.name, "provider": model.provider}

    # Sort: models with scores first (by score desc), then models without scores (by name)
    def sort_key(item):
        model_id, data = item
        score = data["average_score"]
        name = model_info.get(model_id, {}).get("name", model_id)
        # Return tuple: (has_score, negative_score_for_desc, name_for_alpha)
        if score is not None:
            return (0, -score, name.lower())  # 0 = has score, comes first
        else:
            return (1, 0, name.lower())  # 1 = no score, comes after

    sorted_models = sorted(model_data.items(), key=sort_key)

    # Build leaderboard
    leaderboard = []
    for rank, (model_id, data) in enumerate(sorted_models[offset:offset + limit], start=offset + 1):
        # Use database model info if available, otherwise detect provider from model_id
        if model_id in model_info:
            info = model_info[model_id]
        else:
            info = {"name": model_id, "provider": detect_provider_from_model_id(model_id)}
        leaderboard.append(
            LLMLeaderboardEntry(
                rank=rank,
                model_id=model_id,
                model_name=info["name"],
                provider=info["provider"],
                evaluation_count=data["evaluation_count"],
                samples_evaluated=data["samples_evaluated"],
                metrics=data["metrics"],
                average_score=data["average_score"],
                ci_lower=data.get("ci_lower"),
                ci_upper=data.get("ci_upper"),
                last_evaluated=data["last_evaluated"],
            )
        )

    return LLMLeaderboardResponse(
        leaderboard=leaderboard,
        total_models=len(model_data),
        available_metrics=sorted(list(all_metrics_seen)),
        available_evaluation_types=sorted(list(all_evaluation_types_seen)),
        filters={
            "project_ids": project_ids or [],
            "period": period,
            "metric": metric,
            "aggregation": aggregation,
            "evaluation_types": evaluation_types or [],
            "include_all_models": include_all_models,
            "limit": limit,
            "offset": offset,
        },
        confidence_intervals_available=STATS_AVAILABLE,
    )


@router.get("/llm-models/{model_id}")
async def get_llm_model_details(
    model_id: str,
    request: Request,
    project_ids: Optional[List[str]] = Query(None),
    period: str = Query("overall", regex="^(overall|monthly|weekly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed evaluation history for a specific LLM model.

    **Returns**:
    - model_info: Model metadata (name, provider)
    - evaluations: List of evaluation results
    - aggregate_metrics: Average metrics across all evaluations
    - evaluation_count: Total number of evaluations
    """
    # Filter project_ids to only include accessible ones
    org_context = get_org_context_from_request(request)
    project_ids = _filter_accessible_project_ids(db, current_user, project_ids, org_context)

    # Get model info (with provider detection fallback)
    model = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    model_info = (
        {"id": model.id, "name": model.name, "provider": model.provider}
        if model
        else {"id": model_id, "name": model_id, "provider": detect_provider_from_model_id(model_id)}
    )

    # Build query
    query = db.query(EvaluationRun).filter(
        EvaluationRun.model_id == model_id, EvaluationRun.status == "completed"
    )

    if project_ids:
        query = query.filter(EvaluationRun.project_id.in_(project_ids))

    now = datetime.utcnow()
    if period == "monthly":
        query = query.filter(EvaluationRun.created_at >= now - timedelta(days=30))
    elif period == "weekly":
        query = query.filter(EvaluationRun.created_at >= now - timedelta(days=7))

    evaluations = query.order_by(EvaluationRun.created_at.desc()).all()

    # Aggregate metrics
    metric_values: Dict[str, List[float]] = {}
    metric_null_counts: Dict[str, int] = {}  # Phase 6.5: filtered-out audit
    eval_list = []

    for eval in evaluations:
        eval_list.append(
            {
                "id": eval.id,
                "project_id": eval.project_id,
                "metrics": eval.metrics,
                "samples_evaluated": eval.samples_evaluated,
                "created_at": eval.created_at.isoformat() if eval.created_at else None,
                "completed_at": eval.completed_at.isoformat() if eval.completed_at else None,
            }
        )

        if eval.metrics:
            from routers.evaluations.results import _coerce_metric_value

            for metric_name, value in eval.metrics.items():
                # Phase 2: accept legacy bare-float OR new {value, details}
                # shape. Coercion returns None for non-numeric / metadata
                # entries; those get skipped same as before.
                coerced = _coerce_metric_value(value)
                if coerced is None:
                    # Phase 6.5: track null/non-numeric values that get
                    # excluded from the aggregation so consumers can
                    # see the size of the silently-filtered set.
                    metric_null_counts[metric_name] = (
                        metric_null_counts.get(metric_name, 0) + 1
                    )
                    continue
                metric_values.setdefault(metric_name, []).append(coerced)

    # Calculate averages
    aggregate_metrics = {}
    for metric_name, values in metric_values.items():
        if values:
            aggregate_metrics[metric_name] = {
                "mean": round(sum(values) / len(values), 4),
                "min": round(min(values), 4),
                "max": round(max(values), 4),
                "count": len(values),
                # Phase 6.5: how many values were filtered out at
                # aggregation time. Mean is over `count` values; the
                # remaining `null_count` got dropped silently before.
                "null_count": metric_null_counts.get(metric_name, 0),
            }

    return {
        "model_info": model_info,
        "evaluations": eval_list,
        "aggregate_metrics": aggregate_metrics,
        "evaluation_count": len(evaluations),
        "filters": {"project_ids": project_ids or [], "period": period},
    }


@router.get("/llm-models/compare")
async def compare_llm_models(
    request: Request,
    model_ids: List[str] = Query(..., description="Model IDs to compare (2-5 models)"),
    project_ids: Optional[List[str]] = Query(None),
    period: str = Query("overall", regex="^(overall|monthly|weekly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compare evaluation metrics across multiple LLM models.

    **Parameters**:
    - model_ids: List of 2-5 model IDs to compare

    **Returns**:
    - models: Model info and metrics for each model
    - common_metrics: Metrics available for all models
    - comparison: Side-by-side metric comparison
    """
    if len(model_ids) < 2 or len(model_ids) > 5:
        return {"error": "Please provide 2-5 model IDs for comparison"}

    # Filter project_ids to only include accessible ones
    org_context = get_org_context_from_request(request)
    project_ids = _filter_accessible_project_ids(db, current_user, project_ids, org_context)

    # Get model info
    models_db = db.query(LLMModel).filter(LLMModel.id.in_(model_ids)).all()
    model_info = {m.id: {"name": m.name, "provider": m.provider} for m in models_db}

    # Get evaluations for all models
    query = db.query(EvaluationRun).filter(
        EvaluationRun.model_id.in_(model_ids), EvaluationRun.status == "completed"
    )

    if project_ids:
        query = query.filter(EvaluationRun.project_id.in_(project_ids))

    now = datetime.utcnow()
    if period == "monthly":
        query = query.filter(EvaluationRun.created_at >= now - timedelta(days=30))
    elif period == "weekly":
        query = query.filter(EvaluationRun.created_at >= now - timedelta(days=7))

    evaluations = query.all()

    # Aggregate by model
    model_metrics: Dict[str, Dict[str, List[float]]] = {m_id: {} for m_id in model_ids}

    from routers.evaluations.results import _coerce_metric_value

    for eval in evaluations:
        if eval.metrics:
            for metric_name, value in eval.metrics.items():
                # Phase 2: legacy bare-float OR {value, details} dict.
                coerced = _coerce_metric_value(value)
                if coerced is None:
                    continue
                model_metrics[eval.model_id].setdefault(metric_name, []).append(coerced)

    # Calculate averages
    model_averages = {}
    all_metrics = set()

    for model_id, metrics in model_metrics.items():
        model_averages[model_id] = {}
        for metric_name, values in metrics.items():
            if values:
                all_metrics.add(metric_name)
                model_averages[model_id][metric_name] = round(sum(values) / len(values), 4)

    # Find common metrics (present in all models)
    common_metrics = list(all_metrics)
    for model_id in model_ids:
        common_metrics = [m for m in common_metrics if m in model_averages.get(model_id, {})]

    # Build comparison table
    comparison = {}
    for metric in sorted(all_metrics):
        comparison[metric] = {}
        values = []
        for model_id in model_ids:
            val = model_averages.get(model_id, {}).get(metric)
            comparison[metric][model_id] = val
            if val is not None:
                values.append((model_id, val))

        # Determine winner (highest value for most metrics, assuming higher is better)
        if values:
            winner = max(values, key=lambda x: x[1])
            comparison[metric]["_winner"] = winner[0]

    # Calculate pairwise significance for each metric (between top model and others)
    significance_tests = {}
    for metric in common_metrics:
        significance_tests[metric] = {}

        # Get all values for this metric per model
        metric_values_per_model = {}
        for model_id in model_ids:
            if metric in model_metrics.get(model_id, {}):
                metric_values_per_model[model_id] = model_metrics[model_id][metric]

        # Calculate pairwise significance
        for i, model_a in enumerate(model_ids):
            for model_b in model_ids[i + 1 :]:
                values_a = metric_values_per_model.get(model_a, [])
                values_b = metric_values_per_model.get(model_b, [])

                sig_result = calculate_significance(values_a, values_b)
                pair_key = f"{model_a}_vs_{model_b}"
                significance_tests[metric][pair_key] = sig_result

    return {
        "models": {
            model_id: {
                "info": model_info.get(
                    model_id,
                    {"name": model_id, "provider": detect_provider_from_model_id(model_id)},
                ),
                "metrics": model_averages.get(model_id, {}),
            }
            for model_id in model_ids
        },
        "common_metrics": common_metrics,
        "all_metrics": sorted(list(all_metrics)),
        "comparison": comparison,
        "significance": significance_tests,
        "significance_available": STATS_AVAILABLE,
        "filters": {"model_ids": model_ids, "project_ids": project_ids or [], "period": period},
    }
