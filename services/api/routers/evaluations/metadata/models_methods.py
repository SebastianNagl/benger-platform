"""Evaluated-models and configured-methods metadata endpoints."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


@router.get("/projects/{project_id}/evaluated-models")
async def get_evaluated_models(
    request: Request,
    project_id: str,
    include_configured: bool = Query(
        False, description="Include all configured models from generation_config"
    ),
    db: AsyncSession = Depends(get_async_db),
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

        # Get configured models from generation_config
        configured_models = set()
        if include_configured and project.generation_config:
            selected_config = project.generation_config.get("selected_configuration", {})
            configured_models = set(selected_config.get("models", []))

        # Query all generations for tasks in this project
        generations_query = (
            select(Generation.model_id)
            .join(Task, Generation.task_id == Task.id)
            .where(Task.project_id == project_id)
            .where(Generation.parse_status == "success")
            .distinct()
        )

        models_with_generations = {
            g.model_id for g in (await db.execute(generations_query)).all()
        }

        # Get models with actual evaluation results from TaskEvaluation
        # This correctly handles evaluations where Evaluation.model_id = "unknown"
        # by tracing through generation_id to get the real model_id
        models_from_sample_results = (
            select(Generation.model_id)
            .distinct()
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
                DBEvaluationRun.status == "completed",
            )
        )
        models_with_evaluation_results = {
            m[0] for m in (await db.execute(models_from_sample_results)).all()
        }

        # Also include model IDs from direct evaluations
        # Filter out "unknown" as it's a legacy artifact
        models_from_evaluations = (
            select(DBEvaluationRun.model_id)
            .where(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status == "completed",
                DBEvaluationRun.model_id != "unknown",  # Filter out legacy artifact
            )
            .distinct()
        )
        models_with_evaluations = {
            e.model_id for e in (await db.execute(models_from_evaluations)).all()
        }

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
            select(DBUser.id, DBUser.username, DBUser.name, DBUser.pseudonym, DBUser.use_pseudonym)
            .distinct()
            .join(Annotation, Annotation.completed_by == DBUser.id)
            .join(TaskEvaluation, TaskEvaluation.annotation_id == Annotation.id)
            .join(DBEvaluationRun, TaskEvaluation.evaluation_id == DBEvaluationRun.id)
            .where(
                DBEvaluationRun.project_id == project_id,
                DBEvaluationRun.status == "completed",
                TaskEvaluation.generation_id == None,  # noqa: E711
            )
        )
        for user_id, username, name, pseudonym, use_pseudonym in (
            await db.execute(annotation_evals)
        ).all():
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
            (
                await db.execute(
                    select(DBEvaluationRun).where(
                        DBEvaluationRun.project_id == project_id,
                        DBEvaluationRun.model_id.in_(all_model_ids),
                        DBEvaluationRun.status == "completed",
                    )
                )
            )
            .scalars()
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
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
) -> dict:
    """
    Get all configured evaluation methods for this project with their result status.
    Returns methods from evaluation_config.selected_methods with flags indicating
    whether each method has actual results.
    """
    try:
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
            await db.execute(
                select(
                    func.jsonb_object_keys(cast(TaskEvaluation.metrics, JSONB)).label("metric"),
                    func.count().label("cnt"),
                    func.max(TaskEvaluation.created_at).label("last_run"),
                )
                .join(DBEvaluationRun, DBEvaluationRun.id == TaskEvaluation.evaluation_id)
                .where(DBEvaluationRun.project_id == project_id)
                .group_by("metric")
            )
        ).all()

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
