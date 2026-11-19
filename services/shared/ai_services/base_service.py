"""
Base AI Service class with common functionality for all AI service integrations.
"""

import asyncio
import logging
import re
import socket
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Phase 6.6: academic-rigor metadata. Centralized helpers so each
# provider populates the four fields (seed/refusal/truncated/error_type)
# the same way and a researcher can compare runs across providers.
TRUNCATED_FINISH_REASONS = frozenset({
    "length",          # OpenAI / Cohere / Mistral
    "max_tokens",      # Anthropic
    "MAX_TOKENS",      # Google (genai SDK uppercases enum names)
})


def derive_truncated(finish_reason: Optional[str]) -> bool:
    """True if the model stopped because it hit the output-token limit."""
    if not finish_reason:
        return False
    return finish_reason in TRUNCATED_FINISH_REASONS


# Content-policy / safety refusal finish_reasons. Conservative: only the
# documented content-filter signals, so a normal/length/stop response is never
# mislabelled a refusal. OpenAI + Anthropic expose a dedicated ``refusal`` field
# (handled in those services); Google uses a ``SAFETY`` finish_reason (handled in
# google_service). The OpenAI-compatible providers (Grok, DeepInfra) and Cohere
# only surface it via finish_reason, so derive_refusal maps those.
REFUSAL_FINISH_REASONS = frozenset({
    "content_filter",   # OpenAI-compatible (Grok / DeepInfra) content-policy block
    "ERROR_TOXIC",      # Cohere content-policy block
})


def derive_refusal(finish_reason: Optional[str]) -> bool:
    """True if the model DECLINED for content-policy/safety reasons.

    A refusal is distinct from a normal stop or a length truncation: no real
    answer was produced because a safety filter fired. For an academic benchmark
    this matters — a refusal silently scored as a real answer biases the result.
    """
    if not finish_reason:
        return False
    return finish_reason in REFUSAL_FINISH_REASONS


def classify_error_type(exc: BaseException) -> str:
    """Classify a provider-call exception into the error_type enum.

    Returns one of: ``rate_limit``, ``timeout``, ``auth``,
    ``content_filter``, ``context_length``, ``parse_error``, ``api_error``.

    The mapping is intentionally string-matching on the exception name +
    message so the same classifier works across SDKs (openai, anthropic,
    google.genai, cohere, mistralai, …) without pulling each SDK's
    exception types into this base module.
    """
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()

    # Rate limits
    if "ratelimit" in name or "rate_limit" in name:
        return "rate_limit"
    if "429" in msg or "rate limit" in msg or "rate_limit" in msg or "quota" in msg:
        return "rate_limit"

    # Timeouts
    if "timeout" in name or "timeout" in msg or "timed out" in msg:
        return "timeout"

    # Auth / permissions
    if "auth" in name or "permission" in name or "forbidden" in name:
        return "auth"
    if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg or "invalid api key" in msg:
        return "auth"

    # Content filter / safety
    if "contentfilter" in name or "content_filter" in name or "moderation" in name or "safety" in name:
        return "content_filter"
    if "content filter" in msg or "content policy" in msg or "safety" in msg or "blocked" in msg:
        return "content_filter"

    # Context length
    if "context" in msg and ("length" in msg or "window" in msg or "exceed" in msg):
        return "context_length"
    if "maximum context" in msg or "token limit" in msg:
        return "context_length"

    # JSON parse / structured output
    if "json" in name or "parse" in name or "validation" in name:
        return "parse_error"
    if "json" in msg or "could not parse" in msg or "validation" in msg:
        return "parse_error"

    return "api_error"


def continuation_turns(kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Conversation turns a caller asks to send after the first user prompt.

    ``generate(..., continuation=[{"role": "assistant", "content": ...},
    {"role": "user", "content": ...}])`` continues the conversation of the
    system prompt and the user prompt, which is how a format retry re-asks in
    the same conversation. Only ``user`` and ``assistant`` turns are kept;
    each provider maps the roles onto its own message format.
    """
    turns = kwargs.get("continuation") or []
    return [
        {"role": turn["role"], "content": turn.get("content") or ""}
        for turn in turns
        if isinstance(turn, dict) and turn.get("role") in ("user", "assistant")
    ]


class RetryableUpstreamError(Exception):
    """Transient upstream failure (HTTP 429/5xx). The async retry decorator
    backs off and re-attempts these; other exceptions fail fast."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _is_dns_resolution_error(exc: BaseException) -> bool:
    """True when ``exc`` is a failed host lookup: aiohttp's
    ClientConnectorDNSError, or any error whose ``os_error`` or cause chain
    holds a ``socket.gaierror`` (the OpenAI-style SDKs raise their connection
    error ``from`` the httpx error, so the chain reaches the gaierror)."""
    try:
        import aiohttp as _aiohttp

        if isinstance(exc, _aiohttp.ClientConnectorDNSError):
            return True
    except ImportError:  # pragma: no cover
        pass
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, socket.gaierror):
            return True
        if isinstance(getattr(current, "os_error", None), socket.gaierror):
            return True
        current = current.__cause__ or current.__context__
    return False


