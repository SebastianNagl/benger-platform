"""The HTTP core: authentication, retries, idempotency and error mapping."""

from __future__ import annotations

import os
import random
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from typing import Any, TypeVar

import httpx

from ._version import __version__
from .errors import BengerConnectionError, BengerError, error_from_response, parse_retry_after
from .polling import wait_until as _wait_until

__all__ = ["BengerClient", "mask_key", "DEFAULT_BASE_URL"]

DEFAULT_BASE_URL = "https://api.what-a-benger.net"
V1_PREFIX = "/api/v1/"
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
MAX_BACKOFF = 30.0

T = TypeVar("T")


def mask_key(key: str | None) -> str:
    """Return a printable form of an access key: its public prefix only.

    ``bgr_live_k3Yx9Q2a_<secret>`` becomes ``bgr_live_k3Yx9Q2a_***``; anything
    that is not shaped like an access key becomes ``***``.
    """
    if not key:
        return "<none>"
    parts = key.split("_")
    if key.startswith("bgr_") and len(parts) >= 4:
        return "_".join(parts[:3]) + "_***"
    return "***"


class _Secret:
    """Holds the key; ``repr``/``str`` show only the masked prefix."""

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return repr(mask_key(self._value))

    __str__ = __repr__


class BengerClient:
    """Synchronous client for the BenGER API.

    Args:
        api_key: an access key (``bgr_<env>_<id>_<secret>``). Defaults to the
            ``BENGER_API_KEY`` environment variable.
        base_url: deployment root, without ``/api``. Defaults to
            ``BENGER_BASE_URL`` or ``https://api.what-a-benger.net``.
        timeout: per-request timeout in seconds.
        max_retries: how often a request is retried after a 429 (honouring
            ``Retry-After``), and, for GET/HEAD/OPTIONS and v1 POSTs carrying
            an ``Idempotency-Key``, after a 5xx or a connection error.
        backoff_factor: base of the exponential backoff (seconds).
        transport: optional ``httpx`` transport (tests use ``httpx.MockTransport``).
        headers: extra headers sent with every API request.

    Use it as a context manager, or call :meth:`close`. The key is never
    written to ``repr``, logs or exception messages.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        headers: Mapping[str, str] | None = None,
    ):
        key = api_key if api_key is not None else os.environ.get("BENGER_API_KEY")
        if not key or not key.strip():
            raise BengerError(
                "No access key: pass api_key=... or set BENGER_API_KEY "
                "(create a key in your profile or the organisation settings)"
            )
        self._key = _Secret(key.strip())
        root = base_url or os.environ.get("BENGER_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = root.rstrip("/")
        if self.base_url.endswith("/api"):
            self.base_url = self.base_url[: -len("/api")]
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.backoff_factor = backoff_factor
        self._transport = transport
        self._sleep: Callable[[float], None] = time.sleep
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {self._key.reveal()}",
                "Accept": "application/json",
                "User-Agent": f"benger-client/{__version__} httpx/{httpx.__version__}",
                **dict(headers or {}),
            },
        )

        from .resources import (
            Evaluations,
            Exports,
            Generation,
            Imports,
            Models,
            Projects,
            Tasks,
        )

        self.projects = Projects(self)
        self.tasks = Tasks(self)
        self.imports = Imports(self)
        self.models = Models(self)
        self.generation = Generation(self)
        self.evaluations = Evaluations(self)
        self.exports = Exports(self)

    # -- lifecycle -------------------------------------------------------- #

    @property
    def key_prefix(self) -> str:
        """The key's public prefix (``bgr_<env>_<id>_***``), safe to print."""
        return mask_key(self._key.reveal())

    def __repr__(self) -> str:
        return f"BengerClient(base_url={self.base_url!r}, api_key={self.key_prefix!r})"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> BengerClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- requests --------------------------------------------------------- #

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            # Never send the key to another host.
            if not (path == self.base_url or path.startswith(self.base_url + "/")):
                raise BengerError(
                    f"Refusing to send the access key to {httpx.URL(path).host}; "
                    "pass a path such as '/api/projects/'"
                )
            return path[len(self.base_url) :] or "/"
        return path if path.startswith("/") else "/" + path

    def raw_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request with retries and return the ``httpx.Response``.

        Raises :class:`~benger_client.errors.BengerAPIError` (or a subclass)
        for any 4xx/5xx answer. Redirects are not followed.

        POSTs to ``/api/v1/...`` get an ``Idempotency-Key`` automatically
        (one key per call, reused across retries); pass ``idempotency_key``
        to choose it, for example a job name.
        """
        method = method.upper()
        url = self._url(path)
        hdrs = dict(headers or {})
        if params is not None:
            params = {k: v for k, v in params.items() if v is not None}
        if idempotency_key is not None:
            hdrs["Idempotency-Key"] = idempotency_key
        elif method == "POST" and url.startswith(V1_PREFIX):
            if not any(k.lower() == "idempotency-key" for k in hdrs):
                hdrs["Idempotency-Key"] = str(uuid.uuid4())
        replay_safe = method in IDEMPOTENT_METHODS or any(
            k.lower() == "idempotency-key" for k in hdrs
        )

        attempt = 0
        while True:
            try:
                response = self._http.request(
                    method, url, params=params, json=json, headers=hdrs, **kwargs
                )
            except httpx.TransportError as exc:
                if replay_safe and attempt < self.max_retries:
                    self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise BengerConnectionError(f"{method} {url} failed: {exc}") from exc

            status = response.status_code
            if status == 429 and attempt < self.max_retries:
                # Rate limits are enforced before the handler runs, so even a
                # non-idempotent request is safe to resend.
                wait = parse_retry_after(response.headers.get("Retry-After"))
                response.close()
                self._sleep(wait if wait is not None else self._backoff(attempt))
                attempt += 1
                continue
            if status in RETRYABLE_STATUS and replay_safe and attempt < self.max_retries:
                wait = parse_retry_after(response.headers.get("Retry-After"))
                response.close()
                self._sleep(wait if wait is not None else self._backoff(attempt))
                attempt += 1
                continue
            if status >= 400:
                response.read()
                raise error_from_response(response)
            return response

    def _backoff(self, attempt: int) -> float:
        base = self.backoff_factor * (2**attempt)
        return min(MAX_BACKOFF, base + random.uniform(0, self.backoff_factor))

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Call any API route and return the decoded JSON body.

        ``path`` is relative to the deployment root, e.g.
        ``"/api/evaluations/supported-metrics"``. Returns ``None`` for an
        empty body (204), the text for a non-JSON body, and
        ``{"status": 30x, "location": url}`` for a redirect.
        """
        response = self.raw_request(
            method,
            path,
            params=params,
            json=json,
            headers=headers,
            idempotency_key=idempotency_key,
            **kwargs,
        )
        return _decode(response)

    def get(self, path: str, *, params: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        return self.request("GET", path, params=params, **kwargs)

    def post(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return self.request("POST", path, json=json, **kwargs)

    def put(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return self.request("PUT", path, json=json, **kwargs)

    def patch(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return self.request("PATCH", path, json=json, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    # -- v1 helpers ------------------------------------------------------- #

    def me(self) -> dict[str, Any]:
        """``GET /api/v1/me``: the key's principal (scopes, projects, limits) and user."""
        return self.get("/api/v1/me")

    def paginate(
        self, path: str, *, params: Mapping[str, Any] | None = None, limit: int = 100
    ) -> Iterator[Any]:
        """Iterate over every item of a cursor-paginated ``/api/v1`` list."""
        query = dict(params or {})
        query["limit"] = limit
        cursor = None
        while True:
            if cursor:
                query["cursor"] = cursor
            page = self.get(path, params=query)
            yield from page.get("items", [])
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def wait_until(
        self,
        predicate: Callable[[], T],
        *,
        timeout: float = 600.0,
        interval: float = 2.0,
        max_interval: float | None = 30.0,
        description: str = "condition",
    ) -> T:
        """Call ``predicate`` until it returns a truthy value and return it.

        Raises :class:`~benger_client.errors.BengerTimeoutError` after ``timeout``
        seconds. The interval grows by half each round up to ``max_interval``.
        """
        return _wait_until(
            predicate,
            timeout=timeout,
            interval=interval,
            max_interval=max_interval,
            description=description,
            sleep=self._sleep,
        )

    # -- storage (presigned URLs, never with the key) --------------------- #

    def _storage_client(self) -> httpx.Client:
        """A plain client for presigned object-storage URLs (no Authorization)."""
        return httpx.Client(
            timeout=max(self.timeout, 300.0),
            transport=self._transport,
            follow_redirects=True,
        )


def _decode(response: httpx.Response) -> Any:
    if 300 <= response.status_code < 400:
        return {"status": response.status_code, "location": response.headers.get("Location")}
    if response.status_code == 204 or not response.content:
        return None
    ctype = response.headers.get("Content-Type", "")
    if "json" in ctype:
        return response.json()
    try:
        return response.json()
    except ValueError:
        return response.text
