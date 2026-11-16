"""Superadmin list of Bewertungsbogen generation jobs.

``GET /api/admin/rubric-generation-jobs``: the rows of
``rubric_generation_jobs`` (written by the extended edition at dispatch, its
status poll, the Celery task wrapper and its beat sweep), newest first, with
the failure reason of each job and counts per status, error code and
generator model over the filtered set. The frontend host page is
``/admin/rubric-generation-jobs`` (slot ``RubricGenerationJobsAdmin``).

Read-only; the platform never writes these rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import User
from auth_module.dependencies import require_superadmin
from database import get_async_db
from models import Organization
from models import User as UserRow
from project_models import Project, RubricGenerationJob, Task
from rubric_generation_jobs import serialize_rubric_generation_job

router = APIRouter(
    prefix="/api/admin/rubric-generation-jobs", tags=["admin", "rubric-generation-jobs"]
)

MAX_LIMIT = 200

#: Columns the response counts the filtered set by.
_FACETS = {
    "status": RubricGenerationJob.status,
    "error_code": RubricGenerationJob.error_code,
    "generator_model_id": RubricGenerationJob.generator_model_id,
}


@router.get("")
async def list_rubric_generation_jobs(
    status: Optional[str] = Query(None, description="queued | running | completed | failed | lost"),
    entry_point: Optional[str] = Query(None, description="wizard | bulk | task | proposal"),
    error_code: Optional[str] = None,
    generator_model_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    since: Optional[datetime] = Query(None, description="Dispatched at or after (ISO 8601)"),
    until: Optional[datetime] = Query(None, description="Dispatched before (ISO 8601)"),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    _admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Generation jobs matching every given filter, ``created_at DESC, id DESC``.

    ``total`` and ``facets`` (plain counts per value of ``status``,
    ``error_code`` and ``generator_model_id``; NULL values are left out)
    cover the whole filtered set, ignoring ``limit`` and ``offset``.
    """
    conditions = []
    for column, value in (
        (RubricGenerationJob.status, status),
        (RubricGenerationJob.entry_point, entry_point),
        (RubricGenerationJob.error_code, error_code),
        (RubricGenerationJob.generator_model_id, generator_model_id),
        (RubricGenerationJob.organization_id, organization_id),
        (RubricGenerationJob.project_id, project_id),
        (RubricGenerationJob.user_id, user_id),
    ):
        if value is not None:
            conditions.append(column == value)
    if since is not None:
        conditions.append(RubricGenerationJob.created_at >= since)
    if until is not None:
        conditions.append(RubricGenerationJob.created_at < until)

    total = (
        await db.execute(select(func.count()).select_from(RubricGenerationJob).where(*conditions))
    ).scalar_one()

    facets: Dict[str, Dict[str, int]] = {}
    for name, column in _FACETS.items():
        rows = await db.execute(
            select(column, func.count())
            .where(*conditions, column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc(), column)
        )
        facets[name] = {value: count for value, count in rows.all()}

    rows = await db.execute(
        select(
            RubricGenerationJob,
            Project.title,
            Task.inner_id,
            UserRow.email,
            Organization.name,
        )
        .outerjoin(Project, Project.id == RubricGenerationJob.project_id)
        .outerjoin(Task, Task.id == RubricGenerationJob.task_id)
        .outerjoin(UserRow, UserRow.id == RubricGenerationJob.user_id)
        .outerjoin(Organization, Organization.id == RubricGenerationJob.organization_id)
        .where(*conditions)
        .order_by(RubricGenerationJob.created_at.desc(), RubricGenerationJob.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        serialize_rubric_generation_job(
            job,
            project_title=project_title,
            task_inner_id=task_inner_id,
            # Superadmins see who started a job by their account email, as
            # in the other admin lists.
            user_label=user_email,
            organization_name=organization_name,
        )
        for job, project_title, task_inner_id, user_email, organization_name in rows.all()
    ]
    return {"total": total, "items": items, "facets": facets}