def is_transient_upstream_error(exc: BaseException) -> bool:
    """Transient errors worth re-attempting: typed 429/5xx raises from our
    HTTP paths, timeouts, and connection-layer failures. Everything else
    (auth, other 4xx, SSRF-guard rejections, bugs) fails fast.

    A host that does not resolve fails fast too: it is almost always a
    misconfigured endpoint, and backing off five times only delays the
    failure by minutes. The caller's own job-level retry still covers a
    resolver that was briefly down.

    This is the rule the DeepInfra / Custom endpoint retry decorator backs
    off on, with :func:`classify_retryable` as a veto. That classifier
    builds the uniform ``metadata.retryable`` flag of every provider on top
    of it."""
    if isinstance(exc, RetryableUpstreamError):
        return True
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if _is_dns_resolution_error(exc):
        return False
    try:
        # Import the REAL aiohttp here: tests replace the DeepInfra module's
        # ``aiohttp`` binding with a fake, which isinstance() can't take.
        import aiohttp as _aiohttp

        if isinstance(exc, _aiohttp.ClientConnectionError):
            return True
    except ImportError:  # pragma: no cover
        pass
    # Legacy substring fallback (untyped raise sites, foreign callers).
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


# Error codes that mark an exhausted quota or billing limit. The provider
# answers them with HTTP 429 like a plain rate limit, but waiting does not
# help: the account has to be topped up or its limit raised. OpenAI names it
# in the error code, and so do the OpenAI-compatible APIs behind DeepInfra and
# custom endpoints, whose error text keeps the response body. Anthropic and
# Cohere answer billing problems with a 4xx other than 429, which is
# non-retryable anyway. Google's RESOURCE_EXHAUSTED and Mistral's 429 carry no
# such code, and Grok's client drops the body, so there an exhausted quota
# cannot be told from a per-minute limit and stays retryable.
EXHAUSTED_QUOTA_MARKERS = ("insufficient_quota", "billing_hard_limit_reached")

# Statuses the official SDKs themselves retry: request timeout, conflict
# (lock contention) and rate limit; every 5xx is retryable as well.
RETRYABLE_HTTP_STATUSES = frozenset({408, 409, 429})

# Error types in the body of an Anthropic error event that a later attempt
# can get past. A stream that already opened with HTTP 200 reports a mid-stream
# failure only through this type, so the status says nothing about it.
RETRYABLE_PROVIDER_ERROR_TYPES = frozenset(
    {"overloaded_error", "api_error", "rate_limit_error", "timeout_error"}
)

_HTTP_STATUS_PREFIX = re.compile(r"\s*HTTP (\d{3})\b")


