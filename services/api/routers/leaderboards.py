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
from project_models import Annotation, Project
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


def _apply_default_visibility_filter(query, project_ids):
    """Issue #30 PR 5: when a leaderboard endpoint is called without an
    explicit `project_ids` list, default to PUBLIC projects only.

    Background: the unfiltered default was implicitly "every completed
    EvaluationRun the database has," regardless of project visibility. That
    silently mixed scores from private evaluation projects (e.g. ZJS Fälle —
    34k+ BLEU-only task_evaluations) into the global per-model averages,
    skewing rankings.

    Caller contract: query must already join (or be ready to join)
    `EvaluationRun.project_id == Project.id`. We add the join only when
    `project_ids` is empty so callers that supplied an explicit list don't
    pay an extra join.
    """
    if project_ids:
        return query.filter(EvaluationRun.project_id.in_(project_ids))
    return query.join(
        Project, EvaluationRun.project_id == Project.id,
    ).filter(Project.is_public.is_(True))


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
    """Confidence interval of the mean (t-distribution). Thin wrapper over bg_statistics."""
    from bg_statistics import confidence_interval as _ci

    return _ci(values, confidence=confidence)


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
    # Distinct generations the model produced (regardless of how many
    # metrics were run against each). Mirrors `annotation_count` on the
    # human/co-creation leaderboards so the LLM table can show a "Generations"
    # column with the same semantics.
    generation_count: int = 0
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
    # Staleness hint — when the precomputed snapshot we read was built.
    # None for live-aggregation responses (no precomputed snapshot used).
    computed_at: Optional[str] = None


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
# LLM MODEL LEADERBOARD ENDPOINTS — read from precomputed `llm_leaderboard_scores`
# table (refreshed every 12h by the Celery task `recompute_aggregates`).
# Live SQL fallback handles non-precomputed filter combinations. See
# services/api/services/aggregate_summaries.py for the aggregation logic.
# ============================================================================


def _project_scope_key_for_request(
    project_ids: Optional[List[str]], current_user
) -> Optional[str]:
    """Map a request to a precomputed scope key, or return None for live.

    Returns:
      - single-project id when exactly one project is in the filter
      - 'all' for any authenticated user with no filter — logged-in users see
        aggregate leaderboard scores across every project (the leaderboard is
        aggregate-only, never row-level data, so private-project rankings are
        the legitimate signal we want them to act on)
      - 'public' for anonymous visitors with no filter — the public web
        leaderboard stays scoped to is_public=True projects so private
        project rankings don't leak to the open internet
      - None when no precomputed scope matches (multi-project explicit filter)
    """
    if project_ids and len(project_ids) == 1:
        return project_ids[0]
    if project_ids:
        return None  # multi-project filter → live fallback
    if current_user is not None:
        return "all"
    return "public"


