"""Precomputed aggregate summaries — write (from Celery) and read (from API).

This module owns the SQL behind two summary tables introduced in migration
051:

* `llm_leaderboard_scores` — feeds /api/leaderboards/llm-models{,/{id},/compare}
* `project_summaries`      — feeds /api/dashboard/stats and per-project tiles

The recompute_* functions are called by the Celery task
`recompute_aggregates` (hourly beat — tightened from 12h on 2026-05-20).
They scan task_evaluations once per refresh cycle in the worker (12 GiB
pod) and UPSERT into the summary tables. The read_* helpers turn API
requests into single indexed lookups so the API pod never has to
materialise the heavy data into Python.

For unusual filter combinations that no precomputed scope covers (e.g.
multi-project explicit project_ids list, or evaluation_type filter), use
`live_*` helpers — they run the same SQL the worker uses but with a tighter
filter and bounded row count, so they stay safe in the API hot path.

Lives in `/shared` so both the API and the worker can import it as a
top-level module. The previous location (`services/api/services/`) was
unreachable from the worker image and `recompute_aggregates` silently
failed with `ModuleNotFoundError("No module named 'services'")` on every
beat — the projects-list / dashboard tiles read an empty
`project_summaries` table and fell back to the live query path forever.
Moved 2026-05-20.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import cast, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    Generation,
    LLMLeaderboardScore,
    ProjectSummary,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import Annotation, Project, Task

logger = logging.getLogger(__name__)

PERIODS: Tuple[str, ...] = ("overall", "monthly", "weekly")
SCOPES: Tuple[str, ...] = ("all", "public")

# Single source of truth for the noise filter lives in /shared so this
# module is importable by both the API and the worker. Routers re-export
# the name for backwards compatibility with existing call sites.
from metric_filters import _metric_key_is_real  # noqa: E402


# --------------------------------------------------------------------------- #
# Shared utilities                                                            #
# --------------------------------------------------------------------------- #

def _period_cutoff(period: str) -> Optional[datetime]:
    """Cutoff datetime for the period filter; None means no time filter."""
    now = datetime.now(timezone.utc)
    if period == "monthly":
        return now - timedelta(days=30)
    if period == "weekly":
        return now - timedelta(days=7)
    return None


def _coerce_metric_value(val: Any) -> Optional[float]:
    """Local copy of the metric coercion logic.

    Mirrors routers.evaluations.results._coerce_metric_value but kept here
    to avoid an API router import from worker code paths (workers don't
    always have the API routers package fully wired). Behaviour must stay
    in lockstep with the original.
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    if isinstance(val, dict):
        for key in ("value", "total_score", "score"):
            sub = val.get(key)
            coerced = _coerce_metric_value(sub)
            if coerced is not None:
                return coerced
    return None


