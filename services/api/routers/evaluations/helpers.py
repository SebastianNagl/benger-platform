"""
Shared helpers, models, and constants for evaluation sub-routers.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from models import EvaluationType as DBEvaluationType


# Celery app (shared across evaluation sub-routers)
from celery_client import get_celery_app  # noqa: E402


logger = logging.getLogger(__name__)
celery_app = get_celery_app()


# ============= Helper Functions =============


def resolve_user_org_for_project(user, project, db: Session) -> Optional[str]:
    """Find the org the current user belongs to among the project's orgs.

    When a project belongs to multiple orgs, we need to resolve which org
    context to use for API key resolution. Uses the user's membership.
    """
    if not project.organizations:
        return None

    from models import OrganizationMembership

    project_org_ids = {str(org.id) for org in project.organizations}

    memberships = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active == True,  # noqa: E712
            OrganizationMembership.organization_id.in_(project_org_ids),
        )
        .all()
    )

    if memberships:
        return str(memberships[0].organization_id)

    # Fallback for superadmins or edge cases
    return str(project.organizations[0].id)


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
