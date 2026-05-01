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
        "models_supporting_json_schema": [
            "gpt-4o", "gpt-4o-mini", "gpt-4o-2024",
            "gpt-4-turbo", "gpt-4-turbo-preview",
            "gpt-4-0125-preview", "gpt-4-1106-preview",
            "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.4",
            "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4-pro",
            "gpt-5.5", "gpt-5.5-pro",
            "gpt-5-mini", "gpt-5-nano",
            "o1", "o3", "o3-pro", "o4-mini",
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


_COST_CACHE: Optional[Dict[str, Dict[str, "ModelCost"]]] = None


def _load_costs_from_catalog() -> Dict[str, Dict[str, "ModelCost"]]:
    """Build {provider_lower: {model_id: ModelCost}} from llm_models.yaml."""
    # Imported lazily so that this module remains usable when the loader
    # path resolution differs (e.g., tests that monkeypatch sys.path).
    from seeds.llm_models_loader import load_catalog

    catalog = load_catalog()
    by_provider: Dict[str, Dict[str, ModelCost]] = {}
    for m in catalog.models:
        if m.get("input_cost_per_million") is None or m.get("output_cost_per_million") is None:
            continue
        provider = (m["provider"] or "").lower()
        by_provider.setdefault(provider, {})[m["id"]] = ModelCost(
            input=float(m["input_cost_per_million"]),
            output=float(m["output_cost_per_million"]),
        )
    return by_provider


def reload_cost_cache() -> None:
    """Clear the in-memory cost cache so the next lookup re-reads the YAML."""
    global _COST_CACHE
    _COST_CACHE = None


def get_model_cost(provider: str, model_name: str) -> Optional[ModelCost]:
    """Get cost information for a specific model.

    Costs are sourced from `services/api/seeds/llm_models.yaml` (the same
    file the seed function loads). The result is cached in-process; call
    `reload_cost_cache()` after editing the YAML in a long-running process.
    """
    global _COST_CACHE
    if _COST_CACHE is None:
        _COST_CACHE = _load_costs_from_catalog()

    provider_costs = _COST_CACHE.get(provider.lower())
    if not provider_costs:
        return None

    if model_name in provider_costs:
        return provider_costs[model_name]

    # Prefix match for snapshot suffixes (e.g. "claude-3-5-sonnet" -> "claude-3-5-sonnet-20241022")
    model_lower = model_name.lower()
    for key, cost in provider_costs.items():
        if model_lower.startswith(key.lower()):
            return cost
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
    if (
        "mistral" in model_lower
        or "ministral" in model_lower
        or "codestral" in model_lower
        or "devstral" in model_lower
        or "magistral" in model_lower
    ):
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
        or "stepfun-ai" in model_lower
        or "nvidia/" in model_lower
        or "nemotron" in model_lower
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
