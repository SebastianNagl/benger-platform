"""Evaluation results read endpoints plus the `_resolve_scope_block`
helper.

`_resolve_scope_block` lives here (not in `_common`) because only
`get_evaluation_run_results` calls it; co-locating keeps
`patch("routers.evaluations.multi_field.results.<name>")` reaching both.
"""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


async def _resolve_scope_block(
    db: AsyncSession,
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
            await db.execute(
                select(DBUser.id, DBUser.username, DBUser.name, DBUser.pseudonym, DBUser.use_pseudonym)
                .where(DBUser.id.in_(annotator_user_ids))
            )
        ).all()
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



@router.get("/run/results/project/{project_id}")
async def get_project_evaluation_results(
    project_id: str,
    request: Request,
    latest_only: bool = Query(True, description="Return only the most recent evaluation"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
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
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        # Check access permissions
        org_context = get_org_context_from_request(request)
        if not await auth_service.check_project_access_async(
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
            (
                await db.execute(
                    select(DBEvaluationRun)
                    .where(DBEvaluationRun.project_id == project_id)
                    .order_by(DBEvaluationRun.created_at.desc())
                )
            )
            .scalars()
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
                sample_results_count = int(
                    (
                        await db.execute(
                            select(func.count())
                            .select_from(TaskEvaluation)
                            .where(TaskEvaluation.evaluation_id == evaluation.id)
                        )
                    ).scalar()
                    or 0
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
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get detailed evaluation results.

    Returns per-field-combination scores grouped by evaluation config.
    """
    try:
        eval_result = await db.execute(
            select(DBEvaluationRun).where(DBEvaluationRun.id == evaluation_id)
        )
        evaluation = eval_result.scalar_one_or_none()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        # Check project access
        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, evaluation.project_id, org_context):
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
                    await db.execute(
                        select(
                            EvaluationJudgeRun.id,
                            _sa_func.count(TaskEvaluation.id).label("n"),
                        )
                        .outerjoin(TaskEvaluation, TaskEvaluation.judge_run_id == EvaluationJudgeRun.id)
                        .where(EvaluationJudgeRun.evaluation_id == evaluation.id)
                        .group_by(EvaluationJudgeRun.id)
                    )
                ).all()
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
            "scope": await _resolve_scope_block(db, eval_metadata),
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
