"""Pairwise significance-test endpoint."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


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
    db: AsyncSession = Depends(get_async_db),
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
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, project_id, org_context):
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
            select(
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
            .where(
                DBEvaluationRun.project_id == project_id,
                Generation.model_id.in_(model_ids),
            )
        )
        # Issue #111: scope by evaluation_config_id when requested.
        # Guard against FastAPI's Query(None) sentinel leaking through when
        # this handler is called directly from tests (see /history above).
        if isinstance(evaluation_config_ids, list) and evaluation_config_ids:
            sample_results_q = sample_results_q.where(
                TaskEvaluation.evaluation_config_id.in_(evaluation_config_ids)
            )
        sample_results = (await db.execute(sample_results_q)).all()

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
                (
                    await db.execute(
                        select(DBEvaluationRun).where(
                            DBEvaluationRun.project_id == project_id,
                            DBEvaluationRun.model_id.in_(model_ids),
                            DBEvaluationRun.model_id != "unknown",  # Exclude legacy artifacts
                        )
                    )
                )
                .scalars()
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
