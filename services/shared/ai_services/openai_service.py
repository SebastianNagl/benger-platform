"""
Shared OpenAI service implementation.
"""

import logging
import os
import random
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

from openai import OpenAI

from .base_service import BaseAIService

logger = logging.getLogger(__name__)


# Phase 6.2: shared retry-history contextvar lives in base_service so
# all providers (openai/cohere/mistral/deepinfra) push to the same
# audit-trail buffer.
from .base_service import _retry_history_ctx, get_retry_history_snapshot  # noqa: E402,F401


def retry_with_exponential_backoff(
    max_retries: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True
):
    """
    Decorator for exponential backoff retry on rate limit errors.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential growth
        jitter: Add randomness to prevent thundering herd

    Records each rate-limited attempt in :data:`_retry_history_ctx` so
    the wrapped function's response-builder can include the audit trail
    in its response_metadata.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            history: list = []
            token = _retry_history_ctx.set(history)
            try:
                retries = 0
                while True:
                    attempt_start = time.time()
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        error_str = str(e).lower()
                        is_rate_limit = "429" in error_str or "rate limit" in error_str
                        attempt_ms = int((time.time() - attempt_start) * 1000)
                        history.append({
                            "attempt": retries + 1,
                            "error": str(e)[:200],
                            "is_rate_limit": is_rate_limit,
                            "latency_ms": attempt_ms,
                            "retried": is_rate_limit and retries < max_retries,
                        })

                        if not is_rate_limit or retries >= max_retries:
                            raise

                        delay = min(base_delay * (exponential_base ** retries), max_delay)
                        if jitter:
                            delay = delay * (0.5 + random.random())

                        logger.warning(
                            f"⏳ Rate limit hit, retry {retries + 1}/{max_retries} in {delay:.1f}s"
                        )
                        time.sleep(delay)
                        retries += 1
            finally:
                _retry_history_ctx.reset(token)
        return wrapper
    return decorator


# Local alias kept for backward compat with downstream call sites in
# this file; the canonical implementation lives in base_service.
_get_retry_history_snapshot = get_retry_history_snapshot


class OpenAIService(BaseAIService):
    """Service for handling OpenAI API interactions"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenAI service.
        
        Args:
            api_key: OpenAI API key (optional, defaults to OPENAI_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        super().__init__(self.api_key)

    def _initialize_client(self):
        """Initialize the OpenAI client."""
        if not self.api_key:
            logger.debug(
                "Global OPENAI_API_KEY not set - will use user-specific keys"
            )
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=self.api_key)
                logger.info("✅ OpenAI client initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize OpenAI client: {e}")
                self.client = None

    def is_available(self) -> bool:
        """Check if OpenAI service is available (API key set)"""
        return self.client is not None

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "gpt-4",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response using OpenAI API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: OpenAI model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional parameters

        Returns:
            Dict with response data including content, metadata, and usage stats
        """
        # E2E Test Mode: Return mock response
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(f"🧪 E2E Test Mode: Returning mock response for {model_name}")
            return self._create_response_dict(
                content="Mock LLM response for E2E testing. This is a simulated answer generated during automated testing.",
                model=model_name,
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 100,
                    "finish_reason": "stop",
                    "created_at": datetime.now().isoformat(),
                    "e2e_test_mode": True,
                },
                success=True,
                error=None,
            )

        if not self.is_available():
            raise ValueError("OpenAI service is not available - check OPENAI_API_KEY configuration")

        try:
            start_time = datetime.now()

            # GPT-5 models use max_completion_tokens instead of max_tokens
            # Check if model is GPT-5 (any variant)
            model_lower = model_name.lower()
            is_gpt5 = "gpt-5" in model_lower

            # Check if model is o-series (reasoning models)
            is_o_series = any(model_lower.startswith(prefix) for prefix in ["o1", "o3", "o4"])

            # Build API call parameters
            api_params = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "top_p": 1.0,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "seed": 42,  # Add seed for maximum determinism
            }

            # o-series and GPT-5 models require temperature=1 (API rejects other values).
            # Record BOTH the user-requested value and the value we actually
            # sent to the API so a researcher exporting data can tell whether
            # determinism (temperature=0) was honored or coerced. Phase 6.1.
            requested_temperature = temperature
            temperature_coerced = False
            if is_o_series or is_gpt5:
                api_params["temperature"] = 1.0
                if temperature != 1.0:
                    logger.info(
                        f"Overriding temperature={temperature} -> 1.0 for "
                        f"{model_name} (required by API)"
                    )
                    temperature_coerced = True
            else:
                api_params["temperature"] = temperature
            actual_temperature = api_params["temperature"]

            # GPT-5 models don't support these parameters. Track which ones
            # we silently dropped so the audit trail is complete (Phase 6.1).
            unsupported_dropped: list[str] = []
            if is_gpt5:
                for unsupported in ["top_p", "frequency_penalty", "presence_penalty", "seed"]:
                    if unsupported in api_params:
                        api_params.pop(unsupported)
                        unsupported_dropped.append(unsupported)

            # GPT-5 and o-series use max_completion_tokens, older models use max_tokens
            if is_gpt5 or is_o_series:
                api_params["max_completion_tokens"] = max_tokens
            else:
                api_params["max_tokens"] = max_tokens

            # Add reasoning_effort for o-series models (o1, o3, o3-mini, o4-mini)
            reasoning_effort = kwargs.get("reasoning_effort")
            if is_o_series and reasoning_effort:
                # Validate reasoning_effort value
                valid_efforts = ["low", "medium", "high"]
                if reasoning_effort in valid_efforts:
                    api_params["reasoning_effort"] = reasoning_effort
                    logger.info(f"🧠 Using reasoning_effort={reasoning_effort} for {model_name}")

            # Make OpenAI API call with deterministic settings
            response = self.client.chat.completions.create(**api_params)

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response data
            message = response.choices[0].message
            content = message.content.strip() if message.content else ""

            # Log the generation
            logger.info(f"🤖 OpenAI Generation: {model_name}")
            logger.info(
                f"📊 Usage: {response.usage.prompt_tokens} prompt + "
                f"{response.usage.completion_tokens} completion = "
                f"{response.usage.total_tokens} total tokens"
            )
            logger.info(f"⏱️ Response time: {response_time_ms}ms")

            return self._create_response_dict(
                content=content,
                model=model_name,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                metadata={
                    # Legacy field — still echoes the actual value sent to
                    # the API so existing consumers don't break. Researchers
                    # comparing runs should rely on requested_/actual_ pairs.
                    "temperature": actual_temperature,
                    "requested_temperature": requested_temperature,
                    "actual_temperature": actual_temperature,
                    "temperature_coerced": temperature_coerced,
                    "max_tokens": max_tokens,
                    "response_time_ms": response_time_ms,
                    "finish_reason": response.choices[0].finish_reason,
                    "created_at": end_time.isoformat(),
                    "unsupported_params_dropped": unsupported_dropped,
                    "is_gpt5_series": is_gpt5,
                    "is_o_series": is_o_series,
                    # Phase 6.2: per-call retry history. Empty when the
                    # call succeeded on the first attempt; non-empty
                    # entries each record one rate-limit retry that
                    # preceded the success.
                    "retry_attempts": _get_retry_history_snapshot(),
                    "retry_count": len(_get_retry_history_snapshot()),
                    # Phase 6.5: stamped by user_aware_ai_service when
                    # the service was created. None for direct/standalone
                    # service instances (E2E mocks, scripts).
                    "provider_route": getattr(self, "_key_resolution_route", None),
                    "provider_name": getattr(self, "_provider_name", "openai"),
                    "billed_user_id": getattr(self, "_invocation_user_id", None),
                    "billed_organization_id": getattr(
                        self, "_invocation_organization_id", None
                    ),
                },
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "OpenAI")

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "gpt-4",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response using OpenAI's native structured output.

        Uses response_format with json_schema for guaranteed valid JSON output.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: OpenAI model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)

        Returns:
            Dict with response data. The 'content' field will be a JSON string.
        """
        import json

        # E2E Test Mode: Return mock structured response
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(f"🧪 E2E Test Mode: Returning mock structured response for {model_name}")
            # Generate mock response based on schema
            mock_response = {}
            for field_name, field_schema in json_schema.get("properties", {}).items():
                if field_schema.get("enum"):
                    mock_response[field_name] = field_schema["enum"][0]
                elif field_schema.get("type") == "integer":
                    mock_response[field_name] = field_schema.get("minimum", 1)
                elif field_schema.get("type") == "number":
                    mock_response[field_name] = 0.0
                else:
                    mock_response[field_name] = "Mock E2E test answer"
            return self._create_response_dict(
                content=json.dumps(mock_response, ensure_ascii=False),
                model=model_name,
                usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 100,
                    "structured_output": True,
                    "e2e_test_mode": True,
                },
                success=True,
            )

        if not self.is_available():
            raise ValueError("OpenAI service is not available - check OPENAI_API_KEY configuration")

        # Models that support json_schema structured output
        STRUCTURED_OUTPUT_MODELS = [
            "gpt-4o", "gpt-4o-mini", "gpt-4o-2024",
            "gpt-4-turbo", "gpt-4-turbo-preview",
            "gpt-4-0125-preview", "gpt-4-1106-preview",
            "gpt-4.1", "gpt-5", "o1", "o3", "o4-mini",
        ]

        # Check if model supports json_schema (check prefix match)
        model_lower = model_name.lower()
        supports_json_schema = any(
            model_lower.startswith(supported.lower())
            for supported in STRUCTURED_OUTPUT_MODELS
        )

        if not supports_json_schema:
            logger.info(f"⚠️ Model {model_name} doesn't support json_schema, using prompt-based JSON")
            # Fall back to prompt-based JSON generation
            format_instructions = f"""

## Output Format
You MUST respond with a valid JSON object matching this schema:
{json.dumps(json_schema, indent=2)}

Your response must be ONLY the JSON object, no other text before or after.
"""
            enhanced_system_prompt = system_prompt + format_instructions
            return self.generate(
                prompt=prompt,
                system_prompt=enhanced_system_prompt,
                model_name=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

        try:
            start_time = datetime.now()

            model_lower = model_name.lower()
            is_gpt5 = "gpt-5" in model_lower
            is_o_series = any(model_lower.startswith(p) for p in ["o1", "o3", "o4"])

            # o-series and GPT-5 models require temperature=1 (API rejects other values)
            effective_temperature = temperature
            if is_o_series or is_gpt5:
                effective_temperature = 1.0
                if temperature != 1.0:
                    logger.info(f"Overriding temperature={temperature} -> 1.0 for {model_name} (required by API)")

            api_params = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": effective_temperature,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "annotation_response",
                        "schema": json_schema,
                        "strict": True
                    }
                }
            }

            # Only add these params for non-GPT-5 models
            if not is_gpt5:
                api_params["top_p"] = 1.0
                api_params["frequency_penalty"] = 0.0
                api_params["presence_penalty"] = 0.0
                api_params["seed"] = 42

            if is_gpt5 or is_o_series:
                api_params["max_completion_tokens"] = max_tokens
            else:
                api_params["max_tokens"] = max_tokens

            response = self.client.chat.completions.create(**api_params)

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            message = response.choices[0].message
            content = message.content.strip() if message.content else ""

            logger.info(f"🤖 OpenAI Structured Generation: {model_name}")
            logger.info(
                f"📊 Usage: {response.usage.prompt_tokens} prompt + "
                f"{response.usage.completion_tokens} completion = "
                f"{response.usage.total_tokens} total tokens"
            )
            logger.info(f"⏱️ Response time: {response_time_ms}ms")

            return self._create_response_dict(
                content=content,
                model=model_name,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": response_time_ms,
                    "finish_reason": response.choices[0].finish_reason,
                    "structured_output": True,
                    "created_at": end_time.isoformat(),
                },
                success=True,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "OpenAI")

    async def generate_response(
        self,
        system_prompt: str,
        instruction_prompt: str,
        case_data: str,
        model_name: str = "gpt-4",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Legacy method for backward compatibility.
        Generate a response using OpenAI API with case data replacement.
        
        Args:
            system_prompt: System message for context
            instruction_prompt: Specific instruction with placeholders
            case_data: The case data to insert into instruction
            model_name: OpenAI model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional parameters
            
        Returns:
            Dict with response data including content, metadata, and usage stats
        """
        # Replace placeholder in instruction with actual case data
        user_message = instruction_prompt.replace("[FALL EINFÜGEN]", case_data)
        
        # Use the base generate method
        return self.generate(
            prompt=user_message,
            system_prompt=system_prompt,
            model_name=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )


# Global service instance for backward compatibility
openai_service = OpenAIService()