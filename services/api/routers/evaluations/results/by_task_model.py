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
import current_scores
from human_graded_metrics import sql_scored_run
from user_display import masked_name

from evaluation_methods import teacher_current_rows, teacher_rows

from .method_selection import load_method_selection

from routers.projects.helpers import can_read_all_task_content_async


async def _require_content_access(db, user, project_id: str) -> None:
    """These views carry every task's content, reference answers and other
    people's scores: contributors only (see can_read_all_task_content)."""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not await can_read_all_task_content_async(db, user, project):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _add_annotator_cells(
    db,
    rows,
    *,
    include_history: bool,
    task_scores: dict,
    model_scores: dict,
    model_ids: list,
    model_name_map: dict,
    model_export_labels: dict,
    selection=None,
    configs_by_id=None,
) -> None:
    """Add the annotator columns (``annotator:<display>``) to a grid.

    ``rows`` are evaluation rows of answers: without ``include_history`` the
    current row of every cell (shared/current_scores.py), and the column
    shows the newest of them that carries a score; with it every row, and
    the column shows their mean. Each column contributes ONE score per task
    to its average, however many rows the cell had. ``selection`` (a
    ``MethodSelection``) keeps the rows a teacher view shows for the account
    that submitted the answer (``evaluation_methods.teacher_rows``: the
    official config's, else another config of the group that has a score
    for the cell, with their history when ``include_history`` is set);
    ``configs_by_id`` are the project's configs, which decide a row's cell.
    """
    from models import User as DBUser

    annotation_ids = list({r.annotation_id for r in rows if r.annotation_id})
    if not annotation_ids:
        return
    annotations_with_users = (
        await db.execute(
            select(
                Annotation.id,
                DBUser.username,
                DBUser.name,
                DBUser.pseudonym,
                DBUser.use_pseudonym,
                DBUser.id.label("user_id"),
            )
            .join(DBUser, Annotation.completed_by == DBUser.id)
            .where(Annotation.id.in_(annotation_ids))
        )
    ).all()
    # Mirror the leaderboard pseudonym resolution
    # (benger_extended/api/routers/leaderboards_human.py) so users with
    # use_pseudonym=true display under their pseudonym.
    annotator_name_map = {
        a.id: (a.pseudonym if (a.use_pseudonym and a.pseudonym) else (a.name or a.username))
        for a in annotations_with_users
    }
    # What a DOWNLOAD of this grid may say about the same people. The labels
    # above honour each person's own choice for the screen and can be a real
    # name; a file never names anyone, so it gets the account id and the
    # pseudonym instead.
    annotator_export_map = {
        a.id: (a.user_id, masked_name(user_id=a.user_id, pseudonym=a.pseudonym))
        for a in annotations_with_users
    }
    user_of = {a.id: a.user_id for a in annotations_with_users}
    shown = None
    if selection is not None:
        shown = teacher_rows(selection, rows, user_of, configs_by_id)

    cells: dict = {}  # {(task_id, synthetic_model_id): [(official, created_at, score), ...]}
    for r in rows:
        if shown is not None and current_scores.row_id(r) not in shown:
            continue
        score = _extract_primary_score(r.metrics)
        if score is None:
            continue
        display = annotator_name_map.get(r.annotation_id, "Unknown")
        synthetic_model_id = f"annotator:{display}"
        if synthetic_model_id not in model_scores:
            model_scores[synthetic_model_id] = []
            model_ids.append(synthetic_model_id)
        model_name_map[synthetic_model_id] = f"Annotator: {display}"
        export_user_id, export_label = annotator_export_map.get(r.annotation_id, (None, "Unknown"))
        model_export_labels[synthetic_model_id] = {
            "id": f"annotator:{export_user_id or 'unknown'}",
            "name": f"Annotator: {export_label}",
        }
        own = shown is None or shown[current_scores.row_id(r)] is None
        cells.setdefault((r.task_id, synthetic_model_id), []).append((own, r.created_at, score))

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    for (task_id, synthetic_model_id), entries in cells.items():
        if include_history:
            value = sum(e[2] for e in entries) / len(entries)
        else:
            # A score of the official config wins over a stand-in's.
            value = max(entries, key=lambda e: (e[0], e[1] or epoch))[2]
        task_scores.setdefault(task_id, {})[synthetic_model_id] = value
        model_scores[synthetic_model_id].append(value)


