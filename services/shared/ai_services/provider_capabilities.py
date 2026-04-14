"""
Provider Capabilities Registry for Multi-Provider AI Service Architecture.

Centralized configuration of AI provider capabilities including:
- Structured output methods and strictness
- Determinism support (seed parameters)
- Temperature ranges
- Cost tracking per model
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class StructuredOutputMethod(str, Enum):
    """Methods for generating structured JSON output."""
    JSON_SCHEMA = "json_schema"  # Native JSON schema (OpenAI)
    TOOL_USE = "tool_use"  # Function/tool calling (Anthropic)
    JSON_MODE = "json_mode"  # JSON mode without schema enforcement
    PROMPT_BASED = "prompt_based"  # Schema in prompt only


@dataclass
class StructuredOutputCapability:
    """Structured output capability for a provider."""
    method: StructuredOutputMethod
    strict_mode: bool  # Whether schema is strictly enforced
    guaranteed: bool  # Whether valid JSON is guaranteed


@dataclass
class DeterminismCapability:
    """Determinism support for a provider."""
    seed_support: bool
    recommended_seed: Optional[int] = 42


@dataclass
class TemperatureCapability:
    """Temperature range for a provider."""
    min_value: float
    max_value: float
    default: float


@dataclass
class ModelCost:
    """Cost per million tokens for a model."""
    input: float  # USD per million input tokens
    output: float  # USD per million output tokens


# Provider capabilities registry
PROVIDER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "openai": {
        "display_name": "OpenAI",
        "structured_output": {
            "method": StructuredOutputMethod.JSON_SCHEMA,
            "strict_mode": True,
            "guaranteed": True,
        },
        "determinism": {
            "seed_support": True,
            "recommended_seed": 42,
        },
        "temperature": {
            "min": 0.0,
            "max": 2.0,
            "default": 0.0,
        },
        "cost_per_million_tokens": {
            "gpt-5.4": {"input": 2.50, "output": 15.00},
            "gpt-5.2": {"input": 1.75, "output": 14.00},
            "gpt-5.1": {"input": 1.25, "output": 10.00},
            "gpt-5": {"input": 1.25, "output": 10.00},
            "gpt-5-mini": {"input": 0.25, "output": 2.00},
            "gpt-5-nano": {"input": 0.05, "output": 0.40},
            "gpt-4.1": {"input": 2.00, "output": 8.00},
            "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
            "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
            "o3": {"input": 2.00, "output": 8.00},
            "o3-mini": {"input": 1.10, "output": 4.40},
            "o4-mini": {"input": 1.10, "output": 4.40},
            "o1": {"input": 15.00, "output": 60.00},
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00},
            "gpt-4": {"input": 30.00, "output": 60.00},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        },
        "models_supporting_json_schema": [
            "gpt-4o", "gpt-4o-mini", "gpt-4o-2024",
            "gpt-4-turbo", "gpt-4-turbo-preview",
            "gpt-4-0125-preview", "gpt-4-1106-preview",
            "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.4",
            "gpt-5-mini", "gpt-5-nano",
            "o1", "o3", "o4-mini",
        ],
    },
    "anthropic": {
        "display_name": "Anthropic",
        "structured_output": {
            "method": StructuredOutputMethod.TOOL_USE,
            "strict_mode": True,
            "guaranteed": True,
        },
        "determinism": {
            "seed_support": False,
            "recommended_seed": None,
        },
        "temperature": {
            "min": 0.0,
            "max": 1.0,
            "default": 0.0,
        },
        "cost_per_million_tokens": {
            # Claude 4.6 family
            "claude-opus-4-6": {"input": 5.00, "output": 25.00},
            "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
            # Claude 4.5 family (latest)
            "claude-opus-4-5-20251101": {"input": 5.00, "output": 25.00},
            "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
            "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
            # Claude 4 family
            "claude-opus-4-1-20250805": {"input": 15.00, "output": 75.00},
            "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
            "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
            # Claude 3.7
            "claude-3-7-sonnet-20250219": {"input": 3.00, "output": 15.00},
            # Legacy (kept for backward compatibility with existing records)
            "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
            "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
            "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
            "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
            "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        },
    },
    "google": {
        "display_name": "Google",
        "structured_output": {
            "method": StructuredOutputMethod.JSON_MODE,
            "strict_mode": False,
            "guaranteed": False,
        },
        "determinism": {
            "seed_support": False,
            "recommended_seed": None,
        },
        "temperature": {
            "min": 0.0,
            "max": 2.0,
            "default": 0.0,
        },
        "cost_per_million_tokens": {
            "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
            "gemini-3-flash-preview": {"input": 0.50, "output": 3.00},
            "gemini-3.1-flash-lite-preview": {"input": 0.25, "output": 1.50},
            "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
            "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
            "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
            "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
        },
    },
    "deepinfra": {
        "display_name": "DeepInfra",
        "structured_output": {
            "method": StructuredOutputMethod.PROMPT_BASED,
            "strict_mode": False,
            "guaranteed": False,
        },
        "determinism": {
            "seed_support": False,
            "recommended_seed": None,
        },
        "temperature": {
            "min": 0.0,
            "max": 2.0,
            "default": 0.0,
        },
        "cost_per_million_tokens": {
            "deepseek-ai/DeepSeek-V3.1": {"input": 0.21, "output": 0.79},
            "deepseek-ai/DeepSeek-R1-0528": {"input": 0.50, "output": 2.15},
            "deepseek-ai/DeepSeek-V3.2": {"input": 0.26, "output": 0.38},
            "deepseek-ai/DeepSeek-R1-Distill-Llama-70B": {"input": 0.70, "output": 0.80},
            "Qwen/Qwen3-235B-A22B-Instruct-2507": {"input": 0.071, "output": 0.10},
            "Qwen/Qwen3-235B-A22B-Thinking-2507": {"input": 0.23, "output": 2.30},
            "Qwen/QwQ-32B": {"input": 0.20, "output": 0.60},
            "Qwen/Qwen2.5-Coder-32B-Instruct": {"input": 0.20, "output": 0.60},
            "Qwen/Qwen3-Coder-480B-A35B-Instruct": {"input": 0.40, "output": 1.60},
            "meta-llama/Llama-3.3-70B-Instruct-Turbo": {"input": 0.10, "output": 0.32},
            "meta-llama/Meta-Llama-3.1-70B-Instruct": {"input": 0.40, "output": 0.40},
            "meta-llama/Meta-Llama-3.1-8B-Instruct": {"input": 0.02, "output": 0.05},
            "meta-llama/Llama-4-Scout-17B-16E-Instruct": {"input": 0.08, "output": 0.30},
            "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8": {"input": 0.15, "output": 0.60},
            "moonshotai/Kimi-K2-Instruct-0905": {"input": 0.40, "output": 2.00},
            "moonshotai/Kimi-K2.5": {"input": 0.45, "output": 2.25},
            "MiniMaxAI/MiniMax-M2.5": {"input": 0.27, "output": 0.95},
            # GLM models (via DeepInfra, formerly separate Zhipu AI provider)
            "zai-org/GLM-5": {"input": 0.80, "output": 2.56},
            "zai-org/GLM-4.7": {"input": 0.40, "output": 1.75},
            "zai-org/GLM-4.7-Flash": {"input": 0.06, "output": 0.40},
        },
    },
    "grok": {
        "display_name": "Grok (xAI)",
        "structured_output": {
            "method": StructuredOutputMethod.JSON_MODE,
            "strict_mode": False,
            "guaranteed": False,
        },
        "determinism": {
            "seed_support": True,  # OpenAI-compatible API supports seed
            "recommended_seed": 42,
        },
        "temperature": {
            "min": 0.0,
            "max": 2.0,
            "default": 0.0,
        },
        "cost_per_million_tokens": {
            "grok-4": {"input": 3.00, "output": 15.00},
            "grok-4-1-fast": {"input": 0.20, "output": 0.50},
            "grok-3": {"input": 3.00, "output": 15.00},
            "grok-3-mini": {"input": 0.30, "output": 0.50},
            "grok-3-beta": {"input": 5.00, "output": 15.00},
            "grok-3-mini-beta": {"input": 0.30, "output": 0.50},
        },
    },
    "mistral": {
        "display_name": "Mistral AI",
        "structured_output": {
            "method": StructuredOutputMethod.JSON_MODE,
            "strict_mode": False,
            "guaranteed": False,
        },
        "determinism": {
            "seed_support": True,  # Mistral supports random_seed parameter
            "recommended_seed": 42,
        },
        "temperature": {
            "min": 0.0,
            "max": 1.0,
            "default": 0.0,
        },
        "cost_per_million_tokens": {
            "mistral-large-latest": {"input": 0.50, "output": 1.50},
            "mistral-medium-latest": {"input": 0.40, "output": 2.00},
            "mistral-small-latest": {"input": 0.06, "output": 0.18},
            "magistral-medium-latest": {"input": 2.00, "output": 5.00},
            "magistral-small-latest": {"input": 0.50, "output": 1.00},
            "codestral-latest": {"input": 0.30, "output": 0.90},
            "devstral-latest": {"input": 0.40, "output": 0.90},
        },
    },
    "cohere": {
        "display_name": "Cohere",
        "structured_output": {
            "method": StructuredOutputMethod.JSON_MODE,
            "strict_mode": False,
            "guaranteed": False,
        },
        "determinism": {
            "seed_support": True,  # Cohere supports seed parameter
            "recommended_seed": 42,
        },
        "temperature": {
            "min": 0.0,
            "max": 1.0,
            "default": 0.0,
        },
        "cost_per_million_tokens": {
            "command-a-03-2025": {"input": 2.50, "output": 10.00},
            "command-r-plus-08-2024": {"input": 2.50, "output": 10.00},
            "command-r-08-2024": {"input": 0.15, "output": 0.60},
        },
    },
}


def get_provider_capability(provider: str, capability: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific capability for a provider.

    Args:
        provider: Provider name (e.g., 'openai', 'anthropic')
        capability: Capability key (e.g., 'structured_output', 'determinism')

    Returns:
        Capability dict or None if not found
    """
    provider_data = PROVIDER_CAPABILITIES.get(provider.lower())
    if not provider_data:
        return None
    return provider_data.get(capability)


