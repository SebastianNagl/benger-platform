"""
Base AI Service class with common functionality for all AI service integrations.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

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


class RetryableUpstreamError(Exception):
    """Transient upstream failure (HTTP 429/5xx). The async retry decorator
    backs off and re-attempts these; other exceptions fail fast."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


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
            **additional_data: Additional data to include

        Returns:
            Standardized response dictionary
        """
        response = {
            "content": content,
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
            _retry_history_ctx.reset(token)


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
