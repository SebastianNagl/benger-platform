"""
Shared helper functions for projects API.

These functions provide common operations used across multiple project endpoints.
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from sqlalchemy import case, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload

from models import (
    EvaluationRun,
    Generation,
    LtiPlatformRegistration,
    LtiResourceLink,
    OrganizationMembership,
    OrganizationRole,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from org_groups import (
    attachment_eligible,
    attachment_group_clause,
    build_select_group_admin_on_attachments,
    drop_protected_lti_attachments,
    get_attachment_group_map,
    get_attachment_group_map_async,
    get_lti_attachment_map,
    get_lti_attachment_map_async,
    get_lti_row_org_ids,
    get_lti_row_org_ids_async,
    get_user_group_context,
    get_user_group_context_async,
    grants_full_tier,
    lti_staff_role,
    non_lti_attachment,
)
from project_models import (
    Annotation,
    MarketplaceEntitlement,
    Project,
    ProjectOrganization,
    ProjectShareMember,
    Task,
    TaskAssignment,
)
from project_schemas import ProjectResponse
from project_window import (
    project_reads_allowed,
    project_window_state,
    project_writes_allowed,
)


# Re-export the noise filter from /shared. Single source of truth lives in
# metric_filters so the API, the worker, and the aggregate-summaries
# refresh job agree on what counts as a "real" metric — historically the
# worker couldn't import this module at all, so the live and precomputed
# paths could silently disagree. See services/shared/metric_filters.py.
from metric_filters import (  # noqa: F401 — re-exported for legacy callers
    _METRIC_EXCLUDED_KEYS,
    _METRIC_NOISE_SUFFIXES,
    _metric_key_is_real,
    metric_key_counts_as_evaluation,
)


def attempt_score_from_metrics(metrics: Any) -> Optional[float]:
    """Unified attempt score (0..1) from a ``TaskEvaluation.metrics`` blob.

    Every metric writer persists the nested-canonical shape
    ``{"<metric_key>": {"value": <0..1>, ...}, ...}`` — falloesung, generic
    llm_judge and korrektur rows alike; no writer produces a top-level
    ``"value"`` key. A top-level ``"value"`` is still honored first so a
    future flat writer keeps working. A row normally carries exactly one
    real metric; if several are present the largest non-null value wins
    (order-independent). Returns ``None`` for rows without a usable score
    (e.g. judge-error rows, where ``value`` is null).
    """
    if not isinstance(metrics, dict):
        return None
    top = metrics.get("value")
    if isinstance(top, (int, float)) and not isinstance(top, bool):
        return float(top)
    best: Optional[float] = None
    for key, sub in metrics.items():
        if not _metric_key_is_real(key) or not isinstance(sub, dict):
            continue
        value = sub.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            best = float(value) if best is None else max(best, float(value))
    return best


def attempt_grade_points_from_metrics(metrics: Any) -> Optional[float]:
    """Notenpunkte (0..18) of an attempt row, when its writer produced them.

    Lifted from ``metrics[<metric>].details.grade_points`` (falloesung,
    korrektur and rubric writers) or the flat ``<metric>_grade_points``
    sibling (bulk judge rows); ``None`` for rows without a grade so callers
    fall back to their own conversion.
    """
    if not isinstance(metrics, dict):
        return None
    for key, sub in metrics.items():
        if not _metric_key_is_real(key):
            continue
        candidates = []
        if isinstance(sub, dict) and isinstance(sub.get("details"), dict):
            candidates.append(sub["details"].get("grade_points"))
        candidates.append(metrics.get(f"{key}_grade_points"))
        for value in candidates:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def _scored_pairs_query(db: Session):
    """Base query that yields (project_id, subject_id, config_id, metric_key)
    for every (annotation|generation, evaluation config, metric) cell that has
    at least one scored row in a completed evaluation run. Caller adds project
    filters + DISTINCT. The config id keeps two judges of the same metric on
    one answer apart; re-runs of one config still collapse."""
    subject_expr = func.coalesce(
        TaskEvaluation.annotation_id, TaskEvaluation.generation_id
    )
    metrics_jsonb = cast(TaskEvaluation.metrics, JSONB)
    return (
        db.query(
            EvaluationRun.project_id,
            subject_expr.label("subject_id"),
            func.coalesce(TaskEvaluation.evaluation_config_id, "").label("config_id"),
            func.jsonb_object_keys(metrics_jsonb).label("metric_key"),
        )
        .select_from(TaskEvaluation)
        .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
        .filter(
            EvaluationRun.status == "completed",
            subject_expr.isnot(None),
            TaskEvaluation.metrics.isnot(None),
            func.jsonb_typeof(metrics_jsonb) == "object",
        )
    )


def _async_scored_pairs_select():
    """select()-based twin of :func:`_scored_pairs_query` for the async lane.

    Yields (project_id, subject_id, config_id, metric_key) for every
    (subject, evaluation config, metric) cell with a scored row in a
    completed run. Caller adds project filters +
    ``.distinct()`` exactly like the sync builder.
    """
    subject_expr = func.coalesce(
        TaskEvaluation.annotation_id, TaskEvaluation.generation_id
    )
    metrics_jsonb = cast(TaskEvaluation.metrics, JSONB)
    return (
        select(
            EvaluationRun.project_id,
            subject_expr.label("subject_id"),
            func.coalesce(TaskEvaluation.evaluation_config_id, "").label("config_id"),
            func.jsonb_object_keys(metrics_jsonb).label("metric_key"),
        )
        .select_from(TaskEvaluation)
        .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
        .where(
            EvaluationRun.status == "completed",
            subject_expr.isnot(None),
            TaskEvaluation.metrics.isnot(None),
            func.jsonb_typeof(metrics_jsonb) == "object",
        )
    )


def _generation_models_count(project: Project) -> int:
    selected = (project.generation_config or {}).get("selected_configuration") or {}
    models = selected.get("models") or []
    return len(models)


def _evaluation_methods_count(project: Project) -> int:
    """Number of distinct evaluation methods configured on the project.

    Counts entries in evaluation_config.evaluation_configs (new shape, one
    entry per field × method) and falls back to selected_methods (legacy
    per-field map).
    """
    eval_cfg = project.evaluation_config or {}
    new_shape = eval_cfg.get("evaluation_configs") or []
    if new_shape:
        return len(new_shape)
    legacy = eval_cfg.get("selected_methods") or {}
    return len(legacy)


def _mix_progress(parts: List[tuple]) -> float:
    """parts = [(completed, expected), ...] across stages. Stages with
    expected == 0 are ignored so the bar isn't permanently stuck at 0 when
    a stage is enabled but hasn't been configured yet."""
    relevant = [(c, e) for (c, e) in parts if e > 0]
    if not relevant:
        return 0.0
    completed_sum = sum(c for c, _ in relevant)
    expected_sum = sum(e for _, e in relevant)
    return min(100.0, (completed_sum / expected_sum) * 100)


def _progress_parts(
    project: Optional[Project],
    response: ProjectResponse,
    completed_generations: int,
) -> List[tuple]:
    """Per-stage (completed, expected) tuples gated on enable_* flags.

    Stages with expected == 0 (e.g. evaluation enabled but no eval methods
    configured yet) are still returned; _mix_progress skips them so the
    progress bar isn't pinned at 0 forever for half-configured projects.
    """
    if project is None:
        return []

    parts: List[tuple] = []

    if getattr(project, "enable_annotation", True):
        parts.append((response.completed_tasks_count, response.task_count))

    gen_models = _generation_models_count(project)
    if getattr(project, "enable_generation", True):
        # One ResponseGeneration is expected per (task × configured model).
        parts.append((completed_generations, response.task_count * gen_models))

    if getattr(project, "enable_evaluation", True):
        # One EvaluationRun is expected per (configured model × configured
        # eval method). Cap the completed count at expected so a
        # mis-tracked re-run can't push progress over 100 %.
        eval_methods = _evaluation_methods_count(project)
        expected_eval = gen_models * eval_methods
        completed_eval = (
            min(response.evaluations_completed_count, expected_eval)
            if expected_eval > 0
            else 0
        )
        parts.append((completed_eval, expected_eval))

    return parts


def apply_mixed_progress(
    project: Project,
    response: ProjectResponse,
    completed_generations: int,
) -> None:
    """Set response.progress_percentage to the per-stage mix gated on enable_* flags.

    Shared by `calculate_project_stats` (single-project path) and the
    batch path in list_projects so both produce identical numbers.
    """
    response.progress_percentage = _mix_progress(
        _progress_parts(project, response, completed_generations)
    )


def calculate_project_stats(
    db: Session,
    project_id: str,
    response: ProjectResponse,
    project: Optional[Project] = None,
) -> None:
    """Calculate and set project statistics on a response object.

    Progress is a weighted mix across the enable_annotation / enable_generation
    / enable_evaluation stages: sum(completed) / sum(expected) across stages
    that are both enabled and have nonzero expected work. A project with only
    annotation enabled (the historical default) behaves identically to before.

    NOTE: For batch operations (e.g., list_projects), use calculate_project_stats_batch
    instead to avoid N+1 query problem.
    """

    if project is None:
        project = db.query(Project).filter(Project.id == project_id).first()

    response.task_count = db.query(Task).filter(Task.project_id == project_id).count()
    # Count annotations that aren't cancelled
    response.annotation_count = (
        db.query(Annotation)
        .filter(Annotation.project_id == project_id, Annotation.was_cancelled == False)  # noqa: E712
        .count()
    )
    response.completed_tasks_count = (
        db.query(Task).filter(Task.project_id == project_id, Task.is_labeled == True).count()  # noqa: E712
    )

    # Generation completion (tasks × models) — mirrors the logic in
    # calculate_generation_stats but the count is needed here too so the
    # progress mix has a numerator for the generation stage.
    completed_generations = 0
    gen_models = _generation_models_count(project) if project is not None else 0
    if response.task_count > 0 and gen_models > 0:
        completed_generations = (
            db.query(ResponseGeneration)
            .join(Task, ResponseGeneration.task_id == Task.id)
            .filter(
                Task.project_id == project_id,
                ResponseGeneration.status == "completed",
            )
            .count()
        )

    # Evaluation tallies — count distinct (subject, metric) pairs that have at
    # least one scored row in a completed run. Matches the user's intuition of
    # "how many of my answers have been evaluated on how many metrics"; the old
    # job-count masked partial coverage (a 1-job run scoring 314 of 500
    # subjects looked identical to a fully-scored run).
    #
    # Reads from the precomputed `project_summaries.evaluation_pairs_count`
    # (refreshed by the `recompute_aggregates` Celery task hourly). Falls
    # back to the original live computation when no precomputed row exists —
    # brand-new projects shouldn't render zero before the next refresh.
    from aggregate_summaries import read_project_summary

    summary = read_project_summary(db, project_id, period="overall")
    if response.task_count == 0:
        # No tasks -> no evaluable pairs. Guards against a stale precomputed
        # summary claiming evaluations after the last task was deleted (the
        # summary only refreshes hourly / on mutation endpoints).
        response.evaluation_count = 0
    elif summary is not None:
        response.evaluation_count = int(summary.evaluation_pairs_count or 0)
    else:
        pairs = (
            _scored_pairs_query(db)
            .filter(EvaluationRun.project_id == project_id)
            .distinct()
            .all()
        )
        response.evaluation_count = sum(
            1
            for _pid, _sub_id, _cfg, mk in pairs
            if metric_key_counts_as_evaluation(mk)
        )
    response.evaluations_completed_count = response.evaluation_count

    # Mirror to the legacy aliases so frontends reading either name see the
    # same value (the labeling page reads num_tasks for the "Task X of Y"
    # progress counter).
    response.num_tasks = response.task_count
    response.num_annotations = response.annotation_count

    apply_mixed_progress(project, response, completed_generations)


def _build_select_task_count(project_id: str):
    return select(func.count()).select_from(Task).where(Task.project_id == project_id)


def _build_select_annotation_count(project_id: str):
    return (
        select(func.count())
        .select_from(Annotation)
        .where(
            Annotation.project_id == project_id,
            Annotation.was_cancelled == False,  # noqa: E712
        )
    )


def _build_select_completed_task_count(project_id: str):
    return (
        select(func.count())
        .select_from(Task)
        .where(Task.project_id == project_id, Task.is_labeled == True)  # noqa: E712
    )


def _build_select_completed_generations(project_id: str):
    return (
        select(func.count())
        .select_from(ResponseGeneration)
        .join(Task, ResponseGeneration.task_id == Task.id)
        .where(
            Task.project_id == project_id,
            ResponseGeneration.status == "completed",
        )
    )


