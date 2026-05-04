"""
Shared DeepInfra service implementation.
"""

import asyncio
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


# Phase 6.2: shared retry-history contextvar (defined in base_service).
from .base_service import _retry_history_ctx, get_retry_history_snapshot  # noqa: F401


def async_retry_with_exponential_backoff(
    max_retries: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True
):
    """Async decorator for exponential backoff retry on rate limit errors.

    Records attempts in the shared retry-history contextvar (Phase 6.2).
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            history: list = []
            token = _retry_history_ctx.set(history)
            try:
                retries = 0
                while True:
                    attempt_start = time.time()
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        error_str = str(e).lower()
                        is_rate_limit = (
                            "429" in error_str
                            or "rate limit" in error_str
                            or "too many requests" in error_str
                        )
                        history.append({
                            "attempt": retries + 1,
                            "error": str(e)[:200],
                            "is_rate_limit": is_rate_limit,
                            "latency_ms": int((time.time() - attempt_start) * 1000),
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
                        await asyncio.sleep(delay)
                        retries += 1
            finally:
                _retry_history_ctx.reset(token)
        return wrapper
    return decorator


class DeepInfraService(BaseAIService):
    """Service for handling DeepInfra API interactions"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize DeepInfra service.
        
        Args:
            api_key: DeepInfra API key (optional, defaults to DEEPINFRA_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("DEEPINFRA_API_KEY")
        self.base_url = "https://api.deepinfra.com/v1/openai"
        
        # Model name mapping from display names to API names
        self.model_mapping = {
            # DeepSeek models
            "DeepSeek-V3.2": "deepseek-ai/DeepSeek-V3.2",
            "DeepSeek-V3.1": "deepseek-ai/DeepSeek-V3.1",
            "DeepSeek-R1": "deepseek-ai/DeepSeek-R1-0528",
            "DeepSeek-R1-Distill-Llama-70B": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
            # Qwen models
            "Qwen3-235B Instruct": "Qwen/Qwen3-235B-A22B-Instruct-2507",
            "Qwen3-235B Thinking": "Qwen/Qwen3-235B-A22B-Thinking-2507",
            "Qwen3 Coder 480B": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "Qwen3 32B": "Qwen/Qwen3-32B",
            "QwQ-32B": "Qwen/QwQ-32B",
            "Qwen 2.5 Coder 32B": "Qwen/Qwen2.5-Coder-32B-Instruct",
            # Llama models
            "Llama 3.3 70B Turbo": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "Llama 3.1 70B": "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "Llama 3.1 8B": "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "Llama 4 Scout": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
            "Llama 4 Maverick": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            # Kimi models
            "Kimi K2.5": "moonshotai/Kimi-K2.5",
            "Kimi K2 Instruct": "moonshotai/Kimi-K2-Instruct-0905",
            "Kimi K2 Thinking": "moonshotai/Kimi-K2-Thinking",
            # MiniMax
            "MiniMax M2.5": "MiniMaxAI/MiniMax-M2.5",
            # GLM models (formerly separate Zhipu AI provider)
            "GLM-5": "zai-org/GLM-5",
            "GLM-4.7": "zai-org/GLM-4.7",
            "GLM-4.7-Flash": "zai-org/GLM-4.7-Flash",
            # Backward compatibility: map old incorrect API names to correct ones
            "meta-llama/Llama-3.1-70B-Instruct": "meta-llama/Meta-Llama-3.1-70B-Instruct",
            "meta-llama/Llama-3.1-8B-Instruct": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        }
        
        super().__init__(self.api_key)

    def _initialize_client(self):
        """Initialize the DeepInfra client."""
        if not self.api_key or self.api_key == "your-deepinfra-api-key-here":
            logger.debug(
                "Global DEEPINFRA_API_KEY not set - will use user-specific keys"
            )
            self.client = None
        else:
            self.client = True  # Simple flag to indicate we have API key
            logger.info("✅ DeepInfra client initialized")

    def is_available(self) -> bool:
        """Check if DeepInfra service is available (API key set)"""
        return self.client is not None

    @async_retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "meta-llama/Llama-3.3-70B-Instruct",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a response using DeepInfra API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            model_name: DeepInfra model to use
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
                content="Mock DeepInfra response for E2E testing. This is a simulated answer generated during automated testing.",
                model=model_name,
                usage={
                    "prompt_tokens": 105,
                    "completion_tokens": 52,
                    "total_tokens": 157,
                },
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 110,
                    "cost_usd": 0.0,
                    "provider": "DeepInfra",
                    "created_at": datetime.now().isoformat(),
                    "e2e_test_mode": True,
                    **self.get_invocation_provenance(),
                },
                success=True,
                error=None,
            )

        if not self.is_available():
            raise ValueError(
                "DeepInfra service is not available - check DEEPINFRA_API_KEY configuration"
            )

        try:
            start_time = datetime.now()
            
            # Map display name to API model name
            api_model_name = self.model_mapping.get(model_name, model_name)
            logger.info(f"🔄 Model mapping: '{model_name}' -> '{api_model_name}'")

            # Prepare the request payload (OpenAI-compatible format)
            payload = {
                "model": api_model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Make DeepInfra API call
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),  # 5 minutes timeout
                ) as response:
                    if response.status >= 400:
                        error_body = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_body[:500]}")
                    result = await response.json()

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Extract response text
            response_text = ""
            if result.get("choices") and len(result["choices"]) > 0:
                response_text = result["choices"][0]["message"]["content"]

            # Calculate token usage
            usage = result.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # Estimate cost (DeepInfra: typically $0.27/1M input, $1.35/1M output for Llama models)
            cost_usd = (input_tokens * 0.00000027) + (output_tokens * 0.00000135)

            logger.info(f"🤖 DeepInfra Generation: {model_name}")
            logger.info(f"📊 Tokens: {input_tokens} input + {output_tokens} output = {total_tokens}")
            logger.info(f"💰 Cost: ${cost_usd:.4f}")
            logger.info(f"⏱️ Response time: {response_time_ms}ms")

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
                    "provider": "DeepInfra",
                    "created_at": end_time.isoformat(),
                    **self.get_invocation_provenance(),
                },
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, model_name, "DeepInfra")

    @async_retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "meta-llama/Llama-3.3-70B-Instruct",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response using prompt-based instructions.

        DeepInfra doesn't support native structured output, so we inject format
        instructions into the prompt and parse the JSON response.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            json_schema: JSON Schema defining the expected response structure
            model_name: DeepInfra model to use
            max_tokens: Maximum response tokens
            temperature: Response creativity (0.0-1.0)

        Returns:
            Dict with response data. The 'content' field will be a JSON string.
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
                usage={"prompt_tokens": 105, "completion_tokens": 52, "total_tokens": 157},
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 110,
                    "structured_output": True,
                    "e2e_test_mode": True,
                    **self.get_invocation_provenance(),
                },
                success=True,
            )

        if not self.is_available():
            raise ValueError("DeepInfra service is not available - check DEEPINFRA_API_KEY configuration")

        try:
            # Add format instructions to system prompt
            format_instructions = f"""

## Output Format
You MUST respond with a valid JSON object matching this schema:
{json.dumps(json_schema, indent=2)}

Your response must be ONLY the JSON object, no other text before or after.
"""
            enhanced_system_prompt = system_prompt + format_instructions

            # Use the base generate method
            result = await self.generate(
                prompt=prompt,
                system_prompt=enhanced_system_prompt,
                model_name=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

            if result["success"]:
                # Validate and extract JSON using ResponseValidator
                validator = ResponseValidator(strict=True)
                validation_result = validator.validate_response(
                    result["content"],
                    json_schema,
                    attempt_repair=True
                )

                if validation_result.valid and validation_result.data is not None:
                    result["content"] = json.dumps(validation_result.data, ensure_ascii=False)
                    result["metadata"]["structured_output"] = True
                    result["metadata"]["validation_status"] = "valid"
                    result["metadata"]["schema_validated"] = True
                elif validation_result.extracted_json:
                    result["content"] = validation_result.extracted_json
                    result["metadata"]["structured_output"] = True
                    result["metadata"]["validation_status"] = "extracted_only"
                    result["metadata"]["schema_validated"] = False
                    result["metadata"]["validation_errors"] = validation_result.errors
                    logger.warning(f"DeepInfra response extracted but not schema-valid: {validation_result.errors}")
                else:
                    result["metadata"]["structured_output"] = True
                    result["metadata"]["validation_status"] = "invalid"
                    result["metadata"]["schema_validated"] = False
                    result["metadata"]["validation_errors"] = validation_result.errors
                    logger.warning(f"DeepInfra response not valid JSON: {validation_result.errors}")

                if validation_result.repair_attempted:
                    result["metadata"]["repair_attempted"] = True
                    result["metadata"]["repair_successful"] = validation_result.repair_successful

            return result

        except Exception as e:
            return self._create_error_response(e, model_name, "DeepInfra")

    def generate_structured_sync(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "meta-llama/Llama-3.3-70B-Instruct",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """Synchronous wrapper for generate_structured method."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.generate_structured(prompt, system_prompt, json_schema, model_name, max_tokens, temperature, **kwargs)
            )
        finally:
            loop.close()

    # Non-async wrapper for backward compatibility
    def generate_sync(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "meta-llama/Llama-3.3-70B-Instruct",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Synchronous wrapper for generate method.
        """
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.generate(prompt, system_prompt, model_name, max_tokens, temperature, **kwargs)
            )
        finally:
            loop.close()

    async def generate_response(
        self,
        system_prompt: str,
        instruction_prompt: str,
        case_data: str,
        model_name: str = "meta-llama/Llama-3.3-70B-Instruct",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Legacy method for backward compatibility.
        Generate a response using DeepInfra API with case data.
        
        Args:
            system_prompt: System-level instructions
            instruction_prompt: Specific task instructions
            case_data: The case/question to analyze
            model_name: DeepInfra model to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with response data and metadata
        """
        # Combine prompts for the user message
        user_message = f"{instruction_prompt}\n\nCase to analyze:\n{case_data}"
        
        # Use the base generate method
        result = await self.generate(
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
                "provider": "DeepInfra",
            }
        else:
            raise Exception(result.get("error", "Unknown error"))


# Global instance for backward compatibility
deepinfra_service = DeepInfraService()