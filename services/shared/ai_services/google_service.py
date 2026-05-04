"""
Shared Google Gemini service implementation.
Updated to use the new google.genai SDK (replacing deprecated google.generativeai)
"""

import logging
import os
import random
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

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
                    is_rate_limit = "429" in error_str or "rate limit" in error_str or "quota" in error_str or "resource exhausted" in error_str

                    if not is_rate_limit or retries >= max_retries:
                        raise

                    delay = min(
                        base_delay * (exponential_base ** retries), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"⏳ Rate limit hit, retry {retries + 1}/{max_retries} in {delay:.1f}s")
                    time.sleep(delay)
                    retries += 1
        return wrapper
    return decorator


class GoogleService(BaseAIService):
    """Service for handling Google Gemini API interactions using the new google.genai SDK"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Google service.

        Args:
            api_key: Google API key (optional, defaults to GOOGLE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        super().__init__(self.api_key)

    def _initialize_client(self):
        """Initialize the Google Gemini client using the new SDK."""
        if not self.api_key or self.api_key == "your-google-ai-studio-api-key-here":
            logger.debug(
                "Global GOOGLE_API_KEY not set - will use user-specific keys"
            )
            self.client = None
        else:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(
                    "✅ Google Gemini client initialized (google.genai SDK)")
            except Exception as e:
                logger.error(
                    f"❌ Failed to initialize Google Gemini client: {e}")
                self.client = None

    def is_available(self) -> bool:
        """Check if Google service is available (API key set)"""
        return self.client is not None

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "gemini-2.0-flash",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response using Google Gemini API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: Gemini model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional parameters

        Returns:
            Dict with response data including content, metadata, and usage stats
        """
        # E2E Test Mode: Return mock response
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(
                f"🧪 E2E Test Mode: Returning mock response for {model_name}")
            return self._create_response_dict(
                content="Mock Gemini response for E2E testing. This is a simulated answer generated during automated testing.",
                model=model_name,
                usage={
                    "prompt_tokens": 110,
                    "completion_tokens": 55,
                    "total_tokens": 165,
                },
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 120,
                    "cost_usd": 0.0,
                    "provider": "Google",
                    "created_at": datetime.now().isoformat(),
                    "e2e_test_mode": True,
                    **self.get_invocation_provenance(),
                },
                success=True,
                error=None,
            )

        if not self.is_available():
            raise ValueError(
                "Google service is not available - check GOOGLE_API_KEY configuration")

        try:
            start_time = datetime.now()

            # Configure safety settings to allow legitimate legal/research content
            # This is necessary for academic legal exam content which may be falsely flagged
            # Using proper enum types as per Google SDK documentation
            # Including CIVIC_INTEGRITY for legal/political content
            safety_settings = [
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
            ]

            # Configure thinking budget for models that support it
            # Thinking tokens count against max_output_tokens, so we limit them
            # to ensure actual response content is generated
            thinking_config = None
            supports_thinking = (
                "2.5-pro" in model_name
                or "2.5-flash" in model_name
                or "3-flash" in model_name
                or "3.1-pro" in model_name
            )
            if supports_thinking:
                thinking_budget = kwargs.get("thinking_budget", 1024)
                thinking_config = types.ThinkingConfig(thinking_budget=int(thinking_budget))
                logger.info(f"🧠 Configured thinking_budget={thinking_budget} for {model_name}")

            # Configure generation settings using new SDK types
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                system_instruction=system_prompt if system_prompt else None,
                safety_settings=safety_settings,
                thinking_config=thinking_config,
            )

            # Log exact API request for debugging
            logger.info(f"📤 GOOGLE API REQUEST for {model_name}:")
            logger.info(f"📤 System prompt ({len(system_prompt) if system_prompt else 0} chars): {system_prompt[:500] if system_prompt else 'None'}{'...' if system_prompt and len(system_prompt) > 500 else ''}")
            logger.info(f"📤 User prompt ({len(prompt)} chars): {prompt[:500]}{'...' if len(prompt) > 500 else ''}")
            logger.info(f"📤 Config: temperature={temperature}, max_tokens={max_tokens}, thinking_config={thinking_config}")

            # Make Google Gemini API call using new client-based approach
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )

            end_time = datetime.now()
            response_time_ms = int(
                (end_time - start_time).total_seconds() * 1000)

            # Extract response text with detailed logging
            response_text = ""

            # Log response structure for debugging
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                logger.info(
                    f"🔍 Response has {len(response.candidates)} candidate(s)")

                # Check finish reason
                if hasattr(candidate, 'finish_reason'):
                    logger.info(f"🔍 Finish reason: {candidate.finish_reason}")

                # Check for safety ratings/blocks
                if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                    for rating in candidate.safety_ratings:
                        if hasattr(rating, 'blocked') and rating.blocked:
                            logger.warning(
                                f"⚠️ Content blocked by safety filter: {rating.category}")

                # Extract content from candidate
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts') and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                response_text += part.text
                        logger.info(
                            f"🔍 Extracted text from {len(candidate.content.parts)} part(s), length: {len(response_text)}")
                    else:
                        logger.warning(f"⚠️ Candidate content has no parts. Content type: {type(candidate.content)}, content: {candidate.content}")
                        # Try direct text extraction from candidate
                        if hasattr(candidate, 'text') and candidate.text:
                            response_text = candidate.text
                            logger.info(f"🔍 Extracted from candidate.text, length: {len(response_text)}")
                else:
                    logger.warning(f"⚠️ Candidate has no content. Candidate attrs: {dir(candidate)}")
            else:
                logger.warning("⚠️ Response has no candidates")
                # Check for prompt feedback (safety block at prompt level)
                if hasattr(response, 'prompt_feedback'):
                    feedback = response.prompt_feedback
                    logger.warning(f"⚠️ Prompt feedback: {feedback}")

                    # Check if blocked due to policy
                    if hasattr(feedback, 'block_reason') and feedback.block_reason:
                        block_reason = str(feedback.block_reason)
                        error_msg = f"Google blocked this request due to content policy: {block_reason}. This is a Google API policy restriction, not a code error. Consider using a different model (Claude, GPT-4, DeepSeek) for this content."
                        logger.error(f"❌ {error_msg}")
                        raise ValueError(error_msg)

            # Fallback to .text property if direct extraction failed
            if not response_text and hasattr(response, 'text') and response.text:
                response_text = response.text
                logger.info(
                    f"🔍 Used response.text fallback, length: {len(response_text)}")

            # Get actual token usage if available, otherwise estimate
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = getattr(
                    response.usage_metadata, 'prompt_token_count', 0) or 0
                output_tokens = getattr(
                    response.usage_metadata, 'candidates_token_count', 0) or 0
                total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) or (
                    input_tokens + output_tokens)
            else:
                # Fallback to estimation
                prompt_length = len(system_prompt + prompt)
                input_tokens = int(prompt_length / 4)
                response_length = len(response_text)
                output_tokens = int(response_length / 4)
                total_tokens = input_tokens + output_tokens

            # Estimate cost (Gemini 2.5 Pro: roughly $7/1M tokens, combined input/output)
            cost_usd = total_tokens * 0.000007

            logger.info(f"🤖 Gemini Generation: {model_name}")
            logger.info(
                f"📊 Tokens: {input_tokens} input + "
                f"{output_tokens} output = {total_tokens}"
            )
            logger.info(f"💰 Cost: ~${cost_usd:.4f}")
            logger.info(f"⏱️ Response time: {response_time_ms}ms")

            if not response_text.strip():
                return self._create_response_dict(
                    content="",
                    model=model_name,
                    usage={
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": total_tokens,
                    },
                    metadata={
                        "provider": "Google",
                        "created_at": end_time.isoformat(),
                        **self.get_invocation_provenance(),
                    },
                    success=False,
                    error="Model returned empty response (possible safety filter or capacity issue)",
                )

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
                    "provider": "Google",
                    "created_at": end_time.isoformat(),
                    **self.get_invocation_provenance(),
                },
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "Google Gemini")

    @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "gemini-2.0-flash",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response using Google Gemini's JSON mode.

        Uses response_mime_type="application/json" for guaranteed JSON output.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: Gemini model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)

        Returns:
            Dict with response data. The 'content' field will be a JSON string.
        """
        import json

        # E2E Test Mode: Return mock structured response
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(
                f"🧪 E2E Test Mode: Returning mock structured response for {model_name}")
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
                usage={"prompt_tokens": 110,
                       "completion_tokens": 55, "total_tokens": 165},
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 120,
                    "structured_output": True,
                    "e2e_test_mode": True,
                    **self.get_invocation_provenance(),
                },
                success=True,
            )

        if not self.is_available():
            raise ValueError(
                "Google service is not available - check GOOGLE_API_KEY configuration")

        try:
            start_time = datetime.now()

            # Add format instructions to prompt since Gemini may not support schema directly
            format_instructions = f"\n\nRespond with a JSON object matching this schema:\n{json.dumps(json_schema, indent=2)}\n\nRespond ONLY with valid JSON."
            enhanced_prompt = prompt + format_instructions

            # Configure safety settings to allow legitimate legal/research content
            # Using OFF threshold for academic legal exam content which may be falsely flagged
            # Using proper enum types as per Google SDK documentation
            # Including CIVIC_INTEGRITY for legal/political content
            safety_settings = [
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                    threshold=types.HarmBlockThreshold.OFF,
                ),
            ]

            # Configure thinking budget for thinking-capable Gemini models
            thinking_config = None
            supports_thinking = (
                "2.5-pro" in model_name
                or "2.5-flash" in model_name
                or "3-flash" in model_name
                or "3.1-pro" in model_name
            )
            if supports_thinking:
                thinking_budget = kwargs.get("thinking_budget", 1024)
                thinking_config = types.ThinkingConfig(thinking_budget=int(thinking_budget))
                logger.info(f"🧠 Configured thinking_budget={thinking_budget} for {model_name}")

            # Configure generation with JSON mode using new SDK types
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                system_instruction=system_prompt if system_prompt else None,
                response_mime_type="application/json",
                safety_settings=safety_settings,
                thinking_config=thinking_config,
            )

            response = self.client.models.generate_content(
                model=model_name,
                contents=enhanced_prompt,
                config=config,
            )

            end_time = datetime.now()
            response_time_ms = int(
                (end_time - start_time).total_seconds() * 1000)

            response_text = response.text if response.text else ""

            # Get actual token usage if available, otherwise estimate
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = getattr(
                    response.usage_metadata, 'prompt_token_count', 0) or 0
                output_tokens = getattr(
                    response.usage_metadata, 'candidates_token_count', 0) or 0
                total_tokens = getattr(response.usage_metadata, 'total_token_count', 0) or (
                    input_tokens + output_tokens)
            else:
                prompt_length = len(system_prompt + enhanced_prompt)
                input_tokens = int(prompt_length / 4)
                response_length = len(response_text)
                output_tokens = int(response_length / 4)
                total_tokens = input_tokens + output_tokens

            cost_usd = total_tokens * 0.000007

            logger.info(f"🤖 Gemini Structured Generation: {model_name}")
            logger.info(
                f"📊 Tokens: {input_tokens} input + "
                f"{output_tokens} output = {total_tokens}"
            )
            logger.info(f"💰 Cost: ~${cost_usd:.4f}")
            logger.info(f"⏱️ Response time: {response_time_ms}ms")

            # Validate and extract JSON using ResponseValidator
            validator = ResponseValidator(strict=True)
            validation_result = validator.validate_response(
                response_text,
                json_schema,
                attempt_repair=True
            )

            result_metadata = {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_time_ms": response_time_ms,
                "cost_usd": cost_usd,
                "provider": "Google",
                "structured_output": True,
                "created_at": end_time.isoformat(),
            }

            if validation_result.valid and validation_result.data is not None:
                content = json.dumps(
                    validation_result.data, ensure_ascii=False)
                result_metadata["validation_status"] = "valid"
                result_metadata["schema_validated"] = True
            elif validation_result.extracted_json:
                content = validation_result.extracted_json
                result_metadata["validation_status"] = "extracted_only"
                result_metadata["schema_validated"] = False
                result_metadata["validation_errors"] = validation_result.errors
                logger.warning(
                    f"Google response extracted but not schema-valid: {validation_result.errors}")
            else:
                content = response_text
                result_metadata["validation_status"] = "invalid"
                result_metadata["schema_validated"] = False
                result_metadata["validation_errors"] = validation_result.errors
                logger.warning(
                    f"Google response not valid JSON: {validation_result.errors}")

            if validation_result.repair_attempted:
                result_metadata["repair_attempted"] = True
                result_metadata["repair_successful"] = validation_result.repair_successful

            return self._create_response_dict(
                content=content,
                model=model_name,
                usage={
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
                metadata=result_metadata,
                success=True,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "Google Gemini")

    async def generate_response(
        self,
        system_prompt: str,
        instruction_prompt: str,
        case_data: str,
        model_name: str = "gemini-2.0-flash",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Legacy method for backward compatibility.
        Generate a response using Google Gemini API with case data.

        Args:
            system_prompt: System-level instructions
            instruction_prompt: Specific task instructions
            case_data: The case/question to analyze
            model_name: Gemini model to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional parameters

        Returns:
            Dictionary with response data and metadata
        """
        # Combine instruction and case data
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
                "provider": "Google",
            }
        else:
            raise Exception(result.get("error", "Unknown error"))


# Global instance for backward compatibility
google_service = GoogleService()
