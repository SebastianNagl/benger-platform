"""
By-task-model results, project-level aggregation, and sample-result endpoints.

The local data-availability / preview helpers (`_get_task_data_availability`,
`_task_preview_rows`, `_build_all_tasks_response`) live HERE — not in
`_common` — because they are used only by handlers in this submodule, and
`_build_all_tasks_response` calls the other two internally. Co-locating them
means a test that patches `_get_task_data_availability` on this module
reaches both the handler's direct call and the helper's internal call.
"""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


@router.get("/{evaluation_id}/results/by-task-model")
async def get_results_by_task_model(
    evaluation_id: str,
    request: Request,
    include_history: bool = Query(
        False,
        description=(
            "When false (default), each (task, model/annotator) cell shows the "
            "latest score. When true, human-graded runs (e.g. korrektur_falloesung) "
            "show the mean across all grading scores for that cell — exposing the "
            "history that's preserved when multiple correctors grade the same target. "
            "LLM-driven runs are unaffected by this flag."
        ),
    ),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get evaluation results grouped by task and model.

    Returns a matrix of scores for each task-model combination,
    enabling detailed comparison of model performance across tasks.
    """
    try:
        from models import TaskEvaluation
        from models import Generation as GenerationModel
        from models import LLMModel

        # Verify evaluation exists
        eval_result = await db.execute(
            select(DBEvaluationRun).where(DBEvaluationRun.id == evaluation_id)
        )
        evaluation = eval_result.scalar_one_or_none()
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation '{evaluation_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, evaluation.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # `include_history` controls cell aggregation:
        #   off  → cell shows the score of the LATEST generation per (task,
        #          model) only (the user's mental model: "what are the
        #          current results"). For human-graded runs, "latest" means
        #          the most recently appended grade row.
        #   on   → cell shows the arithmetic mean across all historical
        #          rows for that (task, model) — multiple generations for
        #          LLM runs, or multiple correctors for human runs.
        # Without this, three historical gpt-5.4 generations contributed
        # 24 rows to a single cell average (8 metrics × 3 gens) silently.
        aggregate_mean = include_history

        if aggregate_mean:
            # Fetch all eval rows; cell_scores collector below averages them.
            sample_results = (
                await db.execute(
                    select(
                        TaskEvaluation.task_id,
                        TaskEvaluation.metrics,
                        TaskEvaluation.passed,
                        TaskEvaluation.generation_id,
                        GenerationModel.model_id,
                    )
                    .join(
                        GenerationModel,
                        TaskEvaluation.generation_id == GenerationModel.id,
                    )
                    .where(TaskEvaluation.evaluation_id == evaluation_id)
                )
            ).all()
        else:
            # Two-step dedup:
            # 1. latest_gen_id per (task_id, model_id) — picks the single
            #    most recent generation that should drive the cell.
            # 2. latest eval per (generation_id, field_name) within the set
            #    of latest gens — picks the freshest eval if a gen was
            #    re-evaluated.
            #
            # Without step 1, the previous implementation kept the latest
            # eval of EVERY historical generation, then averaged them all
            # into the cell (silently — the user expected "latest only").
            latest_gen = (
                select(
                    GenerationModel.id.label("gen_id"),
                    func.row_number()
                    .over(
                        partition_by=[GenerationModel.task_id, GenerationModel.model_id],
                        order_by=GenerationModel.created_at.desc(),
                    )
                    .label("rn"),
                )
                .where(GenerationModel.status == "completed")
                .subquery()
            )
            latest_gen_ids = (
                select(latest_gen.c.gen_id).where(latest_gen.c.rn == 1).subquery()
            )

            ranked_results = (
                select(
                    TaskEvaluation.task_id,
                    TaskEvaluation.metrics,
                    TaskEvaluation.passed,
                    TaskEvaluation.generation_id,
                    GenerationModel.model_id,
                    func.row_number()
                    .over(
                        partition_by=[TaskEvaluation.generation_id, TaskEvaluation.field_name],
                        order_by=TaskEvaluation.created_at.desc(),
                    )
                    .label("rn"),
                )
                .join(
                    GenerationModel,
                    TaskEvaluation.generation_id == GenerationModel.id,
                )
                .where(
                    TaskEvaluation.evaluation_id == evaluation_id,
                    TaskEvaluation.generation_id.in_(select(latest_gen_ids.c.gen_id)),
                )
                .subquery()
            )
            sample_results = (
                await db.execute(
                    select(
                        ranked_results.c.task_id,
                        ranked_results.c.metrics,
                        ranked_results.c.passed,
                        ranked_results.c.generation_id,
                        ranked_results.c.model_id,
                    )
                    .where(ranked_results.c.rn == 1)
                )
            ).all()

        # Query 2: Get annotation-based evaluation results.
        # Same latest-only / mean-of-all symmetry as the generation
        # branch: when include_history is off, scope to the LATEST
        # annotation per (task_id, completed_by) before joining evals.
        # If a task has a fresh annotation that hasn't been evaluated
        # yet, this leaves the cell empty (rendered as n/a) instead of
        # silently surfacing an evaluation of an older annotation —
        # which is what the user explicitly asked for.
        from models import User as DBUser

        if aggregate_mean:
            annotation_eval_results = (
                await db.execute(
                    select(
                        TaskEvaluation.task_id,
                        TaskEvaluation.annotation_id,
                        TaskEvaluation.field_name,
                        TaskEvaluation.metrics,
                        TaskEvaluation.created_at,
                    )
                    .where(
                        TaskEvaluation.evaluation_id == evaluation_id,
                        TaskEvaluation.generation_id == None,  # noqa: E711
                        TaskEvaluation.annotation_id != None,  # noqa: E711
                    )
                )
            ).all()
        else:
            latest_ann = (
                select(
                    Annotation.id.label("ann_id"),
                    func.row_number()
                    .over(
                        partition_by=[Annotation.task_id, Annotation.completed_by],
                        order_by=Annotation.created_at.desc(),
                    )
                    .label("rn"),
                )
                .where(
                    Annotation.completed_by.isnot(None),
                    Annotation.was_cancelled == False,  # noqa: E712
                )
                .subquery()
            )
            latest_ann_ids = (
                select(latest_ann.c.ann_id).where(latest_ann.c.rn == 1).subquery()
            )
            ranked_ann_evals = (
                select(
                    TaskEvaluation.task_id,
                    TaskEvaluation.annotation_id,
                    TaskEvaluation.field_name,
                    TaskEvaluation.metrics,
                    TaskEvaluation.created_at,
                    func.row_number()
                    .over(
                        partition_by=[TaskEvaluation.annotation_id, TaskEvaluation.field_name],
                        order_by=TaskEvaluation.created_at.desc(),
                    )
                    .label("rn"),
                )
                .where(
                    TaskEvaluation.evaluation_id == evaluation_id,
                    TaskEvaluation.generation_id == None,  # noqa: E711
                    TaskEvaluation.annotation_id.isnot(None),
                    TaskEvaluation.annotation_id.in_(select(latest_ann_ids.c.ann_id)),
                )
                .subquery()
            )
            annotation_eval_results = (
                await db.execute(
                    select(
                        ranked_ann_evals.c.task_id,
                        ranked_ann_evals.c.annotation_id,
                        ranked_ann_evals.c.field_name,
                        ranked_ann_evals.c.metrics,
                        ranked_ann_evals.c.created_at,
                    )
                    .where(ranked_ann_evals.c.rn == 1)
                )
            ).all()

        if not sample_results and not annotation_eval_results:
            return {
                "evaluation_id": evaluation_id,
                "models": [],
                "model_names": {},
                "tasks": [],
                "summary": {},
            }

        # Get all unique model_ids
        model_ids = list(set(r.model_id for r in sample_results if r.model_id))

        # Get model display names from LLMModel table
        llm_models = (
            (await db.execute(select(LLMModel).where(LLMModel.id.in_(model_ids)))).scalars().all()
            if model_ids
            else []
        )
        model_name_map = {m.id: m.name for m in llm_models}

        # For models not in LLMModel table, use the model_id as the name
        for model_id in model_ids:
            if model_id not in model_name_map:
                model_name_map[model_id] = model_id

        # Task previews — push the SUBSTRING into SQL so we don't load every
        # `tasks.data` JSON blob (often 1–5KB each) into Python just to keep
        # the first 100 characters of `text`/`content`. For a 10k-task project
        # the old shape pulled tens of MB across the wire to discard 99 % of it.
        from sqlalchemy import cast as sa_cast, func as sa_func
        from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

        all_task_ids = list(set(
            [r.task_id for r in sample_results if r.task_id]
            + [r.task_id for r in annotation_eval_results if r.task_id]
        ))
        task_preview_map: dict = {}
        if all_task_ids:
            jsonb_data = sa_cast(Task.data, PG_JSONB)
            text_expr = sa_func.coalesce(
                jsonb_data.op("->>")("text"),
                jsonb_data.op("->>")("content"),
                "",
            )
            preview_rows = (
                await db.execute(
                    select(Task.id, sa_func.left(text_expr, 100), sa_func.length(text_expr))
                    .where(Task.id.in_(all_task_ids))
                )
            ).all()
            for tid, head, total_len in preview_rows:
                head = head or ""
                task_preview_map[tid] = (
                    head + "..." if total_len and total_len > 100 else head
                )

        # Build task-model score matrix.
        # When aggregate_mean is on, multiple rows can share the same
        # (task, model) cell — collect them in `cell_scores` and average
        # at the end. Otherwise, the upstream window-function dedup already
        # guaranteed at most one row per cell, so direct assignment is fine.
        task_model_scores = {}  # {task_id: {model_id: score}}
        model_scores_list = {model_id: [] for model_id in model_ids}  # For averages
        cell_scores: dict = {}  # {(task_id, model_id): [score, ...]} when aggregating

        for result in sample_results:
            task_id = result.task_id
            model_id = result.model_id

            if not task_id or not model_id:
                continue

            score = _extract_primary_score(result.metrics)
            if score is None:
                continue

            if aggregate_mean:
                cell_scores.setdefault((task_id, model_id), []).append(score)
            else:
                task_model_scores.setdefault(task_id, {})[model_id] = score
                model_scores_list[model_id].append(score)

        if aggregate_mean:
            for (task_id, model_id), scores in cell_scores.items():
                mean = sum(scores) / len(scores)
                task_model_scores.setdefault(task_id, {})[model_id] = mean
                model_scores_list[model_id].append(mean)

        # Process annotation-based results as synthetic annotator "models"
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
                # Mirror the leaderboard's pseudonym resolution
                # (benger_extended/api/routers/leaderboards_human.py:168) so
                # annotators with use_pseudonym=true display under their
                # pseudonym instead of their real name/username.
                annotator_name_map = {
                    a.id: (
                        a.pseudonym
                        if (a.use_pseudonym and a.pseudonym)
                        else (a.name or a.username)
                    )
                    for a in annotations_with_users
                }

                # When aggregate_mean is on, keep ALL rows so we can average
                # across graders / re-grades for each (task, annotator, field)
                # cell. Otherwise dedup to the latest row, preserving existing
                # behavior for LLM evaluation runs.
                if aggregate_mean:
                    rows_for_aggregation = list(annotation_eval_results)
                else:
                    seen_task_annotations: dict = {}
                    for r in sorted(annotation_eval_results, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc)):
                        seen_task_annotations[(r.task_id, r.annotation_id, r.field_name)] = r
                    rows_for_aggregation = list(seen_task_annotations.values())

                annotation_cell_scores: dict = {}  # {(task_id, synthetic_model_id): [score, ...]}

                for r in rows_for_aggregation:
                    display = annotator_name_map.get(r.annotation_id, "Unknown")
                    synthetic_model_id = f"annotator:{display}"
                    score = _extract_primary_score(r.metrics)
                    if score is None:
                        continue

                    if synthetic_model_id not in model_scores_list:
                        model_scores_list[synthetic_model_id] = []
                        model_ids.append(synthetic_model_id)
                    model_name_map[synthetic_model_id] = f"Annotator: {display}"

                    if aggregate_mean:
                        annotation_cell_scores.setdefault(
                            (r.task_id, synthetic_model_id), []
                        ).append(score)
                    else:
                        task_model_scores.setdefault(r.task_id, {})[synthetic_model_id] = score
                        model_scores_list[synthetic_model_id].append(score)

                if aggregate_mean:
                    for (task_id, synthetic_model_id), scores in annotation_cell_scores.items():
                        mean = sum(scores) / len(scores)
                        task_model_scores.setdefault(task_id, {})[synthetic_model_id] = mean
                        model_scores_list[synthetic_model_id].append(mean)

        # Build response
        tasks_response = []
        for task_id in all_task_ids:
            scores = task_model_scores.get(task_id, {})
            if scores:
                tasks_response.append(
                    {
                        "task_id": task_id,
                        "task_preview": task_preview_map.get(task_id, ""),
                        "scores": scores,
                    }
                )

        # Sort tasks by task_id for consistent ordering
        tasks_response.sort(key=lambda x: x["task_id"])

        # Calculate model summaries
        summary = {}
        for model_id in model_ids:
            scores = model_scores_list[model_id]
            if scores:
                summary[model_id] = {
                    "avg": sum(scores) / len(scores),
                    "count": len(scores),
                    "model_name": model_name_map.get(model_id, model_id),
                }

        # Sort models by average score descending
        sorted_models = sorted(
            model_ids, key=lambda m: summary.get(m, {}).get("avg", 0), reverse=True
        )

        return {
            "evaluation_id": evaluation_id,
            "models": sorted_models,
            "model_names": model_name_map,
            "tasks": tasks_response,
            "summary": summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get results by task/model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get results by task/model: {str(e)}",
        )


async def _get_task_data_availability(db, task_ids: list) -> tuple:
    """Return (tasks_with_annotations, generation_models_by_task,
    annotator_displays_by_task) for the given task IDs.

    `annotator_displays_by_task[task_id]` is the set of annotator display
    strings (`pseudonym → name → username`) of users who submitted an
    annotation for that task. The eval-results table uses this to decide
    whether an empty `annotator:<display>` cell should render a clickable
    "n/a" (annotation exists, just not graded yet) versus a greyed one
    (no annotation by that annotator on that task).
    """
    from models import Generation as GenerationModel
    from models import User as DBUser

    tasks_with_annotations: set = set()
    generation_model_by_task: dict = {}
    annotator_displays_by_task: dict = {}

    if task_ids:
        annotated = (
            await db.execute(
                select(Annotation.task_id)
                .where(
                    Annotation.task_id.in_(task_ids),
                    Annotation.was_cancelled == False,  # noqa: E712
                )
                .distinct()
            )
        ).all()
        tasks_with_annotations = {r[0] for r in annotated}

        gen_rows = (
            await db.execute(
                select(GenerationModel.task_id, GenerationModel.model_id)
                .where(GenerationModel.task_id.in_(task_ids))
                .distinct()
            )
        ).all()
        for row in gen_rows:
            generation_model_by_task.setdefault(row.task_id, set()).add(row.model_id)

        annotator_rows = (
            await db.execute(
                select(
                    Annotation.task_id,
                    DBUser.username,
                    DBUser.name,
                    DBUser.pseudonym,
                    DBUser.use_pseudonym,
                )
                .join(DBUser, Annotation.completed_by == DBUser.id)
                .where(
                    Annotation.task_id.in_(task_ids),
                    Annotation.was_cancelled == False,  # noqa: E712
                    Annotation.result != None,  # noqa: E711
                )
                .distinct()
            )
        ).all()
        for row in annotator_rows:
            display = (
                row.pseudonym
                if (row.use_pseudonym and row.pseudonym)
                else (row.name or row.username)
            )
            annotator_displays_by_task.setdefault(row.task_id, set()).add(
                f"annotator:{display}"
            )

    return tasks_with_annotations, generation_model_by_task, annotator_displays_by_task


async def _task_preview_rows(db, project_id: str) -> list:
    """Return `[(task_id, preview)]` for every task in a project.

    The 100-character preview is computed by Postgres so `Task.data` (1–5KB
    JSON per row) never leaves the server — loading the blobs to slice a
    preview in Python streamed tens of MB across the wire on large projects.
    Key precedence: input → text → question → prompt → content, else "".
    """
    from sqlalchemy import cast as sa_cast, func as sa_func
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

    jsonb_data = sa_cast(Task.data, PG_JSONB)
    preview_text = sa_func.coalesce(
        jsonb_data.op("->>")("input"),
        jsonb_data.op("->>")("text"),
        jsonb_data.op("->>")("question"),
        jsonb_data.op("->>")("prompt"),
        jsonb_data.op("->>")("content"),
        "",
    )
    return (
        await db.execute(
            select(Task.id, sa_func.left(preview_text, 100))
            .where(Task.project_id == project_id)
        )
    ).all()


async def _build_all_tasks_response(db, project_id: str) -> list:
    """Build task list with data availability info for all tasks in a project."""
    rows = await _task_preview_rows(db, project_id)
    all_task_ids = [tid for tid, _ in rows]
    tasks_with_annotations, gen_model_by_task, annot_displays_by_task = (
        await _get_task_data_availability(db, all_task_ids)
    )

    return [
        {
            "task_id": tid,
            "task_preview": preview or "",
            "scores": {},
            "has_annotation": tid in tasks_with_annotations,
            "generation_models": list(gen_model_by_task.get(tid, set())),
            "annotator_columns": list(annot_displays_by_task.get(tid, set())),
        }
        for tid, preview in rows
    ]


@router.get("/projects/{project_id}/results/by-task-model")
async def get_project_results_by_task_model(
    project_id: str,
    request: Request,
    evaluation_ids: Optional[str] = Query(None, description="Comma-separated evaluation run IDs to filter by"),
    metric: Optional[str] = Query(
        None,
        description=(
            "When set, only rows whose `metrics` dict carries this key "
            "are returned. Required when an EvaluationRun bundles multiple "
            "metrics, since the cell-aggregation loop collapses multiple "
            "rows for the same (task, model) into one — without this filter, "
            "the last metric processed wins and every column shows the "
            "same number."
        ),
    ),
    evaluation_config_id: Optional[str] = Query(
        None,
        description=(
            "When set, restrict rows to this single evaluation method via "
            "`task_evaluations.evaluation_config_id` — the stable per-config "
            "grouping key (issue #111; same scoping as metadata/significance "
            "and metadata/history). Scans ALL of the project's runs — immediate "
            "KI-Votum, the hourly cron sweep, and manual batch/missing-only — "
            "and unions generation-side (model columns) with annotation-side "
            "(annotator columns) rows for the ONE method, so no run's scores "
            "are dropped. Legacy rows whose config id IS NULL (pre-migration, "
            "~0.6% on prod) are excluded; remediate with "
            "scripts/backfill_immediate_eval_config_id.py. Combine with `metric` "
            "for primary-score extraction."
        ),
    ),
    include_history: bool = Query(
        False,
        description=(
            "When true, human-graded run rows for the same (task, annotator) "
            "cell are averaged instead of latest-only. LLM-driven runs always "
            "use latest-only."
        ),
    ),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get aggregated evaluation results across ALL completed evaluations for a project.

    Uses generation_id as the natural key to deduplicate results:
    - If a generation was evaluated in multiple runs, uses the LATEST result
    - Aggregates results from ALL completed evaluations (evaluation/llm_judge types)
    """
    from sqlalchemy import func

    from models import TaskEvaluation
    from models import Generation as GenerationModel
    from models import LLMModel

    try:
        # Verify project exists and user has access
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Get evaluations for this project (completed + in-flight),
        # optionally filtered by IDs. In-flight runs commit each row as
        # the evaluator finishes it, so surfacing them here lets the
        # frontend stream live progress instead of waiting for the run
        # to flip to `completed`. Failed runs still drop out.
        eval_query = select(DBEvaluationRun.id).where(
            DBEvaluationRun.project_id == project_id,
            DBEvaluationRun.status.in_(("completed", "running", "pending")),
        )
        if evaluation_ids:
            filter_ids = [eid.strip() for eid in evaluation_ids.split(",") if eid.strip()]
            if filter_ids:
                eval_query = eval_query.where(DBEvaluationRun.id.in_(filter_ids))
        completed_evals = (await db.execute(eval_query)).all()
        completed_eval_ids = [e.id for e in completed_evals]

        if not completed_eval_ids:
            return {
                "project_id": project_id,
                "models": [],
                "model_names": {},
                "tasks": await _build_all_tasks_response(db, project_id),
                "summary": {},
            }

        # F1: when `include_history` is OFF, the cell must reflect the
        # SINGLE latest generation per (task_id, model_id) — not the latest
        # eval row across all historical gens. Without this scope, an older
        # gen's eval row silently feeds the cell when the latest gen has no
        # valid eval (e.g. the only eval row for the latest gen came from a
        # cancelled run and got filtered upstream by EvaluationRun.status).
        # The user's mental model is "n/a if the current gen has no
        # eval", not "fall back to whatever older gen still has a score".
        # Mirrors the same pattern used by the /by-task-model sibling
        # endpoint (this file, around line 777).
        latest_gen_ids_subq = None
        latest_ann_ids_subq = None
        if not include_history:
            project_task_ids = select(Task.id).where(Task.project_id == project_id).subquery()
            latest_gen = (
                select(
                    GenerationModel.id.label("gen_id"),
                    func.row_number()
                    .over(
                        partition_by=[GenerationModel.task_id, GenerationModel.model_id],
                        order_by=GenerationModel.created_at.desc(),
                    )
                    .label("rn"),
                )
                .where(
                    GenerationModel.status == "completed",
                    GenerationModel.task_id.in_(select(project_task_ids.c.id)),
                )
                .subquery()
            )
            latest_gen_ids_subq = (
                select(latest_gen.c.gen_id).where(latest_gen.c.rn == 1).subquery()
            )
            latest_ann = (
                select(
                    Annotation.id.label("ann_id"),
                    func.row_number()
                    .over(
                        partition_by=[Annotation.task_id, Annotation.completed_by],
                        order_by=Annotation.created_at.desc(),
                    )
                    .label("rn"),
                )
                .where(
                    Annotation.completed_by.isnot(None),
                    Annotation.was_cancelled == False,  # noqa: E712
                    Annotation.task_id.in_(select(project_task_ids.c.id)),
                )
                .subquery()
            )
            latest_ann_ids_subq = (
                select(latest_ann.c.ann_id).where(latest_ann.c.rn == 1).subquery()
            )

        # Project a "lite" metrics blob that drops the heavy nested fields we
        # never use for score extraction — for an llm_judge_falloesung row on
        # zjs fälle this collapses ~6 KB → ~50 B, so the by-task-model
        # endpoint pulls ~600 KB from Postgres instead of ~45 MB (page-load
        # latency 3.1s → ~0.4s on prod-shaped data, 2026-05-18 measurement).
        # The Python `_extract_primary_score` still owns the priority logic;
        # it only needs the `value` (or bare numeric) per metric key, and an
        # optional `error` to skip failed runs.
        # `task_evaluations.metrics` is `Column(JSON)` (text JSON), so
        # `jsonb_each` requires an explicit cast — Postgres won't auto-promote
        # `json` to `jsonb`. Production schemas where the column happens to
        # be jsonb still work because the cast is a no-op there.
        metrics_lite_expr = literal_column("""
            (SELECT COALESCE(jsonb_object_agg(k,
                CASE WHEN jsonb_typeof(v) = 'object'
                     THEN v - 'details' - 'method' - 'raw' - 'justification'
                     ELSE v END
              ), '{}'::jsonb)
             FROM jsonb_each(task_evaluations.metrics::jsonb) AS j(k, v))
        """).label("metrics")

        # Subquery: rank results by (generation_id, field_name), ordered by created_at DESC
        # Keeps the latest result per generation per config/field combination
        gen_query = (
            select(
                TaskEvaluation.task_id,
                TaskEvaluation.generation_id,
                metrics_lite_expr,
                GenerationModel.model_id,
                TaskEvaluation.created_at,
                func.row_number()
                .over(
                    partition_by=[TaskEvaluation.generation_id, TaskEvaluation.field_name],
                    order_by=TaskEvaluation.created_at.desc(),
                )
                .label("rn"),
            )
            .join(
                GenerationModel,
                TaskEvaluation.generation_id == GenerationModel.id,
            )
            .where(TaskEvaluation.evaluation_id.in_(completed_eval_ids))
        )
        if latest_gen_ids_subq is not None:
            gen_query = gen_query.where(
                TaskEvaluation.generation_id.in_(select(latest_gen_ids_subq.c.gen_id))
            )
        # When a single EvaluationRun bundles multiple metrics, every metric
        # produces its own row for the same (gen, model) cell. The aggregation
        # loop below assigns score by overwriting `task_model_scores[t][m]`
        # — so without filtering by the user's selected metric, the last
        # row to land wins and every column shows the same number.
        if metric:
            from sqlalchemy import cast
            from sqlalchemy.dialects.postgresql import JSONB
            gen_query = gen_query.where(
                cast(TaskEvaluation.metrics, JSONB).has_key(metric)
            )
        # Issue #111: scope to a single method. Pre-filtering to one config id
        # also makes the (generation_id, field_name) latest-wins partition below
        # collision-free across two configs that share a metric key.
        if evaluation_config_id:
            gen_query = gen_query.where(
                TaskEvaluation.evaluation_config_id == evaluation_config_id
            )
        ranked_results = gen_query.subquery()

        # Filter to only the latest result per generation (rn = 1)
        sample_results = (
            await db.execute(
                select(
                    ranked_results.c.task_id,
                    ranked_results.c.generation_id,
                    ranked_results.c.metrics,
                    ranked_results.c.model_id,
                    ranked_results.c.created_at,
                )
                .where(ranked_results.c.rn == 1)
            )
        ).all()

        # Phase 6.3: count suppressed runs so consumers see the
        # deduplication footprint. Per (generation_id, field_name) a single
        # latest row is surfaced; older runs survive in the DB but get
        # filtered out here. Without this audit trail a leaderboard score
        # could swing on re-evaluation with no record of which historical
        # run was hidden.
        suppressed_count = (
            (
                await db.execute(
                    select(func.count())
                    .select_from(ranked_results)
                    .where(ranked_results.c.rn > 1)
                )
            ).scalar()
            or 0
        )
        deduplication_summary = {
            "scope": "(generation_id, field_name)",
            "policy": "latest_wins_by_created_at_desc",
            "suppressed_run_count": int(suppressed_count),
        }

        # Query 2: Get annotation-based evaluation results (generation_id IS NULL)
        from models import User as DBUser
        from models import TaskEvaluation as TE2

        # Same lite-metrics projection as the gen branch (see comment there).
        ann_metrics_lite_expr = literal_column("""
            (SELECT COALESCE(jsonb_object_agg(k,
                CASE WHEN jsonb_typeof(v) = 'object'
                     THEN v - 'details' - 'method' - 'raw' - 'justification'
                     ELSE v END
              ), '{}'::jsonb)
             FROM jsonb_each(task_evaluations.metrics::jsonb) AS j(k, v))
        """).label("metrics")

        ann_query = (
            select(
                TE2.task_id,
                TE2.annotation_id,
                TE2.field_name,
                ann_metrics_lite_expr,
                TE2.created_at,
            )
            .where(
                TE2.evaluation_id.in_(completed_eval_ids),
                TE2.generation_id == None,  # noqa: E711
                TE2.annotation_id != None,  # noqa: E711
            )
        )
        if latest_ann_ids_subq is not None:
            ann_query = ann_query.where(
                TE2.annotation_id.in_(select(latest_ann_ids_subq.c.ann_id))
            )
        if metric:
            from sqlalchemy import cast as _cast
            from sqlalchemy.dialects.postgresql import JSONB as _JSONB
            ann_query = ann_query.where(
                _cast(TE2.metrics, _JSONB).has_key(metric)
            )
        # Issue #111: scope to a single method (same key as the gen branch).
        if evaluation_config_id:
            ann_query = ann_query.where(
                TE2.evaluation_config_id == evaluation_config_id
            )
        annotation_eval_results = (await db.execute(ann_query)).all()

        if not sample_results and not annotation_eval_results:
            return {
                "project_id": project_id,
                "models": [],
                "model_names": {},
                "tasks": await _build_all_tasks_response(db, project_id),
                "summary": {},
            }

        # Get unique model_ids and their display names
        model_ids = list(set(r.model_id for r in sample_results if r.model_id))

        # Get model display names from LLMModel table
        llm_models = (
            (await db.execute(select(LLMModel).where(LLMModel.id.in_(model_ids)))).scalars().all()
            if model_ids
            else []
        )
        model_name_map = {m.id: m.name for m in llm_models}

        # For models not in LLMModel table, use the model_id as the name
        for model_id in model_ids:
            if model_id not in model_name_map:
                model_name_map[model_id] = model_id

        # Build task-model score matrix
        # Structure: {task_id: {model_id: score, ...}, ...}
        #
        # Each (task, model) cell may carry multiple TaskEvaluation rows: the
        # project often generates >1 sample per (task, model) prompt, so
        # there is one row per (gen × pred-field × ref-field). Two display
        # modes:
        #   - include_history=False (default): cell = score of the most
        #     recently created row for that (task, model). Matches the
        #     "latest sample wins" mental model the user expects when
        #     looking at a single number per cell.
        #   - include_history=True: cell = arithmetic mean across all rows
        #     for that (task, model). For sampling/reliability studies.
        # Single-row cells render the same value either way.
        task_scores: dict = {}
        task_previews: dict = {}
        cell_score_buckets: dict = {}  # {(task_id, model_id): [(created_at, score), ...]}
        model_scores: dict = {mid: [] for mid in model_ids}

        for result in sample_results:
            task_id = result.task_id
            model_id = result.model_id
            metrics = result.metrics or {}

            score = _extract_primary_score(metrics)

            if score is not None and model_id:
                cell_score_buckets.setdefault((task_id, model_id), []).append(
                    (result.created_at, score)
                )

        for (task_id, model_id), entries in cell_score_buckets.items():
            if include_history:
                cell_score = sum(s for _, s in entries) / len(entries)
            else:
                # Latest-wins: pick the score whose row has the max created_at.
                cell_score = max(entries, key=lambda e: e[0] or datetime.min.replace(tzinfo=timezone.utc))[1]
            task_scores.setdefault(task_id, {})[model_id] = cell_score
            model_scores[model_id].append(cell_score)

        # Process annotation-based results: add as synthetic annotator "models"
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
                # Mirror the leaderboard pseudonym resolution so users with
                # use_pseudonym=true display under their pseudonym.
                annotator_name_map = {
                    a.id: (
                        a.pseudonym
                        if (a.use_pseudonym and a.pseudonym)
                        else (a.name or a.username)
                    )
                    for a in annotations_with_users
                }

                # When `include_history` is on, keep ALL rows so we can mean
                # across grader history per (task, annotator) cell. Otherwise
                # dedup to the latest row, preserving existing LLM-eval
                # behavior.
                if include_history:
                    rows_for_aggregation = list(annotation_eval_results)
                else:
                    seen_task_annotations: dict = {}
                    for r in sorted(annotation_eval_results, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc)):
                        seen_task_annotations[(r.task_id, r.annotation_id, r.field_name)] = r
                    rows_for_aggregation = list(seen_task_annotations.values())

                annotation_cell_scores: dict = {}  # {(task_id, synthetic_model_id): [score, ...]}

                for r in rows_for_aggregation:
                    display = annotator_name_map.get(r.annotation_id, "Unknown")
                    synthetic_model_id = f"annotator:{display}"
                    score = _extract_primary_score(r.metrics)
                    if score is None:
                        continue

                    if synthetic_model_id not in model_scores:
                        model_scores[synthetic_model_id] = []
                        model_ids.append(synthetic_model_id)
                    model_name_map[synthetic_model_id] = f"Annotator: {display}"

                    if include_history:
                        annotation_cell_scores.setdefault(
                            (r.task_id, synthetic_model_id), []
                        ).append(score)
                    else:
                        task_scores.setdefault(r.task_id, {})[synthetic_model_id] = score
                        model_scores[synthetic_model_id].append(score)

                if include_history:
                    for (task_id_, synthetic_model_id), scores in annotation_cell_scores.items():
                        mean = sum(scores) / len(scores)
                        task_scores.setdefault(task_id_, {})[synthetic_model_id] = mean
                        model_scores[synthetic_model_id].append(mean)

        # Get ALL project tasks (not just evaluated ones) so unevaluated tasks
        # show as n/a. Previews are computed in SQL — selecting Task.data here
        # loaded every JSONB blob in the project into Python (issue #106).
        preview_rows = await _task_preview_rows(db, project_id)
        all_task_ids = [tid for tid, _ in preview_rows]
        for tid, preview in preview_rows:
            task_previews[tid] = preview or ""

        # Get data availability for clickable n/a cells
        tasks_with_annotations, generation_model_by_task, annot_displays_by_task = (
            await _get_task_data_availability(db, all_task_ids)
        )

        # Sort models by average score (descending)
        model_avgs = {
            mid: sum(scores) / len(scores) if scores else 0 for mid, scores in model_scores.items()
        }
        sorted_models = sorted(model_avgs.keys(), key=lambda m: model_avgs[m], reverse=True)

        # Build response - include ALL project tasks, not just evaluated ones
        tasks_response = []
        for tid in all_task_ids:
            gen_models = generation_model_by_task.get(tid, set())
            annot_cols = annot_displays_by_task.get(tid, set())
            tasks_response.append(
                {
                    "task_id": tid,
                    "task_preview": task_previews.get(tid, ""),
                    "scores": task_scores.get(tid, {}),
                    "has_annotation": tid in tasks_with_annotations,
                    "generation_models": list(gen_models),
                    # Annotator columns (`annotator:<display>`) for which this
                    # task has an actual submitted annotation. Drives the
                    # clickable-n/a behavior: empty cell + annotation present
                    # = clickable (open the annotation), no annotation = grey.
                    "annotator_columns": list(annot_cols),
                }
            )

        # Build summary
        summary = {}
        for model_id in sorted_models:
            scores = model_scores[model_id]
            if scores:
                summary[model_id] = {
                    "avg": sum(scores) / len(scores),
                    "count": len(scores),
                    "model_name": model_name_map.get(model_id, model_id),
                }

        return {
            "project_id": project_id,
            "models": sorted_models,
            "model_names": model_name_map,
            "tasks": tasks_response,
            "summary": summary,
            # Phase 6.3: how many historical runs were suppressed by
            # the (generation_id, field_name) latest-wins dedup. A
            # researcher comparing two snapshots of the same project
            # can use this to understand whether a score change came
            # from new data or a re-evaluation.
            "deduplication_summary": deduplication_summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get project results by task/model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get project results by task/model: {str(e)}",
        )


