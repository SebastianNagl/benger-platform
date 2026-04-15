"""
Shared AI services module.
Contains base implementations of AI service integrations used by both API and Workers.
"""

from .base_service import BaseAIService
from .openai_service import OpenAIService
from .anthropic_service import AnthropicService
from .google_service import GoogleService
from .deepinfra_service import DeepInfraService
from .grok_service import GrokService
from .mistral_service import MistralService
from .cohere_service import CohereService
from .user_aware_ai_service import user_aware_ai_service
from .schema_generator import (
    generate_json_schema_from_label_config,
    generate_format_instructions,
    extract_field_names,
)
from .provider_capabilities import (
    PROVIDER_CAPABILITIES,
    StructuredOutputMethod,
    get_provider_capability,
    supports_feature,
    get_structured_output_method,
    get_model_cost,
    get_temperature_range,
    get_all_providers,
    get_providers_with_guaranteed_json,
    get_providers_with_seed_support,
    calculate_cost,
    get_provider_summary,
)
from .response_validator import (
    ResponseValidator,
    ValidationResult,
    RepairResult,
    validate_structured_response,
)

__all__ = [
    "BaseAIService",
    "OpenAIService",
    "AnthropicService",
    "GoogleService",
    "DeepInfraService",
    "GrokService",
    "MistralService",
    "CohereService",
    "user_aware_ai_service",
    "generate_json_schema_from_label_config",
    "generate_format_instructions",
    "extract_field_names",
    # Provider capabilities
    "PROVIDER_CAPABILITIES",
    "StructuredOutputMethod",
    "get_provider_capability",
    "supports_feature",
    "get_structured_output_method",
    "get_model_cost",
    "get_temperature_range",
    "get_all_providers",
    "get_providers_with_guaranteed_json",
    "get_providers_with_seed_support",
    "calculate_cost",
    "get_provider_summary",
    # Response validation
    "ResponseValidator",
    "ValidationResult",
    "RepairResult",
    "validate_structured_response",
]