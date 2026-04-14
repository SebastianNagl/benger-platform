"""
User-aware AI service that routes requests to user-specific API keys
"""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from .anthropic_service import AnthropicService
from .cohere_service import CohereService
from .deepinfra_service import DeepInfraService
from .google_service import GoogleService
from .grok_service import GrokService
from .mistral_service import MistralService
from .openai_service import OpenAIService
import sys
import os

# User API key service is in the parent shared directory
parent_dir = os.path.dirname(os.path.dirname(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from user_api_key_service import user_api_key_service

logger = logging.getLogger(__name__)


class UserAwareAIService:
    """Service that creates AI service instances with user-specific API keys"""

    def __init__(self):
        pass

    def get_ai_service_for_user(
        self, db: Session, user_id: str, provider: str, organization_id: str = None
    ) -> Optional[Any]:
        """Get AI service instance configured with user's or org's API key"""
        try:
            # Resolve API key based on context (Issue #1180)
            if organization_id:
                try:
                    from shared_org_api_key_service import org_api_key_service

                    if org_api_key_service is not None:
                        user_api_key = org_api_key_service.resolve_api_key(
                            db, user_id, organization_id, provider
                        )
                    else:
                        logger.warning(
                            f"org_api_key_service is None - falling back to user key for {provider}"
                        )
                        user_api_key = user_api_key_service.get_user_api_key(db, user_id, provider)
                except ImportError:
                    user_api_key = user_api_key_service.get_user_api_key(db, user_id, provider)
            else:
                user_api_key = user_api_key_service.get_user_api_key(db, user_id, provider)

            if not user_api_key:
                logger.warning(f"No API key found for user {user_id} and provider {provider}")
                return None

            provider_lower = provider.lower()

            if provider_lower == "openai":
                return UserSpecificOpenAIService(user_api_key)
            elif provider_lower == "anthropic":
                return UserSpecificAnthropicService(user_api_key)
            elif provider_lower == "google":
                return UserSpecificGoogleService(user_api_key)
            elif provider_lower == "deepinfra":
                return UserSpecificDeepInfraService(user_api_key)
            elif provider_lower == "grok":
                return UserSpecificGrokService(user_api_key)
            elif provider_lower == "mistral":
                return UserSpecificMistralService(user_api_key)
            elif provider_lower == "cohere":
                return UserSpecificCohereService(user_api_key)
            else:
                logger.error(f"Unsupported provider: {provider}")
                return None

        except Exception as e:
            logger.error(f"Error creating user-specific AI service: {e}")
            return None

    def get_ai_service_for_model(
        self, db: Session, user_id: str, model_provider: str
    ) -> Optional[Any]:
        """Get AI service for a specific model provider with user's API key"""
        return self.get_ai_service_for_user(db, user_id, model_provider)


class UserSpecificOpenAIService(OpenAIService):
    """OpenAI service with user-specific API key"""

    def __init__(self, api_key: str):
        # Don't call super().__init__() to avoid using global API key
        self.api_key = api_key
        if self.api_key:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
                logger.info("✅ User-specific OpenAI client initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize user-specific OpenAI client: {e}")
                self.client = None
        else:
            self.client = None


class UserSpecificAnthropicService(AnthropicService):
    """Anthropic service with user-specific API key"""

    def __init__(self, api_key: str):
        # Don't call super().__init__() to avoid using global API key
        self.api_key = api_key
        if self.api_key:
            try:
                import anthropic

                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info("✅ User-specific Anthropic client initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize user-specific Anthropic client: {e}")
                self.client = None
        else:
            self.client = None


class UserSpecificGoogleService(GoogleService):
    """Google service with user-specific API key"""

    def __init__(self, api_key: str):
        # Don't call super().__init__() to avoid using global API key
        self.api_key = api_key
        if self.api_key:
            try:
                from google import genai

                self.client = genai.Client(api_key=self.api_key)
                logger.info("User-specific Google client initialized")
            except ImportError:
                logger.error("google-genai package not installed")
                self.client = None
            except Exception as e:
                logger.error(f"Failed to initialize user-specific Google client: {e}")
                self.client = None
        else:
            self.client = None


class UserSpecificDeepInfraService(DeepInfraService):
    """DeepInfra service with user-specific API key"""

    def __init__(self, api_key: str):
        # Don't call super().__init__() to avoid using global API key
        self.api_key = api_key
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

        if self.api_key:
            self.client = True  # Simple flag to indicate we have API key
            logger.info("User-specific DeepInfra client initialized")
        else:
            self.client = None


class UserSpecificGrokService(GrokService):
    """Grok service with user-specific API key"""

    def __init__(self, api_key: str):
        # Don't call super().__init__() to avoid using global API key
        self.api_key = api_key
        self.base_url = "https://api.x.ai/v1"
        if self.api_key:
            self.client = True  # Flag to indicate we have API key
            logger.info("User-specific Grok client initialized")
        else:
            self.client = None


class UserSpecificMistralService(MistralService):
    """Mistral service with user-specific API key"""

    def __init__(self, api_key: str):
        # Don't call super().__init__() to avoid using global API key
        self.api_key = api_key
        if self.api_key:
            try:
                try:
                    from mistralai import Mistral
                except ImportError:
                    from mistralai.client import Mistral
                self.client = Mistral(api_key=self.api_key)
                logger.info("User-specific Mistral client initialized")
            except ImportError:
                logger.error("mistralai package not installed")
                self.client = None
            except Exception as e:
                logger.error(f"Failed to initialize user-specific Mistral client: {e}")
                self.client = None
        else:
            self.client = None


class UserSpecificCohereService(CohereService):
    """Cohere service with user-specific API key"""

    def __init__(self, api_key: str):
        # Don't call super().__init__() to avoid using global API key
        self.api_key = api_key
        if self.api_key:
            try:
                import cohere
                self.client = cohere.ClientV2(api_key=self.api_key)
                logger.info("User-specific Cohere client initialized")
            except ImportError:
                logger.error("cohere package not installed")
                self.client = None
            except Exception as e:
                logger.error(f"Failed to initialize user-specific Cohere client: {e}")
                self.client = None
        else:
            self.client = None


# Global service instance
user_aware_ai_service = UserAwareAIService()