def _confidence_interval(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """95% CI of the mean via t-distribution.

    Returns (None, None) when fewer than 2 samples or scipy is unavailable.
    """
    if len(values) < 2:
        return None, None
    try:
        import numpy as np
        from scipy import stats
    except ImportError:
        return None, None
    arr = np.array(values, dtype=float)
    mean = float(arr.mean())
    sem = stats.sem(arr)
    if sem == 0 or not np.isfinite(sem):
        return mean, mean
    half = float(sem * stats.t.ppf(0.975, len(arr) - 1))
    return mean - half, mean + half


# --------------------------------------------------------------------------- #
# Project summaries                                                           #
# --------------------------------------------------------------------------- #

def recompute_project_summaries(db: Session) -> int:
    """Refresh every (project, period) row in `project_summaries`.

    Returns the number of rows UPSERTed.
    """
    project_ids = [row[0] for row in db.execute(select(Project.id)).all()]
    now = datetime.now(timezone.utc)
    upserts = 0
    for pid in project_ids:
        for period in PERIODS:
            row = _compute_project_summary(db, pid, period, _period_cutoff(period), now)
            _upsert_project_summary(db, row)
            upserts += 1
    db.commit()
    return upserts


def _compute_project_summary(
    db: Session,
    project_id: str,
    period: str,
    cutoff: Optional[datetime],
    computed_at: datetime,
) -> Dict[str, Any]:
    total_tasks = db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id)
    ).scalar() or 0

    labeled_tasks = db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id, Task.is_labeled == True  # noqa: E712
        )
    ).scalar() or 0

    ann_stmt = select(func.count(Annotation.id)).where(
        Annotation.project_id == project_id,
        Annotation.was_cancelled == False,  # noqa: E712
        func.jsonb_array_length(Annotation.result) > 0,
    )
    if cutoff is not None:
        ann_stmt = ann_stmt.where(Annotation.created_at >= cutoff)
    annotations_count = db.execute(ann_stmt).scalar() or 0

    gen_stmt = (
        select(func.count(Generation.id))
        .join(Task, Generation.task_id == Task.id)
        .where(
            Task.project_id == project_id,
            Generation.parse_status == "success",
        )
    )
    if cutoff is not None:
        gen_stmt = gen_stmt.where(Generation.created_at >= cutoff)
    generations_count = db.execute(gen_stmt).scalar() or 0

    rg_stmt = select(func.count(ResponseGeneration.id)).where(
        ResponseGeneration.project_id == project_id
    )
    if cutoff is not None:
        rg_stmt = rg_stmt.where(ResponseGeneration.created_at >= cutoff)
    response_generations_count = db.execute(rg_stmt).scalar() or 0

    # Status='completed' subset — feeds the projects-list progress bar in
    # `apply_generation_stats`. Kept separate from the total so callers that
    # care about activity (any state) still have an accurate denominator.
    rg_completed_stmt = select(func.count(ResponseGeneration.id)).where(
        ResponseGeneration.project_id == project_id,
        ResponseGeneration.status == "completed",
    )
    if cutoff is not None:
        rg_completed_stmt = rg_completed_stmt.where(
            ResponseGeneration.created_at >= cutoff
        )
    completed_response_generations_count = (
        db.execute(rg_completed_stmt).scalar() or 0
    )

    evaluation_pairs_count = _count_eval_pairs(db, project_id, cutoff)

    # available_models is config-ish — not subject to a period filter.
    available_models = sorted(
        {
            row[0]
            for row in db.execute(
                select(Generation.model_id)
                .join(Task, Generation.task_id == Task.id)
                .where(
                    Task.project_id == project_id,
                    Generation.parse_status == "success",
                )
                .distinct()
            ).all()
            if row[0]
        }
    )

    return {
        "project_id": project_id,
        "period": period,
        "total_tasks": int(total_tasks),
        "labeled_tasks": int(labeled_tasks),
        "annotations_count": int(annotations_count),
        "generations_count": int(generations_count),
        "response_generations_count": int(response_generations_count),
        "completed_response_generations_count": int(
            completed_response_generations_count
        ),
        "evaluation_pairs_count": int(evaluation_pairs_count),
        "available_models": available_models,
        "computed_at": computed_at,
    }


def _count_eval_pairs(db: Session, project_id: str, cutoff: Optional[datetime]) -> int:
    """Count DISTINCT (subject, real-metric) pairs scored in completed runs.

    Mirrors routers.projects.helpers._scored_pairs_query semantics but
    project-scoped and time-filtered. The Python loop applies the
    `_metric_key_is_real` noise filter — same source of truth as the live
    path.
    """
    subject_expr = func.coalesce(
        TaskEvaluation.annotation_id, TaskEvaluation.generation_id
    )
    metrics_jsonb = cast(TaskEvaluation.metrics, JSONB)
    stmt = (
        select(
            subject_expr.label("subject_id"),
            func.jsonb_object_keys(metrics_jsonb).label("metric_key"),
        )
        .select_from(TaskEvaluation)
        .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
        .where(
            EvaluationRun.project_id == project_id,
            EvaluationRun.status == "completed",
            subject_expr.isnot(None),
            TaskEvaluation.metrics.isnot(None),
            func.jsonb_typeof(metrics_jsonb) == "object",
        )
        .distinct()
    )
    if cutoff is not None:
        stmt = stmt.where(EvaluationRun.created_at >= cutoff)
    return sum(
        1 for _sub, mk in db.execute(stmt).all() if _metric_key_is_real(mk)
    )