def _build_select_project_summary(project_id: str, period: str = "overall"):
    from models import ProjectSummary

    return select(ProjectSummary).where(
        ProjectSummary.project_id == project_id,
        ProjectSummary.period == period,
    )


async def calculate_project_stats_async(
    db: AsyncSession,
    project_id: str,
    response: ProjectResponse,
    project: Optional[Project] = None,
) -> None:
    """Async equivalent of :func:`calculate_project_stats`.

    Mirrors the sync logic exactly: per-stage counts + precomputed-summary
    read with a live fallback for brand-new projects. The summary read is
    inlined (rather than calling ``read_project_summary``) because that
    helper lives in /shared on the sync API.
    """
    if project is None:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()

    response.task_count = (
        await db.execute(_build_select_task_count(project_id))
    ).scalar() or 0
    response.annotation_count = (
        await db.execute(_build_select_annotation_count(project_id))
    ).scalar() or 0
    response.completed_tasks_count = (
        await db.execute(_build_select_completed_task_count(project_id))
    ).scalar() or 0

    completed_generations = 0
    gen_models = _generation_models_count(project) if project is not None else 0
    if response.task_count > 0 and gen_models > 0:
        completed_generations = (
            await db.execute(_build_select_completed_generations(project_id))
        ).scalar() or 0

    summary = (
        await db.execute(_build_select_project_summary(project_id))
    ).scalar_one_or_none()
    if response.task_count == 0:
        # Mirrors the sync guard: a stale summary must not claim evaluations
        # for a project whose last task was just deleted.
        response.evaluation_count = 0
    elif summary is not None:
        response.evaluation_count = int(summary.evaluation_pairs_count or 0)
    else:
        pairs_result = await db.execute(
            _async_scored_pairs_select()
            .where(EvaluationRun.project_id == project_id)
            .distinct()
        )
        response.evaluation_count = sum(
            1
            for _pid, _sub_id, _cfg, mk in pairs_result.all()
            if metric_key_counts_as_evaluation(mk)
        )
    response.evaluations_completed_count = response.evaluation_count

    response.num_tasks = response.task_count
    response.num_annotations = response.annotation_count

    apply_mixed_progress(project, response, completed_generations)


def calculate_project_stats_batch(db: Session, project_ids: List[str]) -> Dict[str, Dict[str, int]]:
    """Calculate project statistics for multiple projects.

    Reads from the precomputed `project_summaries` table (period='overall',
    refreshed by the `recompute_aggregates` Celery task) so the common case
    is one indexed lookup keyed by `project_id IN (...)`. For brand-new
    projects that don't have a summary row yet (created between beat runs),
    falls back to live aggregation queries scoped to *only* those missing
    ids — the established 99% of the list pays nothing.

    Returns: Dict mapping project_id to stats dict with keys
    `task_count`, `completed_tasks_count`, `annotation_count`,
    `evaluation_count`, `evaluations_completed_count`.
    """
    from models import ProjectSummary
    from sqlalchemy import select as sa_select

    if not project_ids:
        return {}

    # Read all four counters from the precomputed table in one indexed query.
    summary_rows = db.execute(
        sa_select(
            ProjectSummary.project_id,
            ProjectSummary.total_tasks,
            ProjectSummary.labeled_tasks,
            ProjectSummary.annotations_count,
            ProjectSummary.evaluation_pairs_count,
        ).where(
            ProjectSummary.project_id.in_(project_ids),
            ProjectSummary.period == "overall",
        )
    ).all()

    stats_map: Dict[str, Dict[str, int]] = {}
    for pid, total, labeled, ann, eval_pairs in summary_rows:
        stats_map[pid] = {
            'task_count': int(total or 0),
            'completed_tasks_count': int(labeled or 0),
            'annotation_count': int(ann or 0),
            'evaluation_count': int(eval_pairs or 0),
            'evaluations_completed_count': int(eval_pairs or 0),
        }

    missing_summary_ids = [pid for pid in project_ids if pid not in stats_map]
    if missing_summary_ids:
        for pid in missing_summary_ids:
            stats_map[pid] = {
                'task_count': 0,
                'completed_tasks_count': 0,
                'annotation_count': 0,
                'evaluation_count': 0,
                'evaluations_completed_count': 0,
            }

        task_stats = (
            db.query(
                Task.project_id,
                func.count(Task.id).label('task_count'),
                func.sum(case((Task.is_labeled == True, 1), else_=0)).label(  # noqa: E712
                    'completed_tasks_count'
                ),
            )
            .filter(Task.project_id.in_(missing_summary_ids))
            .group_by(Task.project_id)
            .all()
        )
        for stat in task_stats:
            stats_map[stat.project_id]['task_count'] = stat.task_count or 0
            stats_map[stat.project_id]['completed_tasks_count'] = (
                stat.completed_tasks_count or 0
            )

        # Match the worker's filter (services/aggregate_summaries._compute_project_summary)
        # so freshly-created projects display the same number both before and
        # after the next recompute_aggregates cycle.
        annotation_stats = (
            db.query(
                Annotation.project_id, func.count(Annotation.id).label('annotation_count')
            )
            .filter(
                Annotation.project_id.in_(missing_summary_ids),
                Annotation.was_cancelled == False,  # noqa: E712
                Annotation.result != None,  # noqa: E711
                func.jsonb_array_length(cast(Annotation.result, JSONB)) > 0,
            )
            .group_by(Annotation.project_id)
            .all()
        )
        for stat in annotation_stats:
            stats_map[stat.project_id]['annotation_count'] = stat.annotation_count or 0

        live_pairs = (
            _scored_pairs_query(db)
            .filter(EvaluationRun.project_id.in_(missing_summary_ids))
            .distinct()
            .all()
        )
        for pid, _sub_id, _cfg, metric_key in live_pairs:
            if not metric_key_counts_as_evaluation(metric_key):
                continue
            stats_map[pid]['evaluation_count'] += 1
            stats_map[pid]['evaluations_completed_count'] += 1

    return stats_map


def calculate_generation_stats(db: Session, project: Project, response: ProjectResponse) -> None:
    """Calculate and set generation-related statistics for the /generation page"""

    # 1. Check if project has generation_config with prompt structures (Issue #762)
    generation_config = project.generation_config or {}
    prompt_structures = generation_config.get("prompt_structures", {})
    response.generation_config_ready = bool(prompt_structures)

    # For backward compatibility, generation_prompts_ready now checks prompt structures
    response.generation_prompts_ready = bool(prompt_structures)

    # 2. Total Generation rows for this project — feeds the Statistiken
    # "Generations" tile on the project detail page (rendered conditionally
    # when > 0).
    response.generation_count = (
        db.query(func.count(Generation.id))
        .join(Task, Generation.task_id == Task.id)
        .filter(Task.project_id == project.id)
        .scalar()
    ) or 0

    # 3. Count configured models in generation_config (single source of truth)
    response.generation_models_count = 0
    if (
        project.generation_config
        and project.generation_config.get('selected_configuration')
        and project.generation_config['selected_configuration'].get('models')
    ):
        response.generation_models_count = len(
            project.generation_config['selected_configuration']['models']
        )

    # 4. Check if generation is complete for all tasks and all models
    response.generation_completed = False
    if response.task_count > 0 and response.generation_models_count > 0:
        # Get all task IDs for this project
        project_task_ids = [
            task.id for task in db.query(Task.id).filter(Task.project_id == project.id).all()
        ]

        if project_task_ids:
            # Count completed generations for tasks in this project
            completed_generations = (
                db.query(ResponseGeneration)
                .filter(
                    ResponseGeneration.task_id.in_(project_task_ids),
                    ResponseGeneration.status == 'completed',
                )
                .count()
            )

            expected_generations = response.task_count * response.generation_models_count
            response.generation_completed = completed_generations >= expected_generations


async def calculate_generation_stats_async(
    db: AsyncSession, project: Project, response: ProjectResponse
) -> None:
    """Async equivalent of :func:`calculate_generation_stats`."""
    generation_config = project.generation_config or {}
    prompt_structures = generation_config.get("prompt_structures", {})
    response.generation_config_ready = bool(prompt_structures)
    response.generation_prompts_ready = bool(prompt_structures)

    response.generation_count = (
        await db.execute(
            select(func.count(Generation.id))
            .join(Task, Generation.task_id == Task.id)
            .where(Task.project_id == project.id)
        )
    ).scalar() or 0

    response.generation_models_count = 0
    if (
        project.generation_config
        and project.generation_config.get('selected_configuration')
        and project.generation_config['selected_configuration'].get('models')
    ):
        response.generation_models_count = len(
            project.generation_config['selected_configuration']['models']
        )

    response.generation_completed = False
    if response.task_count > 0 and response.generation_models_count > 0:
        task_id_result = await db.execute(
            select(Task.id).where(Task.project_id == project.id)
        )
        project_task_ids = [row[0] for row in task_id_result.all()]

        if project_task_ids:
            completed_generations = (
                await db.execute(
                    select(func.count())
                    .select_from(ResponseGeneration)
                    .where(
                        ResponseGeneration.task_id.in_(project_task_ids),
                        ResponseGeneration.status == 'completed',
                    )
                )
            ).scalar() or 0

            expected_generations = response.task_count * response.generation_models_count
            response.generation_completed = completed_generations >= expected_generations


def calculate_generation_stats_batch(
    db: Session, projects: List[Project]
) -> Dict[str, Dict[str, int]]:
    """Batch generation stats for many projects.

    Reads from `project_summaries` (period='overall') for every project that
    has a summary row; falls back to the original two grouped queries only
    for projects the worker hasn't summarized yet. After Phase 6.2 the
    summary table carries both the total Generation count and the
    status='completed' ResponseGeneration count, so the dashboard pays
    nothing on the established 99 % of projects.

    Returns: project_id -> {generation_count, completed_generations}.
    Caller still computes config_ready / prompts_ready / models_count /
    completed in-process from each Project's generation_config (no DB hit).
    """
    from models import ProjectSummary
    from sqlalchemy import select as sa_select

    if not projects:
        return {}

    project_ids = [p.id for p in projects]

    out: Dict[str, Dict[str, int]] = {}

    # Step 1: read from the precomputed summary in one indexed query.
    summary_rows = db.execute(
        sa_select(
            ProjectSummary.project_id,
            ProjectSummary.generations_count,
            ProjectSummary.completed_response_generations_count,
        ).where(
            ProjectSummary.project_id.in_(project_ids),
            ProjectSummary.period == "overall",
        )
    ).all()
    for pid, gen_c, completed_c in summary_rows:
        out[pid] = {
            "generation_count": int(gen_c or 0),
            "completed_generations": int(completed_c or 0),
        }

    # Step 2: live fallback only for projects without a summary row yet.
    missing_summary_ids = [pid for pid in project_ids if pid not in out]
    for pid in missing_summary_ids:
        out[pid] = {"generation_count": 0, "completed_generations": 0}
    if not missing_summary_ids:
        return out

    # Query 1: total Generation rows per missing project
    gen_counts = (
        db.query(Task.project_id, func.count(Generation.id).label("c"))
        .join(Generation, Generation.task_id == Task.id)
        .filter(Task.project_id.in_(missing_summary_ids))
        .group_by(Task.project_id)
        .all()
    )

    # Query 2: completed ResponseGeneration rows per missing project
    completed_counts = (
        db.query(Task.project_id, func.count(ResponseGeneration.id).label("c"))
        .join(ResponseGeneration, ResponseGeneration.task_id == Task.id)
        .filter(
            Task.project_id.in_(missing_summary_ids),
            ResponseGeneration.status == "completed",
        )
        .group_by(Task.project_id)
        .all()
    )

    for row in gen_counts:
        out[row.project_id]["generation_count"] = row.c or 0
    for row in completed_counts:
        out[row.project_id]["completed_generations"] = row.c or 0
    return out


def apply_generation_stats(
    project: Project, response: ProjectResponse, batch_stats: Dict[str, int]
) -> None:
    """In-process variant of calculate_generation_stats: fills the same fields
    on `response` using pre-fetched per-project counts (no DB query)."""
    generation_config = project.generation_config or {}
    prompt_structures = generation_config.get("prompt_structures", {})
    response.generation_config_ready = bool(prompt_structures)
    response.generation_prompts_ready = bool(prompt_structures)
    response.generation_count = int(batch_stats.get("generation_count", 0))

    response.generation_models_count = 0
    selected = (project.generation_config or {}).get("selected_configuration") or {}
    if selected.get("models"):
        response.generation_models_count = len(selected["models"])

    response.generation_completed = False
    if response.task_count > 0 and response.generation_models_count > 0:
        expected = response.task_count * response.generation_models_count
        response.generation_completed = (
            batch_stats.get("completed_generations", 0) >= expected
        )


