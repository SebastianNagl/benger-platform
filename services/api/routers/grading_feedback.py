"""Read endpoints for solver feedback on gradings (``grading_feedback``).

Platform owns the table and these generic reads; the write path (participant
access policy, target validation, grade snapshot) is workflow logic and lives
in the benger_extended router (``PUT /api/student/exams/{project_id}/
grading-feedback``). See the GradingFeedback model docstring in
``services/shared/project_models.py``.

Three readers, three gates:

- ``GET /api/projects/{id}/grading-feedback/mine`` — the caller's own rows.
  Deliberately NO project-tier gate: share invitees / participant-tier
  students fail ``PROJECT_VIEW`` (the very reason the extended
  ``own-korrektur`` endpoint exists). Rows are self-owned, so a stranger just
  gets an empty list and nothing leaks.
- ``GET /api/projects/{id}/grading-feedback/summary`` — project editors
  (creator, org ADMIN/CONTRIBUTOR, superadmin). Anonymized: counts per source
  and rating plus the comments WITHOUT any user identity.
- ``GET /api/admin/grading-feedback/export`` — superadmin-only cross-project
  dump (CSV or JSON, user ids included) for the operators' analysis.
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import User, require_user
from auth_module.dependencies import require_superadmin
from database import get_async_db
from project_models import GradingFeedback, Project, Task, project_is_deleted
from routers.projects.helpers import check_user_can_edit_project_async

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/grading-feedback",
    tags=["grading-feedback"],
)
admin_router = APIRouter(
    prefix="/api/admin/grading-feedback",
    tags=["grading-feedback-admin"],
)

# "general" = free-text feedback about the exam/platform (no rating, no snapshot).
GRADING_SOURCES = ("llm", "human", "general")
SUMMARY_COMMENT_LIMIT = 500
EXPORT_DEFAULT_LIMIT = 10_000
EXPORT_MAX_LIMIT = 50_000
EXPORT_COLUMNS = [
    "id",
    "created_at",
    "updated_at",
    "project_id",
    "project_title",
    "project_kind",
    "task_id",
    "task_inner_id",
    "annotation_id",
    "user_id",
    "grading_source",
    "evaluation_run_id",
    "judge_model_id",
    "grade_points",
    "passed",
    "rating",
    "comment",
    "context",
]


class GradingFeedbackResponse(BaseModel):
    """Public shape of one feedback row (no user id, no raw context). The
    extended write endpoint returns the same shape."""

    id: str
    project_id: str
    task_id: str
    annotation_id: str
    grading_source: str
    evaluation_run_id: Optional[str] = None
    judge_model_id: Optional[str] = None
    grade_points: Optional[float] = None
    passed: Optional[bool] = None
    rating: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SourceTotals(BaseModel):
    up: int = 0
    down: int = 0
    comments: int = 0


class GradingFeedbackCommentRead(BaseModel):
    """One anonymized comment for the editor summary."""

    created_at: Optional[datetime] = None
    task_inner_id: Optional[int] = None
    grading_source: str
    rating: Optional[str] = None
    comment: str
    judge_model_id: Optional[str] = None
    grade_points: Optional[float] = None


class GradingFeedbackSummary(BaseModel):
    project_id: str
    total: int
    totals: Dict[str, SourceTotals]
    comments: List[GradingFeedbackCommentRead]


@router.get("/mine", response_model=List[GradingFeedbackResponse])
async def my_grading_feedback(
    project_id: str,
    annotation_id: Optional[str] = Query(None, description="Limit to one submission"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The caller's own feedback rows in this project (UI hydration).

    Self-owned rows only, so no project gate is needed: users without any
    feedback here (or without access to the project) get ``[]``.
    """
    stmt = select(GradingFeedback).where(
        GradingFeedback.project_id == project_id,
        GradingFeedback.user_id == str(current_user.id),
    )
    if annotation_id:
        stmt = stmt.where(GradingFeedback.annotation_id == annotation_id)
    stmt = stmt.order_by(GradingFeedback.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_editable_project(
    project_id: str, current_user: User, db: AsyncSession
) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project or (
        project_is_deleted(project) and not getattr(current_user, "is_superadmin", False)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    if not await check_user_can_edit_project_async(db, current_user, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this project's grading feedback",
        )
    return project


@router.get("/summary", response_model=GradingFeedbackSummary)
async def grading_feedback_summary(
    project_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Editor view: counts per source × rating and the comments, anonymized.

    No user ids leave this endpoint; the exam owner sees WHAT was said about
    the gradings, never WHO said it.
    """
    await _get_editable_project(project_id, current_user, db)

    counts = (
        await db.execute(
            select(
                GradingFeedback.grading_source,
                GradingFeedback.rating,
                func.count(GradingFeedback.id),
                func.count(GradingFeedback.comment),
            )
            .where(GradingFeedback.project_id == project_id)
            .group_by(GradingFeedback.grading_source, GradingFeedback.rating)
        )
    ).all()

    totals: Dict[str, SourceTotals] = {s: SourceTotals() for s in GRADING_SOURCES}
    total = 0
    for source, rating, n_rows, n_comments in counts:
        bucket = totals.setdefault(source, SourceTotals())
        total += int(n_rows)
        if rating == "up":
            bucket.up += int(n_rows)
        elif rating == "down":
            bucket.down += int(n_rows)
        bucket.comments += int(n_comments)

    comment_rows = (
        await db.execute(
            select(GradingFeedback, Task.inner_id)
            .join(Task, Task.id == GradingFeedback.task_id)
            .where(
                GradingFeedback.project_id == project_id,
                GradingFeedback.comment.isnot(None),
            )
            .order_by(GradingFeedback.created_at.desc())
            .limit(SUMMARY_COMMENT_LIMIT)
        )
    ).all()

    return GradingFeedbackSummary(
        project_id=project_id,
        total=total,
        totals=totals,
        comments=[
            GradingFeedbackCommentRead(
                created_at=fb.created_at,
                task_inner_id=inner_id,
                grading_source=fb.grading_source,
                rating=fb.rating,
                comment=fb.comment or "",
                judge_model_id=fb.judge_model_id,
                grade_points=fb.grade_points,
            )
            for fb, inner_id in comment_rows
        ],
    )


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _export_row(
    fb: GradingFeedback, project_title: Optional[str], project_kind: Optional[str],
    task_inner_id: Optional[int],
) -> Dict[str, Any]:
    return {
        "id": fb.id,
        "created_at": _iso(fb.created_at),
        "updated_at": _iso(fb.updated_at),
        "project_id": fb.project_id,
        "project_title": project_title,
        "project_kind": project_kind,
        "task_id": fb.task_id,
        "task_inner_id": task_inner_id,
        "annotation_id": fb.annotation_id,
        "user_id": fb.user_id,
        "grading_source": fb.grading_source,
        "evaluation_run_id": fb.evaluation_run_id,
        "judge_model_id": fb.judge_model_id,
        "grade_points": fb.grade_points,
        "passed": fb.passed,
        "rating": fb.rating,
        "comment": fb.comment,
        "context": fb.context,
    }


@admin_router.get("/export")
async def export_grading_feedback(
    format: Literal["csv", "json"] = Query("csv"),
    since: Optional[datetime] = Query(
        None, description="Only rows created at or after this timestamp"
    ),
    project_id: Optional[str] = Query(None, description="Limit to one project"),
    limit: int = Query(EXPORT_DEFAULT_LIMIT, ge=1, le=EXPORT_MAX_LIMIT),
    _superadmin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
):
    """Cross-project dump for the operators' analysis (superadmin only).

    Includes user ids and the raw ``context`` snapshot. Volume is one row per
    solver per grading, so a bounded in-memory response beats streaming;
    page with ``since`` + ``limit`` when the table grows.
    """
    stmt = (
        select(GradingFeedback, Project.title, Project.kind, Task.inner_id)
        .join(Project, Project.id == GradingFeedback.project_id)
        .join(Task, Task.id == GradingFeedback.task_id)
    )
    if since is not None:
        stmt = stmt.where(GradingFeedback.created_at >= since)
    if project_id:
        stmt = stmt.where(GradingFeedback.project_id == project_id)
    stmt = stmt.order_by(GradingFeedback.created_at).limit(limit)

    rows = [
        _export_row(fb, title, kind, inner_id)
        for fb, title, kind, inner_id in (await db.execute(stmt)).all()
    ]
    if format == "json":
        return rows

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                **row,
                "context": (
                    json.dumps(row["context"], ensure_ascii=False)
                    if row["context"] is not None
                    else ""
                ),
            }
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="grading_feedback_{stamp}.csv"'
        },
    )
