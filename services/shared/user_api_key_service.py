"""
User API Key Management Service
"""

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class UserApiKeyService:
    """Service for managing user API keys"""

    def __init__(self, encryption_service):
        self.encryption_service = encryption_service

    def set_user_api_key(self, db: Session, user_id: str, provider: str, api_key: str) -> bool:
        """Set API key for a user and provider"""
        try:
            # Validate API key format
            if not self.encryption_service.is_valid_api_key_format(api_key, provider):
                logger.warning(f"Invalid API key format for provider {provider}")
                return False

            # Encrypt the API key
            encrypted_key = self.encryption_service.encrypt_api_key(api_key)
            if not encrypted_key:
                logger.error("Failed to encrypt API key")
                return False

            # Get user and update the appropriate field
            from models import User
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"User {user_id} not found")
                return False

            provider_lower = provider.lower()
            if provider_lower == "openai":
                user.encrypted_openai_api_key = encrypted_key
            elif provider_lower == "anthropic":
                user.encrypted_anthropic_api_key = encrypted_key
            elif provider_lower == "google":
                user.encrypted_google_api_key = encrypted_key
            elif provider_lower == "deepinfra":
                user.encrypted_deepinfra_api_key = encrypted_key
            elif provider_lower == "grok":
                user.encrypted_grok_api_key = encrypted_key
            elif provider_lower == "mistral":
                user.encrypted_mistral_api_key = encrypted_key
            elif provider_lower == "cohere":
                user.encrypted_cohere_api_key = encrypted_key
            else:
                logger.error(f"Unsupported provider: {provider}")
                return False

            db.commit()
            logger.info(f"API key set for user {user_id} and provider {provider}")
            return True

        except Exception as e:
            logger.error(f"Error setting API key: {e}")
            db.rollback()
            return False

    def get_user_api_key(self, db: Session, user_id: str, provider: str) -> Optional[str]:
        """Get decrypted API key for a user and provider"""
        try:
            from models import User
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None

            provider_lower = provider.lower()
            encrypted_key = None

            if provider_lower == "openai":
                encrypted_key = user.encrypted_openai_api_key
            elif provider_lower == "anthropic":
                encrypted_key = user.encrypted_anthropic_api_key
            elif provider_lower == "google":
                encrypted_key = user.encrypted_google_api_key
            elif provider_lower == "deepinfra":
                encrypted_key = user.encrypted_deepinfra_api_key
            elif provider_lower == "grok":
                encrypted_key = user.encrypted_grok_api_key
            elif provider_lower == "mistral":
                encrypted_key = user.encrypted_mistral_api_key
            elif provider_lower == "cohere":
                encrypted_key = user.encrypted_cohere_api_key

            if not encrypted_key:
                return None

            return self.encryption_service.decrypt_api_key(encrypted_key)

        except Exception as e:
            logger.error(f"Error getting API key: {e}")
            return None

    def remove_user_api_key(self, db: Session, user_id: str, provider: str) -> bool:
        """Remove API key for a user and provider"""
        try:
            from models import User
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False

            provider_lower = provider.lower()
            if provider_lower == "openai":
                user.encrypted_openai_api_key = None
            elif provider_lower == "anthropic":
                user.encrypted_anthropic_api_key = None
            elif provider_lower == "google":
                user.encrypted_google_api_key = None
            elif provider_lower == "deepinfra":
                user.encrypted_deepinfra_api_key = None
            elif provider_lower == "grok":
                user.encrypted_grok_api_key = None
            elif provider_lower == "mistral":
                user.encrypted_mistral_api_key = None
            elif provider_lower == "cohere":
                user.encrypted_cohere_api_key = None
            else:
                return False

            db.commit()
            logger.info(f"API key removed for user {user_id} and provider {provider}")
            return True

        except Exception as e:
            logger.error(f"Error removing API key: {e}")
            db.rollback()
            return False

    def get_user_available_providers(self, db: Session, user_id: str) -> List[str]:
        """Get list of providers for which user has valid API keys"""
        try:
            from models import User
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return []

            providers = []

            if user.encrypted_openai_api_key:
                providers.append("OpenAI")
            if user.encrypted_anthropic_api_key:
                providers.append("Anthropic")
            if user.encrypted_google_api_key:
                providers.append("Google")
            if user.encrypted_deepinfra_api_key:
                providers.append("DeepInfra")
            if user.encrypted_grok_api_key:
                providers.append("Grok")
            if user.encrypted_mistral_api_key:
                providers.append("Mistral")
            if user.encrypted_cohere_api_key:
                providers.append("Cohere")

            return providers

        except Exception as e:
            logger.error(f"Error getting available providers: {e}")
            return []

    def get_user_api_key_status(self, db: Session, user_id: str) -> Dict[str, bool]:
        """Get status of API keys for all providers"""
        try:
            from models import User
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {}

            return {
                "openai": bool(user.encrypted_openai_api_key),
                "anthropic": bool(user.encrypted_anthropic_api_key),
                "google": bool(user.encrypted_google_api_key),
                "deepinfra": bool(user.encrypted_deepinfra_api_key),
                "grok": bool(user.encrypted_grok_api_key),
                "mistral": bool(user.encrypted_mistral_api_key),
                "cohere": bool(user.encrypted_cohere_api_key),
            }

        except Exception as e:
            logger.error(f"Error getting API key status: {e}")
            return {}

    async def validate_api_key(self, api_key: str, provider: str) -> Tuple[bool, str, str]:
        """
        Validate API key by making a test request to the provider

        Returns:
            tuple[bool, str, str]: (is_valid, message, error_type)
            error_type can be: "auth", "network", "quota", "timeout", "unknown"
        """
        try:
            provider_lower = provider.lower()

            if provider_lower == "openai":
                return await self._validate_openai_key(api_key)
            elif provider_lower == "anthropic":
                return await self._validate_anthropic_key(api_key)
            elif provider_lower == "google":
                return await self._validate_google_key(api_key)
            elif provider_lower == "deepinfra":
                return await self._validate_deepinfra_key(api_key)
            elif provider_lower == "grok":
                return await self._validate_grok_key(api_key)
            elif provider_lower == "mistral":
                return await self._validate_mistral_key(api_key)
            elif provider_lower == "cohere":
                return await self._validate_cohere_key(api_key)

            return False, f"Unsupported provider: {provider}", "unknown"

        except Exception as e:
            logger.error(f"Error validating API key for {provider}: {e}")
            return False, f"Validation error: {str(e)}", "unknown"

    async def _validate_openai_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate OpenAI API key"""
        try:
            import asyncio

            import openai
            from openai import OpenAI

            client = OpenAI(api_key=api_key, timeout=30.0)

            # Test with a simple request
            try:
                # Run the synchronous call in a thread pool with timeout
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda: client.models.list()),
                    timeout=30.0,
                )
                return True, "Connection to OpenAI successful", "success"
            except openai.AuthenticationError:
                logger.warning("OpenAI API key authentication failed")
                return False, "Invalid API key - please check your OpenAI key", "auth"
            except openai.RateLimitError:
                logger.info("OpenAI API key valid but rate limited")
                return True, "API key valid (rate limit reached)", "quota"
            except openai.PermissionDeniedError:
                logger.warning("OpenAI API key permission denied")
                return False, "API key lacks required permissions", "auth"
            except asyncio.TimeoutError:
                logger.warning("OpenAI API key validation timeout")
                return False, "Connection timeout - please check your network", "timeout"
            except Exception as inner_e:
                error_str = str(inner_e).lower()
                if (
                    "authentication" in error_str
                    or "invalid" in error_str
                    or "unauthorized" in error_str
                ):
                    return False, "Invalid API key - authentication failed", "auth"
                elif "timeout" in error_str or "timed out" in error_str:
                    return False, "Connection timeout - please check your network", "timeout"
                elif "network" in error_str or "connection" in error_str:
                    return False, "Network error - please check your connection", "network"
                else:
                    # For other errors (rate limits, etc.), consider the key valid
                    logger.info(f"OpenAI key validation succeeded despite error: {inner_e}")
                    return True, f"API key valid (service issue: {str(inner_e)})", "quota"
        except Exception as e:
            logger.warning(f"OpenAI API key validation failed: {e}")
            error_str = str(e).lower()
            if "timeout" in error_str:
                return False, "Connection timeout - please check your network", "timeout"
            elif "network" in error_str or "connection" in error_str:
                return False, "Network error - please check your connection", "network"
            else:
                return False, f"Validation failed: {str(e)}", "unknown"

    async def _validate_anthropic_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate Anthropic API key"""
        try:
            import asyncio

            import anthropic

            client = anthropic.Anthropic(api_key=api_key, timeout=30.0)

            # Test with a minimal request - just validate the API key works
            try:
                # Run the synchronous call in a thread pool with timeout
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: client.messages.create(
                            model="claude-3-haiku-20240307",
                            max_tokens=1,
                            messages=[{"role": "user", "content": "test"}],
                        ),
                    ),
                    timeout=30.0,
                )
                return True, "Connection to Anthropic successful", "success"
            except anthropic.AuthenticationError:
                logger.warning("Anthropic API key authentication failed")
                return False, "Invalid API key - please check your Anthropic key", "auth"
            except anthropic.RateLimitError:
                logger.info("Anthropic API key valid but rate limited")
                return True, "API key valid (rate limit reached)", "quota"
            except anthropic.PermissionDeniedError:
                logger.warning("Anthropic API key permission denied")
                return False, "API key lacks required permissions", "auth"
            except asyncio.TimeoutError:
                logger.warning("Anthropic API key validation timeout")
                return False, "Connection timeout - please check your network", "timeout"
            except Exception as inner_e:
                error_str = str(inner_e).lower()
                if (
                    "authentication" in error_str
                    or "invalid" in error_str
                    or "unauthorized" in error_str
                ):
                    return False, "Invalid API key - authentication failed", "auth"
                elif "timeout" in error_str or "timed out" in error_str:
                    return False, "Connection timeout - please check your network", "timeout"
                elif "network" in error_str or "connection" in error_str:
                    return False, "Network error - please check your connection", "network"
                elif "rate limit" in error_str or "quota" in error_str:
                    return True, "API key valid (rate limit reached)", "quota"
                else:
                    # For other errors, consider the key valid if it's not clearly auth-related
                    logger.info(f"Anthropic key validation succeeded despite error: {inner_e}")
                    return True, f"API key valid (service issue: {str(inner_e)})", "quota"
        except Exception as e:
            logger.warning(f"Anthropic API key validation failed: {e}")
            error_str = str(e).lower()
            if "timeout" in error_str:
                return False, "Connection timeout - please check your network", "timeout"
            elif "network" in error_str or "connection" in error_str:
                return False, "Network error - please check your connection", "network"
            else:
                return False, f"Validation failed: {str(e)}", "unknown"

    async def _validate_google_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate Google API key via Gemini REST API"""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return True, "Connection to Google successful", "success"
                    elif response.status in (400, 403):
                        return False, "Invalid API key - please check your Google key", "auth"
                    elif response.status == 429:
                        return True, "API key valid (rate limit reached)", "quota"
                    else:
                        return False, f"Google API error: {response.status}", "unknown"
        except Exception as e:
            error_str = str(e).lower()
            if "timeout" in error_str:
                return False, "Connection timeout - please check your network", "timeout"
            return False, f"Validation failed: {str(e)}", "unknown"

    async def _validate_deepinfra_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate DeepInfra API key"""
        try:
            import asyncio

            import aiohttp

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            # DeepInfra doesn't have a /models endpoint, so we test with a minimal chat completion
            payload = {
                "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
                "temperature": 0.0,
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.deepinfra.com/v1/openai/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status == 200:
                            return True, "Connection to DeepInfra successful", "success"
                        elif response.status == 401:
                            # 401 means invalid API key
                            return (
                                False,
                                "Invalid API key - please check your DeepInfra key",
                                "auth",
                            )
                        elif response.status == 429:
                            # Rate limit
                            return True, "API key valid (rate limit reached)", "quota"
                        elif response.status == 402:
                            # Payment required / quota exceeded
                            return True, "API key valid (quota exceeded)", "quota"
                        else:
                            # Other errors - check response content
                            error_text = await response.text()
                            error_lower = error_text.lower()
                            if (
                                "authentication" in error_lower
                                or "invalid" in error_lower
                                or "unauthorized" in error_lower
                            ):
                                return False, "Invalid API key - authentication failed", "auth"
                            elif "quota" in error_lower or "limit" in error_lower:
                                return True, "API key valid (quota/limit reached)", "quota"
                            else:
                                # For other errors, consider the key valid but service has issues
                                logger.info(
                                    f"DeepInfra key validation succeeded despite status {response.status}"
                                )
                                return (
                                    True,
                                    f"API key valid (service issue: HTTP {response.status})",
                                    "quota",
                                )
            except aiohttp.ClientError as e:
                error_str = str(e).lower()
                if "timeout" in error_str:
                    return False, "Connection timeout - please check your network", "timeout"
                else:
                    return False, "Network error - please check your connection", "network"
            except asyncio.TimeoutError:
                return False, "Connection timeout - please check your network", "timeout"
        except Exception as e:
            logger.warning(f"DeepInfra API key validation failed: {e}")
            error_str = str(e).lower()
            if "timeout" in error_str:
                return False, "Connection timeout - please check your network", "timeout"
            elif "network" in error_str or "connection" in error_str:
                return False, "Network error - please check your connection", "network"
            else:
                return False, f"Validation failed: {str(e)}", "unknown"

    async def _validate_grok_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate xAI Grok API key"""
        try:
            import asyncio
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "grok-3",
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 1,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return True, "Connection to xAI (Grok) successful", "success"
                    elif response.status == 401:
                        return False, "Invalid API key - please check your Grok key", "auth"
                    elif response.status == 429:
                        return True, "API key valid (rate limit reached)", "quota"
                    else:
                        return False, f"Grok API error: {response.status}", "unknown"
        except asyncio.TimeoutError:
            return False, "Connection timeout - please check your network", "timeout"
        except Exception as e:
            logger.warning(f"Grok API key validation failed: {e}")
            return False, f"Validation failed: {str(e)}", "unknown"

    async def _validate_mistral_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate Mistral AI API key"""
        try:
            import asyncio
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.mistral.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "mistral-small-latest",
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 1,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return True, "Connection to Mistral AI successful", "success"
                    elif response.status == 401:
                        return False, "Invalid API key - please check your Mistral key", "auth"
                    elif response.status == 429:
                        return True, "API key valid (rate limit reached)", "quota"
                    else:
                        return False, f"Mistral API error: {response.status}", "unknown"
        except asyncio.TimeoutError:
            return False, "Connection timeout - please check your network", "timeout"
        except Exception as e:
            logger.warning(f"Mistral API key validation failed: {e}")
            return False, f"Validation failed: {str(e)}", "unknown"

    async def _validate_cohere_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate Cohere API key"""
        try:
            import asyncio
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.cohere.com/v2/chat",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "command-r-08-2024",
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 1,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return True, "Connection to Cohere successful", "success"
                    elif response.status == 401:
                        return False, "Invalid API key - please check your Cohere key", "auth"
                    elif response.status == 429:
                        return True, "API key valid (rate limit reached)", "quota"
                    else:
                        return False, f"Cohere API error: {response.status}", "unknown"
        except asyncio.TimeoutError:
            return False, "Connection timeout - please check your network", "timeout"
        except Exception as e:
            logger.warning(f"Cohere API key validation failed: {e}")
            return False, f"Validation failed: {str(e)}", "unknown"


def create_user_api_key_service(encryption_service) -> UserApiKeyService:
    """Factory function to create UserApiKeyService with encryption service dependency"""
    return UserApiKeyService(encryption_service)


# Create global singleton instance
from encryption_service import encryption_service
user_api_key_service = UserApiKeyService(encryption_service)