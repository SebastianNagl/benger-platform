"""In-app problem reports: limits, the technical context, the issue text and
the delivery to an issue tracker.

A report ("Report a problem" in the account menu, the footer and the error
pages) is stored in ``bug_reports`` (``models.BugReport``) by
``routers/bug_reports.py`` and then delivered by the worker task
``tasks.deliver_bug_report`` as an issue of a GitHub repository. Everything
that decides what a report may hold and what the issue says lives here, so
the API and the workers share one definition.

Delivery target
    Configured by environment, read on every call (tests and a redeploy can
    change it):

    - ``BUG_REPORT_GITHUB_REPO``: ``owner/name`` of the repository.
    - ``BUG_REPORT_GITHUB_TOKEN``: a token that may create issues there.
    - ``BUG_REPORT_GITHUB_LABELS``: comma-separated labels (default
      ``bug,user-report``; empty for none).
    - ``BUG_REPORT_GITHUB_API_URL``: the API base (default
      ``https://api.github.com``; a test stack points it at a stub).

    Without repository or token nothing is delivered: the report is kept
    with status ``stored`` and superadmins see it in the list. A repository
    that is not private is refused before any issue is created: the report
    is kept as ``failed`` with that error and can be delivered again once
    the repository is private.

What leaves the platform
    The issue carries the reporter's text and the technical context, the
    reporter only as an internal user id, and links into the platform (the
    report in the admin list, the screenshot behind the superadmin route).
    No name, no e-mail address, no contact address, no project or task
    title: the context holds ids only, and the screenshot never leaves the
    platform (the issues API takes no attachments, and a public link would
    expose it).
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

MAX_TITLE_CHARS = 150
MAX_DESCRIPTION_CHARS = 5000
MAX_EXPECTED_CHARS = 5000
MAX_CONTACT_EMAIL_CHARS = 254
#: Compact JSON of the context as the browser sends it.
MAX_CONTEXT_BYTES = 64 * 1024
MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024

#: Reports per hour: a signed-in user, and a caller without a session (by
#: client address, so a shared address shares the bucket).
USER_REPORTS_PER_HOUR = 10
ANONYMOUS_REPORTS_PER_HOUR = 3

#: Image types a screenshot may have, by their leading bytes.
SCREENSHOT_TYPES: Dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

STATUS_PENDING = "pending"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"
STATUS_STORED = "stored"
STATUSES = (STATUS_PENDING, STATUS_DELIVERED, STATUS_FAILED, STATUS_STORED)

#: Retries of one delivery after the first attempt, and their back-off.
MAX_DELIVERY_RETRIES = 5
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 3600

#: A pending report nobody touched for this long is queued again by the
#: sweep (its first send was lost, for example while the broker was down).
#: Longer than the whole retry chain, so a running chain is left alone.
SWEEP_STALE_AFTER = timedelta(hours=1)

HTTP_TIMEOUT_SECONDS = 20.0
MAX_ERROR_CHARS = 500


def retry_countdown(retries: int) -> int:
    """Seconds before retry number ``retries + 1``: 60, 120, 240, ... capped."""
    return min(RETRY_BASE_SECONDS * (2 ** max(0, retries)), RETRY_MAX_SECONDS)


def sniff_screenshot_type(data: bytes) -> Optional[str]:
    """The image type of ``data`` from its leading bytes, or None when it is
    not one of :data:`SCREENSHOT_TYPES` (the declared type is not trusted)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# ---------------------------------------------------------------------------
# The technical context
# ---------------------------------------------------------------------------

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_TOKENISH = re.compile(r"^[A-Za-z0-9_\-.~%]{24,}$")
#: Pages whose last path segment is a secret (invitation, activation,
#: password reset and e-mail links).
_TOKEN_ROUTES = frozenset(
    {
        "accept-invitation",
        "activate",
        "confirm-email-change",
        "reset-password",
        "verify-email",
    }
)
REDACTED = "[redacted]"

_MAX_PATH = 500
_MAX_SHORT = 100
_MAX_TEXT = 500
_MAX_MESSAGE = 1000
_MAX_STACK = 4000
_MAX_ERRORS = 5
_MAX_REQUESTS = 10
_MAX_NAVIGATION = 15
_MAX_NAMES = 50
_MAX_PARAMS = 10

