"""Evaluation-history (trend chart) endpoint."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


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
    db: AsyncSession = Depends(get_async_db),
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
            select(
                DBEvaluationRun.created_at,
                Generation.model_id,
                TaskEvaluation.evaluation_config_id,
                TaskEvaluation.metrics,
            )
            .join(Generation, TaskEvaluation.generation_id == Generation.id)
            .join(DBEvaluationRun, TaskEvaluation.evaluation_id == DBEvaluationRun.id)
            .where(
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
            q = q.where(TaskEvaluation.evaluation_config_id.in_(evaluation_config_ids))
        rows = (await db.execute(q)).all()

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
