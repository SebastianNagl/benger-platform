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

from .base_service import BaseAIService, derive_truncated
from .provider_capabilities import model_supports_seed

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

    @staticmethod
    def _is_responses_api_only_model(model_name: str) -> bool:
        """OpenAI's `*-pro` reasoning tiers (gpt-5-pro, gpt-5.5-pro,
        o3-pro, o4-pro, …) are exposed only via the `/v1/responses`
        endpoint; calling them on `/v1/chat/completions` returns
        `404 — not a chat model`. The base reasoning models (o3, o3-mini,
        o4-mini) and the standard GPT-5 family work on chat-completions
        and stay on that path.
        """
        m = model_name.lower()
        if not m.endswith("-pro"):
            return False
        return m.startswith(("gpt-5", "o1", "o3", "o4"))

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
        # Phase 6.6: caller may override the deterministic seed (default 42)
        # for variance studies. Pulled from kwargs so existing call sites
        # that don't pass anything keep getting the same seed they always
        # got. GPT-5 silently drops it; we record what was *requested*
        # alongside what was actually sent.
        requested_seed = kwargs.get("seed", 42)

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
                    "truncated": False,
                    "refusal": False,
                    "error_type": None,
                    "seed": requested_seed,
                    "created_at": datetime.now().isoformat(),
                    "e2e_test_mode": True,
                },
                success=True,
                error=None,
            )

        if not self.is_available():
            raise ValueError("OpenAI service is not available - check OPENAI_API_KEY configuration")

        # `*-pro` reasoning tiers are only reachable via `/v1/responses`;
        # the chat-completions endpoint returns "not a chat model" for them.
        if self._is_responses_api_only_model(model_name):
            return self._generate_via_responses_api(
                prompt=prompt,
                system_prompt=system_prompt,
                model_name=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                requested_seed=requested_seed,
                **kwargs,
            )

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
            }
            # Phase 6.6 (#7): only forward seed when this specific model
            # accepts it. Per-model overrides in llm_models.yaml
            # (`constraints.seed.supported`) win over the provider-level
            # default. ``supports_seed_here`` is also written into the
            # response metadata below so consumers can tell when a
            # requested seed was *not* honored.
            supports_seed_here = model_supports_seed("openai", model_name)
            if supports_seed_here:
                api_params["seed"] = requested_seed

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

            finish_reason = response.choices[0].finish_reason
            # OpenAI surfaces safety refusals via message.refusal (gpt-4o+).
            refusal = bool(getattr(message, "refusal", None))
            # The seed actually sent reflects (a) per-model support and
            # (b) GPT-5's silent drop. If neither honored it, record None.
            if not supports_seed_here or "seed" in unsupported_dropped:
                seed_in_metadata = None
            else:
                seed_in_metadata = requested_seed

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
                    "finish_reason": finish_reason,
                    # Phase 6.6: academic-rigor standard fields.
                    "seed": seed_in_metadata,
                    "refusal": refusal,
                    "truncated": derive_truncated(finish_reason),
                    "error_type": None,
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

    def _generate_via_responses_api(
        self,
        prompt: str,
        system_prompt: str,
        model_name: str,
        max_tokens: int,
        temperature: float,
        requested_seed: int,
        **kwargs,
    ) -> Dict[str, Any]:
        """Call OpenAI's `/v1/responses` endpoint for `*-pro` reasoning models.

        These models reject chat-completions; the responses API takes
        `input` (instead of `messages`) and `max_output_tokens` (instead
        of `max_completion_tokens`). System prompt is conveyed via the
        `instructions` parameter so it doesn't compete with reasoning
        budget for output tokens.

        Output mapping keeps the same response-dict shape downstream
        consumers expect: `content`, `usage` (with the legacy
        `prompt_tokens`/`completion_tokens` aliases), and the same
        metadata fields the chat-completions path produces.
        """
        try:
            start_time = datetime.now()

            api_params: Dict[str, Any] = {
                "model": model_name,
                "input": prompt,
                # max_output_tokens caps the *visible* answer; reasoning
                # tokens are billed separately and don't count toward it.
                "max_output_tokens": max_tokens,
            }
            if system_prompt:
                api_params["instructions"] = system_prompt

            # `*-pro` tiers enforce temperature=1.0 like every other
            # GPT-5/o-series model. Record the coercion the same way so
            # researchers exporting data see consistent fields.
            requested_temperature = temperature
            api_params["temperature"] = 1.0
            temperature_coerced = temperature != 1.0
            if temperature_coerced:
                logger.info(
                    f"Overriding temperature={temperature} -> 1.0 for "
                    f"{model_name} (Responses API enforces 1.0 for *-pro)"
                )

            reasoning_effort = kwargs.get("reasoning_effort")
            if reasoning_effort in ("low", "medium", "high"):
                api_params["reasoning"] = {"effort": reasoning_effort}
                logger.info(f"🧠 Using reasoning.effort={reasoning_effort} for {model_name}")

            # `*-pro` models silently ignore seed/top_p/etc. so we don't
            # send them. Track which of the requested params were dropped
            # so the audit trail mirrors the chat-completions path.
            unsupported_dropped = ["top_p", "frequency_penalty", "presence_penalty", "seed"]

            response = self.client.responses.create(**api_params)

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # `output_text` is the SDK's convenience accessor that joins
            # all visible message-content text items, skipping the hidden
            # reasoning items. Empty string means a refusal or truncation.
            content = (response.output_text or "").strip()

            # Responses-API usage uses input_tokens/output_tokens; map to
            # legacy keys so downstream cost/aggregation code keeps working.
            usage = response.usage
            prompt_tokens = getattr(usage, "input_tokens", 0)
            completion_tokens = getattr(usage, "output_tokens", 0)
            total_tokens = getattr(
                usage, "total_tokens", prompt_tokens + completion_tokens
            )

            # Finish reason: responses-API emits status='completed' or
            # status='incomplete' on the response itself; per-item
            # reasons (length, content_filter, refusal) live on the last
            # output item. Prefer the item-level reason when present.
            status = getattr(response, "status", None)
            finish_reason: Optional[str] = None
            refusal = False
            if response.output:
                last = response.output[-1]
                finish_reason = getattr(last, "stop_reason", None) or getattr(
                    last, "finish_reason", None
                )
                refusal = bool(getattr(last, "refusal", None))
            if not finish_reason:
                # Fall back to response-level status — `incomplete` with
                # `incomplete_details.reason == "max_output_tokens"` is
                # the common truncation signal on this endpoint.
                if status == "incomplete":
                    details = getattr(response, "incomplete_details", None)
                    finish_reason = getattr(details, "reason", "incomplete")
                else:
                    finish_reason = status

            logger.info(f"🤖 OpenAI Responses-API Generation: {model_name}")
            logger.info(
                f"📊 Usage: {prompt_tokens} prompt + {completion_tokens} completion = "
                f"{total_tokens} total tokens"
            )
            logger.info(f"⏱️ Response time: {response_time_ms}ms")

            return self._create_response_dict(
                content=content,
                model=model_name,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
                metadata={
                    "temperature": api_params["temperature"],
                    "requested_temperature": requested_temperature,
                    "actual_temperature": api_params["temperature"],
                    "temperature_coerced": temperature_coerced,
                    "max_tokens": max_tokens,
                    "response_time_ms": response_time_ms,
                    "finish_reason": finish_reason,
                    "seed": None,  # *-pro tiers don't honor seed
                    "refusal": refusal,
                    "truncated": derive_truncated(finish_reason),
                    "error_type": None,
                    "created_at": end_time.isoformat(),
                    "unsupported_params_dropped": unsupported_dropped,
                    "is_gpt5_series": "gpt-5" in model_name.lower(),
                    "is_o_series": any(
                        model_name.lower().startswith(p) for p in ("o1", "o3", "o4")
                    ),
                    "api_endpoint": "responses",
                    "retry_attempts": _get_retry_history_snapshot(),
                    "retry_count": len(_get_retry_history_snapshot()),
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

        requested_seed = kwargs.get("seed", 42)

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
                    "finish_reason": "stop",
                    "truncated": False,
                    "refusal": False,
                    "error_type": None,
                    "seed": requested_seed,
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
            format_instructions = """

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

            # Only add these params for non-GPT-5 models. Phase 6.6 (#7):
            # also gate seed on per-model support.
            supports_seed_here = model_supports_seed("openai", model_name)
            seed_in_metadata = requested_seed if supports_seed_here else None
            if not is_gpt5:
                api_params["top_p"] = 1.0
                api_params["frequency_penalty"] = 0.0
                api_params["presence_penalty"] = 0.0
                if supports_seed_here:
                    api_params["seed"] = requested_seed
            else:
                # GPT-5 silently drops seed; record None so the persisted
                # row reflects what actually happened.
                seed_in_metadata = None

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

            finish_reason = response.choices[0].finish_reason
            refusal = bool(getattr(message, "refusal", None))

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
                    "finish_reason": finish_reason,
                    "seed": seed_in_metadata,
                    "refusal": refusal,
                    "truncated": derive_truncated(finish_reason),
                    "error_type": None,
                    "structured_output": True,
                    "created_at": end_time.isoformat(),
                    "retry_attempts": _get_retry_history_snapshot(),
                    "retry_count": len(_get_retry_history_snapshot()),
                    "provider_route": getattr(self, "_key_resolution_route", None),
                    "provider_name": getattr(self, "_provider_name", "openai"),
                    "billed_user_id": getattr(self, "_invocation_user_id", None),
                    "billed_organization_id": getattr(
                        self, "_invocation_organization_id", None
                    ),
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