def _upsert_project_summary(db: Session, row: Dict[str, Any]) -> None:
    values = dict(row)
    values["id"] = str(uuid.uuid4())
    set_ = {k: values[k] for k in row.keys() if k not in ("project_id", "period")}
    stmt = (
        pg_insert(ProjectSummary.__table__)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_ps_scope",
            set_=set_,
        )
    )
    db.execute(stmt)


# --------------------------------------------------------------------------- #
# LLM leaderboard scores                                                      #
# --------------------------------------------------------------------------- #

def recompute_llm_leaderboard_scores(db: Session) -> int:
    """Refresh every (model, scope, period, metric) row in `llm_leaderboard_scores`.

    Returns the number of rows UPSERTed.
    """
    now = datetime.now(timezone.utc)
    upserts = 0
    for scope in SCOPES:
        for period in PERIODS:
            run_ids = _eval_run_ids_for_scope(db, scope, _period_cutoff(period))
            if not run_ids:
                continue
            rows = _aggregate_leaderboard_rows(db, run_ids, scope, period, now)
            for row in rows:
                _upsert_leaderboard_score(db, row)
                upserts += 1
    db.commit()
    return upserts


def _eval_run_ids_for_scope(
    db: Session, scope: str, cutoff: Optional[datetime]
) -> List[str]:
    stmt = select(EvaluationRun.id).where(EvaluationRun.status == "completed")
    if scope == "public":
        stmt = stmt.join(Project, EvaluationRun.project_id == Project.id).where(
            Project.is_public.is_(True)
        )
    # 'all' = every completed EvaluationRun
    if cutoff is not None:
        stmt = stmt.where(EvaluationRun.created_at >= cutoff)
    return [row[0] for row in db.execute(stmt).all()]