def get_user_with_memberships(db: Session, user_id: str) -> User:
    """Get user with organization memberships loaded (sync).

    Sync body intentionally kept on the legacy ``db.query`` API so the
    extensive ``db.query``-mocking unit tests keep passing; the async lane
    has its own ``select``-based twin below.
    """
    return (
        db.query(User)
        .options(joinedload(User.organization_memberships))
        .filter(User.id == user_id)
        .first()
    )


def _build_select_user_with_memberships(user_id: str):
    """Shared SQL builder for the async user + memberships eager load.

    joinedload keeps the memberships eagerly populated so callers can read
    ``user.organization_memberships`` in the async lane without a lazy load
    (which would raise MissingGreenlet under the async engine).
    """
    return (
        select(User)
        .options(joinedload(User.organization_memberships))
        .where(User.id == user_id)
    )


async def get_user_with_memberships_async(db: AsyncSession, user_id: str) -> User:
    """Async equivalent of :func:`get_user_with_memberships`."""
    result = await db.execute(_build_select_user_with_memberships(user_id))
    return result.unique().scalar_one_or_none()


async def get_org_membership_role_async(
    db: AsyncSession, user, org_context: Optional[str]
) -> Optional[str]:
    """Resolve the user's active role within ``org_context`` (async).

    Returns the ``OrganizationRole`` value (e.g. ``"ANNOTATOR"``) for the user's
    active membership in that org, or ``None`` when there is no org context
    (private/legacy) or no active membership. Superadmin is not special-cased
    here — callers needing the bypass should check ``user.is_superadmin`` first.
    """
    if not org_context or org_context == "private":
        return None
    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    if not user_with_memberships or not user_with_memberships.organization_memberships:
        return None
    for membership in user_with_memberships.organization_memberships:
        if membership.organization_id == org_context and membership.is_active:
            return membership.role
    return None


def get_accessible_project_ids(
    db: Session,
    user,
    org_context: Optional[str] = None,
    include_all_private: bool = False,
) -> Optional[List[str]]:
    """Get the project IDs a user may open with the full tier.

    The union over every active org membership (the per-org rules of
    :func:`_pick_member_org_projects`), the user's own private projects, the
    LMS-linked private exams they open as staff
    (:func:`get_lti_staff_project_ids`) and the public projects. The list is
    the same whichever organization the client has selected.

    Args:
        db: Database session
        user: Current authenticated user (auth_module User or DB User)
        org_context: Accepted for call-site symmetry and ignored: the
                     selected organization is not a read boundary (the
                     participant and attempted tiers never were either).
        include_all_private: Superadmin-only opt-in. When True, the helper
                     returns None (no filter) so the caller sees every project
                     in the system, including other users' private projects.
                     When False (default) a superadmin sees every org's projects
                     + public projects + their own private, but other users'
                     private projects stay hidden.

    Returns:
        List of accessible project IDs, or None for superadmins with
        include_all_private=True (no filter needed).
    """
    if user.is_superadmin:
        if include_all_private:
            return None
        # Default superadmin view: every project across every org, plus public
        # and own private. Other users' private projects stay hidden until the
        # toggle is flipped. Org context is intentionally ignored — a
        # superadmin's projects browser is org-agnostic.
        rows = (
            db.query(Project.id)
            .filter(
                or_(
                    Project.is_private == False,  # noqa: E712
                    Project.created_by == str(user.id),
                ),
                not_deleted(),
            )
            .all()
        )
        seen = set()
        result = []
        for r in rows:
            if r.id not in seen:
                seen.add(r.id)
                result.append(r.id)
        return result

    public_ids = [
        r.id
        for r in db.query(Project.id)
        .filter(Project.is_public == True, not_deleted())  # noqa: E712
        .all()
    ]

    # Every membership counts (the org context is not a read boundary):
    # own private projects and the LMS-linked exams the caller opens as
    # staff, plus the projects each active membership lists.
    own_private = [
        r.id
        for r in db.query(Project.id)
        .filter(
            Project.is_private == True,  # noqa: E712
            Project.created_by == str(user.id),
            not_deleted(),
        )
        .all()
    ]
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    memberships = [m for m in _memberships_of(user_with_memberships) if m.is_active]
    lti_staff_ids = get_lti_staff_project_ids(db, user, memberships=memberships)
    org_arm: List[str] = []
    if memberships:
        active = {str(m.organization_id): m for m in memberships}
        rows = db.execute(_build_select_member_org_list_rows(active)).all()
        if rows:
            user_groups = get_user_group_context(db, str(user.id))
            protected = _lti_protected_org_ids(
                db, _protected_candidate_orgs(rows, user.id)
            )
            org_arm = _pick_member_org_projects(
                rows, active, user.id, user_groups, lti_staff_ids, protected
            )
    return _dedup_preserve_order(
        own_private + sorted(lti_staff_ids) + org_arm, public_ids
    )


def _build_select_member_org_list_rows(org_ids):
    """Shared SQL builder: every attachment row of the caller's orgs with the
    project columns :func:`_pick_member_org_projects` needs (alive projects
    only). One query for all memberships; the per-row rules are pure."""
    return (
        select(
            ProjectOrganization.project_id,
            ProjectOrganization.organization_id,
            ProjectOrganization.group_id,
            ProjectOrganization.attached_via,
            Project.is_private,
            Project.created_by,
            Project.kind,
            Project.is_archived,
        )
        .join(Project, Project.id == ProjectOrganization.project_id)
        .where(
            ProjectOrganization.organization_id.in_(sorted(str(o) for o in org_ids)),
            not_deleted(),
        )
    )


def _protected_candidate_orgs(rows, user_id) -> set:
    """Pure: the orgs whose LMS-linking rows on other users' non-private
    exams may be protected (the input of the fail-closed hook)."""
    uid = str(user_id)
    return {
        str(r.organization_id)
        for r in rows
        if r.attached_via == "lti"
        and r.kind == "exam"
        and not r.is_private
        and str(r.created_by) != uid
    }


def _role_name(role) -> str:
    """'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR' from an enum or a string."""
    return str(getattr(role, "value", role)).upper()


def _pick_member_org_projects(
    rows, active_memberships, user_id, user_groups, lti_staff_ids, protected_org_ids
) -> List[str]:
    """Pure: the project ids the caller's org memberships list.

    ``rows`` are the rows of :func:`_build_select_member_org_list_rows`,
    ``active_memberships`` maps org id to the caller's active membership.
    Each rule mirrors a per-project decider:

    - the attachment must be eligible (:func:`org_groups.attachment_eligible`:
      org-wide, or the caller's group, or ORG_ADMIN, or the creator);
    - a private project in an org (only LMS linking attaches one) is listed
      for its creator and for the staff the LMS grant opens it to;
    - an ANNOTATOR membership does not list exams (students reach org exams
      through the participant tier) nor archived projects (the archive
      carve-out of ``check_project_accessible``), unless the caller created
      the project or group-admins the attachment's group; a staff membership
      in another attached org may still list the same project;
    - on an org whose connections stay superadmin-run, other authors' exams
      attached only by an LMS link are for its admins and the attachment
      group's admins.
    """
    uid = str(user_id)
    admin_groups = {str(g) for g, is_admin in (user_groups or {}).items() if is_admin}
    protected = {str(o) for o in (protected_org_ids or ()) if o}
    staff_ids = {str(i) for i in (lti_staff_ids or ())}
    picked: List[str] = []
    for r in rows:
        membership = active_memberships.get(str(r.organization_id))
        if membership is None:
            continue
        role = _role_name(membership.role)
        group_id = str(r.group_id) if r.group_id else None
        is_creator = str(r.created_by) == uid
        group_admin = group_id is not None and group_id in admin_groups
        if not attachment_eligible(
            group_id,
            is_creator=is_creator,
            membership_role=membership.role,
            user_groups=user_groups,
        ):
            continue
        if r.is_private and not is_creator and str(r.project_id) not in staff_ids:
            continue
        if role == "ANNOTATOR" and not is_creator and not group_admin:
            if r.kind == "exam" or bool(r.is_archived):
                continue
        if (
            r.attached_via == "lti"
            and r.kind == "exam"
            and not r.is_private
            and not is_creator
            and str(r.organization_id) in protected
            and role != "ORG_ADMIN"
            and not group_admin
        ):
            continue
        picked.append(str(r.project_id))
    return picked


def _dedup_preserve_order(ids, extra=()):
    """Dedup an id list preserving first-seen order, then append `extra` ids
    that weren't already present (also order-preserving). Shared by the
    sync/async accessible-project-id helpers."""
    seen = set()
    result = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            result.append(i)
    for i in extra:
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result


# ── LMS-linked private exams in the project lists (D13) ─────────────────────
# The per-project deciders open another user's private exam to the staff of
# an org it is LMS-linked to (``org_groups.lti_staff_role``). The helpers
# below find those exams in bulk and hand every candidate to that same pure
# predicate, so the lists and the deciders cannot disagree.


def _lti_staff_reach(memberships, user_groups):
    """Where the LMS staff grant can come from (pure; a pre-filter only).

    Returns ``(staff_org_ids, admin_group_ids)``: the orgs with an active
    CONTRIBUTOR or ORG_ADMIN membership, and the groups the user
    group-admins. An attachment outside both never passes
    :func:`org_groups.lti_staff_role`, so skipping it changes nothing.
    """
    staff_org_ids = {
        str(m.organization_id)
        for m in memberships or ()
        if m.is_active and _role_rank(m.role) >= _role_rank("CONTRIBUTOR")
    }
    admin_group_ids = {
        str(gid) for gid, is_admin in (user_groups or {}).items() if is_admin
    }
    return staff_org_ids, admin_group_ids


def _build_select_lti_staff_candidates(user_id: str, staff_org_ids, admin_group_ids):
    """Shared SQL builder: LMS-linking attachments that may open another
    user's private exam to ``user_id``, as (project, org, group) rows.

    Same rows as ``org_groups._lti_attachment_filters`` (``attached_via='lti'``
    and an activity of a connection of that org still points at the exam),
    for many projects at once; change both together. Only rows in the
    ``_lti_staff_reach`` orgs and groups are read.
    """
    still_linked = exists().where(
        LtiResourceLink.project_id == ProjectOrganization.project_id,
        LtiResourceLink.registration_id == LtiPlatformRegistration.id,
        LtiPlatformRegistration.organization_id == ProjectOrganization.organization_id,
    )
    reach = []
    if staff_org_ids:
        reach.append(ProjectOrganization.organization_id.in_(sorted(staff_org_ids)))
    if admin_group_ids:
        reach.append(ProjectOrganization.group_id.in_(sorted(admin_group_ids)))
    return (
        select(
            ProjectOrganization.project_id,
            ProjectOrganization.organization_id,
            ProjectOrganization.group_id,
        )
        .join(Project, Project.id == ProjectOrganization.project_id)
        .where(
            Project.is_private == True,  # noqa: E712
            Project.kind == "exam",
            Project.created_by != str(user_id),
            not_deleted(),
            ProjectOrganization.attached_via == "lti",
            still_linked,
            or_(*reach),
        )
    )


def _pick_lti_staff_projects(rows, memberships, user_groups, protected_org_ids) -> set:
    """Pure: the candidate projects :func:`org_groups.lti_staff_role` grants.

    ``rows`` are the (project, org, group) rows of the builder above. The
    per-project map holds only the caller's reachable orgs; the orgs it
    leaves out never grant anything, so the answer equals the decider's.
    """
    by_project: Dict[str, Dict[str, Optional[str]]] = {}
    for project_id, org_id, group_id in rows:
        by_project.setdefault(str(project_id), {})[str(org_id)] = (
            str(group_id) if group_id else None
        )
    return {
        project_id
        for project_id, lti_attachments in by_project.items()
        if lti_staff_role(
            "exam",
            memberships,
            lti_attachments,
            user_groups,
            protected_org_ids=protected_org_ids,
        )
        is not None
    }


def get_lti_staff_project_ids(db: Session, user, memberships=None) -> set:
    """Other users' private exams the caller opens as LMS-linked org staff.

    The bulk form of the private-exam rule in the per-project deciders
    (creator excluded, soft-deleted excluded, archived included). Empty for
    users without an active staff membership or group-admin role, which
    costs at most two reads. ``memberships`` may pass the already loaded
    ``organization_memberships``.
    """
    if memberships is None:
        loaded = get_user_with_memberships(db, str(user.id))
        memberships = loaded.organization_memberships if loaded is not None else ()
    memberships = [m for m in memberships or () if m.is_active]
    if not memberships:
        return set()
    user_groups = get_user_group_context(db, str(user.id))
    staff_org_ids, admin_group_ids = _lti_staff_reach(memberships, user_groups)
    if not staff_org_ids and not admin_group_ids:
        return set()
    rows = db.execute(
        _build_select_lti_staff_candidates(user.id, staff_org_ids, admin_group_ids)
    ).all()
    if not rows:
        return set()
    protected_org_ids = _lti_protected_org_ids(db, {str(r[1]) for r in rows})
    return _pick_lti_staff_projects(rows, memberships, user_groups, protected_org_ids)