def supports_feature(provider: str, feature: str) -> bool:
    """
    Check if a provider supports a specific feature.

    Args:
        provider: Provider name
        feature: Feature to check (e.g., 'seed', 'json_schema', 'tool_use')

    Returns:
        True if feature is supported
    """
    provider_lower = provider.lower()
    provider_data = PROVIDER_CAPABILITIES.get(provider_lower)
    if not provider_data:
        return False

    if feature == "seed":
        return provider_data.get("determinism", {}).get("seed_support", False)
    elif feature == "json_schema":
        structured = provider_data.get("structured_output", {})
        return structured.get("method") == StructuredOutputMethod.JSON_SCHEMA
    elif feature == "tool_use":
        structured = provider_data.get("structured_output", {})
        return structured.get("method") == StructuredOutputMethod.TOOL_USE
    elif feature == "json_mode":
        structured = provider_data.get("structured_output", {})
        return structured.get("method") in [
            StructuredOutputMethod.JSON_SCHEMA,
            StructuredOutputMethod.JSON_MODE
        ]
    elif feature == "guaranteed_json":
        structured = provider_data.get("structured_output", {})
        return structured.get("guaranteed", False)

    return False


def get_structured_output_method(provider: str) -> Optional[StructuredOutputMethod]:
    """
    Get the structured output method for a provider.

    Args:
        provider: Provider name

    Returns:
        StructuredOutputMethod enum value or None
    """
    structured = get_provider_capability(provider, "structured_output")
    if structured:
        return structured.get("method")
    return None