def _aggregate_leaderboard_rows(
    db: Session,
    run_ids: List[str],
    scope: str,
    period: str,
    computed_at: datetime,
) -> List[Dict[str, Any]]:
    """Build the per-(model, metric) rows for one (scope, period).

    Streams (model_id, metric_key, metric_val_json) triples from
    task_evaluations and buckets them in Python, then computes mean + CI
    per bucket. 60k input rows → ~3 MB Python memory; runs once per cycle
    in the worker.
    """
    if not run_ids:
        return []

    # Per-(model, metric) raw values for mean + CI.
    metrics_jsonb = cast(TaskEvaluation.metrics, JSONB)
    pairs_stmt = (
        select(
            Generation.model_id.label("model_id"),
            func.jsonb_each(metrics_jsonb).label("kv"),
        )
        .join(Generation, TaskEvaluation.generation_id == Generation.id)
        .join(EvaluationRun, TaskEvaluation.evaluation_id == EvaluationRun.id)
        .where(
            TaskEvaluation.evaluation_id.in_(run_ids),
            TaskEvaluation.generation_id.isnot(None),
            TaskEvaluation.metrics.isnot(None),
            func.jsonb_typeof(metrics_jsonb) == "object",
        )
    )

    # jsonb_each returns a record type; using text() for clarity.
    #
    # The UNION ALL branch synthesises a `llm_judge_falloesung_grade_points`
    # triple per row from `metrics.llm_judge_falloesung.details.grade_points`.
    # The worker stores grade points inside `details` (next to raw_score), so
    # jsonb_each above only ever sees the parent `llm_judge_falloesung`
    # (0–1 normalised score). The frontend leaderboard defaults to the
    # grade_points metric — without this lift the column is always n/a even
    # though the per-row value exists.
    raw_sql = text(
        """
        SELECT
            g.model_id,
            kv.key   AS metric_key,
            kv.value AS metric_val
        FROM task_evaluations te
        JOIN generations g ON g.id = te.generation_id
        JOIN evaluation_runs er ON er.id = te.evaluation_id
        CROSS JOIN LATERAL jsonb_each(te.metrics::jsonb) AS kv
        WHERE te.evaluation_id = ANY(:run_ids)
          AND te.generation_id IS NOT NULL
          AND te.metrics IS NOT NULL
          AND jsonb_typeof(te.metrics::jsonb) = 'object'

        UNION ALL

        SELECT
            g.model_id,
            'llm_judge_falloesung_grade_points' AS metric_key,
            te.metrics::jsonb->'llm_judge_falloesung'->'details'->'grade_points' AS metric_val
        FROM task_evaluations te
        JOIN generations g ON g.id = te.generation_id
        JOIN evaluation_runs er ON er.id = te.evaluation_id
        WHERE te.evaluation_id = ANY(:run_ids)
          AND te.generation_id IS NOT NULL
          AND te.metrics IS NOT NULL
          AND jsonb_typeof(te.metrics::jsonb) = 'object'
          AND te.metrics::jsonb ? 'llm_judge_falloesung'
          AND te.metrics::jsonb->'llm_judge_falloesung'->'details' ? 'grade_points'
          AND jsonb_typeof(te.metrics::jsonb->'llm_judge_falloesung'->'details'->'grade_points') = 'number'
        """
    ).bindparams(run_ids=run_ids)

    # (model_id, metric_key) -> list[float]
    buckets: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for model_id, metric_key, metric_val in db.execute(
        raw_sql.execution_options(stream_results=True)
    ).yield_per(5000):
        if not model_id or not _metric_key_is_real(metric_key):
            continue
        coerced = _coerce_metric_value(metric_val)
        if coerced is None:
            continue
        buckets[(model_id, metric_key)].append(coerced)

    # Per-model rollups for evaluation_count / generation_count / last_at.
    rollup_sql = text(
        """
        SELECT
            g.model_id                  AS model_id,
            COUNT(DISTINCT te.evaluation_id)  AS evaluation_count,
            COUNT(DISTINCT g.id)        AS generation_count,
            COALESCE(COUNT(te.id), 0)   AS samples_evaluated,
            MAX(er.completed_at)        AS last_evaluated_at
        FROM task_evaluations te
        JOIN generations g ON g.id = te.generation_id
        JOIN evaluation_runs er ON er.id = te.evaluation_id
        WHERE te.evaluation_id = ANY(:run_ids)
          AND te.generation_id IS NOT NULL
        GROUP BY g.model_id
        """
    ).bindparams(run_ids=run_ids)
    per_model_meta = {
        row.model_id: {
            "evaluation_count": int(row.evaluation_count or 0),
            "generation_count": int(row.generation_count or 0),
            "samples_evaluated": int(row.samples_evaluated or 0),
            "last_evaluated_at": row.last_evaluated_at,
        }
        for row in db.execute(rollup_sql).all()
    }

    rows: List[Dict[str, Any]] = []
    # Per-metric rows.
    for (model_id, metric_key), values in buckets.items():
        meta = per_model_meta.get(model_id, {})
        ci_lower, ci_upper = _confidence_interval(values)
        rows.append(
            {
                "model_id": model_id,
                "project_scope_key": scope,
                "period": period,
                "metric": metric_key,
                "score": round(sum(values) / len(values), 4) if values else None,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "samples_evaluated": meta.get("samples_evaluated", 0),
                "evaluation_count": meta.get("evaluation_count", 0),
                "generation_count": meta.get("generation_count", 0),
                "last_evaluated_at": meta.get("last_evaluated_at"),
                "computed_at": computed_at,
            }
        )

    # Per-model 'average' row — the cross-metric mean used for default ranking.
    by_model: Dict[str, List[float]] = defaultdict(list)
    for (model_id, _metric_key), values in buckets.items():
        by_model[model_id].extend(values)
    for model_id, values in by_model.items():
        meta = per_model_meta.get(model_id, {})
        ci_lower, ci_upper = _confidence_interval(values)
        rows.append(
            {
                "model_id": model_id,
                "project_scope_key": scope,
                "period": period,
                "metric": "average",
                "score": round(sum(values) / len(values), 4) if values else None,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "samples_evaluated": meta.get("samples_evaluated", 0),
                "evaluation_count": meta.get("evaluation_count", 0),
                "generation_count": meta.get("generation_count", 0),
                "last_evaluated_at": meta.get("last_evaluated_at"),
                "computed_at": computed_at,
            }
        )

    return rows


