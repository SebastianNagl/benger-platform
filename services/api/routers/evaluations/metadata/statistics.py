"""Comprehensive statistics computation endpoint."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


@router.post("/projects/{project_id}/statistics", response_model=StatisticsResponse)
async def compute_project_statistics(
    http_request: Request,
    project_id: str,
    request: StatisticsRequest,
    db: AsyncSession = Depends(get_async_db),
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
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(http_request)
        if not await check_project_accessible_async(db, current_user, project_id, org_context):
            raise HTTPException(status_code=403, detail="Access denied")

        warnings: List[str] = []

        # Get all completed evaluations for the project
        evaluations = (
            (
                await db.execute(
                    select(DBEvaluationRun).where(
                        DBEvaluationRun.project_id == project_id,
                        DBEvaluationRun.status == "completed",
                    )
                )
            )
            .scalars()
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
        # This is the authoritative data source for per-sample, per-model scores.
        # Metrics are projected through the shared "lite" expression
        # (routers/evaluations/metrics_lite.py): statistics only ever extracts
        # numeric values via `_coerce_metric_value`, but the full column drags
        # the judge rubric/justification prose along — ZJS-scale projects carry
        # ~140 MB of metrics JSON, and hydrating that per request OOM-killed
        # both prod api pods on 2026-07-23 when two evaluation pages loaded
        # concurrently.
        from routers.evaluations.metrics_lite import metrics_lite_expr

        generation_sample_results_q = (
            select(
                TaskEvaluation.task_id,
                TaskEvaluation.field_name,
                TaskEvaluation.evaluation_config_id,
                metrics_lite_expr(),
                Generation.model_id,
            )
            .join(
                Generation,
                TaskEvaluation.generation_id == Generation.id,
            )
            .where(
                TaskEvaluation.evaluation_id.in_(evaluation_ids),
            )
        )
        if request.evaluation_config_ids:
            generation_sample_results_q = generation_sample_results_q.where(
                TaskEvaluation.evaluation_config_id.in_(request.evaluation_config_ids)
            )
        generation_sample_results = (await db.execute(generation_sample_results_q)).all()

        # Query annotation-based evaluation results.
        # IMPORTANT: import the SQLAlchemy User model from `models`, not the
        # Pydantic AuthUser from `auth_module` — the latter has no ORM
        # columns, so `DBUser.username` raises AttributeError when used in
        # a query, returning 500 from /statistics. Mirrors the precedent
        # at metadata.py:208.
        from models import User as DBUser
        from types import SimpleNamespace

        annotation_eval_results_q = (
            select(
                TaskEvaluation.task_id,
                TaskEvaluation.field_name,
                TaskEvaluation.evaluation_config_id,
                metrics_lite_expr(),
                TaskEvaluation.annotation_id,
            )
            .where(
                TaskEvaluation.evaluation_id.in_(evaluation_ids),
                TaskEvaluation.generation_id == None,  # noqa: E711
                TaskEvaluation.annotation_id != None,  # noqa: E711
            )
        )
        if request.evaluation_config_ids:
            annotation_eval_results_q = annotation_eval_results_q.where(
                TaskEvaluation.evaluation_config_id.in_(request.evaluation_config_ids)
            )
        annotation_eval_results = (await db.execute(annotation_eval_results_q)).all()

        # Build annotator name map and merge results — apply pseudonym
        # rule so user-facing model_id matches the leaderboard.
        sample_results = list(generation_sample_results)
        if annotation_eval_results:
            annotation_ids = list(set(r.annotation_id for r in annotation_eval_results if r.annotation_id))
            if annotation_ids:
                annotations_with_users = (
                    await db.execute(
                        select(
                            Annotation.id,
                            DBUser.username,
                            DBUser.name,
                            DBUser.pseudonym,
                            DBUser.use_pseudonym,
                        )
                        .join(DBUser, Annotation.completed_by == DBUser.id)
                        .where(Annotation.id.in_(annotation_ids))
                    )
                ).all()
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
                select(
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
                .where(TaskEvaluation.evaluation_id.in_(evaluation_ids))
            )
            if request.evaluation_config_ids:
                multirun_q = multirun_q.where(
                    TaskEvaluation.evaluation_config_id.in_(request.evaluation_config_ids)
                )
            multirun_rows = (await db.execute(multirun_q)).all()

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