#: Route parameters that may travel (ids of what the page shows).
_PARAM_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,49}$")


def _text(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = value.replace("\x00", "").strip()
    if not value:
        return None
    return value[:limit]


def _number(value: Any, *, low: float = 0, high: float = 100_000) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value < low or value > high:  # NaN or out of range
        return None
    return int(value) if float(value).is_integer() else round(float(value), 3)


def clean_path(value: Any) -> Optional[str]:
    """A page or API path without query, fragment or secrets.

    Accepts a path or a full URL; keeps only the path. A segment after one of
    the token routes, and any long token-like segment that is not a UUID, is
    replaced by ``[redacted]``, so links with secrets in them never travel.
    """
    raw = _text(value, 2000)
    if raw is None:
        return None
    if "://" in raw:
        raw = raw.split("://", 1)[1]
        raw = "/" + raw.split("/", 1)[1] if "/" in raw else "/"
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    if not raw.startswith("/"):
        raw = "/" + raw
    segments = raw.split("/")
    cleaned: List[str] = []
    after_token_route = False
    for segment in segments:
        if after_token_route and segment:
            cleaned.append(REDACTED)
            after_token_route = False
            continue
        if segment in _TOKEN_ROUTES:
            after_token_route = True
            cleaned.append(segment)
            continue
        if _TOKENISH.match(segment) and not _UUID.match(segment):
            cleaned.append(REDACTED)
            continue
        cleaned.append(segment)
    return "/".join(cleaned)[:_MAX_PATH]


def _names(value: Any, limit: int = _MAX_NAMES) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        name = _text(item, _MAX_SHORT)
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def _time(value: Any) -> Optional[str]:
    return _text(value, 40)


def _params(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: Dict[str, str] = {}
    for key, item in value.items():
        if len(out) >= _MAX_PARAMS:
            break
        if not isinstance(key, str) or not _PARAM_KEY.match(key):
            continue
        text = _text(item, _MAX_SHORT)
        if text is None:
            continue
        if _TOKENISH.match(text) and not _UUID.match(text):
            text = REDACTED
        out[key] = text
    return out


def _size(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    width = _number(value.get("width"))
    height = _number(value.get("height"))
    if width is None or height is None:
        return None
    return {"width": width, "height": height}


def _errors(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value[-_MAX_ERRORS:]:
        if not isinstance(item, dict):
            continue
        message = _text(item.get("message"), _MAX_MESSAGE)
        if message is None:
            continue
        entry: Dict[str, Any] = {"message": message}
        for key, limit in (("name", _MAX_SHORT), ("source", _MAX_SHORT), ("digest", _MAX_SHORT)):
            text = _text(item.get(key), limit)
            if text:
                entry[key] = text
        stack = _text(item.get("stack"), _MAX_STACK)
        if stack:
            entry["stack"] = stack
        path = clean_path(item.get("path"))
        if path:
            entry["path"] = path
        when = _time(item.get("time"))
        if when:
            entry["time"] = when
        out.append(entry)
    return out


def _requests(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value[-_MAX_REQUESTS:]:
        if not isinstance(item, dict):
            continue
        method = _text(item.get("method"), 10)
        path = clean_path(item.get("path"))
        if not method or not path:
            continue
        entry: Dict[str, Any] = {"method": method.upper(), "path": path}
        status = _number(item.get("status"), high=999)
        entry["status"] = int(status) if status is not None else 0
        for key in ("request_id", "error"):
            text = _text(item.get(key), _MAX_SHORT)
            if text:
                entry[key] = text
        duration = _number(item.get("duration_ms"), high=3_600_000)
        if duration is not None:
            entry["duration_ms"] = duration
        when = _time(item.get("time"))
        if when:
            entry["time"] = when
        out.append(entry)
    return out


def _navigation(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value[-_MAX_NAVIGATION:]:
        if not isinstance(item, dict):
            continue
        path = clean_path(item.get("path"))
        if not path:
            continue
        entry: Dict[str, Any] = {"path": path}
        when = _time(item.get("time"))
        if when:
            entry["time"] = when
        out.append(entry)
    return out


def clean_context(raw: Any) -> Dict[str, Any]:
    """The technical context a browser sent, reduced to the keys, types and
    sizes a report may hold. Unknown keys are dropped; nothing here can carry
    request bodies, cookies or tokens."""
    if not isinstance(raw, dict):
        return {}
    ctx: Dict[str, Any] = {}

    def put(key: str, value: Any) -> None:
        if value not in (None, "", [], {}):
            ctx[key] = value

    put("source", _text(raw.get("source"), 20))
    put("page", clean_path(raw.get("page")))
    put("query_keys", _names(raw.get("query_keys"), 20))
    put("route_params", _params(raw.get("route_params")))
    put("referrer", clean_path(raw.get("referrer")))
    put("time", _time(raw.get("time")))
    put("timezone", _text(raw.get("timezone"), _MAX_SHORT))
    put("locale", _text(raw.get("locale"), 20))
    put("languages", _names(raw.get("languages"), 5))
    put("user_agent", _text(raw.get("user_agent"), _MAX_TEXT))
    put("platform", _text(raw.get("platform"), _MAX_SHORT))
    put("viewport", _size(raw.get("viewport")))
    put("screen", _size(raw.get("screen")))
    put("device_pixel_ratio", _number(raw.get("device_pixel_ratio"), high=20))
    put("color_scheme", _text(raw.get("color_scheme"), 20))
    if isinstance(raw.get("online"), bool):
        ctx["online"] = raw["online"]
    put("app_version", _text(raw.get("app_version"), _MAX_SHORT))
    put("core_version", _text(raw.get("core_version"), 20))
    put("edition", _text(raw.get("edition"), 40))
    put("extensions", _names(raw.get("extensions")))
    put("feature_flags", _names(raw.get("feature_flags")))
    put("ui_mode", _text(raw.get("ui_mode"), 20))
    put("org_roles", _names(raw.get("org_roles"), 10))
    put("errors", _errors(raw.get("errors")))
    put("failed_requests", _requests(raw.get("failed_requests")))
    put("navigation", _navigation(raw.get("navigation")))
    return ctx


def server_context(*, user_agent: Optional[str], is_superadmin: Optional[bool]) -> Dict[str, Any]:
    """What the server adds to a report: when it arrived, the deployed
    versions and the request's browser line (the browser's own claim can be
    missing or stale)."""
    from app_version import app_version
    from core_version import CORE_API_VERSION

    out: Dict[str, Any] = {
        "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "core_version": CORE_API_VERSION,
    }
    version = app_version()
    if version:
        out["app_version"] = version
    ua = _text(user_agent, _MAX_TEXT)
    if ua:
        out["user_agent"] = ua
    if is_superadmin is not None:
        out["reporter_is_superadmin"] = bool(is_superadmin)
    return out


# ---------------------------------------------------------------------------
# The issue
# ---------------------------------------------------------------------------


def _single_line(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _fenced(text: str, info: str = "") -> str:
    """``text`` as a fenced code block that no backtick run inside it can
    close, so the reporter's words render verbatim: no markup, no mentions,
    no links."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{info}\n{text}\n{fence}"


def report_admin_url(frontend_url: str, report_id: str) -> str:
    return f"{frontend_url.rstrip('/')}/admin/bug-reports?report={report_id}"


def screenshot_admin_url(frontend_url: str, report_id: str) -> str:
    return f"{frontend_url.rstrip('/')}/api/bug-reports/{report_id}/screenshot"


def _facts(report, ctx: Dict[str, Any], server: Dict[str, Any]) -> str:
    lines: List[str] = []

    def line(label: str, value: Any) -> None:
        if value in (None, "", [], {}):
            return
        lines.append(f"{label}: {value}")

    line("Page", ctx.get("page"))
    line("Opened from", ctx.get("source"))
    params = ctx.get("route_params") or {}
    line("Route params", ", ".join(f"{k}={v}" for k, v in params.items()))
    line("Query keys", ", ".join(ctx.get("query_keys") or []))
    line("Referrer", ctx.get("referrer"))
    line("Reported at", server.get("received_at"))
    line("Client time", ctx.get("time"))
    line("Timezone", ctx.get("timezone"))
    line("Locale", ctx.get("locale"))
    line("Browser", server.get("user_agent") or ctx.get("user_agent"))
    line("Platform", ctx.get("platform"))
    viewport = ctx.get("viewport")
    if viewport:
        dpr = ctx.get("device_pixel_ratio")
        line(
            "Viewport",
            f"{viewport['width']}x{viewport['height']}" + (f" @{dpr}x" if dpr else ""),
        )
    screen = ctx.get("screen")
    if screen:
        line("Screen", f"{screen['width']}x{screen['height']}")
    line("Color scheme", ctx.get("color_scheme"))
    if "online" in ctx:
        line("Online", "yes" if ctx["online"] else "no")
    line("App version (server)", server.get("app_version"))
    line("App version (browser)", ctx.get("app_version"))
    line("Core version", server.get("core_version") or ctx.get("core_version"))
    line("Edition", ctx.get("edition"))
    line("Extensions", ", ".join(ctx.get("extensions") or []))
    line("Feature flags on", ", ".join(ctx.get("feature_flags") or []))
    line("UI mode", ctx.get("ui_mode"))
    if report.reporter_id:
        role = "superadmin" if server.get("reporter_is_superadmin") else "user"
        roles = ", ".join(ctx.get("org_roles") or [])
        line("Reporter", f"{role} {report.reporter_id}" + (f" (org roles: {roles})" if roles else ""))
    else:
        line(
            "Reporter",
            "not signed in" + (", left a contact address (see BenGER)" if report.contact_email else ""),
        )
    return "\n".join(lines)


def render_issue(report, *, frontend_url: str) -> Tuple[str, str]:
    """Title and Markdown body of the issue for ``report``."""
    ctx = report.context or {}
    server = ctx.get("server") or {}
    title = _single_line(report.title, MAX_TITLE_CHARS) or "Problem report"
    parts: List[str] = [
        "### What happened",
        _fenced(report.description.strip(), "text"),
    ]
    if report.expected and report.expected.strip():
        parts += ["### What was expected", _fenced(report.expected.strip(), "text")]
    parts += ["### Context", _fenced(_facts(report, ctx, server), "text")]

    if report.screenshot_key:
        parts += [
            "### Screenshot",
            f"[Open the screenshot in BenGER]({screenshot_admin_url(frontend_url, report.id)})"
            " (superadmin sign-in required).",
        ]

    errors = ctx.get("errors") or []
    if errors:
        blocks = []
        for entry in errors:
            head = " ".join(
                x for x in (entry.get("time"), entry.get("name"), entry.get("source")) if x
            )
            text = (f"[{head}] " if head else "") + entry["message"]
            if entry.get("path"):
                text += f"\nat page {entry['path']}"
            if entry.get("digest"):
                text += f"\ndigest {entry['digest']}"
            if entry.get("stack"):
                text += "\n" + entry["stack"]
            blocks.append(_fenced(text, "text"))
        parts.append(
            f"<details><summary>Recent frontend errors ({len(errors)})</summary>\n\n"
            + "\n\n".join(blocks)
            + "\n\n</details>"
        )

    requests = ctx.get("failed_requests") or []
    if requests:
        rows = []
        for entry in requests:
            row = f"{entry.get('time', '')} {entry['method']} {entry['path']} -> {entry.get('status', 0)}"
            if entry.get("error"):
                row += f" ({entry['error']})"
            if entry.get("duration_ms") is not None:
                row += f" {entry['duration_ms']} ms"
            if entry.get("request_id"):
                row += f" request-id {entry['request_id']}"
            rows.append(row.strip())
        parts.append(
            f"<details><summary>Failed API requests ({len(requests)})</summary>\n\n"
            + _fenced("\n".join(rows), "text")
            + "\n\n</details>"
        )

    navigation = ctx.get("navigation") or []
    if navigation:
        rows = [f"{entry.get('time', '')} {entry['path']}".strip() for entry in navigation]
        parts.append(
            f"<details><summary>Recent navigation ({len(navigation)})</summary>\n\n"
            + _fenced("\n".join(rows), "text")
            + "\n\n</details>"
        )

    parts += [
        "---",
        f"Report `{report.id}`: [open in BenGER]({report_admin_url(frontend_url, report.id)})"
        " (superadmin sign-in required).",
    ]
    return title, "\n\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_LABELS = ("bug", "user-report")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class DeliveryTarget:
    repo: str
    token: str = field(repr=False)
    labels: Tuple[str, ...]
    api_url: str


def delivery_target() -> Optional[DeliveryTarget]:
    """The configured issue repository, or None when delivery is off (no or
    malformed repository, no token)."""
    repo = os.environ.get("BUG_REPORT_GITHUB_REPO", "").strip()
    token = os.environ.get("BUG_REPORT_GITHUB_TOKEN", "").strip()
    if not repo or not token:
        return None
    if not _REPO.match(repo):
        logger.error("BUG_REPORT_GITHUB_REPO is not of the form owner/name; delivery is off")
        return None
    raw_labels = os.environ.get("BUG_REPORT_GITHUB_LABELS")
    if raw_labels is None:
        labels: Tuple[str, ...] = DEFAULT_LABELS
    else:
        labels = tuple(dict.fromkeys(x.strip() for x in raw_labels.split(",") if x.strip()))
    api_url = os.environ.get("BUG_REPORT_GITHUB_API_URL", "").strip().rstrip("/") or DEFAULT_API_URL
    return DeliveryTarget(repo=repo, token=token, labels=labels, api_url=api_url)


class DeliveryError(Exception):
    """One delivery attempt failed. ``transient``: worth retrying (network,
    timeouts, 5xx, rate limits); otherwise retrying cannot help."""

    def __init__(self, message: str, *, transient: bool):
        super().__init__(message)
        self.transient = transient


def _excerpt(response) -> str:
    try:
        data = response.json()
        message = data.get("message") if isinstance(data, dict) else None
    except Exception:
        message = None
    if not message:
        message = (response.text or "")[:200]
    return _single_line(str(message), 200)


def _is_rate_limited(response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    if response.headers.get("x-ratelimit-remaining") == "0" or response.headers.get("retry-after"):
        return True
    return "rate limit" in (response.text or "").lower()


PRIVATE_CHECK_TTL_SECONDS = 600
NOT_PRIVATE_ERROR = "Delivery refused: the target repository is not private"

# (api_url, repo) -> monotonic time until which the repository counts as
# private; only a confirmed private answer is kept, so a refusal is checked
# again on the next attempt.
_private_until: Dict[Tuple[str, str], float] = {}


def _github_error(response) -> DeliveryError:
    message = f"GitHub answered {response.status_code}: {_excerpt(response)}"
    transient = response.status_code >= 500 or _is_rate_limited(response)
    return DeliveryError(message[:MAX_ERROR_CHARS], transient=transient)


def _require_private(target: DeliveryTarget, http, headers: Dict[str, str]) -> None:
    """Refuse a target repository that is not private: reports hold the
    reporter's text and technical context and must never become public."""
    import httpx

    key = (target.api_url, target.repo)
    now = time.monotonic()
    if _private_until.get(key, 0.0) > now:
        return
    try:
        response = http.get(f"{target.api_url}/repos/{target.repo}", headers=headers)
    except httpx.HTTPError as exc:
        raise DeliveryError(f"GitHub unreachable ({type(exc).__name__})", transient=True) from None
    if response.status_code != 200:
        raise _github_error(response)
    try:
        private = response.json().get("private") is True
    except Exception:
        private = False
    if not private:
        _private_until.pop(key, None)
        logger.error("bug report delivery refused: %s is not a private repository", target.repo)
        raise DeliveryError(NOT_PRIVATE_ERROR, transient=False)
    _private_until[key] = now + PRIVATE_CHECK_TTL_SECONDS


def create_github_issue(
    target: DeliveryTarget,
    title: str,
    body: str,
    *,
    client=None,
) -> Tuple[int, str]:
    """Create the issue; returns ``(number, html_url)``.

    The target repository must be private (checked first, a confirmed answer
    kept for :data:`PRIVATE_CHECK_TTL_SECONDS`); otherwise nothing is posted.
    Labels the repository does not accept (422 on ``labels``) do not lose the
    report: the issue is created again without them. Raises
    :class:`DeliveryError`; its message never holds the token.
    """
    import httpx

    url = f"{target.api_url}/repos/{target.repo}/issues"
    headers = {
        "Authorization": f"Bearer {target.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "benger-bug-reports",
    }
    own_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        _require_private(target, http, headers)
        payload: Dict[str, Any] = {"title": title, "body": body}
        if target.labels:
            payload["labels"] = list(target.labels)
        for attempt in range(2):
            try:
                response = http.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                raise DeliveryError(
                    f"GitHub unreachable ({type(exc).__name__})", transient=True
                ) from None
            if response.status_code == 201:
                data = response.json()
                return int(data["number"]), str(data["html_url"])
            if (
                response.status_code == 422
                and attempt == 0
                and "labels" in payload
                and "label" in (response.text or "").lower()
            ):
                logger.warning("bug report labels refused by the repository; creating without")
                payload.pop("labels")
                continue
            break
        raise _github_error(response)
    finally:
        if own_client:
            http.close()


@dataclass
class DeliveryOutcome:
    """What one delivery attempt did: ``state`` is the report's status
    afterwards (or ``missing`` / ``skipped``); ``retry`` asks the task to try
    again later."""

    state: str
    retry: bool = False
    error: Optional[str] = None


def deliver_report(
    db,
    report_id: str,
    *,
    final: bool,
    frontend_url: Optional[str] = None,
    create_issue: Callable[..., Tuple[int, str]] = create_github_issue,
) -> DeliveryOutcome:
    """One delivery attempt of the report ``report_id`` (sync session).

    The row is locked for the attempt, so a second send of the same report
    (a sweep, a redelivery) waits and then finds it delivered. A report that
    is already delivered is left alone. Without a target the report becomes
    ``stored``. A transient error keeps it ``pending`` and asks for a retry
    unless ``final``; any other error, and a transient one on the final
    attempt, marks it ``failed``. Commits.
    """
    from sqlalchemy import select

    from models import BugReport

    report = db.execute(
        select(BugReport).where(BugReport.id == report_id).with_for_update()
    ).scalar_one_or_none()
    if report is None:
        db.rollback()
        return DeliveryOutcome("missing")
    if report.status == STATUS_DELIVERED or report.issue_url:
        db.rollback()
        return DeliveryOutcome("skipped")

    target = delivery_target()
    if target is None:
        report.status = STATUS_STORED
        report.delivery_error = None
        db.commit()
        return DeliveryOutcome(STATUS_STORED)

    if frontend_url is None:
        from public_hosts import main_frontend_url

        frontend_url = main_frontend_url()
    title, body = render_issue(report, frontend_url=frontend_url)
    report.delivery_attempts = (report.delivery_attempts or 0) + 1
    try:
        number, html_url = create_issue(target, title, body)
    except DeliveryError as exc:
        report.delivery_error = str(exc)[:MAX_ERROR_CHARS]
        retry = exc.transient and not final
        report.status = STATUS_PENDING if retry else STATUS_FAILED
        db.commit()
        logger.warning("bug report %s: delivery failed (%s)", report_id, report.delivery_error)
        return DeliveryOutcome(report.status, retry=retry, error=report.delivery_error)
    except Exception as exc:  # a bug here must not leave the row locked
        report.delivery_error = f"Delivery error ({type(exc).__name__})"
        report.status = STATUS_PENDING if not final else STATUS_FAILED
        db.commit()
        logger.exception("bug report %s: unexpected delivery error", report_id)
        return DeliveryOutcome(report.status, retry=not final, error=report.delivery_error)

    report.status = STATUS_DELIVERED
    report.issue_number = number
    report.issue_url = html_url
    report.delivery_error = None
    report.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return DeliveryOutcome(STATUS_DELIVERED)


def stale_pending_ids(db, *, now: Optional[datetime] = None, limit: int = 100) -> List[str]:
    """Pending reports nobody touched for :data:`SWEEP_STALE_AFTER`."""
    from sqlalchemy import select

    from models import BugReport

    cutoff = (now or datetime.now(timezone.utc)) - SWEEP_STALE_AFTER
    rows = db.execute(
        select(BugReport.id)
        .where(BugReport.status == STATUS_PENDING, BugReport.updated_at < cutoff)
        .order_by(BugReport.created_at)
        .limit(limit)
    ).scalars()
    return list(rows)


def requeue_stale(db, send: Callable[[str], Any], **kwargs) -> List[str]:
    """Queue the delivery of every stale pending report again; returns the ids."""
    ids = stale_pending_ids(db, **kwargs)
    queued: List[str] = []
    for report_id in ids:
        try:
            send(report_id)
            queued.append(report_id)
        except Exception:
            logger.exception("bug report %s: could not queue the delivery", report_id)
    return queued

