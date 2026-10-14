"""Error envelope of the public API.

Every error answered on a ``/api/v1`` path has the shape::

    {"error": {"code": "not_found", "message": "Project not found",
               "request_id": "3f2a...", "details": {}}}

v1 code raises :class:`V1Error`. Errors raised by shared helpers (plain
``HTTPException`` with a string or ``{"code", "message", ...}`` detail) and
request validation errors are re-shaped by the app-level handlers installed
through :func:`install_v1_exception_handlers`; on every other path those
handlers delegate to FastAPI's defaults, so the internal API keeps its
``{"detail": ...}`` contract.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import (
    http_exception_handler as fastapi_http_exception_handler,
    request_validation_exception_handler as fastapi_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

V1_PREFIX = "/api/v1"

#: Fallback ``code`` per status when the raised detail carries none.
STATUS_CODES: Dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    410: "gone",
    412: "precondition_failed",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


class V1Error(HTTPException):
    """An error with a stable machine-readable ``code``.

    ``details`` keyword arguments end up in ``error.details``. Being an
    ``HTTPException``, it also renders sensibly (as ``{"detail": {...}}``)
    in an app without the v1 handlers, such as a bare test app.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        **details: Any,
    ):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, **details},
            headers=headers,
        )
        self.code = code
        self.message = message
        self.details = details


class IdempotentReplay(Exception):
    """Raised by the idempotency dependency to answer with a stored
    response instead of running the handler again."""

    def __init__(self, status_code: int, body: Any):
        super().__init__("idempotent replay")
        self.status_code = status_code
        self.body = body


def is_v1_path(path: Optional[str], root_path: str = "") -> bool:
    if not isinstance(path, str):
        return False
    if root_path and path.startswith(root_path):
        path = path[len(root_path):]
    return path == V1_PREFIX or path.startswith(V1_PREFIX + "/")


def is_v1_request(request: Request) -> bool:
    scope = request.scope
    return is_v1_path(scope.get("path"), scope.get("root_path") or "")


def request_id_of(request: Request) -> Optional[str]:
    """The id the usage middleware assigned (or the caller sent)."""
    state = request.scope.get("state")
    if isinstance(state, dict) and state.get("request_id"):
        return state["request_id"]
    value = request.headers.get("x-request-id")
    return value[:64] if value else None


def error_body(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_of(request),
            "details": jsonable_encoder(details or {}),
        }
    }


def _split_detail(status_code: int, detail: Any):
    """``(code, message, details)`` from whatever a helper put in
    ``HTTPException.detail``."""
    fallback = STATUS_CODES.get(status_code, "error")
    if isinstance(detail, dict):
        rest = {k: v for k, v in detail.items() if k not in ("code", "message")}
        code = detail.get("code") or fallback
        message = detail.get("message") or detail.get("detail") or code.replace("_", " ")
        rest.pop("detail", None)
        return str(code), str(message), rest
    if detail is None or detail == "":
        return fallback, fallback.replace("_", " ").capitalize(), {}
    return fallback, str(detail), {}


async def v1_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if not is_v1_request(request):
        return await fastapi_http_exception_handler(request, exc)
    headers = getattr(exc, "headers", None)
    if exc.status_code in (204, 304):
        return Response(status_code=exc.status_code, headers=headers)
    code, message, details = _split_detail(exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(request, exc.status_code, code, message, details),
        headers=headers,
    )


async def v1_validation_exception_handler(request: Request, exc: RequestValidationError):
    if not is_v1_request(request):
        return await fastapi_validation_exception_handler(request, exc)
    errors = jsonable_encoder(exc.errors())
    for err in errors:
        # Echoing the submitted input back is noise and may carry secrets.
        if isinstance(err, dict):
            err.pop("input", None)
            err.pop("url", None)
    return JSONResponse(
        status_code=422,
        content=error_body(
            request, 422, "validation_error", "The request is invalid", {"errors": errors}
        ),
    )


async def idempotent_replay_handler(request: Request, exc: IdempotentReplay):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.body,
        headers={"Idempotent-Replayed": "true"},
    )


def install_v1_exception_handlers(app: FastAPI) -> None:
    """Register the envelope handlers (v1 paths only, defaults elsewhere)."""
    app.add_exception_handler(StarletteHTTPException, v1_http_exception_handler)
    app.add_exception_handler(RequestValidationError, v1_validation_exception_handler)
    app.add_exception_handler(IdempotentReplay, idempotent_replay_handler)