@router.get("/{evaluation_id}/results/by-task-model")
async def get_results_by_task_model(
    evaluation_id: str,
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

        if not await check_project_accessible_async(db, current_user, evaluation.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        await _require_content_access(db, current_user, evaluation.project_id)
        run_project = (
            await db.execute(select(Project).where(Project.id == evaluation.project_id))
        ).scalar_one_or_none()
        run_configs_by_id = current_scores.configs_by_id(
            getattr(run_project, "evaluation_config", None)
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

            # The current row per cell (shared/current_scores.py): one per
            # (generation, evaluation config, prediction field, reference
            # field), the newest row with a score winning. Partitioning by
            # the raw field_name kept one row per key format.
            ranked_results = (
                select(
                    TaskEvaluation.task_id,
                    TaskEvaluation.metrics,
                    TaskEvaluation.passed,
                    TaskEvaluation.generation_id,
                    GenerationModel.model_id,
                    func.row_number()
                    .over(
                        partition_by=current_scores.sql_cell_partition(
                            TaskEvaluation.generation_id,
                            TaskEvaluation.evaluation_config_id,
                            TaskEvaluation.field_name,
                            run_configs_by_id,
                        ),
                        order_by=current_scores.sql_current_rank_order(
                            TaskEvaluation.metrics,
                            TaskEvaluation.created_at,
                            TaskEvaluation.id,
                        ),
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
            candidate_ann_evals = (
                await db.execute(
                    select(
                        TaskEvaluation.id,
                        TaskEvaluation.task_id,
                        TaskEvaluation.annotation_id,
                        TaskEvaluation.field_name,
                        TaskEvaluation.evaluation_config_id,
                        TaskEvaluation.metrics,
                        TaskEvaluation.created_at,
                    ).where(
                        TaskEvaluation.evaluation_id == evaluation_id,
                        TaskEvaluation.generation_id == None,  # noqa: E711
                        TaskEvaluation.annotation_id.isnot(None),
                        TaskEvaluation.annotation_id.in_(select(latest_ann_ids.c.ann_id)),
                    )
                )
            ).all()
            # The current row per cell (shared/current_scores.py).
            annotation_eval_results = list(
                current_scores.pick_current(candidate_ann_evals, run_configs_by_id).values()
            )

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
        model_export_labels: dict = {}

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
            await _add_annotator_cells(
                db,
                annotation_eval_results,
                include_history=aggregate_mean,
                task_scores=task_model_scores,
                model_scores=model_scores_list,
                model_ids=model_ids,
                model_name_map=model_name_map,
                model_export_labels=model_export_labels,
            )

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
            # File-safe twin of `model_names` for the annotator columns: what
            # the grid's CSV / JSON download writes instead.
            "model_export_labels": model_export_labels,
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
    method_group: Optional[str] = Query(
        None,
        description=(
            "When set, show one evaluation method that the project grades with "
            "several alternative configs (shared/evaluation_methods.py): rows of "
            "the group's configs, each answer under the config that is official "
            "for the account that submitted it, generations under the group's "
            "default official config. The other configs' rows are research data "
            "and are left out; scope to one of them with `evaluation_config_id`."
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

        if not await check_project_accessible_async(db, current_user, project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        await _require_content_access(db, current_user, project_id)

        # Get evaluations for this project (completed + in-flight),
        # optionally filtered by IDs. In-flight runs commit each row as
        # the evaluator finishes it, so surfacing them here lets the
        # frontend stream live progress instead of waiting for the run
        # to flip to `completed`. Deliberately NO run-status filter:
        # per-sample rows are facts once written — a cancelled or failed
        # run's finished samples are real results (ZJS's canonical judge
        # re-score lived in two runs cancelled at the tail, which blanked
        # ~7k data-view cells, 2026-07-24). Error rows are skipped by the
        # score extraction and supersession is handled by latest-wins.
        eval_query = select(DBEvaluationRun.id).where(
            DBEvaluationRun.project_id == project_id,
            # Peer feedback rows are no scores: never a cell of the grid,
            # never the newest row that hides a staff grade.
            sql_scored_run(DBEvaluationRun),
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

        # Every row this grid reads comes from the narrow, trigger-kept mirror
        # `task_evaluation_metric_keys` (migrations 138 and 139), never from
        # `task_evaluations`: the mirror carries the run, subject, config,
        # field name, creation time and metric keys of each task evaluation,
        # and `metrics_lite`, the stored `task_evaluation_metrics_lite()`
        # projection (see routers/evaluations/metrics_lite.py) that
        # `_extract_primary_score` needs. Reading the metrics blob instead
        # (`metrics ? :metric` on every candidate row, the lite projection on
        # every survivor) de-TOASTed the judge rubric text of a whole project
        # per request: ZJS Fälle (160k rows) returned 500 at the API's 15 s
        # statement timeout.
        from sqlalchemy import distinct, tuple_

        from models import TaskEvaluationMetricKeys as MK

        # Run scope as a semi-join instead of splatting every run id into an
        # IN (...) literal list — ZJS-scale projects have hundreds of runs
        # (issue #280). Same semantics as `eval_query` above, still
        # deliberately NO run-status filter (#278).
        run_ids_select = select(DBEvaluationRun.id).where(
            DBEvaluationRun.project_id == project_id
        )
        if evaluation_ids:
            filter_ids = [eid.strip() for eid in evaluation_ids.split(",") if eid.strip()]
            if filter_ids:
                run_ids_select = run_ids_select.where(DBEvaluationRun.id.in_(filter_ids))

        # Predicates shared by both branches.
        scope_filters = [MK.evaluation_id.in_(run_ids_select)]
        # One method graded by alternative configs: their rows, and below only
        # the ones a teacher view shows per subject (the official config's,
        # else another config of the group that has a score).
        selection = None
        if method_group:
            selection = await load_method_selection(db, project)
            group_config_ids = selection.groups.get(method_group) or []
            if not group_config_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Method group '{method_group}' not found",
                )
            # The per-account answers are resolved for the accounts whose
            # answers the scope holds (below, once they are known).
            scope_filters.append(MK.evaluation_config_id.in_(group_config_ids))
        # When a single EvaluationRun bundles multiple metrics, every metric
        # produces its own row for the same (gen, model) cell. The aggregation
        # loop below assigns score by overwriting `task_model_scores[t][m]`
        # — so without filtering by the user's selected metric, the last
        # row to land wins and every column shows the same number.
        if metric:
            scope_filters.append(MK.metric_keys.has_key(metric))
        # Issue #111: scope to a single method. Pre-filtering to one config id
        # also makes the (generation_id, field_name) latest-wins partition below
        # collision-free across two configs that share a metric key.
        if evaluation_config_id:
            scope_filters.append(MK.evaluation_config_id == evaluation_config_id)

        # Gen-side candidate set. The explicit generation_id IS NOT NULL
        # replaces the old inner-join-drops-NULLs behavior now that ranking
        # happens before the Generation join.
        gen_filters = [*scope_filters, MK.generation_id.isnot(None)]

        # The latest-gen scope is applied as a JOIN below, not as a
        # `generation_id IN (subquery)` filter: as an IN-subquery the planner
        # re-scanned the latest-gen set once per candidate row and fell back
        # to a nested loop (~50k block reads on a 2.8 GB table; 10.2 s on
        # ZJS Fälle — the [hotfix] 11f3080 measurements: 10185 ms -> 2645 ms,
        # byte-identical output). The join cannot duplicate rows:
        # latest_gen_ids_subq yields DISTINCT gen_ids (row_number()=1 per
        # (task_id, model_id) partition, and id is the PK).
        def _scope_to_latest_gens(stmt):
            if latest_gen_ids_subq is None:
                return stmt
            return stmt.join(
                latest_gen_ids_subq,
                latest_gen_ids_subq.c.gen_id == MK.generation_id,
            )

        # The current row per cell (shared/current_scores.py): one per
        # (generation, evaluation config, prediction field, reference field),
        # the newest row with a score winning, so a failed re-run never blanks
        # a score and the rows a judge reading its references itself wrote
        # per reference field count once. Filters
        # MUST apply before the window: a row without the selected metric
        # must not win its partition and then be discarded.
        project_configs_by_id = current_scores.configs_by_id(project.evaluation_config)
        cell_partition = current_scores.sql_cell_partition(
            MK.generation_id, MK.evaluation_config_id, MK.field_name, project_configs_by_id
        )
        ranked = _scope_to_latest_gens(
            select(
                MK.task_evaluation_id.label("id"),
                MK.task_id,
                MK.generation_id,
                MK.evaluation_config_id,
                MK.field_name,
                MK.metrics_lite.label("metrics"),
                MK.created_at,
                func.row_number()
                .over(
                    partition_by=cell_partition,
                    order_by=current_scores.sql_current_rank_order(
                        MK.metrics_lite, MK.created_at, MK.task_evaluation_id
                    ),
                )
                .label("rn"),
            )
            .where(*gen_filters)
        ).subquery()

        sample_results = (
            await db.execute(
                select(
                    ranked.c.id,
                    ranked.c.task_id,
                    ranked.c.generation_id,
                    ranked.c.evaluation_config_id,
                    ranked.c.field_name,
                    ranked.c.metrics,
                    GenerationModel.model_id,
                    ranked.c.created_at,
                )
                .join(GenerationModel, ranked.c.generation_id == GenerationModel.id)
                .where(ranked.c.rn == 1)
            )
        ).all()
        gen_shown = None
        if selection is not None:
            # Generations have no submitting account: the default official
            # config, else another config of the group that has a score.
            gen_shown = teacher_current_rows(
                selection, sample_results, configs_by_id=project_configs_by_id
            )
            sample_results = [r for r in sample_results if str(r.id) in gen_shown]

        # Phase 6.3: count suppressed runs so consumers see the
        # deduplication footprint. Per cell a single current row is
        # surfaced; older runs survive in the DB but get filtered out here.
        # Without this audit trail a leaderboard score could swing on
        # re-evaluation with no record of which historical run was hidden.
        #
        # Windowless equivalent of COUNT(*) WHERE rn > 1: total candidate
        # rows minus the number of cell partitions.
        suppressed_count = (
            (
                await db.execute(
                    _scope_to_latest_gens(
                        select(
                            func.count()
                            - func.count(distinct(tuple_(*cell_partition)))
                        ).where(*gen_filters)
                    )
                )
            ).scalar()
            or 0
        )
        deduplication_summary = {
            "scope": "(generation_id, evaluation_config_id, prediction_field, reference_field)",
            "policy": "newest_scored_row_wins",
            "suppressed_run_count": int(suppressed_count),
        }

        # Query 2: Get annotation-based evaluation results (generation_id IS NULL)

        ann_query = select(
            MK.task_evaluation_id.label("id"),
            MK.task_id,
            MK.annotation_id,
            MK.field_name,
            MK.evaluation_config_id,
            MK.metrics_lite.label("metrics"),
            MK.created_at,
        ).where(
            # Same semi-join run scope as the gen branch (issue #280);
            # still no run-status filter (#278).
            *scope_filters,
            MK.generation_id.is_(None),
            MK.annotation_id.isnot(None),
        )
        if latest_ann_ids_subq is not None:
            # Same IN-subquery -> JOIN rewrite as the generation branch above,
            # for the same reason. latest_ann_ids_subq is likewise DISTINCT
            # (row_number()=1 per (task_id, completed_by), id is the PK), so
            # no row duplication.
            ann_query = ann_query.join(
                latest_ann_ids_subq,
                latest_ann_ids_subq.c.ann_id == MK.annotation_id,
            )
        annotation_eval_results = (await db.execute(ann_query)).all()
        if not include_history:
            # The current row per cell (shared/current_scores.py); the
            # project's configs resolve the on-submit rows labelled with a
            # model-side selector to the answer field they graded.
            annotation_eval_results = list(
                current_scores.pick_current(
                    annotation_eval_results, project_configs_by_id
                ).values()
            )
        if selection is not None and annotation_eval_results:
            submitter_ids = (
                await db.execute(
                    select(Annotation.completed_by)
                    .where(
                        Annotation.id.in_(
                            list({r.annotation_id for r in annotation_eval_results})
                        )
                    )
                    .distinct()
                )
            ).scalars().all()
            selection = await load_method_selection(db, project, submitter_ids)

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
        model_export_labels: dict = {}

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
        cell_score_buckets: dict = {}  # {(task_id, model_id): [(official, created_at, score), ...]}
        model_scores: dict = {mid: [] for mid in model_ids}

        for result in sample_results:
            task_id = result.task_id
            model_id = result.model_id
            metrics = result.metrics or {}

            score = _extract_primary_score(metrics)

            if score is not None and model_id:
                own = gen_shown is None or gen_shown[str(result.id)] is None
                cell_score_buckets.setdefault((task_id, model_id), []).append(
                    (own, result.created_at, score)
                )

        for (task_id, model_id), entries in cell_score_buckets.items():
            if include_history:
                cell_score = sum(e[2] for e in entries) / len(entries)
            else:
                # Latest-wins, a score of the official config over a
                # stand-in's: the max (official, created_at).
                cell_score = max(
                    entries,
                    key=lambda e: (e[0], e[1] or datetime.min.replace(tzinfo=timezone.utc)),
                )[2]
            task_scores.setdefault(task_id, {})[model_id] = cell_score
            model_scores[model_id].append(cell_score)

        # Process annotation-based results: add as synthetic annotator "models"
        if annotation_eval_results:
            await _add_annotator_cells(
                db,
                annotation_eval_results,
                include_history=include_history,
                task_scores=task_scores,
                model_scores=model_scores,
                model_ids=model_ids,
                model_name_map=model_name_map,
                model_export_labels=model_export_labels,
                selection=selection,
                configs_by_id=project_configs_by_id,
            )

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
            # File-safe twin of `model_names` for the annotator columns: what
            # the grid's CSV / JSON download writes instead.
            "model_export_labels": model_export_labels,
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
    task_id: str = Query(..., description="Task ID"),
    model_id: str = Query(..., description="Model ID"),
    include_history: bool = Query(
        True,
        description=(
            "Include all historical results. When false, only the current row "
            "of each (subject, evaluation config, prediction field, reference "
            "field) cell (shared/current_scores.py), and for an annotator only their "
            "latest answer to the task."
        ),
    ),
    evaluation_config_ids: Optional[str] = Query(
        None,
        description="Comma-separated evaluation config ids: only rows of these configs.",
    ),
    method_group: Optional[str] = Query(
        None,
        description=(
            "Only rows of this method group's configs (shared/evaluation_methods.py)."
        ),
    ),
    include_research: bool = Query(
        True,
        description=(
            "When false, leave out rows that are research data for the subject "
            "(a config the method selection does not make official for it)."
        ),
    ),
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

        if not await check_project_accessible_async(db, current_user, task.project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        await _require_content_access(db, current_user, task.project_id)

        if model_id.startswith("annotator:"):
            # Annotation-based evaluation: the suffix after `annotator:` is the
            # annotator's *display name*, computed by `by-task-model` /
            # `evaluated-models` as: pseudonym (if use_pseudonym) → name →
            # username. So resolve back through the same precedence rather
            # than assuming `username` literally — otherwise users whose
            # display name comes from `name` or `pseudonym` (e.g. the
            # imported "Imported User <hash>" cohort) won't be found and the
            # detail modal renders empty.
            # Each field only matches when it IS the user's display label, and
            # only users who annotated this task are candidates, as in the
            # annotation filter (annotations.py): a real name or login never
            # resolves a user shown by pseudonym, so this is no lookup of who
            # is behind a pseudonym.
            from sqlalchemy import and_, exists, or_

            from models import User as DBUser

            display = model_id.split(":", 1)[1]
            shows_alias = and_(
                DBUser.use_pseudonym.is_(True),
                DBUser.pseudonym.isnot(None),
                DBUser.pseudonym != "",
            )
            has_name = and_(DBUser.name.isnot(None), DBUser.name != "")
            user = (
                await db.execute(
                    select(DBUser).where(
                        exists().where(
                            Annotation.task_id == task_id,
                            Annotation.completed_by == DBUser.id,
                        ),
                        or_(
                            and_(shows_alias, DBUser.pseudonym == display),
                            and_(~shows_alias, has_name, DBUser.name == display),
                            and_(~shows_alias, ~has_name, DBUser.username == display),
                        ),
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

        # Current row per cell (shared/current_scores.py), over every row of
        # the cell before any filter, so `is_current` means the same in every
        # view of it.
        project = (
            await db.execute(select(Project).where(Project.id == task.project_id))
        ).scalar_one_or_none()
        project_configs_by_id = current_scores.configs_by_id(
            getattr(project, "evaluation_config", None)
        )
        current_ids = current_scores.current_row_ids(sample_results, project_configs_by_id)

        submitter_of: dict = {}
        annotation_ids = list({sr.annotation_id for sr in sample_results if sr.annotation_id})
        if annotation_ids:
            submitter_of = dict(
                (
                    await db.execute(
                        select(Annotation.id, Annotation.completed_by).where(
                            Annotation.id.in_(annotation_ids)
                        )
                    )
                ).all()
            )

        def _config_of(sr) -> str:
            return current_scores.cell_config_id(sr.evaluation_config_id, sr.field_name)

        # Also in the research view: it labels research rows and stand-ins.
        selection = None
        if project is not None:
            selection = await load_method_selection(
                db, project, set(submitter_of.values())
            )

        # The rows a teacher view shows (evaluation_methods.teacher_rows):
        # per cell the official config's, else another config of the group
        # that has a score, which then stands in for it, with the history of
        # the same config. Over every config's rows, before any scope narrows
        # them.
        shown: dict = {}
        if selection is not None:
            shown = teacher_rows(selection, sample_results, submitter_of, project_configs_by_id)

        wanted_configs = {
            c.strip() for c in (evaluation_config_ids or "").split(",") if c.strip()
        }
        if method_group and selection is not None:
            wanted_configs |= set(selection.groups.get(method_group) or [])
        if wanted_configs or (method_group and selection is not None):
            sample_results = [sr for sr in sample_results if _config_of(sr) in wanted_configs]

        def _config_label(config_id):
            config = project_configs_by_id.get(config_id or "") or {}
            label = config.get("display_name")
            return label.strip() if isinstance(label, str) and label.strip() else None

        def _stands_in_for(sr):
            return shown.get(str(sr.id))

        def _official(sr) -> bool:
            if selection is None:
                return True
            if _stands_in_for(sr) is not None:
                return True
            return selection.is_official(_config_of(sr), submitter_of.get(sr.annotation_id))

        if not include_research and selection is not None:
            sample_results = [sr for sr in sample_results if str(sr.id) in shown]

        if not include_history:
            sample_results = [sr for sr in sample_results if sr.id in current_ids]
            if not model_id.startswith("annotator:") and not generation_id:
                # The model's latest generation only, like the grid's cell.
                latest_gen = (
                    await db.execute(
                        select(GenerationModel.id)
                        .where(
                            GenerationModel.task_id == task_id,
                            GenerationModel.model_id == model_id,
                            GenerationModel.status == "completed",
                        )
                        .order_by(GenerationModel.created_at.desc(), GenerationModel.id.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                sample_results = [
                    sr for sr in sample_results if sr.generation_id == latest_gen
                ]
            if annotation_ids:
                # The annotator's latest answer only, like the grid's cell.
                latest = (
                    await db.execute(
                        select(Annotation.id)
                        .where(
                            Annotation.id.in_(annotation_ids),
                            Annotation.was_cancelled == False,  # noqa: E712
                        )
                        .order_by(Annotation.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                sample_results = [
                    sr for sr in sample_results
                    if sr.annotation_id is None or sr.annotation_id == latest
                ]

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
                "evaluation_config_id": _config_of(sr) or None,
                # The current row of its cell; the others are history.
                "is_current": sr.id in current_ids,
                # False when the row is research data for its subject.
                "is_official": _official(sr),
                # The official config this row's score stands in for, when
                # that config has no score for the subject; else None.
                "stands_in_for_config_id": _stands_in_for(sr),
                "evaluation_config_label": _config_label(_config_of(sr)),
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