def get_model_cost(provider: str, model_name: str) -> Optional[ModelCost]:
    """
    Get cost information for a specific model.

    Args:
        provider: Provider name
        model_name: Model name

    Returns:
        ModelCost dataclass or None if not found
    """
    costs = get_provider_capability(provider, "cost_per_million_tokens")
    if not costs:
        return None

    # Try exact match first
    if model_name in costs:
        cost_data = costs[model_name]
        return ModelCost(input=cost_data["input"], output=cost_data["output"])

    # Try prefix match
    model_lower = model_name.lower()
    for model_key, cost_data in costs.items():
        if model_lower.startswith(model_key.lower()):
            return ModelCost(input=cost_data["input"], output=cost_data["output"])

    return None


def get_temperature_range(provider: str) -> Optional[TemperatureCapability]:
    """
    Get temperature range for a provider.

    Args:
        provider: Provider name

    Returns:
        TemperatureCapability dataclass or None
    """
    temp_data = get_provider_capability(provider, "temperature")
    if temp_data:
        return TemperatureCapability(
            min_value=temp_data["min"],
            max_value=temp_data["max"],
            default=temp_data["default"]
        )
    return None


def get_all_providers() -> List[str]:
    """Get list of all registered providers."""
    return list(PROVIDER_CAPABILITIES.keys())