async def get_lti_staff_project_ids_async(
    db: AsyncSession, user, memberships=None
) -> set:
    """Async twin of :func:`get_lti_staff_project_ids`."""
    if memberships is None:
        loaded = await get_user_with_memberships_async(db, str(user.id))
        memberships = loaded.organization_memberships if loaded is not None else ()
    memberships = [m for m in memberships or () if m.is_active]
    if not memberships:
        return set()
    user_groups = await get_user_group_context_async(db, str(user.id))
    staff_org_ids, admin_group_ids = _lti_staff_reach(memberships, user_groups)
    if not staff_org_ids and not admin_group_ids:
        return set()
    rows = (
        await db.execute(
            _build_select_lti_staff_candidates(user.id, staff_org_ids, admin_group_ids)
        )
    ).all()
    if not rows:
        return set()
    protected_org_ids = await _lti_protected_org_ids_async(
        db, {str(r[1]) for r in rows}
    )
    return _pick_lti_staff_projects(rows, memberships, user_groups, protected_org_ids)


async def get_accessible_project_ids_async(
    db: AsyncSession,
    user,
    org_context: Optional[str] = None,
    include_all_private: bool = False,
) -> Optional[List[str]]:
    """Async equivalent of :func:`get_accessible_project_ids`."""
    if user.is_superadmin:
        if include_all_private:
            return None
        rows = (
            await db.execute(
                select(Project.id).where(
                    or_(
                        Project.is_private == False,  # noqa: E712
                        Project.created_by == str(user.id),
                    ),
                    not_deleted(),
                )
            )
        ).all()
        return _dedup_preserve_order([r.id for r in rows])

    public_rows = (
        await db.execute(
            select(Project.id).where(Project.is_public == True, not_deleted())  # noqa: E712
        )
    ).all()
    public_ids = [r.id for r in public_rows]

    # Lockstep with the sync helper: every membership counts.
    own_rows = (
        await db.execute(
            select(Project.id).where(
                Project.is_private == True,  # noqa: E712
                Project.created_by == str(user.id),
                not_deleted(),
            )
        )
    ).all()
    own_private = [r.id for r in own_rows]
    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    memberships = [m for m in _memberships_of(user_with_memberships) if m.is_active]
    lti_staff_ids = await get_lti_staff_project_ids_async(
        db, user, memberships=memberships
    )
    org_arm: List[str] = []
    if memberships:
        active = {str(m.organization_id): m for m in memberships}
        rows = (await db.execute(_build_select_member_org_list_rows(active))).all()
        if rows:
            user_groups = await get_user_group_context_async(db, str(user.id))
            protected = await _lti_protected_org_ids_async(
                db, _protected_candidate_orgs(rows, user.id)
            )
            org_arm = _pick_member_org_projects(
                rows, active, user.id, user_groups, lti_staff_ids, protected
            )
    return _dedup_preserve_order(
        own_private + sorted(lti_staff_ids) + org_arm, public_ids
    )


def get_org_context_from_request(request: Request) -> Optional[str]:
    """Extract organization context from request.

    Checks request.state (set by OrgContextMiddleware) first,
    falls back to X-Organization-Context header.
    """
    if hasattr(request, "state") and hasattr(request.state, "organization_context"):
        return request.state.organization_context
    return request.headers.get("X-Organization-Context")


def _org_grants_full_tier(
    project, membership, attachment_group_id=None, user_groups=None
) -> bool:
    """Whether an org membership confers the FULL project tier on ``project``.

    ANNOTATOR org members never get the full tier on exam-kind projects —
    for an exam, full tier means raw ``task.data`` (the Musterlösung),
    exports, settings, and other students' attempts. Student-members reach
    org-shared exams through the narrow participant tier instead
    (``get_student_read_access``). Non-exam projects and staff roles are
    unaffected, and a group admin of the attachment's group is staff on
    that group's projects regardless of org role (see shared/org_groups).
    """
    return grants_full_tier(
        getattr(project, "kind", None),
        membership.role,
        attachment_group_id,
        user_groups,
    )


def _decide_private_project(
    user,
    project,
    user_with_memberships,
    lti_attachments,
    user_groups,
    protected_org_ids=None,
) -> bool:
    """Shared private-project rule of both pure deciders (no DB).

    The creator, plus eligible staff of an org the exam is LMS-linked to
    (``org_groups.lti_staff_role``), whatever org context the client sent.
    ``lti_attachments`` omitted (None) keeps the creator-only rule;
    ``protected_org_ids`` are the linked orgs whose connections stay
    superadmin-run (only their admins count).
    """
    if str(user.id) == str(project.created_by):
        return True
    memberships = (
        user_with_memberships.organization_memberships
        if user_with_memberships is not None
        else None
    )
    return (
        lti_staff_role(
            getattr(project, "kind", None),
            memberships,
            lti_attachments,
            user_groups,
            protected_org_ids=protected_org_ids,
        )
        is not None
    )


def _lti_protected_org_ids(db: Session, lti_attachments) -> set:
    """Sync: the linked orgs whose connections stay superadmin-run.

    Fails closed (``extensions.lti_protected_org_subset``): a broken hook
    counts every linked org as protected.
    """
    if not lti_attachments:
        return set()
    import extensions

    return extensions.lti_protected_org_subset(db, list(lti_attachments))


async def _lti_protected_org_ids_async(db: AsyncSession, lti_attachments) -> set:
    """Async twin of :func:`_lti_protected_org_ids` (the hooks are sync)."""
    if not lti_attachments:
        return set()
    import extensions

    org_ids = list(lti_attachments)
    return await db.run_sync(
        lambda sync_db: extensions.lti_protected_org_subset(sync_db, org_ids)
    )


def _memberships_of(user_with_memberships):
    """The loaded memberships (only iterated when a rule needs them)."""
    if user_with_memberships is None:
        return ()
    return getattr(user_with_memberships, "organization_memberships", None) or ()


def _needs_protected_lti_filter(user, project) -> bool:
    """Whether ``project`` is someone else's non-private exam, where the LMS
    attachments of protected orgs count only for their admins
    (``org_groups.drop_protected_lti_attachments``). Strict string and bool
    checks keep the mock-based unit tests on the generic path."""
    return (
        project is not None
        and getattr(project, "kind", None) == "exam"
        and getattr(project, "is_private", False) is not True
        and not getattr(user, "is_superadmin", False)
        and str(getattr(project, "created_by", "")) != str(getattr(user, "id", user))
    )


def _drop_protected_lti_rows(
    db: Session, user, project, attachment_groups, memberships, user_groups
):
    """Sync: ``attachment_groups`` as they count for ``user`` on ``project``
    (the protected-org rule on non-private exams; fails closed)."""
    if not attachment_groups or not _needs_protected_lti_filter(user, project):
        return attachment_groups
    lti_orgs = get_lti_row_org_ids(db, str(project.id)) & set(attachment_groups)
    protected = _lti_protected_org_ids(db, lti_orgs)
    if not protected:
        return attachment_groups
    return drop_protected_lti_attachments(
        attachment_groups, protected, memberships, user_groups
    )


async def _drop_protected_lti_rows_async(
    db: AsyncSession, user, project, attachment_groups, memberships, user_groups
):
    """Async twin of :func:`_drop_protected_lti_rows`."""
    if not attachment_groups or not _needs_protected_lti_filter(user, project):
        return attachment_groups
    lti_orgs = await get_lti_row_org_ids_async(db, str(project.id))
    lti_orgs &= set(attachment_groups)
    protected = await _lti_protected_org_ids_async(db, lti_orgs)
    if not protected:
        return attachment_groups
    return drop_protected_lti_attachments(
        attachment_groups, protected, memberships, user_groups
    )


def _decide_project_accessible(
    user,
    project,
    project_org_ids,
    user_with_memberships,
    *,
    attachment_groups=None,
    user_groups=None,
    lti_attachments=None,
    protected_org_ids=None,
) -> bool:
    """The full-tier decision (pure; no DB), whatever the client's context.

    The creator always passes. Otherwise evaluated per attachment (not
    org-set intersection) so a group-scoped attachment only counts through
    an eligible membership; the first eligible membership that grants the
    full tier wins. ``attachment_groups``
    ({org_id: group_id|None}) and ``user_groups`` ({group_id: is_group_admin})
    carry the group axis; omitted (None) they fall back to "every attachment
    is org-wide". Private projects: the creator, plus LMS-linked staff when
    ``lti_attachments`` is given (``protected_org_ids``: linked orgs where
    only admins count).
    """
    if getattr(project, "is_private", False):
        return _decide_private_project(
            user,
            project,
            user_with_memberships,
            lti_attachments,
            user_groups,
            protected_org_ids,
        )

    # The creator keeps their project whatever context the client sends and
    # whether or not they still hold a membership in an attached org (the
    # role model resolves them to ORG_ADMIN and the edit check lets them
    # through; the old private-context branch granted the same).
    if str(user.id) == str(project.created_by):
        return True

    if not project_org_ids:
        return False

    if not user_with_memberships or not user_with_memberships.organization_memberships:
        return False

    project_org_id_set = set(project_org_ids)
    for m in user_with_memberships.organization_memberships:
        if m.organization_id not in project_org_id_set or not m.is_active:
            continue
        group_id = (attachment_groups or {}).get(m.organization_id)
        if not attachment_eligible(
            group_id,
            membership_role=m.role,
            user_groups=user_groups,
        ):
            continue
        if _org_grants_full_tier(project, m, group_id, user_groups):
            return True
    return False


def _private_exam_needs_lti_map(project, is_creator: bool) -> bool:
    """Whether the private-project decision needs the LMS attachment map:
    only someone else's private exam can be opened through one."""
    return (
        bool(getattr(project, "is_private", False))
        and not is_creator
        and getattr(project, "kind", None) == "exam"
    )


def check_project_accessible(
    db: Session,
    user,
    project_id: str,
    org_context: Optional[str] = None,
    project: Optional[Project] = None,
) -> bool:
    """Check if a user can access a specific project (sync).

    Args:
        db: Database session
        user: Current authenticated user
        project_id: Project to check access for
        org_context: Accepted for call-site symmetry and ignored: access is
            decided from every active membership, whatever organization the
            client has selected (the selected org used to be a read boundary
            and demoted staff of a started exam to the participant tier).
        project: Optional pre-loaded Project object to avoid redundant DB query.
    """
    if user.is_superadmin:
        return True

    if project is None:
        project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False

    if _is_deleted(project):
        # Soft-deleted: invisible to every non-superadmin (owner included).
        return False

    # Archived projects are read-only to annotators: an annotator who is
    # otherwise a member loses access once a project is archived. Higher roles
    # (and the creator/superadmin, who already short-circuit above / resolve to
    # ORG_ADMIN) keep access so they can view and unarchive.
    if getattr(project, "is_archived", False):
        if get_effective_project_role(db, user, project) == "ANNOTATOR":
            return False

    # Public projects are readable by every authenticated user regardless of context.
    if getattr(project, "is_public", False) is True:
        return True

    # Fast-path that needs no org/group reads: a private project resolves
    # on creatorship alone (the decider applies the same rule). A private
    # exam of someone else falls through: its LMS attachments may grant
    # staff.
    is_creator = str(user.id) == str(project.created_by)
    needs_lti = _private_exam_needs_lti_map(project, is_creator)
    if getattr(project, "is_private", False) and not needs_lti:
        return is_creator

    # Load, then delegate to the pure decider (same as the async lane) so the
    # sync/async semantics, including the group-eligibility axis, cannot
    # drift. The reads stay on the legacy ``db.query`` API for the
    # mock-based unit tests.
    lti_attachments = get_lti_attachment_map(db, project_id) if needs_lti else None
    if needs_lti and not lti_attachments:
        return False
    protected_org_ids = _lti_protected_org_ids(db, lti_attachments)
    attachment_groups = get_attachment_group_map(db, project_id)
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    user_groups = get_user_group_context(db, str(user.id))
    attachment_groups = _drop_protected_lti_rows(
        db,
        user,
        project,
        attachment_groups,
        _memberships_of(user_with_memberships),
        user_groups,
    )
    return _decide_project_accessible(
        user,
        project,
        list(attachment_groups.keys()),
        user_with_memberships,
        attachment_groups=attachment_groups,
        user_groups=user_groups,
        lti_attachments=lti_attachments,
        protected_org_ids=protected_org_ids,
    )


