"""
Shared Cohere service implementation.

Provides integration with Cohere's models including:
- Command A, Command R+, Command R
- Support for chat completions and structured output
"""

import json
import logging
import os
import random
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

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


class CohereService(BaseAIService):
    """Service for handling Cohere API interactions"""

    # Model name mapping from display names to API names
    MODEL_MAPPING = {
        # Latest models
        "Command A": "command-a-03-2025",
        "Command A Vision": "command-a-03-2025",
        "Command A Reasoning": "command-a-03-2025",
        "Command R+": "command-r-plus-08-2024",
        "Command R+ 08-2024": "command-r-plus-08-2024",
        "Command R": "command-r-08-2024",
        "Command R 08-2024": "command-r-08-2024",
        # Aya multilingual models
        "Aya Expanse": "aya-expanse-32b",
        "Aya Expanse 32B": "aya-expanse-32b",
        "Aya Expanse 8B": "aya-expanse-8b",
        # Direct model IDs
        "command-a-03-2025": "command-a-03-2025",
        "command-r-plus-08-2024": "command-r-plus-08-2024",
        "command-r-08-2024": "command-r-08-2024",
        "aya-expanse-32b": "aya-expanse-32b",
        "aya-expanse-8b": "aya-expanse-8b",
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Cohere service.

        Args:
            api_key: Cohere API key (optional, defaults to CO_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("CO_API_KEY") or os.getenv("COHERE_API_KEY")
        super().__init__(self.api_key)

    def _initialize_client(self):
        """Initialize the Cohere client."""
        if not self.api_key:
            logger.debug(
                "Global CO_API_KEY not set - will use user-specific keys"
            )
            self.client = None
        else:
            try:
                import cohere
                self.client = cohere.ClientV2(api_key=self.api_key)
                logger.info("Cohere client initialized")
            except ImportError:
                logger.error("cohere package not installed. Run: pip install cohere")
                self.client = None
            except Exception as e:
                logger.error(f"Failed to initialize Cohere client: {e}")
                self.client = None

    def is_available(self) -> bool:
        """Check if Cohere service is available (API key set)"""
        return self.client is not None

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "command-r-plus-08-2024",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response using Cohere API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: Cohere model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional parameters

        Returns:
            Dict with response data including content, metadata, and usage stats
        """
        # E2E Test Mode: Return mock response
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(f"E2E Test Mode: Returning mock response for {model_name}")
            return self._create_response_dict(
                content="Mock Cohere response for E2E testing. This is a simulated answer generated during automated testing.",
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
            raise ValueError("Cohere service is not available - check CO_API_KEY configuration")

        try:
            start_time = datetime.now()

            # Map display name to API model name
            api_model_name = self.MODEL_MAPPING.get(model_name, model_name)

            # Build messages list for Cohere v2 API
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Build API call parameters
            api_params = {
                "model": api_model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "seed": 42,  # Add seed for maximum determinism
            }

            # Add thinking configuration for Command A models
            thinking_token_budget = kwargs.get("thinking_token_budget")
            if "command-a" in model_name.lower() and thinking_token_budget:
                api_params["thinking"] = {"tokenBudget": int(thinking_token_budget)}
                logger.info(f"Using thinking.tokenBudget={thinking_token_budget} for {model_name}")

            # Make Cohere API call
            response = self.client.chat(**api_params)

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response data - Cohere v2 API response structure
            content = ""
            if hasattr(response, 'message') and response.message:
                if hasattr(response.message, 'content') and response.message.content:
                    # Content is a list of content blocks
                    for block in response.message.content:
                        if hasattr(block, 'text'):
                            content += block.text
                content = content.strip()

            # Get usage stats
            usage = response.usage if hasattr(response, 'usage') else None
            prompt_tokens = 0
            completion_tokens = 0
            if usage:
                if hasattr(usage, 'tokens'):
                    tokens = usage.tokens
                    prompt_tokens = tokens.input_tokens if hasattr(tokens, 'input_tokens') else 0
                    completion_tokens = tokens.output_tokens if hasattr(tokens, 'output_tokens') else 0
            total_tokens = prompt_tokens + completion_tokens

            logger.info(f"Cohere Generation: {model_name}")
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
                    "finish_reason": response.finish_reason if hasattr(response, 'finish_reason') else "unknown",
                    "created_at": end_time.isoformat(),
                },
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "Cohere")

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "command-r-plus-08-2024",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response using Cohere's response format.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: Cohere model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)

        Returns:
            Dict with response data. The 'content' field will be a JSON string.
        """
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
            raise ValueError("Cohere service is not available - check CO_API_KEY configuration")

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

            # Make Cohere API call with JSON response format
            response = self.client.chat(
                model=api_model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                seed=42,  # Add seed for maximum determinism
                response_format={"type": "json_object"},
            )

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response data
            raw_content = ""
            if hasattr(response, 'message') and response.message:
                if hasattr(response.message, 'content') and response.message.content:
                    for block in response.message.content:
                        if hasattr(block, 'text'):
                            raw_content += block.text
                raw_content = raw_content.strip()

            # Get usage stats
            usage = response.usage if hasattr(response, 'usage') else None
            prompt_tokens = 0
            completion_tokens = 0
            if usage:
                if hasattr(usage, 'tokens'):
                    tokens = usage.tokens
                    prompt_tokens = tokens.input_tokens if hasattr(tokens, 'input_tokens') else 0
                    completion_tokens = tokens.output_tokens if hasattr(tokens, 'output_tokens') else 0
            total_tokens = prompt_tokens + completion_tokens

            logger.info(f"Cohere Structured Generation: {model_name}")
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
                "finish_reason": response.finish_reason if hasattr(response, 'finish_reason') else "unknown",
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
                logger.warning(f"Cohere response extracted but not schema-valid: {validation_result.errors}")
            else:
                content = raw_content
                result_metadata["validation_status"] = "invalid"
                result_metadata["schema_validated"] = False
                result_metadata["validation_errors"] = validation_result.errors
                logger.warning(f"Cohere response not valid JSON: {validation_result.errors}")

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
            return self._create_error_response(e, model_name, "Cohere")


# Global service instance for backward compatibility
cohere_service = CohereService()
