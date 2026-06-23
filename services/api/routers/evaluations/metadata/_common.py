"""
Evaluation metadata, statistics, and significance endpoints.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_async_db, get_db
from models import EvaluationRun as DBEvaluationRun
from project_models import Annotation, Project, Task
from routers.projects.helpers import (
    check_project_accessible,
    check_project_accessible_async,
    get_org_context_from_request,
)

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


# Explicit export surface. ``from ._common import *`` binds exactly these names,
# so the concern submodules (models_methods / history / significance / statistics)
# no longer need to repeat an explicit import block just to dodge F405 — this
# single list documents the full shared surface once. It is the FULL set of public
# names this module binds (every import above plus ``logger``/``router`` and the
# Pydantic models), so the star binding is unchanged.
__all__ = [
    # stdlib / typing
    "logging",
    "datetime",
    "Dict",
    "List",
    "Optional",
    # fastapi
    "APIRouter",
    "Depends",
    "HTTPException",
    "Query",
    "Request",
    "status",
    # pydantic
    "BaseModel",
    # sqlalchemy
    "func",
    "select",
    "AsyncSession",
    "Session",
    # auth_module
    "User",
    "require_user",
    # database
    "get_async_db",
    "get_db",
    # models / project_models
    "DBEvaluationRun",
    "Annotation",
    "Project",
    "Task",
    # routers.projects.helpers
    "check_project_accessible",
    "check_project_accessible_async",
    "get_org_context_from_request",
    # this module
    "logger",
    "router",
    # Pydantic models
    "StatisticsRequest",
    "MetricStatistics",
    "PairwiseComparison",
    "ModelStatistics",
    "FieldStatistics",
    "RawScore",
    "RunsAggregate",
    "TaskConsistency",
    "JudgeAgreement",
    "PerRunMean",
    "StatisticsResponse",
]