async def check_project_accessible_async(
    db: AsyncSession,
    user,
    project_id: str,
    org_context: Optional[str] = None,
    project: Optional[Project] = None,
) -> bool:
    """Async equivalent of :func:`check_project_accessible`."""
    if user.is_superadmin:
        return True

    if project is None:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
    if not project:
        return False

    if _is_deleted(project):
        # Soft-deleted: invisible to every non-superadmin (owner included).
        return False

    if getattr(project, "is_archived", False):
        if await get_effective_project_role_async(db, user, project) == "ANNOTATOR":
            return False

    if getattr(project, "is_public", False) is True:
        return True

    # The LMS attachment map is only an input for someone else's private
    # exam (lockstep with the sync lane, which skips every read otherwise).
    is_creator = str(user.id) == str(project.created_by)
    lti_attachments = None
    if _private_exam_needs_lti_map(project, is_creator):
        lti_attachments = await get_lti_attachment_map_async(db, project_id)
        if not lti_attachments:
            return False
    protected_org_ids = await _lti_protected_org_ids_async(db, lti_attachments)
    attachment_groups = await get_attachment_group_map_async(db, project_id)
    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    user_groups = await get_user_group_context_async(db, str(user.id))
    attachment_groups = await _drop_protected_lti_rows_async(
        db,
        user,
        project,
        attachment_groups,
        _memberships_of(user_with_memberships),
        user_groups,
    )
    return _decide_project_accessible(
        user,
        project,
        list(attachment_groups.keys()),
        user_with_memberships,
        attachment_groups=attachment_groups,
        user_groups=user_groups,
        lti_attachments=lti_attachments,
        protected_org_ids=protected_org_ids,
    )


async def get_share_access_async(
    db: AsyncSession, user, project_id: str
) -> Optional[ProjectShareMember]:
    """Return the user's consented share membership for a project, or None.

    This is the NARROW participant-access primitive for the student exam
    sharing feature (issue #35). It is deliberately NOT folded into
    ``check_project_accessible`` — that helper gates project exports, settings,
    and whole-``task.data`` reads, so granting a share invitee full project
    access there would let them export the Musterlösung and every other
    student's attempt. Instead, the extended attempt / own-review endpoints
    call this to grant ONLY participant-level access (attempt the task, read
    their own annotation + grade, see the cohort leaderboard).

    A pure platform-table read: a membership confers ongoing access while the
    row exists (owner eviction = deleting the row) and consent has been
    captured. Link ``expires_at`` / ``max_uses`` / ``revoked_at`` gate the JOIN
    action only — they do not retroactively evict an existing member — so they
    are intentionally not re-checked here.
    """
    result = await db.execute(
        select(ProjectShareMember).where(
            ProjectShareMember.project_id == project_id,
            ProjectShareMember.user_id == str(user.id),
            ProjectShareMember.gdpr_consent_at.isnot(None),
        )
    )
    # .first(), not scalar_one_or_none: one user can hold memberships via
    # SEVERAL links of the same project (rotated/re-minted links), and a
    # MultipleResultsFound here would 500 every participant surface.
    return result.scalars().first()


async def get_entitlement_access_async(
    db: AsyncSession, user, project_id: str
) -> Optional[MarketplaceEntitlement]:
    """Return the user's active marketplace entitlement for a project, or None.

    The vendor-marketplace twin of ``get_share_access_async``: a student who
    bought (``source='purchase'``) or was unlocked (``source='vendor_grant'``)
    a vendor exam/deck holds an entitlement row that confers the SAME narrow
    participant-level access a consented share member gets — never the full
    ``check_project_accessible`` tier (so the Musterlösung and other students'
    attempts stay gated identically). ``revoked_at`` (manual revocation /
    future refund handling) excludes the row. A pure platform-table read.
    """
    result = await db.execute(
        select(MarketplaceEntitlement).where(
            MarketplaceEntitlement.project_id == project_id,
            MarketplaceEntitlement.user_id == str(user.id),
            MarketplaceEntitlement.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_student_read_access_async(
    db: AsyncSession, user, project_id: str
) -> bool:
    """Whether a student has participant access (share, purchase, or org exam).

    The single gate the student exam/deck/SRS read endpoints should use: True
    if the user is a consented share member, holds an active marketplace
    entitlement, OR is an active member of an org that shares this exam
    org-wide (non-private, non-archived, windowless ``kind='exam'`` — the
    LTI/university ongoing-training catalog; a windowed exam counts once its
    window has started — never before). Short-circuits on the share check (the common
    #35 path). All three grant the identical narrow tier; callers that only
    need a yes/no should prefer this over calling the primitives.
    """
    if await get_share_access_async(db, user, project_id):
        return True
    if await get_entitlement_access_async(db, user, project_id) is not None:
        return True
    result = await db.execute(_build_select_org_exam_participant(user, project_id))
    return result.first() is not None


def _build_select_org_exam_participant(user, project_id: str):
    """Shared SQL builder: participant grant via org membership on an
    org-shared exam or flashcard collection.

    An ACTIVE membership (any role — CONTRIBUTOR+ callers pass
    ``check_project_accessible`` first and never reach this fallback) in an
    org attached to the project grants the narrow tier iff the project is a
    NON-private, non-archived exam or deck whose access window (if any) has
    STARTED. ``is_private=True`` projects
    deliberately stay entitlement/share/creator-only: blanket org membership
    is not per-project consent by anyone, and widening it would expose every
    student-created exam (all private) to the whole university org. Exams
    whose window has NOT YET OPENED are likewise excluded — pre-window entry
    stays explicit-channel-only (LTI launch, share, entitlement) so students
    cannot pre-read the Sachverhalt by browsing the org catalog. Once the
    window has started the grant holds (post-window too, so students keep
    their own review; the read-window enforcement governs the timeline).
    Decks (``flashcard_collection``, included 2026-08-26) have no windows —
    the clause passes on NULL. Without this arm, an org member studying an
    org deck under a mismatched org context (the vertretbar apex host sends
    ``X-Organization-Context: private``) had no fallback and got 403.
    """
    return (
        select(OrganizationMembership.id)
        .join(
            ProjectOrganization,
            ProjectOrganization.organization_id
            == OrganizationMembership.organization_id,
        )
        .join(Project, Project.id == ProjectOrganization.project_id)
        .where(
            ProjectOrganization.project_id == project_id,
            OrganizationMembership.user_id == str(user.id),
            OrganizationMembership.is_active == True,  # noqa: E712
            Project.kind.in_(("exam", "flashcard_collection")),
            Project.is_private == False,  # noqa: E712
            not_deleted(),
            or_(Project.is_archived.is_(None), Project.is_archived == False),  # noqa: E712
            or_(
                Project.window_start_at.is_(None),
                Project.window_start_at <= func.now(),
            ),
            # Group axis: a group-scoped attachment grants the participant
            # tier only to that group's members (org admins and the creator
            # keep it — the same eligibility rule as everywhere else).
            attachment_group_clause(
                ProjectOrganization,
                str(user.id),
                membership=OrganizationMembership,
                project=Project,
            ),
        )
    )


def get_student_read_access(db: Session, user, project_id: str) -> bool:
    """Sync twin of :func:`get_student_read_access_async`.

    Participant access via a consented ``ProjectShareMember``, an active
    ``MarketplaceEntitlement`` (vendor purchase / vendor grant / discovery
    enrollment), OR active org membership on an org-shared exam (non-private,
    non-archived, windowless — the university ongoing-training catalog). Used by the sync
    annotation-write path (``create_annotation``) so its submit gate AGREES
    with the read gate the extended student endpoints use: a consented share
    member of a private exam, an entitled/enrolled student, or a university
    org member may attempt the task even though ``check_project_accessible``
    denies them the full tier. Narrow participant tier only — it never widens
    export / settings / whole-``task.data`` access.
    """
    share = (
        db.query(ProjectShareMember)
        .filter(
            ProjectShareMember.project_id == project_id,
            ProjectShareMember.user_id == str(user.id),
            ProjectShareMember.gdpr_consent_at.isnot(None),
        )
        .first()
    )
    if share is not None:
        return True
    ent = (
        db.query(MarketplaceEntitlement)
        .filter(
            MarketplaceEntitlement.project_id == project_id,
            MarketplaceEntitlement.user_id == str(user.id),
            MarketplaceEntitlement.revoked_at.is_(None),
        )
        .first()
    )
    if ent is not None:
        return True
    return db.execute(_build_select_org_exam_participant(user, project_id)).first() is not None


def _build_select_org_admin_membership(user_id, project_org_ids):
    """Shared SQL builder: is `user` an active ORG_ADMIN of any of these orgs?"""
    return (
        select(OrganizationMembership.id)
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id.in_(project_org_ids),
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
    )


async def get_soft_deletable_project_ids_async(db: AsyncSession, user, projects) -> set:
    """Ids among the loaded ``projects`` the user may soft-delete (batched).

    The one place of the delete rule (``DELETE /projects/{id}``, bulk delete,
    and the delete controls of the student exam list and detail):
    superadmins delete everything. Only manual org attachments count: an LMS
    link (``attached_via='lti'``) opens an exam to the linking org's staff
    but never hands deletion to them, nor takes it from the creator, at any
    visibility. A private project is its creator's alone. Otherwise a
    project without manual org rows is the creator's, and a project with
    them needs an active ORG_ADMIN membership in one of those orgs (a mere
    CONTRIBUTOR creator cannot delete it out from under the org).
    """
    projects = [p for p in projects if p is not None]
    if getattr(user, "is_superadmin", False):
        return {p.id for p in projects}
    uid = str(user.id)
    allowed = set()
    shared = []
    for project in projects:
        if project.is_private:
            if str(project.created_by) == uid:
                allowed.add(project.id)
        else:
            shared.append(project)
    if not shared:
        return allowed
    orgs_by_project: Dict[str, set] = {}
    rows = await db.execute(
        select(
            ProjectOrganization.project_id,
            ProjectOrganization.organization_id,
            non_lti_attachment(ProjectOrganization),
        ).where(ProjectOrganization.project_id.in_([p.id for p in shared]))
    )
    for project_id, org_id, is_manual in rows.all():
        if is_manual:
            orgs_by_project.setdefault(str(project_id), set()).add(str(org_id))
    all_orgs = set().union(*orgs_by_project.values()) if orgs_by_project else set()
    admin_orgs = set()
    if all_orgs:
        admin_rows = await db.execute(
            select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == uid,
                OrganizationMembership.organization_id.in_(sorted(all_orgs)),
                OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
                OrganizationMembership.is_active == True,  # noqa: E712
            )
        )
        admin_orgs = {str(org_id) for org_id in admin_rows.scalars().all()}
    for project in shared:
        org_ids = orgs_by_project.get(str(project.id))
        if not org_ids:
            if str(project.created_by) == uid:
                allowed.add(project.id)
        elif org_ids & admin_orgs:
            allowed.add(project.id)
    return allowed


def check_user_can_edit_task_data(db: Session, user, project: Project) -> bool:
    """Whether a user may edit the `data` of a task within the given project.

    Allowed: superadmins, the project creator, and active ORG_ADMIN members of
    any organization the project belongs to. Mirrors the frontend notion of
    getEffectiveProjectRole(...) == 'ORG_ADMIN'. This governs *who* may edit;
    callers still verify project/task access separately.
    """
    if user.is_superadmin:
        return True
    if str(user.id) == str(project.created_by):
        return True

    project_org_ids = [
        r.organization_id
        for r in db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project.id)
        .all()
    ]
    if not project_org_ids:
        return False

    admin_membership = (
        db.query(OrganizationMembership.id)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id.in_(project_org_ids),
            OrganizationMembership.role == OrganizationRole.ORG_ADMIN,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        .first()
    )
    if admin_membership is not None:
        return True
    # Group admins hold ORG_ADMIN-equivalent powers on projects attached via
    # their group (the builder is inherently scoped to THIS project's
    # grouped attachments).
    return (
        db.execute(build_select_group_admin_on_attachments(user.id, project.id)).first()
        is not None
    )


async def check_user_can_edit_task_data_async(db: AsyncSession, user, project: Project) -> bool:
    """Async equivalent of :func:`check_user_can_edit_task_data`."""
    if user.is_superadmin:
        return True
    if str(user.id) == str(project.created_by):
        return True

    org_result = await db.execute(_build_select_project_org_ids(project.id))
    project_org_ids = list(org_result.scalars().all())
    if not project_org_ids:
        return False

    admin_result = await db.execute(
        _build_select_org_admin_membership(user.id, project_org_ids)
    )
    if admin_result.first() is not None:
        return True
    group_admin_result = await db.execute(
        build_select_group_admin_on_attachments(user.id, project.id)
    )
    return group_admin_result.first() is not None


