"""Per-user abuse ceilings (documented in docs/full-api.md, "Limits").

Three ceilings, each far above what heavy legitimate use reaches, so they
only stop runaway scripts and blatant abuse. Each is a setting where 0
switches it off; superadmins are exempt from all three.

- ``BEARER_TOKEN_RPM`` (default 1200): requests per minute per user made with
  a session token in ``Authorization: Bearer`` (the script token from
  ``POST /api/auth/token``). Browser sessions authenticate with the cookie and
  are not counted; access keys have their own per-key limits
  (``services/rate_limiter.enforce_key_rate_limit``). Checked by the auth
  dependencies (``auth_module/dependencies.py``). ``429 rate_limited``.
- ``UPLOAD_URLS_PER_DAY`` (default 200): presigned import upload URLs per
  user and rolling 24 hours, across both upload-url routes.
  ``429 upload_url_limit_exceeded``.
- ``MAX_ACTIVE_RUNS_PER_USER`` (default 50): generation and evaluation runs
  a user has queued or running at once, checked where runs are started,
  resumed or retried. An evaluation run is one ``EvaluationRun``; generation
  has no run record (a start creates one row per task, model and structure),
  so a user's queued or running generation work on one project counts as one
  run, and more generation on a project that already has some is never
  refused. ``429 too_many_active_runs``.

Every refusal carries ``Retry-After`` and counts in
``benger_rate_limited_total`` (``services/limit_metrics.py``). The two Redis
limits fail open when Redis is down, like the other request limits.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from services.limit_metrics import record_rate_limited
from services import rate_limiter as _rl

logger = logging.getLogger(__name__)

BEARER_RATE_ENDPOINT = "bearer"
UPLOAD_URL_ENDPOINT = "upload_url"
UPLOAD_URL_WINDOW_SECONDS = 86400
#: Run statuses that count as active (queued or running).
ACTIVE_RUN_STATUSES = ("pending", "running")
#: ``Retry-After`` of a refused run start: there is no fixed reset time, the
#: client checks again once some of its runs have finished.
ACTIVE_RUNS_RETRY_AFTER = 60

_COUNTED_ATTR = "bearer_rate_counted"


def _settings():
    from app.core.config import settings

    return settings


def _limit(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _too_many(kind: str, code: str, message: str, retry_after: int, headers=None, **extra):
    """The 429 of one ceiling; ``kind`` is its ``benger_rate_limited_total``
    label, ``extra`` goes into the detail."""
    record_rate_limited(kind)
    return HTTPException(
        status_code=429,
        detail={"code": code, "message": message, "retry_after": retry_after, **extra},
        headers={"Retry-After": str(retry_after), **(headers or {})},
    )


# --------------------------------------------------------------------------- #
# Bearer session tokens
# --------------------------------------------------------------------------- #


def enforce_bearer_rate_limit(request, user) -> None:
    """Count one request of ``user`` made with a session token sent in the
    Authorization header; 429 ``rate_limited`` above ``BEARER_TOKEN_RPM``.

    The caller decides that the token came from the header. A request is
    counted once even when several auth dependencies run for it.
    """
    rpm = _limit(_settings().bearer_token_rpm)
    if not rpm or user is None or getattr(user, "is_superadmin", False):
        return
    state = getattr(request, "state", None)
    if state is not None and getattr(state, _COUNTED_ATTR, False) is True:
        return
    try:
        setattr(state, _COUNTED_ATTR, True)
    except Exception:  # pragma: no cover - requests without state
        pass
    error = _rl.rate_limiter.check_rate_limit_sync(
        request,
        BEARER_RATE_ENDPOINT,
        {"minute": (rpm, 60)},
        client_id=f"user:{user.id}",
    )
    if error:
        raise _too_many(
            "user_bearer",
            "rate_limited",
            f"Too many requests with this token: at most {rpm} per minute per user. "
            "Wait for Retry-After, or use an access key with its own limits.",
            error["retry_after"],
            headers={
                "X-RateLimit-Limit": str(error["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(error["reset"]),
            },
        )


# --------------------------------------------------------------------------- #
# Import upload URLs
# --------------------------------------------------------------------------- #


async def enforce_upload_url_limit(user) -> None:
    """Count one presigned upload URL for ``user``; 429
    ``upload_url_limit_exceeded`` above ``UPLOAD_URLS_PER_DAY`` in the last
    24 hours. Call it after the route's own checks, so a refused request does
    not use up the allowance."""
    per_day = _limit(_settings().upload_urls_per_day)
    if not per_day or user is None or getattr(user, "is_superadmin", False):
        return
    error = await _rl.rate_limiter.check_rolling_limit(
        f"user:{user.id}", UPLOAD_URL_ENDPOINT, per_day, UPLOAD_URL_WINDOW_SECONDS
    )
    if error:
        raise _too_many(
            "upload_url",
            "upload_url_limit_exceeded",
            f"Too many import uploads: at most {per_day} upload URLs per user in 24 hours.",
            error["retry_after"],
            limit=per_day,
        )


# --------------------------------------------------------------------------- #
# Active generation and evaluation runs
# --------------------------------------------------------------------------- #


def _evaluation_runs_stmt(user_id: str):
    from sqlalchemy import func, select

    from models import EvaluationRun

    return (
        select(func.count())
        .select_from(EvaluationRun)
        .where(
            EvaluationRun.created_by == user_id,
            EvaluationRun.status.in_(ACTIVE_RUN_STATUSES),
            # Only runs started with POST /evaluations/run; immediate
            # per-annotation grading and human-graded runs are not counted.
            EvaluationRun.eval_metadata["evaluation_type"].as_string() == "evaluation",
        )
    )


def _generation_projects_stmt(user_id: str):
    from sqlalchemy import distinct, func, select

    from models import ResponseGeneration

    return select(func.count(distinct(func.coalesce(ResponseGeneration.project_id, "")))).where(
        ResponseGeneration.created_by == user_id,
        ResponseGeneration.status.in_(ACTIVE_RUN_STATUSES),
    )


def _project_generating_stmt(user_id: str, project_id: str):
    from sqlalchemy import select

    from models import ResponseGeneration

    return (
        select(ResponseGeneration.id)
        .where(
            ResponseGeneration.created_by == user_id,
            ResponseGeneration.project_id == project_id,
            ResponseGeneration.status.in_(ACTIVE_RUN_STATUSES),
        )
        .limit(1)
    )


def _runs_refusal(active: int, limit: int) -> HTTPException:
    return _too_many(
        "active_runs",
        "too_many_active_runs",
        f"You have {active} generation or evaluation runs queued or running; "
        f"at most {limit} may run at once. Wait for some to finish, or stop or "
        "pause some, then start again.",
        ACTIVE_RUNS_RETRY_AFTER,
        limit=limit,
        active=active,
    )


def _active_runs_limit(user) -> int:
    if user is None or getattr(user, "is_superadmin", False):
        return 0
    return _limit(_settings().max_active_runs_per_user)


async def check_active_runs(db, user, *, generation_project_id: Optional[str] = None) -> None:
    """429 ``too_many_active_runs`` when ``user`` already has
    ``MAX_ACTIVE_RUNS_PER_USER`` runs queued or running (async session).

    ``generation_project_id``: the call starts generation work on this
    project, which adds no run when the user already generates there.
    """
    limit = _active_runs_limit(user)
    if not limit:
        return
    user_id = str(user.id)
    if generation_project_id is not None:
        already = (
            await db.execute(_project_generating_stmt(user_id, generation_project_id))
        ).first()
        if already is not None:
            return
    evaluations = (await db.execute(_evaluation_runs_stmt(user_id))).scalar() or 0
    generations = (await db.execute(_generation_projects_stmt(user_id))).scalar() or 0
    active = int(evaluations) + int(generations)
    if active >= limit:
        raise _runs_refusal(active, limit)


def check_active_runs_sync(db, user, *, generation_project_id: Optional[str] = None) -> None:
    """Sync-session twin of :func:`check_active_runs`."""
    limit = _active_runs_limit(user)
    if not limit:
        return
    user_id = str(user.id)
    if generation_project_id is not None:
        if db.execute(_project_generating_stmt(user_id, generation_project_id)).first():
            return
    evaluations = db.execute(_evaluation_runs_stmt(user_id)).scalar() or 0
    generations = db.execute(_generation_projects_stmt(user_id)).scalar() or 0
    active = int(evaluations) + int(generations)
    if active >= limit:
        raise _runs_refusal(active, limit)
