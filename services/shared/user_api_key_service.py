"""
User API Key Management Service
"""

import logging
from typing import Dict, List, Optional, Tuple

import httpx
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
        """Validate Anthropic API key via GET /v1/models."""
        if not api_key.startswith("sk-ant-"):
            return False, "Invalid Anthropic API key format", "invalid_format"
        try:
            import asyncio

            result = await asyncio.wait_for(self._make_anthropic_request(api_key), timeout=10.0)
            return result
        except asyncio.TimeoutError:
            return False, "Anthropic validation timeout", "timeout"
        except Exception as e:
            error_name = type(e).__name__
            if "AuthenticationError" in error_name:
                return False, "Invalid API key - please check your Anthropic key", "auth"
            return False, f"Anthropic validation failed: {str(e)}", "connection_error"

    async def _make_anthropic_request(self, api_key: str) -> Tuple[bool, str, str]:
        """Hit Anthropic's /v1/models endpoint to verify auth."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10.0,
            )
            if response.status_code == 200:
                return True, "Connection to Anthropic successful", "success"
            elif response.status_code == 401:
                return False, "Invalid API key - please check your Anthropic key", "auth"
            elif response.status_code == 429:
                return True, "Anthropic API key valid - rate limit reached", "quota"
            else:
                return False, f"Anthropic API error: {response.status_code}", "api_error"

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
        """Validate DeepInfra API key via GET /v1/openai/models."""
        return await self._validate_via_models_get(
            "DeepInfra",
            "https://api.deepinfra.com/v1/openai/models",
            {"Authorization": f"Bearer {api_key}"},
        )

    async def _validate_grok_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate xAI Grok API key via GET /v1/models (OpenAI-compatible)."""
        return await self._validate_via_models_get(
            "xAI (Grok)",
            "https://api.x.ai/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        )

    async def _validate_mistral_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate Mistral AI API key via GET /v1/models."""
        return await self._validate_via_models_get(
            "Mistral AI",
            "https://api.mistral.ai/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        )

    async def _validate_cohere_key(self, api_key: str) -> Tuple[bool, str, str]:
        """Validate Cohere API key via GET /v1/models."""
        return await self._validate_via_models_get(
            "Cohere",
            "https://api.cohere.com/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        )

    async def _validate_via_models_get(
        self, provider_label: str, url: str, headers: Dict[str, str]
    ) -> Tuple[bool, str, str]:
        """Shared GET /models auth check for OpenAI-compatible providers."""
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return True, f"Connection to {provider_label} successful", "success"
                    elif response.status in (401, 403):
                        return False, f"Invalid {provider_label} API key", "auth"
                    elif response.status == 429:
                        return True, f"{provider_label} API key valid - rate limit reached", "quota"
                    else:
                        return False, f"{provider_label} API error: {response.status}", "api_error"
        except Exception as e:
            error_name = type(e).__name__
            if "AuthenticationError" in error_name:
                return False, f"Invalid API key - please check your {provider_label} key", "auth"
            return False, f"{provider_label} validation failed: {str(e)}", "network"


async def validate_openai_compatible_endpoint(
    base_url: str,
    api_key: Optional[str] = None,
    timeout_seconds: float = 5.0,
) -> Tuple[bool, str, str]:
    """Probe an OpenAI-compatible endpoint via ``GET {base_url}/models``.

    BYOM (custom model) variant of ``_validate_via_models_get``: the URL is
    user-supplied, so the Authorization header is only sent when a key is
    given, and — SECURITY — every upstream detail is collapsed into one of
    three generic outcomes (auth / unreachable / invalid_response). Callers
    MUST run the SSRF url_guard on ``base_url`` before calling this; the
    generic messages here keep the endpoint from doubling as a port-scan
    oracle (no upstream status codes, bodies, or socket errors are echoed).

    DNS-rebinding immunity: this re-resolves ``base_url`` via
    ``resolve_and_validate`` at call time and PINS the outbound connection
    to the exact validated IPs, so a TTL-0 rebind between the caller's
    guard check and aiohttp's own lookup cannot reach an internal address.
    A rebinding rejection (ValueError) collapses into the generic
    "unreachable" outcome below — never an oracle.

    Returns ``(ok, message, error_type)`` like ``validate_api_key``.
    """
    try:
        import aiohttp

        from url_guard import pinned_connector, resolve_and_validate

        _normalized_url, validated_ips = resolve_and_validate(base_url)

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        url = f"{base_url.rstrip('/')}/models"
        async with aiohttp.ClientSession(
            connector=pinned_connector(validated_ips)
        ) as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                # SECURITY: never follow redirects. The caller ran url_guard
                # on base_url only; a 3xx to an internal/metadata host would
                # be followed to an address the guard was meant to fence off,
                # turning this probe into an SSRF/port-scan oracle.
                allow_redirects=False,
            ) as response:
                if 300 <= response.status < 400:
                    return (
                        False,
                        "Endpoint did not return a valid /models response",
                        "invalid_response",
                    )
                if response.status in (401, 403):
                    return (
                        False,
                        "Endpoint reachable, but authentication failed",
                        "auth",
                    )
                if response.status != 200:
                    return (
                        False,
                        "Endpoint did not return a valid /models response",
                        "invalid_response",
                    )
                try:
                    await response.json()
                except Exception:
                    return (
                        False,
                        "Endpoint did not return a valid /models response",
                        "invalid_response",
                    )
                return True, "Endpoint reachable — /models responded", "success"
    except Exception:
        # Timeout, DNS failure, connection refused, TLS error, ... — all
        # deliberately indistinguishable to the caller.
        return False, "Endpoint could not be reached", "unreachable"


def create_user_api_key_service(encryption_service) -> UserApiKeyService:
    """Factory function to create UserApiKeyService with encryption service dependency"""
    return UserApiKeyService(encryption_service)


# Create global singleton instance
from encryption_service import encryption_service
user_api_key_service = UserApiKeyService(encryption_service)
