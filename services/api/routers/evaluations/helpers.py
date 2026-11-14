"""
Shared helpers, models, and constants for evaluation sub-routers.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel
from sqlalchemy import distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models import EvaluationType as DBEvaluationType
from models import TaskEvaluation


# Celery app (shared across evaluation sub-routers)
from celery_client import get_celery_app  # noqa: E402


logger = logging.getLogger(__name__)
celery_app = get_celery_app()


# ============= Helper Functions =============


async def run_cells_completed(db: AsyncSession, evaluation) -> int:
    """Cells (generations and answers) the run has graded: those graded
    before its latest dispatch plus the dispatched cells with a
    TaskEvaluation row written since. Rows an earlier attempt left on a
    re-dispatched cell (a failed judge call) do not count. A cell writes one
    row per field key and judge run, so ``samples_evaluated`` counts rows,
    not cells."""
    meta = evaluation.eval_metadata if isinstance(evaluation.eval_metadata, dict) else {}
    before = meta.get("cells_graded_before_dispatch", 0)
    if not isinstance(before, int) or isinstance(before, bool):
        before = 0
    query = select(
        func.count(distinct(TaskEvaluation.generation_id)),
        func.count(distinct(TaskEvaluation.annotation_id)),
    ).where(TaskEvaluation.evaluation_id == evaluation.id)
    dispatched_at = _parse_aware(meta.get("dispatched_at"))
    if dispatched_at is not None:
        query = query.where(TaskEvaluation.created_at >= dispatched_at)
    else:
        before = 0
    gens, anns = (await db.execute(query)).one()
    return before + int(gens or 0) + int(anns or 0)


def _parse_aware(value) -> Optional[datetime]:
    """A timezone-aware ISO timestamp, else None (absent or a legacy naive
    worker-local time that cannot be compared with ``created_at``)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def run_cells_total(evaluation) -> Optional[int]:
    """The run's cells: those its latest dispatch sent plus those it had
    graded before (a resume or retry dispatches only the cells left).
    None while nothing is dispatched yet."""
    meta = evaluation.eval_metadata if isinstance(evaluation.eval_metadata, dict) else {}
    counts = [meta.get("cells_dispatched"), meta.get("cells_graded_before_dispatch", 0)]
    if not all(isinstance(c, int) and not isinstance(c, bool) and c >= 0 for c in counts):
        return None
    total = sum(counts)
    return total if total > 0 else None


def run_progress(evaluation, cells_completed: int) -> Optional[float]:
    """Percent of the run's cells that are graded; None while unknown."""
    if evaluation.status == "completed":
        return 100.0
    total = run_cells_total(evaluation)
    if total is None:
        return None
    return round(min(100.0, 100.0 * cells_completed / total), 1)


def resolve_user_org_for_project(
    user, project, db: Session, *, min_role: Optional[str] = None
) -> Optional[str]:
    """Find the org the current user belongs to among the project's orgs.

    Thin delegate kept for its many importers — the shared implementation in
    ``org_resolution`` is the single source of truth (active membership wins;
    superadmins fall back to the project's first org; ordinary non-members
    resolve to ``None`` → personal key). ``min_role`` (for runs a caller
    starts: ``"CONTRIBUTOR"``) ignores memberships below that role.
    """
    from org_resolution import resolve_dispatch_org_for_project

    return resolve_dispatch_org_for_project(db, user, project, min_role=min_role)


def _build_select_evaluation_types_for_task_type(dialect_name: str, task_type: str):
    """Shared ``select`` builder for the dialect-aware task-type filter.

    PostgreSQL uses the jsonb ``?`` membership operator; SQLite falls back to
    a ``JSON_EXTRACT(...) LIKE`` scan. Both lanes (sync + async) execute the
    statement this returns so the SQL is identical between them.
    """
    if dialect_name == "postgresql":
        return select(DBEvaluationType).where(
            text("applicable_project_types::jsonb ? :task_type").params(
                task_type=task_type
            ),
            DBEvaluationType.is_active.is_(True),
        )
    return select(DBEvaluationType).where(
        text("JSON_EXTRACT(applicable_project_types, '$') LIKE :pattern").params(
            pattern=f'%"{task_type}"%'
        ),
        DBEvaluationType.is_active.is_(True),
    )


def _build_select_active_evaluation_types():
    """Fallback ``select`` for all active evaluation types (used when the
    dialect-specific JSON filter raises)."""
    return select(DBEvaluationType).where(DBEvaluationType.is_active.is_(True))


def get_evaluation_types_for_task_type(db: Session, task_type: str):
    """
    Get evaluation types that are applicable for a given task type.
    Database-agnostic function that works with both PostgreSQL and SQLite.
    """
    try:
        stmt = _build_select_evaluation_types_for_task_type(
            db.bind.dialect.name, task_type
        )
        return db.execute(stmt).scalars().all()
    except Exception as e:
        # Fallback: return all evaluation types if JSON query fails
        logger.warning(f"Failed to query evaluation types by task type: {e}")
        return db.execute(_build_select_active_evaluation_types()).scalars().all()


def extract_metric_name(metric_selection: Union[str, Dict[str, Any]]) -> str:
    """
    Extract metric name from metric selection.

    Supports two formats for metric selections:
    1. Simple string format: "bleu"
    2. Object format with parameters: {"name": "bleu", "parameters": {"max_order": 4}}

    This function enables the evaluation config system to accept both simple metric
    selections and advanced selections with custom parameters, as implemented in
    Issue #483 (comprehensive evaluation configuration system).

    Args:
        metric_selection: Metric in string or dict format

    Returns:
        Metric name as string, or empty string if format is invalid

    Example:
        >>> extract_metric_name("bleu")
        "bleu"
        >>> extract_metric_name({"name": "bleu", "parameters": {"max_order": 2}})
        "bleu"
        >>> extract_metric_name(None)
        ""
    """
    if isinstance(metric_selection, str):
        return metric_selection
    elif isinstance(metric_selection, dict):
        return metric_selection.get("name", "")
    return ""


# ============= Shared Response Models =============


class EvaluationStatus(BaseModel):
    """Model for evaluation status"""

    id: str
    status: str  # pending, running, completed, failed
    message: Optional[str] = None
    # Percent done (0-100): the run's graded cells over its cells (see
    # ``run_progress``); None before the run has dispatched its cells.
    progress: Optional[float] = None


class EvaluationResult(BaseModel):
    """Model for evaluation result"""

    model_config = {"protected_namespaces": ()}

    id: str
    project_id: str
    model_id: str
    metrics: dict
    created_at: datetime
    status: str = "completed"
    metadata: Optional[Dict[str, Any]] = None
    samples_evaluated: Optional[int] = None


class EvaluationTypeResponse(BaseModel):
    """Response model for evaluation types"""

    id: str
    name: str
    description: Optional[str] = None
    category: str
    higher_is_better: bool = True
    value_range: Optional[Dict[str, float]] = None
    applicable_project_types: List[str] = []
    is_active: bool = True


class EvaluationResultsResponse(BaseModel):
    """Response model for evaluation results"""

    project_id: str
    results: Dict[str, Any]
    metadata: Dict[str, Any]
    created_at: datetime
