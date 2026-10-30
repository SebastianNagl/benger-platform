"""Exceptions raised by the BenGER client.

The API answers errors in two shapes and :func:`error_from_response` reads
both:

* ``/api/v1``: ``{"error": {"code", "message", "request_id", "details"}}``
* the full API: ``{"detail": {"code", "message", ...extra}}``,
  ``{"detail": "text"}`` or, for FastAPI validation errors,
  ``{"detail": [{"loc", "msg", "type"}, ...]}``.

Branch on :attr:`BengerAPIError.code` (stable), not on the message.
"""

from __future__ import annotations

from typing import Any

import httpx

__all__ = [
    "BengerError",
    "BengerConnectionError",
    "BengerTimeoutError",
    "BengerJobError",
    "BengerAPIError",
    "BadRequestError",
    "AuthenticationError",
    "PermissionDeniedError",
    "InsufficientScopeError",
    "NotFoundError",
    "ConflictError",
    "GoneError",
    "ValidationError",
    "RateLimitError",
    "ServerError",
    "error_from_response",
]

_DEFAULT_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


class BengerError(Exception):
    """Base class of every exception this package raises."""


class BengerConnectionError(BengerError):
    """The request never got an HTTP answer (DNS, connect, read timeout)."""


class BengerTimeoutError(BengerError):
    """A wait helper gave up before the job reached a final state."""

    def __init__(self, message: str, last_value: Any = None):
        super().__init__(message)
        self.last_value = last_value


class BengerJobError(BengerError):
    """An asynchronous job (import, export, generation, evaluation) failed."""

    def __init__(self, message: str, job: Any = None):
        super().__init__(message)
        self.job = job


class BengerAPIError(BengerError):
    """An HTTP error answer from the API.

    Attributes:
        status: HTTP status code.
        code: machine-readable error code (``insufficient_scope``, ``not_found``...).
        message: human-readable message (may change between releases).
        request_id: the ``X-Request-ID`` of the request, quote it in bug reports.
        details: extra structured data (``required_scopes``, ``errors``...).
        method, url: the request that failed (no credentials).
        response: the raw ``httpx.Response``.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
        *,
        method: str | None = None,
        url: str | None = None,
        response: httpx.Response | None = None,
    ):
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.details = details or {}
        self.method = method
        self.url = url
        self.response = response
        super().__init__(str(self))

    def __str__(self) -> str:
        where = f" [{self.method} {self.url}]" if self.method and self.url else ""
        rid = f" (request_id={self.request_id})" if self.request_id else ""
        return f"{self.status} {self.code}: {self.message}{where}{rid}"

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(status={self.status!r}, code={self.code!r}, "
            f"message={self.message!r}, request_id={self.request_id!r})"
        )


class BadRequestError(BengerAPIError):
    """400."""


class AuthenticationError(BengerAPIError):
    """401: missing, unknown, revoked or expired key, or a route closed to keys
    (``api_key_not_allowed_here``)."""


class PermissionDeniedError(BengerAPIError):
    """403: the role, organisation, time window or key restriction forbids it."""


class InsufficientScopeError(PermissionDeniedError):
    """403 ``insufficient_scope``: the key lacks :attr:`required_scopes`."""

    @property
    def required_scopes(self) -> list[str]:
        scopes = self.details.get("required_scopes") or []
        return list(scopes) if isinstance(scopes, (list, tuple)) else [str(scopes)]


class NotFoundError(BengerAPIError):
    """404: unknown, invisible to this key, or not ready yet."""


class ConflictError(BengerAPIError):
    """409 (for example ``idempotency_in_progress``)."""


class GoneError(BengerAPIError):
    """410 (for example ``export_expired``)."""


class ValidationError(BengerAPIError):
    """422: invalid body or query. ``details["errors"]`` lists FastAPI field errors."""


class RateLimitError(BengerAPIError):
    """429 after the client used up its retries. :attr:`retry_after` in seconds."""

    @property
    def retry_after(self) -> float | None:
        if self.response is None:
            return None
        return parse_retry_after(self.response.headers.get("Retry-After"))


class ServerError(BengerAPIError):
    """5xx."""


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a ``Retry-After`` header (delta seconds or an HTTP date)."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    from email.utils import parsedate_to_datetime

    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    from datetime import datetime, timezone

    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _class_for(status: int, code: str) -> type[BengerAPIError]:
    if status == 403 and code == "insufficient_scope":
        return InsufficientScopeError
    if status >= 500:
        return ServerError
    return {
        400: BadRequestError,
        401: AuthenticationError,
        403: PermissionDeniedError,
        404: NotFoundError,
        409: ConflictError,
        410: GoneError,
        422: ValidationError,
        429: RateLimitError,
    }.get(status, BengerAPIError)


def _summarize_validation(errors: list[Any]) -> str:
    parts = []
    for err in errors[:3]:
        if isinstance(err, dict):
            loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
            parts.append(f"{loc}: {err.get('msg', err)}" if loc else str(err.get("msg", err)))
        else:
            parts.append(str(err))
    more = f" (+{len(errors) - 3} more)" if len(errors) > 3 else ""
    return "; ".join(parts) + more if parts else "Validation failed"


def parse_error_body(status: int, body: Any) -> tuple[str, str, str | None, dict[str, Any]]:
    """``(code, message, request_id, details)`` from a decoded error body."""
    default_code = _DEFAULT_CODES.get(status, "server_error" if status >= 500 else "error")
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        details = err.get("details")
        return (
            str(err.get("code") or default_code),
            str(err.get("message") or ""),
            err.get("request_id"),
            dict(details) if isinstance(details, dict) else {},
        )
    if isinstance(body, dict) and "detail" in body:
        detail = body["detail"]
        if isinstance(detail, dict):
            extra = {k: v for k, v in detail.items() if k not in ("code", "message", "request_id")}
            nested = extra.pop("details", None)
            if isinstance(nested, dict):
                extra = {**nested, **extra}
            message = detail.get("message")
            if message is None:
                message = detail.get("error") or detail.get("msg") or str(detail)
            return (
                str(detail.get("code") or default_code),
                str(message),
                detail.get("request_id"),
                extra,
            )
        if isinstance(detail, list):
            return ("validation_error", _summarize_validation(detail), None, {"errors": detail})
        return (default_code, str(detail), None, {})
    if isinstance(body, str) and body.strip():
        return (default_code, body.strip()[:500], None, {})
    return (default_code, f"HTTP {status}", None, {})


def error_from_response(response: httpx.Response) -> BengerAPIError:
    """Build the matching :class:`BengerAPIError` subclass for ``response``."""
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    code, message, request_id, details = parse_error_body(response.status_code, body)
    request_id = request_id or response.headers.get("X-Request-ID")
    request = response.request if _has_request(response) else None
    cls = _class_for(response.status_code, code)
    return cls(
        response.status_code,
        code,
        message,
        request_id,
        details,
        method=request.method if request is not None else None,
        url=str(request.url.copy_with(query=None)) if request is not None else None,
        response=response,
    )


def _has_request(response: httpx.Response) -> bool:
    try:
        response.request  # noqa: B018 - raises RuntimeError when unset
    except RuntimeError:
        return False
    return True
