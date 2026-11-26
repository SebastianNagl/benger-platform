"""Problem reports sent from inside the app ("Report a problem").

Behind the platform flag ``bug_reports`` (off by default): while it is off for
the caller every route answers 404 ``feature_disabled``.

- ``POST /api/bug-reports`` (multipart): anyone the flag is on for, signed in
  or not. Fields ``title``, ``description``, optional ``expected``, optional
  ``contact_email`` (only kept without a session), optional ``context`` (the
  technical context as JSON, reduced by ``bug_reports.clean_context``) and an
  optional ``screenshot`` (PNG, JPEG or WebP, checked by its bytes). Limited
  to ``USER_REPORTS_PER_HOUR`` per user and ``ANONYMOUS_REPORTS_PER_HOUR``
  per client address (429). The report is stored, the screenshot goes to
  object storage, and ``tasks.deliver_bug_report`` delivers it as an issue.
- Superadmins: ``GET /api/bug-reports`` (newest first, ``status`` filter),
  ``GET /api/bug-reports/{id}``, ``GET /api/bug-reports/{id}/screenshot``
  (the image, never a public link) and ``POST /api/bug-reports/{id}/redeliver``
  (queue the delivery again, for a failed report or one kept while no target
  was configured).

Access keys stay out (``app/core/key_routes``).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import bug_reports as reports
from auth_module.dependencies import optional_user, require_superadmin
from database import get_async_db
from feature_flags import service as flag_service
from feature_flags.deps import feature_disabled_error, require_feature_flag
from feature_flags.registry import BUG_REPORTS
from models import BugReport
from services.rate_limiter import get_client_ip, rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bug-reports", tags=["bug-reports"])

DELIVER_TASK = "tasks.deliver_bug_report"
RATE_LIMIT_ENDPOINT = "bug_report"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PAGE = 200

require_bug_reports = require_feature_flag(BUG_REPORTS)


class BugReportCreated(BaseModel):
    id: str
    status: str


class BugReportSummary(BaseModel):
    id: str
    created_at: datetime
    title: str
    status: str
    reporter_id: Optional[str] = None
    anonymous: bool
    page: Optional[str] = None
    has_screenshot: bool
    delivery_attempts: int
    delivery_error: Optional[str] = None
    issue_url: Optional[str] = None
    issue_number: Optional[int] = None
    delivered_at: Optional[datetime] = None


class BugReportDetail(BugReportSummary):
    description: str
    expected: Optional[str] = None
    contact_email: Optional[str] = None
    context: Dict[str, Any]
    screenshot_content_type: Optional[str] = None
    screenshot_size: Optional[int] = None


class BugReportPage(BaseModel):
    items: List[BugReportSummary]
    total: int


def _invalid(code: str, message: str, status_code: int = 422) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _summary_fields(row: BugReport) -> Dict[str, Any]:
    ctx = row.context or {}
    return {
        "id": row.id,
        "created_at": row.created_at,
        "title": row.title,
        "status": row.status,
        "reporter_id": row.reporter_id,
        "anonymous": row.reporter_id is None,
        "page": ctx.get("page"),
        "has_screenshot": bool(row.screenshot_key),
        "delivery_attempts": row.delivery_attempts or 0,
        "delivery_error": row.delivery_error,
        "issue_url": row.issue_url,
        "issue_number": row.issue_number,
        "delivered_at": row.delivered_at,
    }


def _detail(row: BugReport) -> BugReportDetail:
    return BugReportDetail(
        **_summary_fields(row),
        description=row.description,
        expected=row.expected,
        contact_email=row.contact_email,
        context=row.context or {},
        screenshot_content_type=row.screenshot_content_type,
        screenshot_size=row.screenshot_size,
    )


def _queue_delivery(report_id: str) -> None:
    """Send the delivery task; a broker error leaves the report pending for
    the sweep (``tasks.sweep_pending_bug_reports``)."""
    try:
        from celery_client import send_task_safe

        send_task_safe(DELIVER_TASK, args=[report_id])
    except Exception:
        logger.exception("bug report %s: delivery not queued, the sweep will retry", report_id)


def _required_text(value: Optional[str], code: str, limit: int) -> str:
    text = (value or "").replace("\x00", "").strip()
    if not text:
        raise _invalid(code, "This field is required.")
    if len(text) > limit:
        raise _invalid("too_long", f"At most {limit} characters.")
    return text


def _parse_context(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    if len(raw.encode("utf-8", "ignore")) > reports.MAX_CONTEXT_BYTES:
        raise _invalid("context_too_large", "The technical context is too large.", 413)
    try:
        value = json.loads(raw)
    except ValueError:
        raise _invalid("invalid_context", "The technical context is not valid JSON.")
    return reports.clean_context(value)


async def _read_screenshot(screenshot: Optional[UploadFile]):
    if screenshot is None:
        return None
    data = await screenshot.read(reports.MAX_SCREENSHOT_BYTES + 1)
    if not data:
        return None
    if len(data) > reports.MAX_SCREENSHOT_BYTES:
        raise _invalid("screenshot_too_large", "The screenshot is too large.", 413)
    content_type = reports.sniff_screenshot_type(data)
    if content_type is None:
        raise _invalid("screenshot_type", "The screenshot must be a PNG, JPEG or WebP image.", 415)
    return data, content_type


@router.post("", response_model=BugReportCreated, status_code=201)
async def create_bug_report(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    expected: Optional[str] = Form(None),
    contact_email: Optional[str] = Form(None),
    context: Optional[str] = Form(None),
    screenshot: Optional[UploadFile] = File(None),
    current_user=Depends(optional_user),
    db: AsyncSession = Depends(get_async_db),
) -> BugReportCreated:
    if not await flag_service.is_enabled_for(db, current_user, BUG_REPORTS):
        raise feature_disabled_error(BUG_REPORTS)

    clean_title = _required_text(title, "title_required", reports.MAX_TITLE_CHARS)
    clean_description = _required_text(
        description, "description_required", reports.MAX_DESCRIPTION_CHARS
    )
    clean_expected = (expected or "").replace("\x00", "").strip() or None
    if clean_expected and len(clean_expected) > reports.MAX_EXPECTED_CHARS:
        raise _invalid("too_long", f"At most {reports.MAX_EXPECTED_CHARS} characters.")
    email: Optional[str] = None
    if current_user is None and contact_email and contact_email.strip():
        email = contact_email.strip()
        if len(email) > reports.MAX_CONTACT_EMAIL_CHARS or not _EMAIL.match(email):
            raise _invalid("invalid_email", "The contact address is not a valid e-mail address.")
    ctx = _parse_context(context)
    shot = await _read_screenshot(screenshot)

    if current_user is not None:
        client_id = f"user:{current_user.id}"
        per_hour = reports.USER_REPORTS_PER_HOUR
    else:
        client_id = f"ip:{get_client_ip(request)}"
        per_hour = reports.ANONYMOUS_REPORTS_PER_HOUR
    limited = await rate_limiter.check_rolling_limit(client_id, RATE_LIMIT_ENDPOINT, per_hour, 3600)
    if limited:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": "Too many reports. Please try again later.",
                "retry_after": limited.get("retry_after"),
            },
            headers={"Retry-After": str(limited.get("retry_after", 3600))},
        )

    server = reports.server_context(
        user_agent=request.headers.get("user-agent"),
        is_superadmin=getattr(current_user, "is_superadmin", None) if current_user else None,
    )
    row = BugReport(
        reporter_id=current_user.id if current_user is not None else None,
        contact_email=email,
        title=clean_title,
        description=clean_description,
        expected=clean_expected,
        status=reports.STATUS_PENDING,
    )

    stored_key: Optional[str] = None
    if shot is not None:
        data, content_type = shot
        try:
            from object_storage import object_storage

            result = await asyncio.to_thread(
                object_storage.upload_file,
                data,
                f"screenshot.{reports.SCREENSHOT_TYPES[content_type]}",
                file_type="bug_reports",
                content_type=content_type,
            )
            stored_key = result["file_key"]
            row.screenshot_key = stored_key
            row.screenshot_content_type = content_type
            row.screenshot_size = len(data)
        except Exception:
            # The report matters more than its picture: keep it without.
            logger.exception("bug report screenshot could not be stored")
            server["screenshot_not_stored"] = True
    ctx["server"] = server
    row.context = ctx

    db.add(row)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if stored_key:
            from stored_files import delete_stored_files

            await asyncio.to_thread(
                delete_stored_files, [stored_key], what="bug report screenshot"
            )
        raise
    _queue_delivery(row.id)
    return BugReportCreated(id=row.id, status=row.status)


@router.get("", response_model=BugReportPage)
async def list_bug_reports(
    response: Response,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    _flag=Depends(require_bug_reports),
    _admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
) -> BugReportPage:
    response.headers["Cache-Control"] = "no-store"
    if status is not None and status not in reports.STATUSES:
        raise _invalid("invalid_status", f"status must be one of {', '.join(reports.STATUSES)}")
    stmt = select(BugReport)
    count = select(func.count()).select_from(BugReport)
    if status:
        stmt = stmt.where(BugReport.status == status)
        count = count.where(BugReport.status == status)
    total = (await db.execute(count)).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(BugReport.created_at.desc(), BugReport.id).limit(limit).offset(offset)
        )
    ).scalars()
    return BugReportPage(
        items=[BugReportSummary(**_summary_fields(row)) for row in rows], total=total
    )


async def _get_or_404(db: AsyncSession, report_id: str) -> BugReport:
    row = await db.get(BugReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bug report not found")
    return row


@router.get("/{report_id}", response_model=BugReportDetail)
async def get_bug_report(
    report_id: str,
    response: Response,
    _flag=Depends(require_bug_reports),
    _admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
) -> BugReportDetail:
    response.headers["Cache-Control"] = "no-store"
    return _detail(await _get_or_404(db, report_id))


@router.get("/{report_id}/screenshot")
async def get_bug_report_screenshot(
    report_id: str,
    _flag=Depends(require_bug_reports),
    _admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    row = await _get_or_404(db, report_id)
    if not row.screenshot_key:
        raise HTTPException(status_code=404, detail="This report has no screenshot")
    from object_storage import object_storage

    buffer = io.BytesIO()
    try:
        await asyncio.to_thread(object_storage.download_to_fileobj, row.screenshot_key, buffer)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="The screenshot is no longer stored")
    data = buffer.getvalue()
    # The stored type was sniffed at upload; check again rather than trust it.
    content_type = reports.sniff_screenshot_type(data) or "application/octet-stream"
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Content-Disposition": (
                f'inline; filename="bug-report-{row.id}.'
                f'{reports.SCREENSHOT_TYPES.get(content_type, "bin")}"'
            ),
        },
    )


@router.post("/{report_id}/redeliver", response_model=BugReportDetail)
async def redeliver_bug_report(
    report_id: str,
    _flag=Depends(require_bug_reports),
    _admin=Depends(require_superadmin),
    db: AsyncSession = Depends(get_async_db),
) -> BugReportDetail:
    row = await _get_or_404(db, report_id)
    if row.status == reports.STATUS_DELIVERED or row.issue_url:
        raise HTTPException(
            status_code=409,
            detail={"code": "already_delivered", "message": "This report is already delivered."},
        )
    row.status = reports.STATUS_PENDING
    row.delivery_error = None
    await db.commit()
    await db.refresh(row)
    _queue_delivery(row.id)
    return _detail(row)
