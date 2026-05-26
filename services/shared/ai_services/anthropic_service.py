"""
Shared Anthropic service implementation.
"""

import logging
import os
import random
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

import anthropic

from .base_service import BaseAIService, derive_truncated
from .provider_capabilities import calculate_cost

logger = logging.getLogger(__name__)


def retry_with_exponential_backoff(
    max_retries: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True
):
    """Decorator for exponential backoff retry on rate limit errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    is_rate_limit = "429" in error_str or "rate limit" in error_str or "overloaded" in error_str

                    if not is_rate_limit or retries >= max_retries:
                        raise

                    delay = min(base_delay * (exponential_base ** retries), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(f"⏳ Rate limit hit, retry {retries + 1}/{max_retries} in {delay:.1f}s")
                    time.sleep(delay)
                    retries += 1
        return wrapper
    return decorator


class AnthropicService(BaseAIService):
    """Service for handling Anthropic Claude API interactions"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Anthropic service.

        Args:
            api_key: Anthropic API key (optional, defaults to ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        super().__init__(self.api_key)

    def _initialize_client(self):
        """Initialize the Anthropic client."""
        if not self.api_key or self.api_key == "your-anthropic-api-key-here":
            logger.debug(
                "Global ANTHROPIC_API_KEY not set - will use user-specific keys"
            )
            self.client = None
        else:
            try:
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info("✅ Anthropic client initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Anthropic client: {e}")
                self.client = None

    def is_available(self) -> bool:
        """Check if Anthropic service is available (API key set)"""
        return self.client != None

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response using Anthropic Claude API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: Claude model to use
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
                content="Mock Claude response for E2E testing. This is a simulated answer generated during automated testing.",
                model=model_name,
                usage={
                    "prompt_tokens": 120,
                    "completion_tokens": 60,
                    "total_tokens": 180,
                },
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 150,
                    "cost_usd": 0.0,
                    "provider": "Anthropic",
                    "finish_reason": "end_turn",
                    "truncated": False,
                    "refusal": False,
                    "error_type": None,
                    # Anthropic API does not accept a seed parameter.
                    "seed": None,
                    "created_at": datetime.now().isoformat(),
                    "e2e_test_mode": True,
                    **self.get_invocation_provenance(),
                },
                success=True,
                error=None,
            )

        if not self.is_available():
            raise ValueError(
                "Anthropic service is not available - check ANTHROPIC_API_KEY configuration"
            )

        try:
            start_time = datetime.now()

            # Build API call parameters
            api_params = {
                "model": model_name,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}],
            }

            # Check if model supports extended thinking (Claude 3.7+, Claude 4+)
            model_lower = model_name.lower()
            supports_thinking = any(prefix in model_lower for prefix in [
                "claude-3-7", "claude-opus-4", "claude-sonnet-4", "claude-haiku-4"
            ])

            # Add thinking budget for supported models
            thinking_budget = kwargs.get("thinking_budget")
            if supports_thinking and thinking_budget:
                api_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": int(thinking_budget)
                }
                logger.info(f"🧠 Using thinking_budget={thinking_budget} for {model_name}")

            # Make Anthropic API call
            response = self.client.messages.create(**api_params)

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response text
            response_text = response.content[0].text if response.content else ""

            # Calculate token usage
            input_tokens = response.usage.input_tokens if hasattr(response, "usage") else 0
            output_tokens = response.usage.output_tokens if hasattr(response, "usage") else 0
            total_tokens = input_tokens + output_tokens

            # Phase 6.6 (#9): cost from llm_models.yaml (single source of
            # truth) instead of a hardcoded Sonnet-3.5 estimate that
            # silently misreports for Opus / Haiku / older snapshots.
            # Falls back to 0.0 if the model isn't in the catalog.
            cost_usd = calculate_cost("anthropic", model_name, input_tokens, output_tokens) or 0.0

            logger.info(f"🤖 Claude Generation: {model_name}")
            logger.info(f"📊 Tokens: {input_tokens} input + {output_tokens} output = {total_tokens}")
            logger.info(f"💰 Cost: ${cost_usd:.4f}")
            logger.info(f"⏱️ Response time: {response_time_ms}ms")

            # Anthropic stop_reason values: end_turn, max_tokens,
            # stop_sequence, tool_use, refusal (Claude 3.5+).
            finish_reason = getattr(response, "stop_reason", None)
            refusal = finish_reason == "refusal"

            return self._create_response_dict(
                content=response_text,
                model=model_name,
                usage={
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": response_time_ms,
                    "cost_usd": cost_usd,
                    "provider": "Anthropic",
                    "finish_reason": finish_reason,
                    "truncated": derive_truncated(finish_reason),
                    "refusal": refusal,
                    "error_type": None,
                    # Anthropic API does not accept a seed parameter.
                    "seed": None,
                    "created_at": end_time.isoformat(),
                    **self.get_invocation_provenance(),
                },
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "Anthropic")

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response by instructing the model to emit
        JSON in its text response, mirroring the OpenAI/Google paths.

        Previously this used Anthropic's tool_use API with forced tool_choice
        and input_schema=json_schema. That path silently broke on deeply nested
        schemas with large outputs: Sonnet 4.6 returned nested object fields as
        JSON-stringified blobs truncated at ~10kB, and Opus 4.7 hit the same
        bug at ~2% rate on long judge prompts. Switching to text-mode JSON
        (system prompt injects the schema as instruction, caller parses the
        text content) avoids the tool_use serialiser's quirks. The Falllösung
        3-stage parser already handles raw JSON, markdown-fenced JSON, and
        brace-matched-JSON-with-preamble.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: Claude model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)

        Returns:
            Dict with response data. The 'content' field is a JSON text string.
        """
        import json

        # E2E Test Mode: Return mock structured response
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(f"🧪 E2E Test Mode: Returning mock structured response for {model_name}")
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
                usage={"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 150,
                    "finish_reason": "end_turn",
                    "truncated": False,
                    "refusal": False,
                    "error_type": None,
                    "seed": None,
                    "structured_output": True,
                    "e2e_test_mode": True,
                    **self.get_invocation_provenance(),
                },
                success=True,
            )

        if not self.is_available():
            raise ValueError("Anthropic service is not available - check ANTHROPIC_API_KEY configuration")

        try:
            start_time = datetime.now()

            # Inject the JSON schema as an instruction onto the system prompt,
            # mirroring google_service.py:_build_json_prompt. Bilingual hint
            # because the Falllösung judge prompt is in German; the parser is
            # robust to either-language preamble that the model might emit.
            schema_text = json.dumps(json_schema, ensure_ascii=False, indent=2)
            enhanced_system = (
                system_prompt
                + "\n\nRespond with ONLY valid JSON (no markdown fences, no "
                  "preamble or trailing text) matching this schema. "
                  "Antworte ausschließlich mit validem JSON nach diesem Schema:\n"
                + schema_text
            )

            response = self.client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=enhanced_system,
                messages=[{"role": "user", "content": prompt}],
            )

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response text (same shape as generate() at line 180)
            content = response.content[0].text if response.content else ""

            input_tokens = response.usage.input_tokens if hasattr(response, "usage") else 0
            output_tokens = response.usage.output_tokens if hasattr(response, "usage") else 0
            total_tokens = input_tokens + output_tokens
            cost_usd = (input_tokens * 0.000003) + (output_tokens * 0.000015)

            logger.info(f"🤖 Claude Structured Generation: {model_name}")
            logger.info(f"📊 Tokens: {input_tokens} input + {output_tokens} output = {total_tokens}")
            logger.info(f"💰 Cost: ${cost_usd:.4f}")
            logger.info(f"⏱️ Response time: {response_time_ms}ms")

            finish_reason = getattr(response, "stop_reason", None)
            refusal = finish_reason == "refusal"

            return self._create_response_dict(
                content=content,
                model=model_name,
                usage={
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": response_time_ms,
                    "cost_usd": cost_usd,
                    "provider": "Anthropic",
                    "finish_reason": finish_reason,
                    "truncated": derive_truncated(finish_reason),
                    "refusal": refusal,
                    "error_type": None,
                    "seed": None,
                    "structured_output": True,
                    "created_at": end_time.isoformat(),
                    **self.get_invocation_provenance(),
                },
                success=True,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "Anthropic")

    async def generate_response(
        self,
        system_prompt: str,
        instruction_prompt: str,
        case_data: str,
        model_name: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Legacy method for backward compatibility.
        Generate a response using Anthropic Claude API with case data.

        Args:
            system_prompt: System-level instructions
            instruction_prompt: Specific task instructions
            case_data: The case/question to analyze
            model_name: Claude model to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional parameters

        Returns:
            Dictionary with response data and metadata
        """
        # Combine prompts for Claude
        user_message = f"{instruction_prompt}\n\nCase to analyze:\n{case_data}"

        # Use the base generate method
        result = self.generate(
            prompt=user_message,
            system_prompt=system_prompt,
            model_name=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        # Map to legacy response format for backward compatibility
        if result["success"]:
            return {
                "response_text": result["content"],
                "model_name": result["model"],
                "prompt_tokens": result["usage"]["prompt_tokens"],
                "completion_tokens": result["usage"]["completion_tokens"],
                "total_tokens": result["usage"]["total_tokens"],
                "cost_usd": result["metadata"].get("cost_usd", 0),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "provider": "Anthropic",
            }
        else:
            raise Exception(result.get("error", "Unknown error"))


# Global instance for backward compatibility
anthropic_service = AnthropicService()
