"""
Shared Grok (xAI) service implementation.

Provides integration with xAI's Grok models including:
- Grok-2, Grok-3, Grok-4
- Support for chat completions and structured output via OpenAI-compatible API
"""

import json
import logging
import os
import random
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

import aiohttp

from .base_service import BaseAIService
from .response_validator import ResponseValidator

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
                    is_rate_limit = "429" in error_str or "rate limit" in error_str

                    if not is_rate_limit or retries >= max_retries:
                        raise

                    delay = min(base_delay * (exponential_base ** retries), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"Rate limit hit, retry {retries + 1}/{max_retries} in {delay:.1f}s"
                    )
                    time.sleep(delay)
                    retries += 1
        return wrapper
    return decorator


class GrokService(BaseAIService):
    """Service for handling xAI Grok API interactions"""

    # Model name mapping from display names to API names
    MODEL_MAPPING = {
        # Grok 4 models
        "Grok 4": "grok-4",
        "Grok 4 Fast": "grok-4-fast",
        "Grok 4.1 Fast": "grok-4-1-fast",
        # Grok 3 models
        "Grok 3": "grok-3",
        "Grok 3 Beta": "grok-3-beta",
        "Grok 3 Mini": "grok-3-mini",
        "Grok 3 Mini Beta": "grok-3-mini-beta",
        # Grok 2 models
        "Grok 2": "grok-2-1212",
        "Grok 2 Vision": "grok-2-vision-1212",
        # Direct model IDs
        "grok-4": "grok-4",
        "grok-4-fast": "grok-4-fast",
        "grok-4-1-fast": "grok-4-1-fast",
        "grok-3": "grok-3",
        "grok-3-beta": "grok-3-beta",
        "grok-3-mini": "grok-3-mini",
        "grok-3-mini-beta": "grok-3-mini-beta",
        "grok-2-1212": "grok-2-1212",
        "grok-2-vision-1212": "grok-2-vision-1212",
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Grok service.

        Args:
            api_key: xAI API key (optional, defaults to XAI_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
        self.base_url = "https://api.x.ai/v1"
        super().__init__(self.api_key)

    def _initialize_client(self):
        """Initialize the xAI Grok client."""
        if not self.api_key:
            logger.debug(
                "Global XAI_API_KEY not set - will use user-specific keys"
            )
            self.client = None
        else:
            # xAI uses OpenAI-compatible API, so we just need the API key
            self.client = True  # Flag to indicate we have API key
            logger.info("Grok client initialized")

    def is_available(self) -> bool:
        """Check if Grok service is available (API key set)"""
        return self.client is not None

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "grok-3",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response using xAI Grok API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: Grok model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional parameters

        Returns:
            Dict with response data including content, metadata, and usage stats
        """
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._generate_async(prompt, system_prompt, model_name, max_tokens, temperature, **kwargs)
            )
        finally:
            loop.close()

    async def _generate_async(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "grok-3",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """Async implementation of generate."""
        # E2E Test Mode: Return mock response
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(f"E2E Test Mode: Returning mock response for {model_name}")
            return self._create_response_dict(
                content="Mock Grok response for E2E testing. This is a simulated answer generated during automated testing.",
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
            raise ValueError("Grok service is not available - check XAI_API_KEY configuration")

        try:
            start_time = datetime.now()

            # Map display name to API model name
            api_model_name = self.MODEL_MAPPING.get(model_name, model_name)

            # Build messages list
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Prepare payload (OpenAI-compatible format)
            payload = {
                "model": api_model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "seed": 42,  # Add seed for maximum determinism
            }

            # Add reasoning_effort for grok-3-mini models
            reasoning_effort = kwargs.get("reasoning_effort")
            if "mini" in model_name.lower() and reasoning_effort:
                valid_efforts = ["low", "high"]
                if reasoning_effort in valid_efforts:
                    payload["reasoning_effort"] = reasoning_effort
                    logger.info(f"Using reasoning_effort={reasoning_effort} for {model_name}")

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Make xAI API call
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:
                    response.raise_for_status()
                    result = await response.json()

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response text
            content = ""
            if result.get("choices") and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"].strip()

            # Get usage stats
            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            logger.info(f"Grok Generation: {model_name}")
            logger.info(
                f"Usage: {prompt_tokens} prompt + "
                f"{completion_tokens} completion = "
                f"{total_tokens} total tokens"
            )
            logger.info(f"Response time: {response_time_ms}ms")

            return self._create_response_dict(
                content=content,
                model=model_name,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": response_time_ms,
                    "finish_reason": result["choices"][0].get("finish_reason", "unknown") if result.get("choices") else "unknown",
                    "created_at": end_time.isoformat(),
                },
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "Grok")

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "grok-3",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response using Grok's OpenAI-compatible API.

        Grok supports JSON mode via the OpenAI-compatible API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: Grok model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)

        Returns:
            Dict with response data. The 'content' field will be a JSON string.
        """
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._generate_structured_async(prompt, system_prompt, json_schema, model_name, max_tokens, temperature, **kwargs)
            )
        finally:
            loop.close()

    async def _generate_structured_async(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "grok-3",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """Async implementation of generate_structured."""
        # E2E Test Mode: Return mock structured response
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(f"E2E Test Mode: Returning mock structured response for {model_name}")
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
            raise ValueError("Grok service is not available - check XAI_API_KEY configuration")

        try:
            start_time = datetime.now()

            # Map display name to API model name
            api_model_name = self.MODEL_MAPPING.get(model_name, model_name)

            # Add format instructions to system prompt
            format_instructions = f"""

## Output Format
You MUST respond with a valid JSON object matching this schema:
{json.dumps(json_schema, indent=2)}

Your response must be ONLY the JSON object, no other text before or after.
"""
            enhanced_system_prompt = system_prompt + format_instructions

            # Build messages list
            messages = []
            if enhanced_system_prompt:
                messages.append({"role": "system", "content": enhanced_system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Prepare payload with JSON mode
            payload = {
                "model": api_model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "seed": 42,  # Add seed for maximum determinism
                "response_format": {"type": "json_object"},
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Make xAI API call
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:
                    response.raise_for_status()
                    result = await response.json()

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response text
            raw_content = ""
            if result.get("choices") and len(result["choices"]) > 0:
                raw_content = result["choices"][0]["message"]["content"].strip()

            # Get usage stats
            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            logger.info(f"Grok Structured Generation: {model_name}")
            logger.info(f"Usage: {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total tokens")
            logger.info(f"Response time: {response_time_ms}ms")

            # Validate and extract JSON using ResponseValidator
            validator = ResponseValidator(strict=True)
            validation_result = validator.validate_response(
                raw_content,
                json_schema,
                attempt_repair=True
            )

            result_metadata = {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_time_ms": response_time_ms,
                "structured_output": True,
                "finish_reason": result["choices"][0].get("finish_reason", "unknown") if result.get("choices") else "unknown",
                "created_at": end_time.isoformat(),
            }

            if validation_result.valid and validation_result.data is not None:
                content = json.dumps(validation_result.data, ensure_ascii=False)
                result_metadata["validation_status"] = "valid"
                result_metadata["schema_validated"] = True
            elif validation_result.extracted_json:
                content = validation_result.extracted_json
                result_metadata["validation_status"] = "extracted_only"
                result_metadata["schema_validated"] = False
                result_metadata["validation_errors"] = validation_result.errors
                logger.warning(f"Grok response extracted but not schema-valid: {validation_result.errors}")
            else:
                content = raw_content
                result_metadata["validation_status"] = "invalid"
                result_metadata["schema_validated"] = False
                result_metadata["validation_errors"] = validation_result.errors
                logger.warning(f"Grok response not valid JSON: {validation_result.errors}")

            if validation_result.repair_attempted:
                result_metadata["repair_attempted"] = True
                result_metadata["repair_successful"] = validation_result.repair_successful

            return self._create_response_dict(
                content=content,
                model=model_name,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
                metadata=result_metadata,
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "Grok")


# Global service instance for backward compatibility
grok_service = GrokService()
