"""
Base AI Service class with common functionality for all AI service integrations.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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
        pass

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
        pass

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
        error_str = str(error)
        
        logger.error(f"❌ {service_name} API Error: {error_str}")
        
        return self._create_response_dict(
            content="",
            model=model,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            success=False,
            error=error_str
        )

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