def check_task_assigned_to_user(
    db: Session,
    user,
    task_id: str,
    project: Project,
) -> bool:
    """Check if a task is assigned to the user when in manual/auto assignment mode.

    Aligned with Label Studio Enterprise: unassigned tasks should be invisible
    to annotators (404), not forbidden (403). Callers decide the HTTP status.

    Returns True if:
    - Project assignment_mode is 'open' (no restrictions)
    - User is superadmin
    - User's org role is not ANNOTATOR (admins/contributors bypass)
    - User has an active assignment for this task

    Returns False only when an annotator tries to access an unassigned task
    in manual/auto mode.
    """
    if getattr(project, "assignment_mode", "open") == "open":
        return True

    if user.is_superadmin:
        return True

    # Resolve user role from org memberships
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    user_role = None
    if user_with_memberships and user_with_memberships.organization_memberships:
        project_org_ids = [
            r.organization_id
            for r in db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project.id)
            .all()
        ]
        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    # Non-annotator roles (admin, contributor) bypass assignment checks
    if user_role and user_role.upper() not in ["ANNOTATOR"]:
        return True

    # Check if user has any assignment for this task (including completed)
    # Completed assignments still grant read access so annotators can review their work
    assignment = (
        db.query(TaskAssignment)
        .filter(
            TaskAssignment.task_id == task_id,
            TaskAssignment.user_id == str(user.id),
            TaskAssignment.status.in_(["assigned", "in_progress", "completed"]),
        )
        .first()
    )
    if assignment is not None:
        return True
    # An own non-cancelled annotation counts as assigned: the submission stays
    # readable (attempted tier) even after the assignment row was removed.
    return user_attempted_task(db, user.id, task_id)


def _build_select_task_assignment(task_id, user_id):
    """Shared SQL builder: active/read-granting assignment of task to user."""
    return select(TaskAssignment).where(
        TaskAssignment.task_id == task_id,
        TaskAssignment.user_id == str(user_id),
        TaskAssignment.status.in_(["assigned", "in_progress", "completed"]),
    )


async def check_task_assigned_to_user_async(
    db: AsyncSession,
    user,
    task_id: str,
    project: Project,
) -> bool:
    """Async equivalent of :func:`check_task_assigned_to_user`."""
    if getattr(project, "assignment_mode", "open") == "open":
        return True

    if user.is_superadmin:
        return True

    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    user_role = None
    if user_with_memberships and user_with_memberships.organization_memberships:
        org_result = await db.execute(_build_select_project_org_ids(project.id))
        project_org_ids = list(org_result.scalars().all())
        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    if user_role and user_role.upper() not in ["ANNOTATOR"]:
        return True

    # .scalars().first() (NOT scalar_one_or_none): the (task_id, user_id) key is
    # only partially unique (WHERE target_type='task'); item-level Korrektur
    # assignments allow multiple rows per (task_id, user_id), so one_or_none
    # would raise MultipleResultsFound → 500. Matches the sync twin's .first().
    assignment_result = await db.execute(_build_select_task_assignment(task_id, user.id))
    if assignment_result.scalars().first() is not None:
        return True
    # Own non-cancelled annotation counts as assigned (matches the sync twin).
    return await user_attempted_task_async(db, user.id, task_id)


# Canonical definitions live in /shared (usable by workers + extended too);
# re-exported here because router code imports visibility helpers from this
# module.
from project_models import project_is_deleted as _is_deleted  # noqa: E402
from project_models import project_not_deleted as not_deleted  # noqa: E402


def _build_select_project_org_ids(project_id: str):
    """Shared SQL builder for the org ids a project is assigned to."""
    return select(ProjectOrganization.organization_id).where(
        ProjectOrganization.project_id == project_id
    )


_ROLE_RANK = {"ORG_ADMIN": 3, "CONTRIBUTOR": 2, "ANNOTATOR": 1}


def _role_rank(role) -> int:
    """Rank an OrganizationRole enum or bare string (str() on a str-enum
    yields 'OrganizationRole.X', so normalize via .value)."""
    return _ROLE_RANK.get(str(getattr(role, "value", role)).upper(), 0)


def _resolve_effective_role(
    user,
    project: Project,
    user_with_memberships,
    project_org_ids,
    *,
    attachment_groups=None,
    user_groups=None,
) -> Optional[str]:
    """Pure resolution logic shared by the sync/async role helpers.

    Takes already-loaded data (no DB access) so both lanes share identical
    semantics — only the reads (memberships + attachment group map + user
    group context) differ between sync and async. Group axis: a membership
    only counts through an ELIGIBLE attachment, and eligibility via a group
    the user group-admins upgrades that attachment's role to ORG_ADMIN. All
    memberships are considered and the best eligible role wins — first-match
    would be membership-order-dependent once ineligible attachments are
    skipped. Group inputs omitted (None) = every attachment org-wide
    (pre-groups behavior, kept for legacy callers).
    """
    best: Optional[str] = None
    if user_with_memberships and user_with_memberships.organization_memberships:
        is_creator = str(getattr(user, "id", user)) == str(project.created_by)
        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id not in project_org_ids or not membership.is_active:
                continue
            group_id = (attachment_groups or {}).get(membership.organization_id)
            if not attachment_eligible(
                group_id,
                is_creator=is_creator,
                membership_role=membership.role,
                user_groups=user_groups,
            ):
                continue
            role = (
                "ORG_ADMIN"
                if group_id is not None and (user_groups or {}).get(group_id, False)
                else membership.role
            )
            if best is None or _role_rank(role) > _role_rank(best):
                best = role
    if best is not None:
        return best

    if getattr(project, "is_public", False) is True and getattr(project, "public_role", None):
        return project.public_role

    return None


# Participants (consented share members, entitled/enrolled students, org
# members of a windowless org exam) hold the NARROW tier. For every existing
# ``role == "ANNOTATOR"`` branch (task-data blinding, write-role gates, the
# archived carve-out) they must behave exactly like an org annotator, so the
# effective-role resolvers fall back to this value when no membership/public
# claim exists but ``get_student_read_access`` holds.
PARTICIPANT_EFFECTIVE_ROLE = "ANNOTATOR"


def _private_project_role(
    project, user_with_memberships, lti_attachments, user_groups, protected
) -> Optional[str]:
    """Pure: the org role someone else holds on a PRIVATE project.

    Only a live, non-protected LMS link of an exam counts
    (:func:`_private_edit_role`); plain, stale or manual org rows give
    nothing, as in the access and edit checks.
    """
    if getattr(project, "kind", None) != "exam" or not lti_attachments:
        return None
    return _private_edit_role(
        user_with_memberships, lti_attachments, user_groups, protected
    )


def get_effective_project_role(
    db: Session,
    user,
    project: Project,
) -> Optional[str]:
    """Resolve the effective role a user holds within a project (sync).

    Returns one of: "ORG_ADMIN", "CONTRIBUTOR", "ANNOTATOR", or None.
    Resolution order:
      1. Superadmin or project creator → ORG_ADMIN.
      2. Someone else's private project: only the staff role a live LMS link
         grants (the private rule of the access and edit checks).
      3. Otherwise, active org membership in any org assigned to this
         project → that role (on someone else's exam, LMS attachments of
         protected orgs count only for their admins).
      4. Project is public and user has no other claim → project.public_role.
      5. A participant grant → ANNOTATOR. Otherwise → None.

    Sync body kept on the legacy ``db.query`` API to preserve the existing
    ``db.query``-mocking unit tests; the async twin lives below.
    """
    if user.is_superadmin or str(project.created_by) == str(user.id):
        return "ORG_ADMIN"

    user_with_memberships = get_user_with_memberships(db, str(user.id))
    if _is_private_row(project):
        user_groups = get_user_group_context(db, str(user.id))
        lti_attachments = (
            get_lti_attachment_map(db, str(project.id))
            if getattr(project, "kind", None) == "exam"
            else {}
        )
        role = _private_project_role(
            project,
            user_with_memberships,
            lti_attachments,
            user_groups,
            _lti_protected_org_ids(db, lti_attachments),
        )
    else:
        attachment_groups = get_attachment_group_map(db, str(project.id))
        user_groups = get_user_group_context(db, str(user.id))
        attachment_groups = _drop_protected_lti_rows(
            db,
            user,
            project,
            attachment_groups,
            _memberships_of(user_with_memberships),
            user_groups,
        )
        role = _resolve_effective_role(
            user,
            project,
            user_with_memberships,
            list(attachment_groups.keys()),
            attachment_groups=attachment_groups,
            user_groups=user_groups,
        )
    if role is None and get_student_read_access(db, user, str(project.id)):
        return PARTICIPANT_EFFECTIVE_ROLE
    return role


async def get_effective_project_role_async(
    db: AsyncSession,
    user,
    project: Project,
) -> Optional[str]:
    """Async equivalent of :func:`get_effective_project_role`."""
    if user.is_superadmin or str(project.created_by) == str(user.id):
        return "ORG_ADMIN"

    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    if _is_private_row(project):
        user_groups = await get_user_group_context_async(db, str(user.id))
        lti_attachments = (
            await get_lti_attachment_map_async(db, str(project.id))
            if getattr(project, "kind", None) == "exam"
            else {}
        )
        role = _private_project_role(
            project,
            user_with_memberships,
            lti_attachments,
            user_groups,
            await _lti_protected_org_ids_async(db, lti_attachments),
        )
    else:
        attachment_groups = await get_attachment_group_map_async(db, str(project.id))
        user_groups = await get_user_group_context_async(db, str(user.id))
        attachment_groups = await _drop_protected_lti_rows_async(
            db,
            user,
            project,
            attachment_groups,
            _memberships_of(user_with_memberships),
            user_groups,
        )
        role = _resolve_effective_role(
            user,
            project,
            user_with_memberships,
            list(attachment_groups.keys()),
            attachment_groups=attachment_groups,
            user_groups=user_groups,
        )
    if role is None and await get_student_read_access_async(db, user, str(project.id)):
        return PARTICIPANT_EFFECTIVE_ROLE
    return role



TIER_FULL = "full"
TIER_PARTICIPANT = "participant"
# "attempted": the user has a non-cancelled annotation on the project and
# keeps READ access to that submission (grades, corrections, whatever the
# project reveals after submit) even when nothing else grants access anymore
# — closed / not-yet-open window, archived, flipped private, membership
# deactivated, group moved, roster evicted, share link revoked, or the user
# left. Only the project's soft delete removes it. Never grants a write.
TIER_ATTEMPTED = "attempted"

# Tiers that may still WRITE (submit / edit / draft / skip). ``attempted`` is
# read-only by construction; ``None`` is no access.
WRITE_TIERS = (TIER_FULL, TIER_PARTICIPANT)


def tier_allows_writes(tier: Optional[str]) -> bool:
    """Whether a resolved access tier may mutate solver data on the project."""
    return tier in WRITE_TIERS


def require_write_tier(tier: Optional[str]) -> None:
    """Raise the write-gate 403 unless :func:`tier_allows_writes`.

    ``None`` keeps the plain ``"Access denied"`` detail every read gate
    raises; ``attempted`` raises a coded detail so the client can render the
    read-only state instead of a generic permission error.
    """
    if tier is None:
        raise HTTPException(status_code=403, detail="Access denied")
    if not tier_allows_writes(tier):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "attempted_read_only",
                "message": "Your submission on this project is read-only.",
            },
        )


def _build_select_user_attempted_project(user_id, project_id: str):
    """Shared SQL builder for the attempted predicate: EXISTS a non-cancelled
    annotation by the user on the project (served by the partial unique
    index ``uq_annotations_active_task_user``)."""
    return (
        select(Annotation.id)
        .where(
            Annotation.project_id == project_id,
            Annotation.completed_by == str(user_id),
            Annotation.was_cancelled == False,  # noqa: E712
        )
        .limit(1)
    )


def _build_select_user_attempted_task(user_id, task_id: str):
    """Task-level twin of :func:`_build_select_user_attempted_project`."""
    return (
        select(Annotation.id)
        .where(
            Annotation.task_id == task_id,
            Annotation.completed_by == str(user_id),
            Annotation.was_cancelled == False,  # noqa: E712
        )
        .limit(1)
    )


