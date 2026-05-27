"""
Evaluation metadata, statistics, and significance endpoints.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

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
    # Issue #111: scope statistics to one or more evaluation_configs. When
    # provided, only TaskEvaluation rows whose ``evaluation_config_id``
    # matches are included in sample-level aggregations and the four
    # ``*_by_model_metric`` composite-keyed dicts. When None / empty all
    # configs are included (legacy behavior).
    evaluation_config_ids: Optional[List[str]] = None


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
    """Statistics for a single field across metrics.

    Issue #111: the encoded ``"{cfg_id}|{pred}|{ref}"`` string that the
    workers historically wrote into ``TaskEvaluation.field_name`` is now
    parsed server-side and exposed as discrete fields so the UI never has
    to split the string itself. ``display_name`` is sourced from
    ``project.evaluation_config.evaluation_configs[*].display_name`` and
    falls back to the raw ``field_name`` when no matching config is found
    (legacy bare-name rows). The outer dict key in
    ``StatisticsResponse.by_field`` remains the raw ``field_name`` string
    — kept as a stable identifier for client-side sort / expand state.
    """

    evaluation_config_id: Optional[str] = None
    prediction_field: Optional[str] = None
    reference_field: Optional[str] = None
    display_name: str
    metrics: Dict[str, MetricStatistics]
    sample_count: int


class RawScore(BaseModel):
    """Raw score for a single sample (for box plots).

    Issue #111: ``evaluation_config_id`` carries the new column directly
    so the UI can filter per-config without parsing ``field_name``. May be
    ``None`` for legacy rows that pre-date the column.
    """

    task_id: Optional[str] = None
    model_id: str
    field_name: Optional[str] = None
    evaluation_config_id: Optional[str] = None
    metric: str
    value: float


class RunsAggregate(BaseModel):
    """Cross-run aggregate for a (target_model, metric) pair (multi-run feature).

    `n_runs` counts distinct EvaluationJudgeRun children that produced rows
    for this metric. mean_of_means / std_of_means / CI summarize the per-run
    means; when only one run is present the CI bounds collapse to None and
    std_of_means to 0. Numeric metrics only — categorical metrics surface
    `null` here and use the agreement_by_metric block instead.
    """

    n_runs: int
    mean_of_means: Optional[float] = None
    std_of_means: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None


class TaskConsistency(BaseModel):
    """Per-task consistency for a (target_model, metric) pair across runs.

    For numeric metrics: variance across runs of the same task. For
    categorical / boolean (passed/failed, choice): Fleiss kappa. For text:
    omitted (frontend renders "—"). Sorted ascending by task_id.
    """

    task_id: str
    n_runs: int
    variance: Optional[float] = None
    fleiss_kappa: Optional[float] = None
    percent_agreement: Optional[float] = None


class JudgeAgreement(BaseModel):
    """Inter-judge agreement for a (target_model, metric) pair.

    Only returned when ≥2 distinct judge_model_ids produced rows for the
    metric. Pairwise Cohen's kappa keys are "judgeA__judgeB" strings; Pearson
    correlation is computed when scores are numeric.
    """

    n_judges: int
    n_items: int
    fleiss_kappa: Optional[float] = None
    cohens_kappa_pairwise: Dict[str, float] = {}
    pearson_r_pairwise: Dict[str, float] = {}
    percent_agreement: Optional[float] = None
    mean_absolute_deviation: Optional[float] = None


class PerRunMean(BaseModel):
    """Per-judge_run aggregate mean for a (target_model, metric) pair.

    Used by the EvaluationResults "By run" chart toggle: one entry per
    (judge_model_id, run_index) with the mean score across that run's tasks.
    Lets the chart split into one series per run.
    """

    judge_run_id: str
    judge_model_id: Optional[str] = None
    run_index: int
    mean: float
    n_tasks: int


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
    # Multi-run aggregates (migration 042). Keys are
    # ``"model_id|config_id|metric"`` (issue #111 — was ``"model_id|metric"``
    # before, but multiple ``evaluation_configs`` of the same metric type
    # would collapse into a single bucket and hide cross-config variance).
    # ``config_id`` is the literal string ``"unknown"`` for rows that
    # pre-date the dedicated column (legacy bare-name ``field_name``).
    # Always present in the response shape; values default to n_runs=1 with
    # null variance fields for legacy single-run evaluations.
    runs_by_model_metric: Optional[Dict[str, RunsAggregate]] = None
    task_consistency_by_model_metric: Optional[Dict[str, List[TaskConsistency]]] = None
    judge_agreement_by_model_metric: Optional[Dict[str, JudgeAgreement]] = None
    # Per-run means keyed on ``"model_id|config_id|metric"`` → list of
    # (judge_run_id, judge_model_id, run_index, mean, n_tasks). Used by the
    # "By run" chart toggle to split a single bar into one bar per run.
    per_run_means_by_model_metric: Optional[Dict[str, List[PerRunMean]]] = None
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

        # Discover annotator-based models from annotation evaluations.
        # Resolve display name via leaderboard's pseudonym rule
        # (benger_extended/api/routers/leaderboards_human.py:168) so
        # use_pseudonym=true users appear under their pseudonym instead
        # of their real name/username.
        from models import User as DBUser
        # synthetic_id ("annotator:{display}") -> display_name. Kept keyed by
        # the public synthetic id because eval_runs the worker writes carry
        # this exact shape as `eval_run.model_id`; downstream display sites
        # (evaluations/page.tsx, reports/[id]/page.tsx, EvaluationResults.tsx)
        # also strip this prefix to render the annotator name. Changing the
        # on-wire shape would cascade into all of those.
        annotator_models: dict[str, str] = {}
        # synthetic_id -> [user_id, ...]. A list, not a single id, so two
        # distinct users with coincidentally identical display names (e.g.
        # both pseudonym='X') don't silently overwrite each other. The
        # response builder later emits one row per user_id, all sharing the
        # same `model_id` but each carrying its own `user_id`. Picker keys
        # on `user_id`, so dispatch is unambiguous; aggregated stats still
        # collapse by display (pre-existing behavior — eval_runs don't
        # disambiguate by user).
        annotator_user_ids: dict[str, list[str]] = {}
        annotation_evals = (
            db.query(DBUser.id, DBUser.username, DBUser.name, DBUser.pseudonym, DBUser.use_pseudonym)
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
        for user_id, username, name, pseudonym, use_pseudonym in annotation_evals.all():
            display = pseudonym if (use_pseudonym and pseudonym) else (name or username)
            synthetic_id = f"annotator:{display}"
            annotator_models[synthetic_id] = f"Annotator: {display}"
            # Dedupe: `.distinct()` is on the full tuple, so a user whose
            # username/name/pseudonym changed over time can appear in
            # multiple rows. Append-only would duplicate the user_id and
            # produce two identical response rows.
            existing = annotator_user_ids.setdefault(synthetic_id, [])
            if user_id not in existing:
                existing.append(user_id)

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

        # Filter out artifacts: "unknown" (legacy), "immediate" (replaced by
        # annotator entries), the human-graded singleton run's pseudo model id
        # ("human"), and any pre-singleton orphan runs ("human:<uid>"). The
        # actual solver columns surface naturally via models_with_evaluation_results
        # (LLM models that produced the answers being graded) or via the
        # synthetic annotator: entries above.
        all_model_ids = [
            m for m in all_model_ids
            if m not in ("unknown", "immediate", "human")
            and not (isinstance(m, str) and m.startswith("human:"))
        ]

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
                from routers.evaluations.results import _coerce_metric_value

                for metric_name, value in eval.metrics.items():
                    coerced = _coerce_metric_value(value)
                    if coerced is not None:
                        eval_data[model_id]["all_scores"].append(coerced)

        # Build result list. Annotator rows expand into one entry per
        # underlying user_id so two distinct users sharing a display name
        # surface as two pickable rows in the eval modal (otherwise the
        # second user_id would silently overwrite the first and the
        # annotator-scoped dispatch would target the wrong person).
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

            is_annotator = model_id in annotator_models
            display_name = annotator_models.get(model_id, model_id)
            # For annotators, iterate the user_id list (one row per user).
            # For non-annotators, the loop runs exactly once with user_id=None.
            user_ids: list[Optional[str]] = (
                list(annotator_user_ids.get(model_id, []))
                if is_annotator
                else [None]
            )

            for uid in user_ids:
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
                    # D2: only emit user_id key for annotator rows so non-annotator
                    # rows aren't cluttered with a redundant null field.
                    **({"user_id": uid} if is_annotator and uid else {}),
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

        # Build method result map: method_name -> {count, last_run}.
        #
        # Counts the number of *actual scored TaskEvaluation rows* per metric
        # for this project — not the number of historical EvaluationRun rows
        # that ever referenced the metric in their aggregated summary.
        # The old approach inflated counts (e.g. korrektur_falloesung showing
        # 550 even with 0 scored rows); see results.py:_build_field_results
        # for the matching read-side shim.
        from models import TaskEvaluation
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB

        raw_counts = (
            db.query(
                func.jsonb_object_keys(cast(TaskEvaluation.metrics, JSONB)).label("metric"),
                func.count().label("cnt"),
                func.max(TaskEvaluation.created_at).label("last_run"),
            )
            .join(DBEvaluationRun, DBEvaluationRun.id == TaskEvaluation.evaluation_id)
            .filter(DBEvaluationRun.project_id == project_id)
            .group_by("metric")
            .all()
        )

        # Drop sidekey/derivation noise so the dropdown only shows real metric
        # names (no `_details`, `_raw`, `raw_score`, etc.).
        _SUFFIX_NOISE = ("_details", "_raw", "_passed", "_grade_points", "_response")
        _EXCLUDED_KEYS = {"raw_score", "error"}
        method_results = {
            r.metric: {"count": r.cnt, "last_run": r.last_run}
            for r in raw_counts
            if r.metric
            and r.metric not in _EXCLUDED_KEYS
            and not r.metric.endswith(_SUFFIX_NOISE)
        }

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
    metrics: List[str] = Query(..., description="One or more metric names. Pass repeatedly: ?metrics=bleu&metrics=rouge_l"),
    evaluation_config_ids: Optional[List[str]] = Query(
        None,
        description="Optional list of evaluation_config_ids to scope the series; when omitted, all configs that produced rows for the requested metrics are included.",
    ),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
) -> dict:
    """
    Get historical evaluation data for trend charts.

    Issue #111: aggregates ``TaskEvaluation`` rows by
    ``(day, model_id, evaluation_config_id, metric)`` and emits one series
    per ``(metric, evaluation_config_id)`` pair so multiple configs of the
    same metric type render as distinct lines. ``display_name`` is sourced
    from ``project.evaluation_config.evaluation_configs[*].display_name``
    when available and falls back to a formatted metric name.

    Response::

        {
            "series": [
                {
                    "metric": "bleu",
                    "evaluation_config_id": "cfg-abc",
                    "display_name": "BLEU (3-gram)",
                    "data": [
                        {"date": "2026-05-01", "model_id": "gpt-4",
                         "value": 0.82, "ci_lower": 0.78,
                         "ci_upper": 0.86, "sample_count": 42},
                        ...
                    ],
                },
                ...
            ]
        }
    """
    try:
        from models import TaskEvaluation, Generation
        from routers.evaluations.results import _coerce_metric_value
        from routers.leaderboards import calculate_confidence_interval
        from collections import defaultdict

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

        # Build the project's evaluation_config lookup once so per-series
        # display names resolve cleanly. Robust to missing / malformed
        # evaluation_config payloads (legacy projects keep the field at
        # NULL until the first generation_config save).
        cfg_by_id: Dict[str, dict] = {}
        if isinstance(project.evaluation_config, dict):
            for cfg in (project.evaluation_config.get("evaluation_configs") or []):
                if isinstance(cfg, dict):
                    cfg_id = cfg.get("id")
                    if cfg_id:
                        cfg_by_id[cfg_id] = cfg

        # Build date filters
        date_filters = []
        if start_date:
            date_filters.append(DBEvaluationRun.created_at >= datetime.fromisoformat(start_date))
        if end_date:
            date_filters.append(DBEvaluationRun.created_at <= datetime.fromisoformat(end_date))

        # Query TaskEvaluation rows joined through Generation for the model
        # axis and through EvaluationRun for the date axis and project /
        # status filters. We pull TaskEvaluation.metrics (the per-sample
        # dict) and coerce the numeric value per-metric in Python.
        q = (
            db.query(
                DBEvaluationRun.created_at,
                Generation.model_id,
                TaskEvaluation.evaluation_config_id,
                TaskEvaluation.metrics,
            )
            .join(Generation, TaskEvaluation.generation_id == Generation.id)
            .join(DBEvaluationRun, TaskEvaluation.evaluation_id == DBEvaluationRun.id)
            .filter(
                DBEvaluationRun.project_id == project_id,
                Generation.model_id.in_(model_ids),
                DBEvaluationRun.status == "completed",
                *date_filters,
            )
        )
        # `evaluation_config_ids` defaults to FastAPI's Query(None) sentinel,
        # which is truthy when this handler is called directly from tests
        # (FastAPI resolves it to None in the request path). Guard against the
        # sentinel leaking into the SQL `IN (...)` clause.
        if isinstance(evaluation_config_ids, list) and evaluation_config_ids:
            q = q.filter(TaskEvaluation.evaluation_config_id.in_(evaluation_config_ids))
        rows = q.all()

        # Bucket: {(date_str, model_id, cfg_id, metric): [floats]}.
        # cfg_id may be None for legacy rows that pre-date the column —
        # those collapse into a single ``evaluation_config_id=None`` series.
        buckets: Dict[tuple, List[float]] = defaultdict(list)
        for row in rows:
            metrics_dict = row.metrics or {}
            if not isinstance(metrics_dict, dict):
                continue
            if not row.created_at:
                continue
            date_str = row.created_at.date().isoformat()
            for metric_name in metrics:
                val = _coerce_metric_value(metrics_dict.get(metric_name))
                if val is None:
                    continue
                buckets[(date_str, row.model_id, row.evaluation_config_id, metric_name)].append(
                    float(val)
                )

        # Group buckets into series keyed by (metric, evaluation_config_id).
        series_map: Dict[tuple, List[dict]] = defaultdict(list)
        for (date_str, model_id, cfg_id, metric_name), values in buckets.items():
            if not values:
                continue
            mean_val = sum(values) / len(values)
            ci_lower, ci_upper, _ = calculate_confidence_interval(values)
            series_map[(metric_name, cfg_id)].append(
                {
                    "date": date_str,
                    "model_id": model_id,
                    "value": round(float(mean_val), 4),
                    "ci_lower": round(ci_lower, 4) if ci_lower is not None else None,
                    "ci_upper": round(ci_upper, 4) if ci_upper is not None else None,
                    "sample_count": len(values),
                }
            )

        # Emit one series per (metric, evaluation_config_id) pair, sorted
        # by date inside each series so chart consumers don't have to
        # re-sort. Series order is deterministic ((metric, cfg_id)
        # lexicographic) so snapshot tests stay stable.
        series: List[dict] = []
        for (metric_name, cfg_id) in sorted(
            series_map.keys(), key=lambda k: (k[0], k[1] or "")
        ):
            cfg = cfg_by_id.get(cfg_id) if cfg_id else None
            display_name = (
                (cfg.get("display_name") if cfg else None)
                or metric_name.replace("_", " ").title()
            )
            data_points = sorted(series_map[(metric_name, cfg_id)], key=lambda p: p["date"])
            series.append(
                {
                    "metric": metric_name,
                    "evaluation_config_id": cfg_id,
                    "display_name": display_name,
                    "data": data_points,
                }
            )

        return {"series": series}

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
    evaluation_config_ids: Optional[List[str]] = Query(
        None,
        description="Optional evaluation_config_ids to scope the comparison; when set, the run-level direct_evaluations fallback is skipped (run-aggregated metrics cannot be filtered by config_id).",
    ),
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
        sample_results_q = (
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
        )
        # Issue #111: scope by evaluation_config_id when requested.
        # Guard against FastAPI's Query(None) sentinel leaking through when
        # this handler is called directly from tests (see /history above).
        if isinstance(evaluation_config_ids, list) and evaluation_config_ids:
            sample_results_q = sample_results_q.filter(
                TaskEvaluation.evaluation_config_id.in_(evaluation_config_ids)
            )
        sample_results = sample_results_q.all()

        # Collect scores from sample results
        for result in sample_results:
            model_id = result.model_id
            if model_id not in model_metric_scores:
                continue
            if not result.metrics:
                continue

            from routers.evaluations.results import _coerce_metric_value
            for metric in metrics:
                if metric in result.metrics:
                    coerced = _coerce_metric_value(result.metrics[metric])
                    if coerced is not None:
                        model_metric_scores[model_id][metric].append(coerced)

        # Also check direct evaluations for backwards compatibility — but
        # skip when an explicit evaluation_config_ids filter is set. Run-
        # level ``EvaluationRun.metrics`` are aggregated across configs
        # and cannot be re-scoped retroactively; mixing them in would
        # silently leak cross-config data into a per-config comparison.
        # ``not Query(None)`` is False (Query() is a truthy sentinel), so
        # this branch correctly runs when called via FastAPI without the
        # param. Tests calling directly with ``evaluation_config_ids=None``
        # also fall through here.
        if not (isinstance(evaluation_config_ids, list) and evaluation_config_ids):
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

                from routers.evaluations.results import _coerce_metric_value  # noqa: F402
                for metric in metrics:
                    if metric in eval.metrics:
                        coerced = _coerce_metric_value(eval.metrics[metric])
                        if coerced is not None:
                            model_metric_scores[eval.model_id][metric].append(coerced)

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
        import numpy as np

        from models import TaskEvaluation, Generation
        from routers.leaderboards import (
            STATS_AVAILABLE,
            calculate_confidence_interval,
            calculate_significance,
        )
        from bg_statistics import (
            cliffs_delta as _cliffs_delta,
            cohens_d as _cohens_d,
            pearson as _pearson,
        )

        if STATS_AVAILABLE:
            from scipy import stats as scipy_stats  # noqa: F401  (kept for any inline downstream uses)

        def compute_cohens_d(values_a: List[float], values_b: List[float]) -> dict:
            return _cohens_d(values_a, values_b)

        def compute_cliffs_delta(values_a: List[float], values_b: List[float]) -> dict:
            return _cliffs_delta(values_a, values_b)

        def compute_correlation(
            metric_values: Dict[str, List[float]]
        ) -> Dict[str, Dict[str, Optional[float]]]:
            metrics = list(metric_values.keys())
            result: Dict[str, Dict[str, Optional[float]]] = {}
            for m1 in metrics:
                result[m1] = {}
                for m2 in metrics:
                    if m1 == m2:
                        result[m1][m2] = 1.0
                    else:
                        result[m1][m2] = _pearson(metric_values[m1], metric_values[m2])
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

        # Issue #111: cache the project's evaluation_configs lookup once so
        # FieldStatistics can resolve human-friendly display names from
        # config ids without hitting the DB per-row.
        cfg_by_id: Dict[str, dict] = {}
        if isinstance(project.evaluation_config, dict):
            for cfg in (project.evaluation_config.get("evaluation_configs") or []):
                if isinstance(cfg, dict):
                    cfg_id = cfg.get("id")
                    if cfg_id:
                        cfg_by_id[cfg_id] = cfg

        # Query sample results with model information (handles N:M field evaluations)
        # This is the authoritative data source for per-sample, per-model scores
        generation_sample_results_q = (
            db.query(
                TaskEvaluation.task_id,
                TaskEvaluation.field_name,
                TaskEvaluation.evaluation_config_id,
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
        )
        if request.evaluation_config_ids:
            generation_sample_results_q = generation_sample_results_q.filter(
                TaskEvaluation.evaluation_config_id.in_(request.evaluation_config_ids)
            )
        generation_sample_results = generation_sample_results_q.all()

        # Query annotation-based evaluation results.
        # IMPORTANT: import the SQLAlchemy User model from `models`, not the
        # Pydantic AuthUser from `auth_module` — the latter has no ORM
        # columns, so `DBUser.username` raises AttributeError when used in
        # a query, returning 500 from /statistics. Mirrors the precedent
        # at metadata.py:208.
        from models import User as DBUser
        from types import SimpleNamespace

        annotation_eval_results_q = (
            db.query(
                TaskEvaluation.task_id,
                TaskEvaluation.field_name,
                TaskEvaluation.evaluation_config_id,
                TaskEvaluation.metrics,
                TaskEvaluation.annotation_id,
            )
            .filter(
                TaskEvaluation.evaluation_id.in_(evaluation_ids),
                TaskEvaluation.generation_id == None,  # noqa: E711
                TaskEvaluation.annotation_id != None,  # noqa: E711
            )
        )
        if request.evaluation_config_ids:
            annotation_eval_results_q = annotation_eval_results_q.filter(
                TaskEvaluation.evaluation_config_id.in_(request.evaluation_config_ids)
            )
        annotation_eval_results = annotation_eval_results_q.all()

        # Build annotator name map and merge results — apply pseudonym
        # rule so user-facing model_id matches the leaderboard.
        sample_results = list(generation_sample_results)
        if annotation_eval_results:
            annotation_ids = list(set(r.annotation_id for r in annotation_eval_results if r.annotation_id))
            if annotation_ids:
                annotations_with_users = (
                    db.query(
                        Annotation.id,
                        DBUser.username,
                        DBUser.name,
                        DBUser.pseudonym,
                        DBUser.use_pseudonym,
                    )
                    .join(DBUser, Annotation.completed_by == DBUser.id)
                    .filter(Annotation.id.in_(annotation_ids))
                    .all()
                )
                annotator_name_map = {
                    a.id: (
                        a.pseudonym
                        if (a.use_pseudonym and a.pseudonym)
                        else (a.name or a.username)
                    )
                    for a in annotations_with_users
                }

                for r in annotation_eval_results:
                    display = annotator_name_map.get(r.annotation_id, "Unknown")
                    sample_results.append(SimpleNamespace(
                        task_id=r.task_id,
                        field_name=r.field_name,
                        evaluation_config_id=r.evaluation_config_id,
                        metrics=r.metrics,
                        model_id=f"annotator:{display}",
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
        # Issue #111: remember the evaluation_config_id observed alongside
        # each ``field_name`` so we can hydrate the structured
        # FieldStatistics shape without re-parsing the encoded key.
        field_to_cfg_id: Dict[str, Optional[str]] = {}
        raw_scores: List[RawScore] = []

        for result in sample_results:
            if not result.metrics:
                continue

            model_id = result.model_id
            field_name = result.field_name or "default"
            cfg_id = getattr(result, "evaluation_config_id", None)

            # Initialize nested dicts if needed
            if model_id not in model_metric_values:
                model_metric_values[model_id] = {m: [] for m in request.metrics}
            if field_name not in field_metric_values:
                field_metric_values[field_name] = {m: [] for m in request.metrics}
                field_to_cfg_id[field_name] = cfg_id

            from routers.evaluations.results import _coerce_metric_value
            for metric in request.metrics:
                if metric in result.metrics:
                    coerced = _coerce_metric_value(result.metrics[metric])
                    if coerced is not None:
                        float_value = coerced

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
                                    evaluation_config_id=cfg_id,
                                    metric=metric,
                                    value=float_value,
                                )
                            )

        # If no sample results, fall back to evaluation-level metrics.
        # Issue #111: skip this fallback when an explicit evaluation_config
        # filter is set — run-aggregated ``EvaluationRun.metrics`` are not
        # config-scoped and would silently leak cross-config data.
        if not any(overall_metric_values.values()) and not request.evaluation_config_ids:
            from routers.evaluations.results import _coerce_metric_value
            for eval in evaluations:
                if not eval.metrics:
                    continue

                model_id = eval.model_id if eval.model_id != "unknown" else "aggregated"

                if model_id not in model_metric_values:
                    model_metric_values[model_id] = {m: [] for m in request.metrics}

                for metric in request.metrics:
                    if metric in eval.metrics:
                        coerced = _coerce_metric_value(eval.metrics[metric])
                        if coerced is not None:
                            float_value = coerced
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
            # Compute per-field statistics. Issue #111: parse the encoded
            # ``"{cfg_id}|{pred}|{ref}"`` ``field_name`` into discrete
            # components and resolve a human display name from the
            # project's evaluation_configs lookup. The outer dict key
            # stays the raw ``field_name`` so clients keep their stable
            # sort / expand identifier.
            by_field = {}
            for field_name, metric_data in field_metric_values.items():
                field_metrics: Dict[str, MetricStatistics] = {}
                sample_count = 0
                for metric, values in metric_data.items():
                    stats = compute_metric_stats(values, metric)
                    if stats:
                        field_metrics[metric] = stats
                        sample_count = max(sample_count, stats.n)

                if not field_metrics:
                    continue

                # Prefer the column value observed alongside the
                # ``field_name`` (matches the worker's write path 1:1).
                # Fall back to splitting the encoded ``field_name`` when
                # the column is NULL for legacy rows.
                cfg_id: Optional[str] = field_to_cfg_id.get(field_name)
                pred_field: Optional[str] = None
                ref_field: Optional[str] = None
                if "|" in field_name:
                    parts = field_name.split("|", 3)[:3]
                    if cfg_id is None and len(parts) >= 1 and parts[0]:
                        cfg_id = parts[0]
                    if len(parts) >= 2:
                        pred_field = parts[1] or None
                    if len(parts) >= 3:
                        ref_field = parts[2] or None
                display_name = (
                    (cfg_by_id.get(cfg_id, {}).get("display_name") if cfg_id else None)
                    or field_name
                )

                by_field[field_name] = FieldStatistics(
                    evaluation_config_id=cfg_id,
                    prediction_field=pred_field,
                    reference_field=ref_field,
                    display_name=display_name,
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

        # ── Multi-run aggregates (migration 042) ──
        # Pull one row per (target_model, task, metric, judge_model, run_index)
        # via TaskEvaluation → EvaluationJudgeRun → Generation join. Then call
        # the shared statistics helpers to compute cross-run means / stddev /
        # CI, per-task consistency, and inter-judge agreement. Numeric metrics
        # only — categorical metrics surface as null in `runs_by_model_metric`
        # and use the `judge_agreement_by_model_metric` block.
        runs_by_model_metric: Dict[str, RunsAggregate] = {}
        task_consistency_by_model_metric: Dict[str, List[TaskConsistency]] = {}
        judge_agreement_by_model_metric: Dict[str, JudgeAgreement] = {}
        per_run_means_by_model_metric: Dict[str, List[PerRunMean]] = {}

        try:
            from models import EvaluationJudgeRun
            from bg_statistics import (
                compute_agreement,
                confidence_interval,
                stddev,
            )

            # OUTER JOIN Generation so annotation-evaluation rows (where
            # generation_id IS NULL) still flow through. For those rows we use
            # a synthetic "human" target_model_id so the per-(target, metric)
            # grouping still works — the Korrektur-style human grades end up
            # under their own model bucket alongside LLM targets.
            from sqlalchemy import func as _sa_func

            multirun_q = (
                db.query(
                    TaskEvaluation.task_id,
                    TaskEvaluation.metrics,
                    TaskEvaluation.evaluation_config_id,
                    _sa_func.coalesce(Generation.model_id, "human").label("model_id"),
                    EvaluationJudgeRun.id.label("judge_run_id"),
                    EvaluationJudgeRun.judge_model_id,
                    EvaluationJudgeRun.run_index,
                )
                .outerjoin(Generation, TaskEvaluation.generation_id == Generation.id)
                .join(
                    EvaluationJudgeRun,
                    TaskEvaluation.judge_run_id == EvaluationJudgeRun.id,
                )
                .filter(TaskEvaluation.evaluation_id.in_(evaluation_ids))
            )
            if request.evaluation_config_ids:
                multirun_q = multirun_q.filter(
                    TaskEvaluation.evaluation_config_id.in_(request.evaluation_config_ids)
                )
            multirun_rows = multirun_q.all()

            # Index rows by (model_id, config_id, metric, judge_model_id, run_index, task_id)
            # → primary scalar value. Skip rows where the metric value isn't
            # numeric (e.g. judge-error placeholders that store a dict under
            # the metric key with `error: True`). Issue #111: the
            # ``config_id`` axis prevents two ``evaluation_configs`` of the
            # same metric type (e.g. three ``llm_judge_falloesung`` configs
            # with different judges) from collapsing into one bucket.
            from collections import defaultdict

            per_run_per_task: Dict[tuple, Dict[str, float]] = defaultdict(dict)
            judge_models_per_metric: Dict[tuple, set] = defaultdict(set)
            # Map (model_id, config_id, metric, judge_model_id, run_index)
            # → judge_run_id for the per_run_means_by_model_metric block
            # (chart by-run toggle).
            judge_run_id_by_key: Dict[tuple, str] = {}
            for row in multirun_rows:
                metrics_dict = row.metrics or {}
                if not isinstance(metrics_dict, dict):
                    continue
                # Sentinel "unknown" lets legacy bare-name rows (NULL
                # evaluation_config_id) still group cleanly; otherwise the
                # tuple key would carry `None` and the response key would
                # render as `model|None|metric`.
                cfg_id = row.evaluation_config_id or "unknown"
                for metric_name in request.metrics:
                    val = metrics_dict.get(metric_name)
                    if not isinstance(val, (int, float)):
                        continue
                    key = (
                        row.model_id,
                        cfg_id,
                        metric_name,
                        row.judge_model_id,
                        row.run_index,
                    )
                    per_run_per_task[key][row.task_id] = float(val)
                    # Only add to the inter-judge-agreement set when the
                    # judge_model_id is a real string. Deterministic-metric
                    # catch-all judge_runs (and historical rows the
                    # 042-lift missed before migration 044) carry NULL
                    # judge_model_id and would surface as a "None" axis
                    # label on the heatmap if we treated them as a
                    # distinct rater. Per-run aggregates stay correct
                    # because per_run_per_task still records them.
                    if row.judge_model_id:
                        judge_models_per_metric[(row.model_id, cfg_id, metric_name)].add(
                            row.judge_model_id
                        )
                    judge_run_id_by_key[key] = row.judge_run_id

            # Group keys by (model_id, config_id, metric).
            keys_by_mcm: Dict[tuple, List[tuple]] = defaultdict(list)
            for key in per_run_per_task.keys():
                model_id, cfg_id, metric_name, _jm, _ri = key
                keys_by_mcm[(model_id, cfg_id, metric_name)].append(key)

            for (model_id, cfg_id, metric_name), run_keys in keys_by_mcm.items():
                resp_key = f"{model_id}|{cfg_id}|{metric_name}"

                # Cross-run aggregate: one mean per (judge_model, run_index).
                # Track per-key means in parallel so we can emit them under
                # per_run_means_by_model_metric for the chart by-run toggle.
                per_run_means: List[float] = []
                per_run_entries: List[PerRunMean] = []
                for k in run_keys:
                    vals = list(per_run_per_task[k].values())
                    if not vals:
                        continue
                    mean_v = sum(vals) / len(vals)
                    per_run_means.append(mean_v)
                    _mid, _cid, _met, jm, ri = k
                    per_run_entries.append(PerRunMean(
                        judge_run_id=judge_run_id_by_key[k],
                        judge_model_id=jm,
                        run_index=int(ri),
                        mean=round(float(mean_v), 4),
                        n_tasks=len(vals),
                    ))
                n_runs = len(per_run_means)
                if n_runs == 0:
                    continue
                mean_of_means = sum(per_run_means) / n_runs
                std_runs = stddev(per_run_means) if n_runs >= 2 else 0.0
                ci_lo, ci_hi, _ = confidence_interval(per_run_means) if n_runs >= 2 else (None, None, n_runs)
                runs_by_model_metric[resp_key] = RunsAggregate(
                    n_runs=n_runs,
                    mean_of_means=round(float(mean_of_means), 4),
                    std_of_means=round(float(std_runs or 0.0), 4),
                    ci_lower=ci_lo,
                    ci_upper=ci_hi,
                )
                if per_run_entries:
                    per_run_means_by_model_metric[resp_key] = per_run_entries

                # Per-task consistency: variance across the run-keys for the
                # same task. Tasks with <2 runs are skipped (variance undefined).
                if n_runs >= 2:
                    task_to_run_vals: Dict[str, List[float]] = defaultdict(list)
                    for k in run_keys:
                        for tid, v in per_run_per_task[k].items():
                            task_to_run_vals[tid].append(v)
                    consistencies: List[TaskConsistency] = []
                    for tid in sorted(task_to_run_vals.keys()):
                        vals = task_to_run_vals[tid]
                        if len(vals) < 2:
                            continue
                        # numeric variance; agreement metrics only meaningful
                        # for categorical scores which we don't see in this
                        # numeric path (see TODO at the bottom of this block).
                        m = sum(vals) / len(vals)
                        variance = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
                        consistencies.append(TaskConsistency(
                            task_id=tid,
                            n_runs=len(vals),
                            variance=round(variance, 6),
                        ))
                    if consistencies:
                        task_consistency_by_model_metric[resp_key] = consistencies

                # Inter-judge agreement: only when ≥2 distinct judge_model_ids
                # produced rows for this metric. Build (rater, item, score)
                # triples where rater = judge_model_id, item = task_id, score
                # is the per-task mean across that judge's runs.
                judges_for_mm = judge_models_per_metric.get(
                    (model_id, cfg_id, metric_name), set()
                )
                if len(judges_for_mm) >= 2:
                    triples: List[tuple] = []
                    # Aggregate across run_index per judge: mean of that
                    # judge's score for the task.
                    by_judge_task: Dict[tuple, List[float]] = defaultdict(list)
                    for k in run_keys:
                        _mid, _cid, _met, jm, _ri = k
                        # Defense in depth — judges_for_mm is already
                        # filtered above, but a None rater here would
                        # corrupt the kappa / pearson computation.
                        if not jm:
                            continue
                        for tid, v in per_run_per_task[k].items():
                            by_judge_task[(jm, tid)].append(v)
                    for (jm, tid), vals in by_judge_task.items():
                        triples.append((jm, tid, sum(vals) / len(vals)))
                    if triples:
                        report = compute_agreement(triples, score_type="numeric")
                        # Re-key pairwise dicts to "modelA__modelB" strings for
                        # JSON-friendliness (the dataclass uses tuples).
                        pairwise = {f"{a}__{b}": v for (a, b), v in report.pearson_r_pairwise.items()}
                        judge_agreement_by_model_metric[resp_key] = JudgeAgreement(
                            n_judges=report.n_raters,
                            n_items=report.n_items,
                            fleiss_kappa=report.fleiss_kappa,
                            cohens_kappa_pairwise={
                                f"{a}__{b}": v for (a, b), v in report.cohens_kappa_pairwise.items()
                            },
                            pearson_r_pairwise=pairwise,
                            percent_agreement=report.percent_agreement,
                            mean_absolute_deviation=report.mean_absolute_deviation,
                        )
            # NOTE: per-task consistency for categorical / boolean metrics
            # (passed/failed, choice) lives under `judge_agreement_by_model_metric`
            # above when ≥2 judges agree on the same item; for same-judge
            # multi-run, the variance over numeric scores is the right proxy
            # and is what we surface here.
        except Exception as multirun_err:
            logger.exception(f"Multi-run statistics computation failed: {multirun_err}")
            warnings.append(f"multi-run stats unavailable: {multirun_err}")

        return StatisticsResponse(
            aggregation=request.aggregation,
            metrics=metrics_stats,
            by_model=by_model,
            by_field=by_field,
            raw_scores=raw_scores_response,
            pairwise_comparisons=pairwise_comparisons if pairwise_comparisons else None,
            correlations=correlations,
            runs_by_model_metric=runs_by_model_metric or None,
            task_consistency_by_model_metric=task_consistency_by_model_metric or None,
            judge_agreement_by_model_metric=judge_agreement_by_model_metric or None,
            per_run_means_by_model_metric=per_run_means_by_model_metric or None,
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