def _upsert_leaderboard_score(db: Session, row: Dict[str, Any]) -> None:
    values = dict(row)
    values["id"] = str(uuid.uuid4())
    set_ = {
        k: values[k]
        for k in row.keys()
        if k not in ("model_id", "project_scope_key", "period", "metric")
    }
    stmt = (
        pg_insert(LLMLeaderboardScore.__table__)
        .values(**values)
        .on_conflict_do_update(constraint="uq_lls_scope", set_=set_)
    )
    db.execute(stmt)


# --------------------------------------------------------------------------- #
# Read helpers (API path)                                                     #
# --------------------------------------------------------------------------- #

def read_dashboard_sum(
    db: Session,
    accessible_project_ids: Optional[List[str]],
    period: str = "overall",
) -> Dict[str, int]:
    """Sum ProjectSummary rows across accessible projects for a period.

    `accessible_project_ids=None` means "superadmin / unscoped" — sum all.
    `accessible_project_ids=[]`   means "no access" — all zeros.
    """
    zeros = {
        "project_count": 0,
        "total_tasks": 0,
        "labeled_tasks": 0,
        "annotations_count": 0,
        "generations_count": 0,
        "response_generations_count": 0,
        "completed_response_generations_count": 0,
        "evaluation_pairs_count": 0,
    }
    if accessible_project_ids == []:
        return zeros

    stmt = select(
        func.count(ProjectSummary.id).label("project_count"),
        func.coalesce(func.sum(ProjectSummary.total_tasks), 0).label("total_tasks"),
        func.coalesce(func.sum(ProjectSummary.labeled_tasks), 0).label("labeled_tasks"),
        func.coalesce(func.sum(ProjectSummary.annotations_count), 0).label(
            "annotations_count"
        ),
        func.coalesce(func.sum(ProjectSummary.generations_count), 0).label(
            "generations_count"
        ),
        func.coalesce(func.sum(ProjectSummary.response_generations_count), 0).label(
            "response_generations_count"
        ),
        func.coalesce(
            func.sum(ProjectSummary.completed_response_generations_count), 0
        ).label("completed_response_generations_count"),
        func.coalesce(func.sum(ProjectSummary.evaluation_pairs_count), 0).label(
            "evaluation_pairs_count"
        ),
    ).where(ProjectSummary.period == period)
    if accessible_project_ids is not None:
        stmt = stmt.where(ProjectSummary.project_id.in_(accessible_project_ids))
    row = db.execute(stmt).one()
    return {
        "project_count": int(row.project_count or 0),
        "total_tasks": int(row.total_tasks or 0),
        "labeled_tasks": int(row.labeled_tasks or 0),
        "annotations_count": int(row.annotations_count or 0),
        "generations_count": int(row.generations_count or 0),
        "response_generations_count": int(row.response_generations_count or 0),
        "completed_response_generations_count": int(
            row.completed_response_generations_count or 0
        ),
        "evaluation_pairs_count": int(row.evaluation_pairs_count or 0),
    }


def read_project_summary(
    db: Session, project_id: str, period: str = "overall"
) -> Optional[ProjectSummary]:
    return db.execute(
        select(ProjectSummary).where(
            ProjectSummary.project_id == project_id,
            ProjectSummary.period == period,
        )
    ).scalar_one_or_none()


