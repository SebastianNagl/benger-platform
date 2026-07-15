"""Generic OpenAI-compatible client for custom (BYOM) models.

Generalizes the DeepInfra service pattern (plain HTTP POST to
``{base_url}/chat/completions`` with optional Bearer auth) for
user-registered endpoints: vLLM, Ollama, LM Studio, llama.cpp, TGI, or any
cloud service exposing the OpenAI chat-completions schema.

Differences from the fixed-provider services:

- ``base_url`` / ``endpoint_model_name`` come from the llm_models row, not
  constants. The row's PK (``custom-<uuid>``) is never sent to the remote
  server.
- ``api_key`` may be None (``requires_api_key=False`` endpoints, e.g. a
  local vLLM) — the Authorization header is simply omitted.
- Cost is computed inline from the row's per-million rates. The YAML-backed
  ``calculate_cost``/``get_model_cost`` never see custom rows, so using them
  here would silently price everything at 0 while the pre-run estimate
  (cost_estimate.py, DB-based) showed real numbers.
- Seed is gated on the row's ``parameter_constraints.seed.supported``
  (constructor arg), not the YAML-backed ``model_supports_seed``.
- SSRF hardening: before every outbound request the base_url is re-resolved
  and validated via url_guard, and the aiohttp connection is PINNED to the
  exact validated IPs (save-time validation alone is defeated by a TTL-0 DNS
  rebind between the guard's lookup and aiohttp's). Redirects are NOT followed
  (a redirect to an internal address would bypass the pre-flight IP check).
- response_metadata never includes ``base_url`` or credential material —
  project exports embed Generation.response_metadata verbatim, and shared
  results must not leak another user's endpoint details.

Structured output is prompt-based (schema injected into the system prompt,
response validated/extracted by ResponseValidator) — arbitrary
OpenAI-compatible servers cannot be assumed to support json_schema mode.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp

from .base_service import BaseAIService, derive_refusal, derive_truncated
from .deepinfra_service import async_retry_with_exponential_backoff
from .response_validator import ResponseValidator

logger = logging.getLogger(__name__)


class OpenAICompatibleService(BaseAIService):
    """Client for a user-registered OpenAI-compatible endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        endpoint_model_name: Optional[str] = None,
        *,
        input_cost_per_million: Optional[float] = None,
        output_cost_per_million: Optional[float] = None,
        supports_seed: bool = False,
        timeout_s: int = 300,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.endpoint_model_name = endpoint_model_name
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.supports_seed = supports_seed
        self.timeout_s = timeout_s
        super().__init__(api_key)

    def _initialize_client(self):
        # Keyless endpoints are valid (requires_api_key=False models):
        # available == "we have an endpoint", not "we have a key".
        self.client = bool(self.base_url)
        if self.client:
            logger.info("OpenAI-compatible custom-model client initialized")

    def is_available(self) -> bool:
        return bool(self.client)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Cost from the model row's per-million rates; 0.0 when unset."""
        cost = 0.0
        if self.input_cost_per_million:
            cost += (input_tokens / 1_000_000) * self.input_cost_per_million
        if self.output_cost_per_million:
            cost += (output_tokens / 1_000_000) * self.output_cost_per_million
        return cost

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _resolve_model(self, model_name: str) -> str:
        """The remote 'model' string. endpoint_model_name wins; the caller's
        model_name (already endpoint_model_name in the worker path) is the
        fallback for direct callers."""
        return self.endpoint_model_name or model_name

    @async_retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    async def _generate_async(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs,
    ) -> Dict[str, Any]:
        api_model_name = self._resolve_model(model_name)

        # E2E Test Mode: mock response, same shape as the real providers
        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(f"🧪 E2E Test Mode: mock custom-model response for {api_model_name}")
            return self._create_response_dict(
                content="Mock custom-model response for E2E testing.",
                model=api_model_name,
                usage={"prompt_tokens": 105, "completion_tokens": 52, "total_tokens": 157},
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 110,
                    "cost_usd": 0.0,
                    "provider": "Custom",
                    "finish_reason": "stop",
                    "truncated": False,
                    "refusal": False,
                    "error_type": None,
                    "seed": None,
                    "created_at": datetime.now().isoformat(),
                    "e2e_test_mode": True,
                    **self.get_invocation_provenance(),
                },
                success=True,
                error=None,
            )

        if not self.is_available():
            raise ValueError("Custom model endpoint is not configured (missing base_url)")

        requested_seed = kwargs.get("seed", 42)

        try:
            # Call-time SSRF re-check + connection pinning. resolve_and_validate
            # runs the full guard and returns the exact IPs that passed; the
            # pinned connector then makes aiohttp connect to ONLY those IPs, so
            # a TTL-0 DNS rebind between this lookup and aiohttp's own cannot
            # swap in an internal address. Inside the try so a rejection
            # surfaces as the standard error dict, not an exception out of
            # generate(). Import here: url_guard lives at the /shared root, on
            # sys.path in both containers.
            from url_guard import pinned_connector, resolve_and_validate

            _normalized_url, validated_ips = resolve_and_validate(self.base_url)

            start_time = datetime.now()

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
            if self.supports_seed:
                payload["seed"] = requested_seed

            # URL keeps the hostname (never the pinned IP) so TLS SNI + cert
            # verification stay correct; the connector routes it to the
            # validated IP.
            async with aiohttp.ClientSession(
                connector=pinned_connector(validated_ips)
            ) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_s),
                    allow_redirects=False,
                ) as response:
                    if 300 <= response.status < 400:
                        # Following a redirect would bypass the pre-flight
                        # IP check — refuse instead.
                        raise Exception(
                            f"HTTP {response.status}: custom model endpoints must not redirect"
                        )
                    if response.status >= 400:
                        error_body = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_body[:500]}")
                    result = await response.json()

            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            response_text = ""
            if result.get("choices") and len(result["choices"]) > 0:
                response_text = result["choices"][0]["message"]["content"] or ""

            usage = result.get("usage") or {}
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            cost_usd = self._calculate_cost(input_tokens, output_tokens)

            finish_reason = (
                result["choices"][0].get("finish_reason") if result.get("choices") else None
            )

            logger.info(
                f"🤖 Custom model generation: {api_model_name} | "
                f"{input_tokens}+{output_tokens} tokens | ${cost_usd:.4f} | {response_time_ms}ms"
            )

            # NOTE: no base_url in metadata — response_metadata is embedded
            # verbatim in project exports and shared results.
            return self._create_response_dict(
                content=response_text,
                model=api_model_name,
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
                    "provider": "Custom",
                    "finish_reason": finish_reason,
                    "truncated": derive_truncated(finish_reason),
                    "refusal": derive_refusal(finish_reason),
                    "error_type": None,
                    "seed": requested_seed if self.supports_seed else None,
                    "created_at": end_time.isoformat(),
                    **self.get_invocation_provenance(),
                },
                success=True,
                error=None,
            )

        except Exception as e:
            return self._create_error_response(e, api_model_name, "Custom")

    @async_retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
    async def _generate_structured_async(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """Prompt-based structured output (schema injected, response
        validated) — arbitrary OpenAI-compatible servers cannot be assumed
        to support native json_schema mode."""
        import json

        api_model_name = self._resolve_model(model_name)

        if os.getenv("E2E_TEST_MODE") == "true":
            logger.info(
                f"🧪 E2E Test Mode: mock structured custom-model response for {api_model_name}"
            )
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
                model=api_model_name,
                usage={"prompt_tokens": 105, "completion_tokens": 52, "total_tokens": 157},
                metadata={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_time_ms": 110,
                    "finish_reason": "stop",
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

        try:
            format_instructions = f"""

## Output Format
You MUST respond with a valid JSON object matching this schema:
{json.dumps(json_schema, indent=2)}

Your response must be ONLY the JSON object, no other text before or after.
"""
            enhanced_system_prompt = system_prompt + format_instructions

            result = await self._generate_async(
                prompt=prompt,
                system_prompt=enhanced_system_prompt,
                model_name=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )

            if result["success"]:
                validator = ResponseValidator(strict=True)
                validation_result = validator.validate_response(
                    result["content"],
                    json_schema,
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
                    logger.warning(
                        f"Custom-model response extracted but not schema-valid: {validation_result.errors}"
                    )
                else:
                    result["metadata"]["structured_output"] = True
                    result["metadata"]["validation_status"] = "invalid"
                    result["metadata"]["schema_validated"] = False
                    result["metadata"]["validation_errors"] = validation_result.errors
                    logger.warning(
                        f"Custom-model response not valid JSON: {validation_result.errors}"
                    )

            return result

        except Exception as e:
            return self._create_error_response(e, api_model_name, "Custom")

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model_name: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """Sync entry point matching BaseAIService.generate (worker lane)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._generate_async(
                    prompt, system_prompt, model_name, max_tokens, temperature, **kwargs
                )
            )
        finally:
            loop.close()

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: Dict[str, Any],
        model_name: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """Sync entry point matching BaseAIService.generate_structured."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._generate_structured_async(
                    prompt, system_prompt, json_schema, model_name, max_tokens, temperature, **kwargs
                )
            )
        finally:
            loop.close()
