"""
Shared Mistral AI service implementation.

Provides integration with Mistral AI's models including:
- Mistral Large, Mistral Medium, Mistral Small
- Codestral (code-optimized)
- Magistral (reasoning-optimized)
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


class MistralService(BaseAIService):
    """Service for handling Mistral AI API interactions"""

    # Model name mapping from display names to API names
    MODEL_MAPPING = {
        # Premier/Frontier models
        "Mistral Large": "mistral-large-latest",
        "Mistral Large 3": "mistral-large-latest",
        "Mistral Medium": "mistral-medium-latest",
        "Mistral Medium 3.1": "mistral-medium-latest",
        "Mistral Small": "mistral-small-latest",
        "Mistral Small 3.2": "mistral-small-latest",
        # Code models
        "Codestral": "codestral-latest",
        "Codestral 2508": "codestral-latest",
        "Devstral": "devstral-small-latest",
        # Reasoning models (Magistral)
        "Magistral Medium": "magistral-medium-latest",
        "Magistral Small": "magistral-small-latest",
        # Edge models
        "Ministral 8B": "ministral-8b-latest",
        "Ministral 3B": "ministral-3b-latest",
        # Direct model IDs
        "mistral-large-latest": "mistral-large-latest",
        "mistral-medium-latest": "mistral-medium-latest",
        "mistral-small-latest": "mistral-small-latest",
        "codestral-latest": "codestral-latest",
        "magistral-medium-latest": "magistral-medium-latest",
        "magistral-small-latest": "magistral-small-latest",
        "ministral-8b-latest": "ministral-8b-latest",
        "ministral-3b-latest": "ministral-3b-latest",
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Mistral service.

        Args:
            api_key: Mistral AI API key (optional, defaults to MISTRAL_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        super().__init__(self.api_key)

    def _initialize_client(self):
        """Initialize the Mistral AI client."""
        if not self.api_key:
            logger.debug(
                "Global MISTRAL_API_KEY not set - will use user-specific keys"
            )
            self.client = None
        else:
            try:
                try:
                    from mistralai import Mistral
                except ImportError:
                    from mistralai.client import Mistral
                self.client = Mistral(api_key=self.api_key)
                logger.info("Mistral client initialized")
            except ImportError:
                logger.error("mistralai package not installed. Run: pip install mistralai")
                self.client = None
            except Exception as e:
                logger.error(f"Failed to initialize Mistral client: {e}")
                self.client = None

    def is_available(self) -> bool:
        """Check if Mistral service is available (API key set)"""
        return self.client is not None

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "mistral-large-latest",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response using Mistral AI API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: Mistral model to use
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
                content="Mock Mistral response for E2E testing. This is a simulated answer generated during automated testing.",
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
            raise ValueError("Mistral service is not available - check MISTRAL_API_KEY configuration")

        try:
            start_time = datetime.now()

            # Map display name to API model name
            api_model_name = self.MODEL_MAPPING.get(model_name, model_name)

            # Build messages list
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
                "random_seed": 42,  # Add seed for maximum determinism
            }

            # Add prompt_mode for Magistral models (reasoning models)
            prompt_mode = kwargs.get("prompt_mode")
            if "magistral" in model_name.lower() and prompt_mode:
                api_params["prompt_mode"] = prompt_mode
                logger.info(f"Using prompt_mode={prompt_mode} for {model_name}")

            # Make Mistral API call
            response = self.client.chat.complete(**api_params)

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response data
            content = response.choices[0].message.content.strip() if response.choices else ""

            # Get usage stats
            usage = response.usage if hasattr(response, 'usage') else None
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens

            logger.info(f"Mistral Generation: {model_name}")
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
                    "finish_reason": response.choices[0].finish_reason if response.choices else "unknown",
                    "created_at": end_time.isoformat(),
                },
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "Mistral")

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "mistral-large-latest",
        max_tokens: int = 1500,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response using Mistral's native JSON mode.

        Mistral supports native JSON mode for structured outputs.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: Mistral model to use
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
            raise ValueError("Mistral service is not available - check MISTRAL_API_KEY configuration")

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

            # Make Mistral API call with JSON mode
            response = self.client.chat.complete(
                model=api_model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                random_seed=42,  # Add seed for maximum determinism
                response_format={"type": "json_object"},
            )

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response data
            raw_content = response.choices[0].message.content.strip() if response.choices else ""

            # Get usage stats
            usage = response.usage if hasattr(response, 'usage') else None
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens

            logger.info(f"Mistral Structured Generation: {model_name}")
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
                "finish_reason": response.choices[0].finish_reason if response.choices else "unknown",
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
                logger.warning(f"Mistral response extracted but not schema-valid: {validation_result.errors}")
            else:
                content = raw_content
                result_metadata["validation_status"] = "invalid"
                result_metadata["schema_validated"] = False
                result_metadata["validation_errors"] = validation_result.errors
                logger.warning(f"Mistral response not valid JSON: {validation_result.errors}")

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
            return self._create_error_response(e, model_name, "Mistral")


# Global service instance for backward compatibility
mistral_service = MistralService()