def get_providers_with_guaranteed_json() -> List[str]:
    """Get list of providers that guarantee valid JSON output."""
    return [
        provider for provider in PROVIDER_CAPABILITIES
        if supports_feature(provider, "guaranteed_json")
    ]


def get_providers_with_seed_support() -> List[str]:
    """Get list of providers that support seed for determinism."""
    return [
        provider for provider in PROVIDER_CAPABILITIES
        if supports_feature(provider, "seed")
    ]


def get_provider_from_model(model_id: str) -> str:
    """Determine LLM provider from model ID string.

    Returns lowercase provider key matching PROVIDER_CAPABILITIES keys.
    Falls back to 'openai' for unknown models.
    """
    model_lower = model_id.lower()

    if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower or "o4" in model_lower:
        return "openai"
    if "claude" in model_lower:
        return "anthropic"
    if "gemini" in model_lower or "bard" in model_lower:
        return "google"
    if "grok" in model_lower:
        return "grok"
    if "mistral" in model_lower or "codestral" in model_lower or "devstral" in model_lower or "magistral" in model_lower:
        return "mistral"
    if "command" in model_lower or "cohere" in model_lower or "aya" in model_lower:
        return "cohere"
    if (
        "deepinfra" in model_lower
        or "llama" in model_lower
        or "qwen" in model_lower
        or "qwq" in model_lower
        or "kimi" in model_lower
        or "deepseek" in model_lower
        or "mixtral" in model_lower
        or "minimax" in model_lower
        or "glm" in model_lower
        or "zai-org" in model_lower
    ):
        return "deepinfra"
    return "openai"


def calculate_cost(
    provider: str,
    model_name: str,
    input_tokens: int,
    output_tokens: int
) -> Optional[float]:
    """
    Calculate the cost for a generation.

    Args:
        provider: Provider name
        model_name: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Cost in USD or None if cost info not available
    """
    model_cost = get_model_cost(provider, model_name)
    if not model_cost:
        return None

    input_cost = (input_tokens / 1_000_000) * model_cost.input
    output_cost = (output_tokens / 1_000_000) * model_cost.output

    return input_cost + output_cost


def get_provider_summary(provider: str) -> Optional[Dict[str, Any]]:
    """
    Get a summary of provider capabilities for UI display.

    Args:
        provider: Provider name

    Returns:
        Summary dict with display-friendly information
    """
    provider_data = PROVIDER_CAPABILITIES.get(provider.lower())
    if not provider_data:
        return None

    structured = provider_data.get("structured_output", {})
    determinism = provider_data.get("determinism", {})

    return {
        "provider": provider,
        "display_name": provider_data.get("display_name", provider.title()),
        "structured_output_method": structured.get("method", StructuredOutputMethod.PROMPT_BASED).value,
        "guaranteed_json": structured.get("guaranteed", False),
        "strict_schema": structured.get("strict_mode", False),
        "seed_support": determinism.get("seed_support", False),
        "temperature_range": f"{provider_data.get('temperature', {}).get('min', 0.0)}-{provider_data.get('temperature', {}).get('max', 1.0)}",
    }