def own_active_annotation_exists(user_id):
    """Correlated EXISTS clause over ``Task``: the user has a non-cancelled
    annotation on that task. Used to scope task listings (my-tasks, the
    attempted tier's task list) to the caller's own submissions."""
    from sqlalchemy import exists as sa_exists

    return sa_exists().where(
        (Annotation.task_id == Task.id)
        & (Annotation.completed_by == str(user_id))
        & (Annotation.was_cancelled == False)  # noqa: E712
    )


async def user_attempted_project_async(db: AsyncSession, user_id, project_id: str) -> bool:
    """Attempted predicate: the user holds a non-cancelled annotation on the project."""
    result = await db.execute(_build_select_user_attempted_project(user_id, project_id))
    return result.first() is not None


def user_attempted_project(db: Session, user_id, project_id: str) -> bool:
    """Sync twin of :func:`user_attempted_project_async`."""
    return db.execute(_build_select_user_attempted_project(user_id, project_id)).first() is not None


async def user_attempted_task_async(db: AsyncSession, user_id, task_id: str) -> bool:
    """Whether the user holds a non-cancelled annotation on this task."""
    result = await db.execute(_build_select_user_attempted_task(user_id, task_id))
    return result.first() is not None


def user_attempted_task(db: Session, user_id, task_id: str) -> bool:
    """Sync twin of :func:`user_attempted_task_async`."""
    return db.execute(_build_select_user_attempted_task(user_id, task_id)).first() is not None


def _build_select_attempted_project_ids(user_id):
    """Shared SQL builder: every non-deleted project the user has a
    non-cancelled annotation on (the attempted set, before tier precedence)."""
    return (
        select(Annotation.project_id)
        .join(Project, Project.id == Annotation.project_id)
        .where(
            Annotation.completed_by == str(user_id),
            Annotation.was_cancelled == False,  # noqa: E712
            not_deleted(),
        )
        .distinct()
    )


async def get_attempted_project_ids_async(db: AsyncSession, user_id) -> set:
    """Ids of every non-deleted project the user has attempted.

    Deliberately NOT filtered by window / archive / privacy / membership —
    that is the point of the tier. Callers that stamp list rows combine it
    with the full and participant sets (both take precedence).
    """
    result = await db.execute(_build_select_attempted_project_ids(user_id))
    return {str(pid) for pid in result.scalars().all()}


def get_attempted_project_ids(db: Session, user_id) -> set:
    """Sync twin of :func:`get_attempted_project_ids_async`."""
    return {
        str(pid)
        for pid in db.execute(_build_select_attempted_project_ids(user_id)).scalars().all()
    }


async def get_project_access_tier_async(
    db: AsyncSession,
    user,
    project_id: str,
    org_context: Optional[str] = None,
    project: Optional[Project] = None,
) -> Optional[str]:
    """Resolve which access tier a user holds on a project.

    ``"full"`` is exactly today's :func:`check_project_accessible_async`
    (unchanged — exports, settings and whole-``task.data`` reads keep gating
    on it). ``"participant"`` is the narrow tier of
    :func:`get_student_read_access_async` (share member, entitlement, org
    exam) and is only honoured by the explicit allow-list of solver endpoints
    (task listing/next with blinding, own annotations, drafts, my-tasks,
    cohort leaderboard). Archived projects never grant the participant tier
    (mirrors the org-annotator archived carve-out). ``"attempted"`` is the
    read-only tier of :func:`user_attempted_project_async`: an own
    non-cancelled annotation keeps the submission readable whatever happened
    to the window / archive / privacy / membership / share / enrollment since
    — only the project's soft delete removes it. Precedence: full >
    participant > attempted. ``None`` = no access.
    """
    if project is None:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
    if not project:
        return None
    if _is_deleted(project) and not user.is_superadmin:
        return None
    if await check_project_accessible_async(db, user, project_id, org_context, project=project):
        return TIER_FULL
    if getattr(project, "is_archived", False):
        # Archived never grants the narrow tier — but an own submission keeps
        # its read access (attempted) through the archive.
        if await user_attempted_project_async(db, user.id, project_id):
            return TIER_ATTEMPTED
        return None
    if await get_student_read_access_async(db, user, project_id):
        return TIER_PARTICIPANT
    if await user_attempted_project_async(db, user.id, project_id):
        return TIER_ATTEMPTED
    return None


def get_project_access_tier(
    db: Session,
    user,
    project_id: str,
    org_context: Optional[str] = None,
    project: Optional[Project] = None,
) -> Optional[str]:
    """Sync twin of :func:`get_project_access_tier_async`."""
    if project is None:
        project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None
    if _is_deleted(project) and not user.is_superadmin:
        return None
    if check_project_accessible(db, user, project_id, org_context, project=project):
        return TIER_FULL
    if getattr(project, "is_archived", False):
        if user_attempted_project(db, user.id, project_id):
            return TIER_ATTEMPTED
        return None
    if get_student_read_access(db, user, project_id):
        return TIER_PARTICIPANT
    if user_attempted_project(db, user.id, project_id):
        return TIER_ATTEMPTED
    return None


def _build_select_project_attachment_kinds(project_id: str):
    """Shared SQL builder: the project's attachments as (org id, is manual)."""
    return select(
        ProjectOrganization.organization_id,
        non_lti_attachment(ProjectOrganization),
    ).where(ProjectOrganization.project_id == project_id)


def _share_manager_by_attachments(user, project, rows):
    """Pure first step of the share-management gates.

    ``rows`` are (org_id, is_manual) pairs. Returns ``(decided, org_ids)``:
    ``decided`` is True/False when the rows settle it, None when the org
    admin / group admin checks must run over ``org_ids``. Only a MANUAL org
    attachment takes share management away from the creator; linking the
    exam to an LMS activity (``attached_via='lti'``) does not.
    """
    org_ids = [str(org_id) for org_id, _ in rows]
    if not org_ids:
        return str(user.id) == str(project.created_by), org_ids
    if str(user.id) == str(project.created_by) and not any(
        manual for _, manual in rows
    ):
        return True, org_ids
    return None, org_ids


async def check_user_can_manage_shares_async(db: AsyncSession, user, project: Project) -> bool:
    """Whether a user may create / update / revoke share links on a project.

    Org projects (≥1 manual ``ProjectOrganization`` row): only active
    ORG_ADMIN members of one of the project's orgs — deliberately NO creator
    fast-path, so a CONTRIBUTOR who created an org project cannot let outside
    people in on their own. Personal projects (no org rows, or only rows
    created by LMS linking): the creator. The attached orgs' ORG_ADMINs and
    the attachments' group admins also manage an LMS-linked exam.
    Superadmins always. Viewing links / the roster / evicting stays on the
    edit tier.
    """
    if user.is_superadmin:
        return True
    rows = (
        await db.execute(_build_select_project_attachment_kinds(project.id))
    ).all()
    decided, project_org_ids = _share_manager_by_attachments(user, project, rows)
    if decided is not None:
        return decided
    admin_result = await db.execute(
        _build_select_org_admin_membership(user.id, project_org_ids)
    )
    if admin_result.first() is not None:
        return True
    # Group admins manage share links of their group's projects (chair staff
    # must run their own exams without holding org-wide admin).
    group_admin_result = await db.execute(
        build_select_group_admin_on_attachments(user.id, project.id)
    )
    return group_admin_result.first() is not None


def check_user_can_manage_shares(db: Session, user, project: Project) -> bool:
    """Sync twin of :func:`check_user_can_manage_shares_async`."""
    if user.is_superadmin:
        return True
    rows = db.execute(_build_select_project_attachment_kinds(project.id)).all()
    decided, project_org_ids = _share_manager_by_attachments(user, project, rows)
    if decided is not None:
        return decided
    if (
        db.execute(_build_select_org_admin_membership(user.id, project_org_ids)).first()
        is not None
    ):
        return True
    return (
        db.execute(build_select_group_admin_on_attachments(user.id, project.id)).first()
        is not None
    )


PARTICIPANT_VIA_SHARE = "share"
PARTICIPANT_VIA_ENTITLEMENT = "entitlement"
PARTICIPANT_VIA_ORG_EXAM = "org_exam"


async def get_participant_project_ids_async(
    db: AsyncSession, user_id: str
) -> Dict[str, str]:
    """Projects the user reaches ONLY through the participant tier.

    Returns ``{project_id: via}`` with ``via`` ∈ share / entitlement /
    org_exam (first match wins in that order). The three arms mirror the
    per-project predicates — consent filter of :func:`get_share_access_async`,
    revoked filter of :func:`get_entitlement_access_async`, and every
    condition of :func:`_build_select_org_exam_participant` — as batch
    queries; change those predicates and this tagging in lockstep. Archived projects and projects
    the user created are excluded — the creator already holds the full tier
    and archived projects never grant the narrow one. Used by the project
    list so joined/enrolled projects show up (tagged) next to the projects
    the user owns or reaches through an org.
    """
    uid = str(user_id)
    not_archived = or_(Project.is_archived.is_(None), Project.is_archived == False)  # noqa: E712
    alive = not_deleted()
    result: Dict[str, str] = {}

    share_rows = await db.execute(
        select(ProjectShareMember.project_id)
        .join(Project, Project.id == ProjectShareMember.project_id)
        .where(
            ProjectShareMember.user_id == uid,
            ProjectShareMember.gdpr_consent_at.isnot(None),
            Project.created_by != uid,
            not_archived,
            alive,
        )
    )
    for pid in share_rows.scalars().all():
        result.setdefault(str(pid), PARTICIPANT_VIA_SHARE)

    ent_rows = await db.execute(
        select(MarketplaceEntitlement.project_id)
        .join(Project, Project.id == MarketplaceEntitlement.project_id)
        .where(
            MarketplaceEntitlement.user_id == uid,
            MarketplaceEntitlement.revoked_at.is_(None),
            Project.created_by != uid,
            not_archived,
            alive,
        )
    )
    for pid in ent_rows.scalars().all():
        result.setdefault(str(pid), PARTICIPANT_VIA_ENTITLEMENT)

    org_rows = await db.execute(
        select(ProjectOrganization.project_id)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == ProjectOrganization.organization_id,
        )
        .join(Project, Project.id == ProjectOrganization.project_id)
        .where(
            OrganizationMembership.user_id == uid,
            OrganizationMembership.is_active == True,  # noqa: E712
            # Lockstep with _build_select_org_exam_participant (decks
            # included 2026-08-26, group clause 2026-08-31).
            Project.kind.in_(("exam", "flashcard_collection")),
            Project.is_private == False,  # noqa: E712
            Project.created_by != uid,
            not_archived,
            alive,
            or_(
                Project.window_start_at.is_(None),
                Project.window_start_at <= func.now(),
            ),
            attachment_group_clause(
                ProjectOrganization,
                uid,
                membership=OrganizationMembership,
                project=Project,
            ),
        )
    )
    for pid in org_rows.scalars().all():
        result.setdefault(str(pid), PARTICIPANT_VIA_ORG_EXAM)
    return result


