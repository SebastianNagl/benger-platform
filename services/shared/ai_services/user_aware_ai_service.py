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
from .openai_compatible_service import OpenAICompatibleService
from .openai_service import OpenAIService
import sys
import os

# User API key service is in the parent shared directory
parent_dir = os.path.dirname(os.path.dirname(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from user_api_key_service import user_api_key_service

logger = logging.getLogger(__name__)


def _user_can_use_custom_model(db: Session, user_id: str, model: Any) -> bool:
    """Access check for custom (BYOM) models: creator, public, org-shared
    (active membership), or superadmin.

    Enforced INSIDE the factory as defense in depth: every consumer
    (generation worker, LLM-judge paths, future callers) goes through
    here, so a guessed custom-<uuid> id can never be used by someone the
    model isn't shared with — including keyless (requires_api_key=False)
    endpoints where no missing-credential error would stop them.
    """
    if getattr(model, "is_public", False):
        return True
    if model.created_by and str(model.created_by) == str(user_id):
        return True
    try:
        from models import ModelOrganization, OrganizationMembership, User

        user = db.query(User).filter(User.id == user_id).first()
        if user and getattr(user, "is_superadmin", False):
            return True

        model_org_ids = {
            row[0]
            for row in db.query(ModelOrganization.organization_id)
            .filter(ModelOrganization.model_id == model.id)
            .all()
        }
        if not model_org_ids:
            return False
        memberships = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.is_active.is_(True),
            )
            .all()
        )
        return any(m.organization_id in model_org_ids for m in memberships)
    except Exception as e:
        logger.error(f"Custom-model access check failed for {model.id}: {e}")
        return False


class UserAwareAIService:
    """Service that creates AI service instances with user-specific API keys"""

    def __init__(self):
        pass

    def get_ai_service_for_user(
        self, db: Session, user_id: str, provider: str, organization_id: str = None
    ) -> Optional[Any]:
        """Get AI service instance configured with user's or org's API key.

        Phase 6.5: records the actual key-resolution route on the
        returned service instance via ``service._key_resolution_route``
        so downstream response_metadata can include it. Without this, a
        Generation row shows the provider name (``openai``) but never
        which key actually billed for it (org's vs. user's).
        """
        # Custom (BYOM) models cannot be resolved by provider name alone —
        # they need the model row (base_url, endpoint_model_name,
        # per-(user, model) credential). Refuse loudly instead of falling
        # into the SDK map and producing a misleading "no key" error.
        if provider and provider.lower() == "custom":
            logger.error(
                "Provider 'custom' requires the model row - use get_ai_service_for_model_row"
            )
            return None

        # Track which path we took so the caller can persist it.
        key_route = "user_key"  # default
        try:
            # Resolve API key based on context (Issue #1180)
            if organization_id:
                try:
                    from shared_org_api_key_service import org_api_key_service

                    if org_api_key_service is not None:
                        user_api_key = org_api_key_service.resolve_api_key(
                            db, user_id, organization_id, provider
                        )
                        # The org service returns either the org's shared
                        # key or falls through to the user's depending on
                        # require_private_keys; record the higher-level
                        # decision so a researcher tracing billing can
                        # at least see the org context was honored.
                        key_route = "org_resolved" if user_api_key else "org_resolved_failed"
                    else:
                        logger.warning(
                            f"org_api_key_service is None - falling back to user key for {provider}"
                        )
                        user_api_key = user_api_key_service.get_user_api_key(db, user_id, provider)
                        key_route = "user_key_fallback_org_service_unavailable"
                except ImportError:
                    user_api_key = user_api_key_service.get_user_api_key(db, user_id, provider)
                    key_route = "user_key_fallback_org_service_missing"
            else:
                user_api_key = user_api_key_service.get_user_api_key(db, user_id, provider)
                key_route = "user_key"

            if not user_api_key:
                logger.warning(f"No API key found for user {user_id} and provider {provider}")
                return None

            provider_lower = provider.lower()

            service_class_map = {
                "openai": UserSpecificOpenAIService,
                "anthropic": UserSpecificAnthropicService,
                "google": UserSpecificGoogleService,
                "deepinfra": UserSpecificDeepInfraService,
                "grok": UserSpecificGrokService,
                "mistral": UserSpecificMistralService,
                "cohere": UserSpecificCohereService,
            }
            cls = service_class_map.get(provider_lower)
            if cls is None:
                logger.error(f"Unsupported provider: {provider}")
                return None

            service = cls(user_api_key)
            # Phase 6.5: stamp the key-resolution route + invocation
            # context on the service instance so each response_metadata
            # can include them. Generation rows can then be filtered by
            # billing path / org context when reproducing benchmarks.
            service._key_resolution_route = key_route
            service._provider_name = provider_lower
            service._invocation_user_id = user_id
            service._invocation_organization_id = organization_id
            return service

        except Exception as e:
            logger.error(f"Error creating user-specific AI service: {e}")
            return None

    def get_ai_service_for_model(
        self, db: Session, user_id: str, model_provider: str
    ) -> Optional[Any]:
        """Get AI service for a specific model provider with user's API key"""
        return self.get_ai_service_for_user(db, user_id, model_provider)

    def get_ai_service_for_model_row(
        self, db: Session, user_id: str, model: Any, organization_id: str = None
    ) -> Optional[Any]:
        """Resolve an AI service from an llm_models ROW (BYOM-aware).

        Official rows delegate to the provider-keyed path
        (get_ai_service_for_user). Custom rows build an OpenAI-compatible
        client from the row's base_url/endpoint_model_name with strictly
        the INVOKING user's per-(user, model) credential — never the model
        owner's key, and deliberately outside the org
        ``require_private_keys`` shared-billing machinery.

        Returns None when a requires_api_key custom model has no stored
        credential for this user (callers surface a "add your key for this
        model" error).
        """
        if getattr(model, "is_official", True):
            return self.get_ai_service_for_user(
                db, user_id, model.provider, organization_id=organization_id
            )

        try:
            if not model.is_active:
                logger.warning(f"Custom model {model.id} is inactive (deleted)")
                return None
            if not _user_can_use_custom_model(db, user_id, model):
                logger.warning(
                    f"User {user_id} has no access to custom model {model.id}"
                )
                return None

            from custom_model_credential_service import get_credential

            api_key = get_credential(db, user_id, str(model.id))
            if getattr(model, "requires_api_key", True) and not api_key:
                logger.warning(
                    f"No custom-model credential stored for user {user_id} "
                    f"and model {model.id}"
                )
                return None

            constraints = model.parameter_constraints or {}
            seed_cfg = constraints.get("seed") or {}

            service = OpenAICompatibleService(
                base_url=model.base_url,
                api_key=api_key,
                endpoint_model_name=model.endpoint_model_name,
                input_cost_per_million=model.input_cost_per_million,
                output_cost_per_million=model.output_cost_per_million,
                supports_seed=bool(seed_cfg.get("supported", False)),
            )
            service._key_resolution_route = (
                "custom_model_user_credential" if api_key else "custom_model_no_auth"
            )
            service._provider_name = "custom"
            service._invocation_user_id = user_id
            service._invocation_organization_id = organization_id
            return service

        except Exception as e:
            logger.error(f"Error creating custom-model AI service: {e}")
            return None


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