def _is_error_status(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 400 <= value <= 599


def _http_status(exc: BaseException) -> Optional[int]:
    """The HTTP error status an SDK or our own HTTP path attached to
    ``exc``: ``status_code`` (OpenAI, Anthropic, Mistral, Cohere, Grok),
    ``code`` (google.genai), ``status`` (RetryableUpstreamError, aiohttp),
    or the ``HTTP <status>:`` prefix of the plain errors the DeepInfra /
    Custom paths raise. Only 4xx and 5xx count: None when the error carries
    no such status, as an SDK error raised mid-stream from a 200 response."""
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if _is_error_status(value):
            return value
    match = _HTTP_STATUS_PREFIX.match(str(exc))
    if match and _is_error_status(int(match.group(1))):
        return int(match.group(1))
    return None


def _provider_error_type(exc: BaseException) -> Optional[str]:
    """The ``error.type`` of an Anthropic-style error body
    (``{"type": "error", "error": {"type": ...}}``), or None."""
    body = getattr(exc, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    error_type = error.get("type") if isinstance(error, dict) else None
    return error_type if isinstance(error_type, str) else None


def _is_exhausted_quota(exc: BaseException) -> bool:
    parts = [str(exc), str(getattr(exc, "code", "") or ""), str(getattr(exc, "body", "") or "")]
    text = " ".join(parts).lower()
    return any(marker in text for marker in EXHAUSTED_QUOTA_MARKERS)


def classify_retryable(exc: BaseException) -> bool:
    """Whether trying the same call again can succeed: the uniform
    ``metadata.retryable`` flag on every provider's error response.

    The rules, first match wins:

    * exhausted quota or billing limit (:data:`EXHAUSTED_QUOTA_MARKERS`)
      -> False, even though the provider sends it as HTTP 429;
    * a host that does not resolve -> False (misconfigured endpoint);
    * an HTTP error status -> True for 408, 409, 429 and 5xx, False for
      every other 4xx (invalid or missing key, unknown model 404, bad
      request, content filter, context length);
    * no error status, but an error body whose ``error.type`` is in
      :data:`RETRYABLE_PROVIDER_ERROR_TYPES` -> True (an Anthropic stream
      that fails after HTTP 200, e.g. a mid-stream ``overloaded_error``);
    * a timeout, a connection failure, a dropped HTTP stream (httpx
      ``NetworkError`` such as ``ReadError``, or ``RemoteProtocolError``,
      raised raw when a stream breaks after HTTP 200) or a
      :class:`RetryableUpstreamError` -> True;
    * no status: the :func:`classify_error_type` class decides, True for
      ``rate_limit``, ``timeout`` and ``parse_error`` (a fresh sample can
      return valid JSON), False for the rest.

    Everything else fails fast, including a missing API key (the services
    raise a plain ValueError), the url_guard rejection of an unreachable or
    private host (``url_guard.UNREACHABLE_HOST_MESSAGE``) and our own bugs.

    Every provider's retry decorator consults it too: the decorator backs
    off only on an error that both its own rule matches and this function
    deems retryable, so an exhausted quota fails on the first attempt.
    """
    if _is_exhausted_quota(exc):
        return False
    if _is_dns_resolution_error(exc):
        return False
    status = _http_status(exc)
    if status is not None:
        return status in RETRYABLE_HTTP_STATUSES or status >= 500
    if _provider_error_type(exc) in RETRYABLE_PROVIDER_ERROR_TYPES:
        return True
    if is_transient_upstream_error(exc):
        return True
    names = [cls.__name__.lower() for cls in type(exc).__mro__]
    if any(
        "timeout" in n or "connection" in n or n in ("networkerror", "remoteprotocolerror")
        for n in names
    ):
        return True
    return classify_error_type(exc) in ("rate_limit", "timeout", "parse_error")


class BaseAIService(ABC):
    """
    Abstract base class for AI service integrations.
    Provides common functionality and interface for all AI services.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the AI service with an API key.

        Args:
            api_key: API key for the service (optional, can be set via environment)
        """
        self.api_key = api_key
        self.client = None
        self._initialize_client()

    @abstractmethod
    def _initialize_client(self):
        """Initialize the service client."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response from the AI service.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: Model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional service-specific parameters

        Returns:
            Dict with response data including content, metadata, and usage stats
        """

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response from the AI service.

        Uses native structured output APIs when available (OpenAI JSON mode,
        Anthropic tool_use, Google JSON mode), falling back to prompt-based
        instructions for providers without native support.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: Model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional service-specific parameters

        Returns:
            Dict with response data. The 'content' field will be a JSON string
            matching the provided schema (when generation is successful).
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement generate_structured()"
        )

    def get_invocation_provenance(self) -> Dict[str, Any]:
        """Phase 6.2 + 6.5: standard audit fields every provider's
        ``response_metadata`` should include so a researcher exporting a
        Generation row can always tell:

        * which retry attempts (if any) preceded the successful call
        * which API key was used (org's vs. user's, fallback path, etc.)
        * which provider name + which user / org context was billed

        Provider services call this helper from their metadata-building
        blocks. The user_aware_ai_service factory stamps the
        ``_key_resolution_route`` / ``_provider_name`` /
        ``_invocation_user_id`` / ``_invocation_organization_id``
        attributes on each freshly-created service instance — direct
        callers (E2E mocks, scripts) get ``None`` values.

        Retry attempts come from a thread-safe contextvar populated by
        the per-provider retry decorator (see :data:`_retry_history_ctx`
        and :func:`get_retry_history_snapshot` above).
        """
        attempts = get_retry_history_snapshot()
        return {
            "retry_attempts": attempts,
            "retry_count": len(attempts),
            "provider_route": getattr(self, "_key_resolution_route", None),
            "provider_name": getattr(self, "_provider_name", None),
            "billed_user_id": getattr(self, "_invocation_user_id", None),
            "billed_organization_id": getattr(
                self, "_invocation_organization_id", None
            ),
        }

    def _create_response_dict(
        self,
        content: str,
        model: str,
        usage: Dict[str, int],
        success: bool = True,
        error: str = None,
        reasoning: Optional[str] = None,
        **additional_data
    ) -> Dict[str, Any]:
        """
        Create a standardized response dictionary.

        Args:
            content: Generated content
            model: Model used
            usage: Token usage statistics
            success: Whether generation was successful
            error: Error message if failed
            reasoning: Reasoning text the provider returned beside the
                answer (see ``ai_services.reasoning``); ``None`` when it
                returned none. Kept apart from ``content``: it is stored
                as research data and never parsed or scored.
            **additional_data: Additional data to include

        Returns:
            Standardized response dictionary
        """
        response = {
            "content": content,
            "reasoning": reasoning,
            "model": model,
            "usage": usage,
            "metadata": {
                "service": self.__class__.__name__.replace("Service", ""),
                "timestamp": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
            },
            "success": success,
        }

        if error:
            response["error"] = error

        # Add any additional data
        response.update(additional_data)

        return response

    def _create_error_response(
        self,
        error: Exception,
        model: str,
        service_name: str = None
    ) -> Dict[str, Any]:
        """
        Create a standardized error response.

        Args:
            error: Exception that occurred
            model: Model that was attempted
            service_name: Name of the service (optional)

        Returns:
            Error response dictionary
        """
        service_name = service_name or self.__class__.__name__.replace("Service", "")
        # Classify on the ORIGINAL exception (name/message signals intact),
        # then scrub the persisted text via the provider hook.
        error_str = self._sanitize_error_text(str(error))
        error_type = classify_error_type(error)

        logger.error(f"❌ {service_name} API Error ({error_type}): {error_str}")

        response = self._create_response_dict(
            content="",
            model=model,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            success=False,
            error=error_str,
        )
        # Phase 6.6: academic-rigor — every failed call also surfaces
        # the four standard fields so downstream persistence sees a
        # consistent shape on success and failure.
        response["metadata"]["error_type"] = error_type
        # Whether the same call can succeed when tried again (see
        # classify_retryable). Callers that repeat a failed generation read
        # this flag instead of guessing from error_type or the message.
        response["metadata"]["retryable"] = classify_retryable(error)
        response["metadata"]["finish_reason"] = None
        response["metadata"]["truncated"] = False
        response["metadata"]["refusal"] = False
        response["metadata"]["seed"] = None
        # Surface retry + provenance on the error path too — usually the
        # most interesting case for a researcher (which retry exhausted).
        response["metadata"].update(self.get_invocation_provenance())
        return response

    def _sanitize_error_text(self, text: str) -> str:
        """Hook: providers may scrub endpoint identifiers from persisted
        error text (``response['error']`` lands in ``generations.error_message``,
        which is exportable). Default: identity — official providers keep
        their errors verbatim."""
        return text

    def _error_response_with_history(
        self,
        error: Exception,
        model: str,
        service_name: str = None,
    ) -> Dict[str, Any]:
        """Build the standard error dict AFTER the retry decorator unwound:
        re-seed the contextvar from the trail the decorator stamped on the
        exception so retry provenance survives its reset."""
        token = _retry_history_ctx.set(
            list(getattr(error, "_retry_history", []) or [])
        )
        try:
            return self._create_error_response(error, model, service_name)
        finally:
            try:
                _retry_history_ctx.reset(token)
            except ValueError:
                # The set() above ran in a different Context than this
                # finally (provider SDKs hop threads/asyncio contexts on
                # error paths). reset() then raises "Token was created in a
                # different Context", masking the ORIGINAL error and killing
                # the caller. Clearing directly is equivalent here.
                _retry_history_ctx.set(None)


# ----------------------------------------------------------------
# Phase 6.2: Per-call retry history (academic-rigor audit trail)
# ----------------------------------------------------------------
#
# All provider services use a `retry_with_exponential_backoff` decorator
# (one duplicated copy each in openai_service / cohere_service /
# mistral_service / deepinfra_service). Each decorator pushes attempt
# records into the contextvar below; each generate() reads it back when
# building response_metadata so consumers see exactly which rate-limit
# failures preceded a successful response. Empty when the call succeeded
# on the first attempt.
import contextvars

_retry_history_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "ai_service_retry_history", default=None
)


def get_retry_history_snapshot() -> list:
    """Snapshot of retry attempts that preceded the current call.

    Returns a *copy* so callers can persist it without depending on the
    contextvar lifecycle (the decorator resets it after the call returns).
    Empty list if no decorator is active (direct calls from tests, etc.).
    """
    history = _retry_history_ctx.get()
    return list(history) if history else []