def check_project_write_access(
    db: Session,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Check if a user can perform a write/contribute action on a project.

    Combines read access + role gate. The role check honours the public_role
    fallback for public-tier visitors:
      - public_role=ANNOTATOR  → blocked (only ORG_ADMIN/CONTRIBUTOR allowed)
      - public_role=CONTRIBUTOR → allowed
      - org-member with allowed role → allowed
      - creator + superadmin → always allowed (via get_effective_project_role)

    Use for endpoints that mutate task/annotation/generation data on a project
    (e.g. import, generate, bulk delete) where the documented public_role
    contract should be enforced.
    """
    if user.is_superadmin:
        return True

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or _is_deleted(project):
        return False

    role = get_effective_project_role(db, user, project)
    return role in allowed_roles


async def check_project_write_access_async(
    db: AsyncSession,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Async equivalent of :func:`check_project_write_access`."""
    if user.is_superadmin:
        return True

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project or _is_deleted(project):
        return False

    role = await get_effective_project_role_async(db, user, project)
    return role in allowed_roles


def check_user_can_edit_project(
    db: Session,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Check if a user can edit a project (creator, superadmin, or allowed org role).

    Used for project updates, bulk task operations, and other write actions.
    Does NOT check general project accessibility (public projects, archived
    annotators, org context) — call check_project_accessible first. It does
    apply the private-project rule itself (:func:`_private_edit_role`), so a
    caller that skips the access check cannot hand someone else's private
    project to a plain org member.
    """
    if user.is_superadmin:
        return True

    # Check if user is the project creator
    project = db.query(Project).filter(Project.id == project_id).first()
    if _is_deleted(project):
        # Soft-deleted (093): no edit rights for anyone but superadmins.
        return False
    if project and str(project.created_by) == str(user.id):
        return True

    if _is_private_row(project):
        if getattr(project, "kind", None) != "exam":
            return False
        lti_attachments = get_lti_attachment_map(db, project_id)
        if not lti_attachments:
            return False
        user_with_memberships = get_user_with_memberships(db, str(user.id))
        return (
            _private_edit_role(
                user_with_memberships,
                lti_attachments,
                get_user_group_context(db, str(user.id)),
                _lti_protected_org_ids(db, lti_attachments),
            )
            in allowed_roles
        )

    # Check org role — a membership only counts through an ELIGIBLE
    # attachment (group axis), and eligibility via a group the user
    # group-admins upgrades that attachment's role to ORG_ADMIN.
    user_with_memberships = get_user_with_memberships(db, str(user.id))
    if user_with_memberships and user_with_memberships.organization_memberships:
        attachment_groups = get_attachment_group_map(db, project_id)
        user_groups = get_user_group_context(db, str(user.id))
        # On someone else's exam, protected orgs' LMS rows count only for
        # their admins (same rule as the private branch above).
        attachment_groups = _drop_protected_lti_rows(
            db,
            user,
            project,
            attachment_groups,
            user_with_memberships.organization_memberships,
            user_groups,
        )
        return _membership_grants_edit(
            user_with_memberships.organization_memberships,
            attachment_groups,
            user_groups,
            allowed_roles,
        )

    return False


def _is_private_row(project) -> bool:
    """Whether a loaded project row is private. Strict ``is True`` so the
    mock-based unit tests (whose ``Mock`` rows answer every attribute with a
    truthy ``Mock``) keep the generic path."""
    return project is not None and getattr(project, "is_private", False) is True


def _private_edit_role(user_with_memberships, lti_attachments, user_groups, protected):
    """Pure: the edit role on someone else's private exam (or None).

    Plain org memberships never count on a private project. The only path is
    a live LMS link, with the same staff rule the access deciders apply
    (:func:`org_groups.lti_staff_role`: active, group-eligible CONTRIBUTOR or
    ORG_ADMIN, only admins for protected orgs). Stale or manual attachment
    rows grant nothing.
    """
    memberships = (
        user_with_memberships.organization_memberships
        if user_with_memberships is not None
        else None
    )
    return lti_staff_role(
        "exam",
        memberships,
        lti_attachments,
        user_groups,
        protected_org_ids=protected,
    )


def _membership_grants_edit(
    memberships, attachment_groups, user_groups, allowed_roles
) -> bool:
    """Pure edit-role loop shared by the sync/async edit-project gates."""
    for membership in memberships:
        if membership.organization_id not in attachment_groups or not membership.is_active:
            continue
        group_id = attachment_groups[membership.organization_id]
        if not attachment_eligible(
            group_id, membership_role=membership.role, user_groups=user_groups
        ):
            continue
        role = (
            "ORG_ADMIN"
            if group_id is not None and (user_groups or {}).get(group_id, False)
            else membership.role
        )
        if role in allowed_roles:
            return True
    return False


async def resolve_project_roles_batch_async(
    db: AsyncSession,
    user,
    projects,
    *,
    memberships=None,
    user_groups=None,
) -> Dict[str, "tuple[Optional[str], bool]"]:
    """``{project_id: (effective_role, can_edit)}`` for one list page.

    The per-row answers of :func:`get_effective_project_role_async` and
    :func:`check_user_can_edit_project_async`, computed from data loaded once
    for the page: the caller's memberships and group context, and one
    protected-org hook call over the LMS orgs of the page's foreign exams.
    Each project's ``project_organizations`` must be loaded (the list query
    eager-loads them), so the per-row work is pure. Only someone else's
    private exam (an LMS-staff row) reads its attachment map. A ``None``
    role on a participant row is the caller's business
    (``PARTICIPANT_EFFECTIVE_ROLE``).
    """
    from types import SimpleNamespace

    out: Dict[str, "tuple[Optional[str], bool]"] = {}
    if not projects:
        return out
    uid = str(user.id)
    if getattr(user, "is_superadmin", False):
        return {str(p.id): ("ORG_ADMIN", True) for p in projects}
    if memberships is None:
        loaded = await get_user_with_memberships_async(db, uid)
        memberships = list(_memberships_of(loaded))
    if user_groups is None:
        user_groups = await get_user_group_context_async(db, uid)
    holder = SimpleNamespace(organization_memberships=memberships)

    def _attachments(project):
        return list(getattr(project, "project_organizations", None) or [])

    lti_orgs = set()
    for p in projects:
        if _needs_protected_lti_filter(user, p):
            lti_orgs |= {
                str(po.organization_id)
                for po in _attachments(p)
                if getattr(po, "attached_via", None) == "lti"
            }
    protected = await _lti_protected_org_ids_async(db, lti_orgs)

    editor_roles = ("ORG_ADMIN", "CONTRIBUTOR")
    for p in projects:
        pid = str(p.id)
        if _is_deleted(p):
            out[pid] = (None, False)
            continue
        if str(p.created_by) == uid:
            out[pid] = ("ORG_ADMIN", True)
            continue
        if _is_private_row(p):
            role = None
            if getattr(p, "kind", None) == "exam":
                lti_attachments = await get_lti_attachment_map_async(db, pid)
                if lti_attachments:
                    role = _private_edit_role(
                        holder,
                        lti_attachments,
                        user_groups,
                        await _lti_protected_org_ids_async(db, lti_attachments),
                    )
            out[pid] = (role, role in editor_roles)
            continue
        attachment_groups = {
            str(po.organization_id): (str(po.group_id) if po.group_id else None)
            for po in _attachments(p)
        }
        if protected and _needs_protected_lti_filter(user, p):
            lti_here = {
                str(po.organization_id)
                for po in _attachments(p)
                if getattr(po, "attached_via", None) == "lti"
            } & protected
            if lti_here:
                attachment_groups = drop_protected_lti_attachments(
                    attachment_groups, lti_here, memberships, user_groups
                )
        role = _resolve_effective_role(
            user,
            p,
            holder,
            list(attachment_groups.keys()),
            attachment_groups=attachment_groups,
            user_groups=user_groups,
        )
        can_edit = _membership_grants_edit(
            memberships, attachment_groups, user_groups, editor_roles
        )
        out[pid] = (role, can_edit)
    return out


async def check_user_can_edit_project_async(
    db: AsyncSession,
    user,
    project_id: str,
    allowed_roles: tuple = ("ORG_ADMIN", "CONTRIBUTOR"),
) -> bool:
    """Async equivalent of :func:`check_user_can_edit_project`."""
    if user.is_superadmin:
        return True

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if _is_deleted(project):
        # Soft-deleted (093): no edit rights for anyone but superadmins.
        return False
    if project and str(project.created_by) == str(user.id):
        return True

    if _is_private_row(project):
        # Lockstep with the sync lane: a private project opens to others
        # only through a live LMS link.
        if getattr(project, "kind", None) != "exam":
            return False
        lti_attachments = await get_lti_attachment_map_async(db, project_id)
        if not lti_attachments:
            return False
        user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
        return (
            _private_edit_role(
                user_with_memberships,
                lti_attachments,
                await get_user_group_context_async(db, str(user.id)),
                await _lti_protected_org_ids_async(db, lti_attachments),
            )
            in allowed_roles
        )

    user_with_memberships = await get_user_with_memberships_async(db, str(user.id))
    if user_with_memberships and user_with_memberships.organization_memberships:
        attachment_groups = await get_attachment_group_map_async(db, project_id)
        user_groups = await get_user_group_context_async(db, str(user.id))
        attachment_groups = await _drop_protected_lti_rows_async(
            db,
            user,
            project,
            attachment_groups,
            user_with_memberships.organization_memberships,
            user_groups,
        )
        return _membership_grants_edit(
            user_with_memberships.organization_memberships,
            attachment_groups,
            user_groups,
            allowed_roles,
        )

    return False


# ── Timed access window (annotate / generate / evaluate) ─────────────────────
# The pure state predicates (project_window_state / project_reads_allowed /
# project_writes_allowed) live in /shared/project_window.py so the api AND the
# workers (auto-submit timer) agree. Here we add the api-side ENFORCEMENT
# wrappers: they apply the editor-exemption (anyone who can EDIT the project —
# superadmin / creator / ORG_ADMIN / CONTRIBUTOR — is exempt, so a teacher can
# set up before and review/re-grade after) and raise HTTPException. This
# generalizes the is_archived annotator read-only carve-out to a time window,
# adding a pre-open "listed-but-no-data" phase.


def _window_403(project, state: str) -> HTTPException:
    """Build the 403 raised when a non-editor hits a closed/pre-open window."""
    start = getattr(project, "window_start_at", None)
    end = getattr(project, "window_end_at", None)
    message = (
        "This project is not open yet."
        if state == "upcoming"
        else "This project is closed for changes."
    )
    return HTTPException(
        status_code=403,
        detail={
            "code": f"project_window_{state}",
            "message": message,
            "window_start_at": start.isoformat() if start is not None else None,
            "window_end_at": end.isoformat() if end is not None else None,
        },
    )


def enforce_project_read_window(
    db: Session, user, project, tier: Optional[str] = None
) -> None:
    """Sync: raise 403 if the pre-open window hides task data from a non-editor.

    No-op when there's no window, when the window is open/closed (reads stay
    allowed then — closed is "viewable but immutable"), or when the user can
    edit the project. Call at the DATA-serving read endpoints only — never the
    project LIST query, so pre-open projects stay listed.

    ``tier``: the caller's already-resolved access tier, if it has one. The
    attempted tier is never window-gated (its whole point is reading an own
    submission after the fact). When no tier is passed the predicate is
    re-checked here, so older call sites stay correct without threading it.
    """
    if project_reads_allowed(project):
        return
    if tier == TIER_ATTEMPTED:
        return
    if getattr(user, "is_superadmin", False) or check_user_can_edit_project(
        db, user, project.id
    ):
        return
    if tier is None and user_attempted_project(db, user.id, project.id):
        return
    raise _window_403(project, "upcoming")


async def enforce_project_read_window_async(
    db: AsyncSession, user, project, tier: Optional[str] = None
) -> None:
    """Async twin of :func:`enforce_project_read_window`."""
    if project_reads_allowed(project):
        return
    if tier == TIER_ATTEMPTED:
        return
    if getattr(user, "is_superadmin", False) or await check_user_can_edit_project_async(
        db, user, project.id
    ):
        return
    if tier is None and await user_attempted_project_async(db, user.id, project.id):
        return
    raise _window_403(project, "upcoming")


def enforce_project_write_window(db: Session, user, project) -> None:
    """Sync: raise 403 if the window (pre-open OR closed) forbids a non-editor's write.

    No-op when there's no window, when the window is open, or when the user can
    edit the project. Call at every annotate / generate / evaluate write
    choke-point (including the auto-submit workers).
    """
    if project_writes_allowed(project):
        return
    if getattr(user, "is_superadmin", False) or check_user_can_edit_project(
        db, user, project.id
    ):
        return
    raise _window_403(project, project_window_state(project))


async def enforce_project_write_window_async(db: AsyncSession, user, project) -> None:
    """Async twin of :func:`enforce_project_write_window`."""
    if project_writes_allowed(project):
        return
    if getattr(user, "is_superadmin", False) or await check_user_can_edit_project_async(
        db, user, project.id
    ):
        return
    raise _window_403(project, project_window_state(project))


# NOTE: the canonical project-access dependency is `require_project_access` in
# routers/projects/deps.py (returns a ProjectAccess container, supports
# min_role="edit"). An earlier, simpler view-only variant that lived here was
# removed — every router adopts the deps.py one.


def _format_project_organizations(project_orgs) -> List[Dict[str, Any]]:
    """Pure shaping shared by the sync/async org-list helpers."""
    return [
        {
            "id": po.organization.id,
            "name": po.organization.name,
        }
        for po in project_orgs
        if po.organization  # Filter out any with missing organization references
    ]


def get_project_organizations(db: Session, project_id: str) -> List[Dict[str, Any]]:
    """Get all organizations assigned to a project"""
    project_orgs = (
        db.query(ProjectOrganization)
        .options(joinedload(ProjectOrganization.organization))
        .filter(ProjectOrganization.project_id == project_id)
        .all()
    )

    return _format_project_organizations(project_orgs)


async def get_project_organizations_async(
    db: AsyncSession, project_id: str
) -> List[Dict[str, Any]]:
    """Async equivalent of :func:`get_project_organizations`."""
    result = await db.execute(
        select(ProjectOrganization)
        .options(joinedload(ProjectOrganization.organization))
        .where(ProjectOrganization.project_id == project_id)
    )
    return _format_project_organizations(result.scalars().unique().all())