def read_llm_leaderboard(
    db: Session,
    project_scope_key: str,
    period: str,
    sort_metric: str,
    limit: int,
    offset: int,
) -> Tuple[List[Dict[str, Any]], int, List[str], Optional[datetime]]:
    """Read precomputed leaderboard rows for a single (scope, period).

    Returns (entries, total_models, available_metrics, computed_at) where:
    - entries: pivoted list of {model_id, score, ci_*, samples_*, ..., metrics: {...}}
    - total_models: COUNT(DISTINCT model_id) over the scope (before LIMIT)
    - available_metrics: sorted distinct metric keys (excluding 'average')
    - computed_at: max computed_at across the scope (UI staleness hint)
    """
    # Step 1: top-N model_ids by `sort_metric` score.
    base = select(LLMLeaderboardScore).where(
        LLMLeaderboardScore.project_scope_key == project_scope_key,
        LLMLeaderboardScore.period == period,
    )

    total_models = db.execute(
        select(func.count(func.distinct(LLMLeaderboardScore.model_id))).where(
            LLMLeaderboardScore.project_scope_key == project_scope_key,
            LLMLeaderboardScore.period == period,
        )
    ).scalar() or 0

    available_metrics = sorted(
        m
        for (m,) in db.execute(
            select(LLMLeaderboardScore.metric)
            .where(
                LLMLeaderboardScore.project_scope_key == project_scope_key,
                LLMLeaderboardScore.period == period,
            )
            .distinct()
        ).all()
        if m and m != "average"
    )

    top_stmt = (
        base.where(LLMLeaderboardScore.metric == sort_metric)
        .order_by(
            LLMLeaderboardScore.score.is_(None).asc(),  # nulls last
            LLMLeaderboardScore.score.desc(),
            LLMLeaderboardScore.model_id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    top_rows = db.execute(top_stmt).scalars().all()

    if not top_rows:
        # If the requested sort_metric has no rows for this scope/period,
        # bail with empty leaderboard rather than re-querying — the caller
        # can fall back to a different metric if needed.
        return [], int(total_models), available_metrics, None

    model_ids = [r.model_id for r in top_rows]

    # Step 2: pull all metric rows for those model_ids in one shot.
    detail_stmt = base.where(LLMLeaderboardScore.model_id.in_(model_ids))
    detail_rows = db.execute(detail_stmt).scalars().all()

    by_model: Dict[str, Dict[str, Any]] = {}
    for r in detail_rows:
        entry = by_model.setdefault(
            r.model_id,
            {
                "model_id": r.model_id,
                "metrics": {},
                # populated from the sort-metric row below
                "score": None,
                "ci_lower": None,
                "ci_upper": None,
                "samples_evaluated": 0,
                "evaluation_count": 0,
                "generation_count": 0,
                "last_evaluated_at": None,
            },
        )
        if r.metric == "average":
            # The 'average' row carries the per-model rollup counters we
            # already store on every row, but keep it canonical here for
            # the `metrics={...}` dict the API returns to the frontend.
            entry["metrics"]["average"] = r.score
        else:
            entry["metrics"][r.metric] = r.score

        if r.metric == sort_metric:
            entry["score"] = r.score
            entry["ci_lower"] = r.ci_lower
            entry["ci_upper"] = r.ci_upper
            entry["samples_evaluated"] = r.samples_evaluated
            entry["evaluation_count"] = r.evaluation_count
            entry["generation_count"] = r.generation_count
            entry["last_evaluated_at"] = r.last_evaluated_at

    # Preserve top-N order.
    ordered = [by_model[mid] for mid in model_ids if mid in by_model]
    computed_at = max((r.computed_at for r in detail_rows if r.computed_at), default=None)
    return ordered, int(total_models), available_metrics, computed_at


def read_llm_model_aggregate(
    db: Session, model_id: str, project_scope_key: str, period: str
) -> Dict[str, Any]:
    """Read one model's row set for /llm-models/{model_id}. Returns a dict with
    `metrics` (dict, by metric → {mean, ci_lower, ci_upper, count}),
    plus evaluation_count, samples_evaluated, generation_count, last_evaluated_at.
    """
    rows = db.execute(
        select(LLMLeaderboardScore).where(
            LLMLeaderboardScore.model_id == model_id,
            LLMLeaderboardScore.project_scope_key == project_scope_key,
            LLMLeaderboardScore.period == period,
        )
    ).scalars().all()

    out: Dict[str, Any] = {
        "metrics": {},
        "evaluation_count": 0,
        "samples_evaluated": 0,
        "generation_count": 0,
        "last_evaluated_at": None,
        "computed_at": None,
    }
    for r in rows:
        if r.metric != "average":
            out["metrics"][r.metric] = {
                "mean": r.score,
                "ci_lower": r.ci_lower,
                "ci_upper": r.ci_upper,
                "count": r.samples_evaluated,
            }
        # The per-model rollup is identical across rows; just take the max.
        out["evaluation_count"] = max(out["evaluation_count"], r.evaluation_count)
        out["samples_evaluated"] = max(out["samples_evaluated"], r.samples_evaluated)
        out["generation_count"] = max(out["generation_count"], r.generation_count)
        if r.last_evaluated_at and (
            out["last_evaluated_at"] is None
            or r.last_evaluated_at > out["last_evaluated_at"]
        ):
            out["last_evaluated_at"] = r.last_evaluated_at
        if r.computed_at and (
            out["computed_at"] is None or r.computed_at > out["computed_at"]
        ):
            out["computed_at"] = r.computed_at
    return out


def live_aggregate_leaderboard(
    db: Session,
    project_ids: Optional[List[str]],
    period: str,
    evaluation_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Live (uncached) aggregation for filter combos with no precomputed scope.

    Returns the same per-(model, metric) row shape the worker writes. The
    API uses this when project_ids/evaluation_types don't match any
    precomputed scope. It still streams task_evaluations via yield_per — no
    `.all()` materialisation — so it's safe in the API hot path for the
    rare uncached query.

    `project_ids=None` means "all projects" (no visibility filter applied
    here; callers must apply visibility themselves before calling).
    """
    stmt = select(EvaluationRun.id).where(EvaluationRun.status == "completed")
    if project_ids:
        stmt = stmt.where(EvaluationRun.project_id.in_(project_ids))
    cutoff = _period_cutoff(period)
    if cutoff is not None:
        stmt = stmt.where(EvaluationRun.created_at >= cutoff)
    if evaluation_types:
        # EvaluationRun.evaluation_type_ids is JSON; cast to JSONB on the
        # column side and pass the right-hand side as a typed bind parameter
        # via `literal(..., type_=JSONB)`. SQLAlchemy's JSONB type runs the
        # JSON encoder, so a value containing a `"` or backslash can't break
        # out of the literal — properly parameterised, no injection.
        from sqlalchemy import literal, or_

        col_jsonb = cast(EvaluationRun.evaluation_type_ids, JSONB)
        type_filters = [
            col_jsonb.contains(literal([et], type_=JSONB))
            for et in evaluation_types
        ]
        stmt = stmt.where(or_(*type_filters))

    run_ids = [row[0] for row in db.execute(stmt).all()]
    if not run_ids:
        return []
    now = datetime.now(timezone.utc)
    return _aggregate_leaderboard_rows(db, run_ids, scope="live", period=period, computed_at=now)


def scope_key_for_project_ids(project_ids: Optional[List[str]]) -> Optional[str]:
    """Map a request's project_ids filter onto a precomputed scope key.

    Returns:
      'all'         when project_ids is None/empty AND the caller wants every project
                    (the caller has to decide; we just provide the key)
      'public'      not auto-inferable from project_ids alone (caller decides)
      single id     when exactly one project_id is supplied
      None          when no precomputed scope matches — caller must use live SQL
    """
    if not project_ids:
        return None  # caller chooses 'all' or 'public'
    if len(project_ids) == 1:
        return project_ids[0]
    return None