@router.get("/sample-result")
async def get_sample_result_by_task_model(
    request: Request,
    task_id: str = Query(..., description="Task ID"),
    model_id: str = Query(..., description="Model ID"),
    include_history: bool = Query(True, description="Include all historical results. When false, deduplicate to latest per field_name."),
    generation_id: Optional[str] = Query(
        None,
        description=(
            "Restrict results to evaluations of this exact generation. "
            "Used by the result modal to keep its three tabs (Annotation, "
            "Generation, Evaluation) locked to the same generation_id — "
            "without it the modal could show today's generation in one tab "
            "and yesterday's eval of a stale generation in another."
        ),
    ),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get evaluation sample results for a specific task and model combination.

    Returns all evaluation sample results where the generation was produced by
    the specified model for the specified task. Includes metrics, ground truth,
    prediction, and evaluation metadata.
    """
    try:
        from models import TaskEvaluation
        from models import Generation as GenerationModel

        # Resolve project from task and check access
        task_result = await db.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one_or_none()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_id}' not found",
            )

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(db, current_user, task.project_id, org_context):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        if model_id.startswith("annotator:"):
            # Annotation-based evaluation: the suffix after `annotator:` is the
            # annotator's *display name*, computed by `by-task-model` /
            # `evaluated-models` as: pseudonym (if use_pseudonym) → name →
            # username. So resolve back through the same precedence rather
            # than assuming `username` literally — otherwise users whose
            # display name comes from `name` or `pseudonym` (e.g. the
            # imported "Imported User <hash>" cohort) won't be found and the
            # detail modal renders empty.
            from sqlalchemy import or_, and_
            from models import User as DBUser

            display = model_id.split(":", 1)[1]
            user = (
                await db.execute(
                    select(DBUser)
                    .where(
                        or_(
                            and_(DBUser.use_pseudonym == True, DBUser.pseudonym == display),  # noqa: E712
                            DBUser.name == display,
                            DBUser.username == display,
                        )
                    )
                )
            ).scalars().first()

            if user:
                # Mirror the cell aggregator's run-status filter
                # (results.py: completed/running/pending only) so the modal
                # never surfaces a row from a cancelled or failed run when
                # the table cell already excluded it. Without this the modal
                # eval tab can show a `{score:1, justification}` row from a
                # cancelled judge run while the cell shows a different,
                # valid score from an earlier successful run.
                sample_results = (
                    (
                        await db.execute(
                            select(TaskEvaluation)
                            .join(Annotation, TaskEvaluation.annotation_id == Annotation.id)
                            .join(DBEvaluationRun, TaskEvaluation.evaluation_id == DBEvaluationRun.id)
                            .where(
                                TaskEvaluation.task_id == task_id,
                                Annotation.completed_by == user.id,
                                TaskEvaluation.generation_id == None,  # noqa: E711
                                DBEvaluationRun.status.in_(("completed", "running", "pending")),
                            )
                            .order_by(TaskEvaluation.created_at.desc())
                        )
                    )
                    .scalars()
                    .all()
                )
            else:
                sample_results = []
        else:
            # Generation-based evaluation: join on Generation model
            q = (
                select(TaskEvaluation)
                .join(
                    GenerationModel,
                    TaskEvaluation.generation_id == GenerationModel.id,
                )
                .join(
                    DBEvaluationRun,
                    TaskEvaluation.evaluation_id == DBEvaluationRun.id,
                )
                .where(
                    TaskEvaluation.task_id == task_id,
                    GenerationModel.model_id == model_id,
                    DBEvaluationRun.status.in_(("completed", "running", "pending")),
                )
            )
            if generation_id:
                # Modal tab-cohesion path. The frontend obtains its
                # `generation_id` from `/generation-tasks/generation-result`,
                # which returns `response_generations.id` (the parent row
                # per task/model/structure). `task_evaluations.generation_id`
                # FKs to the inner `generations` table, so a direct equality
                # on `TaskEvaluation.generation_id == generation_id` never
                # matches and the modal renders empty even when the page
                # shows a score for that cell. Filter on the joined
                # `Generation.generation_id` (which is the FK back to
                # ResponseGeneration) instead — that's the column whose
                # value matches what the frontend sent.
                q = q.where(GenerationModel.generation_id == generation_id)
            sample_results = (
                (await db.execute(q.order_by(TaskEvaluation.created_at.desc())))
                .scalars()
                .all()
            )

        if not sample_results:
            return {
                "task_id": task_id,
                "model_id": model_id,
                "results": [],
                "message": "No evaluation results found for this task and model",
            }

        # Deduplicate to latest per field_name when history is off
        # Results are already ordered by created_at desc, so first per field wins
        if not include_history:
            seen_fields = set()
            deduplicated = []
            for sr in sample_results:
                if sr.field_name not in seen_fields:
                    seen_fields.add(sr.field_name)
                    deduplicated.append(sr)
            sample_results = deduplicated

        # Build response with full evaluation details
        # Batch-load evaluation runs to avoid N+1 queries
        eval_ids = list(set(sr.evaluation_id for sr in sample_results if sr.evaluation_id))
        eval_map = (
            {
                e.id: e
                for e in (
                    await db.execute(
                        select(DBEvaluationRun).where(DBEvaluationRun.id.in_(eval_ids))
                    )
                )
                .scalars()
                .all()
            }
            if eval_ids
            else {}
        )

        results = []
        for sr in sample_results:
            evaluation = eval_map.get(sr.evaluation_id)

            result_data = {
                "id": sr.id,
                "evaluation_id": sr.evaluation_id,
                "field_name": sr.field_name,
                "answer_type": sr.answer_type,
                "ground_truth": sr.ground_truth,
                "prediction": sr.prediction,
                "metrics": sr.metrics,
                "passed": sr.passed,
                "confidence_score": sr.confidence_score,
                "error_message": sr.error_message,
                "processing_time_ms": sr.processing_time_ms,
                "created_at": sr.created_at.isoformat() if sr.created_at else None,
            }

            # Add evaluation context if available
            if evaluation:
                result_data["evaluation_context"] = {
                    "evaluation_type": (evaluation.eval_metadata or {}).get("evaluation_type"),
                    "status": evaluation.status,
                    "eval_metadata": evaluation.eval_metadata,
                }

            results.append(result_data)

        return {
            "task_id": task_id,
            "model_id": model_id,
            "results": results,
            "total_count": len(results),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sample result: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get evaluation sample result: {str(e)}",
        )