def _evaluation_types_in_scope(
    db: Session, project_ids: Optional[List[str]], scope_key: Optional[str]
) -> List[str]:
    """Distinct evaluation_type_ids surfaced for the UI filter chip list.

    Cheap: scans EvaluationRun (a few hundred rows in prod), not task_evaluations.
    """
    stmt = db.query(EvaluationRun.evaluation_type_ids).filter(
        EvaluationRun.status == "completed"
    )
    if project_ids:
        stmt = stmt.filter(EvaluationRun.project_id.in_(project_ids))
    elif scope_key == "public":
        stmt = stmt.join(Project, EvaluationRun.project_id == Project.id).filter(
            Project.is_public.is_(True)
        )
    seen: set = set()
    for (type_ids,) in stmt.all():
        if isinstance(type_ids, list):
            for t in type_ids:
                if t:
                    seen.add(t)
    return sorted(seen)


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

    Reads from the precomputed `llm_leaderboard_scores` table for the
    standard filter combinations (no project filter, single-project, or
    public). Falls back to a live (but bounded) SQL aggregation for the
    rare unusual filter combinations (multi-project explicit, evaluation
    type filter, sum aggregation).

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
    - limit: Maximum number of results (default: 50, max: 200)

    **Returns**:
    - leaderboard: List of ranked models with metrics
    - total_models: Total number of models evaluated
    - available_metrics: List of metrics with data
    - computed_at: ISO timestamp of the precomputed snapshot
                   (null for live-aggregation responses)
    """
    from aggregate_summaries import (
        live_aggregate_leaderboard,
        read_llm_leaderboard,
    )

    org_context = get_org_context_from_request(request)
    project_ids = _filter_accessible_project_ids(db, current_user, project_ids, org_context)

    scope_key = _project_scope_key_for_request(project_ids, current_user)

    # Precomputed scores cover the common case (no per-request evaluation_type
    # filter, average aggregation). Anything outside falls through to live SQL
    # — still bounded by yield_per streaming inside the helper.
    use_precomputed = (
        scope_key is not None
        and not evaluation_types
        and aggregation == "average"
    )

    computed_at: Optional[datetime] = None
    entries: List[Dict[str, Any]]
    if use_precomputed:
        entries, total_models, available_metrics, computed_at = read_llm_leaderboard(
            db, scope_key, period, metric, limit, offset
        )
    else:
        rows = live_aggregate_leaderboard(db, project_ids, period, evaluation_types)
        by_model: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            entry = by_model.setdefault(
                r["model_id"],
                {
                    "model_id": r["model_id"],
                    "metrics": {},
                    "score": None,
                    "ci_lower": None,
                    "ci_upper": None,
                    "samples_evaluated": r["samples_evaluated"],
                    "evaluation_count": r["evaluation_count"],
                    "generation_count": r["generation_count"],
                    "last_evaluated_at": r["last_evaluated_at"],
                },
            )
            score = r["score"]
            if r["metric"] == "average":
                entry["metrics"]["average"] = score
            else:
                entry["metrics"][r["metric"]] = score
            if r["metric"] == metric:
                entry["score"] = score
                entry["ci_lower"] = r["ci_lower"]
                entry["ci_upper"] = r["ci_upper"]

        sorted_entries = sorted(
            by_model.values(),
            key=lambda e: (e["score"] is None, -(e["score"] or 0), e["model_id"]),
        )
        total_models = len(sorted_entries)
        entries = sorted_entries[offset : offset + limit]
        available_metrics = sorted(
            {r["metric"] for r in rows if r["metric"] != "average"}
        )

    # Look up model metadata (small bounded query — at most `limit` models).
    model_ids_in_page = [e["model_id"] for e in entries]
    model_info: Dict[str, Dict[str, str]] = {}
    if model_ids_in_page:
        for m in db.query(LLMModel).filter(LLMModel.id.in_(model_ids_in_page)).all():
            model_info[m.id] = {"name": m.name, "provider": m.provider}

    available_evaluation_types = _evaluation_types_in_scope(db, project_ids, scope_key)

    leaderboard: List[LLMLeaderboardEntry] = []
    for rank, entry in enumerate(entries, start=offset + 1):
        info = model_info.get(
            entry["model_id"],
            {
                "name": entry["model_id"],
                "provider": detect_provider_from_model_id(entry["model_id"]),
            },
        )
        last_at = entry.get("last_evaluated_at")
        # Drop the synthetic 'average' key from the per-metric dict the frontend
        # iterates over — it's surfaced separately as `average_score`.
        metrics_for_display = {
            k: v for k, v in entry.get("metrics", {}).items() if k != "average"
        }
        leaderboard.append(
            LLMLeaderboardEntry(
                rank=rank,
                model_id=entry["model_id"],
                model_name=info["name"],
                provider=info["provider"],
                evaluation_count=entry.get("evaluation_count", 0),
                samples_evaluated=entry.get("samples_evaluated", 0),
                generation_count=entry.get("generation_count", 0),
                metrics=metrics_for_display,
                average_score=entry.get("score"),
                ci_lower=entry.get("ci_lower"),
                ci_upper=entry.get("ci_upper"),
                last_evaluated=last_at.isoformat() if last_at else None,
            )
        )

    # Include zero-row entries for active models that aren't in the page.
    if include_all_models:
        seen = {e.model_id for e in leaderboard}
        for m in db.query(LLMModel).filter(LLMModel.is_active == True).all():  # noqa: E712
            if m.id in seen:
                continue
            leaderboard.append(
                LLMLeaderboardEntry(
                    rank=len(leaderboard) + 1,
                    model_id=m.id,
                    model_name=m.name,
                    provider=m.provider,
                    evaluation_count=0,
                    samples_evaluated=0,
                    generation_count=0,
                    metrics={},
                    average_score=None,
                    ci_lower=None,
                    ci_upper=None,
                    last_evaluated=None,
                )
            )
            total_models += 1

    return LLMLeaderboardResponse(
        leaderboard=leaderboard,
        total_models=total_models,
        available_metrics=available_metrics,
        available_evaluation_types=available_evaluation_types,
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
        computed_at=computed_at.isoformat() if computed_at else None,
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
    Get aggregated evaluation metrics for a specific LLM model.

    Reads from the precomputed `llm_leaderboard_scores` table where
    possible, falling back to live aggregation for multi-project filters.

    **Returns**:
    - model_info: Model metadata (name, provider)
    - aggregate_metrics: Per-metric {mean, ci_lower, ci_upper, count}
    - evaluation_count: Total number of evaluations
    - samples_evaluated: Sum of TaskEvaluation rows
    - generation_count: Distinct generations
    - last_evaluated: ISO of the most recent EvaluationRun completion
    - computed_at: When the precomputed snapshot was built (null for live)
    """
    from aggregate_summaries import (
        live_aggregate_leaderboard,
        read_llm_model_aggregate,
    )

    org_context = get_org_context_from_request(request)
    project_ids = _filter_accessible_project_ids(db, current_user, project_ids, org_context)

    model = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    model_info = (
        {"id": model.id, "name": model.name, "provider": model.provider}
        if model
        else {
            "id": model_id,
            "name": model_id,
            "provider": detect_provider_from_model_id(model_id),
        }
    )

    scope_key = _project_scope_key_for_request(project_ids, current_user)

    if scope_key is not None:
        aggregate = read_llm_model_aggregate(db, model_id, scope_key, period)
    else:
        rows = [
            r
            for r in live_aggregate_leaderboard(db, project_ids, period, None)
            if r["model_id"] == model_id
        ]
        aggregate = {
            "metrics": {},
            "evaluation_count": 0,
            "samples_evaluated": 0,
            "generation_count": 0,
            "last_evaluated_at": None,
            "computed_at": None,
        }
        for r in rows:
            if r["metric"] != "average":
                aggregate["metrics"][r["metric"]] = {
                    "mean": r["score"],
                    "ci_lower": r["ci_lower"],
                    "ci_upper": r["ci_upper"],
                    "count": r["samples_evaluated"],
                }
            aggregate["evaluation_count"] = max(
                aggregate["evaluation_count"], r["evaluation_count"]
            )
            aggregate["samples_evaluated"] = max(
                aggregate["samples_evaluated"], r["samples_evaluated"]
            )
            aggregate["generation_count"] = max(
                aggregate["generation_count"], r["generation_count"]
            )
            last = r["last_evaluated_at"]
            if last and (
                aggregate["last_evaluated_at"] is None
                or last > aggregate["last_evaluated_at"]
            ):
                aggregate["last_evaluated_at"] = last

    return {
        "model_info": model_info,
        "aggregate_metrics": aggregate["metrics"],
        "evaluation_count": aggregate["evaluation_count"],
        "samples_evaluated": aggregate["samples_evaluated"],
        "generation_count": aggregate["generation_count"],
        "last_evaluated": (
            aggregate["last_evaluated_at"].isoformat()
            if aggregate.get("last_evaluated_at")
            else None
        ),
        "computed_at": (
            aggregate["computed_at"].isoformat()
            if aggregate.get("computed_at")
            else None
        ),
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

    Reads precomputed per-(model, metric) means from `llm_leaderboard_scores`.
    Significance tests require raw per-task distributions which the precomputed
    table doesn't carry — they're disabled here. Frontend already handles
    `significance_available=False`.

    **Parameters**:
    - model_ids: List of 2-5 model IDs to compare

    **Returns**:
    - models: Model info and metrics for each model
    - common_metrics: Metrics available for all models
    - comparison: Side-by-side metric comparison
    """
    if len(model_ids) < 2 or len(model_ids) > 5:
        return {"error": "Please provide 2-5 model IDs for comparison"}

    from models import LLMLeaderboardScore
    from aggregate_summaries import live_aggregate_leaderboard

    org_context = get_org_context_from_request(request)
    project_ids = _filter_accessible_project_ids(db, current_user, project_ids, org_context)

    models_db = db.query(LLMModel).filter(LLMModel.id.in_(model_ids)).all()
    model_info = {m.id: {"name": m.name, "provider": m.provider} for m in models_db}

    scope_key = _project_scope_key_for_request(project_ids, current_user)

    model_averages: Dict[str, Dict[str, float]] = {m_id: {} for m_id in model_ids}
    all_metrics: set = set()

    if scope_key is not None:
        rows = (
            db.query(LLMLeaderboardScore)
            .filter(
                LLMLeaderboardScore.project_scope_key == scope_key,
                LLMLeaderboardScore.period == period,
                LLMLeaderboardScore.model_id.in_(model_ids),
                LLMLeaderboardScore.metric != "average",
            )
            .all()
        )
        for r in rows:
            if r.score is None:
                continue
            model_averages[r.model_id][r.metric] = round(r.score, 4)
            all_metrics.add(r.metric)
    else:
        live_rows = live_aggregate_leaderboard(db, project_ids, period, None)
        for r in live_rows:
            if r["model_id"] not in model_ids or r["metric"] == "average":
                continue
            score = r["score"]
            if score is None:
                continue
            model_averages[r["model_id"]][r["metric"]] = round(score, 4)
            all_metrics.add(r["metric"])

    common_metrics = sorted(
        m
        for m in all_metrics
        if all(m in model_averages.get(mid, {}) for mid in model_ids)
    )

    comparison: Dict[str, Dict[str, Any]] = {}
    for m in sorted(all_metrics):
        comparison[m] = {}
        values = []
        for mid in model_ids:
            val = model_averages.get(mid, {}).get(m)
            comparison[m][mid] = val
            if val is not None:
                values.append((mid, val))
        if values:
            winner = max(values, key=lambda x: x[1])
            comparison[m]["_winner"] = winner[0]

    return {
        "models": {
            mid: {
                "info": model_info.get(
                    mid,
                    {"name": mid, "provider": detect_provider_from_model_id(mid)},
                ),
                "metrics": model_averages.get(mid, {}),
            }
            for mid in model_ids
        },
        "common_metrics": common_metrics,
        "all_metrics": sorted(list(all_metrics)),
        "comparison": comparison,
        "significance": {},
        "significance_available": False,
        "filters": {"model_ids": model_ids, "project_ids": project_ids or [], "period": period},
    }
